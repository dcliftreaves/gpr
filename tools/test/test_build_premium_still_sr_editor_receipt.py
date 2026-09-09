#!/usr/bin/env python3
"""Regression test for premium still-SR editor/openability receipt builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_editor_receipt.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_file(path: Path, size: int = 16) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(range(size)))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_editor_", dir=temp_root()) as td:
        root = Path(td)
        artifacts = root / "artifacts"
        bench = artifacts / "bench.json"
        packaging = artifacts / "packaging.json"
        metadata_audit = artifacts / "metadata_audit.json"
        out = root / "out"
        sr_raw = artifacts / "sr.raw"
        dng = artifacts / "frame.dng"
        gpr = artifacts / "frame.gpr"
        mov = artifacts / "review.mov"
        mov2 = artifacts / "review_twoframe.mov"
        metadata_dng = artifacts / "frame_meta.dng"
        for path in (sr_raw, dng, gpr, mov, mov2, metadata_dng):
            write_file(path)
        bench.write_text(
            json.dumps(
                {
                    "device": "cpu",
                    "timing": {
                        "fps_with_write": 1.5,
                        "fps_inference_only": 1.8,
                        "total_with_write_s": 0.66,
                        "tile": 512,
                        "overlap": 64,
                        "tile_count": 35,
                    },
                }
            ),
            encoding="utf-8",
        )
        packaging.write_text(
            json.dumps(
                {
                    "sr_raw": {"path": "artifacts/sr.raw", "width": 11664, "height": 8748},
                    "editable_dng": {
                        "path": "artifacts/frame.dng",
                        "rawpy_open_shape": [8748, 11664],
                        "raw_roundtrip_byte_identical": True,
                    },
                    "editable_gpr": {
                        "path": "artifacts/frame.gpr",
                        "quality": 3,
                        "raw_to_gpr_mode": "scratch_copy",
                        "readback_metrics": {
                            "psnr14_db": 63.3,
                            "mae_dn": 6.5,
                            "rmse_dn": 11.2,
                            "max_abs_dn": 355,
                        },
                        "gpr_to_dng_rawpy_open_shape": [8748, 11664],
                    },
                    "prores_review": {
                        "path": "artifacts/review.mov",
                        "ffprobe": {"streams": [{"codec_name": "prores", "width": 2048, "height": 1536, "nb_frames": "1"}]},
                    },
                    "prores_fps_review": {
                        "path": "artifacts/review_twoframe.mov",
                        "ffprobe": {"streams": [{"codec_name": "prores", "width": 2048, "height": 1536, "nb_frames": "2"}]},
                    },
                }
            ),
            encoding="utf-8",
        )
        metadata_audit.write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "source": str(metadata_dng),
                            "readable_by_exiftool": True,
                            "missing_required": [],
                            "missing_recommended": ["OpcodeList2"],
                            "diffs_from_reference": [{"tag": "ActiveArea"}, {"tag": "AsShotNeutral"}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--bench-receipt",
                str(bench),
                "--packaging-receipt",
                str(packaging),
                "--output-dir",
                str(out),
                "--external-root",
                str(root),
                "--route",
                "x2d:100mp:dng",
                "--camera",
                "Hasselblad X2D",
                "--source-frame",
                "fixture",
                "--metadata-audit",
                str(metadata_audit),
                "--metadata-dng",
                str(metadata_dng),
            ],
            check=True,
        )
        receipt = json.loads((out / "editor_receipt.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_editor_receipt.v1"
        assert receipt["openability_pass"] is True
        assert receipt["production_ready"] is False
        assert receipt["metadata_transplant"]["passed"] is True
        assert "raw-editor latitude" in " ".join(receipt["blockers"])
        assert receipt["dimensions"]["width"] == 11664
        assert receipt["editable_gpr"]["psnr14_db"] == 63.3
        assert receipt["editable_gpr"]["psnr_range_db"] > 60.0
        assert (out / "index.html").is_file()

    print("test_build_premium_still_sr_editor_receipt: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
