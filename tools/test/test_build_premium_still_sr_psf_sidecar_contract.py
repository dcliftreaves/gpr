#!/usr/bin/env python3
"""Regression test for the premium still-SR PSF sidecar contract builder."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_psf_sidecar_contract.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("build_psf_sidecar_contract", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_receipt(path: Path, weights: list[float]) -> None:
    path.write_text(
        json.dumps({"schema": "gpr.bayer_resize_psf_receipt.v1", "psf_model": {"normalized_weights": weights}}, sort_keys=True),
        encoding="utf-8",
    )


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_psf_sidecar_contract: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_psf_sidecar_contract_", dir=tmp_parent) as td:
        root = Path(td)
        rows = [
            {"scene_id": "x2d_scene", "crop": "center", "crop_xy": [0, 0], "source_dng": "/fixtures/x2d/frame_000.dng", "ev": 0.0},
            {"scene_id": "z8_scene", "crop": "upper_left", "crop_xy": [4, 8], "source_dng": "/fixtures/z8/frame_001.dng", "ev": 1.0},
            {"scene_id": "iphone_scene", "crop": "center", "crop_xy": [2, 2], "source_dng": "/fixtures/iphone/IMG_9270.DNG", "ev": -1.0},
        ]
        targets = root / "targets.npz"
        np.savez_compressed(targets, meta=np.asarray(json.dumps(rows, sort_keys=True)))

        default_receipt = root / "default_psf.json"
        x2d_receipt = root / "x2d_psf.json"
        z8_receipt = root / "z8_psf.json"
        iphone_receipt = root / "iphone_psf.json"
        write_receipt(default_receipt, [0.25, 0.25, 0.25, 0.25])
        write_receipt(x2d_receipt, [0.50, 0.20, 0.20, 0.10])
        write_receipt(z8_receipt, [0.10, 0.20, 0.30, 0.40])
        write_receipt(iphone_receipt, [0.35, 0.25, 0.25, 0.15])

        sidecar, contract = tool.build_sidecar_and_contract(
            targets=targets,
            target_rows=rows,
            camera_receipts={"x2d": x2d_receipt, "z8": z8_receipt},
            default_psf=default_receipt,
            near_box_epsilon=1.0e-3,
        )
        assert sidecar["schema"] == tool.SIDECAR_SCHEMA
        assert contract["schema"] == tool.CONTRACT_SCHEMA
        assert len(sidecar["rows"]) == 3
        assert contract["summary"]["rows_with_camera_specific_psf"] == 2
        assert contract["summary"]["rows_using_default_psf"] == 1
        assert contract["summary"]["rows_missing_psf"] == 0
        assert contract["summary"]["unique_kernel_count"] == 3
        assert contract["summary"]["training_ready_for_psf_conditioning"] is False
        assert any(row["id"] == "default_global_psf_rows" for row in contract["blockers"])

        sidecar_ready, contract_ready = tool.build_sidecar_and_contract(
            targets=targets,
            target_rows=rows,
            camera_receipts={"x2d": x2d_receipt, "z8": z8_receipt, "iphone": iphone_receipt},
            default_psf=default_receipt,
            near_box_epsilon=1.0e-3,
        )
        assert len(sidecar_ready["rows"]) == 3
        assert contract_ready["summary"]["rows_with_camera_specific_psf"] == 3
        assert contract_ready["summary"]["rows_using_default_psf"] == 0
        assert contract_ready["summary"]["rows_missing_psf"] == 0
        assert contract_ready["summary"]["unique_kernel_count"] == 3
        assert contract_ready["summary"]["training_ready_for_psf_conditioning"] is True

        html = tool.render_html(contract, root / "premium_still_sr_psf_sidecar.json")
        assert "Premium Still SR PSF Sidecar Contract" in html
        assert "default_global_psf_rows" in html

    print("test_build_premium_still_sr_psf_sidecar_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
