#!/usr/bin/env python3
"""Build the Gate 13 feature-rich tail-safe source smoke receipt.

The prior Gate 13 tail-safe smoke proved that simple candidate tile statistics
can make the best X2D source safe only in aggregate. This smoke expands the
runtime-allowed feature family to include scene-normalized tile statistics,
tile coordinates, and texture ratios, then checks whether even the safe-feature
upper bound can keep every X2D scene median positive without selecting any
known-regressing row.
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import math
import statistics
import struct
import time
import zipfile
from pathlib import Path
from typing import Any

import build_premium_still_sr_gate13_tail_safe_source_smoke as base


SCHEMA = "gpr.premium_still_sr_gate13_feature_rich_tail_safe_source_smoke.v1"
DEFAULT_OUTPUT_DIR = base.ARTIFACT_ROOT / "premium_still_sr_gate13_feature_rich_tail_safe_source_smoke_20260702"
TEXTURE_RATIO_PAIRS = (
    ("grad_mean", "range"),
    ("lap_mean", "range"),
    ("std", "range"),
    ("grad_mean", "std"),
    ("lap_mean", "std"),
    ("ch_mean_spread", "std"),
    ("ch_std_max", "std"),
    ("ch_range_max", "range"),
)


def read_meta(npz_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(npz_path) as z:
        if "meta.npy" not in z.namelist():
            return {}
        with z.open("meta.npy") as f:
            magic = f.read(6)
            if magic != b"\x93NUMPY":
                raise ValueError("meta.npy has invalid NPY magic")
            version = f.read(2)
            if version == b"\x01\x00":
                header_len = struct.unpack("<H", f.read(2))[0]
            elif version in {b"\x02\x00", b"\x03\x00"}:
                header_len = struct.unpack("<I", f.read(4))[0]
            else:
                raise ValueError(f"unsupported meta.npy NPY version {version!r}")
            header = ast.literal_eval(f.read(header_len).decode("latin1").strip())
            if not isinstance(header, dict):
                raise ValueError("meta.npy header must be a dict")
            raw = f.read()
    descr = str(header.get("descr", ""))
    if descr.startswith("<U"):
        text = raw.decode("utf-32le").rstrip("\x00")
    elif descr.startswith("|S"):
        text = raw.rstrip(b"\x00").decode("utf-8")
    else:
        return {}
    data = json.loads(text)
    return data if isinstance(data, dict) else {}


def add_feature_rich_runtime_stats(rows: list[dict[str, Any]], pairs_path: Path, max_span_rows: int) -> list[str]:
    features = base.input_features_from_npz(pairs_path, [int(row["tile_index"]) for row in rows], max_span_rows)
    meta = read_meta(pairs_path)
    tiles = meta.get("tiles") if isinstance(meta.get("tiles"), list) else []
    images = {
        str(row.get("image_id")): row
        for row in meta.get("images", [])
        if isinstance(row, dict) and row.get("image_id") is not None
    }
    feature_keys = list(base.FEATURE_KEYS)
    coordinate_keys = [
        "low_x_norm",
        "low_y_norm",
        "high_x_norm",
        "high_y_norm",
        "low_radius_norm",
        "low_xy_sum",
        "low_xy_diff",
    ]
    for row in rows:
        tile_index = int(row["tile_index"])
        row.update(features[tile_index])
        tile = tiles[tile_index] if 0 <= tile_index < len(tiles) and isinstance(tiles[tile_index], dict) else {}
        image = images.get(str(tile.get("image_id") or row.get("image_id")), {})
        low_width = float(image.get("low_width") or 1.0)
        low_height = float(image.get("low_height") or 1.0)
        high_width = float(image.get("high_width") or low_width * 2.0 or 1.0)
        high_height = float(image.get("high_height") or low_height * 2.0 or 1.0)
        low_x = float(tile.get("low_x") or 0.0)
        low_y = float(tile.get("low_y") or 0.0)
        high_x = float(tile.get("high_x") or low_x * 2.0)
        high_y = float(tile.get("high_y") or low_y * 2.0)
        row["low_x_norm"] = low_x / max(1.0, low_width)
        row["low_y_norm"] = low_y / max(1.0, low_height)
        row["high_x_norm"] = high_x / max(1.0, high_width)
        row["high_y_norm"] = high_y / max(1.0, high_height)
        row["low_radius_norm"] = math.sqrt((row["low_x_norm"] - 0.5) ** 2 + (row["low_y_norm"] - 0.5) ** 2)
        row["low_xy_sum"] = row["low_x_norm"] + row["low_y_norm"]
        row["low_xy_diff"] = row["low_x_norm"] - row["low_y_norm"]
    feature_keys.extend(coordinate_keys)
    by_image: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_image.setdefault(str(row["image_id"]), []).append(row)
    for key in base.FEATURE_KEYS:
        feature_keys.extend([f"{key}_img_z", f"{key}_img_center", f"{key}_img_minmax", f"{key}_img_rank"])
        for image_rows in by_image.values():
            values = [float(row[key]) for row in image_rows]
            mean = sum(values) / len(values)
            std = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values)) or 1.0
            med = statistics.median(values)
            sorted_values = sorted(values)
            span = sorted_values[-1] - sorted_values[0] or 1.0
            for row in image_rows:
                value = float(row[key])
                below = sum(1 for v in sorted_values if v < value)
                equal = sum(1 for v in sorted_values if v == value)
                row[f"{key}_img_z"] = (value - mean) / std
                row[f"{key}_img_center"] = (value - med) / (abs(med) + 1e-6)
                row[f"{key}_img_minmax"] = (value - sorted_values[0]) / span
                row[f"{key}_img_rank"] = (below + (equal - 1) / 2.0) / (len(sorted_values) - 1) if len(sorted_values) > 1 else 0.0
    for num, den in TEXTURE_RATIO_PAIRS:
        for key in (f"{num}_over_{den}", f"{num}_minus_{den}"):
            feature_keys.append(key)
        for row in rows:
            row[f"{num}_over_{den}"] = float(row[num]) / (float(row[den]) + 1e-6)
            row[f"{num}_minus_{den}"] = float(row[num]) - float(row[den])
    return feature_keys


def predicate_masks(rows: list[dict[str, Any]], feature_keys: list[str]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    seen_masks: set[int] = {0}
    for key in feature_keys:
        values = sorted({float(row[key]) for row in rows})
        if not values:
            continue
        thresholds = [values[0] - 1.0] + [(a + b) / 2.0 for a, b in zip(values, values[1:])] + [values[-1] + 1.0]
        for op in (">=", "<="):
            for threshold in thresholds:
                mask = 0
                for i, row in enumerate(rows):
                    value = float(row[key])
                    if (value >= threshold) if op == ">=" else (value <= threshold):
                        mask |= 1 << i
                if mask in seen_masks:
                    continue
                seen_masks.add(mask)
                out.append((f"{key} {op} {threshold:.8g}", mask))
    return out


def positive_counts(mask: int, image_pos_masks: dict[str, int]) -> dict[str, int]:
    return {image_id: int((mask & pos_mask).bit_count()) for image_id, pos_mask in sorted(image_pos_masks.items())}


def find_compact_safe_or(
    rows: list[dict[str, Any]],
    safe_predicates: list[tuple[str, int]],
    image_masks: dict[str, int],
    image_pos_masks: dict[str, int],
    minimum_median: float,
    minimum_worst: float,
    max_rule_terms: int,
    beam_width: int,
) -> dict[str, Any] | None:
    needs = {image_id: mask.bit_count() // 2 for image_id, mask in image_masks.items()}

    def enough(mask: int) -> bool:
        return all((mask & image_pos_masks[image_id]).bit_count() >= need for image_id, need in needs.items())

    def score(mask: int) -> int:
        counts = positive_counts(mask, image_pos_masks)
        return min(counts.values()) * 1000 + sum(counts.values())

    beam: list[tuple[int, tuple[str, ...], int]] = [(0, (), 0)]
    seen_masks = {0}
    best: dict[str, Any] | None = None
    for _depth in range(1, max_rule_terms + 1):
        next_beam: list[tuple[int, tuple[str, ...], int]] = []
        for _score, names, mask in beam:
            for name, pred_mask in safe_predicates:
                combined = mask | pred_mask
                if combined == mask or combined in seen_masks:
                    continue
                seen_masks.add(combined)
                combined_names = names + (name,)
                if enough(combined):
                    metrics = base.mask_metrics(rows, combined, image_masks)
                    if base.passes_strict(metrics, minimum_median, minimum_worst):
                        item = {"rule": " OR ".join(f"({name})" for name in combined_names), "term_count": len(combined_names), "metrics": metrics}
                        if best is None or (item["term_count"], -float(item["metrics"]["median"])) < (
                            int(best["term_count"]),
                            -float(best["metrics"]["median"]),
                        ):
                            best = item
                next_beam.append((score(combined), combined_names, combined))
        next_beam.sort(key=lambda item: item[0], reverse=True)
        beam = next_beam[:beam_width]
        if best is not None:
            return best
        if not beam:
            return None
    return best


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    source = base.load_json(args.source_receipt)
    rows = [dict(row) for row in base.nested(source, ["eval", "holdout", "rows"], []) if isinstance(row, dict)]
    if not rows:
        raise ValueError("source receipt has no eval.holdout.rows")
    pairs_path = args.pairs or Path(str(source.get("pairs")))
    if not pairs_path.exists():
        raise FileNotFoundError(pairs_path)
    feature_keys = add_feature_rich_runtime_stats(rows, pairs_path, args.max_input_span_rows)
    neg_mask, _pos_mask, image_masks, image_pos_masks = base.build_masks(rows)
    predicates = predicate_masks(rows, feature_keys)
    safe_predicates = [(name, mask) for name, mask in predicates if (mask & neg_mask) == 0 and any(mask & pos for pos in image_pos_masks.values())]
    safe_predicates.sort(
        key=lambda item: (
            min(positive_counts(item[1], image_pos_masks).values()),
            sum(positive_counts(item[1], image_pos_masks).values()),
        ),
        reverse=True,
    )
    safe_union_mask = 0
    for _name, mask in safe_predicates:
        safe_union_mask |= mask
    safe_union_metrics = base.mask_metrics(rows, safe_union_mask, image_masks)
    compact = find_compact_safe_or(
        rows,
        safe_predicates[: args.max_safe_predicates_for_compact_search],
        image_masks,
        image_pos_masks,
        args.minimum_median_mae_improvement_pct,
        args.minimum_worst_row_mae_improvement_pct,
        args.max_rule_terms,
        args.beam_width,
    )
    z8 = base.gate12_z8_exact_noop(args.gate12_acceptance)
    z8_ok = bool(z8.get("exact_noop")) and bool(z8.get("passed"))
    union_passes = base.passes_strict(
        safe_union_metrics,
        args.minimum_median_mae_improvement_pct,
        args.minimum_worst_row_mae_improvement_pct,
    )
    smoke_passed = bool(compact and z8_ok)
    if smoke_passed:
        verdict = "gate13_feature_rich_tail_safe_source_smoke_passed"
        blocker = "none"
        next_action = "Build Gate 14 candidate intake from the compact feature-rich runtime gate and keep Z8 exact-noop."
    elif not union_passes:
        verdict = "blocked_feature_rich_runtime_gate_upper_bound_insufficient"
        blocker = "runtime_feature_separability_gap"
        next_action = (
            "Do not launch a long run. Even the safe-feature OR upper bound cannot keep every X2D scene median positive; "
            "change the source/model/objective or add stronger candidate-only runtime evidence."
        )
    else:
        verdict = "blocked_compact_runtime_gate_search_insufficient"
        blocker = "compact_rule_search_gap"
        next_action = "Do not launch a long run until a compact deterministic runtime rule is found for the passing feature-rich upper bound."
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": verdict,
        "production_ready": False,
        "smoke_gate_passed": smoke_passed,
        "long_run_allowed": smoke_passed,
        "gate14_candidate_intake_allowed": smoke_passed,
        "blocker_classification": blocker,
        "next_unambiguous_action": next_action,
        "acceptance": {
            "minimum_median_mae_improvement_pct": args.minimum_median_mae_improvement_pct,
            "minimum_worst_row_mae_improvement_pct": args.minimum_worst_row_mae_improvement_pct,
            "requires_strict_per_image_positive_median": True,
            "requires_z8_exact_noop": True,
        },
        "inputs": {
            "source_receipt": {"path": str(args.source_receipt), "sha256": base.sha256_file(args.source_receipt)},
            "pairs": {"path": str(pairs_path), "sha256": base.sha256_file(pairs_path)},
            "gate12_acceptance": {"path": str(args.gate12_acceptance), "sha256": base.sha256_file(args.gate12_acceptance)},
            "previous_tail_safe_smoke": {
                "path": str(args.previous_tail_safe_smoke),
                "sha256": base.sha256_file(args.previous_tail_safe_smoke) if args.previous_tail_safe_smoke.exists() else None,
            },
        },
        "runtime_policy": {
            "allowed_runtime_inputs": [
                "candidate_raw",
                "camera_metadata",
                "candidate_tile_statistics",
                "candidate_tile_coordinates",
                "candidate_scene_normalized_tile_statistics",
                "validated_noise_sidecar_optional",
            ],
            "forbidden_runtime_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG", "target_mae", "gate_metric", "oracle_row_label"],
            "tested_gate_family": "safe monotone OR of threshold predicates over feature-rich candidate-only tile statistics with exact no-op fallback",
        },
        "feature_summary": {
            "feature_count": len(feature_keys),
            "predicate_count": len(predicates),
            "safe_predicate_count": len(safe_predicates),
            "max_safe_predicates_for_compact_search": args.max_safe_predicates_for_compact_search,
            "max_rule_terms": args.max_rule_terms,
            "beam_width": args.beam_width,
        },
        "z8_policy": z8,
        "safe_feature_or_upper_bound": {
            "passes_strict": union_passes,
            "positive_row_counts": positive_counts(safe_union_mask, image_pos_masks),
            "metrics": safe_union_metrics,
        },
        "best_compact_safe_or_rule": compact,
        "required_next_receipts": [
            {
                "id": "premium_still_sr_gate13_source_or_objective_revision_<date>",
                "done_when": "A revised candidate/source/objective creates candidate-only separable positives: every X2D image median MAE >0.001%, worst-row MAE >=0%, and Z8 exact-noop remains zero-regression.",
            },
            {"id": "premium_still_sr_gate14_candidate_intake_<date>", "allowed_only_if": "smoke_gate_passed == true"},
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            return html.escape(f"{value:.6g}")
        return html.escape(str(value))

    upper = data["safe_feature_or_upper_bound"]
    image_rows = []
    for image_id, row in upper["metrics"]["by_image"].items():
        image_rows.append(
            "<tr>"
            f"<td>{cell(image_id)}</td>"
            f"<td>{cell(upper['positive_row_counts'].get(image_id))}</td>"
            f"<td>{cell(row.get('median'))}</td>"
            f"<td>{cell(row.get('min'))}</td>"
            f"<td>{cell(row.get('selected_row_count'))}</td>"
            "</tr>"
        )
    compact = data.get("best_compact_safe_or_rule") or {}
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Premium Still-SR Gate 13 Feature-Rich Tail-Safe Smoke</title>
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
<h1>Premium Still-SR Gate 13 Feature-Rich Tail-Safe Smoke</h1>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{cell(data['verdict'])}</div></section>
  <section class="card"><div class="label">Blocker</div><div class="value">{cell(data['blocker_classification'])}</div></section>
  <section class="card"><div class="label">Long run allowed</div><div class="value">{cell(data['long_run_allowed'])}</div></section>
  <section class="card"><div class="label">Safe predicates</div><div class="value">{cell(data['feature_summary']['safe_predicate_count'])}</div></section>
</div>
<h2>Decision</h2>
<p>{html.escape(data['next_unambiguous_action'])}</p>
<h2>Compact Runtime Rule</h2>
<p><code>{cell(compact.get('rule'))}</code></p>
<h2>Safe-Feature OR Upper Bound</h2>
<table><thead><tr><th>Image</th><th>Positive rows covered</th><th>Median MAE %</th><th>Worst MAE %</th><th>Selected rows</th></tr></thead>
<tbody>{''.join(image_rows)}</tbody></table>
<pre>{html.escape(json.dumps(upper['metrics'], indent=2))}</pre>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-receipt", type=Path, default=base.DEFAULT_SOURCE_RECEIPT)
    ap.add_argument("--pairs", type=Path)
    ap.add_argument("--gate12-acceptance", type=Path, default=base.DEFAULT_GATE12_ACCEPTANCE)
    ap.add_argument(
        "--previous-tail-safe-smoke",
        type=Path,
        default=base.DEFAULT_OUTPUT_DIR / "tail_safe_source_smoke.json",
    )
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--minimum-median-mae-improvement-pct", type=float, default=0.001)
    ap.add_argument("--minimum-worst-row-mae-improvement-pct", type=float, default=0.0)
    ap.add_argument("--max-input-span-rows", type=int, default=4096)
    ap.add_argument("--max-safe-predicates-for-compact-search", type=int, default=1000)
    ap.add_argument("--max-rule-terms", type=int, default=7)
    ap.add_argument("--beam-width", type=int, default=3000)
    args = ap.parse_args()
    data = build_receipt(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "feature_rich_tail_safe_source_smoke.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
