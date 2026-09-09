#!/usr/bin/env python3
"""Regression test for the premium still-SR frequency filter audit."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_frequency_filter.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("frequency_filter_audit", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_frequency_filter: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_frequency_filter_audit_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((32, 32))
        inputs = []
        targets = []
        rows = []
        kernel_target = np.roll(((x + y) % 7).astype(np.float32), 1, axis=1) / 7.0
        for i in range(6):
            inp = np.zeros((32, 32, 4), dtype=np.float32)
            base = np.sin((x + i) * 0.4) + np.cos((y - i) * 0.3)
            for plane in range(4):
                inp[:, :, plane] = base + plane * 0.05
            target = np.roll(inp, 1, axis=1) * 0.08 + kernel_target[:, :, None] * 0.01
            inputs.append(inp.astype(np.float16))
            targets.append(target.astype(np.float16))
            rows.append(
                {
                    "scene_id": "holdout_scene" if i == 5 else f"train_scene_{i}",
                    "crop": f"row_{i}",
                    "ev": 0.0,
                    "source_dng": f"/fixtures/{'x2d' if i == 5 else 'z8'}/frame_{i}.dng",
                }
            )
        targets_path = root / "targets.npz"
        np.savez_compressed(
            targets_path,
            candidate_raw_hf_cfa4=np.stack(inputs),
            raw_hf_residual_cfa4=np.stack(targets),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type(
            "Args",
            (),
            {
                "targets": targets_path,
                "output_dir": root / "out",
                "holdout_scene": "holdout_scene",
                "holdout_camera": None,
                "holdout_crop": None,
                "holdout_ev": None,
                "ridge": 1.0e-4,
                "max_train_rows": None,
                "max_holdout_rows": None,
                "eval_train_rows": None,
                "promotion_recovery_threshold": 15.0,
            },
        )()
        receipt = tool.run(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["runtime_policy"]["uses_source_raw_at_runtime"] is False
        assert receipt["runtime_policy"]["uses_ref_or_jpeg_content_at_runtime"] is False
        assert receipt["split"]["holdout_row_count"] == 1
        assert receipt["probe"]["kind"] == "per_cfa_plane_frequency_filter"
        assert receipt["holdout_summary"]["raw_residual_mae_reduction_pct"]["median"] > 30.0
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        html = Path(receipt["artifacts"]["dashboard"]).read_text(encoding="utf-8")
        assert "Premium Still-SR Frequency Filter Audit" in html

    print("test_audit_premium_still_sr_frequency_filter: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
