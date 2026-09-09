#!/usr/bin/env python3
"""Regression-test Mission 1 SR full-frame gate candidate selection."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/cnn/select_mission1_sr_gate_candidate.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("select_mission1_sr_gate_candidate_test", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summary(rows: list[tuple[str, float, float, float, float]]) -> dict:
    rmse = [row[1] for row in rows]
    mae = [row[2] for row in rows]
    grad = [row[3] for row in rows]
    psnr = [row[4] for row in rows]
    return {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "dashboard": "index.html",
        "image_count": len(rows),
        "fps_with_write": {"median": 2.7},
        "rmse_improvement_pct": {"min": min(rmse), "median": sorted(rmse)[len(rmse) // 2]},
        "mae_improvement_pct": {"min": min(mae), "median": sorted(mae)[len(mae) // 2]},
        "gradient_mae_improvement_pct": {"min": min(grad), "median": sorted(grad)[len(grad) // 2]},
        "model_psnr14_db": {"min": min(psnr), "median": sorted(psnr)[len(psnr) // 2]},
        "images": [
            {
                "image": image,
                "rmse_improvement_pct": row_rmse,
                "mae_improvement_pct": row_mae,
                "gradient_mae_improvement_pct": row_grad,
                "model_psnr14_db": row_psnr,
            }
            for image, row_rmse, row_mae, row_grad, row_psnr in rows
        ],
    }


def spec_for(tool, root: Path, label: str) -> object:
    checkpoint = root / f"{label}.pt"
    checkpoint.write_bytes(label.encode("utf-8"))
    return tool.CandidateSpec(
        label=label,
        checkpoint=checkpoint,
        mission_summary=root / f"{label}_mission.json",
        z8_summary=root / f"{label}_z8.json",
        training_receipt=None,
    )


def args(root: Path, candidates: list[object]) -> Namespace:
    return Namespace(
        baseline_label="baseline",
        baseline_mission_summary=root / "baseline_mission.json",
        baseline_z8_summary=root / "baseline_z8.json",
        candidate=candidates,
        rmse_floor=30.0,
        mae_floor=20.0,
        gradient_floor=8.0,
        psnr14_floor=45.0,
        z8_epsilon=0.0,
    )


def main() -> int:
    tool = import_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sr_gate_select_", dir=work_parent) as td:
        root = Path(td)
        write_json(root / "baseline_mission.json", summary([("a", 40, 25, 10, 50), ("b", 45, 30, 12, 52)]))
        write_json(root / "baseline_z8.json", summary([("z1", 44, 7, 2.4, 54), ("z2", 45, 7, 2.5, 54.2)]))

        write_json(root / "good_mission.json", summary([("a", 41, 25, 10, 50), ("b", 45, 30, 12, 52)]))
        write_json(root / "good_z8.json", summary([("z1", 44.5, 7, 2.4, 54.1), ("z2", 45.2, 7, 2.5, 54.3)]))

        write_json(root / "bad_detail_mission.json", summary([("a", 41, 19, 7.5, 50), ("b", 46, 30, 12, 52)]))
        write_json(root / "bad_detail_z8.json", summary([("z1", 44.5, 7, 2.4, 54.1), ("z2", 45.2, 7, 2.5, 54.3)]))

        write_json(root / "missing_mission.json", summary([("a", 50, 30, 12, 52)]))
        write_json(root / "missing_z8.json", summary([("z1", 44.5, 7, 2.4, 54.1), ("z2", 45.2, 7, 2.5, 54.3)]))

        good = spec_for(tool, root, "good")
        bad_detail = spec_for(tool, root, "bad_detail")
        missing = spec_for(tool, root, "missing")
        selection = tool.build_selection(args(root, [bad_detail, missing, good]))
        assert selection["schema"] == tool.SCHEMA
        assert selection["decision"] == "promote_for_registry_review"
        assert selection["best_label"] == "good"
        by_label = {row["label"]: row for row in selection["candidates"]}
        assert by_label["good"]["promoted"] is True
        assert by_label["bad_detail"]["promoted"] is False
        assert by_label["bad_detail"]["mission_failures"][0]["image"] == "a"
        assert any("gradient" in reason for reason in by_label["bad_detail"]["mission_failures"][0]["reasons"])
        assert by_label["missing"]["coverage"]["missing_images"] == ["b"]

        only_bad = tool.build_selection(args(root, [bad_detail]))
        assert only_bad["decision"] == "reject_do_not_register"
        assert only_bad["best_label"] == "bad_detail"

    print("test_select_mission1_sr_gate_candidate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
