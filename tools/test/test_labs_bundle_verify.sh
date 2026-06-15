#!/usr/bin/env bash
# Smoke-test the Labs artifact bundle verifier with a tiny synthetic bundle.
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
WORK=${WORK:-$GPR_TMPDIR/labs_bundle_verify_smoke}
PYTHON_BIN="${PYTHON_BIN:-python3}"

rm -rf "$WORK"
mkdir -p "$WORK/samples" "$WORK/receipts" "$WORK/hashes"

"$PYTHON_BIN" - "$WORK" <<'PY'
import hashlib
import json
import struct
import sys
from pathlib import Path

root = Path(sys.argv[1])
gvid = root / "samples" / "half_res_capture.gvid"
payloads = [b"frame-0000", b"frame-0001-longer"]
data = bytearray()
data += struct.pack("<IBBHHHIIIII", 0x44495647, 1, 0, 4, 3, 0, 640, 360, 24000, 0, len(payloads))
for tag, payload in enumerate(payloads):
    data += struct.pack("<IIQ", 0x004D5246, len(payload), tag)
    data += payload
gvid.write_bytes(data)

meta = root / "samples" / "half_res_capture.gvid.meta.json"
meta.write_text(json.dumps({
    "schema": "gvid_source_metadata.v1",
    "frame_count": len(payloads),
    "frames": [{"frame_index": i, "frame_tag": i, "raw_clean_tiles": []} for i in range(len(payloads))],
}, indent=2), encoding="utf-8")

receipt = root / "receipts" / "gvid_validate.txt"
receipt.write_text("synthetic labs bundle validator smoke\n", encoding="utf-8")

def row(path, kind):
    b = path.read_bytes()
    return {
        "path": str(path.relative_to(root)),
        "kind": kind,
        "size_bytes": len(b),
        "sha256": hashlib.sha256(b).hexdigest(),
    }

manifest = {
    "schema": "gpr_labs_bundle.v1",
    "repo_commit": "synthetic-smoke",
    "ci_run": "local-smoke",
    "target": {"name": "synthetic"},
    "artifacts": [
        row(gvid, "gvid"),
        row(meta, "json"),
        row(receipt, "text"),
    ],
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
bad = json.loads(json.dumps(manifest))
bad["artifacts"][0]["sha256"] = "0" * 64
(root / "bad_manifest.json").write_text(json.dumps(bad, indent=2), encoding="utf-8")

empty_gvid = root / "samples" / "empty_capture.gvid"
empty_gvid.write_bytes(struct.pack("<IBBHHHIIIII", 0x44495647, 1, 0, 4, 3, 0, 640, 360, 24000, 0, 0))
empty_manifest = json.loads(json.dumps(manifest))
empty_manifest["artifacts"][0] = row(empty_gvid, "gvid")
(root / "empty_manifest.json").write_text(json.dumps(empty_manifest, indent=2), encoding="utf-8")
PY

"$PYTHON_BIN" "$REPO/tools/verify_labs_bundle.py" "$WORK/manifest.json"

if "$PYTHON_BIN" "$REPO/tools/verify_labs_bundle.py" "$WORK/bad_manifest.json" > "$WORK/bad_manifest.log" 2>&1; then
  echo "test_labs_bundle_verify: expected bad manifest to fail" >&2
  exit 1
fi
grep -q "sha256 mismatch" "$WORK/bad_manifest.log"

if "$PYTHON_BIN" "$REPO/tools/verify_labs_bundle.py" "$WORK/empty_manifest.json" > "$WORK/empty_manifest.log" 2>&1; then
  echo "test_labs_bundle_verify: expected empty .gvid manifest to fail" >&2
  exit 1
fi
grep -q "zero-frame .gvid stream" "$WORK/empty_manifest.log"

echo "test_labs_bundle_verify: PASS"
