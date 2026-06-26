#!/usr/bin/env bash
# Smoke-test deterministic Labs bundle manifest/checksum generation.
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
WORK=${WORK:-$GPR_TMPDIR/labs_bundle_builder_smoke}
PYTHON_BIN="${PYTHON_BIN:-python3}"

cleanup() {
  local status=$?
  if [ "$status" -eq 0 ] && [ "${GPR_KEEP_TEST_ARTIFACTS:-0}" != "1" ]; then
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT

rm -rf "$WORK"
mkdir -p "$WORK/samples" "$WORK/review" "$WORK/receipts"

"$PYTHON_BIN" - "$WORK" <<'PY'
import json
import struct
import sys
from pathlib import Path

root = Path(sys.argv[1])
payloads = [b"builder-frame-0", b"builder-frame-1"]
data = bytearray()
data += struct.pack("<IBBHHHIIIII", 0x44495647, 1, 0, 4, 3, 0, 640, 360, 24000, 0, len(payloads))
for tag, payload in enumerate(payloads):
    data += struct.pack("<IIQ", 0x004D5246, len(payload), tag)
    data += payload
(root / "samples" / "half_res_capture.gvid").write_bytes(data)
(root / "samples" / "half_res_capture.gvid.meta.json").write_text(
    json.dumps({"schema": "gvid_source_metadata.v1", "frame_count": len(payloads)}, indent=2),
    encoding="utf-8",
)
(root / "review" / "preview_review_dashboard.html").write_text(
    "<!doctype html><title>builder smoke</title>\n",
    encoding="utf-8",
)
(root / "receipts" / "pi5_proxy_receipt.json").write_text(
    json.dumps({"fps_median": 19.98, "proxy_fps": 20.0}, indent=2),
    encoding="utf-8",
)
PY

"$PYTHON_BIN" "$REPO/tools/build_labs_bundle.py" "$WORK" \
  --repo-commit synthetic-builder-smoke \
  --ci-run https://github.com/dcliftreaves/gpr/actions/runs/0 \
  --target-name "Pi 5 stand-in" \
  --target-role stand-in \
  --note "synthetic builder smoke" \
  --artifact samples/half_res_capture.gvid:gvid \
  --artifact samples/half_res_capture.gvid.meta.json:json \
  --artifact review/preview_review_dashboard.html:dashboard \
  --artifact receipts/pi5_proxy_receipt.json:json

"$PYTHON_BIN" "$REPO/tools/verify_labs_bundle.py" "$WORK/manifest.json"
(cd "$WORK" && shasum -a 256 -c hashes/sha256sums.txt)

echo "test_labs_bundle_builder: PASS"
