#!/usr/bin/env bash
# Smoke-test the neutral .gvid packer against the documented wire header.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
GPR_EXTERNAL_ROOT="${GPR_EXTERNAL_ROOT:-/Volumes/OWC_8TB/gpr_work}"
GPR_TMPDIR="${GPR_TMPDIR:-$GPR_EXTERNAL_ROOT/tmp}"
WORK=${WORK:-$GPR_TMPDIR/gvid_pack_smoke}
PYTHON_BIN="${PYTHON_BIN:-python3}"

rm -rf "$WORK"
mkdir -p "$WORK/frames"
printf 'frame-0000-payload' > "$WORK/frames/frame_0000.gpr"
printf 'frame-0001-payload-longer' > "$WORK/frames/frame_0001.gpr"

"$PYTHON_BIN" "$REPO/tools/gvid_pack.py" "$WORK/frames" "$WORK/clip.gvid" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4

"$PYTHON_BIN" - "$WORK/clip.gvid" <<'PY'
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

cat > "$WORK/clip.gvid.meta.json" <<'JSON'
{
  "schema": "gvid_source_metadata.v1",
  "source": "smoke-test",
  "targets": null,
  "gvid": "clip.gvid",
  "frame_count": 2,
  "frames": [
    {
      "frame_index": 0,
      "frame_tag": 0,
      "source_id": "frame_0000",
      "source_path": "frame_0000.dng",
      "iso": 64,
      "raw_clean_tiles": [
        {
          "crop": "A_detail",
          "source_xywh": [3000, 2000, 512, 512],
          "accepted": true,
          "reject_reasons": [],
          "sigma_rms_counts": 12.5,
          "exact_residual_to_sigma_rms": 0.2,
          "lag_max_abs": 0.1,
          "edge_removed_energy_ratio": 0.8
        }
      ]
    },
    {
      "frame_index": 1,
      "frame_tag": 1,
      "source_id": "frame_0001",
      "source_path": "frame_0001.dng",
      "iso": 5000,
      "raw_clean_tiles": [
        {
          "crop": "A_detail",
          "source_xywh": [3000, 2000, 512, 512],
          "accepted": false,
          "reject_reasons": ["lag"],
          "sigma_rms_counts": 110.0,
          "exact_residual_to_sigma_rms": 0.0,
          "lag_max_abs": 0.3,
          "edge_removed_energy_ratio": 1.2
        }
      ]
    }
  ]
}
JSON

"$PYTHON_BIN" "$REPO/tools/gvid_pack.py" "$WORK/frames" "$WORK/clip_with_meta.gvid" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4 \
  --metadata "$WORK/clip.gvid.meta.json"

test -f "$WORK/clip_with_meta.gvid.meta.json"
"$PYTHON_BIN" "$REPO/tools/gvid_metadata.py" validate "$WORK/clip_with_meta.gvid.meta.json" \
  --gvid "$WORK/clip_with_meta.gvid"
"$PYTHON_BIN" - "$WORK/clip_with_meta.gvid.meta.json" <<'PY'
import json
import sys
from pathlib import Path

meta = json.loads(Path(sys.argv[1]).read_text())
assert meta["gvid"] == "clip_with_meta.gvid", meta["gvid"]
PY

"$PYTHON_BIN" - "$WORK/clip.gvid.meta.json" "$WORK/bad_attach.gvid.meta.json" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
meta = json.loads(src.read_text())
meta["frames"][0]["frame_tag"], meta["frames"][1]["frame_tag"] = 1, 0
dst.write_text(json.dumps(meta, indent=2))
PY

if "$PYTHON_BIN" "$REPO/tools/gvid_pack.py" "$WORK/frames" "$WORK/bad_attach.gvid" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4 \
  --metadata "$WORK/bad_attach.gvid.meta.json"; then
  echo "expected bad metadata attach to fail" >&2
  exit 1
fi
test ! -e "$WORK/bad_attach.gvid"

echo "test_gvid_pack: PASS"
