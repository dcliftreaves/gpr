#!/usr/bin/env python3
"""Regression test for the premium still-SR target expansion planner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_target_expansion_plan.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fixture(label: str, camera_key: str, klass: str, ext: str, *, noise: bool, path_stem: str) -> dict:
    return {
        "label": label,
        "camera": {"x2d": "Hasselblad X2D 100C", "z8": "Nikon Z8", "mission1": "GoPro Mission 1"}[camera_key],
        "camera_key": camera_key,
        "class": klass,
        "extension": ext,
        "premium_still_sr_eligible": True,
        "source": {
            "exists": True,
            "path": f"/fixtures/{path_stem}.{ext}",
            "sha256": label.rjust(64, "0")[:64],
        },
        "noise_sidecars": [{"path": f"/noise/{camera_key}.json"}] if noise else [],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_target_plan_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        out = Path(tmp) / "out"
        fixtures = [
            fixture("x2d_existing_1742", "x2d", "100mp", "dng", noise=True, path_stem="2024_April_X2D_1742"),
            fixture("x2d_new_0100", "x2d", "100mp", "dng", noise=True, path_stem="2025_Austin_0100"),
            fixture("x2d_new_0200", "x2d", "100mp", "dng", noise=True, path_stem="2025_Austin_0200"),
            fixture("z8_1000", "z8", "50mp", "dng", noise=True, path_stem="Z8Z_1000"),
            fixture("z8_2000", "z8", "50mp", "dng", noise=True, path_stem="Z8Z_2000"),
            fixture("z8_3000", "z8", "50mp", "dng", noise=True, path_stem="Z8Z_3000"),
            fixture("mission1_5000", "mission1", "50mp", "dng", noise=False, path_stem="GP015000"),
        ]
        write_json(
            root / "artifacts/premium_still_sr_fixture_manifest_routed_20260630/fixture_manifest.json",
            {"schema": "gpr.premium_still_sr_fixture_manifest.v1", "fixtures": fixtures},
        )
        write_json(
            root / "artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630/merged/merge_receipt.json",
            {
                "schema": "gpr.premium_still_sr_hf_residual_targets_merged.v1",
                "summary": {"row_count": 81, "scene_count": 3, "scenes": ["x2d_1742_iso12800", "x2d_austin0150_iso3200", "x2d_austin0181_iso6400"]},
            },
        )
        write_json(
            root / "artifacts/premium_still_sr_blocker_audit_20260630/blocker_audit.json",
            {
                "schema": "gpr.premium_still_sr_blocker_audit.v1",
                "recommended_next_experiment": {
                    "minimum_acceptance": {
                        "minimum_target_rows": 160,
                        "minimum_target_scenes": 5,
                        "holdout_recovery_mae_pct": 15.0,
                        "full_still_editor_latitude_gate": True,
                    }
                },
            },
        )

        proc = subprocess.run(
            [sys.executable, str(TOOL), "--external-root", str(root), "--z8-scenes", "2", "--output-dir", str(out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        plan = json.loads((out / "target_expansion_plan.json").read_text(encoding="utf-8"))
        html = (out / "index.html").read_text(encoding="utf-8")
        assert plan["schema"] == "gpr.premium_still_sr_target_expansion_plan.v1"
        assert plan["current_target"]["scene_count"] == 3
        assert plan["planned_target"]["new_scene_count"] == 4
        assert plan["planned_target"]["total_rows"] == 189
        assert plan["planned_target"]["meets_minimum_target_coverage"] is True
        assert plan["planned_target"]["has_noise_sidecar_for_every_selected_scene"] is True
        assert plan["deferred_target_count"] == 1
        labels = [row["label"] for row in plan["selected_new_targets"]]
        assert "x2d_existing_1742" not in labels
        assert "x2d_new_0100" in labels
        assert sum(1 for row in plan["selected_new_targets"] if row["camera_key"] == "z8") == 2
        assert plan["selected_new_targets"][0]["noise_sidecars"][0]["path"].startswith("/noise/")
        assert plan["selected_new_targets"][0]["selected_noise_sidecars"][0]["path"].startswith("/noise/")
        commands = "\n".join(row["command_template"] for row in plan["commands"])
        assert "build_premium_still_sr_degraded_candidate_raw.py" in commands
        assert "--candidate-raw" in commands
        assert "--include-raw-cfa-features" in commands
        assert "--noise-sidecar" in commands
        assert "--synthetic-hf-sidecar" not in commands
        assert "--feature-mode rgb_multiscale_coord_luma_ev_noise_bright" in commands
        assert "--model-arch raw_cfa_gated" in commands
        assert "--feature-mode rgb_multiscale_rawcfa_phase_coord_luma_ev_noise_bright" in commands
        assert "premium_still_sr_expanded_rawcfa_gated_model_20260630" in commands
        assert "premium_still_sr_expanded_rgb_ablation_model_20260630" in commands
        assert "Premium Still-SR Target Expansion Plan" in html
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_build_premium_still_sr_target_expansion_plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
