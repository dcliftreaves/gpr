#!/usr/bin/env python3
"""Regression test for the Gate 12 Premium still-SR teacher-source audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_measured_degradation_teacher_source_audit.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def source(camera: str, present: bool, mae: float, rmse: float) -> dict:
    return {
        "schema": "gpr.premium_still_sr_source_evidence_audit.v1",
        "holdout_camera": camera,
        "acceptance": {
            "source_evidence_present": present,
            "min_median_mae_recovery_pct": 1.0,
        },
        "summary": {
            "linear_probe_mae_recovery_pct": {"median": mae},
            "linear_probe_rmse_recovery_pct": {"median": rmse},
        },
        "probe": {
            "runtime_inputs": ["candidate_raw"],
            "forbidden_inputs": ["REF", "source_raw", "jpeg"],
        },
    }


def teacher_receipt(*, pass_holdout: bool, mae_rows: list[float], rmse_rows: list[float]) -> dict:
    return {
        "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
        "pairs": "/pairs/premium_still_sr_clean_source_pairs_routed_t64.npz",
        "pairs_sha256": "a" * 64,
        "checkpoint_sha256": "b" * 64,
        "eval": {
            "holdout": {
                "baseline_mae": {"count": len(mae_rows)},
                "rows": [
                    {
                        "mae_improvement_pct": mae,
                        "rmse_improvement_pct": rmse,
                    }
                    for mae, rmse in zip(mae_rows, rmse_rows)
                ],
            }
        },
        "promotion": {
            "baseline": "nearest_same_color_2x",
            "baseline_beaten_on_holdout": pass_holdout,
            "coverage_sufficient_for_promotion": True,
            "promotion_ready": pass_holdout,
            "decision": "candidate may enter broader premium still-SR gate" if pass_holdout else "diagnostic only",
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate12_teacher_source_", dir=temp_root()) as td:
        root = Path(td)
        gate11_acceptance = root / "gate11_acceptance.json"
        gate11_audit = root / "gate11_audit.json"
        target_snr = root / "target_snr.json"
        pair_meta = root / "pairs.npz.json"
        x2d_source = root / "x2d_source.json"
        z8_source = root / "z8_source.json"
        x2d_teacher = root / "x2d_teacher.json"
        z8_teacher = root / "z8_teacher.json"
        out = root / "out"

        write_json(
            gate11_acceptance,
            {
                "schema": "gpr.premium_still_sr_smoke_gate_acceptance.v1",
                "candidate_id": "gate11_route_isolated_teacher_router_rawcfa_v1",
                "smoke_gate_passed": False,
                "long_run_allowed": False,
            },
        )
        write_json(
            gate11_audit,
            {
                "schema": "gpr.premium_still_sr_degradation_source_audit.v1",
                "selected_family": "route_isolated_teacher_then_router",
            },
        )
        write_json(
            target_snr,
            {
                "schema": "gpr.premium_still_sr_raw_target_snr_audit.v1",
                "by_camera": [
                    {
                        "camera": "x2d",
                        "row_count": 81,
                        "classifications": {"signal_dominated": 59, "mixed_signal_noise": 11, "noise_floor": 11},
                        "target_rmse_to_noise_sigma": {"median": 5.34},
                        "target_p95_to_noise_p95": {"median": 5.25},
                    },
                    {
                        "camera": "z8",
                        "row_count": 36,
                        "classifications": {"mixed_signal_noise": 8, "noise_floor": 28},
                        "target_rmse_to_noise_sigma": {"median": 0.48},
                        "target_p95_to_noise_p95": {"median": 0.39},
                    },
                ],
            },
        )
        write_json(
            pair_meta,
            {
                "dataset_label": "premium_still_sr_clean_source_pairs_routed_t64",
                "created_from": "real premium still-SR fixture manifest",
                "downsample": "same-color 2x2 average within each Bayer plane",
                "low_tile": 96,
                "high_tile": 192,
                "fixture_manifest": "/fixtures/fixture_manifest.json",
                "fixture_manifest_sha256": "c" * 64,
                "images": [
                    {"camera_key": "x2d", "class": "100mp", "source_width": 11656, "source_height": 8742},
                    {"camera_key": "z8", "class": "50mp", "source_width": 8256, "source_height": 5504},
                    {"camera_key": "mission1", "class": "50mp", "source_width": 8192, "source_height": 6144},
                ]
                * 25,
            },
        )
        write_json(x2d_source, source("x2d", True, 4.82, 11.52))
        write_json(z8_source, source("z8", False, 0.65, 21.90))
        write_json(x2d_teacher, teacher_receipt(pass_holdout=True, mae_rows=[0.0093, 0.0091, 0.0015], rmse_rows=[0.0001, 0.0067, 0.0002]))
        write_json(z8_teacher, teacher_receipt(pass_holdout=False, mae_rows=[-0.128, 0.948, -0.058], rmse_rows=[-0.156, 0.679, -0.038]))

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--gate11-acceptance",
                str(gate11_acceptance),
                "--gate11-audit",
                str(gate11_audit),
                "--target-snr",
                str(target_snr),
                "--clean-source-pair-meta",
                str(pair_meta),
                "--x2d-source-evidence",
                str(x2d_source),
                "--z8-source-evidence",
                str(z8_source),
                "--x2d-teacher-smoke",
                str(x2d_teacher),
                "--z8-teacher-smoke",
                str(z8_teacher),
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

        data = json.loads((out / "measured_degradation_teacher_source_audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_measured_degradation_teacher_source_audit.v1"
        assert data["verdict"] == "gate12_synthetic_teacher_preflight_allowed_x2d_z8_noop"
        assert data["gate12_candidate_intake_allowed"] is True
        assert data["long_run_allowed"] is False
        assert data["selected_family"] == "synthetic_known_degradation_teacher_x2d_plus_z8_noop"
        assert data["target_source_decision"]["forbidden_training_target_family"] == "source_minus_candidate_raw_hf_residual"
        assert data["route_policy"]["x2d"]["positive_training_allowed"] is True
        assert data["route_policy"]["z8"]["positive_training_allowed"] is False
        assert data["route_policy"]["z8"]["policy"] == "exact_noop_or_new_source_required"
        assert any("Gate 11" in item for item in data["forbidden_gate12_sources"])
        assert data["next_receipts"][0]["receipt"] == "premium_still_sr_gate12_candidate_intake_<date>"
        assert proc.stdout.strip() == str(out / "index.html")

        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Gate 12 Teacher Source Audit" in html
        assert "synthetic_known_degradation_teacher_x2d_plus_z8_noop" in html

    print("test_build_premium_still_sr_measured_degradation_teacher_source_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
