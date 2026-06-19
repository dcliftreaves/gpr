#!/usr/bin/env python3
"""Regression tests for Mission 1 SR checkpoint width expansion."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import torch


REPO = Path(__file__).resolve().parents[2]
TRAINER = REPO / "tools" / "cnn" / "train_mission1_sr.py"


def load_trainer():
    spec = importlib.util.spec_from_file_location("train_mission1_sr", TRAINER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lowres_width_expansion_preserves_source_output() -> None:
    trainer = load_trainer()
    torch.manual_seed(7)
    source = trainer.LowResPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    for param in source.parameters():
        torch.nn.init.normal_(param, mean=0.0, std=0.03)

    target = trainer.LowResPixelShuffleSR(width=10, depth=5, residual_scale=0.3)
    expanded, skipped, unexpected = trainer.expand_lowres_pixelshuffle_state(
        source.state_dict(),
        target.state_dict(),
    )
    assert not skipped
    assert not unexpected
    target.load_state_dict(expanded, strict=True)

    x = torch.rand(2, 4, 12, 12)
    with torch.no_grad():
        expected = source(x)
        actual = target(x)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=1e-6)


def test_lowres_to_adapter_expansion_preserves_source_output() -> None:
    trainer = load_trainer()
    torch.manual_seed(11)
    source = trainer.LowResPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    for param in source.parameters():
        torch.nn.init.normal_(param, mean=0.0, std=0.03)

    target = trainer.AdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    expanded, _skipped, unexpected = trainer.expand_lowres_pixelshuffle_state(
        source.state_dict(),
        target.state_dict(),
    )
    assert not unexpected
    target.load_state_dict(expanded, strict=True)

    x = torch.rand(2, 4, 12, 12)
    with torch.no_grad():
        expected = source(x)
        actual = target(x)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=1e-6)


def test_adapter_to_preclean_preserves_source_output() -> None:
    trainer = load_trainer()
    torch.manual_seed(13)
    source = trainer.AdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    for param in source.parameters():
        torch.nn.init.normal_(param, mean=0.0, std=0.03)

    target = trainer.PrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    remapped = {f"sr.{key}": value for key, value in source.state_dict().items()}
    result = target.load_state_dict(remapped, strict=False)
    assert all(key.startswith("preclean.") for key in result.missing_keys)
    assert not result.unexpected_keys

    x = torch.rand(2, 4, 12, 12)
    with torch.no_grad():
        expected = source(x)
        actual = target(x)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=1e-6)


def test_adapter_to_green_detail_preserves_source_output() -> None:
    trainer = load_trainer()
    torch.manual_seed(15)
    source = trainer.AdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    for param in source.parameters():
        torch.nn.init.normal_(param, mean=0.0, std=0.03)

    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="green_detail_init_", dir=work_parent) as td:
        ckpt = Path(td) / "adapter.pt"
        torch.save(
            {
                "model": source.state_dict(),
                "config": {
                    "architecture": "adapter_pixelshuffle",
                    "width": 6,
                    "depth": 5,
                    "residual_scale": 0.3,
                },
            },
            ckpt,
        )
        target = trainer.GreenDetailAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
        result, details = trainer.initialize_model(
            target,
            ckpt,
            architecture="green_detail_adapter_pixelshuffle",
            width=6,
            depth=5,
            residual_scale=0.3,
            init_nonstrict=False,
            init_expand_lowres=False,
        )

    assert details["mode"] == "adapter_to_green_detail_adapter"
    assert all(key.startswith("green_detail.") for key in result.missing_keys)
    assert not result.unexpected_keys
    x = torch.rand(2, 4, 12, 12)
    with torch.no_grad():
        expected = source(x)
        actual = target(x)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=1e-6)


def test_preclean_to_coord_preclean_preserves_source_output() -> None:
    trainer = load_trainer()
    torch.manual_seed(17)
    source = trainer.PrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    for param in source.parameters():
        torch.nn.init.normal_(param, mean=0.0, std=0.03)

    target = trainer.CoordPrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    expanded, skipped, unexpected = trainer.initialize_coord_preclean_from_preclean(
        source.state_dict(),
        target.state_dict(),
    )
    assert not skipped
    assert not unexpected
    target.load_state_dict(expanded, strict=True)

    x = torch.rand(2, 4, 12, 12)
    coords = torch.rand(2, 2, 12, 12) * 2.0 - 1.0
    with torch.no_grad():
        expected = source(x)
        actual = target(torch.cat([x, coords], dim=1))
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=1e-6)


def test_coord_preclean_continuation_loads_same_architecture() -> None:
    trainer = load_trainer()
    torch.manual_seed(19)
    source = trainer.CoordPrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    for param in source.parameters():
        torch.nn.init.normal_(param, mean=0.0, std=0.03)

    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="coord_preclean_init_", dir=work_parent) as td:
        ckpt = Path(td) / "coord.pt"
        torch.save(
            {
                "model": source.state_dict(),
                "config": {
                    "architecture": "coord_preclean_adapter_pixelshuffle",
                    "width": 6,
                    "depth": 5,
                    "residual_scale": 0.3,
                    "coordinate_channels": True,
                },
            },
            ckpt,
        )
        target = trainer.CoordPrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
        result, details = trainer.initialize_model(
            target,
            ckpt,
            architecture="coord_preclean_adapter_pixelshuffle",
            width=6,
            depth=5,
            residual_scale=0.3,
            init_nonstrict=False,
            init_expand_lowres=False,
        )

    assert details["mode"] == "load_state_dict"
    assert not result.missing_keys
    assert not result.unexpected_keys
    x = torch.rand(2, 6, 12, 12)
    with torch.no_grad():
        expected = source(x)
        actual = target(x)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=1e-6)


def test_coord_deep_preclean_loads_coord_preclean_function() -> None:
    trainer = load_trainer()
    torch.manual_seed(23)
    source = trainer.CoordPrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
    for param in source.parameters():
        torch.nn.init.normal_(param, mean=0.0, std=0.03)

    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="coord_deep_preclean_init_", dir=work_parent) as td:
        ckpt = Path(td) / "coord.pt"
        torch.save(
            {
                "model": source.state_dict(),
                "config": {
                    "architecture": "coord_preclean_adapter_pixelshuffle",
                    "width": 6,
                    "depth": 5,
                    "residual_scale": 0.3,
                    "coordinate_channels": True,
                },
            },
            ckpt,
        )
        target = trainer.CoordDeepPrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)
        result, details = trainer.initialize_model(
            target,
            ckpt,
            architecture="coord_deep_preclean_adapter_pixelshuffle",
            width=6,
            depth=5,
            residual_scale=0.3,
            init_nonstrict=False,
            init_expand_lowres=False,
        )

    assert details["mode"] == "coord_preclean_to_coord_deep_preclean"
    assert all(key.startswith("preclean_extra.") for key in result.missing_keys)
    assert not result.unexpected_keys
    x = torch.rand(2, 6, 12, 12)
    with torch.no_grad():
        expected = source(x)
        actual = target(x)
    torch.testing.assert_close(actual, expected, rtol=0.0, atol=1e-6)


def test_trainable_scope_freezes_preclean_adapter_trunk() -> None:
    trainer = load_trainer()
    model = trainer.PrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)

    details = trainer.configure_trainable_scope(model, "adapter_and_preclean")

    assert details["trainable_parameter_count"] > 0
    assert details["frozen_parameter_count"] > 0
    for name, param in model.named_parameters():
        if name.startswith(("sr.adapter.", "preclean.")):
            assert param.requires_grad, name
        else:
            assert not param.requires_grad, name


def test_trainable_scope_freezes_green_detail_adapter_trunk() -> None:
    trainer = load_trainer()
    model = trainer.GreenDetailAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)

    details = trainer.configure_trainable_scope(model, "green_detail_only")

    assert details["trainable_parameter_count"] > 0
    assert details["frozen_parameter_count"] > 0
    for name, param in model.named_parameters():
        if name.startswith("green_detail."):
            assert param.requires_grad, name
        else:
            assert not param.requires_grad, name


def test_pairs_dataset_derives_dimensions_from_merged_image_rows() -> None:
    trainer = load_trainer()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_sr_merged_dims_", dir=work_parent) as td:
        pairs = Path(td) / "pairs.npz"
        inputs = np.zeros((4, 4, 6, 6), dtype=np.uint16)
        targets = np.zeros((4, 4, 12, 12), dtype=np.uint16)
        meta = {
            "schema": "mission1_sr_pairs_merged.v1",
            "low_tile": 6,
            "images": [
                {"image_id": "A", "low_width": 20, "low_height": 12},
                {"image_id": "B", "low_width": 18, "low_height": 10},
            ],
            "tiles": [
                {"image_id": "A", "low_x": 0, "low_y": 0},
                {"image_id": "A", "low_x": 2, "low_y": 0},
                {"image_id": "B", "low_x": 0, "low_y": 0},
                {"image_id": "B", "low_x": 2, "low_y": 0},
            ],
        }
        np.savez(pairs, inputs=inputs, targets=targets, meta=json.dumps(meta))
        dataset = trainer.Mission1SRPairs(pairs, holdout_image="B")

    assert dataset.plane_width == 10
    assert dataset.plane_height == 6
    assert len(dataset.train_idx) == 2
    assert len(dataset.eval_idx) == 2


def test_trainable_scope_includes_deep_preclean_extra() -> None:
    trainer = load_trainer()
    model = trainer.CoordDeepPrecleanAdapterPixelShuffleSR(width=6, depth=5, residual_scale=0.3)

    details = trainer.configure_trainable_scope(model, "adapter_and_preclean")

    assert any(name.startswith("preclean_extra.") for name in details["trainable_names"])
    for name, param in model.named_parameters():
        if name.startswith(("sr.adapter.", "adapter.", "preclean.", "preclean_extra.")):
            assert param.requires_grad, name
        else:
            assert not param.requires_grad, name


def test_plane_weighted_loss_preserves_uniform_behavior() -> None:
    trainer = load_trainer()
    pred = torch.zeros(1, 4, 2, 2)
    target = torch.ones(1, 4, 2, 2)
    target[:, 0] = 4.0

    uniform = trainer.plane_weight_tensor((1.0, 1.0, 1.0, 1.0), torch.device("cpu"))
    weighted = trainer.plane_weight_tensor((4.0, 1.0, 1.0, 1.0), torch.device("cpu"))

    unweighted_loss = trainer.robust_l1(pred, target, "l1", None)
    uniform_loss = trainer.robust_l1(pred, target, "l1", uniform)
    red_weighted_loss = trainer.robust_l1(pred, target, "l1", weighted)

    torch.testing.assert_close(uniform_loss, unweighted_loss, rtol=0.0, atol=1e-7)
    assert red_weighted_loss > uniform_loss
    assert trainer.parse_plane_weights("1,2,3,4") == (1.0, 2.0, 3.0, 4.0)


def test_detail_phase_loss_weights_same_color_planes() -> None:
    trainer = load_trainer()
    target = torch.zeros(1, 4, 8, 8)
    pred = target.clone()
    target[:, 0, 2:6, 2:6] = 1.0
    pred[:, 0, 2:6, 2:6] = -1.0

    uniform = trainer.plane_weight_tensor((1.0, 1.0, 1.0, 1.0), torch.device("cpu"))
    red_weighted = trainer.plane_weight_tensor((4.0, 1.0, 1.0, 1.0), torch.device("cpu"))

    loss_uniform = trainer.detail_phase_loss(pred, target, "l1", uniform)
    loss_red = trainer.detail_phase_loss(pred, target, "l1", red_weighted)
    loss_masked = trainer.detail_phase_loss(pred, target, "l1", red_weighted, threshold_counts=1.0)

    assert loss_red > loss_uniform
    assert loss_masked > 0.0


if __name__ == "__main__":
    test_lowres_width_expansion_preserves_source_output()
    test_lowres_to_adapter_expansion_preserves_source_output()
    test_adapter_to_preclean_preserves_source_output()
    test_preclean_to_coord_preclean_preserves_source_output()
    test_coord_preclean_continuation_loads_same_architecture()
    test_coord_deep_preclean_loads_coord_preclean_function()
    test_trainable_scope_freezes_preclean_adapter_trunk()
    test_trainable_scope_includes_deep_preclean_extra()
    test_plane_weighted_loss_preserves_uniform_behavior()
    test_detail_phase_loss_weights_same_color_planes()
