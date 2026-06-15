#!/usr/bin/env bash
# Regression smoke for FUSED_PRODUCER_UNPACK with decimated capture.
#
# The active Labs target path uses row+column decimation. Producer-unpack must
# emit exactly the same encoded bytes as the safe per-channel path before it can
# be used as a target-throughput optimization.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$REPO/build}"
BENCH="${BENCH:-$BUILD_DIR/source/app/bench_fused/bench_fused}"
WORK="${WORK:-${TMPDIR:-/tmp}/gpr_dec2_producer_smoke}"
RAW="$WORK/input.raw"

if [ ! -x "$BENCH" ]; then
    echo "ERROR: bench_fused not built at $BENCH" >&2
    exit 2
fi

rm -rf "$WORK"
mkdir -p "$WORK"

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

GPR_INCLUDE_LL=1 \
FUSED_MULTI_LEVEL=1 \
FUSED_WAVELET_LEVELS=2 \
GPR_COL_DECIMATE=2 \
GPR_ROW_DECIMATE=2 \
GPR_BENCH_DUMP="$WORK/per_channel.gpr" \
"$BENCH" "$RAW" 512 512 3 >/dev/null

FUSED_PRODUCER_UNPACK=1 \
GPR_INCLUDE_LL=1 \
FUSED_MULTI_LEVEL=1 \
FUSED_WAVELET_LEVELS=2 \
GPR_COL_DECIMATE=2 \
GPR_ROW_DECIMATE=2 \
GPR_BENCH_DUMP="$WORK/producer.gpr" \
"$BENCH" "$RAW" 512 512 3 >/dev/null

cmp "$WORK/per_channel.gpr" "$WORK/producer.gpr"

rm -rf "$WORK"
echo "test_producer_unpack_decimate_fallback: PASS"
