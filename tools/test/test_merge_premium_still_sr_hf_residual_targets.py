#!/usr/bin/env python3
"""Regression test for premium still-SR HF residual target merge."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/merge_premium_still_sr_hf_residual_targets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("merge_hf_targets_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_merge_premium_still_sr_hf_residual_targets: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_merge_hf_targets_", dir=tmp_parent) as td:
        root = Path(td)
        targets = []
        for idx, scene in enumerate(["scene_a", "scene_b"]):
            arr = np.full((2, 8, 8, 3), idx + 1, dtype=np.float16)
            raw_cfa = np.full((2, 8, 8, 4), idx + 2, dtype=np.float16)
            rows = [
                {"scene_id": scene, "crop": f"crop_{row}", "residual_abs_mean": 0.01 * (idx + row + 1), "hf_y_correlation": 0.5}
                for row in range(2)
            ]
            path = root / f"{scene}.npz"
            np.savez_compressed(
                path,
                inputs=arr,
                hf_residuals=arr * 0.1,
                source_hf_targets=arr * 0.2,
                candidate_raw_cfa4=raw_cfa,
                meta=np.asarray(json.dumps(rows)),
            )
            targets.append(path)
        args = type("Args", (), {"target": targets, "output_dir": root / "out"})()
        receipt = tool.merge(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["summary"]["row_count"] == 4
        assert receipt["summary"]["scene_count"] == 2
        assert receipt["summary"]["raw_cfa_feature_complete"] is True
        assert Path(receipt["output_npz"]).stat().st_size > 0
        with np.load(receipt["output_npz"], allow_pickle=False) as z:
            assert z["inputs"].shape == (4, 8, 8, 3)
            assert z["candidate_raw_cfa4"].shape == (4, 8, 8, 4)

        mixed = root / "mixed_no_raw.npz"
        arr = np.zeros((1, 8, 8, 3), dtype=np.float16)
        np.savez_compressed(
            mixed,
            inputs=arr,
            hf_residuals=arr,
            source_hf_targets=arr,
            meta=np.asarray(json.dumps([{"scene_id": "scene_c", "residual_abs_mean": 0.01, "hf_y_correlation": 0.5}])),
        )
        mixed_args = type("Args", (), {"target": [targets[0], mixed], "output_dir": root / "mixed_out"})()
        mixed_receipt = tool.merge(mixed_args)
        assert mixed_receipt["summary"]["raw_cfa_feature_complete"] is False
        with np.load(mixed_receipt["output_npz"], allow_pickle=False) as z:
            assert "candidate_raw_cfa4" not in z.files

    print("test_merge_premium_still_sr_hf_residual_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
