#!/usr/bin/env python3
"""Smoke tests for the Mission 1 4K cleanup visual signoff builder."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_mission1_4k_visual_signoff.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("build_mission1_4k_visual_signoff", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path)


def create_fixture(root: Path) -> tuple[Path, Path]:
    rgb_summary = root / "rgb/summary.json"
    tone_summary = root / "tone/summary.json"
    crop_dir = root / "rgb/crops"
    rows = []
    for i in range(20):
        stem = f"GP{i:06d}"
        for crop in ("center", "upper_left", "lower_right"):
            stem_crop = f"{stem}_{crop}"
            target = crop_dir / f"{stem_crop}_target_rgb4_from_high.png"
            baseline = crop_dir / f"{stem_crop}_baseline_rgb4.png"
            candidate = crop_dir / f"{stem_crop}_candidate_rgb4.png"
            write_image(target, (80 + i, 80, 80))
            write_image(baseline, (82 + i, 79, 79))
            write_image(candidate, (81 + i, 80, 80))
            delta = 0.02 if i == 0 and crop == "center" else -0.1
            rows.append(
                {
                    "stem_crop": stem_crop,
                    "stem": stem,
                    "crop": crop,
                    "target_png": str(target),
                    "baseline_png": str(baseline),
                    "candidate_png": str(candidate),
                    "candidate_display_mae": 2.0 + i * 0.1,
                    "candidate_minus_baseline_mae_delta": delta,
                    "candidate_green_delta_vs_target": 0.002,
                    "baseline_green_delta_vs_target": 0.004,
                }
            )
    write_json(
        rgb_summary,
        {
            "summary": {
                "rgb_rmse_improvement_pct": {"min": 1.0},
                "cfa_raw_rmse_improvement_pct": {"min": 1.0},
                "y_gradient_improvement_pct": {"min": 1.0},
            }
        },
    )
    write_json(
        tone_summary,
        {
            "summary": {
                "row_count": len(rows),
                "candidate_better_display_mae_count": len(rows) - 1,
                "candidate_worse_display_mae_count": 1,
                "candidate_green_delta_vs_target": {"abs_p95": 0.002},
                "baseline_green_delta_vs_target": {"abs_p95": 0.004},
                "max_abs_candidate_green_delta": 0.002,
            },
            "rows": rows,
        },
    )
    return rgb_summary, tone_summary


def test_report_requires_manual_signoff() -> None:
    tool = load_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_4k_signoff_", dir=work_parent) as td:
        root = Path(td)
        rgb_summary, tone_summary = create_fixture(root)
        out = root / "out"
        out.mkdir()
        report = tool.build_report(rgb_summary, tone_summary, out, max_rows=8)
        html_path = out / "index.html"
        tool.write_html(html_path, report)
        assert report["verdict"] == "objective_visual_metrics_pass_manual_signoff_required"
        assert report["production_ready"] is False
        assert report["manual_visual_signoff"] is False
        assert report["manual_visual_signoff_required"] is True
        assert Path(report["contact_sheet"]).is_file()
        html = html_path.read_text(encoding="utf-8")
        assert "Production Signoff Commands" in html
        assert "build_mission1_4k_cleanup_signoff_receipt.py" in html
        assert "check_mission1_4k_cleanup_signoff_receipt.py" in html


if __name__ == "__main__":
    test_report_requires_manual_signoff()
    print("test_build_mission1_4k_visual_signoff: PASS")
