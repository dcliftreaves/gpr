#!/usr/bin/env python3
"""Build a kernel-stability audit for Mission 1 native PSF measurements."""
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_native_psf_kernel_stability_audit.v1"
DEFAULT_MEASUREMENT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_psf_measurement_20260630/native_psf_measurement.json"
)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measurement", type=Path, default=DEFAULT_MEASUREMENT)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--min-accepted-pairs", type=int, default=3)
    ap.add_argument("--max-weight-std", type=float, default=0.10)
    ap.add_argument("--min-weight-floor", type=float, default=-0.05)
    ap.add_argument("--min-alignment-corr", type=float, default=0.75)
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def number(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def pair_row(pair: dict[str, Any], *, min_alignment_corr: float, min_weight_floor: float) -> dict[str, Any]:
    alignment = pair.get("alignment") if isinstance(pair.get("alignment"), dict) else {}
    fit = pair.get("psf_fit") if isinstance(pair.get("psf_fit"), dict) else {}
    tile = pair.get("tile_summary") if isinstance(pair.get("tile_summary"), dict) else {}
    weights = fit.get("normalized_weights")
    weights = [number(v) for v in weights] if isinstance(weights, list) else []
    accepted = bool(alignment.get("accepted_for_kernel"))
    corr = number(alignment.get("correlation"))
    negative_weight = any(v < min_weight_floor for v in weights)
    reasons = [str(v) for v in pair.get("rejection_reasons", []) if str(v)]
    if accepted and negative_weight:
        reasons.append(f"accepted pair has normalized weight below {min_weight_floor:.2f}")
    if corr < min_alignment_corr:
        reasons.append(f"alignment correlation {corr:.3f} below {min_alignment_corr:.2f}")
    return {
        "low_stem": pair.get("low_stem"),
        "high_stem": pair.get("high_stem"),
        "accepted_for_kernel": accepted,
        "alignment_correlation": corr,
        "shift_low_raw_px_x": alignment.get("shift_low_raw_px_x"),
        "shift_low_raw_px_y": alignment.get("shift_low_raw_px_y"),
        "normalized_weights": weights,
        "has_negative_weight": negative_weight,
        "rmse_14bit": number(fit.get("rmse_14bit")),
        "weight_sum_gain": number(fit.get("weight_sum_gain")),
        "sharp_edge_tile_count": int(number(tile.get("sharp_edge_tile_count"))),
        "texture_field_tile_count": int(number(tile.get("texture_field_tile_count"))),
        "rejection_reasons": reasons,
    }


def build_audit(
    measurement: dict[str, Any],
    measurement_path: Path,
    *,
    min_accepted_pairs: int,
    max_weight_std: float,
    min_weight_floor: float,
    min_alignment_corr: float,
) -> dict[str, Any]:
    summary = measurement.get("summary") if isinstance(measurement.get("summary"), dict) else {}
    combined = measurement.get("combined_kernel") if isinstance(measurement.get("combined_kernel"), dict) else {}
    pairs = [
        pair_row(pair, min_alignment_corr=min_alignment_corr, min_weight_floor=min_weight_floor)
        for pair in measurement.get("pair_measurements", [])
        if isinstance(pair, dict)
    ]
    accepted_pairs = [row for row in pairs if row["accepted_for_kernel"]]
    rejected_pairs = [row for row in pairs if not row["accepted_for_kernel"]]
    accepted_negative = [row for row in accepted_pairs if row["has_negative_weight"]]
    low_corr = [row for row in pairs if row["alignment_correlation"] < min_alignment_corr]
    weight_std = [number(v) for v in combined.get("normalized_weights_std", [])] if isinstance(combined.get("normalized_weights_std"), list) else []
    weight_mean = [number(v) for v in combined.get("normalized_weights_mean", [])] if isinstance(combined.get("normalized_weights_mean"), list) else []
    max_std = max(weight_std) if weight_std else 0.0
    min_mean_weight = min(weight_mean) if weight_mean else 0.0

    pair_count_ready = len(accepted_pairs) >= min_accepted_pairs
    variance_ready = bool(weight_std) and max_std <= max_weight_std
    nonnegative_ready = not accepted_negative and min_mean_weight >= min_weight_floor
    kernel_stable_by_audit = pair_count_ready and variance_ready and nonnegative_ready
    measurement_ready = bool(measurement.get("native_psf_ready_for_model_conditioning"))
    production_ready = kernel_stable_by_audit and measurement_ready

    blockers: list[str] = []
    if not pair_count_ready:
        blockers.append(f"Only {len(accepted_pairs)} accepted pairs are available; {min_accepted_pairs} are required.")
    if not variance_ready:
        blockers.append(f"Combined normalized-weight std max is {max_std:.3f}; <= {max_weight_std:.2f} is required.")
    if accepted_negative:
        names = ", ".join(f"{row['low_stem']}->{row['high_stem']}" for row in accepted_negative)
        blockers.append(f"Accepted pair(s) have invalid negative weights below {min_weight_floor:.2f}: {names}.")
    if min_mean_weight < min_weight_floor:
        blockers.append(f"Combined mean kernel has weight {min_mean_weight:.3f} below {min_weight_floor:.2f}.")
    if low_corr:
        names = ", ".join(f"{row['low_stem']}->{row['high_stem']}" for row in low_corr)
        blockers.append(f"Low-correlation pair(s) remain diagnostic only: {names}.")
    if not measurement_ready:
        blockers.append("native_psf_ready_for_model_conditioning is false in the measurement receipt.")

    if accepted_negative or not variance_ready:
        dominant = "kernel disagreement"
    elif not pair_count_ready:
        dominant = "accepted pair count"
    elif not measurement_ready:
        dominant = "measurement readiness flag"
    else:
        dominant = "none"

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "measurement": {
            "path": measurement_path.as_posix(),
            "schema": measurement.get("schema"),
        },
        "production_ready": production_ready,
        "kernel_stable_by_audit": kernel_stable_by_audit,
        "dominant_blocker": dominant,
        "policy": {
            "min_accepted_pairs": min_accepted_pairs,
            "max_weight_std": max_weight_std,
            "min_weight_floor": min_weight_floor,
            "min_alignment_corr": min_alignment_corr,
        },
        "summary": {
            "selected_pair_count": int(number(summary.get("selected_pair_count"), len(pairs))),
            "accepted_pair_count": len(accepted_pairs),
            "rejected_pair_count": len(rejected_pairs),
            "accepted_negative_weight_pair_count": len(accepted_negative),
            "low_alignment_corr_pair_count": len(low_corr),
            "combined_kernel_available": bool(combined.get("available")),
            "combined_kernel_stable_in_source_receipt": bool(combined.get("kernel_stable")),
            "combined_normalized_weights_mean": weight_mean,
            "combined_normalized_weights_std": weight_std,
            "combined_weight_std_max": max_std,
            "combined_weight_mean_min": min_mean_weight,
            "rmse_14bit_median": number(combined.get("rmse_14bit_median")),
            "native_psf_ready_for_model_conditioning": measurement_ready,
        },
        "pair_rows": pairs,
        "blockers": blockers,
        "next_actions": [
            "Use the current near-time pairs only as diagnostic evidence; do not train a PSF-conditioned replacement from this kernel.",
            "Capture or locate at least three controlled same-scene high/low pairs with fixed settings and source/decoded Bayer hashes.",
            "Re-run native PSF measurement until accepted pair count, coefficient variance, and negative-weight gates all pass.",
            "Only then train or tune a PSF-conditioned 4K cleanup / 8K SR candidate against the approved Mission42 and Z8 baselines.",
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    s = data["summary"]
    cards = [
        ("Production ready", data["production_ready"]),
        ("Dominant blocker", data["dominant_blocker"]),
        ("Accepted pairs", f"{s['accepted_pair_count']} / {data['policy']['min_accepted_pairs']}"),
        ("Max weight std", f"{s['combined_weight_std_max']:.3f}"),
        ("Accepted negative pairs", s["accepted_negative_weight_pair_count"]),
        ("Native PSF ready", s["native_psf_ready_for_model_conditioning"]),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    pair_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['low_stem']))}->{html.escape(str(row['high_stem']))}</td>"
        f"<td>{html.escape(str(row['accepted_for_kernel']))}</td>"
        f"<td>{row['alignment_correlation']:.3f}</td>"
        f"<td><code>{html.escape(', '.join(f'{v:.3f}' for v in row['normalized_weights']))}</code></td>"
        f"<td>{html.escape(str(row['has_negative_weight']))}</td>"
        f"<td>{row['rmse_14bit']:.2f}</td>"
        f"<td>{row['sharp_edge_tile_count']} / {row['texture_field_tile_count']}</td>"
        f"<td>{html.escape('; '.join(row['rejection_reasons']))}</td>"
        "</tr>"
        for row in data["pair_rows"]
    )
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    actions = "".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Mission 1 Native PSF Kernel Stability Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #101820; background: #f6f8fa; }}
main {{ max-width: 1240px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; letter-spacing: 0; }}
.sub {{ color: #5b6673; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #5b6673; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 24px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ white-space: normal; overflow-wrap: anywhere; }}
</style></head><body><main>
<h1>Mission 1 Native PSF Kernel Stability Audit</h1>
<p class="sub">This audit explains why the current native high/low Mission 1 measurement is diagnostic only. It checks accepted-pair count, normalized-kernel coefficient variance, invalid negative weights, and alignment correlation.</p>
<div class="grid">{card_html}</div>
<h2>Pair Measurements</h2>
<table><thead><tr><th>pair</th><th>accepted</th><th>corr</th><th>weights</th><th>negative</th><th>RMSE 14-bit</th><th>edge / texture tiles</th><th>notes</th></tr></thead><tbody>{pair_rows}</tbody></table>
<h2>Blockers</h2><ul>{blockers}</ul>
<h2>Next Actions</h2><ul>{actions}</ul>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    data = build_audit(
        load_json(args.measurement),
        args.measurement,
        min_accepted_pairs=args.min_accepted_pairs,
        max_weight_std=args.max_weight_std,
        min_weight_floor=args.min_weight_floor,
        min_alignment_corr=args.min_alignment_corr,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "kernel_stability_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
