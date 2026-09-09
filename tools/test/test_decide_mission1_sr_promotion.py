#!/usr/bin/env python3
"""Regression-test Mission 1 SR promotion decisions."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/cnn/decide_mission1_sr_promotion.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("decide_mission1_sr_promotion_test", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summary(
    *,
    rmse_min: float,
    rmse_median: float,
    psnr_min: float,
    image: str = "worst",
    rows: list[tuple[str, float, float]] | None = None,
) -> dict:
    payload = {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "dashboard": "index.html",
        "image_count": len(rows) if rows else 8,
        "fps_with_write": {"median": 2.7},
        "rmse_improvement_pct": {"min": rmse_min, "median": rmse_median},
        "mae_improvement_pct": {"min": 22.0, "median": 30.0},
        "gradient_mae_improvement_pct": {"min": 8.5, "median": 15.0},
        "model_psnr14_db": {"min": psnr_min, "median": 55.0},
        "worst_by_rmse_improvement": {"image": image},
    }
    if rows:
        payload["images"] = [
            {
                "image": row_image,
                "rmse_improvement_pct": row_rmse,
                "model_psnr14_db": row_psnr,
            }
            for row_image, row_rmse, row_psnr in rows
        ]
    return payload


def args_for(root: Path, candidate: str) -> Namespace:
    ckpt = root / f"{candidate}.pt"
    receipt = root / f"{candidate}.pt.json"
    ckpt.write_bytes(b"checkpoint")
    write_json(receipt, {"schema": "mission1_sr_train_receipt.v1"})
    return Namespace(
        checkpoint=ckpt,
        training_receipt=receipt,
        description=f"{candidate} candidate",
        candidate_mission_summary=root / f"{candidate}_mission.json",
        candidate_z8_summary=root / f"{candidate}_z8.json",
        baseline_label="guardrail_light",
        baseline_mission_summary=root / "baseline_mission.json",
        baseline_z8_summary=root / "baseline_z8.json",
    )


def main() -> int:
    tool = import_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sr_decision_", dir=work_parent) as td:
        root = Path(td)
        write_json(root / "baseline_mission.json", summary(rmse_min=37.3, rmse_median=49.7, psnr_min=48.0))
        write_json(root / "baseline_z8.json", summary(rmse_min=25.7, rmse_median=28.2, psnr_min=51.2))

        write_json(root / "bad_mission.json", summary(rmse_min=35.3, rmse_median=48.0, psnr_min=47.8))
        write_json(root / "bad_z8.json", summary(rmse_min=23.9, rmse_median=26.5, psnr_min=51.0))
        rejected = tool.build_decision(args_for(root, "bad"))
        assert rejected["schema"] == tool.SCHEMA
        assert rejected["decision"] == "reject_do_not_register"
        assert rejected["deltas_vs_guardrail_light"]["mission_rmse_min"] < 0.0
        assert rejected["deltas_vs_guardrail_light"]["z8_rmse_min"] < 0.0
        assert "not focus-only continuation" in rejected["next_experiment"]

        write_json(root / "good_mission.json", summary(rmse_min=38.1, rmse_median=50.2, psnr_min=48.1))
        write_json(root / "good_z8.json", summary(rmse_min=25.8, rmse_median=28.4, psnr_min=51.2))
        promoted = tool.build_decision(args_for(root, "good"))
        assert promoted["decision"] == "promote_for_registry_review"
        assert promoted["deltas_vs_guardrail_light"]["mission_rmse_min"] > 0.0
        assert promoted["deltas_vs_guardrail_light"]["z8_rmse_min"] >= 0.0

        rows = [("a", 37.0, 48.0), ("b", 49.0, 55.0), ("c", 52.0, 56.0)]
        write_json(
            root / "baseline_mission.json",
            summary(rmse_min=37.0, rmse_median=49.0, psnr_min=48.0, rows=rows),
        )
        write_json(
            root / "baseline_z8.json",
            summary(rmse_min=25.0, rmse_median=26.0, psnr_min=51.0, rows=[("z1", 25.0, 51.0), ("z2", 27.0, 52.0)]),
        )
        write_json(
            root / "subset_mission.json",
            summary(rmse_min=40.0, rmse_median=53.0, psnr_min=49.0, rows=[("a", 40.0, 49.0), ("b", 53.0, 55.5)]),
        )
        write_json(
            root / "subset_z8.json",
            summary(rmse_min=26.0, rmse_median=28.0, psnr_min=51.2, rows=[("z1", 26.0, 51.2), ("z2", 28.0, 52.2)]),
        )
        subset = tool.build_decision(args_for(root, "subset"))
        assert subset["decision"] == "reject_do_not_register"
        assert subset["comparison_scope"]["mission"]["mode"] == "paired_image_rows"
        assert subset["comparison_scope"]["mission"]["missing_baseline_images"] == ["c"]
        assert subset["deltas_vs_guardrail_light"]["mission_rmse_min"] > 0.0
        assert "does not cover the full baseline Mission+Z8 holdout" in subset["reason"]

    print("test_decide_mission1_sr_promotion: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
