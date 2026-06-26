#!/usr/bin/env python3
"""Train and promote Mission 1 SR only through Mission+Z8 full-frame guardrails.

This is the production-oriented loop for 12MP-to-8K CNN revisions. It trains a
candidate while saving every tile-eval checkpoint, runs each checkpoint through
full-frame Mission and regenerated Z8 holdouts, and then delegates the
promotion/rejection decision to `decide_mission1_sr_promotion.py`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], cwd: Path, dry_run: bool) -> None:
    print("+ " + " ".join(cmd), flush=True)
    if not dry_run:
        subprocess.run(cmd, cwd=cwd, check=True)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def checkpoint_stem(path: Path) -> str:
    return path.name.replace(".pt", "")


def eval_summary_dir(out_root: Path, checkpoint: Path, label: str) -> Path:
    return out_root / f"{checkpoint_stem(checkpoint)}_{label}_fullframe"


def train_command(args: argparse.Namespace, eval_dir: Path) -> list[str]:
    cmd = [
        str(args.python),
        "tools/cnn/train_mission1_sr.py",
        "--pairs",
        str(args.pairs),
        "--out",
        str(args.out_root / f"{args.experiment_id}.pt"),
        "--steps",
        str(args.steps),
        "--batch",
        str(args.batch),
        "--width",
        str(args.width),
        "--depth",
        str(args.depth),
        "--architecture",
        args.architecture,
        "--lr",
        str(args.lr),
        "--residual-scale",
        str(args.residual_scale),
        "--gradient-weight",
        str(args.gradient_weight),
        "--loss",
        args.loss,
        "--seed",
        str(args.seed),
        "--eval-every",
        str(args.eval_every),
        "--save-eval-checkpoints-dir",
        str(eval_dir),
    ]
    if args.holdout_image:
        cmd += ["--holdout-image", args.holdout_image]
    if args.focus_image:
        cmd += ["--focus-image", args.focus_image, "--focus-weight", str(args.focus_weight)]
    if args.init_checkpoint:
        cmd += ["--init-checkpoint", str(args.init_checkpoint)]
    if args.init_nonstrict:
        cmd.append("--init-nonstrict")
    if args.init_expand_lowres:
        cmd.append("--init-expand-lowres")
    if args.laplacian_weight:
        cmd += ["--laplacian-weight", str(args.laplacian_weight)]
    if args.detail_phase_weight:
        cmd += ["--detail-phase-weight", str(args.detail_phase_weight)]
        if args.detail_phase_threshold:
            cmd += ["--detail-phase-threshold", str(args.detail_phase_threshold)]
    if args.plane_weights:
        cmd += ["--plane-weights", args.plane_weights]
    if args.trainable_scope != "all":
        cmd += ["--trainable-scope", args.trainable_scope]
    if args.low_clean_aux_weight:
        cmd += ["--low-clean-aux-weight", str(args.low_clean_aux_weight)]
    if args.low_clean_detail_aux_weight:
        cmd += [
            "--low-clean-detail-aux-weight",
            str(args.low_clean_detail_aux_weight),
            "--low-clean-detail-threshold",
            str(args.low_clean_detail_threshold),
        ]
    return cmd


def fullframe_eval_command(
    args: argparse.Namespace,
    checkpoint: Path,
    label: str,
    low_dir: Path,
    target_dir: Path,
    stems: list[str],
    low_width: int,
    low_height: int,
) -> list[str]:
    cmd = [
        str(args.python),
        "tools/cnn/run_mission1_sr_fullframe_broad_eval.py",
        "--low-dir",
        str(low_dir),
        "--target-dir",
        str(target_dir),
        "--checkpoint",
        str(checkpoint),
        "--out-root",
        str(eval_summary_dir(args.out_root, checkpoint, label)),
        "--repo",
        str(args.repo),
        "--low-width",
        str(low_width),
        "--low-height",
        str(low_height),
        "--tile",
        str(args.tile),
        "--overlap",
        str(args.overlap),
        "--device",
        args.device,
    ]
    for stem in stems:
        cmd += ["--stem", stem]
    if args.force_eval:
        cmd.append("--force")
    return cmd


def decision_command(args: argparse.Namespace, checkpoint: Path, mission_summary: Path, z8_summary: Path) -> list[str]:
    train_receipt = args.out_root / f"{args.experiment_id}.pt.json"
    return [
        str(args.python),
        "tools/cnn/decide_mission1_sr_promotion.py",
        "--checkpoint",
        str(checkpoint),
        "--training-receipt",
        str(train_receipt),
        "--description",
        args.description,
        "--candidate-mission-summary",
        str(mission_summary),
        "--candidate-z8-summary",
        str(z8_summary),
        "--baseline-label",
        args.baseline_label,
        "--baseline-mission-summary",
        str(args.baseline_mission_summary),
        "--baseline-z8-summary",
        str(args.baseline_z8_summary),
        "--output",
        str(args.out_root / f"{checkpoint_stem(checkpoint)}_decision.json"),
    ]


def load_train_checkpoints(args: argparse.Namespace, eval_dir: Path) -> list[Path]:
    receipt = load_json(args.out_root / f"{args.experiment_id}.pt.json")
    rows = receipt.get("eval_checkpoints") or []
    checkpoints = [Path(row["checkpoint"]) for row in rows if isinstance(row, dict) and row.get("checkpoint")]
    best = args.out_root / f"{args.experiment_id}.pt"
    if best.exists() and best not in checkpoints:
        checkpoints.append(best)
    if not checkpoints and eval_dir.exists():
        checkpoints = sorted(eval_dir.glob("*.pt"))
    if not checkpoints:
        raise RuntimeError("no eval checkpoints produced")
    return checkpoints


def write_summary(out_root: Path, rows: list[dict[str, Any]]) -> Path:
    promoted = [row for row in rows if row.get("decision") == "promote_for_registry_review"]
    best = promoted[0] if promoted else None
    payload = {
        "schema": "mission1_sr_guarded_experiment.v1",
        "decision": "promotion_candidate_found" if best else "no_candidate_promoted",
        "selected": best,
        "candidates": rows,
        "candidate_count": len(rows),
    }
    path = out_root / "guarded_experiment_summary.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def planned_eval_checkpoints(args: argparse.Namespace, eval_dir: Path) -> list[Path]:
    steps = [1]
    steps.extend(range(args.eval_every, args.steps + 1, args.eval_every))
    if args.steps not in steps:
        steps.append(args.steps)
    out_stem = f"{args.experiment_id}.pt".replace(".pt", "")
    return [eval_dir / f"{out_stem}_step{step:06d}.pt" for step in sorted(set(steps))]


def dry_run_plan(args: argparse.Namespace, eval_dir: Path) -> Path:
    rows: list[dict[str, Any]] = []
    for checkpoint in planned_eval_checkpoints(args, eval_dir):
        mission_dir = eval_summary_dir(args.out_root, checkpoint, "mission")
        z8_dir = eval_summary_dir(args.out_root, checkpoint, "z8")
        mission_cmd = fullframe_eval_command(
            args,
            checkpoint,
            "mission",
            args.mission_low_dir,
            args.mission_target_dir,
            args.mission_stem,
            args.mission_low_width,
            args.mission_low_height,
        )
        z8_cmd = fullframe_eval_command(
            args,
            checkpoint,
            "z8",
            args.z8_low_dir,
            args.z8_target_dir,
            args.z8_stem,
            args.z8_low_width,
            args.z8_low_height,
        )
        decision_cmd = decision_command(args, checkpoint, mission_dir / "summary.json", z8_dir / "summary.json")
        print("+ " + " ".join(mission_cmd), flush=True)
        print("+ " + " ".join(z8_cmd), flush=True)
        print("+ " + " ".join(decision_cmd), flush=True)
        rows.append({
            "checkpoint": str(checkpoint),
            "mission_summary": str(mission_dir / "summary.json"),
            "z8_summary": str(z8_dir / "summary.json"),
            "decision_receipt": str(args.out_root / f"{checkpoint_stem(checkpoint)}_decision.json"),
            "decision": "dry_run",
        })
    payload = {
        "schema": "mission1_sr_guarded_experiment.v1",
        "decision": "dry_run",
        "candidate_count": len(rows),
        "candidates": rows,
    }
    path = args.out_root / "guarded_experiment_summary.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--python", type=Path, default=Path(sys.executable))
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--out-root", type=Path, required=True)
    ap.add_argument("--experiment-id", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--init-checkpoint", type=Path)
    ap.add_argument("--holdout-image")
    ap.add_argument("--focus-image")
    ap.add_argument("--focus-weight", type=float, default=1.0)
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--width", type=int, default=48)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument(
        "--architecture",
        choices=(
            "residual_highres",
            "lowres_pixelshuffle",
            "resblock_pixelshuffle",
            "edge_pixelshuffle",
            "adapter_pixelshuffle",
            "preclean_adapter_pixelshuffle",
            "coord_preclean_adapter_pixelshuffle",
            "coord_detail_preclean_adapter_pixelshuffle",
            "coord_deep_preclean_adapter_pixelshuffle",
        ),
        default="lowres_pixelshuffle",
    )
    ap.add_argument("--init-nonstrict", action="store_true")
    ap.add_argument("--init-expand-lowres", action="store_true")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--residual-scale", type=float, default=0.3)
    ap.add_argument("--gradient-weight", type=float, default=0.2)
    ap.add_argument("--laplacian-weight", type=float, default=0.0)
    ap.add_argument("--detail-phase-weight", type=float, default=0.0)
    ap.add_argument("--detail-phase-threshold", type=float, default=0.0)
    ap.add_argument("--plane-weights", help="comma-separated CFA loss weights in r,g1,g2,b order")
    ap.add_argument(
        "--trainable-scope",
        choices=("all", "adapter_only", "preclean_only", "adapter_and_preclean"),
        default="all",
    )
    ap.add_argument("--low-clean-aux-weight", type=float, default=0.0)
    ap.add_argument("--low-clean-detail-aux-weight", type=float, default=0.0)
    ap.add_argument("--low-clean-detail-threshold", type=float, default=0.0)
    ap.add_argument("--loss", choices=("l1", "charbonnier"), default="l1")
    ap.add_argument("--seed", type=int, default=20260618)
    ap.add_argument("--eval-every", type=int, default=200)
    ap.add_argument("--mission-low-dir", type=Path, required=True)
    ap.add_argument("--mission-target-dir", type=Path, required=True)
    ap.add_argument("--mission-stem", action="append", default=[])
    ap.add_argument("--mission-low-width", type=int, default=4096)
    ap.add_argument("--mission-low-height", type=int, default=3072)
    ap.add_argument("--z8-low-dir", type=Path, required=True)
    ap.add_argument("--z8-target-dir", type=Path, required=True)
    ap.add_argument("--z8-stem", action="append", default=[])
    ap.add_argument("--z8-low-width", type=int, default=4140)
    ap.add_argument("--z8-low-height", type=int, default=2760)
    ap.add_argument("--baseline-label", default="guardrail_light")
    ap.add_argument("--baseline-mission-summary", type=Path, required=True)
    ap.add_argument("--baseline-z8-summary", type=Path, required=True)
    ap.add_argument("--tile", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    ap.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    ap.add_argument("--force-eval", action="store_true")
    ap.add_argument("--stop-on-promote", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    args.out_root.mkdir(parents=True, exist_ok=True)
    eval_dir = args.out_root / "eval_checkpoints"
    run(train_command(args, eval_dir), args.repo, args.dry_run)
    if args.dry_run:
        summary_path = dry_run_plan(args, eval_dir)
        print(json.dumps({"summary": str(summary_path), "candidate_count": len(planned_eval_checkpoints(args, eval_dir))}, indent=2))
        return 0

    candidates = load_train_checkpoints(args, eval_dir)
    rows: list[dict[str, Any]] = []
    for checkpoint in candidates:
        mission_dir = eval_summary_dir(args.out_root, checkpoint, "mission")
        z8_dir = eval_summary_dir(args.out_root, checkpoint, "z8")
        run(
            fullframe_eval_command(
                args,
                checkpoint,
                "mission",
                args.mission_low_dir,
                args.mission_target_dir,
                args.mission_stem,
                args.mission_low_width,
                args.mission_low_height,
            ),
            args.repo,
            args.dry_run,
        )
        run(
            fullframe_eval_command(
                args,
                checkpoint,
                "z8",
                args.z8_low_dir,
                args.z8_target_dir,
                args.z8_stem,
                args.z8_low_width,
                args.z8_low_height,
            ),
            args.repo,
            args.dry_run,
        )
        decision_path = args.out_root / f"{checkpoint_stem(checkpoint)}_decision.json"
        run(decision_command(args, checkpoint, mission_dir / "summary.json", z8_dir / "summary.json"), args.repo, args.dry_run)
        decision = load_json(decision_path)
        rows.append({
            "checkpoint": str(checkpoint),
            "mission_summary": str(mission_dir / "summary.json"),
            "z8_summary": str(z8_dir / "summary.json"),
            "decision_receipt": str(decision_path),
            "decision": decision.get("decision"),
            "reason": decision.get("reason"),
            "deltas": decision.get(f"deltas_vs_{args.baseline_label}"),
        })
        if args.stop_on_promote and decision.get("decision") == "promote_for_registry_review":
            break

    summary_path = write_summary(args.out_root, rows)
    print(json.dumps({"summary": str(summary_path), "candidate_count": len(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
