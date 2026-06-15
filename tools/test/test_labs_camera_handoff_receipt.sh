#!/usr/bin/env bash
# Smoke-test the Labs camera handoff receipt schema.
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
WORK=${WORK:-$GPR_TMPDIR/labs_camera_handoff_smoke}
PYTHON_BIN="${PYTHON_BIN:-python3}"

rm -rf "$WORK"
mkdir -p "$WORK"

"$PYTHON_BIN" - "$WORK" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
base = {
    "schema": "gpr_labs_camera_handoff_receipt.v1",
    "target": {"name": "Pi 5 stand-in", "role": "stand-in"},
    "integration": {
        "frame_source": "file-backed Bayer stand-in",
        "memory_ownership": "synchronous submit; caller owns input through return",
        "write_path": "bench_fused direct .gvid fwrite",
        "sensor_dma_handoff": {"executed": False},
    },
    "input_frame": {
        "width": 8280,
        "height": 5520,
        "stride_bytes": 16560,
        "bit_depth": 14,
        "pixel_format": 4,
        "target_fps": 24.0,
    },
    "capture": {"frames_requested": 14400, "frames_written": 14400, "dropped_frames": 0},
    "timing": {"fps_median": 19.98, "median_ms": 50.04, "p95_ms": 66.01, "p99_ms": 83.0},
    "storage": {"write_mb_s": 17.46, "flush_policy": "sequential fwrite plus receipt validation"},
    "memory": {"rss_kb": 140800},
    "output": {"sha256": "0" * 64, "validation": {"valid": True, "frame_count": 14400}},
    "interruption_recovery": {"proven": True, "validator_rejects_truncated": True},
    "verdict": {
        "firmware_ready": False,
        "target_evidence": True,
        "fps_target_met": False,
        "no_drops": True,
    },
    "blocker": {"cause": "camera hardware not executed"},
}
(root / "standin_ok.json").write_text(json.dumps(base, indent=2), encoding="utf-8")

bad = json.loads(json.dumps(base))
bad["target"] = {"name": "Mission 1", "role": "camera"}
bad["verdict"]["firmware_ready"] = True
bad["integration"]["sensor_dma_handoff"]["executed"] = False
(root / "bad_promoted_camera.json").write_text(json.dumps(bad, indent=2), encoding="utf-8")

blocked_camera = json.loads(json.dumps(base))
blocked_camera["target"] = {"name": "Mission 1", "role": "camera"}
blocked_camera["integration"]["frame_source"] = "sensor DMA"
blocked_camera["integration"]["sensor_dma_handoff"]["executed"] = True
blocked_camera["blocker"] = {"cause": "storage path below target fps"}
(root / "blocked_camera_ok.json").write_text(json.dumps(blocked_camera, indent=2), encoding="utf-8")
PY

"$PYTHON_BIN" "$REPO/tools/check_labs_camera_handoff_receipt.py" "$WORK/standin_ok.json"
"$PYTHON_BIN" "$REPO/tools/check_labs_camera_handoff_receipt.py" "$WORK/blocked_camera_ok.json"

if "$PYTHON_BIN" "$REPO/tools/check_labs_camera_handoff_receipt.py" "$WORK/bad_promoted_camera.json" > "$WORK/bad.log" 2>&1; then
  echo "test_labs_camera_handoff_receipt: expected bad promoted camera receipt to fail" >&2
  exit 1
fi
grep -q "firmware-ready receipt" "$WORK/bad.log"

echo "test_labs_camera_handoff_receipt: PASS"
