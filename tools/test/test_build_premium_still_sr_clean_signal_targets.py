#!/usr/bin/env python3
"""Regression test for clean-signal premium still-SR target builder."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_premium_still_sr_clean_signal_targets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("clean_signal_targets", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_clean_signal_targets: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_clean_signal_targets_", dir=tmp_parent) as td:
        root = Path(td)
        sidecar = root / "noise.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.camera_noise_calibration.v1",
                    "camera": {"black_level": 0.0, "white_level": 1000.0},
                    "calibrations": [
                        {
                            "iso": 1600,
                            "per_plane": {
                                "r": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.4,
                                },
                                "g1": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.4,
                                },
                                "g2": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.4,
                                },
                                "b": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.4,
                                },
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        target = np.zeros((2, 10, 10, 4), dtype=np.float32)
        target[0] = 0.00075
        target[1] = 0.006
        target[1, 0, 0, 0] = -0.006
        candidate_hf = np.full_like(target, 0.02)
        rows = [
            {
                "scene_id": "synthetic_noise_floor",
                "crop": "center",
                "source_dng": "/fixtures/x2d/noise.dng",
                "raw_target_kind": "source_minus_candidate_same_color_highpass_residual",
                "noise_sidecars": [str(sidecar)],
            },
            {
                "scene_id": "synthetic_signal",
                "crop": "center",
                "source_dng": "/fixtures/x2d/signal.dng",
                "raw_target_kind": "source_minus_candidate_same_color_highpass_residual",
                "noise_sidecars": [str(sidecar)],
            },
        ]
        targets_path = root / "targets.npz"
        np.savez_compressed(
            targets_path,
            candidate_raw_cfa4=np.zeros_like(target, dtype=np.float16),
            candidate_raw_hf_cfa4=candidate_hf.astype(np.float16),
            raw_hf_residual_cfa4=target.astype(np.float16),
            source_raw_hf_cfa4=(candidate_hf + target).astype(np.float16),
            render_hf_residual_y=np.zeros(target.shape[:3], dtype=np.float16),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type(
            "Args",
            (),
            {
                "targets": targets_path,
                "output_dir": root / "out",
                "sigma_scale": 2.0,
                "p95_scale": 0.5,
                "fpn_scale": 1.0,
                "ramp_width": 1.0,
                "min_threshold": 0.0,
                "missing_sidecar_threshold": 1.0,
                "write_confidence": True,
            },
        )()
        receipt = tool.run(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert receipt["policy"]["exact_source_noise_addback_allowed_at_runtime"] is False
        assert receipt["summary"]["row_count"] == 2
        assert receipt["summary"]["rows_with_noise_sidecars"] == 2
        by_scene = {row["scene_id"]: row for row in receipt["rows"]}
        assert by_scene["synthetic_noise_floor"]["target_energy_retained_fraction"] == 0.0
        assert by_scene["synthetic_signal"]["target_energy_retained_fraction"] > 0.4
        assert by_scene["synthetic_noise_floor"]["classification"] == "suppressed_noise_floor"
        assert by_scene["synthetic_signal"]["classification"] == "retained_signal"

        out = np.load(receipt["artifacts"]["clean_targets_npz"], allow_pickle=False)
        assert "candidate_raw_cfa4" in out.files
        assert "candidate_raw_hf_cfa4" in out.files
        assert "raw_hf_residual_cfa4" in out.files
        assert "source_raw_hf_cfa4" in out.files
        assert "clean_signal_confidence_cfa4" in out.files
        clean = out["raw_hf_residual_cfa4"].astype(np.float32)
        assert float(np.max(np.abs(clean[0]))) == 0.0
        assert float(np.mean(np.abs(clean[1]))) > 0.004
        out_meta = json.loads(str(out["meta"]))
        assert out_meta[0]["clean_signal_target"]["schema"] == tool.SCHEMA
        assert out_meta[1]["clean_signal_target"]["noise_available"] is True
        assert Path(receipt["artifacts"]["dashboard"]).read_text(encoding="utf-8").find("Clean-Signal Targets") >= 0

    print("test_build_premium_still_sr_clean_signal_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
