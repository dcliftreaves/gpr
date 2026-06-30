#!/usr/bin/env python3
"""Regression test for the four-pillar production burn-down builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_product_burndown.py"


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
    with tempfile.TemporaryDirectory(prefix="gpr_product_burndown_", dir=temp_root()) as tmp:
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

        data = json.loads((out_dir / "product_burndown.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.product_burndown.v1"
        assert data["four_pillar_completion_percent"] == 69
        assert data["production_ready"] is False
        assert data["summary"]["action_count"] == 6
        assert data["summary"]["camera_required_action_count"] == 1
        assert data["summary"]["non_camera_action_count"] == 5
        assert data["summary"]["lowest_readiness_pillar"] == "raw_video_psf_sr"
        assert [row["id"] for row in data["pillars"]] == [
            "raw_stills",
            "raw_video_mvp",
            "premium_still_sr",
            "raw_video_psf_sr",
        ]
        stills_actions = data["pillars"][0]["burn_down_actions"]
        assert any("GRBG" in " ".join(row["evidence_required"]) for row in stills_actions)
        assert any("darkframe" in row["title"].lower() for row in stills_actions)
        video_actions = data["pillars"][1]["burn_down_actions"]
        assert video_actions[0]["can_do_without_camera"] is False
        psf_actions = data["pillars"][3]["burn_down_actions"]
        assert any("PSF-conditioned" in row["title"] for row in psf_actions)

        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "GPR Production Burn-Down" in html
        assert "four-pillar completion" in html
        assert "No camera?" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_product_burndown: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
