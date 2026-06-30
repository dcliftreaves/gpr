#!/usr/bin/env python3
"""Regression test for the premium still-SR candidate signal audit."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_candidate_signal.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("candidate_signal_audit", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_candidate_signal: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_candidate_signal_audit_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((24, 24))
        raws = []
        hfs = []
        residuals = []
        rows = []
        for i in range(6):
            raw = np.zeros((24, 24, 4), dtype=np.float32)
            raw[:, :, 0] = (x + i) / 48.0
            raw[:, :, 1] = (y + i) / 48.0
            raw[:, :, 2] = ((x + y + i) % 11) / 11.0
            raw[:, :, 3] = ((2 * x + y + i) % 13) / 13.0
            hf = raw - raw.mean(axis=(0, 1), keepdims=True)
            residual = hf * 0.04
            raws.append(raw.astype(np.float16))
            hfs.append(hf.astype(np.float16))
            residuals.append(residual.astype(np.float16))
            rows.append(
                {
                    "scene_id": "holdout_scene" if i == 5 else f"train_scene_{i}",
                    "crop": f"row_{i}",
                    "ev": float((i % 3) - 1),
                    "source_dng": f"/fixtures/{'x2d' if i == 5 else 'z8'}/frame_{i}.dng",
                }
            )
        targets = root / "targets.npz"
        np.savez_compressed(
            targets,
            candidate_raw_cfa4=np.stack(raws),
            candidate_raw_hf_cfa4=np.stack(hfs),
            raw_hf_residual_cfa4=np.stack(residuals),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type(
            "Args",
            (),
            {
                "targets": targets,
                "output_dir": root / "out",
                "holdout_scene": "holdout_scene",
                "holdout_camera": None,
                "samples_per_train_row": 128,
                "samples_per_holdout_row": 256,
                "max_train_rows": None,
                "max_holdout_rows": None,
                "ridge": 1.0e-3,
                "promotion_recovery_threshold": 15.0,
                "seed": 7,
            },
        )()
        receipt = tool.run(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["runtime_policy"]["uses_source_raw_at_runtime"] is False
        assert receipt["runtime_policy"]["uses_ref_or_jpeg_content_at_runtime"] is False
        assert receipt["split"]["holdout_row_count"] == 1
        assert receipt["probe"]["kind"] == "ridge_pixel_candidate_signal"
        assert receipt["holdout_summary"]["raw_residual_mae_reduction_pct"]["median"] > 50.0
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        html = Path(receipt["artifacts"]["dashboard"]).read_text(encoding="utf-8")
        assert "Premium Still-SR Candidate Signal Audit" in html
        assert "candidate raw/CFA" in html

    print("test_audit_premium_still_sr_candidate_signal: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
