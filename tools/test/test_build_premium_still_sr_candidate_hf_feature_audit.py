#!/usr/bin/env python3
"""Regression test for the Premium still-SR candidate-HF feature audit."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_candidate_hf_feature_audit.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("candidate_hf_feature_audit", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    mod = load_tool()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        targets = root / "targets.npz"
        rows = [
            {"class": "50mp", "scene_id": "z8", "crop": "a"},
            {"class": "100mp", "scene_id": "x2d", "crop": "b"},
        ]
        target = np.ones((2, 4, 4, 4), dtype=np.float32) * 0.25
        candidate_hf = target.copy()
        np.savez_compressed(
            targets,
            raw_hf_residual_cfa4=target,
            candidate_raw_hf_cfa4=candidate_hf,
            meta=json.dumps(rows),
        )
        args = SimpleNamespace(targets=targets, output_dir=root / "out", alphas="0 0.5 1.0", max_rows=0)
        receipt = mod.run_audit(args)
        assert receipt["schema"] == mod.SCHEMA
        assert receipt["coverage"]["target_row_count"] == 2
        assert receipt["coverage"]["classes"] == {"100mp": 1, "50mp": 1}
        assert receipt["best_alpha_summary"]["alpha"] == 1.0
        assert receipt["best_alpha_summary"]["mae_reduction_pct"]["median"] == 100.0
        assert receipt["next_decision"] == "candidate_hf_feature_has_scalar_signal"
    print("test_build_premium_still_sr_candidate_hf_feature_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
