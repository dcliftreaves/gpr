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
assert "bench_child_maxrss_kb" in receipt["memory"]
assert "loadavg_start" in receipt["cpu"]
assert receipt["verdict"]["gvid_valid"] is True
assert receipt["verdict"]["target_evidence"] is False
PY

echo "test_labs_target_bench_smoke: PASS"
