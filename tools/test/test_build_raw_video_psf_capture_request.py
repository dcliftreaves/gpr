#!/usr/bin/env python3
"""Regression test for the raw-video PSF capture request builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_video_psf_capture_request.py"


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
    with tempfile.TemporaryDirectory(prefix="gpr_raw_video_psf_capture_", dir=temp_root()) as tmp:
        work = Path(tmp)
        gap = work / "gap.json"
        out = work / "out"
        gap.write_text(
            json.dumps(
                {
                    "schema": "gpr.raw_video_psf_gap_plan.v1",
                    "summary": {
                        "candidate_pair_count": 4,
                        "decoded_candidate_pair_count": 4,
                        "selected_pair_count": 3,
                        "accepted_pair_count": 2,
                        "kernel_stable": False,
                        "native_psf_ready_for_model_conditioning": False,
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--gap-plan", str(gap), "--output-dir", str(out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        data = json.loads((out / "raw_video_psf_capture_request.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.raw_video_psf_capture_request.v1"
        assert data["current_gap_summary"]["accepted_pair_count"] == 2
        assert data["summary"]["request_count"] == 2
        assert data["summary"]["required_request_count"] == 1
        assert data["summary"]["minimum_new_controlled_pair_count"] == 3
        assert data["promotion_policy"]["controlled_same_scene_pairs_required_for_kernel_promotion"] is True
        assert data["promotion_policy"]["pair_promotion_requires_source_hashes_and_decoded_raw_hashes"] is True
        assert data["promotion_policy"]["pair_promotion_requires_fixed_camera_settings"] is True
        assert data["promotion_policy"]["pair_promotion_requires_negative_controls"] is True
        primary = [row for row in data["requests"] if row["id"] == "mission1_static_high_low_psf_pairs"][0]
        assert any("SHA-256 source hashes" in item for item in primary["metadata_required"])
        assert any("little-endian uint16 Bayer" in item for item in primary["metadata_required"])
        assert any("camera and scene did not move" in item for item in primary["metadata_required"])
        assert any("decoded raw hashes" in item for item in primary["acceptance"])
        assert any("expected byte size" in item for item in primary["acceptance"])
        controls = [row for row in data["requests"] if row["id"] == "mission1_psf_negative_controls"][0]
        assert any("intended negative-control defect" in item for item in controls["metadata_required"])
        assert any("extract_raw_bayer_u16.py" in command for command in data["validation_commands"])
        assert any("build_mission1_native_psf_measurement.py" in command for command in data["validation_commands"])
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Raw Video PSF Capture Request" in html
        assert "Metadata required" in html
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_build_raw_video_psf_capture_request: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
