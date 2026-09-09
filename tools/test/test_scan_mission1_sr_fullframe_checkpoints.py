#!/usr/bin/env python3
"""Regression-test Mission 1 SR full-frame checkpoint scanning decisions."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/cnn/scan_mission1_sr_fullframe_checkpoints.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("scan_mission1_sr_fullframe_checkpoints_test", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summary(rows: list[tuple[str, float, float, float, float]]) -> dict:
    return {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "dashboard": "index.html",
        "image_count": len(rows),
        "images": [
            {
                "image": image,
                "fps_with_write": 1.2,
                "rmse_improvement_pct": rmse,
                "mae_improvement_pct": mae,
                "gradient_mae_improvement_pct": grad,
                "model_psnr14_db": psnr,
            }
            for image, rmse, mae, grad, psnr in rows
        ],
    }


def main() -> int:
    tool = import_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sr_fullframe_scan_", dir=work_parent) as td:
        root = Path(td)
        write_json(root / "seed.json", summary([("a", 29.4, 18.0, 5.1, 53.5), ("b", 61.0, 24.0, 7.1, 59.0)]))
        write_json(root / "better.json", summary([("a", 30.5, 20.2, 8.2, 53.6), ("b", 62.0, 24.5, 8.1, 59.1)]))
        write_json(root / "worse.json", summary([("a", 28.0, 17.0, 4.5, 53.0), ("b", 60.0, 24.0, 7.0, 59.0)]))
        specs = [
            tool.CheckpointSpec("seed", None, root / "seed.json"),
            tool.CheckpointSpec("better", None, root / "better.json"),
            tool.CheckpointSpec("worse", None, root / "worse.json"),
        ]
        decision = tool.build_decision(
            specs=specs,
            summaries={spec.label: spec.summary for spec in specs if spec.summary is not None},
            baseline_label="seed",
            floors=tool.Floors(rmse=30.0, mae=20.0, gradient=8.0, psnr14=45.0),
        )
        assert decision["schema"] == tool.SCHEMA
        assert decision["decision"] == "promote_for_registry_review"
        assert decision["promoted_labels"] == ["better"]
        by_label = {row["label"]: row for row in decision["candidates"]}
        assert by_label["better"]["promoted"] is True
        assert by_label["seed"]["promoted"] is False
        assert by_label["seed"]["margins"]["gradient_floor"] < 0.0
        assert by_label["worse"]["margins"]["rmse_vs_baseline"] < 0.0

        reject = tool.build_decision(
            specs=[specs[0], specs[2]],
            summaries={"seed": root / "seed.json", "worse": root / "worse.json"},
            baseline_label="seed",
            floors=tool.Floors(rmse=30.0, mae=20.0, gradient=8.0, psnr14=45.0),
        )
        assert reject["decision"] == "reject_do_not_register"
        assert reject["best_label"] == "seed"

    print("test_scan_mission1_sr_fullframe_checkpoints: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
