#!/usr/bin/env python3
"""Regression test for clean-source premium still-SR pair training."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
    import torch  # noqa: F401
except ImportError:  # pragma: no cover
    np = None


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/train_premium_still_sr_clean_source_pairs.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def make_target(inp: np.ndarray, delta: int) -> np.ndarray:
    return np.repeat(np.repeat(inp, 2, axis=1), 2, axis=2).astype(np.uint16) + np.uint16(delta)


def main() -> int:
    if np is None:
        print("test_train_premium_still_sr_clean_source_pairs: SKIP missing numpy/torch")
        return 0
    with tempfile.TemporaryDirectory(prefix="gpr_clean_pair_train_", dir=temp_root()) as tmp:
        td = Path(tmp)
        rng = np.random.default_rng(123)
        inputs = rng.integers(100, 1000, size=(4, 4, 8, 8), dtype=np.uint16)
        targets = np.stack([make_target(inputs[i], 3) for i in range(len(inputs))])
        tiles = [
            {"image_id": "train_a", "low_x": 0, "low_y": 0},
            {"image_id": "train_a", "low_x": 8, "low_y": 0},
            {"image_id": "holdout_b", "low_x": 0, "low_y": 8},
            {"image_id": "holdout_b", "low_x": 8, "low_y": 8},
        ]
        meta = {
            "schema": "gpr.premium_still_sr_pairs.v1",
            "dataset_label": "synthetic_clean_pair_train",
            "images": [{"image_id": "train_a"}, {"image_id": "holdout_b"}],
            "tiles": tiles,
            "low_tile": 8,
            "high_tile": 16,
            "width12": 16,
            "height12": 16,
        }
        pairs = td / "pairs.npz"
        np.savez_compressed(pairs, inputs=inputs, targets=targets, meta=json.dumps(meta, sort_keys=True))
        out = td / "run"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pairs",
                str(pairs),
                "--output-dir",
                str(out),
                "--holdout-image",
                "holdout",
                "--steps",
                "3",
                "--batch",
                "2",
                "--low-crop",
                "8",
                "--model-arch",
                "naf_residual_pixelshuffle",
                "--width",
                "8",
                "--depth",
                "3",
                "--gradient-loss-weight",
                "0.1",
                "--eval-every",
                "1",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        receipt = json.loads((out / "train_receipt.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_clean_source_pair_model.v1"
        assert receipt["pair_meta"]["input_shape"] == [4, 4, 8, 8]
        assert receipt["pair_meta"]["target_shape"] == [4, 4, 16, 16]
        assert receipt["config"]["model_arch"] == "naf_residual_pixelshuffle"
        assert receipt["config"]["gradient_loss_weight"] == 0.1
        assert "gradient_l1" in receipt["history"][0]
        assert receipt["eval"]["train"]["tile_count"] == 2
        assert receipt["eval"]["holdout"]["tile_count"] == 2
        assert receipt["promotion"]["coverage_sufficient_for_promotion"] is False
        assert (out / "premium_still_sr_clean_source_pair_model.pt").is_file()
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Clean-Source Pair Model" in html
        restormer_out = td / "restormer_run"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pairs",
                str(pairs),
                "--output-dir",
                str(restormer_out),
                "--holdout-image",
                "holdout_b",
                "--steps",
                "2",
                "--batch",
                "2",
                "--low-crop",
                "8",
                "--model-arch",
                "restormer_pixelshuffle",
                "--width",
                "8",
                "--depth",
                "2",
                "--eval-every",
                "1",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        restormer_receipt = json.loads((restormer_out / "train_receipt.json").read_text(encoding="utf-8"))
        assert restormer_receipt["config"]["model_arch"] == "restormer_pixelshuffle"
        assert restormer_receipt["eval"]["holdout"]["tile_count"] == 2
    print("test_train_premium_still_sr_clean_source_pairs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
