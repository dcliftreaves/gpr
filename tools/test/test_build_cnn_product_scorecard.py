#!/usr/bin/env python3
"""Regression test for the CNN/product scorecard builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_cnn_product_scorecard.py"


def main() -> int:
    external = Path(os.environ.get("GPR_EXTERNAL_ROOT", "/Volumes/OWC_8TB/gpr_work"))
    if not (external / "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json").is_file():
        print("test_build_cnn_product_scorecard: SKIP missing external CNN artifacts")
        return 0
    out_dir = external / "tmp/test_cnn_product_scorecard"
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--external-root", str(external), "--output-dir", str(out_dir)],
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
    assert data["schema"] == "gpr.cnn_product_scorecard.v1"
    assert data["fourk_cleanup"]["visual_signoff_passed"] is True
    assert data["fourk_cleanup"]["image_count"] == 42
    assert data["eightk_sr"]["production_ready"] is True
    assert data["eightk_sr"]["mission42"]["image_count"] == 42
    assert data["eightk_sr"]["z8_all24"]["image_count"] == 24
    review = data["eightk_sr"]["continuous_review"]
    assert review["available"] is True
    assert review["schema"] == "gpr.z8_continuous_8k_no_cnn_vs_cnn_scene_video.v1"
    assert review["frames"] == 24
    assert review["width"] == 8280
    assert review["height"] == 5520
    assert review["fps"] == 20
    assert "true_no_cnn" in review["true_no_cnn"]["path"]
    assert "with_4k_cleanup_and_8k_sr_cnn" in review["with_cnn"]["path"]
    assert data["compatibility"]["pass_count"] >= 7
    html = dashboard.read_text(encoding="utf-8")
    assert "GPR CNN Product Scorecard" in html
    assert "4K cleanup" in html
    assert "8K SR" in html
    assert "Continuous 8K No-CNN vs CNN Review" in html
    assert "no-CNN 4140 x 2760 Z8 raw Bayer" in html
    assert "retained 4K cleanup CNN Bayer plus approved 8K SR CNN" in html
    assert f'file://{external}/artifacts/' in html
    print("test_build_cnn_product_scorecard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
