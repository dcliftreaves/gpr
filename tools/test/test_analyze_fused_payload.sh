#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
WORK="${GPR_TMPDIR:-${TMPDIR:-/tmp}}/analyze_fused_payload_smoke"

cleanup() {
  local status=$?
  if [ "$status" -eq 0 ] && [ "${GPR_KEEP_TEST_ARTIFACTS:-0}" != "1" ]; then
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT

rm -rf "$WORK"
mkdir -p "$WORK"

"$PYTHON_BIN" - "$WORK/tiny.gpr" <<'PY'
import struct
import sys
from pathlib import Path

out = Path(sys.argv[1])
FUSED_MAGIC = 0x44535546
FLL2 = 0x324C4C46
header = struct.pack("<12I", FUSED_MAGIC, 1, 4, 4, 1, 8, 1, 14, 2, 0, 16, 0)

def fll2_band(width, height, k):
    # All-zero LL residuals under left predictor: one zero unary bit per coeff.
    bits = [0] * (width * height)
    payload = bytearray()
    acc = 0
    nbits = 0
    for bit in bits:
        acc |= bit << nbits
        nbits += 1
        if nbits == 8:
            payload.append(acc)
            acc = 0
            nbits = 0
    if nbits:
        payload.append(acc)
    meta = k
    return struct.pack("<4I", FLL2, meta, width, height) + bytes(payload)

bands = []
for ch in range(4):
    bands.append(fll2_band(1, 1, 0))
    bands.append(bytes([1, 2, 3, ch]))
    bands.append(bytes([4, 5, 6, ch]))
    bands.append(bytes([7, 8, 9, ch]))
table = struct.pack("<16I", *(len(b) for b in bands))
out.write_bytes(header + table + b"".join(bands))
PY

"$PYTHON_BIN" "$ROOT/tools/analyze_fused_payload.py" "$WORK/tiny.gpr" --pretty --output "$WORK/report.json" > "$WORK/stdout.json"

"$PYTHON_BIN" - "$WORK/report.json" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1]))
assert report["header"]["num_bands"] == 16
assert report["storage_target"]["target_read_MBps"] == 205.0
assert report["storage_target"]["target_write_MBps"] == 150.0
assert report["storage_target"]["budget_write_MBps"] == 135.0
assert "128GB-1TB" in report["storage_target"]["name"]
assert "64GB microSD" in report["storage_target"]["profile_note"]
assert report["totals_by_slot"]["LL"] == 68
fll2 = [b for b in report["bands"] if b["codec"] == "fll2_pred_ll"]
assert len(fll2) == 4
assert all(b["rice_k"] == 0 for b in fll2)
assert all(b["zero_residual_fraction"] == 1.0 for b in fll2)
assert report["fll2_best_rice_savings_bytes"] == 0
PY

echo "test_analyze_fused_payload: PASS"
