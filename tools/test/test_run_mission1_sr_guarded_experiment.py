#!/usr/bin/env python3
"""Smoke-test guarded Mission 1 SR experiment command construction."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/cnn/run_mission1_sr_guarded_experiment.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("run_mission1_sr_guarded_experiment_test", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def args(root: Path) -> Namespace:
    return Namespace(
        python=Path("/usr/bin/python3"),
        repo=ROOT,
        pairs=root / "pairs.npz",
        out_root=root / "out",
        experiment_id="exp",
        description="guarded experiment",
        init_checkpoint=root / "init.pt",
        holdout_image="GP017604,Z8Z_1349",
        focus_image="GP017346",
        focus_weight=2.0,
        steps=400,
        batch=4,
        width=48,
        depth=6,
        architecture="coord_preclean_adapter_pixelshuffle",
        init_nonstrict=True,
        init_expand_lowres=False,
        lr=1e-4,
        residual_scale=0.3,
        gradient_weight=0.2,
        laplacian_weight=0.1,
        detail_phase_weight=0.4,
        detail_phase_threshold=2.0,
        plane_weights="1.6,1.4,1.2,1.0",
        trainable_scope="adapter_and_preclean",
        low_clean_aux_weight=0.03,
        low_clean_detail_aux_weight=0.15,
        low_clean_detail_threshold=2.0,
        loss="charbonnier",
        seed=20260618,
        eval_every=200,
        mission_low_dir=root / "mission_low",
        mission_target_dir=root / "mission_target",
        mission_stem=["GP017346"],
        mission_low_width=4096,
        mission_low_height=3072,
        z8_low_dir=root / "z8_low",
        z8_target_dir=root / "z8_target",
        z8_stem=["Z8Z_1349"],
        z8_low_width=4140,
        z8_low_height=2760,
        baseline_label="guardrail_light",
        baseline_mission_summary=root / "baseline_mission.json",
        baseline_z8_summary=root / "baseline_z8.json",
        tile=512,
        overlap=64,
        device="mps",
        force_eval=True,
        dry_run=True,
    )


def main() -> int:
    tool = import_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="guarded_sr_cmd_", dir=work_parent) as td:
        root = Path(td)
        a = args(root)
        train = tool.train_command(a, root / "out/eval_checkpoints")
        assert "tools/cnn/train_mission1_sr.py" in train
        assert "--save-eval-checkpoints-dir" in train
        assert "--focus-image" in train
        assert "--init-checkpoint" in train
        assert "--init-nonstrict" in train
        assert "--init-expand-lowres" not in train
        assert "--laplacian-weight" in train
        assert train[train.index("--laplacian-weight") + 1] == "0.1"
        assert "--detail-phase-weight" in train
        assert train[train.index("--detail-phase-weight") + 1] == "0.4"
        assert "--detail-phase-threshold" in train
        assert train[train.index("--detail-phase-threshold") + 1] == "2.0"
        assert "--plane-weights" in train
        assert train[train.index("--plane-weights") + 1] == "1.6,1.4,1.2,1.0"
        assert "--trainable-scope" in train
        assert train[train.index("--trainable-scope") + 1] == "adapter_and_preclean"
        assert "--low-clean-aux-weight" in train
        assert train[train.index("--low-clean-aux-weight") + 1] == "0.03"
        assert "--low-clean-detail-aux-weight" in train
        assert train[train.index("--low-clean-detail-aux-weight") + 1] == "0.15"
        assert "--low-clean-detail-threshold" in train
        assert train[train.index("--low-clean-detail-threshold") + 1] == "2.0"
        assert train[train.index("--loss") + 1] == "charbonnier"

        ckpt = root / "out/eval_checkpoints/exp_step000200.pt"
        mission = tool.fullframe_eval_command(
            a,
            ckpt,
            "mission",
            a.mission_low_dir,
            a.mission_target_dir,
            a.mission_stem,
            a.mission_low_width,
            a.mission_low_height,
        )
        assert "tools/cnn/run_mission1_sr_fullframe_broad_eval.py" in mission
        assert mission.count("--stem") == 1
        assert mission[mission.index("--low-width") + 1] == "4096"
        assert "--force" in mission

        z8 = tool.fullframe_eval_command(
            a,
            ckpt,
            "z8",
            a.z8_low_dir,
            a.z8_target_dir,
            a.z8_stem,
            a.z8_low_width,
            a.z8_low_height,
        )
        assert z8[z8.index("--low-width") + 1] == "4140"
        assert z8[z8.index("--low-height") + 1] == "2760"

        decision = tool.decision_command(a, ckpt, root / "mission/summary.json", root / "z8/summary.json")
        assert "tools/cnn/decide_mission1_sr_promotion.py" in decision
        assert "--baseline-mission-summary" in decision
        assert str(root / "out/exp_step000200_decision.json") in decision

        planned = tool.planned_eval_checkpoints(a, root / "out/eval_checkpoints")
        assert [p.name for p in planned] == ["exp_step000001.pt", "exp_step000200.pt", "exp_step000400.pt"]

    print("test_run_mission1_sr_guarded_experiment: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
