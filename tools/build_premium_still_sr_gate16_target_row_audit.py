#!/usr/bin/env python3
"""Audit the Gate16 Premium still-SR checkpoint on the available target rows.

This is intentionally narrower than the production promotion receipt. The
current Gate16 target artifact is row/tile evidence, not a full 50 MP / 100 MP
full-frame gate. This tool measures the checkpoint honestly on every available
row, records timing/RSS, and explains whether that evidence can move the
promotion gate.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import resource
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate16_target_row_audit.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_TRAIN_RECEIPT = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate16_x2d_tail_safe_0015_smoke_20260702"
    / "train_receipt.json"
)
DEFAULT_TARGETS = (
    DEFAULT_ROOT
    / "artifacts/premium_still_sr_gate15_smoke_targets_20260702"
    / "gate15_x2d_positive_targets.npz"
)
DEFAULT_CANDIDATE_ID = "premium_still_sr_gate16_tail_safe_x2d_positive_z8_noop_v1"
MAE_RMSE_FLOOR_PCT = 15.0


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_trainer_module(repo_root: Path) -> Any:
    trainer_path = repo_root / "tools/cnn/train_premium_still_sr_raw_cfa_residual.py"
    spec = importlib.util.spec_from_file_location("gate16_premium_still_sr_trainer", trainer_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {trainer_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    return float(value) if isinstance(value, (int, float)) else default


def metric_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def row_class(row: dict[str, Any]) -> str:
    explicit = str(row.get("class") or row.get("camera_class") or "").lower()
    if "100" in explicit:
        return "100mp"
    if "50" in explicit:
        return "50mp"
    camera_key = str(row.get("camera_key") or row.get("domain") or row.get("camera") or "").lower()
    if "x2d" in camera_key or "100" in camera_key:
        return "100mp"
    if "z8" in camera_key or "mission" in camera_key or "gopro" in camera_key or "50" in camera_key:
        return "50mp"
    return "unknown"


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    classes = sorted({row_class(row) for row in rows})
    out: dict[str, Any] = {}
    for cls in classes:
        cls_rows = [row for row in rows if row_class(row) == cls]
        out[cls] = {
            "row_count": len(cls_rows),
            "raw_residual_mae_reduction_pct": metric_stats(
                [number(row.get("raw_residual_mae_reduction_pct")) for row in cls_rows]
            ),
            "raw_residual_rmse_reduction_pct": metric_stats(
                [number(row.get("raw_residual_rmse_reduction_pct")) for row in cls_rows]
            ),
            "exact_raw_mae_reduction_pct": metric_stats(
                [number(row.get("exact_raw_mae_reduction_pct")) for row in cls_rows]
            ),
            "worst_rows": sorted(
                (
                    {
                        "index": row.get("index"),
                        "scene_id": row.get("scene_id"),
                        "crop": row.get("crop"),
                        "raw_residual_mae_reduction_pct": number(row.get("raw_residual_mae_reduction_pct")),
                        "raw_residual_rmse_reduction_pct": number(row.get("raw_residual_rmse_reduction_pct")),
                        "exact_raw_mae_reduction_pct": number(row.get("exact_raw_mae_reduction_pct")),
                    }
                    for row in cls_rows
                ),
                key=lambda item: item["raw_residual_mae_reduction_pct"],
            )[:10],
        }
    return out


def is_full_frame_evidence(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return False
    for row in rows:
        crop_size = int(number(row.get("crop_size"), 0))
        high_raw_tile = int(number(row.get("high_raw_tile"), 0))
        if crop_size and high_raw_tile and crop_size <= high_raw_tile:
            return False
        if str(row.get("crop") or "").startswith(("gate14_tile_", "gate15_tile_")):
            return False
    return True


def gate_decision(class_summary: dict[str, Any], *, full_frame_evidence: bool) -> dict[str, Any]:
    missing: list[str] = []
    for cls in ("50mp", "100mp"):
        summary = class_summary.get(cls)
        if not summary or int(summary.get("row_count") or 0) <= 0:
            missing.append(f"{cls} target rows")
            continue
        mae_median = summary["raw_residual_mae_reduction_pct"]["median"]
        rmse_median = summary["raw_residual_rmse_reduction_pct"]["median"]
        mae_min = summary["raw_residual_mae_reduction_pct"]["min"]
        if mae_median is None or mae_median < MAE_RMSE_FLOOR_PCT:
            missing.append(f"{cls} median MAE reduction >= {MAE_RMSE_FLOOR_PCT}%")
        if rmse_median is None or rmse_median < MAE_RMSE_FLOOR_PCT:
            missing.append(f"{cls} median RMSE reduction >= {MAE_RMSE_FLOOR_PCT}%")
        if mae_min is None or mae_min < 0.0:
            missing.append(f"{cls} nonnegative worst-row MAE reduction")
    if not full_frame_evidence:
        missing.append("full-frame 50 MP / 100 MP evidence; current audit is target-row/tile scope")
    return {
        "production_promotable_from_this_audit": not missing,
        "first_open_step": "full_frame_gate_50mp_100mp" if missing else "promotion_rollup",
        "missing_evidence": missing,
    }


def max_rss_gb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    if sys.platform == "darwin":
        return rss / (1024.0**3)
    return rss / (1024.0**2)


def run_eval(args: argparse.Namespace, train_receipt: dict[str, Any]) -> tuple[dict[str, Any], float, float]:
    trainer = load_trainer_module(args.repo_root)
    torch = trainer.torch
    checkpoint = Path(str(train_receipt["checkpoint"]))
    checkpoint_obj = torch.load(checkpoint, map_location="cpu")
    state_dict = checkpoint_obj.get("state_dict") if isinstance(checkpoint_obj, dict) else checkpoint_obj
    checkpoint_config = checkpoint_obj.get("config", {}) if isinstance(checkpoint_obj, dict) else {}
    config = dict(train_receipt.get("config", {}))
    config.update({k: v for k, v in checkpoint_config.items() if v is not None})

    if args.device == "auto":
        device_name = "mps" if torch.backends.mps.is_available() else "cpu"
    else:
        device_name = args.device
    device = torch.device(device_name)

    data = trainer.RawCfaResidualTargets(
        args.targets,
        default_psf_kernel_weights=trainer.resolve_default_psf_kernel_weights(
            SimpleNamespace(
                psf_kernel_weight=config.get("psf_kernel_weights"),
                psf_receipt=Path(config["psf_receipt"]) if config.get("psf_receipt") else None,
            )
        ),
        psf_sidecar_path=Path(config["psf_sidecar"]) if config.get("psf_sidecar") else None,
    )
    model = trainer.build_model(
        str(config.get("model_arch", "residual")),
        trainer.feature_channels(str(config.get("feature_mode", "raw"))),
        int(config.get("width", 48)),
        int(config.get("depth", 6)),
        float(config.get("residual_scale", 0.12)),
    ).to(device)
    model.load_state_dict({key: value.to(device) for key, value in state_dict.items()})

    indices = list(range(len(data.rows)))
    if args.max_rows > 0:
        indices = indices[: args.max_rows]

    start = time.perf_counter()
    result = trainer.eval_rows(
        model,
        data,
        indices,
        feature_mode=str(config.get("feature_mode", "raw")),
        feature_block=int(config.get("feature_block", 9)),
        target_policy=str(config.get("target_policy", "raw")),
        noise_threshold_scale=float(config.get("noise_threshold_scale", 1.0)),
        device=device,
        tile=int(config.get("eval_tile") or config.get("patch_size") or 128),
        context_padding=int(config.get("context_padding", 0)),
        target_scale_policy=str(config.get("target_scale_policy", "none")),
        target_scale_strength=float(config.get("target_scale_strength", 1.0)),
        target_scale_reference_abs_mean=float(config.get("target_scale_reference_abs_mean", 0.0)),
        target_representation=str(config.get("target_representation", "residual")),
        eval_overlap=int(config.get("eval_overlap", 0)),
        seam_check_width=int(config.get("seam_check_width", 0)),
        candidate_hf_noop_threshold=float(config.get("candidate_hf_noop_threshold", 0.0)),
        candidate_hf_noop_softness=float(config.get("candidate_hf_noop_softness", 0.0)),
    )
    seconds = time.perf_counter() - start
    result["device"] = device_name
    result["config"] = {
        key: config.get(key)
        for key in (
            "feature_mode",
            "model_arch",
            "width",
            "depth",
            "residual_scale",
            "feature_block",
            "patch_size",
            "eval_overlap",
            "seam_check_width",
            "target_policy",
            "target_representation",
            "candidate_hf_noop_threshold",
        )
    }
    return result, seconds, max_rss_gb()


def build_receipt(args: argparse.Namespace, eval_result: dict[str, Any], seconds: float, peak_rss_gb: float) -> dict[str, Any]:
    train_receipt = load_json(args.train_receipt)
    rows = [row for row in eval_result.get("rows", []) if isinstance(row, dict)]
    class_summary = summarize_rows(rows)
    full_frame_evidence = is_full_frame_evidence(rows)
    decision = gate_decision(class_summary, full_frame_evidence=full_frame_evidence)
    checkpoint = Path(str(train_receipt.get("checkpoint") or ""))
    row_count = int(eval_result.get("row_count") or len(rows))
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": args.candidate_id,
        "production_ready": False,
        "production_promotable_from_this_audit": decision["production_promotable_from_this_audit"],
        "first_open_step": decision["first_open_step"],
        "row_scope": "full_frame" if full_frame_evidence else "target_row_tile",
        "full_frame_evidence": full_frame_evidence,
        "promotion_thresholds": {
            "median_mae_reduction_pct_50mp": MAE_RMSE_FLOOR_PCT,
            "median_rmse_reduction_pct_50mp": MAE_RMSE_FLOOR_PCT,
            "median_mae_reduction_pct_100mp": MAE_RMSE_FLOOR_PCT,
            "median_rmse_reduction_pct_100mp": MAE_RMSE_FLOOR_PCT,
            "worst_row_mae_reduction_pct_50mp": 0.0,
            "worst_row_mae_reduction_pct_100mp": 0.0,
        },
        "artifacts": {
            "train_receipt": {"path": args.train_receipt.as_posix(), "sha256": sha256_file(args.train_receipt)},
            "targets": {"path": args.targets.as_posix(), "sha256": sha256_file(args.targets)},
            "checkpoint": {
                "path": checkpoint.as_posix(),
                "sha256": sha256_file(checkpoint) if checkpoint.is_file() else None,
                "expected_sha256": train_receipt.get("checkpoint_sha256"),
            },
        },
        "timing": {
            "eval_seconds": seconds,
            "seconds_per_target_row": seconds / max(row_count, 1),
            "target_rows_per_second": row_count / max(seconds, 1.0e-12),
            "peak_rss_gb": peak_rss_gb,
            "device": eval_result.get("device"),
        },
        "coverage": {
            "target_row_count": row_count,
            "classes": {key: value.get("row_count") for key, value in class_summary.items()},
            "source_images": sorted({str(row.get("source_dng") or row.get("image_id") or "") for row in rows})[:20],
        },
        "metrics_by_class": class_summary,
        "overall_eval": {
            key: eval_result.get(key)
            for key in (
                "baseline_raw_residual_mae",
                "model_raw_residual_mae",
                "raw_residual_mae_reduction_pct",
                "baseline_raw_residual_rmse",
                "model_raw_residual_rmse",
                "raw_residual_rmse_reduction_pct",
                "exact_raw_mae_reduction_pct",
                "candidate_hf_noop_gate",
                "candidate_hf_noop_row_count",
            )
        },
        "missing_evidence_before_100_percent": decision["missing_evidence"],
        "stop_rule": (
            "Do not call Premium still/SR production-ready from this artifact unless it is full-frame, "
            "contains both 50 MP and 100 MP evidence, clears the 15% MAE/RMSE floors, and has nonnegative worst rows."
        ),
    }
    return receipt


def render_html(receipt: dict[str, Any]) -> str:
    cards = [
        ("Production ready", receipt["production_ready"]),
        ("Promotable from audit", receipt["production_promotable_from_this_audit"]),
        ("Row scope", receipt["row_scope"]),
        ("Rows", receipt["coverage"]["target_row_count"]),
        ("Rows/sec", f"{receipt['timing']['target_rows_per_second']:.2f}"),
        ("Peak RSS", f"{receipt['timing']['peak_rss_gb']:.2f} GB"),
    ]
    cards_html = "\n".join(
        f"<section class='card'><div class='label'>{html.escape(label)}</div><div class='value'>{html.escape(str(value))}</div></section>"
        for label, value in cards
    )
    class_rows = []
    for cls, summary in receipt["metrics_by_class"].items():
        class_rows.append(
            "<tr>"
            f"<td>{html.escape(cls)}</td>"
            f"<td>{summary['row_count']}</td>"
            f"<td>{summary['raw_residual_mae_reduction_pct']['median']:.3f}%</td>"
            f"<td>{summary['raw_residual_mae_reduction_pct']['min']:.3f}%</td>"
            f"<td>{summary['raw_residual_rmse_reduction_pct']['median']:.3f}%</td>"
            "</tr>"
        )
    missing = "\n".join(f"<li>{html.escape(item)}</li>" for item in receipt["missing_evidence_before_100_percent"])
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate16 Premium Still-SR Target-Row Audit</title>
<style>
body {{ margin: 30px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f6f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; font-size: 30px; }}
.sub {{ color: #5c6773; max-width: 940px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dbe2e8; border-radius: 8px; padding: 14px; }}
.label {{ color: #5c6773; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 20px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe2e8; margin: 14px 0 24px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; }}
</style>
<main>
<h1>Gate16 Premium Still-SR Target-Row Audit</h1>
<p class="sub">This audit replays the current Gate16 checkpoint over the available target rows. It is a blocker/advance receipt, not a full production promotion receipt unless row scope is full-frame and both 50 MP and 100 MP classes are present.</p>
<div class="grid">{cards_html}</div>
<h2>Class Metrics</h2>
<table><tr><th>class</th><th>rows</th><th>median MAE reduction</th><th>worst MAE reduction</th><th>median RMSE reduction</th></tr>{''.join(class_rows)}</table>
<h2>Missing Evidence Before 100%</h2>
<ul>{missing}</ul>
<h2>Artifact Paths</h2>
<pre>{html.escape(json.dumps(receipt["artifacts"], indent=2, sort_keys=True))}</pre>
</main>
"""


def write_outputs(args: argparse.Namespace, receipt: dict[str, Any]) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "gate16_target_row_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": json_path.as_posix(),
                "dashboard": html_path.as_posix(),
                "production_promotable_from_this_audit": receipt["production_promotable_from_this_audit"],
                "first_open_step": receipt["first_open_step"],
            },
            indent=2,
            sort_keys=True,
        )
    )


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-id", default=DEFAULT_CANDIDATE_ID)
    ap.add_argument("--train-receipt", type=Path, default=DEFAULT_TRAIN_RECEIPT)
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    ap.add_argument("--max-rows", type=int, default=0, help="Debug limit. Default 0 audits all target rows.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    train_receipt = load_json(args.train_receipt)
    eval_result, seconds, peak_rss_gb = run_eval(args, train_receipt)
    receipt = build_receipt(args, eval_result, seconds, peak_rss_gb)
    write_outputs(args, receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
