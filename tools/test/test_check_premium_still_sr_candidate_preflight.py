#!/usr/bin/env python3
"""Regression test for premium still-SR candidate preflight."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_premium_still_sr_candidate_preflight.py"


def smoke_gate_acceptance() -> dict:
    return {
        "baseline": "same-color Bayer interpolation",
        "required_holdouts": ["X2D", "Z8"],
        "minimum_median_mae_reduction_pct": 0.001,
        "minimum_worst_row_mae_reduction_pct": 0.0,
        "long_run_blocked_if_smoke_fails": True,
        "receipt_fields_required": [
            "x2d_smoke_receipt",
            "z8_smoke_receipt",
            "baseline_comparison",
            "checkpoint_hash",
            "training_config_hash",
        ],
    }


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_tool(manifest: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), str(manifest), *extra],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_preflight_") as td:
        base = Path(td)
        passing = base / "passing.json"
        passing_audit = base / "passing_audit.json"
        passing_html = base / "passing.html"
        write_json(
            passing,
            {
                "schema": "gpr.premium_still_sr_candidate_preflight.v1",
                "candidate_id": "clean_source_raw_sr_restormer_teacher_v1",
                "candidate_kind": "teacher",
                "launchable_for_production_attempt": True,
                "requires_material_edits_before_launch": False,
                "material_change_summary": (
                    "Adds row-level measured PSF sidecars from real high/low pairs, "
                    "then requires the teacher beats interpolation before long run on "
                    "joint X2D/Z8 overlapped-tile validation."
                ),
                "runtime_inputs": ["candidate_raw", "camera_metadata", "validated_noise_sidecar_optional"],
                "forbidden_runtime_inputs_absent": True,
                "uses_ref_or_source_content_at_render_time": False,
                "promotion_claimed": False,
                "production_ready": False,
                "model_arch": "Restormer-style raw-SR transformer teacher",
                "architecture_deltas": [
                    "non-local full-image raw restoration teacher",
                    "overlapped-tile high-resolution inference",
                    "self-supervised clean-source RAW SR objective",
                ],
                "degradation_deltas": [
                    "realistic camera blur/PSF synthesis from row-level PSF sidecars",
                    "ISO-conditioned calibrated sensor noise",
                    "bit-depth and compression/decode simulation",
                ],
                "validation_plan": [
                    "held-out X2D full-image gate",
                    "held-out Z8 overlapped-tile gate",
                    "50 MP full-frame gate row accounting",
                    "100 MP full-frame gate row accounting",
                    "both X2D and Z8 smoke holdouts beat interpolation before long run",
                    "worst-row 100 percent crop review",
                ],
                "baseline_comparisons": [
                    "same-color Bayer interpolation baseline",
                    "current still-SR scoreboard and 12k window-attention rejection",
                ],
                "planned_receipts": [
                    "checkpoint hash",
                    "training config hash",
                    "dashboard",
                    "timing memory receipt",
                    "editor latitude review",
                    "editable DNG/GPR raw receipt",
                    "noise policy receipt",
                ],
                "smoke_gate_commands": [
                    (
                        "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                        "--pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs/pairs.npz "
                        "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/x2d_rowpsf_smoke "
                        "--holdout-image x2d --model-arch row_psf_teacher"
                    ),
                    (
                        "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                        "--pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs/pairs.npz "
                        "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/z8_rowpsf_smoke "
                        "--holdout-image z8 --model-arch row_psf_teacher"
                    ),
                ],
                "smoke_gate_acceptance": smoke_gate_acceptance(),
                "noise_policy": {
                    "exact_sidecars_only": True,
                    "forbids_source_residual_noise": True,
                    "missing_sidecars": "metadata_only",
                },
            },
        )
        proc = run_tool(
            passing,
            "--json-out",
            str(passing_audit),
            "--html-out",
            str(passing_html),
            "--require-launchable",
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(passing_audit.read_text(encoding="utf-8"))
        assert audit["schema"] == "gpr.premium_still_sr_candidate_preflight_audit.v1"
        assert audit["launchable_for_production_attempt"] is True
        assert audit["production_ready"] is False
        assert "row-level psf" in audit["material_source_matches"]
        assert "restormer" in audit["architecture_delta_matches"]
        assert "psf" in audit["degradation_delta_matches"]
        assert audit["smoke_gate_acceptance"]["minimum_median_mae_reduction_pct"] == 0.001
        assert audit["smoke_gate_command_count"] == 2
        assert passing_html.exists()

        failing = base / "failing.json"
        failing_audit = base / "failing_audit.json"
        write_json(
            failing,
            {
                "schema": "gpr.premium_still_sr_candidate_preflight.v1",
                "candidate_id": "repeat_residual_pixelshuffle_local_cnn",
                "candidate_kind": "student",
                "runtime_inputs": ["candidate_raw", "camera_metadata", "source_hf"],
                "forbidden_runtime_inputs_absent": False,
                "model_arch": "residual_pixelshuffle local-CNN-only",
                "architecture_deltas": ["same local CNN as before"],
                "degradation_deltas": ["same-color box downsample"],
                "validation_plan": ["one X2D crop"],
                "baseline_comparisons": ["train split only"],
                "planned_receipts": ["dashboard"],
                "noise_policy": {
                    "exact_sidecars_only": False,
                    "forbids_source_residual_noise": False,
                    "missing_sidecars": "synthetic_noise",
                },
                "promotion_claimed": True,
            },
        )
        proc = run_tool(failing, "--json-out", str(failing_audit), "--require-launchable")
        assert proc.returncode != 0
        failed = json.loads(failing_audit.read_text(encoding="utf-8"))
        assert failed["launchable_for_production_attempt"] is False
        assert failed["verdict"] == "blocked_before_long_run"
        assert any("rejected primary path" in item for item in failed["failures"])
        assert any("forbidden render-time content" in item for item in failed["failures"])
        assert any("new source/evidence" in item for item in failed["failures"])
        assert any("smoke_gate_acceptance" in item for item in failed["failures"])
        assert any("held-out Z8" in item for item in failed["failures"])
        assert any("50 MP" in item for item in failed["failures"])
        assert any("100 MP" in item for item in failed["failures"])

        proc = run_tool(failing)
        assert proc.returncode == 0

        generic_restormer = base / "generic_restormer.json"
        generic_restormer_audit = base / "generic_restormer_audit.json"
        write_json(
            generic_restormer,
            {
                "schema": "gpr.premium_still_sr_candidate_preflight.v1",
                "candidate_id": "generic_restormer_blur_noise_decode_repeat",
                "candidate_kind": "teacher",
                "launchable_for_production_attempt": True,
                "requires_material_edits_before_launch": False,
                "material_change_summary": (
                    "Adds camera-conditioned PSF/noise/decode degradation and "
                    "joint X2D/Z8 overlapped-tile validation beyond rejected receipts."
                ),
                "runtime_inputs": ["candidate_raw", "camera_metadata", "validated_noise_sidecar_optional"],
                "forbidden_runtime_inputs_absent": True,
                "uses_ref_or_source_content_at_render_time": False,
                "promotion_claimed": False,
                "production_ready": False,
                "model_arch": "Restormer-style raw-SR transformer teacher",
                "architecture_deltas": [
                    "non-local full-image raw restoration teacher",
                    "self-supervised clean-source RAW SR objective",
                ],
                "degradation_deltas": [
                    "realistic camera blur/PSF synthesis",
                    "ISO-conditioned calibrated sensor noise",
                    "bit-depth and compression/decode simulation",
                ],
                "validation_plan": [
                    "held-out X2D full-image gate",
                    "held-out Z8 overlapped-tile gate",
                    "50 MP full-frame gate row accounting",
                    "100 MP full-frame gate row accounting",
                ],
                "baseline_comparisons": [
                    "same-color Bayer interpolation baseline",
                    "current still-SR scoreboard and 12k window-attention rejection",
                ],
                "planned_receipts": [
                    "checkpoint hash",
                    "training config hash",
                    "dashboard",
                    "timing memory receipt",
                    "editor latitude review",
                    "editable DNG/GPR raw receipt",
                    "noise policy receipt",
                ],
                "noise_policy": {
                    "exact_sidecars_only": True,
                    "forbids_source_residual_noise": True,
                    "missing_sidecars": "metadata_only",
                },
            },
        )
        proc = run_tool(generic_restormer, "--json-out", str(generic_restormer_audit), "--require-launchable")
        assert proc.returncode != 0
        generic_failed = json.loads(generic_restormer_audit.read_text(encoding="utf-8"))
        assert generic_failed["launchable_for_production_attempt"] is False
        assert any("new source/evidence" in item for item in generic_failed["failures"])
        assert any("Restormer-style proposals" in item for item in generic_failed["failures"])

        single_smoke = json.loads(passing.read_text(encoding="utf-8"))
        single_smoke["smoke_gate_commands"] = [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                "--pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs/pairs.npz "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/x2d_z8_combined_smoke "
                "--holdout-image x2d,z8 --model-arch row_psf_teacher"
            )
        ]
        single_smoke_path = base / "single_smoke.json"
        single_smoke_audit = base / "single_smoke_audit.json"
        write_json(single_smoke_path, single_smoke)
        proc = run_tool(single_smoke_path, "--json-out", str(single_smoke_audit), "--require-launchable")
        assert proc.returncode != 0
        single_smoke_failed = json.loads(single_smoke_audit.read_text(encoding="utf-8"))
        assert any("separate X2D and Z8" in item for item in single_smoke_failed["failures"])

        local_tmp_smoke = json.loads(passing.read_text(encoding="utf-8"))
        local_tmp_smoke["smoke_gate_commands"][0] = local_tmp_smoke["smoke_gate_commands"][0].replace(
            "/Volumes/OWC_8TB/gpr_work/artifacts/x2d_rowpsf_smoke",
            "/tmp/x2d_rowpsf_smoke",
        )
        local_tmp_smoke["smoke_gate_commands"][1] = local_tmp_smoke["smoke_gate_commands"][1].replace(
            "/Volumes/OWC_8TB/gpr_work/artifacts/z8_rowpsf_smoke",
            "/tmp/z8_rowpsf_smoke",
        )
        local_tmp_path = base / "local_tmp_smoke.json"
        local_tmp_audit = base / "local_tmp_audit.json"
        write_json(local_tmp_path, local_tmp_smoke)
        proc = run_tool(local_tmp_path, "--json-out", str(local_tmp_audit), "--require-launchable")
        assert proc.returncode != 0
        local_tmp_failed = json.loads(local_tmp_audit.read_text(encoding="utf-8"))
        assert any("/Volumes/OWC_8TB/gpr_work" in item for item in local_tmp_failed["failures"])

        weak_acceptance = json.loads(passing.read_text(encoding="utf-8"))
        weak_acceptance["smoke_gate_acceptance"]["minimum_median_mae_reduction_pct"] = 0.0
        weak_acceptance["smoke_gate_acceptance"]["minimum_worst_row_mae_reduction_pct"] = -0.1
        weak_acceptance_path = base / "weak_acceptance.json"
        weak_acceptance_audit = base / "weak_acceptance_audit.json"
        write_json(weak_acceptance_path, weak_acceptance)
        proc = run_tool(weak_acceptance_path, "--json-out", str(weak_acceptance_audit), "--require-launchable")
        assert proc.returncode != 0
        weak_failed = json.loads(weak_acceptance_audit.read_text(encoding="utf-8"))
        assert any("minimum_median_mae_reduction_pct" in item for item in weak_failed["failures"])
        assert any("minimum_worst_row_mae_reduction_pct" in item for item in weak_failed["failures"])

        rejected_smoke = json.loads(passing.read_text(encoding="utf-8"))
        rejected_smoke["candidate_id"] = "teacher_first_fullframe_raw_sr_smoke_v1"
        rejected_smoke["smoke_gate_commands"] = [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                "--pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_clean_source_pairs_routed_t64_20260702/premium_still_sr_clean_source_pairs_routed_t64.npz "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_teacher_first_smoke_x2d_20260702 "
                "--holdout-image x2d --model-arch row_psf_teacher"
            ),
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                "--pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_clean_source_pairs_routed_t64_20260702/premium_still_sr_clean_source_pairs_routed_t64.npz "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_teacher_first_smoke_z8_20260702 "
                "--holdout-image z8 --model-arch row_psf_teacher"
            ),
        ]
        rejected_smoke_path = base / "rejected_smoke.json"
        rejected_smoke_audit = base / "rejected_smoke_audit.json"
        write_json(rejected_smoke_path, rejected_smoke)
        proc = run_tool(rejected_smoke_path, "--json-out", str(rejected_smoke_audit), "--require-launchable")
        assert proc.returncode != 0
        rejected_failed = json.loads(rejected_smoke_audit.read_text(encoding="utf-8"))
        assert any("already rejected" in item for item in rejected_failed["failures"])
        assert any("reuse rejected teacher-first smoke output directories" in item for item in rejected_failed["failures"])

        renamed_rejected_smoke = json.loads(rejected_smoke_path.read_text(encoding="utf-8"))
        renamed_rejected_smoke["candidate_id"] = "renamed_teacher_first_replay"
        renamed_rejected_path = base / "renamed_rejected_smoke.json"
        renamed_rejected_audit = base / "renamed_rejected_smoke_audit.json"
        write_json(renamed_rejected_path, renamed_rejected_smoke)
        proc = run_tool(renamed_rejected_path, "--json-out", str(renamed_rejected_audit), "--require-launchable")
        assert proc.returncode != 0
        renamed_failed = json.loads(renamed_rejected_audit.read_text(encoding="utf-8"))
        assert not any("already rejected" in item for item in renamed_failed["failures"])
        assert any("reuse rejected teacher-first smoke output directories" in item for item in renamed_failed["failures"])

    print("test_check_premium_still_sr_candidate_preflight: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
