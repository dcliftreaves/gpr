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
