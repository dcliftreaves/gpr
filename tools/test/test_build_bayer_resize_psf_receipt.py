#!/usr/bin/env python3
"""Regression test for the synthetic Bayer resize PSF receipt builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_bayer_resize_psf_receipt.py"
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
    with tempfile.TemporaryDirectory(prefix="gpr_psf_receipt_", dir=temp_root()) as tmp:
        out_dir = Path(tmp) / "psf"
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(out_dir),
                "--resize-factor",
                "2",
                "--cfa-phase",
                "RGGB",
                "--cfa-phase",
                "GBRG",
            ],
            check=True,
        )
        receipt = out_dir / "bayer_resize_psf_receipt.json"
        subprocess.run([sys.executable, str(CHECKER), str(receipt)], check=True)

        payload = json.loads(receipt.read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.bayer_resize_psf_receipt.v1"
        assert payload["production_ready"] is False
        assert payload["dataset"]["sharp_edge_count"] == 2
        assert payload["dataset"]["texture_field_count"] == 1
        assert payload["psf_model"]["kernel_width_px"] > 0.0
        assert payload["psf_model"]["kernel_height_px"] > 0.0
        assert payload["gate_results"]["mission42_passed"] is False

    print("test_build_bayer_resize_psf_receipt: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
