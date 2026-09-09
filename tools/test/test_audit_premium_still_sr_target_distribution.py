#!/usr/bin/env python3
"""Regression test for premium still-SR target distribution audit."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_target_distribution.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("target_distribution_audit", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_target_distribution: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_target_dist_", dir=tmp_parent) as td:
        root = Path(td)
        sidecar = root / "noise.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.camera_noise_calibration.v1",
                    "camera": {"black_level": 0.0, "white_level": 1000.0},
                    "calibrations": [{"iso": 800, "per_plane": {"r": {"sigma_black": 1.0}}}],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        target = np.zeros((4, 8, 8, 4), dtype=np.float32)
        target[0] = 0.001
        target[1] = 0.002
        target[2] = 0.009
        target[3] = 0.010
        candidate = np.linspace(0.0, 1.0, num=4 * 8 * 8 * 4, dtype=np.float32).reshape(4, 8, 8, 4)
        rows = [
            {"scene_id": "train_a", "crop": "a", "source_dng": "/fixtures/x2d/a.dng", "noise_sidecars": [str(sidecar)]},
            {"scene_id": "train_b", "crop": "b", "source_dng": "/fixtures/x2d/b.dng", "noise_sidecars": [str(sidecar)]},
            {"scene_id": "holdout", "crop": "c", "source_dng": "/fixtures/x2d/c.dng", "noise_sidecars": [str(sidecar)]},
            {"scene_id": "holdout", "crop": "d", "source_dng": "/fixtures/x2d/d.dng", "noise_sidecars": [str(sidecar)]},
        ]
        targets = root / "targets.npz"
        np.savez_compressed(
            targets,
            candidate_raw_cfa4=candidate.astype(np.float16),
            raw_hf_residual_cfa4=target.astype(np.float16),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type("Args", (), {"targets": targets, "output_dir": root / "out", "holdout_scene": "holdout", "train_camera": "x2d"})()
        receipt = tool.run(args)
        assert receipt["schema"] == tool.SCHEMA
        assert receipt["policy"]["uses_source_raw_at_runtime"] is False
        assert receipt["summary"]["row_count"] == 4
        assert receipt["summary"]["scene_count"] == 3
        assert receipt["summary"]["camera_counts"] == {"x2d": 4}
        split = receipt["split_comparison"]
        assert split["enabled"] is True
        assert split["holdout_scene"] == "holdout"
        assert split["train_row_count"] == 2
        assert split["holdout_row_count"] == 2
        assert split["holdout_median_to_train_median"] > 5.0
        assert split["distribution_mismatch"] is True
        assert Path(receipt["artifacts"]["receipt"]).stat().st_size > 0
        html = Path(receipt["artifacts"]["dashboard"]).read_text(encoding="utf-8")
        assert "Premium Still-SR Target Distribution Audit" in html
        assert "Holdout Split" in html

    print("test_audit_premium_still_sr_target_distribution: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
