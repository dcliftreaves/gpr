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
    help_proc = subprocess.run(
        [sys.executable, str(TOOL), "--help"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if help_proc.returncode != 0:
        print(help_proc.stdout)
        print(help_proc.stderr, file=sys.stderr)
        return help_proc.returncode
    assert "Train/evaluate clean-source RAW pair SR" in help_proc.stdout
    assert "--pairs" in help_proc.stdout
    assert "--output-dir" in help_proc.stdout
    assert "window_attention_pixelshuffle" in help_proc.stdout
    assert "frequency_pyramid_pixelshuffle" in help_proc.stdout
    assert "gated_frequency_pyramid_pixelshuffle" in help_proc.stdout
    assert "--detail-mask-threshold-counts" in help_proc.stdout
    assert "--detail-mask-loss-weight" in help_proc.stdout
    assert "--no-detail-noop-loss-weight" in help_proc.stdout

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
                "--laplacian-loss-weight",
                "0.05",
                "--loss-mode",
                "charbonnier",
                "--train-input-noise-std-counts",
                "2.0",
                "--train-input-gain-jitter-pct",
                "0.5",
                "--train-input-blur-weight",
                "0.1",
                "--detail-mask-threshold-counts",
                "1.0",
                "--detail-mask-loss-weight",
                "0.25",
                "--no-detail-noop-loss-weight",
                "0.75",
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
        assert receipt["config"]["laplacian_loss_weight"] == 0.05
        assert receipt["config"]["loss_mode"] == "charbonnier"
        assert receipt["config"]["train_input_noise_std_counts"] == 2.0
        assert receipt["config"]["train_input_gain_jitter_pct"] == 0.5
        assert receipt["config"]["train_input_blur_weight"] == 0.1
        assert receipt["config"]["detail_mask_threshold_counts"] == 1.0
        assert receipt["config"]["detail_mask_loss_weight"] == 0.25
        assert receipt["config"]["no_detail_noop_loss_weight"] == 0.75
        assert "gradient_l1" in receipt["history"][0]
        assert "laplacian_l1" in receipt["history"][0]
        assert "pixel_loss" in receipt["history"][0]
        assert "detail_mask_l1" in receipt["history"][0]
        assert "no_detail_noop_l1" in receipt["history"][0]
        assert "detail_mask_fraction" in receipt["history"][0]
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
        window_out = td / "window_attention_run"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pairs",
                str(pairs),
                "--output-dir",
                str(window_out),
                "--holdout-image",
                "holdout_b",
                "--steps",
                "1",
                "--batch",
                "2",
                "--low-crop",
                "8",
                "--model-arch",
                "window_attention_pixelshuffle",
                "--width",
                "8",
                "--depth",
                "1",
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
        window_receipt = json.loads((window_out / "train_receipt.json").read_text(encoding="utf-8"))
        assert window_receipt["config"]["model_arch"] == "window_attention_pixelshuffle"
        assert window_receipt["eval"]["holdout"]["tile_count"] == 2
        frequency_out = td / "frequency_pyramid_run"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pairs",
                str(pairs),
                "--output-dir",
                str(frequency_out),
                "--holdout-image",
                "holdout_b",
                "--steps",
                "1",
                "--batch",
                "2",
                "--low-crop",
                "8",
                "--model-arch",
                "frequency_pyramid_pixelshuffle",
                "--width",
                "8",
                "--depth",
                "1",
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
        frequency_receipt = json.loads((frequency_out / "train_receipt.json").read_text(encoding="utf-8"))
        assert frequency_receipt["config"]["model_arch"] == "frequency_pyramid_pixelshuffle"
        assert frequency_receipt["eval"]["holdout"]["tile_count"] == 2
        gated_out = td / "gated_frequency_pyramid_run"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pairs",
                str(pairs),
                "--output-dir",
                str(gated_out),
                "--holdout-image",
                "holdout_b",
                "--steps",
                "1",
                "--batch",
                "2",
                "--low-crop",
                "8",
                "--model-arch",
                "gated_frequency_pyramid_pixelshuffle",
                "--width",
                "8",
                "--depth",
                "1",
                "--baseline-worsening-loss-weight",
                "0.5",
                "--residual-energy-loss-weight",
                "0.05",
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
        gated_receipt = json.loads((gated_out / "train_receipt.json").read_text(encoding="utf-8"))
        assert gated_receipt["config"]["model_arch"] == "gated_frequency_pyramid_pixelshuffle"
        assert gated_receipt["config"]["baseline_worsening_loss_weight"] == 0.5
        assert gated_receipt["config"]["residual_energy_loss_weight"] == 0.05
        assert gated_receipt["eval"]["holdout"]["tile_count"] == 2
    print("test_train_premium_still_sr_clean_source_pairs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
