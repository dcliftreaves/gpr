#!/usr/bin/env python3
"""Select Mission 1 12MP-to-8K SR checkpoints by full-frame gate metrics.

This is a selection/readiness tool, not a trainer. It consumes full-frame
Mission and regenerated-Z8 summary JSON files and ranks checkpoints by the
production blockers that matter for the current SR pass:

- Mission rows must clear RMSE, MAE, gradient, and PSNR floors.
- Candidate Mission coverage must match the baseline Mission holdout.
- Regenerated Z8 RMSE/PSNR floors must not regress versus the baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA = "mission1_sr_gate_candidate_selection.v1"


@dataclass(frozen=True)
class CandidateSpec:
    label: str
    checkpoint: Path
    mission_summary: Path
    z8_summary: Path
    training_receipt: Path | None = None


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) * 0.5)


def rows_by_image(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in summary.get("images") or []:
        if isinstance(row, dict) and row.get("image") is not None:
            rows[str(row["image"])] = row
    return rows


def metric(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        raise KeyError(f"missing row metric {key}")
    return float(value)


def stat(summary: dict[str, Any], key: str, field: str) -> float:
    value = summary.get(key)
    if not isinstance(value, dict):
        raise KeyError(f"missing {key}.{field}")
    return float(value[field])


def summarize_rows(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rmse = [metric(row, "rmse_improvement_pct") for row in rows.values()]
    mae = [metric(row, "mae_improvement_pct") for row in rows.values()]
    grad = [metric(row, "gradient_mae_improvement_pct") for row in rows.values()]
    psnr = [metric(row, "model_psnr14_db") for row in rows.values()]
    return {
        "image_count": len(rows),
        "rmse_min": min(rmse) if rmse else 0.0,
        "rmse_median": median(rmse),
        "mae_min": min(mae) if mae else 0.0,
        "gradient_min": min(grad) if grad else 0.0,
        "psnr14_min": min(psnr) if psnr else 0.0,
    }


def parse_candidate(value: str) -> CandidateSpec:
    fields = value.split("|")
    if len(fields) not in {4, 5}:
        raise argparse.ArgumentTypeError(
            "--candidate must be label|checkpoint|mission_summary|z8_summary[|training_receipt]"
        )
    training_receipt = Path(fields[4]) if len(fields) == 5 and fields[4] else None
    return CandidateSpec(
        label=fields[0],
        checkpoint=Path(fields[1]),
        mission_summary=Path(fields[2]),
        z8_summary=Path(fields[3]),
        training_receipt=training_receipt,
    )


def row_failures(
    rows: dict[str, dict[str, Any]],
    *,
    rmse_floor: float,
    mae_floor: float,
    gradient_floor: float,
    psnr14_floor: float,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for image, row in sorted(rows.items()):
        metrics = {
            "rmse": metric(row, "rmse_improvement_pct"),
            "mae": metric(row, "mae_improvement_pct"),
            "gradient": metric(row, "gradient_mae_improvement_pct"),
            "psnr14": metric(row, "model_psnr14_db"),
        }
        reasons: list[str] = []
        if metrics["rmse"] < rmse_floor:
            reasons.append(f"rmse {metrics['rmse']:.3f} < {rmse_floor:.3f}")
        if metrics["mae"] < mae_floor:
            reasons.append(f"mae {metrics['mae']:.3f} < {mae_floor:.3f}")
        if metrics["gradient"] < gradient_floor:
            reasons.append(f"gradient {metrics['gradient']:.3f} < {gradient_floor:.3f}")
        if metrics["psnr14"] < psnr14_floor:
            reasons.append(f"psnr14 {metrics['psnr14']:.3f} < {psnr14_floor:.3f}")
        if reasons:
            failures.append({"image": image, "metrics": metrics, "reasons": reasons})
    return failures


def z8_regressions(candidate: dict[str, Any], baseline: dict[str, Any], epsilon: float) -> list[str]:
    regressions: list[str] = []
    cand_rmse = stat(candidate, "rmse_improvement_pct", "min")
    base_rmse = stat(baseline, "rmse_improvement_pct", "min")
    cand_psnr = stat(candidate, "model_psnr14_db", "min")
    base_psnr = stat(baseline, "model_psnr14_db", "min")
    if cand_rmse + epsilon < base_rmse:
        regressions.append(f"z8 rmse_min {cand_rmse:.3f} < baseline {base_rmse:.3f}")
    if cand_psnr + epsilon < base_psnr:
        regressions.append(f"z8 psnr14_min {cand_psnr:.3f} < baseline {base_psnr:.3f}")
    return regressions


def score_candidate(
    spec: CandidateSpec,
    *,
    baseline_mission: dict[str, Any],
    baseline_z8: dict[str, Any],
    rmse_floor: float,
    mae_floor: float,
    gradient_floor: float,
    psnr14_floor: float,
    z8_epsilon: float,
) -> dict[str, Any]:
    mission = read_json(spec.mission_summary)
    z8 = read_json(spec.z8_summary)
    mission_rows = rows_by_image(mission)
    baseline_rows = rows_by_image(baseline_mission)
    expected_images = set(baseline_rows)
    candidate_images = set(mission_rows)
    missing_images = sorted(expected_images - candidate_images)
    extra_images = sorted(candidate_images - expected_images)
    shared_rows = {image: mission_rows[image] for image in sorted(expected_images & candidate_images)}

    failures = row_failures(
        shared_rows,
        rmse_floor=rmse_floor,
        mae_floor=mae_floor,
        gradient_floor=gradient_floor,
        psnr14_floor=psnr14_floor,
    )
    for image in missing_images:
        failures.append({"image": image, "metrics": {}, "reasons": ["missing from candidate mission summary"]})
    z8_failures = z8_regressions(z8, baseline_z8, z8_epsilon)
    coverage_ok = not missing_images
    mission_summary = summarize_rows(shared_rows)
    z8_summary = {
        "image_count": int(z8.get("image_count", 0)),
        "rmse_min": stat(z8, "rmse_improvement_pct", "min"),
        "rmse_median": stat(z8, "rmse_improvement_pct", "median"),
        "mae_min": stat(z8, "mae_improvement_pct", "min"),
        "gradient_min": stat(z8, "gradient_mae_improvement_pct", "min"),
        "psnr14_min": stat(z8, "model_psnr14_db", "min"),
    }
    promoted = coverage_ok and not failures and not z8_failures
    margins = {
        "mission_rmse_floor_margin": mission_summary["rmse_min"] - rmse_floor,
        "mission_mae_floor_margin": mission_summary["mae_min"] - mae_floor,
        "mission_gradient_floor_margin": mission_summary["gradient_min"] - gradient_floor,
        "mission_psnr14_floor_margin": mission_summary["psnr14_min"] - psnr14_floor,
        "z8_rmse_vs_baseline_margin": z8_summary["rmse_min"] - stat(baseline_z8, "rmse_improvement_pct", "min"),
        "z8_psnr14_vs_baseline_margin": z8_summary["psnr14_min"] - stat(baseline_z8, "model_psnr14_db", "min"),
    }
    # Lower rank_score is better. Coverage and hard failures dominate; margins
    # break ties without hiding an explicit blocker.
    worst_margin = min(margins.values()) if margins else 0.0
    rank_score = len(failures) * 1000.0 + len(z8_failures) * 500.0 + (0 if coverage_ok else 10000.0) - worst_margin
    return {
        "label": spec.label,
        "checkpoint": str(spec.checkpoint),
        "checkpoint_sha256": sha256(spec.checkpoint),
        "training_receipt": str(spec.training_receipt) if spec.training_receipt else None,
        "training_receipt_sha256": sha256(spec.training_receipt),
        "mission_summary": str(spec.mission_summary),
        "mission_summary_sha256": sha256(spec.mission_summary),
        "z8_summary": str(spec.z8_summary),
        "z8_summary_sha256": sha256(spec.z8_summary),
        "coverage": {
            "ok": coverage_ok,
            "expected_images": sorted(expected_images),
            "candidate_images": sorted(candidate_images),
            "missing_images": missing_images,
            "extra_images": extra_images,
        },
        "mission": mission_summary,
        "z8": z8_summary,
        "margins": margins,
        "mission_failures": failures,
        "z8_regressions": z8_failures,
        "promoted": promoted,
        "rank_score": rank_score,
        "decision": "promote_for_registry_review" if promoted else "reject_do_not_register",
    }


def build_selection(args: argparse.Namespace) -> dict[str, Any]:
    baseline_mission = read_json(args.baseline_mission_summary)
    baseline_z8 = read_json(args.baseline_z8_summary)
    candidates = [
        score_candidate(
            spec,
            baseline_mission=baseline_mission,
            baseline_z8=baseline_z8,
            rmse_floor=args.rmse_floor,
            mae_floor=args.mae_floor,
            gradient_floor=args.gradient_floor,
            psnr14_floor=args.psnr14_floor,
            z8_epsilon=args.z8_epsilon,
        )
        for spec in args.candidate
    ]
    candidates.sort(
        key=lambda row: (
            row["rank_score"],
            -row["mission"]["rmse_median"],
            -row["z8"]["rmse_min"],
        )
    )
    best = candidates[0] if candidates else None
    return {
        "schema": SCHEMA,
        "baseline": {
            "label": args.baseline_label,
            "mission_summary": str(args.baseline_mission_summary),
            "mission_summary_sha256": sha256(args.baseline_mission_summary),
            "z8_summary": str(args.baseline_z8_summary),
            "z8_summary_sha256": sha256(args.baseline_z8_summary),
        },
        "thresholds": {
            "mission_rmse_floor": args.rmse_floor,
            "mission_mae_floor": args.mae_floor,
            "mission_gradient_floor": args.gradient_floor,
            "mission_psnr14_floor": args.psnr14_floor,
            "z8_epsilon": args.z8_epsilon,
        },
        "best_label": best["label"] if best else None,
        "decision": (
            "promote_for_registry_review"
            if best and best["promoted"]
            else "reject_do_not_register"
        ),
        "reason": (
            f"{best['label']} clears Mission floors and Z8 guardrails."
            if best and best["promoted"]
            else f"{best['label'] if best else 'no candidate'} is best ranked, but at least one Mission/Z8 gate remains open."
        ),
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-label", default="balanced128")
    parser.add_argument("--baseline-mission-summary", type=Path, required=True)
    parser.add_argument("--baseline-z8-summary", type=Path, required=True)
    parser.add_argument("--candidate", type=parse_candidate, action="append", required=True)
    parser.add_argument("--rmse-floor", type=float, default=30.0)
    parser.add_argument("--mae-floor", type=float, default=20.0)
    parser.add_argument("--gradient-floor", type=float, default=8.0)
    parser.add_argument("--psnr14-floor", type=float, default=45.0)
    parser.add_argument("--z8-epsilon", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    selection = build_selection(args)
    text = json.dumps(selection, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
