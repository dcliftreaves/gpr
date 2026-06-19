#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mission1_sr_coverage_manifest_") as td:
        work = Path(td)
        summary = work / "summary.json"
        summary.write_text(
            json.dumps({"images": [{"image": "GP_A"}, {"image": "GP_B"}]}),
            encoding="utf-8",
        )
        hard = work / "hard.json"
        hard.write_text(
            json.dumps(
                {
                    "schema": "mission1_sr_hard_tile_manifest.v1",
                    "low_tile": 4,
                    "tiles": [
                        {"image_id": "GP_A", "low_x": 2, "low_y": 2, "low_tile": 4, "rank": 1, "score": 9.0},
                        {"image_id": "GP_A", "low_x": 0, "low_y": 0, "low_tile": 4, "rank": 2, "score": 8.0},
                        {"image_id": "GP_B", "low_x": 5, "low_y": 4, "low_tile": 4, "rank": 1, "score": 7.0},
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = work / "coverage.json"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "cnn" / "build_mission1_sr_coverage_manifest.py"),
                "--summary",
                str(summary),
                "--image-id",
                "GP_A",
                "--low-width",
                "24",
                "--low-height",
                "16",
                "--low-tile",
                "4",
                "--stride",
                "5",
                "--hard-manifest",
                str(hard),
                "--hard-top-k-per-image",
                "1",
                "--hard-repeat",
                "2",
                "--out",
                str(out),
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        if payload.get("schema") != "mission1_sr_hard_tile_manifest.v1":
            raise AssertionError("unexpected schema")
        if payload.get("image_count") != 2:
            raise AssertionError(f"expected de-duplicated two-image manifest, got {payload.get('image_count')}")
        if payload.get("plane_width") != 12 or payload.get("plane_height") != 8:
            raise AssertionError("raw dimensions were not converted to CFA-plane dimensions")
        per_image = payload.get("per_image") or {}
        if per_image.get("GP_A", {}).get("grid_tiles") != 6:
            raise AssertionError(f"unexpected GP_A grid count: {per_image.get('GP_A')}")
        if per_image.get("GP_A", {}).get("hard_tiles_added") != 2:
            raise AssertionError(f"expected repeated non-overlapping hard tile for GP_A: {per_image.get('GP_A')}")
        if per_image.get("GP_B", {}).get("hard_tiles_added") != 0:
            raise AssertionError("overlapping hard tile for GP_B should have been de-duplicated")
        tiles = payload.get("tiles") or []
        if len(tiles) != 14:
            raise AssertionError(f"expected 20 tiles, got {len(tiles)}")
        gp_a_hard = [t for t in tiles if t.get("image_id") == "GP_A" and t.get("score_mode") == "full_frame_coverage_plus_hard_tile"]
        if len(gp_a_hard) != 2 or any(t.get("low_x") != 2 or t.get("low_y") != 2 for t in gp_a_hard):
            raise AssertionError(f"unexpected hard tile rows: {gp_a_hard}")
        gp_b_edges = {(t["low_x"], t["low_y"]) for t in tiles if t.get("image_id") == "GP_B"}
        if (8, 4) not in gp_b_edges:
            raise AssertionError("coverage grid did not include right/bottom edge tile")
    print("test_build_mission1_sr_coverage_manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
