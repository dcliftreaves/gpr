#!/usr/bin/env bash
# prepare_gpr_corpus.sh — extract Bayer from N source DNGs, encode each with
# $MF_LOCAL using the playback-config env, drop the resulting .gpr files in
# the requested output directory.
#
# usage: prepare_gpr_corpus.sh <dng_dir> <count> <out_dir> [name_prefix]

set -euo pipefail
DNG_DIR=${1:?dng_dir}
COUNT=${2:?count}
OUT_DIR=${3:?out_dir}
PREFIX=${4:-frame}

GPR_EXTERNAL_ROOT="${GPR_EXTERNAL_ROOT:-/Volumes/OWC_8TB/gpr_work}"
GPR_TMPDIR="${GPR_TMPDIR:-$GPR_EXTERNAL_ROOT/tmp}"
TMPDIR="$GPR_TMPDIR"
MF_LOCAL="${MF_LOCAL:-$GPR_EXTERNAL_ROOT/tools/mf_local}"
mkdir -p "$TMPDIR"
WORK=$(mktemp -d "$TMPDIR/prepare_gpr_corpus-XXXXXX")
mkdir -p "$OUT_DIR"
echo "work dir: $WORK"

# 1) Pick first COUNT DNGs
DNGS=()
while IFS= read -r line; do DNGS+=("$line"); done < <(ls "$DNG_DIR"/*.dng 2>/dev/null | head -n "$COUNT")
N=${#DNGS[@]}
echo "selected $N DNGs"
if [ "$N" -lt "$COUNT" ]; then
  echo "warning: only $N DNGs available (requested $COUNT)"
fi

# 2) Extract bayer (LE u16) from each DNG -> .raw, with rawpy
RAW_LIST=()
i=0
for dng in "${DNGS[@]}"; do
  raw="$WORK/$(printf '%04d' $i).raw"
  python3 -c "
import rawpy, numpy as np, sys
with rawpy.imread('$dng') as r:
    img = r.raw_image
    assert img.dtype == np.uint16
    img.tofile('$raw')
"
  RAW_LIST+=("$raw")
  i=$((i+1))
done
echo "wrote $i raw bayers"

# 3) Run mf_local on the batch. MULTI_FRAME_DUMP_ENCODED=1 dumps .gpr per frame.
W=8280
H=5520
OUT_PREFIX="$OUT_DIR/$PREFIX"

# Clean any old .gpr in out dir matching the prefix
rm -f "$OUT_PREFIX"_*.gpr "$OUT_PREFIX"_*.raw "$OUT_PREFIX"_*.ppm 2>/dev/null || true

echo "encoding via $MF_LOCAL ..."
GPR_INCLUDE_LL=1 GPR_ROW_DECIMATE=2 GPR_COL_DECIMATE=2 \
GPR_DROP_HIGHPASS=1 GPR_DECIMATE_AA=1 \
MULTI_FRAME_DUMP_ENCODED=1 \
MULTI_FRAME_SKIP_DECODE=1 \
MULTI_FRAME_SKIP_WRITES=1 \
"$MF_LOCAL" $W $H "$OUT_PREFIX" "${RAW_LIST[@]}" 2> "$WORK/encode.log"

echo "encode timings:"
grep -E "^# " "$WORK/encode.log" | head -5
echo "  ..."
grep -E "^# " "$WORK/encode.log" | tail -5

# 4) Summary
GPR_FILES=("$OUT_PREFIX"_*.gpr)
TOTAL_BYTES=$(du -cb "$OUT_PREFIX"_*.gpr 2>/dev/null | tail -1 | awk '{print $1}')
if [ -z "$TOTAL_BYTES" ]; then
  # macOS du has no -b
  TOTAL_BYTES=$(stat -f%z "$OUT_PREFIX"_*.gpr | awk '{s+=$1} END{print s}')
fi
echo "DONE: ${#GPR_FILES[@]} gpr files, total bytes=$TOTAL_BYTES"
echo "  out dir: $OUT_DIR"
echo "  encode log: $WORK/encode.log"
