#!/usr/bin/env bash
# Regression smoke for FUSED_PRODUCER_UNPACK with decimated capture.
#
# The shared producer ring currently emits full channel-space rows. Decimated
# capture allocates half-size Pass1 buffers, so producer mode must fall back to
# the safe per-channel unpack path until a decimated producer exists.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO/build}"
BENCH="${BENCH:-$BUILD_DIR/source/app/bench_fused/bench_fused}"
RAW="${RAW:-${TMPDIR:-/tmp}/gpr_dec2_producer_smoke.raw}"

if [ ! -x "$BENCH" ]; then
    echo "ERROR: bench_fused not built at $BENCH" >&2
    exit 2
fi

python3 - "$RAW" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
w, h = 512, 512
with path.open("wb") as f:
    for y in range(h):
        row = bytearray(w * 2)
        for x in range(w):
            v = (1024 + x * 7 + y * 11) & 0x3FFF
            row[2 * x] = v & 0xFF
            row[2 * x + 1] = (v >> 8) & 0xFF
        f.write(row)
PY

FUSED_PRODUCER_UNPACK=1 \
GPR_INCLUDE_LL=1 \
FUSED_MULTI_LEVEL=1 \
FUSED_WAVELET_LEVELS=2 \
GPR_COL_DECIMATE=2 \
GPR_ROW_DECIMATE=2 \
"$BENCH" "$RAW" 512 512 3 >/dev/null

rm -f "$RAW"
