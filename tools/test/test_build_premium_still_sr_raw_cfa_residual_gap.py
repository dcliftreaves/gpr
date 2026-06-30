#!/usr/bin/env python3
"""Regression test for the premium still-SR raw-CFA residual gap builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_raw_cfa_residual_gap.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipt(scene: str, mae: float, rmse: float, *, feature_mode: str = "raw_multiscale_coord_ev_noise") -> dict:
    return {
        "schema": "gpr.premium_still_sr_raw_cfa_residual_model.v1",
        "config": {
            "holdout_scene": scene,
            "feature_mode": feature_mode,
            "target_policy": "raw",
            "width": 32,
            "depth": 4,
            "patch_size": 128,
            "steps": 2000,
            "sample_mode": "full_crop" if "X2D" in scene else "random_patch",
        },
        "policy": {
            "uses_source_raw_at_runtime": False,
            "uses_source_raw_at_training": True,
        },
        "eval": {
            "holdout": {
                "raw_residual_mae_reduction_pct": {"median": mae},
                "raw_residual_rmse_reduction_pct": {"median": rmse},
                "exact_raw_mae_reduction_pct": {"median": mae},
            },
            "train": {
                "raw_residual_mae_reduction_pct": {"median": 1.0},
            },
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_gap_", dir=temp_root()) as td:
        root = Path(td)
        target = root / "target.json"
        z8 = root / "z8.json"
        x2d = root / "x2d.json"
        out = root / "out"
        write_json(
            target,
            {
                "schema": "gpr.premium_still_sr_raw_cfa_residual_targets.v1",
                "policy": {"runtime_safe": False, "uses_source_raw": True},
                "summary": {
                    "row_count": 351,
                    "scene_count": 13,
                    "scenes": ["Z8Z_1353", "2024_April_X2D_1742"],
                    "render_y_to_raw_same_color_hf_corr_abs": {"median": 0.691, "mean": 0.677},
                    "raw_to_render_hf_abs_ratio": {"median": 0.346},
                },
            },
        )
        write_json(z8, receipt("Z8Z_1353", 0.5, 1.7))
        write_json(x2d, receipt("2024_April_X2D_1742", -0.2, -0.3))

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--target-receipt",
                str(target),
                "--model-receipt",
                str(z8),
                "--model-receipt",
                str(x2d),
                "--output-dir",
                str(out),
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

        data = json.loads((out / "raw_cfa_residual_gap.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_raw_cfa_residual_gap.v1"
        assert data["production_ready"] is False
        assert data["target"]["row_count"] == 351
        assert data["target"]["render_to_raw_corr_abs_median"] == 0.691
        assert {row["camera"] for row in data["camera_summary"]} == {"Z8", "X2D"}
        assert any("X2D holdout" in blocker for blocker in data["blockers"])
        assert data["next_experiments"][0]["name"] == "full-image or structured raw-CFA residual learner"
        assert "sample_balance" in data["models"][0]
        assert "sample_mode" in data["models"][0]
        assert "context_padding" in data["models"][0]
        assert "model_arch" in data["models"][0]

        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Raw-CFA Residual Gap" in html
        assert "Production ready" in html
        assert "full-image or structured raw-CFA residual learner" in html
        assert "Sampler" in html
        assert "Sample mode" in html
        assert "Context px" in html
        assert "Architecture" in html
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_build_premium_still_sr_raw_cfa_residual_gap: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
