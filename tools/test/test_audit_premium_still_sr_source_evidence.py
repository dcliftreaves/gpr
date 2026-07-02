#!/usr/bin/env python3
"""Regression test for premium still-SR source-evidence audit."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_source_evidence.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("source_evidence_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_source_evidence: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    rng = np.random.default_rng(123)
    n, c, h, w = 8, 4, 8, 8
    inputs = rng.integers(100, 4000, size=(n, c, h, w), dtype=np.uint16).astype(np.float32)
    nearest = np.repeat(np.repeat(inputs, 2, axis=2), 2, axis=3)
    targets = nearest.copy()
    # Add deterministic subpixel signal that a 3x3 local probe can recover from
    # the candidate input, while nearest cannot.
    shifted = np.roll(inputs, shift=1, axis=3)
    for phase_y in (0, 1):
        for phase_x in (0, 1):
            targets[:, :, phase_y::2, phase_x::2] = (
                0.85 * targets[:, :, phase_y::2, phase_x::2] + 0.15 * shifted
            )
    meta = {
        "schema": "gpr.premium_still_sr_pairs.v1",
        "images": [
            {"image_id": "train_a", "camera_key": "z8"},
            {"image_id": "train_b", "camera_key": "mission1"},
            {"image_id": "holdout_a", "camera_key": "x2d"},
        ],
        "tiles": [],
    }
    for idx in range(n):
        if idx < 3:
            image_id = "train_a"
        elif idx < 6:
            image_id = "train_b"
        else:
            image_id = "holdout_a"
        meta["tiles"].append({"image_id": image_id})

    with tempfile.TemporaryDirectory(prefix="gpr_source_evidence_") as td:
        tmp = Path(td)
        pairs = tmp / "pairs.npz"
        np.savez_compressed(pairs, inputs=inputs, targets=targets, meta=json.dumps(meta))
        class Args:
            pass

        args = Args()
        args.pairs = pairs
        args.output_dir = tmp / "out"
        args.holdout_camera = "x2d"
        args.radius = 1
        args.max_train_samples = 4096
        args.ridge_lambda = 0.01
        args.min_recovery_pct = 0.1
        args.seed = 7
        audit = tool.build_audit(args)
        assert audit["schema"] == tool.SCHEMA
        assert audit["holdout_tile_count"] == 2
        assert audit["train_tile_count"] == 6
        assert len(audit["phase_rows"]) == 4
        assert audit["summary"]["linear_probe_mae_recovery_pct"]["median"] > 0.0
        assert audit["acceptance"]["verdict"] == "source_signal_detected"

    print("test_audit_premium_still_sr_source_evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
