#!/usr/bin/env python3
"""Regression test for the raw-video PSF gap plan builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_video_psf_gap_plan.py"


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
    with tempfile.TemporaryDirectory(prefix="gpr_raw_video_psf_gap_", dir=temp_root()) as tmp:
        work = Path(tmp)
        inventory = work / "inventory.json"
        measurement_plan = work / "measurement_plan.json"
        measurement = work / "measurement.json"
        audit = work / "audit.json"
        out_dir = work / "out"
        write_json(
            inventory,
            {
                "schema": "gpr.mission1_native_psf_pair_inventory.v1",
                "summary": {
                    "candidate_pair_count": 4,
                    "decoded_candidate_pair_count": 4,
                },
            },
        )
        write_json(
            measurement_plan,
            {
                "schema": "gpr.mission1_native_psf_measurement_plan.v1",
                "summary": {"selected_pair_count": 3},
            },
        )
        write_json(
            measurement,
            {
                "schema": "gpr.mission1_native_psf_measurement.v1",
                "native_psf_ready_for_model_conditioning": False,
                "summary": {
                    "accepted_pair_count": 2,
                    "rejected_pair_count": 1,
                    "accepted_sharp_edge_tile_count": 1409,
                    "accepted_texture_field_tile_count": 1381,
                    "kernel_stable": False,
                },
            },
        )
        write_json(
            audit,
            {
                "schema": "gpr.raw_video_psf_audit.v1",
                "approved_baselines_ready": True,
                "psf_replacement_ready": False,
                "summary": {
                    "standalone_continuous_8k_review_media_ready": True,
                },
            },
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pair-inventory",
                str(inventory),
                "--measurement-plan",
                str(measurement_plan),
                "--measurement",
                str(measurement),
                "--psf-audit",
                str(audit),
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
        plan = json.loads((out_dir / "raw_video_psf_gap_plan.json").read_text(encoding="utf-8"))
        assert plan["schema"] == "gpr.raw_video_psf_gap_plan.v1"
        assert plan["summary"]["approved_baselines_ready"] is True
        assert plan["summary"]["standalone_continuous_8k_review_media_ready"] is True
        assert plan["summary"]["accepted_pair_count"] == 2
        assert plan["summary"]["tile_support_ready"] is True
        assert plan["summary"]["kernel_stable"] is False
        assert plan["summary"]["production_psf_closure_ready"] is False
        assert any(row["id"] == "accepted_pair_count" for row in plan["blockers"])
        assert not any(row["id"] == "standalone_continuous_8k_review_media" for row in plan["blockers"])
        assert any(row["id"] == "kernel_stability" for row in plan["blockers"])
        assert any("PSF-conditioned" in row["action"] for row in plan["next_actions"])
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Raw Video PSF Gap Plan" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_raw_video_psf_gap_plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
