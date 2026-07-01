#!/usr/bin/env python3
"""Regression test for the four-pillar production burn-down builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_product_burndown.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_product_burndown_", dir=temp_root()) as tmp:
        external = Path(tmp) / "external"
        out_dir = Path(tmp) / "out"
        external.mkdir()
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(external),
                "--output-dir",
                str(out_dir),
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

        data = json.loads((out_dir / "product_burndown.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.product_burndown.v1"
        assert data["source_requirements_schema"] == "gpr.production_capture_requirements.v1"
        assert data["source_requirements_path"] == "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json"
        assert data["four_pillar_completion_percent"] == 82
        assert data["production_ready"] is False
        assert data["summary"]["action_count"] == 3
        assert data["summary"]["open_requirement_count"] == 4
        assert data["summary"]["optional_research_requirement_count"] == 1
        assert data["summary"]["camera_required_action_count"] == 1
        assert data["summary"]["non_camera_action_count"] == 2
        assert data["summary"]["mission1_camera_role_required_action_count"] == 1
        assert data["summary"]["new_sample_required_action_count"] == 1
        assert data["summary"]["model_promotion_action_count"] == 1
        assert data["summary"]["blocker_type_counts"] == {
            "hardware_integration": 1,
            "model_promotion": 1,
            "sample_acquisition": 1,
        }
        assert data["summary"]["lowest_readiness_pillar"] == "premium_still_sr"
        assert [row["id"] for row in data["pillars"]] == [
            "raw_stills",
            "raw_video_mvp",
            "premium_still_sr",
            "raw_video_reconstruction",
        ]
        assert data["open_requirement_ids"] == [
            "mission1_darkframe_stack",
            "iphone_cfa_darkframe_stack",
            "mission1_camera_role_receipts",
            "premium_still_sr_promotion_receipts",
        ]
        assert data["optional_research_requirement_ids"] == ["controlled_mission1_psf_pairs"]
        stills_actions = data["pillars"][0]["burn_down_actions"]
        assert "STILL smallest" in data["pillars"][0]["lock_ledger_paths"]
        assert "Broad real-camera Bayer phase coverage" not in data["pillars"][0]["open_production_gates"]
        assert any("X2D 100MP" in item for item in data["pillars"][0]["locked_artifacts"])
        assert stills_actions[0]["requirement_ids"] == ["mission1_darkframe_stack", "iphone_cfa_darkframe_stack"]
        assert stills_actions[0]["source_requirement_statuses"] == {
            "mission1_darkframe_stack": "open",
            "iphone_cfa_darkframe_stack": "open",
        }
        assert any("build_darkframe_candidate_audit.py" in command for command in stills_actions[0]["validation_commands"])
        assert any("darkframe" in " ".join(row["evidence_required"]).lower() for row in stills_actions)
        assert any("darkframe" in row["title"].lower() for row in stills_actions)
        assert all(row["blocker_type"] == "sample_acquisition" for row in stills_actions)
        assert all(row["requires_new_samples"] is True for row in stills_actions)
        video_actions = data["pillars"][1]["burn_down_actions"]
        assert "VIDEO_FREEZE" in data["pillars"][1]["lock_ledger_paths"]
        assert "Real Mission 1 camera-role raw-video closure" in data["pillars"][1]["open_production_gates"]
        assert any("20 fps" in item for item in data["pillars"][1]["locked_artifacts"])
        assert video_actions[0]["can_do_without_camera"] is False
        assert video_actions[0]["blocker_type"] == "hardware_integration"
        assert video_actions[0]["requires_mission1_camera_role"] is True
        assert video_actions[0]["requirement_ids"] == ["mission1_camera_role_receipts"]
        assert video_actions[0]["source_requirement_statuses"] == {
            "mission1_camera_role_receipts": "blocked_on_real_camera_access"
        }
        assert any("run_gopro_mission1_quick_validation.py" in command for command in video_actions[0]["validation_commands"])
        premium_actions = data["pillars"][2]["burn_down_actions"]
        assert premium_actions[0]["requirement_ids"] == ["premium_still_sr_promotion_receipts"]
        assert any("build_premium_still_sr_gate_receipt.py" in command for command in premium_actions[0]["validation_commands"])
        assert any(
            "check_production_capture_submission.py" in command
            for command in premium_actions[0]["validation_commands"]
        )
        premium_text = "\n".join(premium_actions[0]["evidence_required"] + [premium_actions[0]["completion_gate"]])
        assert "runtime_inputs" in premium_text
        assert "candidate_raw" in premium_text
        assert "REF/source/JPEG" in premium_text
        assert "median_mae_reduction_pct_50mp" in premium_text
        assert "median_mae_reduction_pct_100mp" in premium_text
        assert "worst_row_mae_reduction_pct_50mp" in premium_text
        assert "worst_row_mae_reduction_pct_100mp" in premium_text
        assert "render_seconds_per_50mp_frame" in premium_text
        assert "render_seconds_per_100mp_frame" in premium_text
        assert "peak_rss_gb" in premium_text
        assert "exact-sidecar-only" in premium_text
        reconstruction_actions = data["pillars"][3]["burn_down_actions"]
        assert reconstruction_actions == []
        assert data["pillars"][3]["readiness_percent"] == 95
        assert any("offline" in item.lower() for item in data["pillars"][3]["locked_artifacts"])

        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "GPR Production Burn-Down" in html
        assert "four-pillar completion" in html
        assert "Requirement IDs" in html
        assert "Open production requirement IDs" in html
        assert "Optional research requirement IDs, excluded from release blocker counts" in html
        assert "mission1_darkframe_stack" in html
        assert "controlled_mission1_psf_pairs" in html
        assert "Blocker type" in html
        assert "Lock ledger paths" in html
        assert "Open production gates" in html
        assert "Locked artifacts" in html
        assert "No camera?" in html
        assert "Mission 1 role?" in html
        assert "New samples?" in html
        assert "Validation commands" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_product_burndown: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
