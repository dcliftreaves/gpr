#!/usr/bin/env python3
"""Audit whether a Premium still-SR checkpoint has useful residual direction.

The production gate evaluates the model at its configured output amplitude. This
diagnostic replays the same target rows at fixed candidate-only scalar blends.
If no scalar improves the broad rows, the model objective/direction is wrong. If
a scalar improves the rows, the next production candidate should encode that
runtime-safe scaling policy and rerun the normal gate.
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


SCHEMA = "gpr.premium_still_sr_direction_calibration_audit.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_trainer_module(repo_root: Path) -> Any:
    trainer_path = repo_root / "tools/cnn/train_premium_still_sr_raw_cfa_residual.py"
    spec = importlib.util.spec_from_file_location("premium_still_sr_trainer_for_direction_audit", trainer_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {trainer_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "mean": None, "max": None}
    return {
        "min": min(values),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def max_rss_gb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return rss / (1024.0**3)
    return rss / (1024.0**2)


def parse_alphas(text: str) -> list[float]:
    alphas = sorted({float(part) for part in text.replace(",", " ").split()})
    if not alphas:
        raise ValueError("at least one alpha is required")
    return alphas


def summarize_alpha(rows: list[dict[str, Any]], alpha: float) -> dict[str, Any]:
    selected = [row for row in rows if abs(float(row["alpha"]) - alpha) < 1.0e-12]
    by_class: dict[str, Any] = {}
    for cls in sorted({str(row["class"]) for row in selected}):
        cls_rows = [row for row in selected if str(row["class"]) == cls]
        by_class[cls] = {
            "row_count": len(cls_rows),
            "mae_reduction_pct": stats([float(row["mae_reduction_pct"]) for row in cls_rows]),
            "rmse_reduction_pct": stats([float(row["rmse_reduction_pct"]) for row in cls_rows]),
            "worst_rows": sorted(
                (
                    {
                        "index": row["index"],
                        "scene_id": row["scene_id"],
                        "crop": row["crop"],
                        "mae_reduction_pct": row["mae_reduction_pct"],
                        "rmse_reduction_pct": row["rmse_reduction_pct"],
                    }
                    for row in cls_rows
                ),
                key=lambda item: float(item["mae_reduction_pct"]),
            )[:10],
        }
    return {
        "alpha": alpha,
        "row_count": len(selected),
        "mae_reduction_pct": stats([float(row["mae_reduction_pct"]) for row in selected]),
        "rmse_reduction_pct": stats([float(row["rmse_reduction_pct"]) for row in selected]),
        "by_class": by_class,
    }


def gate_score(summary: dict[str, Any]) -> float:
    classes = summary.get("by_class", {})
    score = float(summary["mae_reduction_pct"]["median"] or -1.0e9)
    for cls in ("50mp", "100mp"):
        cls_summary = classes.get(cls)
        if not cls_summary:
            return -1.0e9
        mae = cls_summary["mae_reduction_pct"]
        rmse = cls_summary["rmse_reduction_pct"]
        score += float(mae["median"] or -1.0e9)
        score += float(rmse["median"] or -1.0e9)
        if mae["min"] is not None and float(mae["min"]) < 0.0:
            score += float(mae["min"])
    return score


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    trainer = load_trainer_module(args.repo_root)
    torch = trainer.torch
    receipt = load_json(args.train_receipt)
    checkpoint = Path(str(receipt["checkpoint"]))
    checkpoint_obj = torch.load(checkpoint, map_location="cpu")
    state_dict = checkpoint_obj.get("state_dict") if isinstance(checkpoint_obj, dict) else checkpoint_obj
    checkpoint_config = checkpoint_obj.get("config", {}) if isinstance(checkpoint_obj, dict) else {}
    config = dict(receipt.get("config", {}))
    config.update({k: v for k, v in checkpoint_config.items() if v is not None})

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
    device_name = "mps" if args.device == "auto" and torch.backends.mps.is_available() else ("cpu" if args.device == "auto" else args.device)
    device = torch.device(device_name)
    model = trainer.build_model(
        str(config.get("model_arch", "residual")),
        trainer.feature_channels(str(config.get("feature_mode", "raw"))),
        int(config.get("width", 48)),
        int(config.get("depth", 6)),
        float(config.get("residual_scale", 0.12)),
    ).to(device)
    model.load_state_dict({key: value.to(device) for key, value in state_dict.items()})
    model.eval()

    target_scale_reference_abs_mean = float(config.get("target_scale_reference_abs_mean", 0.0))
    if not target_scale_reference_abs_mean:
        all_indices = list(range(len(data.rows)))
        target_scale_reference_abs_mean = data.target_scale_reference(all_indices, str(config.get("target_scale_policy", "none")))
    indices = list(range(len(data.rows)))
    if args.max_rows > 0:
        indices = indices[: args.max_rows]
    alphas = parse_alphas(args.alphas)
    rows: list[dict[str, Any]] = []
    start = time.perf_counter()
    with torch.no_grad():
        for idx in indices:
            raw = torch.from_numpy(data.candidate_raw[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
            raw_target = torch.from_numpy(data.target[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
            ev = torch.tensor([float(data.rows[idx].get("ev", 0.0))], dtype=torch.float32, device=device)
            noise = torch.tensor([data.noise_features[idx]], dtype=torch.float32, device=device)
            frame_context = torch.tensor([data.frame_context_features[idx]], dtype=torch.float32, device=device)
            psf = torch.tensor([data.psf_features[idx]], dtype=torch.float32, device=device)
            cfa_phase = torch.tensor([data.cfa_phase_features[idx]], dtype=torch.float32, device=device)
            sigma = torch.tensor([data.noise_sigma4[idx]], dtype=torch.float32, device=device)
            stored_hf = (
                torch.from_numpy(data.candidate_raw_hf[idx].transpose(2, 0, 1)).unsqueeze(0).to(device)
                if data.candidate_raw_hf is not None
                else None
            )
            target = trainer.apply_target_policy(
                raw_target,
                sigma,
                target_policy=str(config.get("target_policy", "raw")),
                noise_threshold_scale=float(config.get("noise_threshold_scale", 1.0)),
            )
            target_scale = torch.tensor(
                [
                    data.target_scale(
                        idx,
                        str(config.get("target_scale_policy", "none")),
                        float(config.get("target_scale_strength", 1.0)),
                        target_scale_reference_abs_mean,
                    )
                ],
                dtype=torch.float32,
                device=device,
            ).view(1, 1, 1, 1)
            pred = trainer.tiled_residual_prediction(
                model,
                raw,
                stored_hf=stored_hf,
                feature_mode=str(config.get("feature_mode", "raw")),
                feature_block=int(config.get("feature_block", 9)),
                ev=ev,
                noise=noise,
                frame_context=frame_context,
                psf=psf,
                cfa_phase=cfa_phase,
                tile=int(config.get("eval_tile") or config.get("patch_size") or 128),
                context_padding=int(config.get("context_padding", 0)),
                eval_overlap=int(config.get("eval_overlap", 0)),
                target_scale=target_scale,
                target_representation=str(config.get("target_representation", "residual")),
            )
            base_mae = float(torch.mean(torch.abs(target)).cpu())
            base_rmse = float(torch.sqrt(torch.mean(target * target)).cpu())
            row_meta = data.rows[idx]
            for alpha in alphas:
                scaled = pred * float(alpha)
                err = scaled - target
                pred_mae = float(torch.mean(torch.abs(err)).cpu())
                pred_rmse = float(torch.sqrt(torch.mean(err * err)).cpu())
                rows.append(
                    {
                        "alpha": float(alpha),
                        "index": idx,
                        "class": row_class(row_meta),
                        "scene_id": row_meta.get("scene_id"),
                        "crop": row_meta.get("crop"),
                        "baseline_mae": base_mae,
                        "model_mae": pred_mae,
                        "baseline_rmse": base_rmse,
                        "model_rmse": pred_rmse,
                        "mae_reduction_pct": 100.0 * (base_mae - pred_mae) / max(base_mae, 1.0e-12),
                        "rmse_reduction_pct": 100.0 * (base_rmse - pred_rmse) / max(base_rmse, 1.0e-12),
                    }
                )
    seconds = time.perf_counter() - start
    summaries = [summarize_alpha(rows, alpha) for alpha in alphas]
    best = max(summaries, key=gate_score)
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": args.candidate_id,
        "production_ready": False,
        "inputs": {
            "train_receipt": str(args.train_receipt),
            "train_receipt_sha256": sha256_file(args.train_receipt),
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": sha256_file(checkpoint),
            "targets": str(args.targets),
            "targets_sha256": sha256_file(args.targets),
        },
        "runtime_policy": {
            "candidate_only_scalar_calibration": True,
            "forbidden_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG", "JPG", "gate_metrics"],
        },
        "coverage": {
            "target_row_count": len(indices),
            "classes": {cls: sum(1 for idx in indices if row_class(data.rows[idx]) == cls) for cls in sorted({row_class(data.rows[idx]) for idx in indices})},
        },
        "config": {
            key: config.get(key)
            for key in (
                "model_arch",
                "feature_mode",
                "target_representation",
                "target_policy",
                "target_scale_policy",
                "candidate_hf_noop_threshold",
                "candidate_hf_noop_softness",
            )
        },
        "alpha_summaries": summaries,
        "best_alpha_summary": best,
        "timing": {
            "device": device_name,
            "eval_seconds": seconds,
            "seconds_per_target_row": seconds / max(len(indices), 1),
            "target_rows_per_second": len(indices) / max(seconds, 1.0e-12),
            "peak_rss_gb": max_rss_gb(),
        },
        "next_decision": (
            "direction_has_candidate_only_scale"
            if float(best["mae_reduction_pct"]["median"] or 0.0) > 1.0
            else "direction_or_objective_wrong"
        ),
    }


def render_html(receipt: dict[str, Any]) -> str:
    rows = []
    for summary in receipt["alpha_summaries"]:
        rows.append(
            "<tr>"
            f"<td>{float(summary['alpha']):.3f}</td>"
            f"<td>{float(summary['mae_reduction_pct']['median'] or 0.0):.3f}%</td>"
            f"<td>{float(summary['rmse_reduction_pct']['median'] or 0.0):.3f}%</td>"
            f"<td>{float(summary['mae_reduction_pct']['min'] or 0.0):.3f}%</td>"
            "</tr>"
        )
    best = receipt["best_alpha_summary"]
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Direction Calibration Audit</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;line-height:1.45;color:#18202a}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d9dee7;padding:8px;text-align:left}}th{{background:#f4f6f9}}
code{{background:#f4f6f9;padding:2px 4px;border-radius:4px}}
</style>
<h1>Premium Still-SR Direction Calibration Audit</h1>
<p>Candidate: <code>{html.escape(receipt["candidate_id"])}</code></p>
<p>Best alpha: <code>{float(best["alpha"]):.3f}</code>, median MAE recovery <code>{float(best["mae_reduction_pct"]["median"] or 0.0):.3f}%</code>.</p>
<table><tr><th>alpha</th><th>median MAE recovery</th><th>median RMSE recovery</th><th>worst MAE recovery</th></tr>{''.join(rows)}</table>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidate-id", required=True)
    ap.add_argument("--train-receipt", type=Path, required=True)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--alphas", default="0 0.025 0.05 0.075 0.1 0.15 0.2 0.3 0.4 0.5 0.75 1.0")
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = run_audit(args)
    receipt_path = args.output_dir / "direction_calibration_audit.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "dashboard": str(html_path), "best_alpha": receipt["best_alpha_summary"]["alpha"], "next_decision": receipt["next_decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
