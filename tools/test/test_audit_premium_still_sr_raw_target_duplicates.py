#!/usr/bin/env python3
"""Regression test for the premium still-SR raw target duplicate audit."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_raw_target_duplicates.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("raw_target_duplicate_audit", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_raw_target_duplicates: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_raw_target_duplicate_audit_", dir=tmp_parent) as td:
        root = Path(td)
        base = np.arange(8 * 8 * 4, dtype=np.float32).reshape(8, 8, 4) / 255.0
        render0 = np.arange(8 * 8, dtype=np.float32).reshape(8, 8) / 100.0
        rows = []
        raw_arrays = {name: [] for name in tool.RAW_ARRAYS}
        render_rows = []
        for ev in (-2.0, 0.0, 2.0):
            rows.append({"scene_id": "scene_a", "crop": "center", "ev": ev})
            for name in tool.RAW_ARRAYS:
                raw_arrays[name].append(base.astype(np.float16))
            render_rows.append((render0 + ev * 0.01).astype(np.float16))
        targets = root / "targets.npz"
        np.savez_compressed(
            targets,
            **{name: np.stack(values) for name, values in raw_arrays.items()},
            render_hf_residual_y=np.stack(render_rows),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type(
            "Args",
            (),
            {
                "targets": targets,
                "output_dir": root / "out",
                "raw_duplicate_epsilon": 0.0,
                "render_vary_epsilon": 1.0e-6,
            },
        )()
        payload = tool.run(args)
        assert payload["schema"] == tool.SCHEMA
        assert payload["summary"]["row_count"] == 3
        assert payload["summary"]["unique_scene_crop_count"] == 1
        assert payload["summary"]["duplicate_factor"] == 3.0
        assert payload["summary"]["raw_duplicate_ev_group_count"] == 1
        assert payload["summary"]["render_varying_ev_group_count"] == 1
        assert payload["production_ready"] is False
        html = Path(payload["artifacts"]["dashboard"]).read_text(encoding="utf-8")
        assert "Premium Still-SR Raw Target Duplicate Audit" in html

    print("test_audit_premium_still_sr_raw_target_duplicates: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
