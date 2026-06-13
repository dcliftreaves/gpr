#!/usr/bin/env python3
"""Rank existing PREVIEW source/teacher evidence for the no-REF blocker.

The goal is not to register a production path. This dashboard collects the
existing receipts that explain the current PREVIEW state and separates
production-shaped no-REF rows from crop-only diagnostics and REF-assisted
oracles.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ARTIFACT_ROOT = Path("/Volumes/OWC_8TB/gpr_work/artifacts")
PREVIEW_THRESHOLDS = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}
METRICS = ("lpips", "ms_ssim", "y_psnr", "dE2000_mean")


@dataclass(frozen=True)
class ReceiptSpec:
    label: str
    path: Path
    default_class: str
    note: str


def default_specs(root: Path) -> list[ReceiptSpec]:
    policy_0613 = root / "preview_runtime_policy_20260613"
    policy_0606 = root / "preview_runtime_policy_20260606"
    return [
        ReceiptSpec(
            "aggregate_failure_audit_v4",
            policy_0613 / "fullframe_failure_mode_audit_v4/preview_fullframe_failure_mode_audit.json",
            "mixed",
            "Broad aggregate: crop-shaped route, full-frame route, hard-eight tiled path, and recent probes.",
        ),
        ReceiptSpec(
            "source_representation_hard8",
            policy_0613 / "source_representation_hard8_v1/preview_source_representation_probe.json",
            "runtime_source",
            "Runtime-legal source renders; REF is metric-only.",
        ),
        ReceiptSpec(
            "codec_teacher_sources_hard8",
            policy_0613 / "codec_teacher_source_score_hard8_v1/preview_codec_teacher_source_score.json",
            "runtime_source",
            "Registered codec-derived no-REF teacher/source renders; REF is metric-only.",
        ),
        ReceiptSpec(
            "codec_teacher_q8_holdout28",
            policy_0613 / "codec_teacher_source_score_holdout28_q8_v1/preview_codec_teacher_source_score.json",
            "runtime_source",
            "Archival q8 no-REF teacher/source render across the 28-image PREVIEW holdout; REF is metric-only.",
        ),
        ReceiptSpec(
            "policy_union_scene_vs_q8",
            policy_0613 / "policy_union_scene_gated_vs_q8_v1/preview_policy_union_score.json",
            "diagnostic_oracle",
            "Metric-selected oracle union between scene-gated full-frame and q8 direct rows; upper bound for a runtime selector.",
        ),
        ReceiptSpec(
            "resolution_oracle_highres",
            policy_0613 / "fullimage_resolution_oracle_hard8_highres_v1/preview_fullimage_resolution_oracle.json",
            "mixed",
            "Source field rows are runtime-shaped; REF-field rows are oracle ceilings.",
        ),
        ReceiptSpec(
            "band_refiner_cropweighted",
            policy_0613 / "fullimage_band_refiner_hard8_w4096_croploss_best_v2/preview_fullimage_band_refiner.json",
            "no_ref_model",
            "Source-only full-image band model plus REF-low oracle rows.",
        ),
        ReceiptSpec(
            "residual_band_4096",
            policy_0613 / "fullimage_band_residual_smoke_0026_6680_w4096_v1/preview_fullimage_band_refiner.json",
            "no_ref_model",
            "Source-preserving residual band smoke on hard failures.",
        ),
        ReceiptSpec(
            "residual_unet_2048",
            policy_0613 / "fullimage_band_residual_unet_smoke_0026_6680_w2048_v1/preview_fullimage_band_refiner.json",
            "no_ref_model",
            "Multi-scale residual U-Net smoke on hard failures.",
        ),
        ReceiptSpec(
            "source_feature_knn",
            policy_0613 / "residual_features_knn_hard8_w2048_v1/preview_fullimage_residual_features.json",
            "diagnostic_oracle",
            "Source-feature residual and kNN residual probes; fitted residual variants are diagnostic.",
        ),
        ReceiptSpec(
            "local_affine_oracle",
            policy_0613 / "fullimage_local_affine_oracle_hard8_v1/preview_fullimage_local_affine_oracle.json",
            "diagnostic_oracle",
            "REF-fitted spatial affine oracle.",
        ),
        ReceiptSpec(
            "dense_warp_oracle",
            policy_0613 / "dense_warp_hard8_w1024_v1/preview_fullimage_dense_warp_oracle.json",
            "diagnostic_oracle",
            "REF-guided dense warp oracle.",
        ),
        ReceiptSpec(
            "rolemap_post_distill",
            policy_0613 / "rolemap_post_distill_exactpass_tiledfail_v1/preview_rolemap_post_distill.json",
            "no_ref_model",
            "No-REF post-distill from arbitrary tiled output toward exact no-REF crop output.",
        ),
        ReceiptSpec(
            "stitched_context_post",
            policy_0613 / "stitched_post_hard8_context_unet_capacity_v1/preview_runtime_refiner.json",
            "no_ref_model",
            "Runtime-safe stitched-frame post-refiner capacity check.",
        ),
        ReceiptSpec(
            "source_roots_0606",
            policy_0606 / "fullframe_source_root_score_hard8_v1/preview_fullframe_source_root_score.json",
            "runtime_source",
            "Earlier hard-eight source DNG root score.",
        ),
        ReceiptSpec(
            "upresable_preview_probe_0606",
            root / "upresable_preview_probe_20260606/upresable_preview_probe_dashboard.json",
            "runtime_source",
            "Native UPRESABLE preview source probe.",
        ),
        ReceiptSpec(
            "lf_atlas_sweep_0606",
            root / "display_lf_atlas_sweep_20260606/lf_atlas_sweep_dashboard.json",
            "diagnostic_oracle",
            "LF atlas sweep; strong ceiling but not a production render contract.",
        ),
        ReceiptSpec(
            "learned_atlas_0606",
            root / "display_learned_atlas_20260606/learned_residual_atlas_dashboard.json",
            "diagnostic_model",
            "Learned residual atlas diagnostic.",
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


def metric_pass(metric: str, value: float | None) -> bool:
    if value is None:
        return False
    threshold = PREVIEW_THRESHOLDS[metric]
    if metric in ("lpips", "dE2000_mean"):
        return value <= threshold
    return value >= threshold


def extract_worst_metrics(row: dict[str, Any]) -> dict[str, float | None]:
    if isinstance(row.get("worst_metrics"), dict):
        raw = row["worst_metrics"]
        return {metric: finite_float(raw.get(metric)) for metric in METRICS}
    return {
        "lpips": finite_float(row.get("worst_lpips")),
        "ms_ssim": finite_float(row.get("worst_ms_ssim")),
        "y_psnr": finite_float(row.get("worst_y_psnr")),
        "dE2000_mean": finite_float(row.get("worst_dE2000_mean")),
    }


def normalize_summary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("variant_summary"), list):
        return [row for row in payload["variant_summary"] if isinstance(row, dict)]

    summary = payload.get("summary")
    if isinstance(summary, list):
        return [row for row in summary if isinstance(row, dict)]

    if isinstance(summary, dict):
        out = []
        for variant, row in summary.items():
            if not isinstance(row, dict) or "count" not in row:
                continue
            item = dict(row)
            item.setdefault("variant", variant)
            out.append(item)
        return out

    return []


def render_class(default_class: str, variant: str) -> str:
    value = variant.lower()
    if "crop_holdout" in value or "exact_manifest_crop" in value or "exact_ref" in value or "teacher_vs_ref" in value:
        return "no_ref_crop_only"
    if "output_teacher" in value or "output_vs_teacher" in value or "source_vs_teacher" in value:
        return "no_ref_teacher_metric"
    if "ref_field_oracle" in value or "ref_low" in value:
        return "ref_oracle"
    if "alignment_oracle" in value or "dense_warp" in value:
        return "ref_oracle"
    if "affine" in value and "source" not in value:
        return "ref_oracle"
    if "lf_atlas" in value:
        return "diagnostic_oracle"
    if "source_fullres" in value or "source_field" in value or "source_baseline" in value:
        return "runtime_source"
    if default_class == "mixed":
        if "fullframe_scene_gated" in value or "fullframe_baseline" in value:
            return "no_ref_fullframe"
        return "diagnostic"
    return default_class


def production_eligible(row_class: str) -> bool:
    return row_class in {"runtime_source", "no_ref_fullframe", "no_ref_model"}


def load_rank_rows(specs: list[ReceiptSpec]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = []
    missing = []
    for spec in specs:
        if not spec.path.exists():
            missing.append({"label": spec.label, "path": str(spec.path)})
            continue
        payload = json.loads(spec.path.read_text())
        for item in normalize_summary(payload):
            variant = str(item.get("variant", spec.label))
            cls = render_class(spec.default_class, variant)
            metrics = extract_worst_metrics(item)
            metric_passes = {metric: metric_pass(metric, metrics[metric]) for metric in METRICS}
            count = int(item.get("count", 0) or 0)
            pass_count = int(item.get("pass_count", 0) or 0)
            pass_rate = float(item.get("pass_rate", pass_count / count if count else 0.0) or 0.0)
            rows.append(
                {
                    "receipt": spec.label,
                    "variant": variant,
                    "class": cls,
                    "production_eligible": production_eligible(cls),
                    "count": count,
                    "pass_count": pass_count,
                    "pass_rate": pass_rate,
                    "worst_metrics": metrics,
                    "metric_passes": metric_passes,
                    "note": spec.note,
                    "path": str(spec.path),
                }
            )
    rows.sort(
        key=lambda row: (
            not row["production_eligible"],
            -row["pass_rate"],
            -row["pass_count"],
            -row["count"],
            row["worst_metrics"].get("lpips") if row["worst_metrics"].get("lpips") is not None else 999.0,
        )
    )
    return rows, missing


def build_findings(rows: list[dict[str, Any]]) -> list[str]:
    findings = []
    eligible = [row for row in rows if row["production_eligible"]]
    fullframe = [row for row in rows if row["class"] == "no_ref_fullframe"]
    hard_models = [row for row in eligible if row["class"] == "no_ref_model" and row["count"] >= 6]
    oracles = [row for row in rows if "oracle" in row["class"]]
    crop_only = [row for row in rows if row["class"] == "no_ref_crop_only"]

    if crop_only:
        best = max(crop_only, key=lambda row: (row["pass_rate"], row["pass_count"]))
        findings.append(
            f"Crop-shaped no-REF evidence reaches {best['pass_count']}/{best['count']} "
            f"({best['variant']}), so crop-local routing is not the blocker."
        )
    if fullframe:
        best = max(fullframe, key=lambda row: (row["pass_rate"], row["pass_count"]))
        findings.append(
            f"Best broad production-shaped full-frame row is {best['pass_count']}/{best['count']} "
            f"({best['variant']}), which leaves severe full-image/tiled failures."
        )
    if hard_models:
        best = max(hard_models, key=lambda row: (row["pass_rate"], row["pass_count"]))
        findings.append(
            f"Best hard-row no-REF model candidate is {best['pass_count']}/{best['count']} "
            f"({best['receipt']}:{best['variant']}), so current local/residual formulations are not enough."
        )
    codec_teachers = [row for row in eligible if row["receipt"].startswith("codec_teacher")]
    if codec_teachers:
        broad = next((row for row in codec_teachers if row["receipt"] == "codec_teacher_q8_holdout28"), None)
        hard = next(
            (
                row
                for row in codec_teachers
                if row["receipt"] == "codec_teacher_sources_hard8"
                and row["variant"] == "codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools"
            ),
            None,
        )
        if broad is not None and hard is not None:
            findings.append(
                f"Archival q8 no-REF teacher/source reaches {broad['pass_count']}/{broad['count']} "
                f"on the broad holdout but only {hard['pass_count']}/{hard['count']} on the hard-eight rows, "
                "so it is a partial source component, not a sufficient PREVIEW teacher."
            )
        else:
            best = max(codec_teachers, key=lambda row: (row["pass_rate"], row["pass_count"]))
            findings.append(
                f"Best codec-derived no-REF teacher/source row is {best['pass_count']}/{best['count']} "
                f"({best['variant']}), so archival/still codec rendering alone is not a sufficient PREVIEW teacher."
            )
    policy_unions = [row for row in rows if row["receipt"] == "policy_union_scene_vs_q8" and row["variant"] == "oracle_union"]
    if policy_unions:
        best = policy_unions[0]
        findings.append(
            f"Metric-selected scene-gated/q8 oracle union reaches only {best['pass_count']}/{best['count']}, "
            "so a simple runtime selector between those two paths cannot clear the PREVIEW gate."
        )
    if oracles:
        best = max(oracles, key=lambda row: (row["pass_rate"], row["pass_count"]))
        findings.append(
            f"Best diagnostic/oracle ceiling is {best['pass_count']}/{best['count']} "
            f"({best['receipt']}:{best['variant']}), showing the target is reachable only with information the current runtime path lacks."
        )
    findings.append(
        "Next production experiment should change the source/teacher representation or use a more global image-conditioned model; "
        "another small local correction, affine field, warp, or residual band variant is already ruled down by the receipts."
    )
    return findings


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    if math.isinf(value):
        return "inf"
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.4f}"


def write_html(path: Path, payload: dict[str, Any]) -> None:
    rows = []
    for row in payload["rows"]:
        metrics = row["worst_metrics"]
        cls = "eligible" if row["production_eligible"] else "diagnostic"
        rows.append(
            "<tr>"
            f"<td>{html.escape(row['receipt'])}</td>"
            f"<td>{html.escape(row['variant'])}</td>"
            f"<td>{html.escape(row['class'])}</td>"
            f"<td class='{cls}'>{'yes' if row['production_eligible'] else 'no'}</td>"
            f"<td>{row['pass_count']}/{row['count']}</td>"
            f"<td>{row['pass_rate']:.1%}</td>"
            f"<td>{fmt(metrics.get('lpips'))}</td>"
            f"<td>{fmt(metrics.get('ms_ssim'))}</td>"
            f"<td>{fmt(metrics.get('y_psnr'))}</td>"
            f"<td>{fmt(metrics.get('dE2000_mean'))}</td>"
            f"<td>{html.escape(row['note'])}</td>"
            "</tr>"
        )

    findings = "".join(f"<li>{html.escape(item)}</li>" for item in payload["findings"])
    missing = "".join(
        f"<li>{html.escape(item['label'])}: {html.escape(item['path'])}</li>"
        for item in payload["missing_receipts"]
    )
    css = """
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:24px; color:#1f2933; }
table { border-collapse:collapse; width:100%; font-size:12px; margin-top:16px; }
th,td { border:1px solid #cbd5df; padding:6px 8px; text-align:left; vertical-align:top; }
th { background:#eef3f7; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:10px; margin:16px 0; }
.card { border:1px solid #cbd5df; background:#fbfcfd; border-radius:6px; padding:10px; }
.eligible { color:#12652f; font-weight:700; }
.diagnostic { color:#8a3416; font-weight:700; }
"""
    doc = f"""<!doctype html>
<meta charset="utf-8">
<title>PREVIEW Candidate Evidence Rank</title>
<style>{css}</style>
<h1>PREVIEW Candidate Evidence Rank</h1>
<p>This dashboard ranks existing receipts for the full-image no-REF PREVIEW blocker. REF-assisted rows are retained only as diagnostic ceilings.</p>
<div class="cards">
<div class="card"><strong>Total variants</strong><br>{payload['summary']['variant_count']}</div>
<div class="card"><strong>Production-eligible variants</strong><br>{payload['summary']['production_eligible_count']}</div>
<div class="card"><strong>Missing receipts</strong><br>{len(payload['missing_receipts'])}</div>
<div class="card"><strong>Gate</strong><br>LPIPS <= 0.15, MS >= 0.95, Y >= 28, dE <= 3</div>
</div>
<h2>Findings</h2>
<ul>{findings}</ul>
<h2>Ranked Variants</h2>
<table>
<thead><tr><th>Receipt</th><th>Variant</th><th>Class</th><th>Eligible</th><th>Pass</th><th>Rate</th><th>Worst LPIPS</th><th>Worst MS</th><th>Worst Y</th><th>Worst dE</th><th>Note</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<h2>Missing Receipts</h2>
<ul>{missing or '<li>none</li>'}</ul>
"""
    path.write_text(doc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-html", type=Path, required=True)
    args = parser.parse_args()

    rows, missing = load_rank_rows(default_specs(args.artifact_root))
    payload = {
        "schema": "preview_candidate_evidence_rank.v1",
        "thresholds": PREVIEW_THRESHOLDS,
        "summary": {
            "variant_count": len(rows),
            "production_eligible_count": sum(1 for row in rows if row["production_eligible"]),
        },
        "findings": build_findings(rows),
        "missing_receipts": missing,
        "rows": rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    write_html(args.output_html, payload)
    print(json.dumps(payload["summary"], indent=2))
    for finding in payload["findings"]:
        print(f"- {finding}")
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
