#!/usr/bin/env bash
# Smoke-test Labs target bench receipt generation without target hardware.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [ -z "${GPR_EXTERNAL_ROOT:-}" ]; then
  if [ -d /Volumes/OWC_8TB/gpr_work ]; then
    GPR_EXTERNAL_ROOT="/Volumes/OWC_8TB/gpr_work"
  else
    GPR_EXTERNAL_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/gpr_work"
  fi
fi
GPR_TMPDIR="${GPR_TMPDIR:-$GPR_EXTERNAL_ROOT/tmp}"
WORK=${WORK:-$GPR_TMPDIR/labs_target_bench_smoke}
PYTHON_BIN="${PYTHON_BIN:-python3}"

rm -rf "$WORK"
mkdir -p "$WORK"

"$PYTHON_BIN" "$REPO/tools/run_labs_target_bench.py" \
  --simulate \
  --frames 8 \
  --output-dir "$WORK" \
  --capture-width 640 \
  --capture-height 360 \
  --target-fps 24

"$PYTHON_BIN" - "$WORK/labs_target_bench.json" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text())
assert receipt["schema"] == "gpr_labs_target_bench.v1"
assert receipt["simulated"] is True
assert receipt["capture"]["frames_requested"] == 8
assert receipt["capture"]["frames_written"] == 8
assert receipt["capture"]["dropped_frames"] == 0
assert receipt["gvid"]["validation"]["frame_count"] == 8
assert receipt["interruption_recovery"]["validator_rejects_truncated"] is True
assert receipt["interruption_recovery"]["complete_frames_recovered"] == 7
assert receipt["fused_timing"]["available"] is False
assert receipt["fused_timing"]["timing_line_count"] == 0
assert "bench_child_maxrss_kb" in receipt["memory"]
assert "loadavg_start" in receipt["cpu"]
assert receipt["verdict"]["gvid_valid"] is True
assert receipt["verdict"]["target_evidence"] is False
PY

cat > "$WORK/fake_bench.py" <<'PY'
#!/usr/bin/env python3
import os
import struct
import sys
from pathlib import Path

raw, w, h, n = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
assert Path(raw).is_file()
out = os.environ.get("GPR_BENCH_GVID")
assert out
with open(out, "wb") as f:
    f.write(struct.pack("<IBBHHHIIIII", 0x44495647, 1, 0, 4, 3, 0, w, h, 24000, 0, n))
    for idx in range(n):
        payload = (f"direct-frame-{idx}\n".encode("ascii") * 3)
        f.write(struct.pack("<IIQ", 0x004D5246, len(payload), idx))
        f.write(payload)
        print(f"{1.0 + idx * 0.01:.2f}")
PY
chmod +x "$WORK/fake_bench.py"
printf '\0%.0s' {1..128} > "$WORK/fake.raw"

FUSED_LOG_POLYNOMIAL=1 \
GPR_DECIMATE_AA=1 \
GPR_BENCH_PIXEL_FORMAT=4 \
"$PYTHON_BIN" "$REPO/tools/run_labs_target_bench.py" \
  --bench "$WORK/fake_bench.py" \
  --raw "$WORK/fake.raw" \
  --frames 4 \
  --output-dir "$WORK/direct" \
  --source-width 8 \
  --source-height 8 \
  --capture-width 8 \
  --capture-height 8 \
  --target-fps 1 \
  --direct-gvid

"$PYTHON_BIN" - "$WORK/direct/labs_target_bench.json" <<'PY'
import json
import sys
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text())
assert receipt["simulated"] is False
assert receipt["capture"]["frames_requested"] == 4
assert receipt["capture"]["frames_written"] == 4
assert receipt["gvid"]["validation"]["frame_count"] == 4
assert receipt["storage"]["fsync_policy"] == "bench_fused sequential .gvid fwrite"
assert receipt["bench"]["env_overrides"]["GPR_INCLUDE_LL"] == "1"
assert receipt["bench"]["env_overrides"]["FUSED_MULTI_LEVEL"] == "1"
assert receipt["bench"]["env_overrides"]["FUSED_WAVELET_LEVELS"] == "2"
assert receipt["bench"]["env_overrides"]["GPR_COL_DECIMATE"] == "2"
assert receipt["bench"]["env_overrides"]["GPR_ROW_DECIMATE"] == "2"
assert receipt["bench"]["env_overrides"]["FUSED_QUALITY"] == "3"
assert receipt["bench"]["env_overrides"]["FUSED_LOG_POLYNOMIAL"] == "1"
assert receipt["bench"]["env_overrides"]["GPR_DECIMATE_AA"] == "1"
assert receipt["bench"]["env_overrides"]["GPR_BENCH_PIXEL_FORMAT"] == "4"
assert receipt["verdict"]["gvid_valid"] is True
assert receipt["verdict"]["target_evidence"] is True
PY

"$PYTHON_BIN" - "$REPO/tools/run_labs_target_bench.py" <<'PY'
import importlib.util
import sys
from pathlib import Path

mod_path = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("run_labs_target_bench", mod_path)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

sample = """
    ch0: unpack=5.0, horiz=1.0, vert+quant=2.0, tokenize=3.0, other=0.5, TOTAL=11.5
    ch1: wait=0.2, horiz=1.3, vert+quant=2.1, tokenize=3.2, other=0.7, TOTAL=7.5
  FUSED ML Pass1 (level-1, parallel):       20.0ms
  FUSED ML Level23 (streamed in pass1):     0.1ms
  FUSED ML Pass2 (40 bands, parallel):      6.0ms
  FUSED ML Total:                           27.0ms
"""
parsed = mod.parse_fused_timing_stderr(sample)
assert parsed["available"] is True
assert parsed["timing_line_count"] == 6
assert parsed["dominant_stage_by_mean_ms"] == "ml_total"
assert parsed["dominant_channel_component_by_mean_ms"] == "total"
assert parsed["stage_ms"]["ml_pass1"]["mean_ms"] == 20.0
assert parsed["channel_component_ms"]["unpack"]["mean_ms"] == 5.0
assert parsed["channel_component_ms"]["vert_quant"]["n"] == 2
assert parsed["channel_component_by_channel_ms"]["1"]["wait"]["mean_ms"] == 0.2
PY

"$PYTHON_BIN" "$REPO/tools/run_labs_perf_sweep.py" \
  --bench "$WORK/fake_bench.py" \
  --raw "$WORK/fake.raw" \
  --frames 4 \
  --output-dir "$WORK/sweep" \
  --source-width 8 \
  --source-height 8 \
  --capture-width 8 \
  --capture-height 8 \
  --target-fps 1 \
  --direct-gvid \
  --variant baseline \
  --variant stripe64_defer:FUSED_STRIPE_ROWS=64,FUSED_DEFER_RANS=1

"$PYTHON_BIN" - "$WORK/sweep/labs_perf_sweep.json" <<'PY'
import json
import sys
from pathlib import Path

sweep = json.loads(Path(sys.argv[1]).read_text())
assert sweep["schema"] == "gpr_labs_perf_sweep.v1"
assert sweep["direct_gvid"] is True
assert sweep["simulated"] is False
assert sweep["production_claim"] is False
assert sweep["frames_per_variant"] == 4
assert set(sweep["ranked_by_fps_median"]) == {"baseline", "stripe64_defer"}
assert len(sweep["variants"]) == 2
by_name = {item["name"]: item for item in sweep["variants"]}
assert by_name["baseline"]["returncode"] == 0
assert by_name["baseline"]["gvid_valid"] is True
assert by_name["stripe64_defer"]["env"]["FUSED_STRIPE_ROWS"] == "64"
assert by_name["stripe64_defer"]["env"]["FUSED_DEFER_RANS"] == "1"
assert Path(by_name["stripe64_defer"]["receipt"]).is_file()
PY

echo "test_labs_target_bench_smoke: PASS"
