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
                    "overlapped-tile high-resolution inference",
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
        assert "restormer" in audit["architecture_delta_matches"]
        assert "psf" in audit["degradation_delta_matches"]
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
        assert any("held-out Z8" in item for item in failed["failures"])

        proc = run_tool(failing)
        assert proc.returncode == 0

    print("test_check_premium_still_sr_candidate_preflight: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
