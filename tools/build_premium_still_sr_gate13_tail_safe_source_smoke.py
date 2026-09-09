#!/usr/bin/env python3
"""Build the Gate 13 Premium still-SR tail-safe source smoke receipt.

Gate 13 found a positive X2D source, but its worst row regresses. This smoke
checks whether that source can be made production-useful by a runtime-allowed
exact no-op gate. The gate may use candidate Bayer tile features only; it may
not use REF, JPEG, target MAE, or post-hoc row metrics to decide at render time.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import math
import statistics
import struct
import time
import zipfile
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate13_tail_safe_source_smoke.v1"
EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
ARTIFACT_ROOT = EXTERNAL_ROOT / "artifacts"
DEFAULT_GATE13_AUDIT = ARTIFACT_ROOT / "premium_still_sr_gate13_degradation_source_upgrade_20260702" / "gate13_degradation_source_upgrade.json"
DEFAULT_GATE12_ACCEPTANCE = ARTIFACT_ROOT / "premium_still_sr_gate12_smoke_acceptance_20260702" / "smoke_gate_acceptance.json"
DEFAULT_SOURCE_RECEIPT = ARTIFACT_ROOT / "premium_still_sr_z8_lowresidual_teacher_x2d2_smoke_20260702_next" / "train_receipt.json"
DEFAULT_OUTPUT_DIR = ARTIFACT_ROOT / "premium_still_sr_gate13_tail_safe_source_smoke_20260702"
FEATURE_KEYS = (
    "mean",
    "std",
    "range",
    "grad_mean",
    "lap_mean",
    "ch_mean_spread",
    "ch_std_max",
    "ch_range_max",
    "std_over_mean",
    "grad_over_mean",
    "lap_over_grad",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def npy_header(stream: Any) -> dict[str, Any]:
    magic = stream.read(6)
    if magic != b"\x93NUMPY":
        raise ValueError("NPY member has invalid magic")
    version = stream.read(2)
    if version == b"\x01\x00":
        header_len = struct.unpack("<H", stream.read(2))[0]
    elif version in {b"\x02\x00", b"\x03\x00"}:
        header_len = struct.unpack("<I", stream.read(4))[0]
    else:
        raise ValueError(f"unsupported NPY version {version!r}")
    header = ast.literal_eval(stream.read(header_len).decode("latin1").strip())
    if not isinstance(header, dict):
        raise ValueError("NPY header must be a dict")
    return header


def stream_skip(stream: Any, byte_count: int) -> None:
    remaining = int(byte_count)
    while remaining > 0:
        chunk = stream.read(min(1024 * 1024, remaining))
        if not chunk:
            raise EOFError("short read while skipping NPY data")
        remaining -= len(chunk)


def input_features_from_npz(npz_path: Path, tile_indices: list[int], max_span_rows: int) -> dict[int, dict[str, float]]:
    if not tile_indices:
        return {}
    lo = min(tile_indices)
    hi = max(tile_indices)
    if hi - lo + 1 > max_span_rows:
        raise ValueError(f"selected tile span {hi - lo + 1} exceeds max span {max_span_rows}")
    with zipfile.ZipFile(npz_path) as z:
        with z.open("inputs.npy") as f:
            header = npy_header(f)
            if header.get("descr") != "<u2" or header.get("fortran_order") is not False:
                raise ValueError(f"inputs.npy must be little-endian uint16 C-order, got {header}")
            shape = header.get("shape")
            if not (isinstance(shape, tuple) and len(shape) == 4):
                raise ValueError(f"inputs.npy must be NCHW, got shape={shape!r}")
            rows, channels, height, width = [int(v) for v in shape]
            if channels <= 0 or height <= 1 or width <= 1:
                raise ValueError(f"invalid inputs.npy shape {shape}")
            if lo < 0 or hi >= rows:
                raise ValueError(f"tile index range {lo}..{hi} outside inputs row count {rows}")
            row_bytes = channels * height * width * 2
            stream_skip(f, lo * row_bytes)
            block = f.read((hi - lo + 1) * row_bytes)
    features: dict[int, dict[str, float]] = {}
    for idx in tile_indices:
        off = (idx - lo) * row_bytes
        features[idx] = compute_features(block[off : off + row_bytes], channels=channels, height=height, width=width)
    return features


def compute_features(buf: bytes, *, channels: int, height: int, width: int) -> dict[str, float]:
    values = memoryview(buf).cast("H")
    expected = channels * height * width
    if len(values) != expected:
        raise ValueError(f"expected {expected} uint16 values, got {len(values)}")
    total = 0
    total_sq = 0
    mn = 65535
    mx = 0
    for v in values:
        total += v
        total_sq += v * v
        if v < mn:
            mn = v
        if v > mx:
            mx = v
    count = len(values)
    mean = total / count
    std = math.sqrt(max(0.0, total_sq / count - mean * mean))
    grad = 0
    grad_n = 0
    lap = 0
    lap_n = 0
    channel_stats: list[tuple[float, float, int]] = []
    plane = height * width
    for c in range(channels):
        base = c * plane
        c_sum = 0
        c_sum_sq = 0
        c_min = 65535
        c_max = 0
        for i in range(base, base + plane):
            v = values[i]
            c_sum += v
            c_sum_sq += v * v
            c_min = min(c_min, v)
            c_max = max(c_max, v)
        c_mean = c_sum / plane
        c_std = math.sqrt(max(0.0, c_sum_sq / plane - c_mean * c_mean))
        channel_stats.append((c_mean, c_std, c_max - c_min))
        for y in range(height):
            row = base + y * width
            for x in range(width - 1):
                grad += abs(values[row + x + 1] - values[row + x])
                grad_n += 1
        for y in range(height - 1):
            row = base + y * width
            row2 = base + (y + 1) * width
            for x in range(width):
                grad += abs(values[row2 + x] - values[row + x])
                grad_n += 1
        for y in range(1, height - 1):
            row = base + y * width
            for x in range(1, width - 1):
                lap += abs(
                    values[row + x] * 4
                    - values[row + x - 1]
                    - values[row + x + 1]
                    - values[row - width + x]
                    - values[row + width + x]
                )
                lap_n += 1
    grad_mean = grad / grad_n if grad_n else 0.0
    lap_mean = lap / lap_n if lap_n else 0.0
    return {
        "mean": float(mean),
        "std": float(std),
        "range": float(mx - mn),
        "grad_mean": float(grad_mean),
        "lap_mean": float(lap_mean),
        "ch_mean_spread": float(max(row[0] for row in channel_stats) - min(row[0] for row in channel_stats)),
        "ch_std_max": float(max(row[1] for row in channel_stats)),
        "ch_range_max": float(max(row[2] for row in channel_stats)),
        "std_over_mean": float(std / (mean + 1e-6)),
        "grad_over_mean": float(grad_mean / (mean + 1e-6)),
        "lap_over_grad": float(lap_mean / (grad_mean + 1e-6)),
    }


def median(values: list[float]) -> float | None:
    return float(statistics.median(values)) if values else None


def improvement_stats(rows: list[dict[str, Any]], mask: int | None = None) -> dict[str, Any]:
    values: list[float] = []
    selected = 0
    for i, row in enumerate(rows):
        applied = True if mask is None else bool((mask >> i) & 1)
        if applied:
            selected += 1
        values.append(float(row["mae_improvement_pct"]) if applied else 0.0)
    return {
        "row_count": len(rows),
        "selected_row_count": selected,
        "min": min(values) if values else None,
        "median": median(values),
        "mean": sum(values) / len(values) if values else None,
        "max": max(values) if values else None,
        "negative_row_count": sum(1 for value in values if value < 0.0),
    }


def build_masks(rows: list[dict[str, Any]]) -> tuple[int, int, dict[str, int], dict[str, int]]:
    neg_mask = 0
    pos_mask = 0
    image_masks: dict[str, int] = {}
    image_pos_masks: dict[str, int] = {}
    for i, row in enumerate(rows):
        bit = 1 << i
        image_id = str(row["image_id"])
        image_masks[image_id] = image_masks.get(image_id, 0) | bit
        if float(row["mae_improvement_pct"]) < 0.0:
            neg_mask |= bit
        if float(row["mae_improvement_pct"]) > 0.0:
            pos_mask |= bit
            image_pos_masks[image_id] = image_pos_masks.get(image_id, 0) | bit
    for image_id in image_masks:
        image_pos_masks.setdefault(image_id, 0)
    return neg_mask, pos_mask, image_masks, image_pos_masks


def predicate_masks(rows: list[dict[str, Any]]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for key in FEATURE_KEYS:
        values = sorted({float(row[key]) for row in rows})
        if not values:
            continue
        thresholds = [values[0] - 1.0] + [(a + b) / 2.0 for a, b in zip(values, values[1:])] + [values[-1] + 1.0]
        for op in (">=", "<="):
            for threshold in thresholds:
                mask = 0
                for i, row in enumerate(rows):
                    value = float(row[key])
                    if value >= threshold if op == ">=" else value <= threshold:
                        mask |= 1 << i
                item = (f"{key} {op} {threshold:.8g}", mask)
                if item not in seen:
                    seen.add(item)
                    out.append(item)
    return out


def mask_metrics(rows: list[dict[str, Any]], mask: int, image_masks: dict[str, int]) -> dict[str, Any]:
    global_stats = improvement_stats(rows, mask)
    by_image: dict[str, dict[str, Any]] = {}
    for image_id, image_mask in sorted(image_masks.items()):
        selected_rows = [row for i, row in enumerate(rows) if (image_mask >> i) & 1]
        local_bits = 0
        local_index = 0
        for i, _row in enumerate(rows):
            if (image_mask >> i) & 1:
                if (mask >> i) & 1:
                    local_bits |= 1 << local_index
                local_index += 1
        by_image[image_id] = improvement_stats(selected_rows, local_bits)
    return {**global_stats, "by_image": by_image}


def passes_global(metrics: dict[str, Any], minimum_median: float, minimum_worst: float) -> bool:
    return (
        metrics["min"] is not None
        and metrics["median"] is not None
        and float(metrics["min"]) >= minimum_worst
        and float(metrics["median"]) > minimum_median
        and int(metrics["negative_row_count"]) == 0
    )


def passes_strict(metrics: dict[str, Any], minimum_median: float, minimum_worst: float) -> bool:
    if not passes_global(metrics, minimum_median, minimum_worst):
        return False
    return all(passes_global(row, minimum_median, minimum_worst) for row in metrics["by_image"].values())


def search_rules(rows: list[dict[str, Any]], minimum_median: float, minimum_worst: float) -> dict[str, Any]:
    neg_mask, pos_mask, image_masks, image_pos_masks = build_masks(rows)
    predicates = predicate_masks(rows)
    strict: list[dict[str, Any]] = []
    global_only: list[dict[str, Any]] = []
    seen_masks: set[int] = set()

    def has_global_capacity(mask: int) -> bool:
        # With exact no-op fallback, unselected rows score 0. For an even row
        # count, selecting exactly half positive rows still gives a positive
        # median because Python's median averages the highest zero and lowest
        # selected positive value.
        return (mask & pos_mask).bit_count() >= len(rows) // 2

    def has_strict_scene_capacity(mask: int) -> bool:
        for image_id, image_mask in image_masks.items():
            needed = image_mask.bit_count() // 2
            if (mask & image_pos_masks[image_id]).bit_count() < needed:
                return False
        return True

    def record(rule: str, mask: int) -> None:
        if mask in seen_masks:
            return
        seen_masks.add(mask)
        if mask & neg_mask:
            return
        if not has_global_capacity(mask):
            return
        metrics = mask_metrics(rows, mask, image_masks)
        item = {"rule": rule, "metrics": metrics}
        if passes_strict(metrics, minimum_median, minimum_worst):
            strict.append(item)
        elif passes_global(metrics, minimum_median, minimum_worst):
            global_only.append(item)

    for name, mask in predicates:
        record(name, mask)
    for idx, (name_a, mask_a) in enumerate(predicates):
        for name_b, mask_b in predicates[idx + 1 :]:
            and_mask = mask_a & mask_b
            if has_global_capacity(and_mask) or has_strict_scene_capacity(and_mask):
                record(f"({name_a}) AND ({name_b})", and_mask)
            or_mask = mask_a | mask_b
            if has_global_capacity(or_mask) or has_strict_scene_capacity(or_mask):
                record(f"({name_a}) OR ({name_b})", or_mask)

    def sort_key(item: dict[str, Any]) -> tuple[float, int]:
        metrics = item["metrics"]
        return (float(metrics.get("median") or -1e9), int(metrics.get("selected_row_count") or 0))

    strict.sort(key=sort_key, reverse=True)
    global_only.sort(key=sort_key, reverse=True)
    return {
        "predicate_count": len(predicates),
        "strict_scene_tail_safe_rule_count": len(strict),
        "global_tail_safe_rule_count": len(global_only),
        "best_strict_scene_tail_safe_rule": strict[0] if strict else None,
        "best_global_tail_safe_rule": global_only[0] if global_only else None,
    }


def gate12_z8_exact_noop(path: Path) -> dict[str, Any]:
    data = load_json(path)
    for row in data.get("rows", []):
        if isinstance(row, dict) and str(row.get("holdout")).lower() == "z8":
            return {
                "receipt": row.get("receipt"),
                "exact_noop": bool(row.get("exact_noop")),
                "passed": bool(row.get("passed")),
                "median_mae_improvement_pct": row.get("median_mae_improvement_pct"),
                "worst_row_mae_improvement_pct": row.get("worst_row_mae_improvement_pct"),
            }
    return {"exact_noop": False, "passed": False}


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    source = load_json(args.source_receipt)
    gate13 = load_json(args.gate13_audit)
    rows = nested(source, ["eval", "holdout", "rows"], [])
    if not isinstance(rows, list) or not rows:
        raise ValueError("source receipt has no eval.holdout.rows")
    rows = [dict(row) for row in rows if isinstance(row, dict)]
    pairs_path = args.pairs or Path(str(source.get("pairs")))
    if not pairs_path.exists():
        raise FileNotFoundError(pairs_path)
    features = input_features_from_npz(pairs_path, [int(row["tile_index"]) for row in rows], args.max_input_span_rows)
    for row in rows:
        row.update(features[int(row["tile_index"])])
    no_gate = improvement_stats(rows, None)
    neg_mask, _pos_mask, image_masks, image_pos_masks = build_masks(rows)
    oracle_mask = 0
    for i, row in enumerate(rows):
        if float(row["mae_improvement_pct"]) > 0.0:
            oracle_mask |= 1 << i
    oracle_metrics = mask_metrics(rows, oracle_mask, image_masks)
    search = search_rules(rows, args.minimum_median_mae_improvement_pct, args.minimum_worst_row_mae_improvement_pct)
    z8 = gate12_z8_exact_noop(args.gate12_acceptance)
    strict_passed = search["best_strict_scene_tail_safe_rule"] is not None
    z8_ok = bool(z8.get("exact_noop")) and bool(z8.get("passed"))
    smoke_passed = bool(strict_passed and z8_ok)
    if smoke_passed:
        blocker = "none"
        verdict = "gate13_tail_safe_source_smoke_passed"
        next_action = "Build candidate intake from the strict scene-tail-safe runtime gate and keep Z8 exact-noop."
    elif search["best_global_tail_safe_rule"] is not None:
        blocker = "scene_generalization_gap"
        verdict = "blocked_global_only_tail_safe_gate"
        next_action = (
            "Do not launch a long run. The current source can be tail-safe only in aggregate; "
            "the next pass needs a scene-normalized or feature-richer runtime gate that keeps every X2D scene median positive."
        )
    else:
        blocker = "tail_safe_runtime_gate_insufficient"
        verdict = "blocked_tail_safe_runtime_gate_insufficient"
        next_action = (
            "Do not launch a long run. The current source needs a richer candidate-only gate, changed objective, "
            "or changed source/model because simple runtime features cannot preserve the median gain while removing all tail regressions."
        )
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
            "gate13_audit": {"path": str(args.gate13_audit), "sha256": sha256_file(args.gate13_audit), "verdict": gate13.get("verdict")},
            "source_receipt": {"path": str(args.source_receipt), "sha256": sha256_file(args.source_receipt)},
            "pairs": {"path": str(pairs_path), "sha256": sha256_file(pairs_path)},
            "gate12_acceptance": {"path": str(args.gate12_acceptance), "sha256": sha256_file(args.gate12_acceptance)},
        },
        "runtime_policy": {
            "allowed_runtime_inputs": ["candidate_raw", "camera_metadata", "candidate_tile_statistics", "validated_noise_sidecar_optional"],
            "forbidden_runtime_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG", "target_mae", "gate_metric", "oracle_row_label"],
            "tested_gate_family": "single or two predicate threshold rules over candidate Bayer tile statistics with exact no-op fallback",
        },
        "z8_policy": z8,
        "source_metrics_without_gate": no_gate,
        "oracle_positive_only_upper_bound": oracle_metrics,
        "runtime_gate_search": search,
        "image_positive_row_capacity": {
            image_id: {
                "positive_row_count": int(image_pos_masks[image_id].bit_count()),
                "row_count": int(image_masks[image_id].bit_count()),
                "minimum_positive_rows_needed_for_positive_median": int(image_masks[image_id].bit_count() // 2),
            }
            for image_id in sorted(image_masks)
        },
        "required_next_receipts": [
            {
                "id": "premium_still_sr_gate13_feature_rich_tail_safe_source_smoke_<date>",
                "done_when": "Every X2D image has median MAE >0.001%, worst-row MAE >=0%, and Z8 exact-noop remains zero-regression using candidate-only runtime features.",
            },
            {
                "id": "premium_still_sr_gate14_candidate_intake_<date>",
                "allowed_only_if": "smoke_gate_passed == true",
            },
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        if isinstance(value, float):
            return html.escape(f"{value:.6g}")
        return html.escape(str(value))

    best_global = data["runtime_gate_search"].get("best_global_tail_safe_rule") or {}
    best_strict = data["runtime_gate_search"].get("best_strict_scene_tail_safe_rule") or {}
    image_rows = []
    for image_id, row in data["oracle_positive_only_upper_bound"]["by_image"].items():
        cap = data["image_positive_row_capacity"].get(image_id, {})
        image_rows.append(
            "<tr>"
            f"<td>{cell(image_id)}</td>"
            f"<td>{cell(cap.get('positive_row_count'))}</td>"
            f"<td>{cell(row.get('median'))}</td>"
            f"<td>{cell(row.get('min'))}</td>"
            f"<td>{cell(row.get('selected_row_count'))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Premium Still-SR Gate 13 Tail-Safe Source Smoke</title>
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
<h1>Premium Still-SR Gate 13 Tail-Safe Source Smoke</h1>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{cell(data['verdict'])}</div></section>
  <section class="card"><div class="label">Blocker</div><div class="value">{cell(data['blocker_classification'])}</div></section>
  <section class="card"><div class="label">Long run allowed</div><div class="value">{cell(data['long_run_allowed'])}</div></section>
  <section class="card"><div class="label">Strict rules found</div><div class="value">{cell(data['runtime_gate_search']['strict_scene_tail_safe_rule_count'])}</div></section>
</div>
<h2>Decision</h2>
<p>{html.escape(data['next_unambiguous_action'])}</p>
<h2>Best Strict Runtime Gate</h2>
<p><code>{cell(best_strict.get('rule'))}</code></p>
<h2>Best Global-Only Runtime Gate</h2>
<p><code>{cell(best_global.get('rule'))}</code></p>
<pre>{html.escape(json.dumps(best_global.get('metrics'), indent=2))}</pre>
<h2>Oracle Positive-Only Upper Bound</h2>
<table><thead><tr><th>Image</th><th>Positive rows</th><th>Median MAE %</th><th>Worst MAE %</th><th>Selected rows</th></tr></thead>
<tbody>{''.join(image_rows)}</tbody></table>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate13-audit", type=Path, default=DEFAULT_GATE13_AUDIT)
    ap.add_argument("--gate12-acceptance", type=Path, default=DEFAULT_GATE12_ACCEPTANCE)
    ap.add_argument("--source-receipt", type=Path, default=DEFAULT_SOURCE_RECEIPT)
    ap.add_argument("--pairs", type=Path)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--minimum-median-mae-improvement-pct", type=float, default=0.001)
    ap.add_argument("--minimum-worst-row-mae-improvement-pct", type=float, default=0.0)
    ap.add_argument("--max-input-span-rows", type=int, default=4096)
    args = ap.parse_args()
    data = build_receipt(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "tail_safe_source_smoke.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
