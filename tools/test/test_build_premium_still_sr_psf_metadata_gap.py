#!/usr/bin/env python3
"""Regression test for the premium still-SR PSF metadata gap audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_psf_metadata_gap.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_train_receipt(path: Path, metric: float, rmse: float = -0.01) -> None:
    write_json(
        path,
        {
            "schema": "gpr.premium_still_sr_raw_cfa_residual_model.v1",
            "best_holdout_probe": {
                "step": 20,
                "row_count": 3,
                "raw_mae_reduction_pct_median": metric,
            },
            "eval": {
                "holdout": {
                    "exact_raw_mae_reduction_pct": {"median": metric},
                    "raw_residual_rmse_reduction_pct": {"median": rmse},
                }
            },
        },
    )


def main() -> int:
    try:
        import numpy as np
    except ImportError:
        print("test_build_premium_still_sr_psf_metadata_gap: SKIP missing numpy")
        return 0

    with tempfile.TemporaryDirectory(prefix="gpr_still_sr_psf_gap_", dir=temp_root()) as tmp:
        work = Path(tmp)
        targets = work / "targets.npz"
        psf_receipt = work / "psf_receipt.json"
        baseline_receipt = work / "baseline_receipt.json"
        psf_probe = work / "psf_probe_receipt.json"
        out_dir = work / "out"

        meta = [
            {
                "scene_id": "x2d_scene",
                "crop": "center",
                "candidate_raw": "/fixtures/x2d_scene_candidate.raw",
                "source_raw": "/fixtures/Hasselblad_X2D_100C/source.raw",
            },
            {
                "scene_id": "z8_scene",
                "crop": "center",
                "candidate_raw": "/fixtures/Z8Z_1234_candidate.raw",
                "source_raw": "/fixtures/Nikon_Z8/source.raw",
                "psf_kernel_weights": [0.25, 0.25, 0.25, 0.25],
            },
            {
                "scene_id": "iphone_scene",
                "crop": "center",
                "camera": "iPhone 15 Pro",
                "candidate_raw": "/fixtures/IMG_9270_candidate.raw",
                "source_raw": "/fixtures/IMG_9270.DNG",
            },
        ]
        np.savez(
            targets,
            candidate_raw_cfa4=np.zeros((3, 4, 2, 2), dtype=np.float32),
            raw_hf_residual_cfa4=np.zeros((3, 4, 2, 2), dtype=np.float32),
            meta=json.dumps(meta),
        )
        write_json(
            psf_receipt,
            {
                "schema": "gpr.bayer_resize_psf_receipt.v1",
                "psf_model": {
                    "normalized_weights": [0.250001, 0.250002, 0.25, 0.249997],
                },
            },
        )
        write_train_receipt(baseline_receipt, 0.153, -0.2)
        write_train_receipt(psf_probe, 0.106, 0.01)

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--targets",
                str(targets),
                "--psf-receipt",
                str(psf_receipt),
                "--baseline-receipt",
                str(baseline_receipt),
                "--psf-probe-receipt",
                str(psf_probe),
                "--output-dir",
                str(out_dir),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        gap = json.loads((out_dir / "premium_still_sr_psf_metadata_gap.json").read_text(encoding="utf-8"))
        assert gap["schema"] == "gpr.premium_still_sr_psf_metadata_gap.v1"
        assert gap["summary"]["target_row_count"] == 3
        assert gap["summary"]["scene_count"] == 3
        assert gap["summary"]["rows_with_psf_metadata"] == 1
        assert gap["summary"]["unique_row_psf_kernel_count"] == 1
        assert gap["summary"]["inferred_camera_counts"] == {"iphone": 1, "x2d": 1, "z8": 1}
        assert gap["summary"]["global_psf_near_box"] is True
        assert gap["summary"]["psf_probe_beats_baseline"] is False
        assert gap["summary"]["psf_metadata_ready_for_model_conditioning"] is False
        assert gap["summary"]["another_psf_cnn_run_justified"] is False
        assert any(row["id"] == "missing_per_row_psf_metadata" for row in gap["blockers"])
        assert any(row["id"] == "global_psf_near_box" for row in gap["blockers"])
        assert any(row["id"] == "psf_probe_did_not_beat_baseline" for row in gap["blockers"])
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR PSF Metadata Gap" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_premium_still_sr_psf_metadata_gap: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
