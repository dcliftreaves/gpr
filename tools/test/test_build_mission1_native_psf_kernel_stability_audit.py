#!/usr/bin/env python3
"""Regression test for Mission 1 native PSF kernel stability audit."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_native_psf_kernel_stability_audit.py"


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_psf_kernel_stability_") as td:
        root = Path(td)
        measurement = root / "measurement.json"
        out = root / "out"
        write_json(
            measurement,
            {
                "schema": "gpr.mission1_native_psf_measurement.v1",
                "native_psf_ready_for_model_conditioning": False,
                "summary": {
                    "selected_pair_count": 3,
                    "accepted_pair_count": 2,
                    "rejected_pair_count": 1,
                    "kernel_stable": False,
                },
                "combined_kernel": {
                    "available": True,
                    "kernel_stable": False,
                    "normalized_weights_mean": [1.0, -0.1, 0.2, -0.1],
                    "normalized_weights_std": [0.5, 0.2, 0.1, 0.1],
                    "rmse_14bit_median": 123.4,
                },
                "pair_measurements": [
                    {
                        "low_stem": "LOW_A",
                        "high_stem": "HIGH_A",
                        "alignment": {
                            "accepted_for_kernel": True,
                            "correlation": 0.96,
                            "shift_low_raw_px_x": 0,
                            "shift_low_raw_px_y": 0,
                        },
                        "psf_fit": {
                            "normalized_weights": [0.25, 0.25, 0.25, 0.25],
                            "rmse_14bit": 100.0,
                            "weight_sum_gain": 1.0,
                        },
                        "tile_summary": {"sharp_edge_tile_count": 100, "texture_field_tile_count": 100},
                        "rejection_reasons": [],
                    },
                    {
                        "low_stem": "LOW_B",
                        "high_stem": "HIGH_B",
                        "alignment": {
                            "accepted_for_kernel": True,
                            "correlation": 0.82,
                            "shift_low_raw_px_x": 8,
                            "shift_low_raw_px_y": 4,
                        },
                        "psf_fit": {
                            "normalized_weights": [1.5, -0.4, -0.2, 0.1],
                            "rmse_14bit": 140.0,
                            "weight_sum_gain": 0.8,
                        },
                        "tile_summary": {"sharp_edge_tile_count": 120, "texture_field_tile_count": 110},
                        "rejection_reasons": [],
                    },
                    {
                        "low_stem": "LOW_C",
                        "high_stem": "HIGH_C",
                        "alignment": {
                            "accepted_for_kernel": False,
                            "correlation": 0.61,
                            "shift_low_raw_px_x": 32,
                            "shift_low_raw_px_y": 16,
                        },
                        "psf_fit": {
                            "normalized_weights": [0.1, 0.2, 0.3, 0.4],
                            "rmse_14bit": 180.0,
                            "weight_sum_gain": 1.1,
                        },
                        "tile_summary": {"sharp_edge_tile_count": 80, "texture_field_tile_count": 75},
                        "rejection_reasons": ["alignment/scene correlation below threshold"],
                    },
                ],
            },
        )
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--measurement", str(measurement), "--output-dir", str(out)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        data = json.loads((out / "kernel_stability_audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.mission1_native_psf_kernel_stability_audit.v1"
        assert data["production_ready"] is False
        assert data["kernel_stable_by_audit"] is False
        assert data["dominant_blocker"] == "kernel disagreement"
        assert data["summary"]["accepted_pair_count"] == 2
        assert data["summary"]["accepted_negative_weight_pair_count"] == 1
        assert data["summary"]["low_alignment_corr_pair_count"] == 1
        assert any("normalized-weight std" in item for item in data["blockers"])
        assert any("invalid negative weights" in item for item in data["blockers"])
        assert "Mission 1 Native PSF Kernel Stability Audit" in (out / "index.html").read_text(encoding="utf-8")
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_build_mission1_native_psf_kernel_stability_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
