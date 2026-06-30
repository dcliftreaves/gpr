#!/usr/bin/env python3
"""Regression test for the premium still-SR readiness builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_readiness.py"
CHECKER = ROOT / "tools/check_product_pillar_receipts.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_noise_sidecar(path: Path, make: str, model: str, iso: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "gpr.camera_noise_calibration.v1",
        "camera": {
            "make": make,
            "model": model,
            "width": 1024,
            "height": 1024,
            "bit_depth": 14,
            "cfa_phase": "RGGB",
            "black_level": 0,
            "white_level": 16383,
        },
        "calibrations": [
            {
                "iso": iso,
                "calibration_method": "test_darkframe_stack",
                "source_kind": "darkframes",
                "sample_count": 4,
                "source": {"path": "test", "sha256": "0" * 64},
                "per_plane": {
                    plane: {
                        "noise_profile_scale": 1.0,
                        "noise_profile_offset": 0.0,
                        "mean_black": 64.0,
                        "sigma_black": 2.0,
                    }
                    for plane in ("r", "g1", "b", "g2")
                },
                "noise_signal_audit": {
                    "separates_noise_from_signal": True,
                    "method": "test",
                    "evidence": "synthetic regression sidecar",
                },
                "usable_for_training_targets": True,
            }
        ],
        "production_ready": True,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_readiness_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        out = Path(tmp) / "out"
        write_noise_sidecar(
            root / "artifacts/camera_noise_sidecars_20260629/x2d/Hasselblad_X2D_100C_ISO800_noise_calibration.json",
            "Hasselblad",
            "X2D 100C",
            800,
        )
        write_noise_sidecar(
            root / "artifacts/camera_noise_sidecars_20260629/z8/NIKON_CORPORATION_NIKON_Z_8_ISO500_noise_calibration.json",
            "NIKON CORPORATION",
            "NIKON Z 8",
            500,
        )
        for rel in (
            "artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_editable_packaging_frame0/frame_000000_sr8k_generic.dng",
            "artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_editable_packaging_frame0/frame_000000_sr8k_sdk_wrapped.gpr",
            "artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_editable_packaging_frame0/frame_000000_sr8k_review_2k_prores.mov",
            "artifacts/premium_still_sr_fixture_manifest_20260629/fixture_manifest.json",
            "artifacts/premium_still_sr_pairs_20260629/premium_still_sr_pairs.npz",
            "artifacts/premium_still_sr_pairs_20260629/premium_still_sr_pairs.npz.json",
            "artifacts/premium_still_sr_candidate_smoke_20260629/premium_still_sr_smoke_w24_d4_120.pt",
            "artifacts/premium_still_sr_candidate_smoke_20260629/premium_still_sr_smoke_w24_d4_120.pt.json",
            "artifacts/premium_still_sr_pairs_large_20260629/premium_still_sr_pairs_64t.npz",
            "artifacts/premium_still_sr_pairs_large_20260629/premium_still_sr_pairs_64t.npz.json",
            "artifacts/premium_still_sr_candidate_large_20260629/premium_still_sr_w32_d5_1000_x2dholdout.pt",
            "artifacts/premium_still_sr_candidate_large_20260629/premium_still_sr_w32_d5_1000_x2dholdout.pt.json",
            "artifacts/premium_still_sr_candidate_dashboard_20260629/index.html",
            "artifacts/premium_still_sr_candidate_dashboard_20260629/candidate_dashboard.json",
            "artifacts/premium_still_sr_visual_review_20260629/index.html",
            "artifacts/premium_still_sr_visual_review_20260629/visual_review.json",
            "artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/index.html",
            "artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/premium_still_sr_x2d_hf_residual_noise_multiscale_w96.pt",
        ):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(rel.encode("utf-8"))
        latest_receipt = root / "artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/train_receipt.json"
        latest_receipt.parent.mkdir(parents=True, exist_ok=True)
        latest_receipt.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_hf_residual_model.v1",
                    "checkpoint_sha256": "1" * 64,
                    "train_seconds": 12.5,
                    "steps": 40,
                    "config": {
                        "feature_mode": "rgb_multiscale_coord_luma_ev_noise_bright",
                        "holdout_scene": "x2d_test",
                    },
                    "policy": {
                        "uses_source_hf_at_training": True,
                        "uses_source_hf_at_runtime": False,
                        "runtime_inputs": "candidate_render_rgb + camera/ISO noise sidecar scalars",
                        "production_status": "smoke_training_probe_not_registered_production_algorithm",
                    },
                    "eval": {
                        "train": {
                            "row_count": 3,
                            "residual_mae_reduction_pct": {"median": 4.0},
                            "residual_rmse_reduction_pct": {"median": 4.5},
                        },
                        "holdout": {
                            "row_count": 2,
                            "residual_mae_reduction_pct": {"median": 2.5},
                            "residual_rmse_reduction_pct": {"median": 2.8},
                        },
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        subprocess.run([sys.executable, str(TOOL), "--external-root", str(root), "--output-dir", str(out)], cwd=ROOT, check=True)
        receipt = out / "premium_still_sr_gate_receipt.json"
        subprocess.run([sys.executable, str(CHECKER), str(receipt)], cwd=ROOT, check=True)

        state = json.loads((out / "readiness.json").read_text(encoding="utf-8"))
        gate = json.loads(receipt.read_text(encoding="utf-8"))
        assert state["schema"] == "gpr.premium_still_sr_readiness.v1"
        assert state["production_ready"] is False
        assert state["evidence_summary"]["has_50mp_still_roundtrip"] is True
        assert state["evidence_summary"]["has_100mp_still_roundtrip"] is True
        assert state["evidence_summary"]["has_validated_x2d_z8_noise_sidecars"] is True
        assert state["evidence_summary"]["has_dedicated_premium_still_sr_pairs"] is True
        assert state["evidence_summary"]["has_dedicated_premium_still_sr_smoke_checkpoint"] is True
        assert state["evidence_summary"]["has_larger_premium_still_sr_pairs"] is True
        assert state["evidence_summary"]["has_larger_premium_still_sr_candidate_checkpoint"] is True
        assert state["evidence_summary"]["has_premium_still_sr_metric_dashboard"] is True
        assert state["evidence_summary"]["has_rendered_visual_premium_still_sr_dashboard"] is True
        assert state["evidence_summary"]["has_latest_no_ref_hf_residual_probe"] is True
        assert state["evidence_summary"]["latest_no_ref_hf_runtime_uses_ref_content"] is False
        assert state["evidence_summary"]["latest_no_ref_hf_holdout_mae_reduction_pct_median"] == 2.5
        assert state["latest_hf_residual_probe"]["uses_source_hf_at_training"] is True
        assert state["latest_hf_residual_probe"]["uses_source_hf_at_runtime"] is False
        assert state["latest_hf_residual_probe"]["promotion_ready"] is False
        assert state["evidence_summary"]["has_production_grade_premium_still_sr_checkpoint"] is False
        assert gate["schema"] == "gpr.premium_still_sr_gate.v1"
        assert gate["production_ready"] is False
        assert "blocked_on_dedicated_premium_still_sr_candidate" in (out / "index.html").read_text(encoding="utf-8")

    print("test_build_premium_still_sr_readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
