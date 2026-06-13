#!/usr/bin/env python3
"""Analyze PREVIEW rows that fail both current production-shaped candidates.

This joins existing row-level receipts and produces a focused dashboard for the
remaining no-REF PREVIEW blocker. It does not render new images and does not
register a candidate; it classifies the already-measured hard rows so the next
candidate work is aimed at the actual missing signal.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACT_ROOT = Path("/Volumes/OWC_8TB/gpr_work/artifacts")
POLICY_0606 = DEFAULT_ARTIFACT_ROOT / "preview_runtime_policy_20260606"
POLICY_0613 = DEFAULT_ARTIFACT_ROOT / "preview_runtime_policy_20260613"

PREVIEW_THRESHOLDS = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}
METRICS = ("lpips", "ms_ssim", "y_psnr", "dE2000_mean")


@dataclass(frozen=True)
class CandidateSpec:
    label: str
    path: Path
    variant: str | None
    class_name: str
    note: str


DEFAULT_CANDIDATES = [
    CandidateSpec(
        "scene_gated_fullframe",
        POLICY_0606 / "fullframe_tiled_v32_holdout28_scene_gated_hairb_train0680_v1_t512/preview_scene_routed_fullframe.json",
        None,
        "production_shaped_no_ref",
        "Current full-frame routed PREVIEW path.",
    ),
    CandidateSpec(
        "codec_q8_direct",
        POLICY_0613 / "codec_teacher_source_score_holdout28_q8_true_ref_v1/preview_codec_teacher_source_score.json",
        "codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools",
        "runtime_source_no_ref",
        "Corrected true-REF broad codec-derived no-REF source probe.",
    ),
    CandidateSpec(
        "crop_holdout_v32",
        POLICY_0606 / "scene_routed_holdout_v32_k16_k40_namespaced_84/preview_scene_routed_holdout.json",
        None,
        "crop_only_no_ref",
        "Crop-shaped ceiling for the current router/CNN family.",
    ),
    CandidateSpec(
        "exact_manifest_crop",
        POLICY_0606 / "fullframe_contract_audit_hard8_scene_gated_v1/preview_fullframe_contract_audit.json",
        "exact_manifest_crop",
        "crop_only_no_ref",
        "Exact manifest-crop contract; not a deployable arbitrary full-image path.",
    ),
    CandidateSpec(
        "editable_dng_sips_fullres",
        POLICY_0613 / "source_representation_hard8_v1/preview_source_representation_probe.json",
        "editable_dng_sips_fullres",
        "runtime_source_no_ref",
        "Direct editable DNG rendered through sips.",
    ),
    CandidateSpec(
        "source_low_plus_source_high_s1",
        POLICY_0613 / "fullimage_band_refiner_hard8_w4096_croploss_best_v2/preview_fullimage_band_refiner.json",
        "source_low_plus_source_high_s1",
        "runtime_source_no_ref",
        "Runtime-safe source low/high reconstruction.",
    ),
    CandidateSpec(
        "generated_lowfield_residual",
        POLICY_0613 / "fullimage_band_refiner_hard8_w4096_croploss_best_v2/preview_fullimage_band_refiner.json",
        "generated_lowfield_residual",
        "no_ref_model",
        "Learned low-field residual model probe.",
    ),
    CandidateSpec(
        "ref_low_plus_source_high_s1",
        POLICY_0613 / "fullimage_band_refiner_hard8_w4096_croploss_best_v2/preview_fullimage_band_refiner.json",
        "ref_low_plus_source_high_s1",
        "ref_oracle",
        "Oracle: REF low field plus source high field.",
    ),
    CandidateSpec(
        "ref_field_oracle_w4096",
        POLICY_0613 / "fullimage_resolution_oracle_hard8_highres_v1/preview_fullimage_resolution_oracle.json",
        "ref_field_oracle_w4096",
        "ref_oracle",
        "Oracle: downsampled REF field at 4096 width.",
    ),
    CandidateSpec(
        "ref_field_oracle_w6144",
        POLICY_0613 / "fullimage_resolution_oracle_hard8_highres_v1/preview_fullimage_resolution_oracle.json",
        "ref_field_oracle_w6144",
        "ref_oracle",
        "Oracle: downsampled REF field at 6144 width.",
    ),
]


def finite_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["image_id"]), str(row["crop"])


def metric_pass(metric: str, value: float | None) -> bool:
    if value is None:
        return False
    threshold = PREVIEW_THRESHOLDS[metric]
    if metric in {"lpips", "dE2000_mean"}:
        return value <= threshold
    return value >= threshold


def failing_metrics(row: dict[str, Any]) -> list[str]:
    return [metric for metric in METRICS if not metric_pass(metric, finite_float(row.get(metric)))]


def normalized_severity(row: dict[str, Any]) -> float:
    values = {metric: finite_float(row.get(metric)) for metric in METRICS}
    lpips = values["lpips"] if values["lpips"] is not None else math.inf
    ms_ssim = values["ms_ssim"] if values["ms_ssim"] is not None else 0.0
    y_psnr = values["y_psnr"] if values["y_psnr"] is not None else 0.0
    de2000 = values["dE2000_mean"] if values["dE2000_mean"] is not None else math.inf
    scores = [
        lpips / PREVIEW_THRESHOLDS["lpips"],
        PREVIEW_THRESHOLDS["ms_ssim"] / max(ms_ssim, 1e-6),
        PREVIEW_THRESHOLDS["y_psnr"] / max(y_psnr, 1e-6),
        de2000 / PREVIEW_THRESHOLDS["dE2000_mean"],
    ]
    return max(scores)


def load_rows(path: Path, variant: str | None) -> dict[tuple[str, str], dict[str, Any]]:
    payload = json.loads(path.read_text())
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError(f"{path} has no rows list")
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if variant == "exact_manifest_crop" and isinstance(row.get("exact_metrics"), dict):
            metrics = dict(row["exact_metrics"])
            item = {
                "image_id": row["image_id"],
                "crop": row["crop"],
                "variant": variant,
                **{metric: metrics.get(metric) for metric in METRICS},
                "preview_pass": bool(metrics.get("preview_pass")),
            }
            assets = row.get("assets") if isinstance(row.get("assets"), dict) else {}
            if assets.get("exact"):
                item["png"] = assets["exact"]
            out[row_key(item)] = item
            continue
        if variant is not None and row.get("variant") != variant:
            continue
        item = dict(row)
        item.setdefault("variant", variant or item.get("variant") or "default")
        out[row_key(item)] = item
    return out


def load_union_both_fail(path: Path) -> list[tuple[str, str]]:
    payload = json.loads(path.read_text())
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError(f"{path} has no rows list")
    keys = []
    for row in rows:
        a = row.get("candidate_a", {})
        b = row.get("candidate_b", {})
        if not a.get("preview_pass") and not b.get("preview_pass"):
            keys.append(row_key(row))
    return sorted(keys)


def copy_png(row: dict[str, Any], receipt_path: Path, output_dir: Path, label: str) -> str | None:
    png = row.get("png")
    if not png:
        return None
    src = receipt_path.parent / str(png)
    if not src.exists():
        return None
    dst_dir = output_dir / "thumbs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{row['image_id']}_{row['crop']}_{label}.png"
    shutil.copy2(src, dst)
    return str(dst.relative_to(output_dir))


def classify_row(candidates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    q8 = candidates.get("codec_q8_direct", {})
    scene = candidates.get("scene_gated_fullframe", {})
    crop = candidates.get("crop_holdout_v32", {})
    ref_low = candidates.get("ref_low_plus_source_high_s1", {})
    ref_field = candidates.get("ref_field_oracle_w6144", {})
    q8_fails = set(failing_metrics(q8)) if q8 else set()
    scene_fails = set(failing_metrics(scene)) if scene else set()

    if q8_fails == {"lpips"} and scene_fails:
        cause = "perceptual_detail_gap_after_q8"
    elif "dE2000_mean" in q8_fails or "dE2000_mean" in scene_fails:
        cause = "lf_color_or_tone_gap"
    elif "ms_ssim" in q8_fails or "ms_ssim" in scene_fails:
        cause = "structure_placement_gap"
    else:
        cause = "mixed_metric_gap"

    oracle_note = "no_oracle_pass"
    if ref_field.get("preview_pass"):
        oracle_note = "ref_field_passes"
    if ref_low.get("preview_pass"):
        oracle_note = "ref_low_plus_source_high_passes"
    if crop.get("preview_pass"):
        oracle_note += "_and_crop_path_passes"

    return {
        "primary_cause": cause,
        "q8_failing_metrics": sorted(q8_fails),
        "scene_failing_metrics": sorted(scene_fails),
        "oracle_note": oracle_note,
    }


def summarize_candidate(rows: list[dict[str, Any]], label: str, class_name: str, note: str) -> dict[str, Any]:
    if not rows:
        return {
            "label": label,
            "class": class_name,
            "note": note,
            "count": 0,
            "pass_count": 0,
            "worst_lpips": None,
            "worst_ms_ssim": None,
            "worst_y_psnr": None,
            "worst_dE2000_mean": None,
        }
    values = {
        metric: [finite_float(row.get(metric)) for row in rows]
        for metric in METRICS
    }
    finite_values = {
        metric: [value for value in metric_values if value is not None]
        for metric, metric_values in values.items()
    }
    return {
        "label": label,
        "class": class_name,
        "note": note,
        "count": len(rows),
        "pass_count": sum(1 for row in rows if row.get("preview_pass")),
        "worst_lpips": max(finite_values["lpips"]) if finite_values["lpips"] else None,
        "worst_ms_ssim": min(finite_values["ms_ssim"]) if finite_values["ms_ssim"] else None,
        "worst_y_psnr": min(finite_values["y_psnr"]) if finite_values["y_psnr"] else None,
        "worst_dE2000_mean": max(finite_values["dE2000_mean"]) if finite_values["dE2000_mean"] else None,
    }


def collect(args: argparse.Namespace) -> dict[str, Any]:
    keys = load_union_both_fail(args.policy_union)
    loaded = {spec.label: load_rows(spec.path, spec.variant) for spec in DEFAULT_CANDIDATES}
    summaries = []
    rows = []
    for spec in DEFAULT_CANDIDATES:
        present = [loaded[spec.label][key] for key in keys if key in loaded[spec.label]]
        summaries.append(summarize_candidate(present, spec.label, spec.class_name, spec.note))

    for key in keys:
        row_candidates = {}
        for spec in DEFAULT_CANDIDATES:
            source_row = loaded[spec.label].get(key)
            if not source_row:
                continue
            item = {
                "label": spec.label,
                "class": spec.class_name,
                "note": spec.note,
                "preview_pass": bool(source_row.get("preview_pass")),
                "failing_metrics": failing_metrics(source_row),
                "severity": normalized_severity(source_row),
                "thumb": copy_png(source_row, spec.path, args.output_json.parent, spec.label) if args.copy_pngs else None,
            }
            item.update({metric: finite_float(source_row.get(metric)) for metric in METRICS})
            row_candidates[spec.label] = item
        rows.append(
            {
                "image_id": key[0],
                "crop": key[1],
                "classification": classify_row(row_candidates),
                "candidates": row_candidates,
            }
        )

    cause_counts: dict[str, int] = {}
    for row in rows:
        cause = row["classification"]["primary_cause"]
        cause_counts[cause] = cause_counts.get(cause, 0) + 1

    q8_only_lpips = sum(
        1
        for row in rows
        if row["classification"]["q8_failing_metrics"] == ["lpips"]
    )
    ref_low_pass = sum(1 for row in rows if row["candidates"].get("ref_low_plus_source_high_s1", {}).get("preview_pass"))
    ref_field_pass = sum(1 for row in rows if row["candidates"].get("ref_field_oracle_w6144", {}).get("preview_pass"))
    crop_pass = sum(1 for row in rows if row["candidates"].get("crop_holdout_v32", {}).get("preview_pass"))

    conclusion = {
        "both_fail_count": len(rows),
        "cause_counts": cause_counts,
        "q8_only_lpips_fail_count": q8_only_lpips,
        "crop_path_pass_count": crop_pass,
        "ref_low_plus_source_high_pass_count": ref_low_pass,
        "ref_field_w6144_pass_count": ref_field_pass,
        "next_candidate_direction": (
            "Train a full-image/global-context no-REF model that uses the q8/direct source as a strong runtime input "
            "but learns the missing perceptual/detail placement without crop identity or REF content. The simple "
            "scene-vs-q8 selector is capped below production because these rows fail both candidates."
        ),
    }

    return {
        "schema": "preview_hard_failure_analysis.v1",
        "thresholds": PREVIEW_THRESHOLDS,
        "policy_union": str(args.policy_union),
        "candidate_specs": [
            {
                "label": spec.label,
                "path": str(spec.path),
                "variant": spec.variant,
                "class": spec.class_name,
                "note": spec.note,
            }
            for spec in DEFAULT_CANDIDATES
        ],
        "summary": summaries,
        "conclusion": conclusion,
        "rows": rows,
    }


def fmt(value: Any) -> str:
    number = finite_float(value)
    if number is None:
        return ""
    if abs(number) > 99999:
        return "inf"
    return f"{number:.4f}" if abs(number) < 10 else f"{number:.2f}"


def write_html(payload: dict[str, Any], path: Path) -> None:
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:22px; color:#1f2933; }
table { border-collapse:collapse; width:100%; font-size:12px; margin:14px 0 28px; }
th,td { border:1px solid #cbd5df; padding:6px 8px; text-align:right; vertical-align:top; }
th.left,td.left { text-align:left; }
.cards { display:grid; grid-template-columns:repeat(5,minmax(150px,1fr)); gap:10px; margin:14px 0; }
.card { border:1px solid #cbd5df; border-radius:6px; padding:10px; background:#fbfcfd; }
.pass { color:#12652f; font-weight:700; }
.fail { color:#9b1c1c; font-weight:700; }
.muted { color:#66788a; }
img { max-width:180px; height:auto; display:block; }
.strip { display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start; }
.shot { width:190px; border:1px solid #d6dee8; padding:5px; border-radius:6px; background:#fff; }
.shot b { display:block; text-align:left; margin-bottom:4px; }
"""
    c = payload["conclusion"]
    parts = [
        "<!doctype html><meta charset='utf-8'><title>PREVIEW Hard Failure Analysis</title>",
        f"<style>{css}</style><h1>PREVIEW Hard Failure Analysis</h1>",
        "<p>Rows here fail both current production-shaped no-REF candidates: scene-gated full-frame and q8 direct. "
        "REF-assisted rows are diagnostic ceilings only.</p>",
        "<div class=cards>",
        f"<div class=card><b>Both-fail rows</b><br>{c['both_fail_count']}</div>",
        f"<div class=card><b>q8 LPIPS-only misses</b><br>{c['q8_only_lpips_fail_count']}</div>",
        f"<div class=card><b>crop path passes</b><br>{c['crop_path_pass_count']}</div>",
        f"<div class=card><b>REF low+source high passes</b><br>{c['ref_low_plus_source_high_pass_count']}</div>",
        f"<div class=card><b>REF field w6144 passes</b><br>{c['ref_field_w6144_pass_count']}</div>",
        "</div>",
        f"<p><b>Next candidate:</b> {html.escape(c['next_candidate_direction'])}</p>",
        "<h2>Candidate Summary</h2><table><thead><tr><th class=left>candidate</th><th class=left>class</th><th>pass</th><th>LPIPS</th><th>MS</th><th>Y</th><th>dE</th><th class=left>note</th></tr></thead><tbody>",
    ]
    for row in payload["summary"]:
        cls = "pass" if row["pass_count"] == row["count"] and row["count"] else "fail"
        parts.append(
            f"<tr><td class=left>{html.escape(row['label'])}</td><td class=left>{html.escape(row['class'])}</td>"
            f"<td class={cls}>{row['pass_count']}/{row['count']}</td><td>{fmt(row['worst_lpips'])}</td>"
            f"<td>{fmt(row['worst_ms_ssim'])}</td><td>{fmt(row['worst_y_psnr'])}</td>"
            f"<td>{fmt(row['worst_dE2000_mean'])}</td><td class=left>{html.escape(row['note'])}</td></tr>"
        )
    parts.append("</tbody></table><h2>Rows</h2>")
    for row in payload["rows"]:
        ident = f"{row['image_id']} {row['crop']}"
        cls = row["classification"]
        parts.append(
            f"<h3>{html.escape(ident)}</h3><p class=muted>{html.escape(cls['primary_cause'])}; "
            f"q8 fails {html.escape(','.join(cls['q8_failing_metrics']) or 'none')}; "
            f"scene fails {html.escape(','.join(cls['scene_failing_metrics']) or 'none')}; "
            f"{html.escape(cls['oracle_note'])}</p>"
        )
        parts.append("<div class=strip>")
        for label in (
            "scene_gated_fullframe",
            "codec_q8_direct",
            "crop_holdout_v32",
            "ref_low_plus_source_high_s1",
            "ref_field_oracle_w6144",
        ):
            cand = row["candidates"].get(label)
            if not cand:
                continue
            status = "pass" if cand["preview_pass"] else "fail"
            parts.append(
                f"<div class=shot><b>{html.escape(label)}</b>"
                f"<span class={status}>{status.upper()}</span><br>"
                f"LPIPS {fmt(cand['lpips'])} MS {fmt(cand['ms_ssim'])}<br>"
                f"Y {fmt(cand['y_psnr'])} dE {fmt(cand['dE2000_mean'])}<br>"
                f"<span class=muted>{html.escape(','.join(cand['failing_metrics']) or 'no metric failures')}</span>"
            )
            if cand.get("thumb"):
                parts.append(f"<img src='{html.escape(cand['thumb'])}'>")
            parts.append("</div>")
        parts.append("</div>")
    path.write_text("".join(parts))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy-union",
        type=Path,
        default=POLICY_0613 / "policy_union_scene_gated_vs_q8_true_ref_v1/preview_policy_union_score.json",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-html", type=Path, required=True)
    parser.add_argument("--copy-pngs", action="store_true")
    args = parser.parse_args()

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(args)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.output_html)
    c = payload["conclusion"]
    print(
        f"both_fail={c['both_fail_count']} "
        f"q8_lpips_only={c['q8_only_lpips_fail_count']} "
        f"crop_pass={c['crop_path_pass_count']} "
        f"ref_low_source_high_pass={c['ref_low_plus_source_high_pass_count']} "
        f"ref_field_w6144_pass={c['ref_field_w6144_pass_count']}"
    )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
