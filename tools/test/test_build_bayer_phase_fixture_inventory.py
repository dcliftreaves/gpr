#!/usr/bin/env python3
"""Regression test for the Bayer phase fixture inventory builder."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_bayer_phase_fixture_inventory.py"
sys.path.insert(0, str(ROOT / "tools"))
import build_bayer_phase_fixture_inventory as inventory  # noqa: E402


def main() -> int:
    assert inventory.parse_exif_cfa({"CFAPattern": "2 2 0 1 1 2"}) == "RGGB"
    assert inventory.parse_exif_cfa({"CFAPattern": "2 2 0 1 1 2", "CFAPlaneColor": "0 1 2"}) == "RGGB"
    assert inventory.parse_exif_cfa({"CFAPattern": [2, 2, 1, 0, 2, 1]}) == "GRBG"
    with tempfile.TemporaryDirectory(prefix="gpr_bayer_phase_inventory_") as td:
        out_dir = Path(td) / "inventory"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--synthetic",
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
        data = json.loads((out_dir / "inventory.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.bayer_phase_fixture_inventory.v1"
        assert data["mode"] == "synthetic"
        assert data["summary"]["files_seen"] == 5
        assert data["summary"]["parsed_count"] == 4
        assert data["summary"]["normal_bayer_phases_present"] == ["RGGB", "GBRG", "GRBG", "BGGR"]
        assert data["summary"]["normal_bayer_phases_missing"] == []
        assert data["summary"]["all_normal_phases_have_fixture"] is True
        assert data["summary"]["production_real_phase_coverage"] is False
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "Bayer Phase Fixture Inventory" in html
        assert "RGGB" in html
        assert "linear RGB negative fixture" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_bayer_phase_fixture_inventory: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
