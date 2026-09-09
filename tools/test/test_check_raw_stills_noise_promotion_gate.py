#!/usr/bin/env python3
"""Regression test for the RAW-stills noise promotion gate."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_raw_stills_noise_promotion_gate.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("raw_stills_noise_promotion_gate", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def readiness() -> dict:
    rows = [
        {
            "camera_key": "iphone",
            "label": "iPhone CFA",
            "production_ready": False,
            "runtime_nonzero_noise_addback_enabled": False,
            "runtime_policy_declares_nonzero_noise_addback": False,
            "runtime_mode": "metadata_conditioning_only",
            "requirement_id": "iphone_cfa_darkframe_stack",
            "ready_isos": [],
            "blocker": "candidate stack needs no-scene-signal provenance",
        },
        {
            "camera_key": "mission1",
            "label": "GoPro Mission 1",
            "production_ready": False,
            "runtime_nonzero_noise_addback_enabled": False,
            "runtime_policy_declares_nonzero_noise_addback": False,
            "runtime_mode": "metadata_conditioning_only",
            "requirement_id": "mission1_darkframe_stack",
            "ready_isos": [],
            "blocker": "needs 2 more matching true darkframe frames",
        },
        {
            "camera_key": "x2d",
            "label": "Hasselblad X2D 100C",
            "production_ready": True,
            "runtime_nonzero_noise_addback_enabled": True,
            "runtime_policy_declares_nonzero_noise_addback": True,
            "runtime_mode": "calibrated_sidecar_required",
            "ready_isos": [64, 200, 800],
            "blocker": None,
        },
        {
            "camera_key": "z8",
            "label": "Nikon Z 8",
            "production_ready": True,
            "runtime_nonzero_noise_addback_enabled": True,
            "runtime_policy_declares_nonzero_noise_addback": True,
            "runtime_mode": "calibrated_sidecar_required",
            "ready_isos": [500],
            "blocker": None,
        },
    ]
    return {
        "schema": "gpr.raw_stills_noise_sidecar_readiness.v1",
        "summary": {
            "production_ready_camera_keys": ["x2d", "z8"],
            "blocked_camera_keys": ["iphone", "mission1"],
            "open_requirement_ids": ["iphone_cfa_darkframe_stack", "mission1_darkframe_stack"],
            "mission_iphone_noise_addback_enabled": False,
            "production_raw_stills_noise_ready": False,
            "nonzero_noise_addback_must_remain_disabled_for_blocked_cameras": True,
            "source_consistency_ok": True,
            "source_consistency_error_count": 0,
            "all_real_bayer_phases_ready": True,
            "darkframe_like_count": 29,
            "production_stack_ready_group_count": 0,
        },
        "camera_readiness": rows,
    }


def main() -> int:
    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_raw_noise_promotion_", dir=tmp_parent) as td:
        root = Path(td)
        ready_path = root / "readiness.json"
        write_json(ready_path, readiness())
        args = type(
            "Args",
            (),
            {
                "readiness": ready_path,
                "output_dir": root / "pass",
                "expect_ready_camera": ["x2d", "z8"],
                "expect_blocked_camera": ["iphone", "mission1"],
                "require_promotion_safe": False,
            },
        )()
        passed = tool.build(args)
        assert passed["schema"] == "gpr.raw_stills_noise_promotion_gate.v1"
        assert passed["promotion_safe"] is True
        assert passed["production_ready"] is False
        assert passed["blockers"] == []
        assert "Mission/iPhone nonzero addback remains blocked" in passed["decision"]
        assert (root / "pass" / "index.html").read_text(encoding="utf-8").find("RAW Stills Noise Promotion Gate") >= 0

        bad = readiness()
        for row in bad["camera_readiness"]:
            if row["camera_key"] == "mission1":
                row["runtime_policy_declares_nonzero_noise_addback"] = True
                row["runtime_nonzero_noise_addback_enabled"] = True
        bad_path = root / "bad_readiness.json"
        write_json(bad_path, bad)
        args.readiness = bad_path
        args.output_dir = root / "fail"
        failed = tool.build(args)
        assert failed["promotion_safe"] is False
        assert any("mission1: nonzero noise addback is enabled while blocked" in item for item in failed["blockers"])
    print("test_check_raw_stills_noise_promotion_gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
