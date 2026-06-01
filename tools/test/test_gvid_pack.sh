#!/usr/bin/env bash
# Smoke-test the neutral .gvid packer against the documented wire header.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORK=${WORK:-/tmp/gvid_pack_smoke}

rm -rf "$WORK"
mkdir -p "$WORK/frames"
printf 'frame-0000-payload' > "$WORK/frames/frame_0000.gpr"
printf 'frame-0001-payload-longer' > "$WORK/frames/frame_0001.gpr"

python3 "$REPO/tools/gvid_pack.py" "$WORK/frames" "$WORK/clip.gvid" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4

python3 - "$WORK/clip.gvid" <<'PY'
import struct
import sys
from pathlib import Path

data = Path(sys.argv[1]).read_bytes()
clip = struct.unpack("<IBBHHHIIIII", data[:32])
assert clip[0] == 0x44495647, clip
assert clip[1] == 1, clip
assert clip[3] == 4, clip
assert clip[4] == 3, clip
assert clip[6] == 8280 and clip[7] == 5520, clip
assert clip[8] == 24000, clip
assert clip[10] == 2, clip
pos = 32
for idx, expected in enumerate([b"frame-0000-payload", b"frame-0001-payload-longer"]):
    magic, size, tag = struct.unpack("<IIQ", data[pos:pos + 16])
    assert magic == 0x004D5246, (magic, idx)
    assert size == len(expected), (size, len(expected), idx)
    assert tag == idx, (tag, idx)
    pos += 16
    assert data[pos:pos + size] == expected, idx
    pos += size
assert pos == len(data), (pos, len(data))
PY

echo "test_gvid_pack: PASS"
