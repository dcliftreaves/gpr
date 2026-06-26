#!/usr/bin/env python3
"""Decide whether a Mission 1 12MP-to-8K SR checkpoint can be promoted.

The decision is intentionally conservative: a candidate must improve the
Mission holdout against the named baseline and must not regress regenerated Z8
guardrail floors. This keeps focus-only retrains from being promoted when they
fix one local hard row but damage the broader sensor/detail boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "mission1_sr_guarded_focus_retrain_decision.v1"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stat(summary: dict[str, Any], key: str, field: str) -> float:
    value = summary.get(key)
    if not isinstance(value, dict):
        raise KeyError(f"missing {key}.{field}")
    return float(value[field])


def worst_image(summary: dict[str, Any], key: str) -> str | None:
    value = summary.get(key)
    if not isinstance(value, dict):
        return None
    image = value.get("image")
    return str(image) if image is not None else None


def median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) * 0.5)


def rows_by_image(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in summary.get("images") or []:
        if not isinstance(row, dict):
            continue
        image = row.get("image")
        if image is not None:
            rows[str(image)] = row
    return rows


def image_metric(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        raise KeyError(key)
    return float(value)


def paired_comparison(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any] | None:
    candidate_rows = rows_by_image(candidate)
    baseline_rows = rows_by_image(baseline)
    if not candidate_rows or not baseline_rows:
        return None

    shared = sorted(set(candidate_rows) & set(baseline_rows))
    missing_baseline = sorted(set(baseline_rows) - set(candidate_rows))
    extra_candidate = sorted(set(candidate_rows) - set(baseline_rows))
    if not shared:
        return {
            "mode": "paired_image_rows",
            "shared_images": [],
            "missing_baseline_images": missing_baseline,
            "extra_candidate_images": extra_candidate,
            "coverage_ok": False,
        }

    cand_rmse = [image_metric(candidate_rows[image], "rmse_improvement_pct") for image in shared]
    base_rmse = [image_metric(baseline_rows[image], "rmse_improvement_pct") for image in shared]
    cand_psnr = [image_metric(candidate_rows[image], "model_psnr14_db") for image in shared]
    base_psnr = [image_metric(baseline_rows[image], "model_psnr14_db") for image in shared]
    return {
        "mode": "paired_image_rows",
        "shared_images": shared,
        "missing_baseline_images": missing_baseline,
        "extra_candidate_images": extra_candidate,
        "coverage_ok": not missing_baseline,
        "rmse_min_delta": min(cand_rmse) - min(base_rmse),
        "rmse_median_delta": median(cand_rmse) - median(base_rmse),
        "psnr14_min_delta": min(cand_psnr) - min(base_psnr),
        "per_image_rmse_delta": {
            image: image_metric(candidate_rows[image], "rmse_improvement_pct")
            - image_metric(baseline_rows[image], "rmse_improvement_pct")
            for image in shared
        },
        "per_image_psnr14_delta": {
            image: image_metric(candidate_rows[image], "model_psnr14_db")
            - image_metric(baseline_rows[image], "model_psnr14_db")
            for image in shared
        },
    }


def comparable_deltas(
    candidate_row: dict[str, Any],
    baseline_row: dict[str, Any],
    candidate_summary: dict[str, Any],
    baseline_summary: dict[str, Any],
) -> tuple[dict[str, float], dict[str, Any]]:
    paired = paired_comparison(candidate_summary, baseline_summary)
    if paired and paired.get("shared_images"):
        deltas = {
            "rmse_min": float(paired["rmse_min_delta"]),
            "rmse_median": float(paired["rmse_median_delta"]),
            "psnr14_min": float(paired["psnr14_min_delta"]),
        }
        return deltas, paired
    return (
        {
            "rmse_min": candidate_row["rmse_improvement_min"] - baseline_row["rmse_improvement_min"],
            "rmse_median": candidate_row["rmse_improvement_median"] - baseline_row["rmse_improvement_median"],
            "psnr14_min": candidate_row["psnr14_min"] - baseline_row["psnr14_min"],
        },
        {
            "mode": "aggregate_summary",
            "coverage_ok": candidate_row["image_count"] >= baseline_row["image_count"],
            "candidate_image_count": candidate_row["image_count"],
            "baseline_image_count": baseline_row["image_count"],
        },
    )


def summarize_holdout(path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": sha256(path),
        "dashboard": summary.get("dashboard"),
        "image_count": int(summary.get("image_count", 0)),
        "fps_with_write_median": stat(summary, "fps_with_write", "median"),
        "rmse_improvement_min": stat(summary, "rmse_improvement_pct", "min"),
        "rmse_improvement_median": stat(summary, "rmse_improvement_pct", "median"),
        "mae_improvement_min": stat(summary, "mae_improvement_pct", "min"),
        "gradient_improvement_min": stat(summary, "gradient_mae_improvement_pct", "min"),
        "psnr14_min": stat(summary, "model_psnr14_db", "min"),
        "worst_rmse_image": worst_image(summary, "worst_by_rmse_improvement"),
    }


def build_decision(args: argparse.Namespace) -> dict[str, Any]:
    mission = read_json(args.candidate_mission_summary)
    z8 = read_json(args.candidate_z8_summary)
    baseline_mission = read_json(args.baseline_mission_summary)
    baseline_z8 = read_json(args.baseline_z8_summary)
    baseline_display = args.baseline_label.replace("_", "-")

    candidate_mission = summarize_holdout(args.candidate_mission_summary, mission)
    candidate_z8 = summarize_holdout(args.candidate_z8_summary, z8)
    baseline_mission_row = summarize_holdout(args.baseline_mission_summary, baseline_mission)
    baseline_z8_row = summarize_holdout(args.baseline_z8_summary, baseline_z8)

    mission_deltas, mission_comparison = comparable_deltas(
        candidate_mission, baseline_mission_row, mission, baseline_mission
    )
    z8_deltas, z8_comparison = comparable_deltas(candidate_z8, baseline_z8_row, z8, baseline_z8)
    deltas = {
        "mission_rmse_min": mission_deltas["rmse_min"],
        "mission_rmse_median": mission_deltas["rmse_median"],
        "mission_psnr14_min": mission_deltas["psnr14_min"],
        "z8_rmse_min": z8_deltas["rmse_min"],
        "z8_psnr14_min": z8_deltas["psnr14_min"],
    }
    coverage_ok = bool(mission_comparison.get("coverage_ok")) and bool(z8_comparison.get("coverage_ok"))

    mission_beats_baseline = (
        coverage_ok
        and
        deltas["mission_rmse_min"] > 0.0
        and deltas["mission_rmse_median"] > 0.0
        and deltas["mission_psnr14_min"] >= 0.0
    )
    z8_no_regression = coverage_ok and deltas["z8_rmse_min"] >= 0.0 and deltas["z8_psnr14_min"] >= 0.0
    if mission_beats_baseline and z8_no_regression:
        decision = "promote_for_registry_review"
        reason = (
            f"The candidate beats {baseline_display} on Mission worst-row/median floors "
            "and does not regress regenerated Z8 guardrail RMSE/PSNR floors."
        )
        next_experiment = "Package, register behind a temporary pipeline id, then rerun the full production audit."
    else:
        decision = "reject_do_not_register"
        failures: list[str] = []
        if not coverage_ok:
            failures.append("does not cover the full baseline Mission+Z8 holdout for promotion")
        if not mission_beats_baseline:
            failures.append(f"does not beat {baseline_display} on Mission worst-row/median floors")
        if not z8_no_regression:
            failures.append("regresses the regenerated Z8 guardrail below the registered/light candidates")
        reason = (
            "The candidate improves only a narrower slice or fails a guardrail: "
            + "; ".join(failures)
            + "."
        )
        next_experiment = (
            "If continuing SR, try mixed objective/early-stop against explicit Mission+Z8 validation, "
            "not focus-only continuation. Candidate must beat guardrail-light on Mission worst rows and "
            "not regress regenerated Z8 RMSE/PSNR minima."
        )

    checkpoint = str(args.checkpoint)
    candidate = {
        "checkpoint": checkpoint,
        "checkpoint_sha256": sha256(args.checkpoint) if args.checkpoint.is_file() else None,
        "description": args.description,
        "training_receipt": str(args.training_receipt) if args.training_receipt else None,
        "training_receipt_sha256": (
            sha256(args.training_receipt) if args.training_receipt and args.training_receipt.is_file() else None
        ),
        "mission_holdout": candidate_mission,
        "z8_regenerated_holdout": candidate_z8,
    }

    return {
        "schema": SCHEMA,
        "candidate": candidate,
        f"deltas_vs_{args.baseline_label}": deltas,
        "comparison_scope": {
            "mission": mission_comparison,
            "z8": z8_comparison,
        },
        "baseline": {
            "label": args.baseline_label,
            "mission_holdout": baseline_mission_row,
            "z8_regenerated_holdout": baseline_z8_row,
        },
        "decision": decision,
        "reason": reason,
        "next_experiment": next_experiment,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path)
    parser.add_argument("--description", required=True)
    parser.add_argument("--candidate-mission-summary", type=Path, required=True)
    parser.add_argument("--candidate-z8-summary", type=Path, required=True)
    parser.add_argument("--baseline-label", default="guardrail_light")
    parser.add_argument("--baseline-mission-summary", type=Path, required=True)
    parser.add_argument("--baseline-z8-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    decision = build_decision(args)
    text = json.dumps(decision, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
