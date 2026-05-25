#!/bin/bash
# Reproduce the FUSED multi-level regression on the user's own machine.
#
# Demonstrates:
#   1. Synthetic patterns: SL vs ML PSNR on horizontal stripes
#   2. Real Z8 DNG: SL vs ML rendered output side-by-side
#   3. File-size deltas at single-level + cranks
#
# Usage:
#   tools/test/reproduce_regression.sh [BUILD_DIR]

set -e
BUILD_DIR="${1:-build-local}"
REPO=$(cd "$(dirname "$0")/../.."; pwd)
BIN="${REPO}/${BUILD_DIR}/bin/test_fused_roundtrip"
BENCH="${REPO}/${BUILD_DIR}/source/app/bench_fused/bench_fused"
GTOOLS="${REPO}/${BUILD_DIR}/source/app/gpr_tools/gpr_tools"

if [ ! -x "$BIN" ]; then
    echo "ERROR: $BIN not found. Build with:"
    echo "  clang -O2 source/app/test_fused_decode_roundtrip.c <libs> -o ${BUILD_DIR}/bin/test_fused_roundtrip"
    exit 2
fi

echo "=== 1. Synthetic-pattern regression tripwire ==="
python3 "${REPO}/tools/test/test_multilevel_regression.py" "${BUILD_DIR}" || true

SRC=/Volumes/OWC_8TB/gpr_artifacts/visual_compare_20260525/source_dngs/Z8Z_0067.dng
if [ ! -f "$SRC" ]; then
    echo
    echo "=== 2. Z8 DNG render comparison ==="
    echo "Source DNGs not present at $SRC, skipping real-image comparison."
    exit 0
fi

echo
echo "=== 2. Real Z8 DNG roundtrip (Z8Z_0067) ==="
WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

# Extract bayer from source
python3 -c "
import rawpy, sys
r = rawpy.imread('$SRC')
r.raw_image.copy().astype('<u2').tofile('$WORK/bayer.raw')
print(f'bayer shape: {r.raw_image.shape}')
" 2>&1

W=8280; H=5520

# Single-level
GPR_INCLUDE_LL=1 FUSED_MULTI_LEVEL=0 "$BIN" "$WORK/bayer.raw" "$W" "$H" "$WORK/dec_sl.raw" 2>&1 | grep -E "PSNR|stats" | head -2

# Multi-level
GPR_INCLUDE_LL=1 FUSED_MULTI_LEVEL=1 "$BIN" "$WORK/bayer.raw" "$W" "$H" "$WORK/dec_ml.raw" 2>&1 | grep -E "PSNR|stats" | head -2

echo
echo "=== 3. File-size comparison (single-level + cranks) ==="
printf "%-32s %-12s %s\n" "config" "MB" "savings"
for cfg in \
    "single:FUSED_MULTI_LEVEL=0" \
    "multi:FUSED_MULTI_LEVEL=1" \
    "single+HHx4:FUSED_MULTI_LEVEL=0 GPR_QUANT_OVERRIDE=3:48" \
    "single+LHHLHHx4:FUSED_MULTI_LEVEL=0 GPR_QUANT_OVERRIDE=1:48,2:48,3:48" \
    "single+LHHLHHx8:FUSED_MULTI_LEVEL=0 GPR_QUANT_OVERRIDE=1:96,2:96,3:96"
do
    label="${cfg%%:*}"
    envs="${cfg#*:}"
    eval "GPR_INCLUDE_LL=1 GPR_BENCH_DUMP=$WORK/out.gpr $envs $BENCH $WORK/bayer.raw $W $H 1" > /dev/null 2>&1 || continue
    sz_mb=$(python3 -c "import os; print(f'{os.path.getsize(\"$WORK/out.gpr\")/1e6:.1f}')")
    printf "%-32s %-12s\n" "$label" "$sz_mb"
done

echo
echo "Done. See docs/REGRESSION_2026-05-25.md for context."
