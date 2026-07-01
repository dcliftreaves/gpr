#!/usr/bin/env python3
"""Regression test for the raw-stills noise sidecar readiness builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_stills_noise_sidecar_readiness.py"


def temp_root() -> str | None:
    for key in ("GPR_TMPDIR", "TMPDIR"):
        value = os.environ.get(key)
        if value:
            Path(value).mkdir(parents=True, exist_ok=True)
            return value
    return None


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_builder(
    coverage: Path,
    runtime: Path,
    darkframes: Path,
    gap: Path,
    capture: Path,
    out_dir: Path,
) -> dict:
    subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--coverage",
            str(coverage),
            "--runtime-policy",
            str(runtime),
            "--darkframe-audit",
            str(darkframes),
            "--gap-plan",
            str(gap),
            "--capture-request",
            str(capture),
            "--output-dir",
            str(out_dir),
        ],
        check=True,
    )
    return json.loads((out_dir / "raw_stills_noise_sidecar_readiness.json").read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_raw_stills_noise_readiness_", dir=temp_root()) as tmp:
        work = Path(tmp)
        coverage = work / "noise_coverage.json"
        runtime = work / "camera_noise_runtime_policy.json"
        darkframes = work / "darkframe_candidate_audit.json"
        gap = work / "stills_fixture_gap_plan.json"
        capture = work / "stills_capture_request.json"
        out_dir = work / "out"

        write_json(
            coverage,
            {
                "schema": "gpr.camera_noise_coverage_audit.v1",
                "summary": {
                    "ready_camera_keys": ["x2d", "z8"],
                    "missing_camera_keys": ["mission1", "iphone"],
                },
                "coverage": [
                    {
                        "key": "x2d",
                        "label": "Hasselblad X2D 100C",
                        "ready": True,
                        "ready_isos": [64, 800],
                    },
                    {
                        "key": "z8",
                        "label": "Nikon Z 8",
                        "ready": True,
                        "ready_isos": [500],
                    },
                    {
                        "key": "mission1",
                        "label": "GoPro Mission 1",
                        "ready": False,
                        "ready_isos": [],
                        "blocker": "no validated sidecar",
                    },
                    {
                        "key": "iphone",
                        "label": "iPhone CFA",
                        "ready": False,
                        "ready_isos": [],
                        "blocker": "no validated sidecar",
                    },
                ],
            },
        )
        write_json(
            runtime,
            {
                "schema": "gpr.camera_noise_runtime_policy.v1",
                "camera_policies": [
                    {
                        "camera_key": "x2d",
                        "label": "Hasselblad X2D 100C",
                        "allow_nonzero_noise_addback": True,
                        "ready_isos": [64, 800],
                        "runtime_fallback": {"mode": "calibrated_sidecar_required"},
                    },
                    {
                        "camera_key": "z8",
                        "label": "Nikon Z 8",
                        "allow_nonzero_noise_addback": True,
                        "ready_isos": [500],
                        "runtime_fallback": {"mode": "calibrated_sidecar_required"},
                    },
                    {
                        "camera_key": "mission1",
                        "label": "GoPro Mission 1",
                        "allow_nonzero_noise_addback": False,
                        "ready_isos": [],
                        "runtime_fallback": {"mode": "metadata_conditioning_only"},
                    },
                    {
                        "camera_key": "iphone",
                        "label": "iPhone CFA",
                        "allow_nonzero_noise_addback": False,
                        "ready_isos": [],
                        "runtime_fallback": {"mode": "metadata_conditioning_only"},
                    },
                ],
            },
        )
        write_json(
            darkframes,
            {
                "schema": "gpr.darkframe_candidate_audit.v1",
                "summary": {
                    "darkframe_like_count": 29,
                    "production_stack_ready_group_count": 0,
                },
            },
        )
        write_json(
            gap,
            {
                "schema": "gpr.stills_fixture_gap_plan.v1",
                "summary": {
                    "all_real_bayer_phases_ready": True,
                    "nearest_darkframe_stack_by_noise_key": {
                        "mission1": {
                            "key": "GoPro|MISSION 1|ISO232|RGGB",
                            "candidate_count": 2,
                            "needed_for_stack": 2,
                            "production_stack_ready": False,
                        },
                        "iphone": {
                            "key": "Apple|iPhone 7 Plus|ISO1250|RGGB",
                            "candidate_count": 27,
                            "needed_for_stack": 0,
                            "production_stack_ready": False,
                        },
                    },
                },
            },
        )
        write_json(
            capture,
            {
                "schema": "gpr.stills_capture_request.v1",
                "summary": {"required_request_count": 2},
                "requests": [
                    {"requirement_id": "mission1_darkframe_stack"},
                    {"requirement_id": "iphone_cfa_darkframe_stack"},
                ],
            },
        )

        data = run_builder(coverage, runtime, darkframes, gap, capture, out_dir)
        assert data["schema"] == "gpr.raw_stills_noise_sidecar_readiness.v1"
        assert data["summary"]["production_ready_camera_keys"] == ["x2d", "z8"]
        assert data["summary"]["blocked_camera_keys"] == ["iphone", "mission1"]
        assert data["summary"]["mission_iphone_noise_addback_enabled"] is False
        assert data["summary"]["production_raw_stills_noise_ready"] is False
        assert data["summary"]["source_consistency_ok"] is True
        assert data["summary"]["source_consistency_error_count"] == 0
        assert data["summary"]["open_requirement_ids"] == [
            "iphone_cfa_darkframe_stack",
            "mission1_darkframe_stack",
        ]
        rows = {row["camera_key"]: row for row in data["camera_readiness"]}
        assert rows["mission1"]["needed_for_stack"] == 2
        assert "needs 2 more" in rows["mission1"]["blocker"]
        assert rows["iphone"]["candidate_count"] == 27
        assert "provenance" in rows["iphone"]["blocker"]
        assert (out_dir / "index.html").exists()

        bad_runtime = json.loads(runtime.read_text(encoding="utf-8"))
        for row in bad_runtime["camera_policies"]:
            if row["camera_key"] == "mission1":
                row["allow_nonzero_noise_addback"] = True
                row["runtime_fallback"] = {"mode": "calibrated_sidecar_required"}
        bad_runtime_path = work / "bad_camera_noise_runtime_policy.json"
        bad_out_dir = work / "bad_out"
        write_json(bad_runtime_path, bad_runtime)
        bad = run_builder(coverage, bad_runtime_path, darkframes, gap, capture, bad_out_dir)
        bad_rows = {row["camera_key"]: row for row in bad["camera_readiness"]}
        assert bad["summary"]["production_ready_camera_keys"] == ["x2d", "z8"]
        assert bad["summary"]["source_consistency_ok"] is False
        assert bad["summary"]["source_consistency_error_count"] == 1
        assert bad["summary"]["source_consistency_errors"] == {
            "mission1": ["runtime policy enables nonzero addback without validated sidecar coverage"]
        }
        assert bad_rows["mission1"]["runtime_policy_declares_nonzero_noise_addback"] is True
        assert bad_rows["mission1"]["runtime_nonzero_noise_addback_enabled"] is False
        assert "without validated sidecar coverage" in bad_rows["mission1"]["blocker"]
    print("test_build_raw_stills_noise_sidecar_readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
