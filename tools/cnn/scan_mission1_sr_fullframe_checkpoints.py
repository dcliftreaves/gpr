#!/usr/bin/env python3
"""Scan Mission 1 SR checkpoints with full-frame gate metrics.

This tool is intentionally gate-first: it ranks saved checkpoints by the same
full-frame rows and floors that block production, instead of trusting training
tile loss. It can either consume existing full-frame summary JSON files or run
`run_mission1_sr_fullframe_broad_eval.py` for each checkpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_sr_fullframe_checkpoint_scan.v1"


@dataclass(frozen=True)
class CheckpointSpec:
    label: str
    checkpoint: Path | None
    summary: Path | None


@dataclass(frozen=True)
class Floors:
    rmse: float
    mae: float
    gradient: float
    psnr14: float


def sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def parse_checkpoint_spec(value: str) -> CheckpointSpec:
    fields = value.split("|")
    if len(fields) != 2:
        raise argparse.ArgumentTypeError("--checkpoint must be label|checkpoint_path")
    return CheckpointSpec(label=fields[0], checkpoint=Path(fields[1]), summary=None)


def parse_summary_spec(value: str) -> CheckpointSpec:
    fields = value.split("|")
    if len(fields) != 2:
        raise argparse.ArgumentTypeError("--summary must be label|summary_json")
    return CheckpointSpec(label=fields[0], checkpoint=None, summary=Path(fields[1]))


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


def row_metric(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None:
        raise KeyError(f"missing row metric {key}")
    return float(value)


def summarize_rows(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rmse = [row_metric(row, "rmse_improvement_pct") for row in rows.values()]
    mae = [row_metric(row, "mae_improvement_pct") for row in rows.values()]
    grad = [row_metric(row, "gradient_mae_improvement_pct") for row in rows.values()]
    psnr = [row_metric(row, "model_psnr14_db") for row in rows.values()]
    fps = [float(row.get("fps_with_write", 0.0)) for row in rows.values()]
    return {
        "image_count": len(rows),
        "rmse_min": min(rmse) if rmse else 0.0,
        "rmse_median": median(rmse),
        "mae_min": min(mae) if mae else 0.0,
        "gradient_min": min(grad) if grad else 0.0,
        "psnr14_min": min(psnr) if psnr else 0.0,
        "fps_median": median(fps),
    }


def floor_failures(rows: dict[str, dict[str, Any]], floors: Floors) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for image, row in sorted(rows.items()):
        metrics = {
            "rmse": row_metric(row, "rmse_improvement_pct"),
            "mae": row_metric(row, "mae_improvement_pct"),
            "gradient": row_metric(row, "gradient_mae_improvement_pct"),
            "psnr14": row_metric(row, "model_psnr14_db"),
        }
        reasons: list[str] = []
        if metrics["rmse"] < floors.rmse:
            reasons.append(f"rmse {metrics['rmse']:.3f} < {floors.rmse:.3f}")
        if metrics["mae"] < floors.mae:
            reasons.append(f"mae {metrics['mae']:.3f} < {floors.mae:.3f}")
        if metrics["gradient"] < floors.gradient:
            reasons.append(f"gradient {metrics['gradient']:.3f} < {floors.gradient:.3f}")
        if metrics["psnr14"] < floors.psnr14:
            reasons.append(f"psnr14 {metrics['psnr14']:.3f} < {floors.psnr14:.3f}")
        if reasons:
            failures.append({"image": image, "metrics": metrics, "reasons": reasons})
    return failures


def score_summary(
    *,
    label: str,
    summary_path: Path,
    checkpoint: Path | None,
    summary: dict[str, Any],
    baseline_rows: dict[str, dict[str, Any]],
    floors: Floors,
) -> dict[str, Any]:
    rows = rows_by_image(summary)
    expected_images = set(baseline_rows)
    candidate_images = set(rows)
    shared_images = sorted(expected_images & candidate_images)
    missing_images = sorted(expected_images - candidate_images)
    extra_images = sorted(candidate_images - expected_images)
    shared_rows = {image: rows[image] for image in shared_images}
    failures = floor_failures(shared_rows, floors)
    for image in missing_images:
        failures.append({"image": image, "metrics": {}, "reasons": ["missing from candidate summary"]})
    row_stats = summarize_rows(shared_rows)
    baseline_stats = summarize_rows({image: baseline_rows[image] for image in shared_images})
    margins = {
        "rmse_floor": row_stats["rmse_min"] - floors.rmse,
        "mae_floor": row_stats["mae_min"] - floors.mae,
        "gradient_floor": row_stats["gradient_min"] - floors.gradient,
        "psnr14_floor": row_stats["psnr14_min"] - floors.psnr14,
        "rmse_vs_baseline": row_stats["rmse_min"] - baseline_stats["rmse_min"],
        "mae_vs_baseline": row_stats["mae_min"] - baseline_stats["mae_min"],
        "gradient_vs_baseline": row_stats["gradient_min"] - baseline_stats["gradient_min"],
        "psnr14_vs_baseline": row_stats["psnr14_min"] - baseline_stats["psnr14_min"],
    }
    floor_pass = not failures and not missing_images
    beats_or_matches_baseline = all(
        margins[key] >= 0.0
        for key in ("rmse_vs_baseline", "mae_vs_baseline", "gradient_vs_baseline", "psnr14_vs_baseline")
    )
    worst_margin = min(margins.values()) if margins else 0.0
    rank_score = len(failures) * 1000.0 + len(missing_images) * 10000.0 - worst_margin
    return {
        "label": label,
        "checkpoint": str(checkpoint) if checkpoint else None,
        "checkpoint_sha256": sha256(checkpoint),
        "summary": str(summary_path),
        "summary_sha256": sha256(summary_path),
        "dashboard": summary.get("dashboard"),
        "coverage": {
            "ok": not missing_images,
            "shared_images": shared_images,
            "missing_images": missing_images,
            "extra_images": extra_images,
        },
        "metrics": row_stats,
        "baseline_metrics_on_shared_images": baseline_stats,
        "margins": margins,
        "floor_pass": floor_pass,
        "beats_or_matches_baseline": beats_or_matches_baseline,
        "promoted": floor_pass and beats_or_matches_baseline,
        "failures": failures,
        "rank_score": rank_score,
    }


def build_decision(
    *,
    specs: list[CheckpointSpec],
    summaries: dict[str, Path],
    baseline_label: str,
    floors: Floors,
) -> dict[str, Any]:
    if baseline_label not in summaries:
        raise ValueError(f"baseline label {baseline_label!r} was not scanned")
    baseline_summary = read_json(summaries[baseline_label])
    baseline_rows = rows_by_image(baseline_summary)
    if not baseline_rows:
        raise ValueError(f"{summaries[baseline_label]} has no image rows")
    by_label = {spec.label: spec for spec in specs}
    candidates = [
        score_summary(
            label=label,
            summary_path=summary_path,
            checkpoint=by_label.get(label).checkpoint if by_label.get(label) else None,
            summary=read_json(summary_path),
            baseline_rows=baseline_rows,
            floors=floors,
        )
        for label, summary_path in summaries.items()
    ]
    candidates.sort(key=lambda row: (row["rank_score"], -row["metrics"]["rmse_median"], row["label"]))
    best = candidates[0] if candidates else None
    promoted = [row for row in candidates if row["promoted"]]
    return {
        "schema": SCHEMA,
        "baseline_label": baseline_label,
        "baseline_summary": str(summaries[baseline_label]),
        "thresholds": {
            "rmse_floor": floors.rmse,
            "mae_floor": floors.mae,
            "gradient_floor": floors.gradient,
            "psnr14_floor": floors.psnr14,
        },
        "best_label": best["label"] if best else None,
        "promoted_labels": [row["label"] for row in promoted],
        "decision": "promote_for_registry_review" if promoted else "reject_do_not_register",
        "reason": (
            f"{promoted[0]['label']} clears full-frame floors and does not regress the baseline."
            if promoted
            else f"{best['label'] if best else 'no checkpoint'} is best ranked, but at least one full-frame gate remains open."
        ),
        "candidates": candidates,
    }


def run_eval(args: argparse.Namespace, spec: CheckpointSpec) -> Path:
    if spec.summary is not None:
        return spec.summary
    if spec.checkpoint is None:
        raise ValueError(f"{spec.label} has neither checkpoint nor summary")
    out_dir = args.out_root / spec.label
    summary = out_dir / "summary.json"
    if summary.exists() and not args.force:
        return summary
    cmd = [
        str(args.python),
        "tools/cnn/run_mission1_sr_fullframe_broad_eval.py",
        "--python",
        str(args.python),
        "--low-dir",
        str(args.low_dir),
        "--target-dir",
        str(args.target_dir),
        "--checkpoint",
        str(spec.checkpoint),
        "--out-root",
        str(out_dir),
        "--tile",
        str(args.tile),
        "--overlap",
        str(args.overlap),
        "--device",
        args.device,
        "--force",
    ]
    for stem in args.stem or []:
        cmd.extend(["--stem", stem])
    subprocess.run(cmd, cwd=args.repo, check=True)
    return summary


def write_tsv(path: Path, decision: dict[str, Any]) -> None:
    lines = [
        "label\trmse_min\tmae_min\tgradient_min\tpsnr14_min\trmse_vs_baseline\tmae_vs_baseline\tgradient_vs_baseline\tpromoted\tfailure_count"
    ]
    for row in decision["candidates"]:
        metrics = row["metrics"]
        margins = row["margins"]
        lines.append(
            "\t".join(
                [
                    row["label"],
                    f"{metrics['rmse_min']:.6f}",
                    f"{metrics['mae_min']:.6f}",
                    f"{metrics['gradient_min']:.6f}",
                    f"{metrics['psnr14_min']:.6f}",
                    f"{margins['rmse_vs_baseline']:.6f}",
                    f"{margins['mae_vs_baseline']:.6f}",
                    f"{margins['gradient_vs_baseline']:.6f}",
                    str(bool(row["promoted"])),
                    str(len(row["failures"])),
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=parse_checkpoint_spec, action="append", default=[])
    parser.add_argument("--summary", type=parse_summary_spec, action="append", default=[])
    parser.add_argument("--baseline-label", required=True)
    parser.add_argument("--low-dir", type=Path)
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--stem", action="append")
    parser.add_argument("--tile", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=64)
    parser.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rmse-floor", type=float, default=30.0)
    parser.add_argument("--mae-floor", type=float, default=20.0)
    parser.add_argument("--gradient-floor", type=float, default=8.0)
    parser.add_argument("--psnr14-floor", type=float, default=45.0)
    args = parser.parse_args()

    specs = list(args.summary) + list(args.checkpoint)
    if not specs:
        raise SystemExit("provide at least one --summary or --checkpoint")
    if args.checkpoint and (args.low_dir is None or args.target_dir is None):
        raise SystemExit("--checkpoint requires --low-dir and --target-dir")

    args.out_root.mkdir(parents=True, exist_ok=True)
    summaries = {spec.label: run_eval(args, spec) for spec in specs}
    decision = build_decision(
        specs=specs,
        summaries=summaries,
        baseline_label=args.baseline_label,
        floors=Floors(args.rmse_floor, args.mae_floor, args.gradient_floor, args.psnr14_floor),
    )
    decision_path = args.out_root / "checkpoint_scan_decision.json"
    decision_path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(args.out_root / "checkpoint_scan.tsv", decision)
    print(json.dumps({"decision": str(decision_path), "result": decision["decision"], "best": decision["best_label"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
