#!/usr/bin/env python3
"""Regression-test production capture submission template generation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_production_capture_submission_template.py"
CHECKER = ROOT / "tools/check_production_capture_submission.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or "/Volumes/OWC_8TB/gpr_work/tmp")
    if not root.exists():
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_capture_submission_template_", dir=temp_root()) as td:
        out = Path(td) / "submission_template.json"
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--output", str(out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.production_capture_submission.v1"
        assert proc.stdout.strip() == str(out)
        ids = {row["id"] for row in data["requirements"]}
        assert ids == {
            "real_grbg_fixture",
            "real_bggr_fixture",
            "mission1_darkframe_stack",
            "iphone_cfa_darkframe_stack",
            "mission1_camera_role_receipts",
            "controlled_mission1_psf_pairs",
            "premium_still_sr_promotion_receipts",
        }
        grbg = next(row for row in data["requirements"] if row["id"] == "real_grbg_fixture")
        assert grbg["evidence"][0]["cfa_phase"] == "GRBG"
        mission = next(row for row in data["requirements"] if row["id"] == "mission1_darkframe_stack")
        assert len(mission["evidence"]) == 4
        assert mission["evidence"][0]["no_scene_signal"] is True
        camera = next(row for row in data["requirements"] if row["id"] == "mission1_camera_role_receipts")
        assert camera["target_role"] == "camera"
        assert "mission1_camera_closure_run" in camera["receipts"]
        psf = next(row for row in data["requirements"] if row["id"] == "controlled_mission1_psf_pairs")
        assert len(psf["pairs"]) == 4
        assert any(pair["negative_control"] is True for pair in psf["pairs"])
        sr = next(row for row in data["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        assert sr["no_ref_runtime"] is True
        assert "<64_hex_sha256>" in out.read_text(encoding="utf-8")

        check = subprocess.run(
            [sys.executable, str(CHECKER), str(out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert check.returncode == 1
        assert "64 hex" in check.stdout or "64-hex" in check.stdout

    print("test_build_production_capture_submission_template: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
