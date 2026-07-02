#!/usr/bin/env python3
"""Build the Gate 14 executable Premium still-SR selector intake.

Gate 13 proved a multi-source selector upper bound can clear the X2D per-scene
tail gate. Gate 14 turns that into an executable first-match decision list:
candidate-only features choose a source model or exact no-op. The sidecar may
contain rules learned from receipts, but render-time inputs remain candidate
raw/metadata/features only.
"""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any

import build_premium_still_sr_gate13_feature_rich_tail_safe_source_smoke as feature_rich
import build_premium_still_sr_gate13_source_or_objective_revision as gate13
import build_premium_still_sr_gate13_tail_safe_source_smoke as base


SCHEMA = "gpr.premium_still_sr_gate14_candidate_intake.v1"
SIDECAR_SCHEMA = "gpr.premium_still_sr_multi_source_selector_sidecar.v1"
DEFAULT_GATE13_REVISION = (
    base.ARTIFACT_ROOT
    / "premium_still_sr_gate13_source_or_objective_revision_20260702"
    / "source_or_objective_revision.json"
)
DEFAULT_OUTPUT_DIR = base.ARTIFACT_ROOT / "premium_still_sr_gate14_candidate_intake_20260702"


def parse_predicate(text: str) -> tuple[str, str, float]:
    parts = text.split()
    if len(parts) != 3 or parts[1] not in {">=", "<="}:
        raise ValueError(f"unsupported predicate {text!r}")
    return parts[0], parts[1], float(parts[2])


def predicate_matches(row: dict[str, Any], predicate: str) -> bool:
    key, op, threshold = parse_predicate(predicate)
    value = float(row[key])
    return value >= threshold if op == ">=" else value <= threshold


def source_runtime_metadata(source: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(source["path"]))
    try:
        data = base.load_json(path)
    except Exception:
        data = {}
    checkpoint = data.get("checkpoint")
    checkpoint_path = Path(str(checkpoint)) if checkpoint else None
    checkpoint_sha256 = data.get("checkpoint_sha256")
    if checkpoint_path and checkpoint_path.exists() and not checkpoint_sha256:
        checkpoint_sha256 = base.sha256_file(checkpoint_path)
    config = data.get("config") if isinstance(data.get("config"), dict) else {}
    return {
        "source_id": source["name"],
        "receipt": str(path),
        "receipt_sha256": source["sha256"],
        "checkpoint": str(checkpoint_path) if checkpoint_path else None,
        "checkpoint_sha256": checkpoint_sha256,
        "model_arch": config.get("model_arch"),
        "runtime_scope": "candidate_raw_to_restored_raw",
    }


def build_safe_selector_items(rows: list[dict[str, Any]], feature_keys: list[str], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    predicates = feature_rich.predicate_masks(rows, feature_keys)
    items: list[dict[str, Any]] = []
    for source_index, source in enumerate(sources):
        values = [float(value) for value in source["values"]]
        non_positive_mask = 0
        pos_mask = 0
        for i, value in enumerate(values):
            if value <= 0.0:
                non_positive_mask |= 1 << i
            if value > 0.0:
                pos_mask |= 1 << i
        for predicate, mask in predicates:
            if (mask & non_positive_mask) != 0 or (mask & pos_mask) == 0:
                continue
            positive_rows = int((mask & pos_mask).bit_count())
            gain = sum(values[i] for i in range(len(rows)) if ((mask >> i) & 1) and values[i] > 0.0)
            items.append(
                {
                    "source_index": source_index,
                    "source_id": source["name"],
                    "predicate": predicate,
                    "mask": mask,
                    "values": values,
                    "positive_rows": positive_rows,
                    "gain": gain,
                }
            )
    return items


def search_decision_list(
    rows: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    feature_keys: list[str],
    minimum_median: float,
    minimum_worst: float,
    max_rules: int,
) -> dict[str, Any]:
    masks = gate13.image_masks(rows)
    items = build_safe_selector_items(rows, feature_keys, sources)
    assigned = [False] * len(rows)
    selected_values = [0.0] * len(rows)
    selected_rules: list[dict[str, Any]] = []

    def metrics(values: list[float]) -> dict[str, Any]:
        return gate13.value_metrics(values, masks)

    def passes(values: list[float]) -> bool:
        return gate13.passes_strict_values(metrics(values), minimum_median, minimum_worst)

    for _step in range(max_rules):
        if passes(selected_values):
            break
        best_item: dict[str, Any] | None = None
        best_score: tuple[Any, ...] | None = None
        best_values: list[float] | None = None
        for item in items:
            if item in selected_rules:
                continue
            candidate_values = list(selected_values)
            new_positive = 0
            new_gain = 0.0
            for i, value in enumerate(item["values"]):
                if not assigned[i] and ((int(item["mask"]) >> i) & 1):
                    candidate_values[i] = float(value)
                    if value > 0.0:
                        new_positive += 1
                        new_gain += float(value)
            if new_positive == 0:
                continue
            candidate_metrics = metrics(candidate_values)
            per_image = candidate_metrics["by_image"]
            score = (
                min(int(row["selected_row_count"]) for row in per_image.values()),
                sum(int(row["selected_row_count"]) for row in per_image.values()),
                min(float(row["median"]) for row in per_image.values()),
                float(candidate_metrics["median"]),
                new_gain,
                new_positive,
            )
            if best_score is None or score > best_score:
                best_score = score
                best_item = item
                best_values = candidate_values
        if best_item is None or best_values is None:
            break
        selected_rules.append(best_item)
        for i, value in enumerate(best_item["values"]):
            if not assigned[i] and ((int(best_item["mask"]) >> i) & 1):
                assigned[i] = True
                selected_values[i] = float(value)

    compact_rules: list[dict[str, Any]] = []
    for order, item in enumerate(selected_rules):
        key, op, threshold = parse_predicate(str(item["predicate"]))
        compact_rules.append(
            {
                "order": order,
                "source_id": item["source_id"],
                "predicate": {"feature": key, "op": op, "threshold": threshold},
                "predicate_text": item["predicate"],
                "positive_rows_in_training_receipt": item["positive_rows"],
            }
        )
    return {
        "rules": compact_rules,
        "metrics": metrics(selected_values),
        "passed": passes(selected_values),
        "safe_selector_count": len(items),
        "selected_rule_count": len(compact_rules),
    }


def apply_sidecar(rows: list[dict[str, Any]], sources: list[dict[str, Any]], sidecar: dict[str, Any]) -> dict[str, Any]:
    source_map = {source["name"]: source for source in sources}
    values = [0.0] * len(rows)
    assigned_rule: list[str | None] = [None] * len(rows)
    for i, row in enumerate(rows):
        for rule in sidecar["rules"]:
            pred = rule["predicate"]
            predicate = f"{pred['feature']} {pred['op']} {pred['threshold']:.8g}"
            if predicate_matches(row, predicate):
                source = source_map[str(rule["source_id"])]
                values[i] = float(source["values"][i])
                assigned_rule[i] = str(rule["rule_id"])
                break
    return {
        "values": values,
        "assigned_rule_count": sum(1 for item in assigned_rule if item is not None),
        "assigned_rules": assigned_rule,
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    gate13_receipt = base.load_json(args.gate13_revision)
    if not gate13_receipt.get("source_or_objective_revision_passed"):
        raise ValueError("Gate 13 source/objective revision must pass before Gate 14 intake")
    anchor_path = Path(str(gate13_receipt["inputs"]["anchor_source_receipt"]["path"]))
    anchor = base.load_json(anchor_path)
    rows = [dict(row) for row in base.nested(anchor, ["eval", "holdout", "rows"], []) if isinstance(row, dict)]
    if not rows:
        raise ValueError("anchor source receipt has no eval.holdout.rows")
    pairs_path = args.pairs or Path(str(anchor.get("pairs")))
    feature_keys = feature_rich.add_feature_rich_runtime_stats(rows, pairs_path, args.max_input_span_rows)
    anchor_keys = [gate13.row_key(row) for row in rows]
    sources = [
        source
        for path in sorted(args.artifact_root.glob(args.receipt_glob))
        if (source := gate13.source_values_for_anchor(path, anchor_keys, pairs_path.name)) is not None
    ]
    if not sources:
        raise ValueError("no compatible sources found")
    decision = search_decision_list(
        rows,
        sources,
        feature_keys,
        args.minimum_median_mae_improvement_pct,
        args.minimum_worst_row_mae_improvement_pct,
        args.max_rules,
    )
    source_ids = sorted({rule["source_id"] for rule in decision["rules"]})
    sidecar = {
        "schema": SIDECAR_SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "selector_id": "premium_still_sr_gate14_multi_source_selector_v1",
        "runtime_policy": {
            "allowed_runtime_inputs": [
                "candidate_raw",
                "camera_metadata",
                "candidate_tile_statistics",
                "candidate_tile_coordinates",
                "candidate_scene_normalized_tile_statistics",
                "validated_noise_sidecar_optional",
            ],
            "forbidden_runtime_inputs": [
                "REF",
                "source_raw",
                "source_rgb",
                "source_hf",
                "JPEG",
                "target_mae",
                "gate_metric",
                "oracle_row_label",
            ],
            "fallback": "exact_noop",
            "rule_resolution": "first_match_wins",
        },
        "feature_schema": feature_keys,
        "sources": [source_runtime_metadata(source) for source in sources if source["name"] in source_ids],
        "rules": [
            {
                **rule,
                "rule_id": f"rule_{rule['order']:03d}",
            }
            for rule in decision["rules"]
        ],
    }
    replay = apply_sidecar(rows, sources, sidecar)
    replay_metrics = gate13.value_metrics(replay["values"], gate13.image_masks(rows))
    replay_passed = gate13.passes_strict_values(
        replay_metrics,
        args.minimum_median_mae_improvement_pct,
        args.minimum_worst_row_mae_improvement_pct,
    )
    z8 = base.gate12_z8_exact_noop(Path(str(gate13_receipt["inputs"]["gate12_acceptance"]["path"])))
    z8_ok = bool(z8.get("exact_noop")) and bool(z8.get("passed"))
    intake_passed = bool(decision["passed"] and replay_passed and z8_ok)
    if intake_passed:
        verdict = "gate14_candidate_intake_passed"
        blocker = "none"
        next_action = "Run the Gate 14 executable selector smoke/promotion path, then full 50 MP / 100 MP Premium still-SR promotion validation."
    else:
        verdict = "blocked_gate14_candidate_intake"
        blocker = "selector_replay_gap" if decision["passed"] and not replay_passed else "selector_search_gap"
        next_action = "Do not launch long training. Fix selector reproducibility, source mapping, or feature-schema drift."
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "production_ready": False,
        "gate14_candidate_intake_passed": intake_passed,
        "selector_smoke_allowed": intake_passed,
        "long_run_allowed": False,
        "blocker_classification": blocker,
        "next_unambiguous_action": next_action,
        "acceptance": {
            "minimum_median_mae_improvement_pct": args.minimum_median_mae_improvement_pct,
            "minimum_worst_row_mae_improvement_pct": args.minimum_worst_row_mae_improvement_pct,
            "requires_strict_per_image_positive_median": True,
            "requires_z8_exact_noop": True,
            "requires_sidecar_replay": True,
        },
        "inputs": {
            "gate13_revision": {"path": str(args.gate13_revision), "sha256": base.sha256_file(args.gate13_revision)},
            "anchor_source_receipt": {"path": str(anchor_path), "sha256": base.sha256_file(anchor_path)},
            "pairs": {"path": str(pairs_path), "sha256": base.sha256_file(pairs_path)},
        },
        "selector_sidecar": sidecar,
        "selector_sidecar_summary": {
            "selector_id": sidecar["selector_id"],
            "rule_count": len(sidecar["rules"]),
            "source_count": len(sidecar["sources"]),
            "feature_count": len(feature_keys),
            "safe_selector_count": decision["safe_selector_count"],
            "assigned_row_count": replay["assigned_rule_count"],
        },
        "decision_list_metrics": decision["metrics"],
        "sidecar_replay_metrics": replay_metrics,
        "sidecar_replay_passed": replay_passed,
        "z8_policy": z8,
        "required_next_receipts": [
            {
                "id": "premium_still_sr_gate14_selector_smoke_<date>",
                "allowed_only_if": "gate14_candidate_intake_passed == true",
                "done_when": "The sidecar is executed through the actual model-loading/render path and reproduces this candidate-only X2D/Z8 gate.",
            },
            {
                "id": "premium_still_sr_promotion_receipts",
                "allowed_only_if": "Gate 14 selector smoke passes.",
            },
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            return html.escape(f"{value:.6g}")
        return html.escape(str(value))

    rows = []
    for image_id, metrics in data["sidecar_replay_metrics"]["by_image"].items():
        rows.append(
            "<tr>"
            f"<td>{cell(image_id)}</td>"
            f"<td>{cell(metrics.get('selected_row_count'))}</td>"
            f"<td>{cell(metrics.get('median'))}</td>"
            f"<td>{cell(metrics.get('min'))}</td>"
            f"<td>{cell(metrics.get('max'))}</td>"
            "</tr>"
        )
    rules = []
    for rule in data["selector_sidecar"]["rules"]:
        rules.append(
            "<tr>"
            f"<td>{cell(rule.get('order'))}</td>"
            f"<td>{cell(rule.get('source_id'))}</td>"
            f"<td><code>{cell(rule.get('predicate_text'))}</code></td>"
            f"<td>{cell(rule.get('positive_rows_in_training_receipt'))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Premium Still-SR Gate 14 Candidate Intake</title>
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
<h1>Premium Still-SR Gate 14 Candidate Intake</h1>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{cell(data['verdict'])}</div></section>
  <section class="card"><div class="label">Rules</div><div class="value">{cell(data['selector_sidecar_summary']['rule_count'])}</div></section>
  <section class="card"><div class="label">Sources</div><div class="value">{cell(data['selector_sidecar_summary']['source_count'])}</div></section>
  <section class="card"><div class="label">Replay pass</div><div class="value">{cell(data['sidecar_replay_passed'])}</div></section>
</div>
<h2>Decision</h2>
<p>{html.escape(data['next_unambiguous_action'])}</p>
<h2>Sidecar Replay Metrics</h2>
<table><thead><tr><th>Image</th><th>Selected rows</th><th>Median MAE %</th><th>Worst MAE %</th><th>Best MAE %</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Decision List</h2>
<table><thead><tr><th>Order</th><th>Source</th><th>Predicate</th><th>Positive rows in source receipt</th></tr></thead><tbody>{''.join(rules)}</tbody></table>
<pre>{html.escape(json.dumps(data['sidecar_replay_metrics'], indent=2))}</pre>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate13-revision", type=Path, default=DEFAULT_GATE13_REVISION)
    ap.add_argument("--pairs", type=Path)
    ap.add_argument("--artifact-root", type=Path, default=base.ARTIFACT_ROOT)
    ap.add_argument("--receipt-glob", default="premium_still_sr*/train_receipt.json")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--minimum-median-mae-improvement-pct", type=float, default=0.001)
    ap.add_argument("--minimum-worst-row-mae-improvement-pct", type=float, default=0.0)
    ap.add_argument("--max-input-span-rows", type=int, default=4096)
    ap.add_argument("--max-rules", type=int, default=16)
    args = ap.parse_args()
    data = build_receipt(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output_dir / "candidate_preflight.json"
    sidecar_path = args.output_dir / "selector_sidecar.json"
    html_path = args.output_dir / "index.html"
    receipt = dict(data)
    receipt["selector_sidecar_path"] = str(sidecar_path)
    receipt["selector_sidecar_sha256"] = None
    sidecar_path.write_text(json.dumps(data["selector_sidecar"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["selector_sidecar_sha256"] = base.sha256_file(sidecar_path)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
