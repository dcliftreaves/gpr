#!/usr/bin/env python3
"""Regression test for premium still-SR candidate preflight template builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_premium_still_sr_candidate_preflight_template.py"
CHECKER = ROOT / "tools/check_premium_still_sr_candidate_preflight.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or "/Volumes/OWC_8TB/gpr_work/tmp")
    if not root.exists():
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_preflight_template_", dir=temp_root()) as td:
        base = Path(td)
        good = base / "clean_source_restormer_teacher.json"
        proc = run([sys.executable, str(BUILDER), "--output", str(good)])
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        assert proc.stdout.strip() == str(good)
        data = json.loads(good.read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_candidate_preflight.v1"
        assert data["launchable_for_production_attempt"] is False
        assert data["requires_material_edits_before_launch"] is True
        assert data["production_ready"] is False
        assert data["promotion_claimed"] is False
        assert data["runtime_inputs"] == [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ]
        assert "Restormer" in data["model_arch"]
        assert any("clean-source RAW SR" in item for item in data["architecture_deltas"])
        assert any("PSF" in item for item in data["degradation_deltas"])
        assert len(data["smoke_gate_commands"]) == 2
        assert any("x2d" in item.lower() for item in data["smoke_gate_commands"])
        assert any("z8" in item.lower() for item in data["smoke_gate_commands"])
        assert data["smoke_gate_acceptance"]["baseline"] == "same-color Bayer interpolation"
        assert data["smoke_gate_acceptance"]["required_holdouts"] == ["X2D", "Z8"]
        assert data["smoke_gate_acceptance"]["minimum_median_mae_reduction_pct"] > 0
        assert data["smoke_gate_acceptance"]["minimum_worst_row_mae_reduction_pct"] == 0.0
        assert data["smoke_gate_acceptance"]["long_run_blocked_if_smoke_fails"] is True
        assert data["noise_policy"]["exact_sidecars_only"] is True

        audit_json = base / "audit.json"
        audit_html = base / "index.html"
        proc = run(
            [
                sys.executable,
                str(CHECKER),
                str(good),
                "--json-out",
                str(audit_json),
                "--html-out",
                str(audit_html),
                "--require-launchable",
            ]
        )
        assert proc.returncode != 0
        assert "material edits" in proc.stderr

        source_split = base / "source_evidence_split_teacher.json"
        proc = run(
            [
                sys.executable,
                str(BUILDER),
                "--template",
                "source_evidence_split_teacher",
                "--output",
                str(source_split),
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        source_data = json.loads(source_split.read_text(encoding="utf-8"))
        assert source_data["candidate_id"] == "source_evidence_split_teacher_v1"
        assert source_data["launchable_for_production_attempt"] is True
        assert source_data["requires_material_edits_before_launch"] is False
        assert len(source_data["source_evidence_receipts"]) == 2
        assert "4.821 percent MAE" in source_data["material_change_summary"]
        assert any("Z8 source/degradation mismatch repair" in item for item in source_data["degradation_deltas"])
        assert any("source_evidence_split_teacher_x2d_smoke" in item for item in source_data["smoke_gate_commands"])
        assert any("source_evidence_split_teacher_z8_smoke" in item for item in source_data["smoke_gate_commands"])
        assert all("window_attention_pixelshuffle" in item for item in source_data["smoke_gate_commands"])
        assert all("--batch 6" in item for item in source_data["smoke_gate_commands"])
        assert all("--batch-size" not in item for item in source_data["smoke_gate_commands"])
        proc = run(
            [
                sys.executable,
                str(CHECKER),
                str(source_split),
                "--json-out",
                str(audit_json),
                "--html-out",
                str(audit_html),
                "--require-launchable",
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(audit_json.read_text(encoding="utf-8"))
        assert audit["launchable_for_production_attempt"] is True
        assert "source-evidence" in audit["material_source_matches"]
        assert "local source evidence" in audit["material_source_matches"]

        masked = base / "masked_detail_noop_teacher.json"
        proc = run(
            [
                sys.executable,
                str(BUILDER),
                "--template",
                "masked_detail_noop_teacher",
                "--output",
                str(masked),
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        masked_data = json.loads(masked.read_text(encoding="utf-8"))
        assert masked_data["candidate_id"] == "masked_detail_noop_teacher_v1"
        assert masked_data["launchable_for_production_attempt"] is True
        assert "target/objective" in masked_data["material_change_summary"]
        assert any("target-derived detail mask" in item for item in masked_data["architecture_deltas"])
        assert any("--detail-mask-threshold-counts 2.0" in item for item in masked_data["smoke_gate_commands"])
        assert any("--no-detail-noop-loss-weight 2.00" in item for item in masked_data["smoke_gate_commands"])
        proc = run(
            [
                sys.executable,
                str(CHECKER),
                str(masked),
                "--json-out",
                str(audit_json),
                "--html-out",
                str(audit_html),
                "--require-launchable",
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(audit_json.read_text(encoding="utf-8"))
        assert audit["launchable_for_production_attempt"] is True
        assert "target/objective" in audit["material_source_matches"]
        assert "target-derived detail mask" in audit["material_source_matches"]

        noop = base / "raw_cfa_candidate_hf_noop_teacher.json"
        proc = run(
            [
                sys.executable,
                str(BUILDER),
                "--template",
                "raw_cfa_candidate_hf_noop_teacher",
                "--output",
                str(noop),
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        noop_data = json.loads(noop.read_text(encoding="utf-8"))
        assert noop_data["candidate_id"] == "raw_cfa_candidate_hf_noop_teacher_v1"
        assert noop_data["launchable_for_production_attempt"] is True
        assert "candidate-only no-op/benefit gate" in noop_data["material_change_summary"]
        assert any("candidate-HF no-op" in item or "no-op benefit gate" in item for item in noop_data["architecture_deltas"])
        assert any("--candidate-hf-noop-threshold 0.004" in item for item in noop_data["smoke_gate_commands"])
        assert any("--candidate-hf-noop-softness 0.004" in item for item in noop_data["smoke_gate_commands"])
        assert all("--sample-mode random_patch" in item for item in noop_data["smoke_gate_commands"])
        proc = run(
            [
                sys.executable,
                str(CHECKER),
                str(noop),
                "--json-out",
                str(audit_json),
                "--html-out",
                str(audit_html),
                "--require-launchable",
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(audit_json.read_text(encoding="utf-8"))
        assert audit["launchable_for_production_attempt"] is True
        assert "no-op behavior" in audit["material_source_matches"]

        edited = base / "edited_clean_source_restormer_teacher.json"
        data["candidate_id"] = "contextual_raw_restoration_teacher_new_degradation_v1"
        data["launchable_for_production_attempt"] = True
        data["requires_material_edits_before_launch"] = False
        data["material_change_summary"] = (
            "Adds row-level measured PSF sidecars from real high/low pairs, "
            "then requires the teacher beats interpolation before long run on "
            "joint X2D/Z8 overlapped-tile validation."
        )
        data["degradation_deltas"][0] = "realistic camera blur/PSF synthesis from row-level PSF sidecars"
        data["validation_plan"].append(
            "both X2D and Z8 smoke holdouts beat interpolation before long run"
        )
        data["smoke_gate_commands"] = [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                "--pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs/pairs.npz "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/x2d_rowpsf_smoke "
                "--holdout-image x2d --model-arch window_attention_pixelshuffle"
            ),
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                "--pairs /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_pairs/pairs.npz "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/z8_rowpsf_smoke "
                "--holdout-image z8 --model-arch window_attention_pixelshuffle"
            ),
        ]
        edited.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        proc = run(
            [
                sys.executable,
                str(CHECKER),
                str(edited),
                "--json-out",
                str(audit_json),
                "--html-out",
                str(audit_html),
                "--require-launchable",
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(audit_json.read_text(encoding="utf-8"))
        assert audit["launchable_for_production_attempt"] is True
        assert audit_html.exists()

        bad = base / "rejected_repeat_fixture.json"
        proc = run(
            [
                sys.executable,
                str(BUILDER),
                "--template",
                "rejected_repeat_fixture",
                "--output",
                str(bad),
            ]
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        proc = run([sys.executable, str(CHECKER), str(bad), "--require-launchable"])
        assert proc.returncode != 0
        assert "rejected primary path" in proc.stderr

    print("test_build_premium_still_sr_candidate_preflight_template: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
