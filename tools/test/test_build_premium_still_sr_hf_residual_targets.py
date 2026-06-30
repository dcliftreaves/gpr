#!/usr/bin/env python3
"""Regression test for premium still-SR HF residual target helpers."""

from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_premium_still_sr_hf_residual_targets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("hf_residual_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
        import PIL  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_hf_residual_targets: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_hf_residual_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((64, 64))
        base = np.full((64, 64, 3), 12000, dtype=np.uint16)
        detail = (((x + y) % 4) == 0).astype(np.uint16) * 600
        ref = base.copy()
        ref[:, :, 0] += detail
        ref[:, :, 1] += detail
        ref[:, :, 2] += detail
        cand = base.copy()
        cand[:, :, 0] += detail // 3
        cand[:, :, 1] += detail // 3
        cand[:, :, 2] += detail // 3
        rows, inputs, residuals, targets = tool.build_rows_from_arrays(
            ref=ref,
            cand=cand,
            ev=0.0,
            crop_size=32,
            crop_grid=2,
            max_crops_per_ev=None,
            block=8,
            residual_scale=0.08,
            panels_dir=root / "panels",
            scene_id="synthetic_scene",
            source_dng=root / "source.dng",
            candidate_dng=root / "candidate.dng",
        )
        assert len(rows) == 4
        assert len(inputs) == len(residuals) == len(targets) == 4
        assert rows[0]["scene_id"] == "synthetic_scene"
        assert rows[0]["crop"].startswith("grid2_")
        assert rows[0]["source_dng"].endswith("source.dng")
        assert rows[0]["residual_abs_mean"] > 0.0
        assert rows[0]["hf_y_correlation"] is not None
        npz = root / "targets.npz"
        tool.write_npz(npz, inputs, residuals, targets, rows)
        assert npz.stat().st_size > 0
        with np.load(npz, allow_pickle=False) as z:
            assert z["inputs"].shape == z["hf_residuals"].shape
            assert z["inputs"].dtype == np.float16
        contact = root / "contact.jpg"
        tool.write_contact_sheet(contact, rows, 4)
        assert contact.stat().st_size > 0

    print("test_build_premium_still_sr_hf_residual_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
