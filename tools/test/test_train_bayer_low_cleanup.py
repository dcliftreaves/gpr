#!/usr/bin/env python3
"""Regression checks for Bayer low-cleanup training helpers."""

from __future__ import annotations

from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "cnn"))

from train_bayer_low_cleanup import detail_content_loss  # noqa: E402


def test_detail_content_loss_tracks_same_color_detail() -> None:
    target = torch.zeros((1, 4, 12, 12), dtype=torch.float32)
    pred_bad = target.clone()
    pred_good = target.clone()

    target[:, 0, 4:8, 4:8] = 0.25
    pred_bad[:, 0, 4:8, 4:8] = -0.25
    pred_good[:, 0, 4:8, 4:8] = 0.22

    weights = torch.tensor([2.0, 1.0, 1.0, 1.0], dtype=torch.float32).view(1, 4, 1, 1)
    bad = detail_content_loss(pred_bad, target, threshold_counts=1.0, plane_weights=weights)
    good = detail_content_loss(pred_good, target, threshold_counts=1.0, plane_weights=weights)
    assert float(good) < float(bad) * 0.25


if __name__ == "__main__":
    test_detail_content_loss_tracks_same_color_detail()
    print("test_train_bayer_low_cleanup: PASS")
