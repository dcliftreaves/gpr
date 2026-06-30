#!/usr/bin/env python3
"""Build a premium still-SR raw-CFA residual gap dashboard.

This is a receipt-level production audit. It does not train a model; it turns
the current raw-CFA residual target and model receipts into a concise answer:
which candidates are promotable, which camera/domain is blocking promotion, and
what the next experiment must prove.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_raw_cfa_residual_gap.v1"
DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_TARGET_RECEIPT = (
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_targets_20260630/raw_cfa_residual_targets.json"
)
DEFAULT_MODEL_RECEIPTS = [
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_w32_2000_lowlr_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w32_2000_lowlr_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w64_5000_block17_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_storedhf_w32_2000_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_signal_residual_model_x2dholdout_w32_2000_thr1_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w48_1600_abs6_patch256_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_context_w40_1800_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_x2donly_w48_2200_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextstoredhf_w40_1800_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_bandloss_w40_1800_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_camera_balanced_w48_2200_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextpad32_w48_1200_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_framectx_unet_w32_1200_20260630/train_receipt.json",
    DEFAULT_EXTERNAL_ROOT
    / "artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_framectx_unet_w32_1200_20260630/train_receipt.json",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def metric(receipt: dict[str, Any], split: str, name: str) -> float | None:
    value = nested(receipt, ["eval", split, name, "median"])
    if isinstance(value, (int, float)):
        return float(value)
    return None


def infer_camera(receipt: dict[str, Any]) -> str:
    config = receipt.get("config") if isinstance(receipt.get("config"), dict) else {}
    holdout_camera = config.get("holdout_camera")
    if holdout_camera:
        return str(holdout_camera).upper()
    scene = str(config.get("holdout_scene") or "").lower()
    if "x2d" in scene or "austin" in scene:
        return "X2D"
    if "z8" in scene:
        return "Z8"
    if "mission" in scene or "gp0" in scene:
        return "MISSION1"
    return "UNKNOWN"


def summarize_target(path: Path) -> dict[str, Any]:
    receipt = load_json(path)
    summary = receipt.get("summary") if isinstance(receipt.get("summary"), dict) else {}
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": receipt.get("schema"),
        "row_count": int(summary.get("row_count") or receipt.get("row_count") or len(receipt.get("rows", []))),
        "scene_count": int(summary.get("scene_count") or len(summary.get("scenes", [])) or 0),
        "scenes": list(summary.get("scenes", [])) if isinstance(summary.get("scenes"), list) else [],
        "render_to_raw_corr_abs_median": nested(summary, ["render_y_to_raw_same_color_hf_corr_abs", "median"]),
        "render_to_raw_corr_abs_mean": nested(summary, ["render_y_to_raw_same_color_hf_corr_abs", "mean"]),
        "raw_to_render_hf_abs_ratio_median": nested(summary, ["raw_to_render_hf_abs_ratio", "median"]),
        "runtime_safe": bool(nested(receipt, ["policy", "runtime_safe"], False)),
        "uses_source_raw": bool(nested(receipt, ["policy", "uses_source_raw"], True)),
    }


def summarize_model(path: Path, threshold_pct: float) -> dict[str, Any]:
    receipt = load_json(path)
    config = receipt.get("config") if isinstance(receipt.get("config"), dict) else {}
    holdout_mae = metric(receipt, "holdout", "raw_residual_mae_reduction_pct")
    holdout_rmse = metric(receipt, "holdout", "raw_residual_rmse_reduction_pct")
    train_mae = metric(receipt, "train", "raw_residual_mae_reduction_pct")
    exact_mae = metric(receipt, "holdout", "exact_raw_mae_reduction_pct")
    row = {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": receipt.get("schema"),
        "camera": infer_camera(receipt),
        "holdout_scene": config.get("holdout_scene"),
        "feature_mode": config.get("feature_mode"),
        "model_arch": config.get("model_arch", "residual"),
        "width": config.get("width"),
        "depth": config.get("depth"),
        "patch_size": config.get("patch_size"),
        "steps": config.get("steps", receipt.get("steps")),
        "target_policy": config.get("target_policy", "raw"),
        "sample_balance": config.get("sample_balance", "row"),
        "context_padding": config.get("context_padding", 0),
        "holdout_mae_recovery_pct_median": holdout_mae,
        "holdout_rmse_recovery_pct_median": holdout_rmse,
        "holdout_exact_raw_mae_recovery_pct_median": exact_mae,
        "train_mae_recovery_pct_median": train_mae,
        "runtime_safe_inputs": nested(receipt, ["policy", "uses_source_raw_at_runtime"]) is False,
        "uses_source_raw_at_training": nested(receipt, ["policy", "uses_source_raw_at_training"]) is True,
    }
    row["promotable"] = bool(
        row["runtime_safe_inputs"]
        and holdout_mae is not None
        and holdout_mae >= threshold_pct
        and holdout_rmse is not None
        and holdout_rmse >= 0.0
    )
    return row


def build_gap(target_receipt: Path, model_receipts: list[Path], threshold_pct: float) -> dict[str, Any]:
    target = summarize_target(target_receipt)
    models = [summarize_model(path, threshold_pct) for path in model_receipts if path.exists()]
    models.sort(
        key=lambda row: (
            row["camera"],
            -float(row["holdout_mae_recovery_pct_median"] if row["holdout_mae_recovery_pct_median"] is not None else -999.0),
        )
    )
    by_camera: dict[str, list[dict[str, Any]]] = {}
    for row in models:
        by_camera.setdefault(str(row["camera"]), []).append(row)
    camera_rows = []
    for camera, rows in sorted(by_camera.items()):
        best = max(
            rows,
            key=lambda row: float(
                row["holdout_mae_recovery_pct_median"] if row["holdout_mae_recovery_pct_median"] is not None else -999.0
            ),
        )
        camera_rows.append(
            {
                "camera": camera,
                "candidate_count": len(rows),
                "best_holdout_mae_recovery_pct_median": best["holdout_mae_recovery_pct_median"],
                "best_holdout_rmse_recovery_pct_median": best["holdout_rmse_recovery_pct_median"],
                "best_path": best["path"],
                "passes_threshold": bool(best["promotable"]),
            }
        )
    promotable = bool(models) and all(row["promotable"] for row in models) and bool(camera_rows)
    hard_blockers = []
    if not target["row_count"]:
        hard_blockers.append("raw-CFA residual target receipt has no rows")
    if not target["render_to_raw_corr_abs_median"] or float(target["render_to_raw_corr_abs_median"]) < 0.50:
        hard_blockers.append("rendered review target is weakly correlated with raw-CFA residual target")
    for row in camera_rows:
        if not row["passes_threshold"]:
            hard_blockers.append(
                f"{row['camera']} holdout best median MAE recovery "
                f"{row['best_holdout_mae_recovery_pct_median']:.3f}% is below {threshold_pct:.1f}%"
            )
    if not models:
        hard_blockers.append("no raw-CFA residual model receipts were found")
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "promotion_thresholds": {
            "holdout_mae_recovery_pct_median_min": threshold_pct,
            "holdout_rmse_recovery_pct_median_min": 0.0,
            "runtime_source_raw_allowed": False,
        },
        "production_ready": bool(promotable and not hard_blockers),
        "target": target,
        "camera_summary": camera_rows,
        "models": models,
        "blockers": hard_blockers,
        "next_experiments": [
            {
                "priority": 1,
                "name": "full-image or structured raw-CFA residual learner",
                "purpose": "make X2D and Z8 holdouts strongly positive at the same time; the first small U-Net/multiscale architecture moves the hard X2D holdout barely positive, while X2D-only camera-domain filtering, camera-balanced sampling-only, 32px context-padding, combined stored-HF plus pooled-context features, simple multiscale band-loss, and absolute-position/full-crop scalar frame context all remained below promotion",
                "must_prove": [
                    f"X2D median raw-residual MAE recovery >= {threshold_pct:.1f}%",
                    f"Z8 median raw-residual MAE recovery >= {threshold_pct:.1f}%",
                    "worst rows are non-negative or visually justified in a full still/editor-latitude dashboard",
                ],
            },
            {
                "priority": 2,
                "name": "full-image or routed raw-context residual model",
                "purpose": "replace the current local-tile learner; larger patches, stronger high-residual weighting, simple pooled raw context, stored candidate-HF, stored-HF plus pooled context, multiscale band-loss reweighting, X2D-only train-domain filtering, camera-balanced sampling, 32px context padding, and simple frame-context scalar planes are not sufficient, while a small U-Net was only barely positive and still far below promotion",
                "must_prove": [
                    "uses candidate raw/metadata only at runtime",
                    "beats the local and pooled-context raw-CFA residual baselines on the hard X2D holdout",
                    "keeps Z8 positive while improving X2D",
                ],
            },
            {
                "priority": 3,
                "name": "scene-family routed residual specialists",
                "purpose": "separate X2D high-ISO/latitude scenes from Z8/Mission detail scenes only with a new context/objective; simple camera-domain specialization is already negative on the hard X2D raw-CFA residual holdout",
                "must_prove": [
                    "router uses candidate raw/metadata only",
                    "each routed specialist beats the shared baseline on its holdout family",
                    "router sidecar hashes match checkpoint and feature schema",
                ],
            },
            {
                "priority": 4,
                "name": "full still promotion gate",
                "purpose": "confirm raw-residual gains survive editable DNG/GPR output and rendered latitude review",
                "must_prove": [
                    "50 MP and 100 MP outputs open as editable raw",
                    "visual/detail dashboard beats STILL q0/q3/q8 baselines",
                    "no render-time source/REF content is used",
                ],
            },
        ],
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    target = data["target"]
    camera_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['camera'])}</td>"
        f"<td>{row['candidate_count']}</td>"
        f"<td>{row['best_holdout_mae_recovery_pct_median']:.3f}%</td>"
        f"<td>{row['best_holdout_rmse_recovery_pct_median']:.3f}%</td>"
        f"<td>{'PASS' if row['passes_threshold'] else 'BLOCKED'}</td>"
        f"<td><code>{html.escape(row['best_path'])}</code></td>"
        "</tr>"
        for row in data["camera_summary"]
    )
    model_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['camera'])}</td>"
        f"<td>{html.escape(str(row['holdout_scene']))}</td>"
        f"<td>{html.escape(str(row['model_arch']))}</td>"
        f"<td>{html.escape(str(row['feature_mode']))}</td>"
        f"<td>{html.escape(str(row['sample_balance']))}</td>"
        f"<td>{html.escape(str(row['context_padding']))}</td>"
        f"<td>{html.escape(str(row['target_policy']))}</td>"
        f"<td>{row['holdout_mae_recovery_pct_median']:.3f}%</td>"
        f"<td>{row['holdout_rmse_recovery_pct_median']:.3f}%</td>"
        f"<td>{'yes' if row['runtime_safe_inputs'] else 'no'}</td>"
        f"<td>{'yes' if row['promotable'] else 'no'}</td>"
        "</tr>"
        for row in data["models"]
    )
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    experiments = "".join(
        "<section class='experiment'>"
        f"<h3>{row['priority']}. {html.escape(row['name'])}</h3>"
        f"<p>{html.escape(row['purpose'])}</p>"
        + "<ul>"
        + "".join(f"<li>{html.escape(item)}</li>" for item in row["must_prove"])
        + "</ul></section>"
        for row in data["next_experiments"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premium Still-SR Raw-CFA Residual Gap</title>
  <style>
    body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #12171c; background: #f5f7f8; }}
    main {{ max-width: 1260px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 36px; letter-spacing: 0; }}
    h2 {{ margin: 28px 0 10px; font-size: 23px; }}
    h3 {{ margin: 0 0 6px; font-size: 17px; }}
    code {{ overflow-wrap: anywhere; white-space: normal; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #dce2e7; }}
    th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #edf2f5; color: #52606d; font-size: 12px; text-transform: uppercase; }}
    .hero {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin: 18px 0; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; border-top: 5px solid #1267a3; }}
    .label {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .value {{ font-size: 32px; font-weight: 760; margin-top: 5px; }}
    .blocked {{ border-top-color: #c53b2c; }}
    .experiment {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; margin: 10px 0; }}
    .meta {{ margin-top: 18px; color: #62707d; font-size: 13px; }}
  </style>
</head>
<body>
<main>
  <h1>Premium Still-SR Raw-CFA Residual Gap</h1>
  <p>This dashboard is built from current target and training receipts. It answers whether the expensive still-SR raw-domain model is promotable today, and what evidence has to move next.</p>
  <div class="hero">
    <section class="card blocked"><div class="label">Production ready</div><div class="value">{str(data["production_ready"]).lower()}</div></section>
    <section class="card"><div class="label">Target rows</div><div class="value">{target["row_count"]}</div></section>
    <section class="card"><div class="label">Scenes</div><div class="value">{target["scene_count"]}</div></section>
    <section class="card"><div class="label">Raw/render corr median</div><div class="value">{float(target["render_to_raw_corr_abs_median"] or 0.0):.3f}</div></section>
  </div>

  <h2>Blockers</h2>
  <ul>{blockers or "<li>No blocker recorded.</li>"}</ul>

  <h2>Camera Holdout Summary</h2>
  <table><thead><tr><th>Camera</th><th>Candidates</th><th>Best MAE recovery</th><th>Best RMSE recovery</th><th>Status</th><th>Best receipt</th></tr></thead><tbody>{camera_rows}</tbody></table>

  <h2>Model Receipts</h2>
  <table><thead><tr><th>Camera</th><th>Holdout</th><th>Architecture</th><th>Features</th><th>Sampler</th><th>Context px</th><th>Target policy</th><th>MAE recovery</th><th>RMSE recovery</th><th>Runtime safe</th><th>Promote</th></tr></thead><tbody>{model_rows}</tbody></table>

  <h2>Next Experiments</h2>
  {experiments}

  <p class="meta">JSON: <code>{html.escape(str(json_path))}</code>. Created {html.escape(data["created_utc"])}.</p>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target-receipt", type=Path, default=DEFAULT_TARGET_RECEIPT)
    ap.add_argument("--model-receipt", action="append", type=Path, default=[])
    ap.add_argument("--threshold-pct", type=float, default=15.0)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    receipts = args.model_receipt or DEFAULT_MODEL_RECEIPTS
    data = build_gap(args.target_receipt, receipts, args.threshold_pct)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "raw_cfa_residual_gap.json"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path = args.output_dir / "index.html"
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
