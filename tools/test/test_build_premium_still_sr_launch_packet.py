#!/usr/bin/env python3
"""Regression test for the premium still-SR launch packet builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_launch_packet.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or "/Volumes/OWC_8TB/gpr_work/tmp")
    if not root.exists():
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_launch_packet_", dir=temp_root()) as td:
        base = Path(td)
        template_only = base / "template_only_packet"
        proc = run([sys.executable, str(TOOL), "--output-dir", str(template_only), "--require-launchable"])
        assert proc.returncode != 0
        blocked_template = json.loads((template_only / "launch_packet.json").read_text(encoding="utf-8"))
        assert blocked_template["preflight"]["launchable_for_production_attempt"] is False
        assert any("explicit --manifest" in item for item in blocked_template["preflight"]["failures"])

        manifest = base / "explicit_candidate.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_candidate_preflight.v1",
                    "candidate_id": "contextual_raw_restoration_teacher_new_degradation_v1",
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
                    "noise_policy": {
                        "exact_sidecars_only": True,
                        "forbids_source_residual_noise": True,
                        "missing_sidecars": "metadata_only",
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        good = base / "good_packet"
        proc = run([sys.executable, str(TOOL), "--output-dir", str(good), "--manifest", str(manifest), "--require-launchable"])
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        for name in (
            "candidate_preflight.json",
            "preflight_audit.json",
            "launch_packet.json",
            "launch_packet.md",
            "index.html",
        ):
            assert (good / name).exists(), name

        packet = json.loads((good / "launch_packet.json").read_text(encoding="utf-8"))
        assert packet["schema"] == "gpr.premium_still_sr_launch_packet.v1"
        assert packet["production_ready"] is False
        assert packet["promotion_claimed"] is False
        assert packet["manifest_source"] == str(manifest)
        assert packet["explicit_manifest_required_for_launchable"] is True
        assert packet["preflight"]["launchable_for_production_attempt"] is True
        assert packet["preflight"]["verdict"] == "launchable_preflight_passed"
        commands = "\n".join(item["command"] for item in packet["next_commands"])
        for token in (
            "build_premium_still_sr_launch_packet.py",
            "--manifest",
            "check_premium_still_sr_candidate_preflight.py",
            "build_premium_still_sr_pairs.py",
            "audit_premium_still_sr_pairs.py",
            "train_premium_still_sr_clean_source_pairs.py",
            "row_psf_teacher",
            "/Volumes/OWC_8TB/gpr_work/artifacts/x2d_rowpsf_smoke",
            "/Volumes/OWC_8TB/gpr_work/artifacts/z8_rowpsf_smoke",
            "build_premium_still_sr_experiment_scoreboard.py",
            "check_premium_still_sr_promotion_gate.py",
        ):
            assert token in commands, token
        assert "restormer_pixelshuffle" not in commands
        repeats = " ".join(packet["blocked_repeats"])
        assert "residual_pixelshuffle" in repeats
        assert "local-CNN" in repeats
        assert "source-HF" in repeats
        assert any("50 MP" in item and "100 MP" in item for item in packet["promotion_stop_conditions"])

        bad = base / "bad_packet"
        proc = run(
            [
                sys.executable,
                str(TOOL),
                "--output-dir",
                str(bad),
                "--template",
                "rejected_repeat_fixture",
                "--require-launchable",
            ]
        )
        assert proc.returncode != 0
        assert (bad / "launch_packet.json").exists()
        blocked = json.loads((bad / "launch_packet.json").read_text(encoding="utf-8"))
        assert blocked["preflight"]["launchable_for_production_attempt"] is False
        assert blocked["preflight"]["verdict"] == "blocked_before_long_run"
        assert any("rejected primary path" in item for item in blocked["preflight"]["failures"])

    print("test_build_premium_still_sr_launch_packet: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
