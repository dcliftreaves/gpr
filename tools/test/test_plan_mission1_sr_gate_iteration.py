#!/usr/bin/env python3
"""Regression-test Mission 1 SR gate-driven iteration planning."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/cnn/plan_mission1_sr_gate_iteration.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("plan_mission1_sr_gate_iteration_test", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def args(root: Path) -> Namespace:
    return Namespace(
        scan_decision=root / "scan.json",
        out=root / "plan.json",
        candidate_label=None,
        repo=ROOT,
        python=Path("/usr/bin/python3"),
        pairs=root / "pairs.npz",
        out_root=root / "out",
        experiment_id="gate_iter",
        description="gate iteration",
        init_checkpoint=None,
        architecture="coord_preclean_adapter_pixelshuffle",
        init_nonstrict=True,
        steps=600,
        batch=4,
        width=96,
        depth=6,
        lr=None,
        residual_scale=0.3,
        gradient_weight=None,
        laplacian_weight=None,
        detail_phase_weight=0.25,
        detail_phase_threshold=2.0,
        plane_weights=None,
        trainable_scope=None,
        low_clean_aux_weight=None,
        low_clean_detail_aux_weight=None,
        low_clean_detail_threshold=None,
        loss="charbonnier",
        seed=20260619,
        eval_every=200,
        focus_weight=None,
        mission_low_dir=root / "mission_low",
        mission_target_dir=root / "mission_target",
        mission_stem=["GP017346", "GP017349", "GP017600"],
        z8_low_dir=root / "z8_low",
        z8_target_dir=root / "z8_target",
        z8_stem=["Z8Z_1349"],
        baseline_label="guardrail_light",
        baseline_mission_summary=root / "baseline_mission.json",
        baseline_z8_summary=root / "baseline_z8.json",
        tile=512,
        overlap=64,
        device="mps",
        force_eval=True,
        stop_on_promote=True,
        dry_run=True,
    )


def main() -> int:
    tool = import_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sr_gate_iteration_", dir=work_parent) as td:
        root = Path(td)
        scan = {
            "schema": "gpr.mission1_sr_fullframe_checkpoint_scan.v1",
            "decision": "reject_do_not_register",
            "best_label": "step0800",
            "thresholds": {
                "rmse_floor": 30.0,
                "mae_floor": 20.0,
                "gradient_floor": 8.0,
                "psnr14_floor": 45.0,
            },
            "candidates": [
                {
                    "label": "step0800",
                    "checkpoint": str(root / "step0800.pt"),
                    "summary": str(root / "summary.json"),
                    "failures": [
                        {
                            "image": "GP017346",
                            "metrics": {"rmse": 60.0, "mae": 18.2, "gradient": 5.2, "psnr14": 53.5},
                            "reasons": ["mae 18.200 < 20.000", "gradient 5.200 < 8.000"],
                        },
                        {
                            "image": "GP017349",
                            "metrics": {"rmse": 29.4, "mae": 30.0, "gradient": 8.5, "psnr14": 54.0},
                            "reasons": ["rmse 29.400 < 30.000"],
                        },
                        {
                            "image": "GP017600",
                            "metrics": {"rmse": 80.0, "mae": 42.0, "gradient": 7.3, "psnr14": 57.0},
                            "reasons": ["gradient 7.300 < 8.000"],
                        },
                    ],
                }
            ],
        }
        write_json(root / "scan.json", scan)
        a = args(root)
        plan = tool.build_plan(a)
        assert plan["schema"] == tool.SCHEMA
        assert plan["decision"] == "run_guarded_iteration"
        assert plan["dominant_blocker"] == "gradient"
        assert plan["focus_images"] == ["GP017346", "GP017349", "GP017600"]
        recipe = plan["recipe"]
        assert recipe["gradient_weight"] == 14.0
        assert recipe["laplacian_weight"] == 0.2
        assert recipe["detail_phase_weight"] == 0.25
        assert recipe["detail_phase_threshold"] == 2.0
        assert recipe["low_clean_aux_weight"] == 0.03
        assert recipe["low_clean_detail_aux_weight"] == 0.15
        assert recipe["low_clean_detail_threshold"] == 2.0
        assert recipe["trainable_scope"] == "adapter_and_preclean"
        assert recipe["plane_weights"] == "1.6,1.4,1.2,1.0"
        assert recipe["init_checkpoint"].endswith("step0800.pt")
        command = plan["guarded_command"]
        assert command is not None
        assert "tools/cnn/run_mission1_sr_guarded_experiment.py" in command
        assert "--dry-run" in command
        assert "--stop-on-promote" in command
        assert "--detail-phase-weight" in command
        assert command[command.index("--detail-phase-weight") + 1] == "0.25"
        assert "--low-clean-detail-aux-weight" in command
        assert command[command.index("--low-clean-detail-aux-weight") + 1] == "0.15"
        assert command[command.index("--focus-image") + 1] == "GP017346,GP017349,GP017600"

    print("test_plan_mission1_sr_gate_iteration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
