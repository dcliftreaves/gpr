#!/usr/bin/env python3
"""Regression test for the premium still-SR editor/latitude coverage audit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_editor_latitude_coverage.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_editor(root: Path, route: str) -> Path:
    editable_dng = root / f"artifacts/{route.replace(':', '_')}/candidate.dng"
    editable_gpr = root / f"artifacts/{route.replace(':', '_')}/candidate.gpr"
    editable_dng.parent.mkdir(parents=True, exist_ok=True)
    editable_dng.write_bytes(b"dng")
    editable_gpr.write_bytes(b"gpr")
    return write_json(
        root / f"artifacts/{route.replace(':', '_')}/editor_receipt.json",
        {
            "schema": "gpr.premium_still_sr_editor_receipt.v1",
            "route": route,
            "camera": route.split(":")[0],
            "source_frame": "frame0",
            "production_ready": False,
            "openability_pass": True,
            "blockers": ["receipt proves openability/export, not full raw-editor latitude"],
            "metadata_transplant": {"passed": True},
            "artifacts": {
                "editable_dng": {"path": "artifacts/" + editable_dng.relative_to(root / "artifacts").as_posix()},
                "editable_gpr": {"path": "artifacts/" + editable_gpr.relative_to(root / "artifacts").as_posix()},
            },
        },
    )


def write_latitude(root: Path, route: str) -> Path:
    source = root / f"artifacts/{route.replace(':', '_')}/source.dng"
    candidate = root / f"artifacts/{route.replace(':', '_')}/candidate.dng"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"source")
    candidate.write_bytes(b"candidate")
    return write_json(
        root / f"artifacts/{route.replace(':', '_')}/latitude_review.json",
        {
            "schema": "gpr.premium_still_sr_latitude_review.v1",
            "source_dng": str(source),
            "candidate_dng": str(candidate),
            "source_dng_sha256": "sourcehash",
            "candidate_dng_sha256": "candidatehash",
            "render": {
                "engine": "rawpy/libraw",
                "use_camera_wb": True,
                "oracle_hf_addback": False,
            },
            "summary": {
                "row_count": 9,
                "mae": {"median": 0.01, "max": 0.02},
                "y_mae": {"median": 0.01, "max": 0.02},
                "psnr_db": {"median": 40.0, "min": 35.0},
            },
        },
    )


def run_tool(root: Path, out: Path, routes: list[str], ready_routes: list[str]) -> dict:
    args = [
        sys.executable,
        str(TOOL),
        "--external-root",
        str(root),
        "--output-dir",
        str(out),
    ]
    for route in routes:
        args += ["--required-route", route]
    for route in ready_routes:
        args += ["--editor", f"{route}={write_editor(root, route)}"]
        args += ["--latitude", f"{route}={write_latitude(root, route)}"]
    subprocess.run(args, cwd=ROOT, check=True)
    return json.loads((out / "coverage.json").read_text(encoding="utf-8"))


def main() -> int:
    routes = ["mission1:50mp:dng", "mission1:50mp:gpr", "z8:50mp:dng", "x2d:100mp:dng"]
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_editor_cov_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        partial = run_tool(root, Path(tmp) / "partial", routes, ["x2d:100mp:dng"])
        assert partial["schema"] == "gpr.premium_still_sr_editor_latitude_coverage.v1"
        assert partial["ready_route_count"] == 1
        assert partial["ready_routes"] == ["x2d:100mp:dng"]
        assert partial["missing_routes"] == ["mission1:50mp:dng", "mission1:50mp:gpr", "z8:50mp:dng"]
        assert partial["openability_route_coverage_ready"] is False
        assert partial["latitude_route_coverage_ready"] is False
        assert partial["production_ready"] is False
        assert any("mission1:50mp:dng" in item for item in partial["blockers"])
        assert "Package Mission 1 DNG/GPR and Z8" in partial["next_unambiguous_steps"][0]
        assert "Premium Still SR Editor Latitude Coverage" in (Path(tmp) / "partial/index.html").read_text(
            encoding="utf-8"
        )

        complete = run_tool(root, Path(tmp) / "complete", routes, routes)
        assert complete["ready_route_count"] == 4
        assert complete["missing_routes"] == []
        assert complete["openability_route_coverage_ready"] is True
        assert complete["latitude_route_coverage_ready"] is True
        assert complete["production_ready"] is False
        assert complete["blockers"] == []
    print("test_build_premium_still_sr_editor_latitude_coverage: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
