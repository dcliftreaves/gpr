#!/usr/bin/env python3
"""Regression test for deterministic Bayer resize PSF known-kernel validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_bayer_resize_psf_known_kernel_validation.py"
CHECKER = ROOT / "tools/check_product_pillar_receipts.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    try:
        import numpy  # noqa: F401
    except ModuleNotFoundError:
        print("test_build_bayer_resize_psf_known_kernel_validation: SKIP missing numpy")
        return 0

    with tempfile.TemporaryDirectory(prefix="gpr_psf_known_kernel_", dir=temp_root()) as tmp:
        out_dir = Path(tmp) / "out"
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--output-dir",
                str(out_dir),
                "--pair-count",
                "3",
                "--height",
                "32",
                "--width",
                "32",
                "--max-samples",
                "1000",
            ],
            check=True,
        )
        receipt_path = out_dir / "bayer_resize_psf_receipt.json"
        validation_path = out_dir / "known_kernel_validation.json"
        subprocess.run([sys.executable, str(CHECKER), str(receipt_path)], check=True)

        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        model = receipt["psf_model"]
        gates = receipt["gate_results"]

        assert receipt["schema"] == "gpr.bayer_resize_psf_receipt.v1"
        assert receipt["production_ready"] is False
        assert validation["schema"] == "gpr.bayer_resize_psf_known_kernel_validation.v1"
        assert validation["algorithm_fixture_ready"] is True
        assert validation["real_mission1_controlled_psf_ready"] is False
        assert receipt["dataset"]["pair_count"] == 3
        assert model["kernel_width_px"] == 2.0
        assert model["kernel_height_px"] == 2.0
        assert model["known_kernel_weight_rmse"] < 1.0e-5
        assert gates["known_kernel_recovered"] is True
        assert gates["negative_control_rejected"] is True
        assert gates["negative_control_rmse_14bit"] > 100.0
        assert (out_dir / "index.html").is_file()

    print("test_build_bayer_resize_psf_known_kernel_validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
