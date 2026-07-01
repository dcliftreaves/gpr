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
        assert data["four_pillar_completion_percent"] == 69
        assert data["score_semantics"]["kind"] == "readiness_burndown_estimate"
        assert data["score_semantics"]["not_a_quality_metric"] is True
        assert data["score_semantics"]["not_a_locked_artifact_regression_signal"] is True
        assert "four-pillar production suite" in data["score_semantics"]["denominator"]
        assert [p["id"] for p in data["pillars"]] == [
            "raw_stills",
            "raw_video_mvp",
            "premium_still_sr",
            "raw_video_psf_sr",
        ]
        assert data["pillars"][0]["readiness_percent"] == 92
        assert data["pillars"][0]["lock_ledger_paths"] == [
            "STILL smallest",
            "STILL primary",
            "STILL archival",
            "Broad real-camera Bayer phase coverage",
        ]
        assert "Broad real-camera Bayer phase coverage" not in data["pillars"][0]["open_production_gates"]
        assert any("X2D 100MP" in item for item in data["pillars"][0]["locked_artifacts"])
        assert any("RGGB/GBRG/GRBG/BGGR" in item for item in data["pillars"][0]["locked_artifacts"])
        assert any("3,000-file" in item for item in data["pillars"][0]["done_evidence"])
        assert data["pillars"][1]["readiness_percent"] == 80
        assert "VIDEO_FREEZE" in data["pillars"][1]["lock_ledger_paths"]
        assert "UPRESABLE editable raw" in data["pillars"][1]["lock_ledger_paths"]
        assert "Real Mission 1 camera-role raw-video closure" in data["pillars"][1]["open_production_gates"]
        assert any("20 fps" in item for item in data["pillars"][1]["locked_artifacts"])
        assert data["pillars"][2]["readiness_percent"] == 60
        assert "Premium still-SR promotion" in data["pillars"][2]["open_production_gates"]
        assert any("351-row" in item for item in data["pillars"][2]["locked_artifacts"])
        assert any("next-experiment contract" in item for item in data["pillars"][2]["done_evidence"])
        assert any(
            "premium_still_sr_next_experiment_contract_20260630/index.html" in ref["path"]
            for ref in data["pillars"][2]["evidence"]
        )
        assert data["pillars"][3]["readiness_percent"] == 44
        assert "PSF-aware raw-video replacement" in data["pillars"][3]["open_production_gates"]
        assert any("8K SR" in item for item in data["pillars"][3]["locked_artifacts"])
        assert any("continuous 8K no-CNN versus CNN" in item for item in data["pillars"][3]["locked_artifacts"])
        assert any("Standalone 8K ProRes A/B" in item for item in data["pillars"][3]["done_evidence"])
        assert any(
            "z8_continuous_8k_no_cnn_vs_cnn_20260630/receipt.json" in ref["path"]
            for ref in data["pillars"][3]["evidence"]
        )
        assert any(
            "mission1_8k_true_no_cnn_vs_cnn_20260630/receipt.json" in ref["path"]
            for ref in data["pillars"][3]["evidence"]
        )
        assert any(
            "mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/receipt.json" in ref["path"]
            for ref in data["pillars"][3]["evidence"]
        )
        assert any(ref["exists"] for ref in data["pillars"][0]["evidence"] if ref["kind"] == "repo")
        assert any(not ref["exists"] for p in data["pillars"] for ref in p["evidence"] if ref["kind"] == "artifact")

        html = dashboard.read_text(encoding="utf-8")
        assert "GPR Product Pillar Scorecard" in html
        assert "Best RAW stills" in html
        assert "GoPro RAW video MVP" in html
        assert "Lock ledger paths" in html
        assert "Open production gates" in html
        assert "Locked artifacts" in html
        assert "Readiness percentages are not quality metrics" in html
        assert "continuous 8K no-CNN versus CNN ProRes review media" in html
        assert "production ready: false" in html
        assert proc.stdout.strip() == str(dashboard)
    print("test_build_product_pillar_scorecard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
