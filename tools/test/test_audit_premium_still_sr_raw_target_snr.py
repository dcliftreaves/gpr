#!/usr/bin/env python3
"""Regression test for premium still-SR raw-target SNR audit."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_raw_target_snr.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("raw_target_snr_audit", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_raw_target_snr: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_raw_target_snr_", dir=tmp_parent) as td:
        root = Path(td)
        sidecar = root / "noise.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.camera_noise_calibration.v1",
                    "camera": {"black_level": 0.0, "white_level": 1000.0},
                    "calibrations": [
                        {
                            "iso": 800,
                            "per_plane": {
                                "r": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.2,
                                },
                                "g1": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.2,
                                },
                                "g2": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.2,
                                },
                                "b": {
                                    "sigma_black": 1.0,
                                    "temporal_noise_p95_counts": 3.0,
                                    "spatial_fpn_rms_counts": 0.2,
                                },
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        target = np.zeros((2, 12, 12, 4), dtype=np.float32)
        target[0] = 0.006
        target[1] = 0.0005
        candidate_hf = np.full_like(target, 0.04)
        source_hf = candidate_hf + target
        rows = [
            {
                "scene_id": "synthetic_signal",
                "crop": "center",
                "source_dng": "/fixtures/x2d/signal.dng",
                "noise_sidecars": [str(sidecar)],
            },
            {
                "scene_id": "synthetic_noise",
                "crop": "center",
                "source_dng": "/fixtures/x2d/noise.dng",
                "noise_sidecars": [str(sidecar)],
            },
        ]
        targets_path = root / "targets.npz"
        np.savez_compressed(
            targets_path,
            candidate_raw_cfa4=np.zeros_like(target),
            candidate_raw_hf_cfa4=candidate_hf.astype(np.float16),
            raw_hf_residual_cfa4=target.astype(np.float16),
            source_raw_hf_cfa4=source_hf.astype(np.float16),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type("Args", (), {"targets": targets_path, "output_dir": root / "out"})()
        receipt = tool.run(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert receipt["summary"]["row_count"] == 2
        assert receipt["summary"]["rows_with_noise_sidecars"] == 2
        classes = {row["scene_id"]: row["classification"] for row in receipt["rows"]}
        assert classes["synthetic_signal"] == "signal_dominated"
        assert classes["synthetic_noise"] == "noise_floor"
        assert receipt["summary"]["classification_counts"]["signal_dominated"] == 1
        assert receipt["summary"]["classification_counts"]["noise_floor"] == 1
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        html = Path(receipt["artifacts"]["dashboard"]).read_text(encoding="utf-8")
        assert "Premium Still-SR Raw Target SNR Audit" in html

    print("test_audit_premium_still_sr_raw_target_snr: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
