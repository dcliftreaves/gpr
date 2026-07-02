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
            "mission1_darkframe_stack",
            "iphone_cfa_darkframe_stack",
            "mission1_camera_role_receipts",
            "premium_still_sr_promotion_receipts",
        }
        mission = next(row for row in data["requirements"] if row["id"] == "mission1_darkframe_stack")
        assert len(mission["evidence"]) == 4
        assert mission["source_provenance_audit_schema"] == "gpr.darkframe_source_provenance_audit.v1"
        assert mission["source_provenance_audit_ready_frame_count"] == 4
        assert mission["source_provenance_audit_production_ready"] is True
        assert mission["evidence"][0]["no_scene_signal"] is True
        assert mission["evidence"][0]["source_kind"] == "confirmed_darkframes"
        assert "extracted_bayer_path" in mission["evidence"][0]
        assert "extracted_bayer_sha256" in mission["evidence"][0]
        assert "capture_setup" in mission["evidence"][0]
        assert "proof" in mission["evidence"][0]
        camera = next(row for row in data["requirements"] if row["id"] == "mission1_camera_role_receipts")
        assert camera["target_role"] == "camera"
        assert camera["source_width"] == 4096
        assert camera["source_height"] == 3072
        assert camera["preview_width"] == 1024
        assert camera["preview_height"] == 768
        assert camera["storage_budget_passed"] is True
        assert "storage_write_mb_s" in camera
        assert "peak_rss_mb" in camera
        assert "mission1_camera_closure_run" in camera["receipts"]
        sr = next(row for row in data["requirements"] if row["id"] == "premium_still_sr_promotion_receipts")
        assert sr["no_ref_runtime"] is True
        assert "candidate_raw" in sr["runtime_inputs"]
        assert sr["candidate_preflight_launchable"] is True
        assert sr["smoke_gate_baseline"] == "same-color Bayer interpolation"
        assert sr["smoke_gate_required_holdouts"] == ["X2D", "Z8"]
        assert sr["smoke_gate_long_run_blocked_if_smoke_fails"] is True
        assert "x2d_smoke_receipt_sha256" in sr
        assert "z8_smoke_receipt_sha256" in sr
        assert "baseline_comparison_sha256" in sr
        assert sr["noise_policy_exact_sidecars_only"] is True
        assert sr["noise_policy_forbids_source_residual_noise"] is True
        assert "full_frame_gate_50mp_row_count" in sr
        assert "render_seconds_per_100mp_frame" in sr
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
