#!/usr/bin/env python3
"""Regression test for the four-pillar product scorecard builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_product_pillar_scorecard.py"


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
    with tempfile.TemporaryDirectory(prefix="gpr_product_pillar_scorecard_", dir=temp_root()) as tmp:
        external = Path(tmp) / "external"
        out_dir = Path(tmp) / "out"
        external.mkdir()
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(external),
                "--output-dir",
                str(out_dir),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        summary = out_dir / "scorecard.json"
        dashboard = out_dir / "index.html"
        data = json.loads(summary.read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.product_pillar_scorecard.v1"
        assert data["production_ready"] is False
        assert data["four_pillar_completion_percent"] == 67
        assert [p["id"] for p in data["pillars"]] == [
            "raw_stills",
            "raw_video_mvp",
            "premium_still_sr",
            "raw_video_psf_sr",
        ]
        assert data["pillars"][0]["readiness_percent"] == 90
        assert data["pillars"][1]["readiness_percent"] == 80
        assert data["pillars"][2]["readiness_percent"] == 52
        assert data["pillars"][3]["readiness_percent"] == 44
        assert any(ref["exists"] for ref in data["pillars"][0]["evidence"] if ref["kind"] == "repo")
        assert any(not ref["exists"] for p in data["pillars"] for ref in p["evidence"] if ref["kind"] == "artifact")

        html = dashboard.read_text(encoding="utf-8")
        assert "GPR Product Pillar Scorecard" in html
        assert "Best RAW stills" in html
        assert "GoPro RAW video MVP" in html
        assert "production ready: false" in html
        assert proc.stdout.strip() == str(dashboard)
    print("test_build_product_pillar_scorecard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
