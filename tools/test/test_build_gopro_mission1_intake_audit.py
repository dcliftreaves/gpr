#!/usr/bin/env python3
"""Regression test for the GoPro Mission 1 intake audit."""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_gopro_mission1_intake_audit.py"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_gvid(path: Path) -> None:
    payload = b"synthetic-frame"
    data = bytearray()
    data += struct.pack("<IBBHHHIIIII", 0x44495647, 1, 0, 1, 8, 0, 4096, 3072, 20000, 0, 1)
    data += struct.pack("<IIQ", 0x004D5246, len(payload), 0)
    data += payload
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build_bundle(root: Path) -> Path:
    write_gvid(root / "samples/mission1_4k_stream_source_8f.gvid")
    (root / "review").mkdir(parents=True)
    (root / "review/readme_showcase.webp").write_bytes(b"review")
    (root / "README.md").write_text("# bundle\n", encoding="utf-8")
    for rel in [
        "docs/REPO_README.md",
        "docs/source/docs__GOPRO_MISSION1_QUICK_VALIDATION.md",
        "docs/source/docs__LABS_FIRMWARE_API.md",
        "docs/source/docs__LABS_MISSION1_RUNBOOK.md",
        "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.md",
        "docs/source/docs__RELEASE_ARTIFACTS.md",
        "docs/source/tools__run_gopro_mission1_quick_validation.py",
        "docs/source/tools__check_mission1_camera_source_probe.py",
    ]:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# doc\n", encoding="utf-8")
    write_json(root / "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.json", {"schema": "test.production_capture"})
    write_json(root / "docs/source/docs__release_evidence_manifest.json", {"schema": "test.release"})
    write_json(
        root / "receipts/quick_validation_dry_run.json",
        {
            "schema": "gpr.gopro_mission1_quick_validation.v1",
            "target": {"role": "camera", "raw_source_kind": "sensor_dma_capture"},
            "verdict": {"command_ready": True, "production_ready": False},
        },
    )
    write_json(
        root / "receipts/labs_target_bench.json",
        {
            "schema": "gpr_labs_target_bench.v1",
            "target": {"name": "Pi 5 stand-in", "actual_wall_fps": 20.5},
            "verdict": {
                "fps_target_met": True,
                "fps_wall_target_met": True,
                "no_drops": True,
                "gvid_valid": True,
                "interruption_recovery_proven": True,
            },
        },
    )
    write_json(
        root / "receipts/camera_handoff_receipt.json",
        {
            "schema": "gpr_labs_camera_handoff_receipt.v1",
            "target": {"role": "stand-in"},
            "verdict": {"firmware_ready": False, "target_evidence": True},
        },
    )
    write_json(
        root / "receipts/preview_ui_receipt.json",
        {
            "schema": "gpr_labs_preview_ui_receipt.v1",
            "target": {"role": "stand-in"},
            "verdict": {"ui_ready": False, "target_evidence": True, "fps_target_met": True},
        },
    )
    write_json(
        root / "receipts/mission1_camera_closure_run.json",
        {
            "schema": "gpr.mission1_camera_closure_run.v1",
            "verdict": {
                "production_ready": False,
                "handoff_blocker": "camera sensor/DMA and camera storage handoff not executed",
                "preview_blocker": "Mission 1 camera UI/display path not executed",
            },
        },
    )

    artifacts = [
        "README.md:text",
        "samples/mission1_4k_stream_source_8f.gvid:gvid",
        "review/readme_showcase.webp:media",
        "receipts/quick_validation_dry_run.json:json",
        "receipts/labs_target_bench.json:json",
        "receipts/camera_handoff_receipt.json:json",
        "receipts/preview_ui_receipt.json:json",
        "receipts/mission1_camera_closure_run.json:json",
        "docs/REPO_README.md:text",
        "docs/source/docs__GOPRO_MISSION1_QUICK_VALIDATION.md:text",
        "docs/source/docs__LABS_FIRMWARE_API.md:text",
        "docs/source/docs__LABS_MISSION1_RUNBOOK.md:text",
        "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.md:text",
        "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.json:json",
        "docs/source/docs__RELEASE_ARTIFACTS.md:text",
        "docs/source/docs__release_evidence_manifest.json:json",
        "docs/source/tools__run_gopro_mission1_quick_validation.py:text",
        "docs/source/tools__check_mission1_camera_source_probe.py:text",
    ]
    cmd = [
        sys.executable,
        str(ROOT / "tools/build_labs_bundle.py"),
        str(root),
        "--repo-commit",
        "synthetic-intake",
        "--ci-run",
        "https://github.com/dcliftreaves/gpr/actions/runs/0",
        "--target-name",
        "Pi 5 stand-in",
        "--target-role",
        "stand-in",
        "--note",
        "synthetic intake test",
    ]
    for artifact in artifacts:
        cmd.extend(["--artifact", artifact])
    proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert proc.returncode == 0, proc.stderr
    return root / "manifest.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_mission1_intake_audit_") as tmp:
        root = Path(tmp)
        manifest = build_bundle(root / "bundle")
        out = root / "out"
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--manifest", str(manifest), "--output-dir", str(out)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        data = json.loads((out / "intake_audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.gopro_mission1_intake_audit.v1"
        assert data["readiness_percent"] == 82
        assert data["handoff_review_ready"] is True
        assert data["camera_production_ready"] is False
        assert data["production_ready"] is False
        pillar_ids = {row["id"] for row in data["product_pillars"]}
        assert pillar_ids == {"raw_stills", "raw_video_mvp", "premium_still_sr", "raw_video_psf_sr"}
        assert data["summary"]["sample_gvid"]["width"] == 4096
        assert data["summary"]["sample_gvid"]["height"] == 3072
        assert any(row["id"] == "product_pillar_labels_packaged" and row["passed"] for row in data["checks"])
        assert any(row["id"] == "camera_handoff_receipts_are_real_camera" and not row["passed"] for row in data["checks"])
        assert "real Mission 1 camera-role" in " ".join(data["blockers"])
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "GoPro Mission 1 Intake Audit" in html
        assert "Product Pillars" in html
        assert "RAW video MVP" in html
        assert "camera production ready: <strong>false</strong>" in html
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_build_gopro_mission1_intake_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
