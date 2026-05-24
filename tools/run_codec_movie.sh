#!/usr/bin/env bash
# End-to-end: codec on remote (typically a Pi) → render on local through
# rawpy/libraw → MP4. Used to validate codec quality with PROPER raw-to-sRGB
# rendering (white balance + color matrix + gamma from the source DNG).
#
# Why this exists: hand-rolling a demosaic from raw Bayer is a trap. Without
# the DNG's per-camera WB and color matrix and a tone curve, the output looks
# spectacularly wrong even when the codec is fine. rawpy (libraw) does the
# same processing Adobe DNG Converter does, so we get an honest visualization.
#
# Pipeline:
#   1. Convert source DNGs to LE u16 raw on the local machine (dcraw + byteswap)
#   2. Upload to the encoding host
#   3. Run /tmp/multi_frame on the host with the codec env flags
#      (GPR_INCLUDE_LL=1 GPR_ROW_DECIMATE=2 GPR_COL_DECIMATE=2 by default —
#      the 50 MP → 4K-equivalent path)
#   4. scp the decoded Bayer back
#   5. Render each through rawpy using the source DNG's metadata
#   6. ffmpeg the rendered frames into MP4
#
# Inputs / environment:
#   PI=<ssh-host>     remote that has /tmp/multi_frame built (default: gpr-pi)
#   HOLD=<seconds>    seconds to hold each codec frame in MP4 (default 1)
#   OUT=<dir>         output dir (default: /tmp/gpr_visuals)
#   FPS=<int>         MP4 framerate (default 24)
#
# Pre-reqs on the encoding host:
#   /tmp/multi_frame (built from source/app/test_multi_frame.c — see top of
#                     that file for the gcc command)
#
# Pre-reqs locally:
#   - dcraw, ffmpeg, ImageMagick `magick`
#   - python3 with rawpy + numpy + Pillow
#
# Usage:
#   ./tools/run_codec_movie.sh [hold_seconds]
#   PI=user@host HOLD=2 ./tools/run_codec_movie.sh
#
# The DNG source list is hardcoded near the top of this script — edit to test
# a different set of frames.

set -e
HOLD=${1:-${HOLD:-1}}
FPS=${FPS:-24}
PI=${PI:-gpr-pi}
OUT=${OUT:-/tmp/gpr_visuals}
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)

mkdir -p "$OUT"/{src_raw,codec_raw,renders,mp4_frames}

# Three source DNGs from the repo's test set. To test different content,
# point at any RGGB-pattern Nikon Z8 DNG (8280x5520).
SOURCES=(
    "iso64    $REPO_ROOT/data/test_sets/entropy_matrix/Z8_ISO64.DNG"
    "z9756    $REPO_ROOT/data/test_sets/smoke/nikon/Z8_9756.DNG"
    "iso22800 $REPO_ROOT/data/test_sets/entropy_matrix/Z8_ISO22800.DNG"
)

echo "=== 1. Convert DNGs to LE u16 raw on local, upload to $PI ==="
PI_FILES=()
for entry in "${SOURCES[@]}"; do
    name=$(echo "$entry" | awk '{print $1}')
    dng=$(echo "$entry" | awk '{print $2}')
    raw_local="$OUT/src_raw/${name}.raw"
    if [ ! -f "$raw_local" ]; then
        echo "  converting $dng"
        cp "$dng" "$OUT/src_raw/${name}.DNG"
        ( cd "$OUT/src_raw" && dcraw -E -4 -D -t 0 "${name}.DNG" > /dev/null 2>&1 )
        # dcraw writes 16-bit BIG-endian PGM. Codec expects little-endian.
        tail -c +20 "$OUT/src_raw/${name}.pgm" | python3 -c "
import sys, array
a = array.array('H'); a.frombytes(sys.stdin.buffer.read())
a.byteswap()
sys.stdout.buffer.write(a.tobytes())
" > "$raw_local"
        rm -f "$OUT/src_raw/${name}.DNG" "$OUT/src_raw/${name}.pgm"
    fi
    ssh "$PI" "mkdir -p /tmp/z8_frames" 2>/dev/null
    scp -q "$raw_local" "$PI:/tmp/z8_frames/${name}.raw"
    PI_FILES+=("/tmp/z8_frames/${name}.raw")
done

echo "=== 2. Run multi_frame on $PI (encode+decode each through fused codec) ==="
PI_CMD="GPR_INCLUDE_LL=1 GPR_ROW_DECIMATE=2 GPR_COL_DECIMATE=2 /tmp/multi_frame 8280 5520 /tmp/codec_run/f ${PI_FILES[*]}"
ssh "$PI" "mkdir -p /tmp/codec_run && rm -f /tmp/codec_run/* && $PI_CMD" 2>&1 | grep -E "^# " || true

echo "=== 3. Pull decoded raws back ==="
rm -f "$OUT"/codec_raw/*.raw
for i in $(seq 0 $((${#SOURCES[@]} - 1))); do
    scp -q "$PI:/tmp/codec_run/f_$(printf %03d $i).raw" "$OUT/codec_raw/f_${i}.raw"
done

echo "=== 4. Render each codec raw through rawpy using source DNG metadata ==="
rm -f "$OUT"/renders/*.png
for i in 0 1 2; do
    name=$(echo "${SOURCES[$i]}" | awk '{print $1}')
    dng=$(echo "${SOURCES[$i]}" | awk '{print $2}')
    python3 "$REPO_ROOT/tools/render_compare.py" \
        --dng "$dng" \
        --codec-raw "$OUT/codec_raw/f_${i}.raw" --codec-w 4140 --codec-h 2760 \
        --out-source "$OUT/renders/${name}_src.png" \
        --out-codec "$OUT/renders/${name}_codec.png" >/dev/null
    echo "  rendered $name"
done

echo "=== 5. Build MP4 (each codec frame held ${HOLD}s) ==="
rm -f "$OUT"/mp4_frames/*.png
n=0
for entry in "${SOURCES[@]}"; do
    name=$(echo "$entry" | awk '{print $1}')
    frame="$OUT/renders/${name}_codec.png"
    small="$OUT/mp4_frames/${name}_codec_720.png"
    magick "$frame" -resize x720 "$small"
    for j in $(seq 1 $((FPS * HOLD))); do
        cp "$small" "$OUT/mp4_frames/f_$(printf %03d $n).png"
        n=$((n+1))
    done
done
ffmpeg -y -framerate $FPS -i "$OUT/mp4_frames/f_%03d.png" \
       -c:v libx264 -pix_fmt yuv420p -crf 18 \
       "$OUT/codec_realmovie.mp4" 2>&1 | tail -2

echo
echo "=== DONE ==="
echo "MP4:        $OUT/codec_realmovie.mp4"
echo "Renders:    $OUT/renders/*.png"
echo "Codec raws: $OUT/codec_raw/f_*.raw"
ls -la "$OUT/codec_realmovie.mp4"
