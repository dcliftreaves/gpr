#!/usr/bin/env python3
"""Regression test for the raw-video PSF/SR audit builder."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_video_psf_audit.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_raw_video_psf_audit_") as td:
        out_dir = Path(td) / "audit"
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

        audit_path = out_dir / "raw_video_psf_audit.json"
        dashboard_path = out_dir / "index.html"
        data = json.loads(audit_path.read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.raw_video_psf_audit.v1"
        assert data["mode"] == "synthetic"
        assert data["readiness_percent"] == 40
        assert data["production_ready"] is False
        assert data["approved_baselines_ready"] is True
        assert data["psf_replacement_ready"] is False
        assert data["summary"]["cleanup_4k_ready"] is True
        assert data["summary"]["sr_8k_ready"] is True
        assert data["summary"]["native_psf_ready"] is False
        assert data["pair_derived_psf"]["best_kernel"] == "same_color_box2"
        assert data["pair_derived_psf"]["fine_share_of_residual_abs"] > 0.99
        assert any(check["id"] == "native_capture_display_psf" and not check["passed"] for check in data["checks"])
        assert any("native camera" in blocker for blocker in data["blockers"])

        html = dashboard_path.read_text(encoding="utf-8")
        assert "Raw Video PSF / SR Audit" in html
        assert "4K cleanup baseline" in html
        assert "PSF replacement" in html
        assert "production ready: false" in html
        assert proc.stdout.strip() == str(dashboard_path)
    print("test_build_raw_video_psf_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
