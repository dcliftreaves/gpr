#!/usr/bin/env python3
"""Regression test for premium still-SR HF residual band analysis."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/analyze_premium_still_sr_hf_residual_bands.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("hf_residual_band_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
        import PIL  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_analyze_premium_still_sr_hf_residual_bands: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_hf_residual_bands_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((64, 64))
        inputs = []
        residuals = []
        source_hf = []
        rows = []
        for idx, ev in enumerate([-2.0, 0.0, 2.0]):
            cand = np.zeros((64, 64, 3), dtype=np.float32)
            cand[:, :, 0] = x / 96.0
            cand[:, :, 1] = y / 96.0
            cand[:, :, 2] = ((x + y + idx) % 16) / 16.0
            fine = (((x + y + idx) % 2) * 2 - 1).astype(np.float32) * 0.015
            mid = np.sin((x + idx) / 5.0).astype(np.float32) * 0.020
            residual_y = fine + mid + ev * 0.005
            residual = np.repeat(residual_y[:, :, None], 3, axis=2)
            inputs.append(cand.astype(np.float16))
            residuals.append(residual.astype(np.float16))
            source_hf.append((residual * 1.4).astype(np.float16))
            rows.append({"crop": f"row_{idx}", "ev": ev, "crop_xy": [0, 0], "crop_size": 64})
        npz = root / "targets.npz"
        np.savez_compressed(
            npz,
            inputs=np.stack(inputs),
            hf_residuals=np.stack(residuals),
            source_hf_targets=np.stack(source_hf),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type(
            "Args",
            (),
            {
                "targets": npz,
                "output_dir": root / "out",
                "fine_block": 4,
                "mid_block": 16,
                "coarse_block": 32,
                "contact_rows": 3,
            },
        )()
        receipt = tool.analyze(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["summary"]["row_count"] == 3
        assert receipt["summary"]["bands"]["fine"]["share_of_residual_abs"]["median"] > 0.0
        assert receipt["summary"]["brightness"]["midtone"]["active_rows"] > 0
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["dashboard"]).stat().st_size > 0
        assert Path(receipt["artifacts"]["contact_sheet"]).stat().st_size > 0

    print("test_analyze_premium_still_sr_hf_residual_bands: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
