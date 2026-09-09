#!/usr/bin/env python3
"""Regression test for the Mission 1 native PSF measurement plan."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_native_psf_measurement_plan.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_mission1_native_psf_plan_") as td:
        out_dir = Path(td) / "plan"
        external_root = Path(td) / "external"
        external_root.mkdir()
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--synthetic",
                "--external-root",
                str(external_root),
                "--output-dir",
                str(out_dir),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        plan_path = out_dir / "measurement_plan.json"
        dashboard_path = out_dir / "index.html"
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.mission1_native_psf_measurement_plan.v1"
        assert data["mode"] == "synthetic"
        assert data["production_ready"] is False
        assert data["native_psf_measured"] is False
        assert data["measurement_plan_ready"] is True
        assert data["summary"]["candidate_pair_count"] == 4
        assert data["summary"]["decoded_candidate_pair_count"] == 3
        assert data["summary"]["selected_pair_count"] == 3
        assert data["summary"]["pair_derived_fixture_count"] == 1024
        assert data["summary"]["pair_derived_best_kernel"] == "same_color_box2"
        assert data["acceptance"]["minimum_selected_pairs"] == 3
        assert any(stage["id"] == "native_psf_estimation" for stage in data["measurement_stages"])
        assert any("No native high-to-low" in blocker for blocker in data["blockers"])

        html = dashboard_path.read_text(encoding="utf-8")
        assert "Mission 1 Native PSF Measurement Plan" in html
        assert "Selected Pairs" in html
        assert "native_psf_estimation" in html
        assert "Plan ready" in html
        assert proc.stdout.strip() == str(dashboard_path)
    print("test_build_mission1_native_psf_measurement_plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
