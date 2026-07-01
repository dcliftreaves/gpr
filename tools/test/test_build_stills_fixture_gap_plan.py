#!/usr/bin/env python3
"""Regression test for the stills fixture gap plan builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_stills_fixture_gap_plan.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_stills_fixture_gap_", dir=temp_root()) as tmp:
        work = Path(tmp)
        bayer = work / "bayer.json"
        bayer_extra = work / "bayer_extra.json"
        dark = work / "dark.json"
        noise = work / "noise.json"
        out_dir = work / "out"
        out_dir_combined = work / "out_combined"
        write_json(
            bayer,
            {
                "schema": "gpr.bayer_phase_fixture_inventory.v1",
                "summary": {
                    "phase_counts": {"RGGB": 4, "GBRG": 1},
                    "normal_bayer_phases_missing": ["GRBG", "BGGR"],
                },
            },
        )
        write_json(
            bayer_extra,
            {
                "schema": "gpr.bayer_phase_fixture_inventory.v1",
                "summary": {
                    "phase_counts": {"GRBG": 2, "BGGR": 3},
                    "normal_bayer_phases_missing": ["GBRG"],
                },
            },
        )
        write_json(
            dark,
            {
                "schema": "gpr.darkframe_candidate_audit.v1",
                "summary": {"production_stack_ready_group_count": 0},
                "stack_groups": [
                    {
                        "key": "GoPro|MISSION 1|ISO232|RGGB",
                        "candidate_count": 2,
                        "production_stack_ready": False,
                        "paths": ["a.dng", "b.dng"],
                    },
                    {
                        "key": "GoPro|MISSION 1|ISO198|RGGB",
                        "candidate_count": 1,
                        "production_stack_ready": False,
                        "paths": ["c.dng"],
                    },
                ],
            },
        )
        write_json(
            noise,
            {
                "schema": "gpr.camera_noise_coverage_audit.v1",
                "summary": {
                    "ready_camera_count": 2,
                    "missing_camera_keys": ["mission1", "iphone"],
                },
                "coverage": [
                    {"key": "x2d", "label": "Hasselblad X2D 100C", "ready": True, "ready_isos": [64, 200]},
                    {"key": "z8", "label": "Nikon Z 8", "ready": True, "ready_isos": [500]},
                    {
                        "key": "mission1",
                        "label": "GoPro Mission 1",
                        "ready": False,
                        "blocker": "no validated sidecar",
                        "fixture_status": "fixtures only",
                    },
                    {
                        "key": "iphone",
                        "label": "iPhone CFA",
                        "ready": False,
                        "blocker": "no validated sidecar",
                        "fixture_status": "fixtures only",
                    },
                ],
            },
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--bayer-inventory",
                str(bayer),
                "--darkframe-audit",
                str(dark),
                "--noise-coverage",
                str(noise),
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
        plan = json.loads((out_dir / "stills_fixture_gap_plan.json").read_text(encoding="utf-8"))
        assert plan["schema"] == "gpr.stills_fixture_gap_plan.v1"
        assert plan["summary"]["production_stills_fixture_closure_ready"] is False
        assert plan["summary"]["missing_real_bayer_phases"] == ["GRBG", "BGGR"]
        assert plan["summary"]["missing_real_bayer_phase_requirement_ids"] == [
            "real_grbg_fixture",
            "real_bggr_fixture",
        ]
        assert plan["summary"]["noise_missing_camera_keys"] == ["mission1", "iphone"]
        assert plan["summary"]["noise_missing_requirement_ids"] == [
            "mission1_darkframe_stack",
            "iphone_cfa_darkframe_stack",
        ]
        assert plan["summary"]["open_requirement_ids"] == [
            "iphone_cfa_darkframe_stack",
            "mission1_darkframe_stack",
            "real_bggr_fixture",
            "real_grbg_fixture",
        ]
        assert plan["summary"]["nearest_darkframe_stack_key"] == "GoPro|MISSION 1|ISO232|RGGB"
        assert plan["summary"]["nearest_darkframe_stack_candidate_count"] == 2
        assert all(row.get("requirement_id") for row in plan["capture_actions"])
        assert any("Top up darkframe group" in row["action"] for row in plan["capture_actions"])
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Stills Fixture Gap Plan" in html
        assert "Requirement" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")

        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--bayer-inventory",
                str(bayer),
                "--bayer-inventory",
                str(bayer_extra),
                "--darkframe-audit",
                str(dark),
                "--noise-coverage",
                str(noise),
                "--output-dir",
                str(out_dir_combined),
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
        combined = json.loads((out_dir_combined / "stills_fixture_gap_plan.json").read_text(encoding="utf-8"))
        assert combined["summary"]["phase_counts"] == {"RGGB": 4, "GBRG": 1, "GRBG": 2, "BGGR": 3}
        assert combined["summary"]["missing_real_bayer_phases"] == []
        assert combined["summary"]["missing_real_bayer_phase_requirement_ids"] == []
        assert combined["summary"]["open_requirement_ids"] == [
            "iphone_cfa_darkframe_stack",
            "mission1_darkframe_stack",
        ]
    print("test_build_stills_fixture_gap_plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
