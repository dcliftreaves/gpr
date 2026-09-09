#!/usr/bin/env python3
"""Build the Gate 13 source/objective revision receipt.

The feature-rich Gate 13 smoke proved that a single positive X2D source is not
tail-safe per scene with the tested candidate-only features. This pass changes
the source/objective shape without doing a long train: it tests whether a
multi-source selector can use candidate-only runtime features to choose among
existing X2D source receipts, with exact no-op fallback for every unselected
row and for Z8.
"""
from __future__ import annotations

import argparse
import html
import json
import statistics
import time
from pathlib import Path
from typing import Any

import build_premium_still_sr_gate13_feature_rich_tail_safe_source_smoke as feature_rich
import build_premium_still_sr_gate13_tail_safe_source_smoke as base


SCHEMA = "gpr.premium_still_sr_gate13_source_or_objective_revision.v1"
DEFAULT_OUTPUT_DIR = base.ARTIFACT_ROOT / "premium_still_sr_gate13_source_or_objective_revision_20260702"
DEFAULT_FEATURE_RICH_SMOKE = (
    base.ARTIFACT_ROOT
    / "premium_still_sr_gate13_feature_rich_tail_safe_source_smoke_20260702"
    / "feature_rich_tail_safe_source_smoke.json"
)
SOURCE_SCHEMA = "gpr.premium_still_sr_clean_source_pair_model.v1"


def row_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row["image_id"]), int(row["tile_index"])


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def source_values_for_anchor(path: Path, anchor_keys: list[tuple[str, int]], pairs_name: str) -> dict[str, Any] | None:
    try:
        data = base.load_json(path)
    except Exception:
        return None
    if data.get("schema") != SOURCE_SCHEMA:
        return None
    if Path(str(data.get("pairs", ""))).name != pairs_name:
        return None
    holdout = base.nested(data, ["eval", "holdout"], {})
    rows = holdout.get("rows") if isinstance(holdout, dict) else None
    if not isinstance(rows, list):
        return None
    by_key: dict[tuple[str, int], float] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("image_id") is not None and row.get("tile_index") is not None:
            by_key[(str(row["image_id"]), int(row["tile_index"]))] = as_float(row.get("mae_improvement_pct"))
    if not all(key in by_key for key in anchor_keys):
        return None
    promotion = data.get("promotion") if isinstance(data.get("promotion"), dict) else {}
    eval_mae = holdout.get("mae_improvement_pct") if isinstance(holdout.get("mae_improvement_pct"), dict) else {}
    return {
        "name": path.parent.name,
        "path": str(path),
        "sha256": base.sha256_file(path),
        "values": [by_key[key] for key in anchor_keys],
        "baseline_beaten_on_holdout": bool(promotion.get("baseline_beaten_on_holdout")),
        "median_mae_improvement_pct": as_float(eval_mae.get("median")),
        "worst_row_mae_improvement_pct": as_float(eval_mae.get("min")),
    }


def image_masks(rows: list[dict[str, Any]]) -> dict[str, int]:
    masks: dict[str, int] = {}
    for i, row in enumerate(rows):
        image_id = str(row["image_id"])
        masks[image_id] = masks.get(image_id, 0) | (1 << i)
    return masks


def value_metrics(values: list[float], masks: dict[str, int]) -> dict[str, Any]:
    def stats(local: list[float]) -> dict[str, Any]:
        return {
            "row_count": len(local),
            "selected_row_count": sum(1 for value in local if value > 0.0),
            "min": min(local) if local else None,
            "median": float(statistics.median(local)) if local else None,
            "mean": sum(local) / len(local) if local else None,
            "max": max(local) if local else None,
            "negative_row_count": sum(1 for value in local if value < 0.0),
        }

    out = stats(values)
    out["by_image"] = {}
    for image_id, mask in sorted(masks.items()):
        local = [values[i] for i in range(len(values)) if (mask >> i) & 1]
        out["by_image"][image_id] = stats(local)
    return out


def passes_strict_values(metrics: dict[str, Any], minimum_median: float, minimum_worst: float) -> bool:
    def ok(row: dict[str, Any]) -> bool:
        return (
            row.get("min") is not None
            and row.get("median") is not None
            and float(row["min"]) >= minimum_worst
            and float(row["median"]) > minimum_median
            and int(row.get("negative_row_count") or 0) == 0
        )

    return ok(metrics) and all(ok(row) for row in metrics["by_image"].values())


def build_safe_selector_upper_bound(
    rows: list[dict[str, Any]],
    feature_keys: list[str],
    sources: list[dict[str, Any]],
) -> tuple[list[float], dict[str, int], list[dict[str, Any]]]:
    predicates = feature_rich.predicate_masks(rows, feature_keys)
    best_values = [0.0] * len(rows)
    best_source_index = [-1] * len(rows)
    safe_selector_count = 0
    source_counts = {source["name"]: 0 for source in sources}
    source_safe_predicate_counts = {source["name"]: 0 for source in sources}
    examples: list[dict[str, Any]] = []
    for source_index, source in enumerate(sources):
        values = [float(value) for value in source["values"]]
        neg_mask = 0
        pos_mask = 0
        for i, value in enumerate(values):
            if value < 0.0:
                neg_mask |= 1 << i
            if value > 0.0:
                pos_mask |= 1 << i
        for predicate, mask in predicates:
            if (mask & neg_mask) != 0 or (mask & pos_mask) == 0:
                continue
            safe_selector_count += 1
            source_safe_predicate_counts[source["name"]] += 1
            if len(examples) < 12:
                examples.append(
                    {
                        "source": source["name"],
                        "predicate": predicate,
                        "positive_rows_selected": int((mask & pos_mask).bit_count()),
                    }
                )
            for i, value in enumerate(values):
                if ((mask >> i) & 1) and value > best_values[i]:
                    best_values[i] = value
                    best_source_index[i] = source_index
    for source_index, source in enumerate(sources):
        source_counts[source["name"]] = sum(1 for idx in best_source_index if idx == source_index)
    return best_values, {**source_counts, "_safe_selector_count": safe_selector_count, **{f"{k}__safe_predicates": v for k, v in source_safe_predicate_counts.items()}}, examples


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    anchor = base.load_json(args.anchor_source_receipt)
    feature_receipt = base.load_json(args.feature_rich_smoke)
    rows = [dict(row) for row in base.nested(anchor, ["eval", "holdout", "rows"], []) if isinstance(row, dict)]
    if not rows:
        raise ValueError("anchor source receipt has no eval.holdout.rows")
    pairs_path = args.pairs or Path(str(anchor.get("pairs")))
    if not pairs_path.exists():
        raise FileNotFoundError(pairs_path)
    feature_keys = feature_rich.add_feature_rich_runtime_stats(rows, pairs_path, args.max_input_span_rows)
    anchor_keys = [row_key(row) for row in rows]
    receipt_paths = sorted(args.artifact_root.glob(args.receipt_glob))
    sources = [
        source
        for path in receipt_paths
        if (source := source_values_for_anchor(path, anchor_keys, pairs_path.name)) is not None
    ]
    if not sources:
        raise ValueError("no compatible source receipts found")
    masks = image_masks(rows)
    best_values, source_counts, selector_examples = build_safe_selector_upper_bound(rows, feature_keys, sources)
    metrics = value_metrics(best_values, masks)
    z8 = base.gate12_z8_exact_noop(args.gate12_acceptance)
    z8_ok = bool(z8.get("exact_noop")) and bool(z8.get("passed"))
    upper_bound_passed = passes_strict_values(
        metrics,
        args.minimum_median_mae_improvement_pct,
        args.minimum_worst_row_mae_improvement_pct,
    )
    revision_passed = bool(upper_bound_passed and z8_ok)
    if revision_passed:
        verdict = "gate13_source_or_objective_revision_passed"
        blocker = "none"
        next_action = (
            "Build Gate 14 candidate intake for an executable multi-source selector: persist the selector sidecar, "
            "route source models from candidate-only features, keep no-op fallback, and keep Z8 exact-noop."
        )
    else:
        verdict = "blocked_source_or_objective_revision"
        blocker = "multi_source_runtime_feature_separability_gap" if not upper_bound_passed else "z8_exact_noop_policy_gap"
        next_action = (
            "Do not launch a long run. Revise the source/objective again; the multi-source candidate-only selector "
            "does not satisfy per-image X2D median and worst-row floors with Z8 exact-noop."
        )
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "production_ready": False,
        "source_or_objective_revision_passed": revision_passed,
        "gate14_candidate_intake_allowed": revision_passed,
        "long_run_allowed": False,
        "blocker_classification": blocker,
        "next_unambiguous_action": next_action,
        "acceptance": {
            "minimum_median_mae_improvement_pct": args.minimum_median_mae_improvement_pct,
            "minimum_worst_row_mae_improvement_pct": args.minimum_worst_row_mae_improvement_pct,
            "requires_strict_per_image_positive_median": True,
            "requires_z8_exact_noop": True,
        },
        "inputs": {
            "anchor_source_receipt": {"path": str(args.anchor_source_receipt), "sha256": base.sha256_file(args.anchor_source_receipt)},
            "feature_rich_smoke": {
                "path": str(args.feature_rich_smoke),
                "sha256": base.sha256_file(args.feature_rich_smoke),
                "verdict": feature_receipt.get("verdict"),
            },
            "pairs": {"path": str(pairs_path), "sha256": base.sha256_file(pairs_path)},
            "gate12_acceptance": {"path": str(args.gate12_acceptance), "sha256": base.sha256_file(args.gate12_acceptance)},
        },
        "runtime_policy": {
            "allowed_runtime_inputs": [
                "candidate_raw",
                "camera_metadata",
                "candidate_tile_statistics",
                "candidate_tile_coordinates",
                "candidate_scene_normalized_tile_statistics",
                "multi_source_selector_sidecar",
                "validated_noise_sidecar_optional",
            ],
            "forbidden_runtime_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG", "target_mae", "gate_metric", "oracle_row_label"],
            "tested_revision": "multi-source candidate-only safe selector with exact no-op fallback",
        },
        "feature_summary": {
            "feature_count": len(feature_keys),
            "compatible_source_count": len(sources),
            "safe_selector_count": int(source_counts.get("_safe_selector_count", 0)),
        },
        "z8_policy": z8,
        "multi_source_safe_selector_upper_bound": {
            "passes_strict": upper_bound_passed,
            "metrics": metrics,
            "source_row_contributions": source_counts,
            "selector_examples": selector_examples,
        },
        "compatible_sources": [
            {key: value for key, value in source.items() if key != "values"}
            for source in sources
        ],
        "required_next_receipts": [
            {
                "id": "premium_still_sr_gate14_candidate_intake_<date>",
                "allowed_only_if": "source_or_objective_revision_passed == true",
                "done_when": "The executable selector sidecar reproduces the upper-bound pass with candidate-only runtime inputs and Z8 exact-noop.",
            },
            {
                "id": "premium_still_sr_promotion_receipts",
                "allowed_only_if": "Gate 14 candidate intake and smoke pass, followed by full 15% / 15% promotion validation.",
            },
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            return html.escape(f"{value:.6g}")
        return html.escape(str(value))

    upper = data["multi_source_safe_selector_upper_bound"]
    rows = []
    for image_id, metrics in upper["metrics"]["by_image"].items():
        rows.append(
            "<tr>"
            f"<td>{cell(image_id)}</td>"
            f"<td>{cell(metrics.get('selected_row_count'))}</td>"
            f"<td>{cell(metrics.get('median'))}</td>"
            f"<td>{cell(metrics.get('min'))}</td>"
            f"<td>{cell(metrics.get('max'))}</td>"
            "</tr>"
        )
    examples = "".join(
        "<tr>"
        f"<td>{cell(row.get('source'))}</td>"
        f"<td><code>{cell(row.get('predicate'))}</code></td>"
        f"<td>{cell(row.get('positive_rows_selected'))}</td>"
        "</tr>"
        for row in upper.get("selector_examples", [])
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Premium Still-SR Gate 13 Source/Objective Revision</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#17202a;background:#f7f8fa}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.card{{background:#fff;border:1px solid #d9dee7;border-radius:8px;padding:14px}}
.label{{font-size:12px;text-transform:uppercase;color:#667085;letter-spacing:.04em}}
.value{{font-size:22px;font-weight:700;margin-top:4px}}
table{{border-collapse:collapse;width:100%;background:#fff;margin-top:12px}}
th,td{{border:1px solid #d9dee7;padding:8px;text-align:left;font-size:13px}}
th{{background:#eef2f7}}
code{{background:#eef2f7;padding:2px 4px;border-radius:4px}}
</style></head><body>
<h1>Premium Still-SR Gate 13 Source/Objective Revision</h1>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{cell(data['verdict'])}</div></section>
  <section class="card"><div class="label">Gate 14 intake</div><div class="value">{cell(data['gate14_candidate_intake_allowed'])}</div></section>
  <section class="card"><div class="label">Sources</div><div class="value">{cell(data['feature_summary']['compatible_source_count'])}</div></section>
  <section class="card"><div class="label">Safe selectors</div><div class="value">{cell(data['feature_summary']['safe_selector_count'])}</div></section>
</div>
<h2>Decision</h2>
<p>{html.escape(data['next_unambiguous_action'])}</p>
<h2>Per-Image Upper Bound</h2>
<table><thead><tr><th>Image</th><th>Selected positive rows</th><th>Median MAE %</th><th>Worst MAE %</th><th>Best MAE %</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>Selector Examples</h2>
<table><thead><tr><th>Source</th><th>Predicate</th><th>Positive rows</th></tr></thead><tbody>{examples}</tbody></table>
<pre>{html.escape(json.dumps(upper['metrics'], indent=2))}</pre>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--anchor-source-receipt", type=Path, default=base.DEFAULT_SOURCE_RECEIPT)
    ap.add_argument("--feature-rich-smoke", type=Path, default=DEFAULT_FEATURE_RICH_SMOKE)
    ap.add_argument("--gate12-acceptance", type=Path, default=base.DEFAULT_GATE12_ACCEPTANCE)
    ap.add_argument("--pairs", type=Path)
    ap.add_argument("--artifact-root", type=Path, default=base.ARTIFACT_ROOT)
    ap.add_argument("--receipt-glob", default="premium_still_sr*/train_receipt.json")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--minimum-median-mae-improvement-pct", type=float, default=0.001)
    ap.add_argument("--minimum-worst-row-mae-improvement-pct", type=float, default=0.0)
    ap.add_argument("--max-input-span-rows", type=int, default=4096)
    args = ap.parse_args()
    data = build_receipt(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "source_or_objective_revision.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
