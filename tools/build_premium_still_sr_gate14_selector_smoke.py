#!/usr/bin/env python3
"""Run the Gate 14 Premium still-SR selector through the runtime smoke path.

Gate 14 candidate intake persisted a first-match selector sidecar. This smoke
reloads that sidecar from disk, recomputes candidate-only runtime features,
checks source/checkpoint hashes, executes the selector, and compares the result
against the intake replay. It is intentionally still a pre-promotion gate: a
pass allows full 50 MP / 100 MP promotion validation, not a production claim.
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
import build_premium_still_sr_gate14_candidate_intake as gate14


SCHEMA = "gpr.premium_still_sr_gate14_selector_smoke.v1"
DEFAULT_INTAKE = (
    base.ARTIFACT_ROOT
    / "premium_still_sr_gate14_candidate_intake_20260702"
    / "candidate_preflight.json"
)
DEFAULT_OUTPUT_DIR = base.ARTIFACT_ROOT / "premium_still_sr_gate14_selector_smoke_20260702"
FORBIDDEN_RUNTIME_INPUTS = {
    "REF",
    "source_raw",
    "source_rgb",
    "source_hf",
    "JPEG",
    "target_mae",
    "gate_metric",
    "oracle_row_label",
}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def sha_ok(path: Path, expected: str | None) -> bool:
    return bool(expected) and path.exists() and base.sha256_file(path) == expected


def numbers_equal(a: Any, b: Any, tolerance: float = 1e-9) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False


def compare_metrics(actual: dict[str, Any], expected: dict[str, Any], tolerance: float) -> list[str]:
    failures: list[str] = []
    for key in ("min", "median", "mean", "max", "selected_row_count", "negative_row_count", "row_count"):
        if not numbers_equal(actual.get(key), expected.get(key), tolerance):
            failures.append(f"global metric {key} drifted: actual={actual.get(key)!r} expected={expected.get(key)!r}")
    actual_by = actual.get("by_image") if isinstance(actual.get("by_image"), dict) else {}
    expected_by = expected.get("by_image") if isinstance(expected.get("by_image"), dict) else {}
    if set(actual_by) != set(expected_by):
        failures.append(f"by_image keys drifted: actual={sorted(actual_by)} expected={sorted(expected_by)}")
        return failures
    for image_id in sorted(actual_by):
        actual_row = actual_by[image_id]
        expected_row = expected_by[image_id]
        if not isinstance(actual_row, dict) or not isinstance(expected_row, dict):
            failures.append(f"by_image {image_id} metric row must be an object")
            continue
        for key in ("min", "median", "mean", "max", "selected_row_count", "negative_row_count", "row_count"):
            if not numbers_equal(actual_row.get(key), expected_row.get(key), tolerance):
                failures.append(
                    f"{image_id} metric {key} drifted: actual={actual_row.get(key)!r} expected={expected_row.get(key)!r}"
                )
    return failures


def source_runtime_row(source_meta: dict[str, Any], anchor_keys: list[tuple[str, int]], pairs_name: str) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    source_id = str(source_meta.get("source_id", ""))
    receipt = Path(str(source_meta.get("receipt", "")))
    if not receipt.exists():
        failures.append(f"{source_id}: receipt missing: {receipt}")
        values: dict[str, Any] | None = None
        receipt_data: dict[str, Any] = {}
    else:
        expected_receipt_sha = str(source_meta.get("receipt_sha256") or "")
        if not sha_ok(receipt, expected_receipt_sha):
            failures.append(f"{source_id}: receipt sha256 drift")
        receipt_data = load_json(receipt)
        values = gate13.source_values_for_anchor(receipt, anchor_keys, pairs_name)
        if values is None:
            failures.append(f"{source_id}: receipt cannot reproduce anchor row values")
        elif values.get("name") != source_id:
            failures.append(f"{source_id}: receipt source id drifted to {values.get('name')!r}")

    checkpoint_text = source_meta.get("checkpoint")
    checkpoint = Path(str(checkpoint_text)) if checkpoint_text else None
    checkpoint_readable = False
    checkpoint_sha_actual: str | None = None
    if checkpoint is None:
        failures.append(f"{source_id}: checkpoint path missing")
    elif not checkpoint.exists():
        failures.append(f"{source_id}: checkpoint missing: {checkpoint}")
    else:
        checkpoint_sha_actual = base.sha256_file(checkpoint)
        expected_checkpoint_sha = str(source_meta.get("checkpoint_sha256") or "")
        if checkpoint_sha_actual != expected_checkpoint_sha:
            failures.append(f"{source_id}: checkpoint sha256 drift")
        with checkpoint.open("rb") as f:
            checkpoint_readable = bool(f.read(16) or checkpoint.stat().st_size == 0)

    config = receipt_data.get("config") if isinstance(receipt_data.get("config"), dict) else {}
    if source_meta.get("model_arch") != config.get("model_arch"):
        failures.append(f"{source_id}: model_arch drift")

    return (
        {
            "source_id": source_id,
            "receipt": str(receipt),
            "receipt_sha256_expected": source_meta.get("receipt_sha256"),
            "receipt_sha256_actual": base.sha256_file(receipt) if receipt.exists() else None,
            "checkpoint": str(checkpoint) if checkpoint else None,
            "checkpoint_sha256_expected": source_meta.get("checkpoint_sha256"),
            "checkpoint_sha256_actual": checkpoint_sha_actual,
            "checkpoint_readable": checkpoint_readable,
            "model_arch": source_meta.get("model_arch"),
            "runtime_scope": source_meta.get("runtime_scope"),
            "values": values["values"] if values is not None else [],
        },
        failures,
    )


def execute_selector(rows: list[dict[str, Any]], source_rows: dict[str, dict[str, Any]], sidecar: dict[str, Any]) -> dict[str, Any]:
    values = [0.0] * len(rows)
    selected_sources: list[str | None] = [None] * len(rows)
    selected_rules: list[str | None] = [None] * len(rows)
    fallback_count = 0
    for i, row in enumerate(rows):
        for rule in sidecar["rules"]:
            pred = rule["predicate"]
            predicate = f"{pred['feature']} {pred['op']} {pred['threshold']:.8g}"
            if gate14.predicate_matches(row, predicate):
                source_id = str(rule["source_id"])
                values[i] = float(source_rows[source_id]["values"][i])
                selected_sources[i] = source_id
                selected_rules[i] = str(rule["rule_id"])
                break
        else:
            fallback_count += 1
    return {
        "values": values,
        "selected_sources": selected_sources,
        "selected_rules": selected_rules,
        "assigned_row_count": sum(1 for item in selected_rules if item is not None),
        "fallback_exact_noop_count": fallback_count,
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    intake = load_json(args.intake)
    if intake.get("schema") != gate14.SCHEMA:
        raise ValueError(f"intake schema must be {gate14.SCHEMA}")
    if intake.get("gate14_candidate_intake_passed") is not True:
        raise ValueError("Gate 14 candidate intake must pass before selector smoke")
    sidecar_path = args.sidecar or Path(str(intake.get("selector_sidecar_path", "")))
    sidecar = load_json(sidecar_path)
    sidecar_sha = base.sha256_file(sidecar_path)
    if sidecar_sha != intake.get("selector_sidecar_sha256"):
        raise ValueError("selector sidecar sha256 does not match intake")
    if sidecar.get("schema") != gate14.SIDECAR_SCHEMA:
        raise ValueError(f"selector sidecar schema must be {gate14.SIDECAR_SCHEMA}")

    runtime_policy = sidecar.get("runtime_policy") if isinstance(sidecar.get("runtime_policy"), dict) else {}
    forbidden = set(str(item) for item in runtime_policy.get("forbidden_runtime_inputs", []))
    forbidden_policy_ok = FORBIDDEN_RUNTIME_INPUTS.issubset(forbidden)
    allowed = set(str(item) for item in runtime_policy.get("allowed_runtime_inputs", []))
    allowed_runtime_ok = {"candidate_raw", "camera_metadata"}.issubset(allowed)

    anchor_path = Path(str(intake["inputs"]["anchor_source_receipt"]["path"]))
    anchor = load_json(anchor_path)
    rows = [dict(row) for row in base.nested(anchor, ["eval", "holdout", "rows"], []) if isinstance(row, dict)]
    if not rows:
        raise ValueError("anchor source receipt has no eval.holdout.rows")
    pairs_path = args.pairs or Path(str(intake["inputs"]["pairs"]["path"]))
    feature_keys = feature_rich.add_feature_rich_runtime_stats(rows, pairs_path, args.max_input_span_rows)
    feature_schema_matches = feature_keys == sidecar.get("feature_schema")
    missing_runtime_features = [
        key
        for key in sidecar.get("feature_schema", [])
        if any(key not in row for row in rows)
    ]
    row_forbidden_keys = sorted({key for row in rows for key in row if key in FORBIDDEN_RUNTIME_INPUTS})

    anchor_keys = [gate13.row_key(row) for row in rows]
    source_rows: dict[str, dict[str, Any]] = {}
    source_failures: list[str] = []
    source_checks: list[dict[str, Any]] = []
    for source_meta in sidecar.get("sources", []):
        if not isinstance(source_meta, dict):
            source_failures.append("source metadata row must be an object")
            continue
        row, failures = source_runtime_row(source_meta, anchor_keys, pairs_path.name)
        source_checks.append({key: value for key, value in row.items() if key != "values"})
        source_rows[str(row["source_id"])] = row
        source_failures.extend(failures)
    rule_sources = {str(rule.get("source_id")) for rule in sidecar.get("rules", []) if isinstance(rule, dict)}
    missing_rule_sources = sorted(rule_sources - set(source_rows))
    if missing_rule_sources:
        source_failures.append("rule source(s) missing from sidecar sources: " + ", ".join(missing_rule_sources))

    runtime = execute_selector(rows, source_rows, sidecar)
    metrics = gate13.value_metrics(runtime["values"], gate13.image_masks(rows))
    metrics_passed = gate13.passes_strict_values(
        metrics,
        float(intake["acceptance"]["minimum_median_mae_improvement_pct"]),
        float(intake["acceptance"]["minimum_worst_row_mae_improvement_pct"]),
    )
    replay_drift = compare_metrics(metrics, intake["sidecar_replay_metrics"], args.metric_tolerance)
    z8 = intake.get("z8_policy") if isinstance(intake.get("z8_policy"), dict) else {}
    z8_ok = bool(z8.get("exact_noop")) and bool(z8.get("passed"))
    smoke_passed = bool(
        metrics_passed
        and not replay_drift
        and not source_failures
        and feature_schema_matches
        and not missing_runtime_features
        and not row_forbidden_keys
        and forbidden_policy_ok
        and allowed_runtime_ok
        and z8_ok
    )
    blocker = "none"
    if not smoke_passed:
        if source_failures:
            blocker = "source_model_mapping_or_checkpoint_drift"
        elif not feature_schema_matches or missing_runtime_features:
            blocker = "feature_schema_drift"
        elif replay_drift or not metrics_passed:
            blocker = "selector_reproducibility_gap"
        elif row_forbidden_keys or not forbidden_policy_ok or not allowed_runtime_ok:
            blocker = "runtime_input_policy_gap"
        elif not z8_ok:
            blocker = "z8_exact_noop_policy_gap"
        else:
            blocker = "unknown_selector_smoke_gap"

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": "gate14_selector_smoke_passed" if smoke_passed else "blocked_gate14_selector_smoke",
        "production_ready": False,
        "gate14_selector_smoke_passed": smoke_passed,
        "promotion_gate_allowed": smoke_passed,
        "long_run_allowed": False,
        "blocker_classification": blocker,
        "next_unambiguous_action": (
            "Run the full 50 MP / 100 MP Premium still-SR promotion gate."
            if smoke_passed
            else "Do not promote. Fix selector reproducibility, feature-schema drift, source mapping, or checkpoint drift."
        ),
        "inputs": {
            "gate14_intake": {"path": str(args.intake), "sha256": base.sha256_file(args.intake)},
            "selector_sidecar": {"path": str(sidecar_path), "sha256": sidecar_sha},
            "anchor_source_receipt": {"path": str(anchor_path), "sha256": base.sha256_file(anchor_path)},
            "pairs": {"path": str(pairs_path), "sha256": base.sha256_file(pairs_path)},
        },
        "runtime_policy": {
            "allowed_runtime_inputs_ok": allowed_runtime_ok,
            "forbidden_runtime_inputs_ok": forbidden_policy_ok,
            "row_forbidden_keys": row_forbidden_keys,
            "fallback": runtime_policy.get("fallback"),
            "rule_resolution": runtime_policy.get("rule_resolution"),
        },
        "feature_schema": {
            "feature_count": len(feature_keys),
            "matches_sidecar": feature_schema_matches,
            "missing_runtime_features": missing_runtime_features,
        },
        "source_model_checks": source_checks,
        "source_model_failures": source_failures,
        "selector_execution": {
            "selector_id": sidecar.get("selector_id"),
            "rule_count": len(sidecar.get("rules", [])),
            "source_count": len(sidecar.get("sources", [])),
            "assigned_row_count": runtime["assigned_row_count"],
            "fallback_exact_noop_count": runtime["fallback_exact_noop_count"],
            "selected_source_counts": {
                source_id: runtime["selected_sources"].count(source_id)
                for source_id in sorted(set(item for item in runtime["selected_sources"] if item is not None))
            },
        },
        "selector_smoke_metrics": metrics,
        "selector_replay_matches_intake": not replay_drift,
        "selector_replay_drift": replay_drift,
        "z8_policy": z8,
    }


def render_html(data: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            return html.escape(f"{value:.6g}")
        return html.escape(str(value))

    cards = [
        ("Verdict", data["verdict"]),
        ("Promotion gate allowed", data["promotion_gate_allowed"]),
        ("Rules", data["selector_execution"]["rule_count"]),
        ("Assigned rows", data["selector_execution"]["assigned_row_count"]),
        ("Fallback no-op rows", data["selector_execution"]["fallback_exact_noop_count"]),
    ]
    metric_rows = []
    for image_id, metrics in data["selector_smoke_metrics"]["by_image"].items():
        metric_rows.append(
            "<tr>"
            f"<td>{cell(image_id)}</td>"
            f"<td>{cell(metrics.get('selected_row_count'))}</td>"
            f"<td>{cell(metrics.get('median'))}</td>"
            f"<td>{cell(metrics.get('min'))}</td>"
            f"<td>{cell(metrics.get('negative_row_count'))}</td>"
            "</tr>"
        )
    source_rows = []
    for source in data["source_model_checks"]:
        source_rows.append(
            "<tr>"
            f"<td>{cell(source.get('source_id'))}</td>"
            f"<td>{cell(source.get('model_arch'))}</td>"
            f"<td>{cell(source.get('checkpoint_readable'))}</td>"
            f"<td><code>{cell(source.get('checkpoint_sha256_actual'))}</code></td>"
            "</tr>"
        )
    card_html = "".join(
        f'<section class="card"><div class="label">{html.escape(label)}</div><div class="value">{cell(value)}</div></section>'
        for label, value in cards
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Premium Still-SR Gate 14 Selector Smoke</title>
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
<h1>Premium Still-SR Gate 14 Selector Smoke</h1>
<div class="grid">{card_html}</div>
<h2>Decision</h2>
<p>{html.escape(data['next_unambiguous_action'])}</p>
<h2>Per-Image Metrics</h2>
<table><thead><tr><th>Image</th><th>Selected rows</th><th>Median MAE %</th><th>Worst MAE %</th><th>Negative rows</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table>
<h2>Source Model Checks</h2>
<table><thead><tr><th>Source</th><th>Model arch</th><th>Checkpoint readable</th><th>Checkpoint sha256</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table>
<h2>Smoke Receipt</h2>
<pre>{html.escape(json.dumps(data, indent=2))}</pre>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--intake", type=Path, default=DEFAULT_INTAKE)
    ap.add_argument("--sidecar", type=Path)
    ap.add_argument("--pairs", type=Path)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--max-input-span-rows", type=int, default=4096)
    ap.add_argument("--metric-tolerance", type=float, default=1e-9)
    ap.add_argument("--require-pass", action="store_true")
    args = ap.parse_args()
    data = build_receipt(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "selector_smoke.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    if args.require_pass and not data["gate14_selector_smoke_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
