#!/usr/bin/env python3
"""Plan the next Mission 1 SR guarded iteration from full-frame gate failures.

This tool consumes `scan_mission1_sr_fullframe_checkpoints.py` output and turns
the actual blocker rows into a deterministic next-pass recipe. It does not
promote or register anything. Its job is to keep SR iteration tied to the
production gate rows instead of manual tile-loss guesses.
"""
from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_sr_gate_iteration_plan.v1"


@dataclass(frozen=True)
class Pressure:
    rmse: float
    mae: float
    gradient: float
    psnr14: float

    def dominant(self) -> str:
        pairs = [
            ("gradient", self.gradient),
            ("mae", self.mae),
            ("rmse", self.rmse),
            ("psnr14", self.psnr14),
        ]
        return max(pairs, key=lambda row: row[1])[0]

    def as_dict(self) -> dict[str, float]:
        return {
            "rmse": self.rmse,
            "mae": self.mae,
            "gradient": self.gradient,
            "psnr14": self.psnr14,
        }


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def find_candidate(decision: dict[str, Any], label: str | None) -> dict[str, Any]:
    candidates = decision.get("candidates") or []
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("scan decision has no candidates")
    selected_label = label or decision.get("best_label")
    if selected_label is None:
        raise ValueError("scan decision does not identify a best_label")
    for row in candidates:
        if isinstance(row, dict) and row.get("label") == selected_label:
            return row
    raise ValueError(f"candidate {selected_label!r} not found in scan decision")


def thresholds(decision: dict[str, Any]) -> dict[str, float]:
    raw = decision.get("thresholds")
    if not isinstance(raw, dict):
        raise ValueError("scan decision missing thresholds")
    return {
        "rmse": float(raw["rmse_floor"]),
        "mae": float(raw["mae_floor"]),
        "gradient": float(raw["gradient_floor"]),
        "psnr14": float(raw["psnr14_floor"]),
    }


def failure_pressure(candidate: dict[str, Any], floors: dict[str, float]) -> tuple[Pressure, list[str], list[dict[str, Any]]]:
    totals = {"rmse": 0.0, "mae": 0.0, "gradient": 0.0, "psnr14": 0.0}
    focus_images: set[str] = set()
    failures = []
    for failure in candidate.get("failures") or []:
        if not isinstance(failure, dict):
            continue
        image = str(failure.get("image", ""))
        metrics = failure.get("metrics") if isinstance(failure.get("metrics"), dict) else {}
        row_deficits: dict[str, float] = {}
        for key in totals:
            if key not in metrics:
                continue
            deficit = max(0.0, floors[key] - float(metrics[key]))
            row_deficits[key] = deficit
            totals[key] += deficit / max(floors[key], 1e-9)
        if image:
            focus_images.add(image)
        failures.append({
            "image": image,
            "metrics": metrics,
            "deficits": row_deficits,
            "reasons": failure.get("reasons") or [],
        })
    pressure = Pressure(
        rmse=totals["rmse"],
        mae=totals["mae"],
        gradient=totals["gradient"],
        psnr14=totals["psnr14"],
    )
    return pressure, sorted(focus_images), failures


def choose_recipe(args: argparse.Namespace, candidate: dict[str, Any], pressure: Pressure, focus_images: list[str]) -> dict[str, Any]:
    dominant = pressure.dominant()
    architecture = args.architecture
    trainable_scope = args.trainable_scope
    gradient_weight = args.gradient_weight
    laplacian_weight = args.laplacian_weight
    low_clean_aux_weight = args.low_clean_aux_weight
    low_clean_detail_aux_weight = args.low_clean_detail_aux_weight
    low_clean_detail_threshold = args.low_clean_detail_threshold
    plane_weights = args.plane_weights
    lr = args.lr
    residual_scale = args.residual_scale
    focus_weight = args.focus_weight

    if dominant == "gradient":
        gradient_weight = 14.0 if gradient_weight is None else gradient_weight
        laplacian_weight = 0.2 if laplacian_weight is None else laplacian_weight
        low_clean_aux_weight = 0.03 if low_clean_aux_weight is None else low_clean_aux_weight
        low_clean_detail_aux_weight = 0.15 if low_clean_detail_aux_weight is None else low_clean_detail_aux_weight
        low_clean_detail_threshold = 2.0 if low_clean_detail_threshold is None else low_clean_detail_threshold
        plane_weights = "1.6,1.4,1.2,1.0" if plane_weights is None else plane_weights
        trainable_scope = trainable_scope or "adapter_and_preclean"
        lr = 2e-5 if lr is None else lr
        focus_weight = 4.0 if focus_weight is None else focus_weight
    elif dominant in {"rmse", "mae"}:
        gradient_weight = 10.0 if gradient_weight is None else gradient_weight
        laplacian_weight = 0.2 if laplacian_weight is None else laplacian_weight
        low_clean_aux_weight = 0.05 if low_clean_aux_weight is None else low_clean_aux_weight
        low_clean_detail_aux_weight = 0.10 if low_clean_detail_aux_weight is None else low_clean_detail_aux_weight
        low_clean_detail_threshold = 2.0 if low_clean_detail_threshold is None else low_clean_detail_threshold
        plane_weights = "1.3,1.2,1.2,1.1" if plane_weights is None else plane_weights
        trainable_scope = trainable_scope or "all"
        lr = 3e-5 if lr is None else lr
        focus_weight = 3.0 if focus_weight is None else focus_weight
    else:
        gradient_weight = 8.0 if gradient_weight is None else gradient_weight
        laplacian_weight = 0.1 if laplacian_weight is None else laplacian_weight
        low_clean_aux_weight = 0.02 if low_clean_aux_weight is None else low_clean_aux_weight
        low_clean_detail_aux_weight = 0.05 if low_clean_detail_aux_weight is None else low_clean_detail_aux_weight
        low_clean_detail_threshold = 2.0 if low_clean_detail_threshold is None else low_clean_detail_threshold
        plane_weights = "1.0,1.0,1.0,1.0" if plane_weights is None else plane_weights
        trainable_scope = trainable_scope or "adapter_and_preclean"
        lr = 2e-5 if lr is None else lr
        focus_weight = 2.0 if focus_weight is None else focus_weight

    checkpoint = args.init_checkpoint or candidate.get("checkpoint")
    if not checkpoint:
        raise ValueError("selected candidate has no checkpoint; pass --init-checkpoint")
    return {
        "selected_label": candidate["label"],
        "init_checkpoint": str(checkpoint),
        "architecture": architecture,
        "init_nonstrict": bool(args.init_nonstrict),
        "steps": args.steps,
        "batch": args.batch,
        "width": args.width,
        "depth": args.depth,
        "lr": lr,
        "residual_scale": residual_scale,
        "gradient_weight": gradient_weight,
        "laplacian_weight": laplacian_weight,
        "detail_phase_weight": float(args.detail_phase_weight or 0.0),
        "detail_phase_threshold": float(args.detail_phase_threshold or 0.0),
        "plane_weights": plane_weights,
        "trainable_scope": trainable_scope,
        "low_clean_aux_weight": low_clean_aux_weight,
        "low_clean_detail_aux_weight": low_clean_detail_aux_weight,
        "low_clean_detail_threshold": low_clean_detail_threshold,
        "loss": args.loss,
        "seed": args.seed,
        "eval_every": args.eval_every,
        "focus_images": focus_images,
        "focus_weight": focus_weight,
    }


def append_optional_path(cmd: list[str], flag: str, value: Path | None) -> None:
    if value is not None:
        cmd.extend([flag, str(value)])


def guarded_command(args: argparse.Namespace, recipe: dict[str, Any]) -> list[str] | None:
    required = [
        args.pairs,
        args.out_root,
        args.mission_low_dir,
        args.mission_target_dir,
        args.z8_low_dir,
        args.z8_target_dir,
        args.baseline_mission_summary,
        args.baseline_z8_summary,
    ]
    if any(value is None for value in required):
        return None
    cmd = [
        str(args.python),
        "tools/cnn/run_mission1_sr_guarded_experiment.py",
        "--repo",
        str(args.repo),
        "--python",
        str(args.python),
        "--pairs",
        str(args.pairs),
        "--out-root",
        str(args.out_root),
        "--experiment-id",
        args.experiment_id,
        "--description",
        args.description,
        "--init-checkpoint",
        recipe["init_checkpoint"],
        "--steps",
        str(recipe["steps"]),
        "--batch",
        str(recipe["batch"]),
        "--width",
        str(recipe["width"]),
        "--depth",
        str(recipe["depth"]),
        "--architecture",
        recipe["architecture"],
        "--lr",
        str(recipe["lr"]),
        "--residual-scale",
        str(recipe["residual_scale"]),
        "--gradient-weight",
        str(recipe["gradient_weight"]),
        "--laplacian-weight",
        str(recipe["laplacian_weight"]),
        "--detail-phase-weight",
        str(recipe["detail_phase_weight"]),
        "--detail-phase-threshold",
        str(recipe["detail_phase_threshold"]),
        "--plane-weights",
        recipe["plane_weights"],
        "--trainable-scope",
        recipe["trainable_scope"],
        "--low-clean-aux-weight",
        str(recipe["low_clean_aux_weight"]),
        "--low-clean-detail-aux-weight",
        str(recipe["low_clean_detail_aux_weight"]),
        "--low-clean-detail-threshold",
        str(recipe["low_clean_detail_threshold"]),
        "--loss",
        recipe["loss"],
        "--seed",
        str(recipe["seed"]),
        "--eval-every",
        str(recipe["eval_every"]),
        "--focus-image",
        ",".join(recipe["focus_images"]),
        "--focus-weight",
        str(recipe["focus_weight"]),
        "--mission-low-dir",
        str(args.mission_low_dir),
        "--mission-target-dir",
        str(args.mission_target_dir),
        "--z8-low-dir",
        str(args.z8_low_dir),
        "--z8-target-dir",
        str(args.z8_target_dir),
        "--baseline-label",
        args.baseline_label,
        "--baseline-mission-summary",
        str(args.baseline_mission_summary),
        "--baseline-z8-summary",
        str(args.baseline_z8_summary),
        "--tile",
        str(args.tile),
        "--overlap",
        str(args.overlap),
        "--device",
        args.device,
    ]
    if recipe["init_nonstrict"]:
        cmd.append("--init-nonstrict")
    for stem in args.mission_stem or []:
        cmd.extend(["--mission-stem", stem])
    for stem in args.z8_stem or []:
        cmd.extend(["--z8-stem", stem])
    if args.force_eval:
        cmd.append("--force-eval")
    if args.stop_on_promote:
        cmd.append("--stop-on-promote")
    if args.dry_run:
        cmd.append("--dry-run")
    return cmd


def shell_join(cmd: list[str] | None) -> str | None:
    if cmd is None:
        return None
    return " ".join(shlex.quote(part) for part in cmd)


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    decision = read_json(args.scan_decision)
    candidate = find_candidate(decision, args.candidate_label)
    floors = thresholds(decision)
    pressure, focus_images, failures = failure_pressure(candidate, floors)
    recipe = choose_recipe(args, candidate, pressure, focus_images)
    command = guarded_command(args, recipe)
    return {
        "schema": SCHEMA,
        "scan_decision": str(args.scan_decision),
        "scan_decision_result": decision.get("decision"),
        "selected_label": candidate["label"],
        "selected_checkpoint": candidate.get("checkpoint"),
        "selected_summary": candidate.get("summary"),
        "thresholds": floors,
        "pressure": pressure.as_dict(),
        "dominant_blocker": pressure.dominant(),
        "focus_images": focus_images,
        "failures": failures,
        "recipe": recipe,
        "guarded_command": command,
        "guarded_command_shell": shell_join(command),
        "decision": "run_guarded_iteration" if failures else "no_gate_failures_found",
        "notes": [
            "This is a planning receipt only; it does not promote or register a checkpoint.",
            "The emitted command keeps selection tied to full-frame Mission/Z8 guardrails.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan-decision", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--candidate-label")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--python", type=Path, default=Path("python3"))
    ap.add_argument("--pairs", type=Path)
    ap.add_argument("--out-root", type=Path)
    ap.add_argument("--experiment-id", default="mission1_sr_gate_iteration")
    ap.add_argument("--description", default="Mission 1 SR gate-driven continuation")
    ap.add_argument("--init-checkpoint")
    ap.add_argument(
        "--architecture",
        default="coord_preclean_adapter_pixelshuffle",
        choices=(
            "coord_preclean_adapter_pixelshuffle",
            "coord_deep_preclean_adapter_pixelshuffle",
        ),
    )
    ap.add_argument("--init-nonstrict", action="store_true")
    ap.add_argument("--steps", type=int, default=800)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--width", type=int, default=96)
    ap.add_argument("--depth", type=int, default=6)
    ap.add_argument("--lr", type=float)
    ap.add_argument("--residual-scale", type=float, default=0.3)
    ap.add_argument("--gradient-weight", type=float)
    ap.add_argument("--laplacian-weight", type=float)
    ap.add_argument("--detail-phase-weight", type=float)
    ap.add_argument("--detail-phase-threshold", type=float)
    ap.add_argument("--plane-weights")
    ap.add_argument("--trainable-scope", choices=("all", "adapter_only", "preclean_only", "adapter_and_preclean"))
    ap.add_argument("--low-clean-aux-weight", type=float)
    ap.add_argument("--low-clean-detail-aux-weight", type=float)
    ap.add_argument("--low-clean-detail-threshold", type=float)
    ap.add_argument("--loss", choices=("l1", "charbonnier"), default="charbonnier")
    ap.add_argument("--seed", type=int, default=20260619)
    ap.add_argument("--eval-every", type=int, default=200)
    ap.add_argument("--focus-weight", type=float)
    ap.add_argument("--mission-low-dir", type=Path)
    ap.add_argument("--mission-target-dir", type=Path)
    ap.add_argument("--mission-stem", action="append")
    ap.add_argument("--z8-low-dir", type=Path)
    ap.add_argument("--z8-target-dir", type=Path)
    ap.add_argument("--z8-stem", action="append")
    ap.add_argument("--baseline-label", default="guardrail_light")
    ap.add_argument("--baseline-mission-summary", type=Path)
    ap.add_argument("--baseline-z8-summary", type=Path)
    ap.add_argument("--tile", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    ap.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    ap.add_argument("--force-eval", action="store_true")
    ap.add_argument("--stop-on-promote", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    plan = build_plan(args)
    args.out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"plan": str(args.out), "decision": plan["decision"], "dominant": plan["dominant_blocker"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
