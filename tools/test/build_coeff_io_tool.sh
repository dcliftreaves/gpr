#!/bin/bash
# Build the debug-instrumented coeff_io_tool for codec-anchored experiments.
#
# Production builds of libvc5_decoder.a are unchanged — the coefficient
# I/O hooks in source/lib/vc5_decoder/fused_decode.c are wrapped in
# #ifdef GPR_DEBUG_COEFF_IO and absent from production. This script
# compiles a separate debug object file of fused_decode.c with the flag
# set, then links it ahead of the production library so the linker
# picks the debug version. The production .a stays clean.
#
# After running this, coeff_io_tool can dump/load wavelet coefficients
# via GPR_DUMP_COEFFS=<dir> and GPR_LOAD_COEFFS=<dir> env vars.
#
# Usage:
#   bash tools/test/build_coeff_io_tool.sh
set -euo pipefail

REPO="${GPR_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BUILD="${BUILD:-$REPO/build-local}"

if [ ! -d "$BUILD" ]; then
  echo "build-local/ not found — run cmake configure + build first"
  exit 1
fi

cd "$BUILD"

# 1. Make sure production libs are up to date (without the debug flag).
make vc5_decoder vc5_encoder vc5_common -j4 >/dev/null

# 2. Compile a debug-instrumented fused_decode.o (with -DGPR_DEBUG_COEFF_IO).
#    Include paths match what cmake uses (see build-local/source/lib/vc5_decoder/CMakeFiles/vc5_decoder.dir/flags.make).
DEBUG_OBJ=$BUILD/fused_decode_debug.o
clang -O2 -arch arm64 -DGPR_DEBUG_COEFF_IO=1 -DNEON=1 \
    -I"$REPO/source/lib/vc5_decoder" \
    -I"$REPO/source/lib/vc5_encoder" \
    -I"$REPO/source/lib/vc5_common" \
    -I"$REPO/source/lib/common/private" \
    -I"$REPO/source/lib/common/public" \
    -c "$REPO/source/lib/vc5_decoder/fused_decode.c" \
    -o "$DEBUG_OBJ"

# 3. Link coeff_io_tool: debug obj FIRST so linker picks it over the .a's symbol.
clang -O2 -arch arm64 \
    -I"$REPO/source/lib/vc5_decoder" \
    -I"$REPO/source/lib/vc5_encoder" \
    -I"$REPO/source/lib/vc5_common" \
    "$REPO/source/app/coeff_io_tool.c" \
    "$DEBUG_OBJ" \
    "$BUILD/source/lib/vc5_decoder/libvc5_decoder.a" \
    "$BUILD/source/lib/vc5_encoder/libvc5_encoder.a" \
    "$BUILD/source/lib/vc5_common/libvc5_common.a" \
    -lm \
    -o "$BUILD/bin/coeff_io_tool"

# 4. Sanity check: production lib must NOT have the debug hook symbols.
if strings "$BUILD/source/lib/vc5_decoder/libvc5_decoder.a" 2>/dev/null | \
   grep -q "GPR_DUMP_COEFFS"; then
    echo "FAIL: libvc5_decoder.a leaked debug hooks — production build is contaminated"
    exit 2
fi

# 5. Sanity check: coeff_io_tool MUST have the debug hooks.
if ! strings "$BUILD/bin/coeff_io_tool" | grep -q "GPR_DUMP_COEFFS"; then
    echo "FAIL: coeff_io_tool missing debug hooks — link order wrong"
    exit 3
fi

echo "OK"
echo "  production libvc5_decoder.a:  clean (no hooks)"
echo "  debug    coeff_io_tool:       has GPR_DUMP_COEFFS / GPR_LOAD_COEFFS"
echo ""
echo "  Use:  GPR_DUMP_COEFFS=<dir> $BUILD/bin/coeff_io_tool <in.raw> W H <out.raw>"
