#!/usr/bin/env bash
# Build & run the round-trip validator.
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPR_ROOT="${GPR_ROOT:-$(cd "$SELF_DIR/../.." && pwd)}"
GPR_EXTERNAL_ROOT="${GPR_EXTERNAL_ROOT:-/Volumes/OWC_8TB/gpr_work}"
FF_ROOT="${FF_ROOT:-$GPR_EXTERNAL_ROOT/external/ffmpeg_gpr}"

OUT="$SELF_DIR/test_roundtrip"

clang -O2 -g -Wall -Wno-unused-parameter \
    -I"$GPR_ROOT/source/lib/vc5_decoder" \
    -I"$FF_ROOT" \
    "$SELF_DIR/test_roundtrip.c" \
    "$GPR_ROOT/build-local/source/lib/vc5_encoder/libvc5_encoder.a" \
    "$GPR_ROOT/build-local/source/lib/vc5_decoder/libvc5_decoder.a" \
    "$GPR_ROOT/build-local/source/lib/vc5_common/libvc5_common.a" \
    "$GPR_ROOT/build-local/source/lib/common/libcommon.a" \
    "$FF_ROOT/libavformat/libavformat.a" \
    "$FF_ROOT/libavcodec/libavcodec.a" \
    "$FF_ROOT/libswresample/libswresample.a" \
    "$FF_ROOT/libavutil/libavutil.a" \
    -framework CoreFoundation -framework CoreVideo \
    -framework CoreMedia -framework VideoToolbox \
    -framework Security -framework AudioToolbox \
    -liconv -lbz2 -lz -lm \
    -o "$OUT"

echo "built: $OUT"
# Multi-level encoding is required for the fused decoder to reconstruct.
# Single-level streams (the default) drop the lowpass and are not decodable.
GPR_TMPDIR="${GPR_TMPDIR:-$GPR_EXTERNAL_ROOT/tmp}"
TMP_BASE="$GPR_TMPDIR"
mkdir -p "$TMP_BASE"
FUSED_MULTI_LEVEL=1 "$OUT" "${1:-$TMP_BASE/gpraw_roundtrip.gpraw}"
