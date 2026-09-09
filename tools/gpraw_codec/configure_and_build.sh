#!/usr/bin/env bash
# configure_and_build.sh — build the patched FFmpeg with GPR decoder enabled.
#
# Run from the FFmpeg source root (after install_patch.sh).
#
# We deliberately go minimal to keep the build fast:
#   - no external codec deps (--disable-everything + targeted enables)
#   - just ffmpeg + ffplay + libavformat + libavcodec
#   - link our static GPR decoder libs via --extra-libs

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPR_ROOT="${GPR_ROOT:-$(cd "$SELF_DIR/../.." && pwd)}"
PREFIX="${PREFIX:-$(pwd)/install-gpr}"

GPR_INC="$GPR_ROOT/source/lib/vc5_decoder"
GPR_LIB_D="$GPR_ROOT/build-local/source/lib/vc5_decoder"
GPR_LIB_C="$GPR_ROOT/build-local/source/lib/vc5_common"
GPR_LIB_X="$GPR_ROOT/build-local/source/lib/common"

for lib in "$GPR_LIB_D/libvc5_decoder.a" \
           "$GPR_LIB_C/libvc5_common.a" \
           "$GPR_LIB_X/libcommon.a"; do
    [ -f "$lib" ] || { echo "missing static lib: $lib (build the GPR repo first)" >&2; exit 1; }
done

# SDL2 is required for ffplay; brew install sdl2 first if missing.
SDL_CFLAGS=$(pkg-config --cflags sdl2 2>/dev/null || true)
SDL_OK=""
if [ -n "$SDL_CFLAGS" ]; then SDL_OK="--enable-sdl2 --enable-ffplay"; fi

./configure \
    --prefix="$PREFIX" \
    --disable-doc \
    --disable-htmlpages \
    --disable-manpages \
    --disable-podpages \
    --disable-txtpages \
    --disable-shared \
    --enable-static \
    --disable-network \
    --disable-everything \
    --enable-demuxer=mov \
    --enable-muxer=mov \
    --enable-protocol=file \
    --enable-decoder=gpr \
    --enable-decoder=rawvideo \
    --enable-encoder=rawvideo \
    --enable-encoder=ffv1 \
    --enable-encoder=prores \
    --enable-encoder=prores_ks \
    --enable-decoder=prores \
    --enable-muxer=rawvideo \
    --enable-muxer=null \
    --enable-muxer=image2 \
    --enable-muxer=md5 \
    --enable-encoder=png \
    --enable-encoder=tiff \
    --enable-decoder=png \
    --enable-decoder=tiff \
    --enable-filter=scale \
    --enable-filter=format \
    --enable-filter=null \
    --enable-ffmpeg \
    $SDL_OK \
    --extra-cflags="-I$GPR_INC" \
    --extra-ldflags="-L$GPR_LIB_D -L$GPR_LIB_C -L$GPR_LIB_X" \
    --extra-libs="-lvc5_decoder -lvc5_common -lcommon"

echo
echo "Configure OK. Building ffmpeg (+ffplay if SDL2 was found)..."
make -j$(sysctl -n hw.ncpu 2>/dev/null || echo 4)

echo
echo "Build complete. Binaries:"
ls -1 ./ffmpeg ./ffplay 2>/dev/null || true
echo
echo "Smoke test:"
./ffmpeg -hide_banner -decoders 2>/dev/null | grep -E "gpr|GoPro RAW" || \
    echo "  (gpr decoder not listed — patch may not have applied cleanly)"
