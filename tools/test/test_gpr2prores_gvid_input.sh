#!/usr/bin/env bash
# Smoke-test gpr2prores direct .gvid input on macOS with local fixtures.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
GPR2PRORES=${GPR2PRORES:-"$REPO/tools/gpr2prores/gpr2prores"}
SRC_GPR=${SRC_GPR:-/Volumes/OWC_8TB/gpr_work/artifacts/upresable/halfres/Z8Z_0258.gpr}
META_DNG=${META_DNG:-/Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng/Z8Z_0258.dng}
WORK=${WORK:-/Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke}

if [ "$(uname -s)" != "Darwin" ]; then
  echo "test_gpr2prores_gvid_input: SKIP non-macOS"
  exit 0
fi
if [ ! -x "$GPR2PRORES" ]; then
  echo "test_gpr2prores_gvid_input: SKIP missing gpr2prores binary: $GPR2PRORES"
  exit 0
fi
if [ ! -f "$SRC_GPR" ] || [ ! -f "$META_DNG" ]; then
  echo "test_gpr2prores_gvid_input: SKIP missing local fixtures"
  echo "  SRC_GPR=$SRC_GPR"
  echo "  META_DNG=$META_DNG"
  exit 0
fi

rm -rf "$WORK"
mkdir -p "$WORK/frames" "$WORK/tmp"
cp "$SRC_GPR" "$WORK/frames/frame_0000.gpr"

python3 "$REPO/tools/gvid_pack.py" "$WORK/frames" "$WORK/oneframe.gvid" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4

TMPDIR="$WORK/tmp" "$GPR2PRORES" \
  --phase0 --no-cnn \
  --meta-dng "$META_DNG" \
  "$WORK/oneframe.gvid" "$WORK/out.mov" \
  2>&1 | tee "$WORK/phase0.log"

grep -q "magic=0x44535546" "$WORK/phase0.log"
grep -q "$WORK/tmp/gpr2prores_gvid_.*/frame_000000.gpr" "$WORK/phase0.log"

mkdir -p "$WORK/order_frames"
cp "$SRC_GPR" "$WORK/order_frames/frame_0000.gpr"
python3 - "$WORK/order_frames/frame_0001.gpr" <<'PY'
import struct
import sys
from pathlib import Path

payload = bytearray(64)
payload[0:4] = struct.pack("<I", 0x21444142)  # "BAD!" in little endian.
payload[8:16] = struct.pack("<II", 1234, 5678)
Path(sys.argv[1]).write_bytes(payload)
PY
python3 "$REPO/tools/gvid_pack.py" "$WORK/order_frames" "$WORK/out_of_order_tags.gvid" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4
python3 - "$WORK/out_of_order_tags.gvid" <<'PY'
import struct
import sys
from pathlib import Path

p = Path(sys.argv[1])
data = bytearray(p.read_bytes())
pos = 32
magic, size, tag = struct.unpack("<IIQ", data[pos:pos + 16])
assert tag == 0
data[pos + 8:pos + 16] = struct.pack("<Q", 7)
pos += 16 + size
magic, size, tag = struct.unpack("<IIQ", data[pos:pos + 16])
assert tag == 1
data[pos + 8:pos + 16] = struct.pack("<Q", 3)
p.write_bytes(data)
PY
TMPDIR="$WORK/tmp" "$GPR2PRORES" \
  --phase0 --no-cnn \
  --meta-dng "$META_DNG" \
  "$WORK/out_of_order_tags.gvid" "$WORK/order.mov" \
  2>&1 | tee "$WORK/order.log"
grep -q "Phase 0 (GPR): .*frame_000000.gpr" "$WORK/order.log"
grep -q "magic=0x44535546" "$WORK/order.log"

TMPDIR="$WORK/tmp" "$GPR2PRORES" \
  --max-frames 1 --no-cnn \
  --demosaic core-image --out-resolution 2k \
  --meta-dng "$META_DNG" \
  "$WORK/oneframe.gvid" "$WORK/out_2k.mov" \
  2>&1 | tee "$WORK/render.log"

test -s "$WORK/out_2k.mov"
grep -q "errors=0" "$WORK/render.log"

cp "$WORK/oneframe.gvid" "$WORK/dup_tag.gvid"
python3 - "$WORK/dup_tag.gvid" <<'PY'
import struct
import sys
from pathlib import Path

p = Path(sys.argv[1])
data = bytearray(p.read_bytes())
pos = 32
magic, size, tag = struct.unpack("<IIQ", data[pos:pos + 16])
frame = data[pos:pos + 16 + size]
out = bytearray(data[:32] + frame + frame)
out[28:32] = struct.pack("<I", 2)
p.write_bytes(out)
PY

if TMPDIR="$WORK/tmp" "$GPR2PRORES" \
  --phase0 --no-cnn \
  --meta-dng "$META_DNG" \
  "$WORK/dup_tag.gvid" "$WORK/dup.mov" \
  >"$WORK/dup.log" 2>&1; then
  echo "expected duplicate frame tag failure" >&2
  exit 1
fi
grep -q "duplicate GVID frame tag" "$WORK/dup.log"

echo "test_gpr2prores_gvid_input: PASS"
