#!/usr/bin/env python3
"""Regression test for X2D premium still-SR manifest expansion."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_x2d_manifest_expansion.py"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base_manifest = root / "base_manifest.json"
        dng_dir = root / "x2d"
        sidecar_root = root / "artifacts/camera_noise_sidecars_20260629/x2d"
        output_dir = root / "out"
        sidecar = sidecar_root / "Hasselblad_X2D_100C_ISO800_exp0.001_noise_calibration.json"
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text('{"schema":"noise"}\n', encoding="utf-8")
        existing = dng_dir / "2024_April_X2D_1742.dng"
        added = dng_dir / "2024_Jan_X2D_0013.dng"
        dng_dir.mkdir()
        existing.write_bytes(b"existing")
        added.write_bytes(b"added")
        write_json(
            base_manifest,
            {
                "schema": "gpr.premium_still_sr_fixture_manifest.v1",
                "fixtures": [
                    {
                        "label": "x2d_100mp_dng",
                        "camera": "Hasselblad X2D 100C",
                        "camera_key": "x2d",
                        "class": "100mp",
                        "extension": "dng",
                        "premium_still_sr_eligible": True,
                        "source": {"path": str(existing.resolve()), "exists": True},
                        "noise_sidecars": [{"path": str(sidecar)}],
                    }
                ],
            },
        )
        metadata = {
            str(existing.resolve()): {
                "Make": "Hasselblad",
                "Model": "Hasselblad X2D 100C",
                "ImageWidth": 11664,
                "ImageHeight": 8750,
                "ISO": 12800,
            },
            str(added.resolve()): {
                "Make": "Hasselblad",
                "Model": "Hasselblad X2D 100C",
                "ImageWidth": 11664,
                "ImageHeight": 8750,
                "ISO": 1600,
            },
        }
        metadata_json = root / "metadata.json"
        write_json(metadata_json, metadata)
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--base-manifest",
                str(base_manifest),
                "--x2d-dng-dir",
                str(dng_dir),
                "--sidecar-root",
                str(sidecar_root),
                "--metadata-json",
                str(metadata_json),
                "--output-dir",
                str(output_dir),
            ],
            cwd=ROOT,
            check=True,
        )
        manifest = json.loads((output_dir / "fixture_manifest.json").read_text(encoding="utf-8"))
        receipt = json.loads((output_dir / "x2d_manifest_expansion_receipt.json").read_text(encoding="utf-8"))
        assert manifest["summary"]["fixture_count"] == 2
        assert manifest["summary"]["added_x2d_scene_count"] == 1
        assert manifest["summary"]["skipped_x2d_scene_count"] == 1
        assert receipt["added_x2d_scenes"][0]["label"] == "x2d_scene_2024_jan_x2d_0013"
        added_fixture = next(f for f in manifest["fixtures"] if f["label"] == "x2d_scene_2024_jan_x2d_0013")
        assert added_fixture["premium_still_sr_eligible"] is True
        assert added_fixture["iso"] == 1600
        assert len(added_fixture["noise_sidecars"]) == 1
    print("test_build_premium_still_sr_x2d_manifest_expansion: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
