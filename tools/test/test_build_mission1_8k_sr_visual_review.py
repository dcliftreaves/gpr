#!/usr/bin/env python3
"""Smoke tests for the Mission 1 8K SR visual-review package builder."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_8k_sr_visual_review.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("build_mission1_8k_sr_visual_review", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_contact(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 72), color).save(path, quality=88)


def summary(root: Path, family: str, count: int, image: str, color: tuple[int, int, int]) -> dict:
    contact = root / family / image / f"{image}_fullframe_contact.jpg"
    write_contact(contact, color)
    row = {
        "image": image,
        "bench_json": str(root / family / image / f"{image}_bench.json"),
        "compare_json": str(root / family / image / f"{image}_compare.json"),
        "contact_sheet": str(contact),
        "fps_with_write": 1.0,
        "total_with_write_s": 1.0,
        "inference_plus_copy_s": 0.9,
        "write_output_s": 0.1,
        "rmse_improvement_pct": 12.0,
        "mae_improvement_pct": 8.0,
        "gradient_mae_improvement_pct": 3.0,
        "baseline_psnr14_db": 48.0,
        "model_psnr14_db": 54.0,
        "baseline_rmse": 42.0,
        "model_rmse": 24.0,
    }
    return {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": count,
        "rmse_improvement_pct": {"min": 12.0, "median": 13.0, "max": 14.0, "mean": 13.0},
        "mae_improvement_pct": {"min": 8.0, "median": 9.0, "max": 10.0, "mean": 9.0},
        "gradient_mae_improvement_pct": {"min": 3.0, "median": 4.0, "max": 5.0, "mean": 4.0},
        "model_psnr14_db": {"min": 54.0, "median": 55.0, "max": 56.0, "mean": 55.0},
        "worst_by_rmse_improvement": row,
        "worst_by_mae_improvement": row,
        "worst_by_gradient_improvement": row,
        "images": [row],
    }


def create_fixture(root: Path) -> Path:
    sr_base = root / "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600"
    mission_dir = sr_base / "mission42_broad_fullframe"
    z8_dir = sr_base / "z8_all24_fullframe"
    write_json(mission_dir / "summary.json", summary(mission_dir, "mission42", 42, "GP017346", (88, 92, 96)))
    write_json(z8_dir / "summary.json", summary(z8_dir, "z8", 24, "Z8Z_1330", (72, 86, 94)))
    (mission_dir / "index.html").write_text("<html>Mission</html>", encoding="utf-8")
    (z8_dir / "index.html").write_text("<html>Z8</html>", encoding="utf-8")
    return sr_base


def test_build_visual_review_package() -> None:
    tool = load_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_8k_visual_review_", dir=work_parent) as td:
        root = Path(td)
        sr_base = create_fixture(root)
        out = root / "artifacts/mission1_8k_sr_visual_review_20260625"
        args = argparse.Namespace(external_root=root, sr_base=sr_base, output_dir=out)
        report = tool.build(args)
        tool.write_html(out / "index.html", report)
        write_json(out / "visual_review.json", report)
        assert report["schema"] == tool.SCHEMA
        assert report["verdict"] == "objective_visual_metrics_pass_manual_review_required"
        assert report["production_ready"] is False
        assert report["manual_visual_review_required"] is True
        assert all(check["passed"] for check in report["checks"])
        assert len(report["selected_rows"]) == 2
        assert (out / "visual_review_contact_sheet.jpg").is_file()
        assert "Mission 1 8K SR Visual Review" in (out / "index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    test_build_visual_review_package()
    print("test_build_mission1_8k_sr_visual_review: PASS")
