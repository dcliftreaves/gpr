#!/usr/bin/env bash
# Smoke-test .gvid source metadata validation against a packed two-frame stream.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
WORK=${WORK:-/tmp/gvid_metadata_smoke}

rm -rf "$WORK"
mkdir -p "$WORK/frames"
printf 'frame-0000-payload' > "$WORK/frames/frame_0000.gpr"
printf 'frame-0001-payload' > "$WORK/frames/frame_0001.gpr"

python3 "$REPO/tools/gvid_pack.py" "$WORK/frames" "$WORK/clip.gvid" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4

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
          "accepted": false,
          "reject_reasons": ["lag"],
          "sigma_rms_counts": 12.5,
          "exact_residual_to_sigma_rms": 0.0,
          "lag_max_abs": 0.3,
          "edge_removed_energy_ratio": 1.2
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
          "accepted": true,
          "reject_reasons": [],
          "sigma_rms_counts": 110.0,
          "exact_residual_to_sigma_rms": 0.24,
          "lag_max_abs": 0.1,
          "edge_removed_energy_ratio": 0.8
        }
      ]
    }
  ]
}
JSON

python3 "$REPO/tools/gvid_metadata.py" validate "$WORK/clip.gvid.meta.json" \
  --gvid "$WORK/clip.gvid"

python3 - "$WORK/clip.gvid.meta.json" "$WORK/bad_tags.gvid.meta.json" <<'PY'
import json
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
meta = json.loads(src.read_text())
meta["frames"][0]["frame_tag"], meta["frames"][1]["frame_tag"] = 1, 0
dst.write_text(json.dumps(meta, indent=2))
PY

if python3 "$REPO/tools/gvid_metadata.py" validate "$WORK/bad_tags.gvid.meta.json" \
  --gvid "$WORK/clip.gvid"; then
  echo "expected swapped frame tags to fail validation" >&2
  exit 1
fi

echo "test_gvid_metadata: PASS"
