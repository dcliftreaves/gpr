#!/usr/bin/env python3
"""Regression test for the raw-stills capture request builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_stills_capture_request.py"


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
    with tempfile.TemporaryDirectory(prefix="gpr_stills_capture_request_", dir=temp_root()) as tmp:
        work = Path(tmp)
        gap_plan = work / "stills_fixture_gap_plan.json"
        out_dir = work / "out"
        gap_plan.write_text(
            json.dumps(
                {
                    "schema": "gpr.stills_fixture_gap_plan.v1",
                    "summary": {
                        "missing_real_bayer_phases": ["GRBG", "BGGR"],
                        "noise_missing_camera_keys": ["mission1", "iphone"],
                        "nearest_darkframe_stack_key": "GoPro|MISSION 1|ISO232|RGGB",
                        "nearest_darkframe_stack_candidate_count": 2,
                        "nearest_darkframe_stack_by_noise_key": {
                            "mission1": {
                                "key": "GoPro|MISSION 1|ISO232|RGGB",
                                "candidate_count": 2,
                                "needed_for_stack": 2,
                                "paths": ["a.dng", "b.dng"],
                            },
                            "iphone": {
                                "key": "Apple|iPhone 7 Plus|ISO1250|RGGB",
                                "candidate_count": 5,
                                "needed_for_stack": 0,
                                "paths": ["iphone0.dng", "iphone1.dng", "iphone2.dng", "iphone3.dng"],
                            },
                        },
                        "production_stills_fixture_closure_ready": False,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--gap-plan", str(gap_plan), "--output-dir", str(out_dir)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        data = json.loads((out_dir / "stills_capture_request.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.stills_capture_request.v1"
        assert data["summary"]["request_count"] == 6
        assert data["summary"]["required_request_count"] == 4
        assert data["summary"]["all_request_ids_are_committed_requirements"] is True
        assert data["summary"]["required_requirement_ids"] == [
            "iphone_cfa_darkframe_stack",
            "mission1_darkframe_stack",
            "real_bggr_fixture",
            "real_grbg_fixture",
        ]
        assert data["summary"]["missing_real_bayer_phases"] == ["GRBG", "BGGR"]
        assert any(row["id"] == "real_grbg_fixture" and row["requirement_id"] == "real_grbg_fixture" for row in data["requests"])
        mission = [row for row in data["requests"] if row["id"] == "mission1_darkframe_stack"][0]
        assert mission["requirement_id"] == "mission1_darkframe_stack"
        assert any("SHA-256" in item for item in mission["metadata_required"])
        assert any("little-endian uint16 Bayer extraction" in item for item in mission["metadata_required"])
        assert any("source-provenance manifest" in item for item in mission["metadata_required"])
        assert any("separates_noise_from_signal=true" in item for item in mission["acceptance"])
        assert any("source_provenance_ready=true" in item for item in mission["acceptance"])
        topup = [row for row in data["requests"] if row["id"] == "mission1_lowest_lift_darkframe_topup"][0]
        assert topup["requirement_id"] == "mission1_darkframe_stack"
        assert topup["minimum_count"] == 2
        assert topup["existing_candidate_count"] == 2
        assert any("ordinary dark-looking scene photos" in item for item in topup["capture_guidance"])
        iphone_topup = [row for row in data["requests"] if row["id"] == "iphone_lowest_lift_darkframe_topup"][0]
        assert iphone_topup["requirement_id"] == "iphone_cfa_darkframe_stack"
        assert iphone_topup["minimum_count"] == 0
        assert iphone_topup["existing_candidate_count"] == 5
        assert any("no-scene-signal" in item for item in iphone_topup["metadata_required"])
        assert any("extract_raw_bayer_u16.py" in command for command in data["validation_commands"])
        assert any("build_camera_noise_calibration.py" in command for command in data["validation_commands"])
        assert any("--require-source-provenance" in command for command in data["validation_commands"])
        assert any("--source-provenance-manifest" in command for command in data["validation_commands"])
        assert data["promotion_policy"]["noise_sidecar_requires_source_hashes_and_fixed_camera_metadata"] is True
        assert data["promotion_policy"]["noise_sidecar_requires_u16_bayer_extraction_receipt"] is True
        assert data["promotion_policy"]["noise_sidecar_requires_strict_source_provenance"] is True
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Raw Stills Capture Request" in html
        assert "Requirement" in html
        assert "Metadata required" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_stills_capture_request: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
