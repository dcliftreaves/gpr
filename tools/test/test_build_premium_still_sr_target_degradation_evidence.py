#!/usr/bin/env python3
"""Regression test for the Premium still-SR target/degradation evidence tool."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_target_degradation_evidence.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def train_receipt(scene: str, mae_median: float, mae_min: float, rmse_median: float, gate_median: float, noop_rows: int) -> dict:
    return {
        "schema": "gpr.premium_still_sr_raw_cfa_residual_model.v1",
        "config": {
            "holdout_scene": scene,
            "feature_mode": "raw_multiscale_coord_ev_noise_cfa",
            "model_arch": "unet",
        },
        "policy": {
            "uses_source_raw_at_runtime": False,
            "runtime_inputs": "candidate_raw_cfa4 + camera metadata",
        },
        "eval": {
            "holdout": {
                "row_count": 6,
                "raw_residual_mae_reduction_pct": {
                    "median": mae_median,
                    "min": mae_min,
                    "max": 0.01,
                },
                "raw_residual_rmse_reduction_pct": {
                    "median": rmse_median,
                    "min": mae_min,
                    "max": 0.01,
                },
                "candidate_hf_noop_gate": {
                    "median": gate_median,
                    "min": 0.0,
                    "max": 1.0,
                },
                "candidate_hf_noop_row_count": noop_rows,
                "candidate_hf_noop_threshold": 0.004,
                "candidate_hf_noop_softness": 0.004,
            }
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_target_degrade_", dir=temp_root()) as td:
        root = Path(td)
        acceptance = root / "acceptance.json"
        x2d = root / "x2d.json"
        z8 = root / "z8.json"
        framectx = root / "framectx.json"
        out = root / "out"

        write_json(
            acceptance,
            {
                "schema": "gpr.premium_still_sr_smoke_gate_acceptance.v1",
                "smoke_gate_passed": False,
                "production_ready": False,
                "long_run_allowed": False,
                "verdict": "blocked_before_long_run",
            },
        )
        write_json(x2d, train_receipt("2025_10_Oct_Austin_0702", -0.0062, -0.2315, -0.0083, 1.0, 0))
        write_json(z8, train_receipt("Z8Z_1353", 0.0, 0.0, 0.0, 0.0, 6))
        write_json(framectx, train_receipt("2025_10_Oct_Austin_0702", -0.0192, -0.1961, -0.0218, 1.0, 0))

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--acceptance",
                str(acceptance),
                "--x2d-receipt",
                str(x2d),
                "--z8-receipt",
                str(z8),
                "--framectx-x2d-receipt",
                str(framectx),
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

        data = json.loads((out / "target_degradation_evidence.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_target_degradation_evidence.v1"
        assert data["production_ready"] is False
        assert data["long_run_allowed"] is False
        assert data["blocker_classification"] == "target_degradation_or_route_conditioning_mismatch"
        assert len(data["rows"]) == 3
        assert data["rows"][0]["camera"] == "X2D"
        assert data["rows"][1]["camera"] == "Z8"
        assert data["rows"][1]["candidate_hf_noop_row_count"] == 6
        assert any("X2D" in blocker for blocker in data["blockers"])
        assert any("Z8" in blocker for blocker in data["blockers"])
        assert any(item["cause"] == "candidate_hf_noop_threshold_tuning" for item in data["ruled_out"])
        assert any(
            item["cause"] == "simple_frame_context_conditioning" and item["decision"] == "ruled_out"
            for item in data["ruled_out"]
        )
        assert data["next_steps"][0]["step"] == "Build a new target/degradation source receipt."

        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Target/Degradation Evidence" in html
        assert "Long run allowed" in html
        assert "target_degradation_or_route_conditioning_mismatch" in html
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_build_premium_still_sr_target_degradation_evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
