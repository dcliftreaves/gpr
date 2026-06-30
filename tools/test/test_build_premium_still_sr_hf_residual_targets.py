#!/usr/bin/env python3
"""Regression test for premium still-SR HF residual target helpers."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_premium_still_sr_hf_residual_targets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("hf_residual_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
        import PIL  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_hf_residual_targets: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_hf_residual_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((64, 64))
        base = np.full((64, 64, 3), 12000, dtype=np.uint16)
        detail = (((x + y) % 4) == 0).astype(np.uint16) * 600
        ref = base.copy()
        ref[:, :, 0] += detail
        ref[:, :, 1] += detail
        ref[:, :, 2] += detail
        cand = base.copy()
        cand[:, :, 0] += detail // 3
        cand[:, :, 1] += detail // 3
        cand[:, :, 2] += detail // 3
        candidate_raw_norm = ((x + y) / 128.0).astype(np.float32)
        rows, inputs, residuals, targets, raw_cfa_features = tool.build_rows_from_arrays(
            ref=ref,
            cand=cand,
            candidate_raw_norm=candidate_raw_norm,
            ev=0.0,
            crop_size=32,
            crop_grid=2,
            max_crops_per_ev=None,
            block=8,
            residual_scale=0.08,
            panels_dir=root / "panels",
            scene_id="synthetic_scene",
            source_dng=root / "source.dng",
            candidate_dng=root / "candidate.dng",
        )
        assert len(rows) == 4
        assert len(inputs) == len(residuals) == len(targets) == len(raw_cfa_features) == 4
        assert rows[0]["scene_id"] == "synthetic_scene"
        assert rows[0]["crop"].startswith("grid2_")
        assert rows[0]["source_dng"].endswith("source.dng")
        assert rows[0]["candidate_raw_cfa_features"] == "local_2x2_cfa_planes_repeated_to_rgb_crop"
        assert rows[0]["residual_abs_mean"] > 0.0
        assert rows[0]["target_cleaning"] == "none"
        assert rows[0]["hf_y_correlation"] is not None
        npz = root / "targets.npz"
        tool.write_npz(npz, inputs, residuals, targets, rows, raw_cfa_features)
        assert npz.stat().st_size > 0
        with np.load(npz, allow_pickle=False) as z:
            assert z["inputs"].shape == z["hf_residuals"].shape
            assert z["inputs"].dtype == np.float16
            assert z["candidate_raw_cfa4"].shape == (4, 32, 32, 4)
        raw_planes = tool.local_cfa4_planes(candidate_raw_norm[:4, :4])
        assert raw_planes.shape == (4, 4, 4)
        assert np.isclose(raw_planes[0, 0, 0], candidate_raw_norm[0, 0])
        assert np.isclose(raw_planes[0, 0, 3], candidate_raw_norm[1, 1])
        sidecar = root / "noise_sidecar.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.camera_noise_calibration.v1",
                    "camera": {"black_level": 0.0, "white_level": 10000.0},
                    "calibrations": [
                        {
                            "usable_for_training_targets": True,
                            "iso": 800,
                            "sample_count": 8,
                            "per_plane": {
                                "r": {"sigma_black": 10.0},
                                "g1": {"sigma_black": 10.0},
                                "g2": {"sigma_black": 10.0},
                                "b": {"sigma_black": 10.0},
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        floor, floor_rows = tool.mean_noise_sigma_norm([sidecar], render_gain=1.0)
        assert np.isclose(floor, 0.001)
        assert floor_rows[0]["usable_for_training_targets"] is True
        tiny_residual = np.full((8, 8, 3), floor * 0.75, dtype=np.float32)
        low_texture = np.zeros_like(tiny_residual)
        cleaned, clean_stats = tool.conservative_noise_floor_clean(
            tiny_residual,
            low_texture,
            low_texture,
            noise_floor=floor,
            sigma_mult=1.0,
            texture_mult=2.0,
        )
        assert np.max(np.abs(cleaned)) == 0.0
        assert clean_stats["changed_fraction"] == 1.0
        strong_texture = np.ones_like(tiny_residual) * 0.1
        preserved, preserve_stats = tool.conservative_noise_floor_clean(
            tiny_residual,
            strong_texture,
            low_texture,
            noise_floor=floor,
            sigma_mult=1.0,
            texture_mult=2.0,
        )
        assert np.allclose(preserved, tiny_residual)
        assert preserve_stats["changed_fraction"] == 0.0
        contact = root / "contact.jpg"
        tool.write_contact_sheet(contact, rows, 4)
        assert contact.stat().st_size > 0
        raw = root / "candidate.raw"
        raw.write_bytes(b"\x00" * (16 * 12 * 2))
        (root / "candidate.raw.json").write_text(
            json.dumps({"candidate": {"width": 16, "height": 12}}),
            encoding="utf-8",
        )
        assert tool.infer_candidate_raw_shape(raw) == (16, 12)

    print("test_build_premium_still_sr_hf_residual_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
