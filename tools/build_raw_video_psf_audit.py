#!/usr/bin/env python3
"""Build the raw-video PSF/SR production-readiness audit.

This audit separates two things that are easy to conflate:

* the approved 4K cleanup and 8K SR baselines, which have useful production
  receipts for offline review/reconstruction, and
* the unfinished PSF-aware replacement work, which still needs native
  camera/display PSF evidence and a PSF-conditioned model gate.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
SCHEMA = "gpr.raw_video_psf_audit.v1"


DEFAULT_PSF_RECEIPT = (
    "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/"
    "bayer_resize_psf_receipt.json"
)
DEFAULT_4K_SIGNOFF = "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"
DEFAULT_8K_PROMOTION = "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json"


def resolve_artifact(external_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return external_root / candidate


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def bool_at(data: dict[str, Any] | None, keys: list[str], default: bool = False) -> bool:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return bool(cur)


def num_at(data: dict[str, Any] | None, keys: list[str]) -> float | None:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def list_at(data: dict[str, Any] | None, keys: list[str]) -> list[Any]:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return []
        cur = cur[key]
    return list(cur) if isinstance(cur, list) else []


def artifact_entry(label: str, path: Path, data: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
        "schema": data.get("schema") if isinstance(data, dict) else None,
    }


def synthetic_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    psf = {
        "schema": "gpr.bayer_resize_psf_receipt.v1",
        "production_ready": False,
        "dataset": {
            "pair_count": 16,
            "sharp_edge_count": 8,
            "texture_field_count": 8,
            "cfa_phases": ["RGGB"],
        },
        "psf_model": {
            "model_id": "synthetic_same_color_box2",
            "best_candidate_kernel": "same_color_box2",
            "normalized_weights": [0.25, 0.25, 0.25, 0.25],
            "rmse_14bit": 0.3,
        },
        "detail_budget": {
            "fine_share_of_residual_abs": 0.999,
            "mid_share_of_residual_abs": 0.003,
            "coarse_share_of_residual_abs": 0.002,
            "residual_to_target_cell_detail_ratio": 1.0,
        },
        "gate_results": {
            "mission42_passed": False,
            "z8_all24_passed": False,
        },
    }
    cleanup = {
        "schema": "gpr.mission1_4k_cleanup_production_signoff.v1",
        "verdict": {"production_ready": True, "accepted_role": "production"},
    }
    sr = {
        "schema": "gpr.mission1_8k_sr_production_promotion.v1",
        "verdict": {"production_ready": True, "accepted_role": "production"},
    }
    return psf, cleanup, sr


def build_audit(
    external_root: Path,
    psf_receipt_path: Path,
    cleanup_signoff_path: Path,
    sr_promotion_path: Path,
    synthetic: bool = False,
) -> dict[str, Any]:
    if synthetic:
        psf_receipt, cleanup_signoff, sr_promotion = synthetic_inputs()
    else:
        psf_receipt = load_json(psf_receipt_path)
        cleanup_signoff = load_json(cleanup_signoff_path)
        sr_promotion = load_json(sr_promotion_path)

    cleanup_ready = bool_at(cleanup_signoff, ["verdict", "production_ready"])
    sr_ready = bool_at(sr_promotion, ["verdict", "production_ready"])
    psf_receipt_ready = bool_at(psf_receipt, ["production_ready"])
    mission42_psf_gate = bool_at(psf_receipt, ["gate_results", "mission42_passed"])
    z8_psf_gate = bool_at(psf_receipt, ["gate_results", "z8_all24_passed"])

    native_psf_ready = False
    psf_conditioned_model_ready = False
    psf_replacement_ready = (
        native_psf_ready
        and psf_conditioned_model_ready
        and psf_receipt_ready
        and mission42_psf_gate
        and z8_psf_gate
    )

    pair_count = int(num_at(psf_receipt, ["dataset", "pair_count"]) or 0)
    sharp_edge_count = int(num_at(psf_receipt, ["dataset", "sharp_edge_count"]) or 0)
    texture_field_count = int(num_at(psf_receipt, ["dataset", "texture_field_count"]) or 0)
    fine_share = num_at(psf_receipt, ["detail_budget", "fine_share_of_residual_abs"])
    mid_share = num_at(psf_receipt, ["detail_budget", "mid_share_of_residual_abs"])
    coarse_share = num_at(psf_receipt, ["detail_budget", "coarse_share_of_residual_abs"])
    detail_ratio = num_at(psf_receipt, ["detail_budget", "residual_to_target_cell_detail_ratio"])

    checks = [
        {
            "id": "approved_4k_cleanup_baseline",
            "passed": cleanup_ready,
            "production_meaning": "Current Mission 1 4K cleanup baseline is available for offline/review use.",
        },
        {
            "id": "approved_8k_sr_baseline",
            "passed": sr_ready,
            "production_meaning": "Current candidate-aware 8K SR baseline has packaging and review receipts.",
        },
        {
            "id": "pair_derived_psf_detail_budget",
            "passed": pair_count >= 1000 and fine_share is not None,
            "production_meaning": "Modeled high-to-low real-fixture pair analysis is broad enough to guide the next PSF experiment.",
        },
        {
            "id": "native_capture_display_psf",
            "passed": native_psf_ready,
            "production_meaning": "Requires real native high-res/low-res or display/capture PSF measurements; not satisfied by modeled pairs.",
        },
        {
            "id": "psf_conditioned_model_gate",
            "passed": psf_conditioned_model_ready,
            "production_meaning": "Requires a PSF-conditioned model beating the approved 4K/8K baselines on raw and rendered gates.",
        },
    ]

    blockers = [
        "No native camera/sensor/DMA/display PSF receipt is present.",
        "No PSF-conditioned replacement model has beaten both current Mission42 and Z8 baselines.",
        "The existing pair-derived receipt is non-production by design; it proves the modeled target, not the native camera path.",
    ]

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "synthetic" if synthetic else "real",
        "external_root": str(external_root),
        "readiness_percent": 40,
        "production_ready": False,
        "approved_baselines_ready": cleanup_ready and sr_ready,
        "psf_replacement_ready": psf_replacement_ready,
        "summary": {
            "cleanup_4k_ready": cleanup_ready,
            "sr_8k_ready": sr_ready,
            "psf_receipt_ready": psf_receipt_ready,
            "mission42_psf_gate_passed": mission42_psf_gate,
            "z8_all24_psf_gate_passed": z8_psf_gate,
            "native_psf_ready": native_psf_ready,
            "psf_conditioned_model_ready": psf_conditioned_model_ready,
        },
        "pair_derived_psf": {
            "pair_count": pair_count,
            "sharp_edge_count": sharp_edge_count,
            "texture_field_count": texture_field_count,
            "cfa_phases": list_at(psf_receipt, ["dataset", "cfa_phases"]),
            "best_kernel": (psf_receipt or {}).get("psf_model", {}).get("best_candidate_kernel"),
            "normalized_weights": list_at(psf_receipt, ["psf_model", "normalized_weights"]),
            "rmse_14bit": num_at(psf_receipt, ["psf_model", "rmse_14bit"]),
            "fine_share_of_residual_abs": fine_share,
            "mid_share_of_residual_abs": mid_share,
            "coarse_share_of_residual_abs": coarse_share,
            "residual_to_target_cell_detail_ratio": detail_ratio,
        },
        "checks": checks,
        "blockers": blockers,
        "next_actions": [
            "Capture or synthesize a native camera-source PSF fixture: high-res reference, native 4K/12MP Bayer source, sharp edges, and texture fields.",
            "Train a PSF-conditioned 4K cleanup or 8K SR candidate against CFA-aware high-res targets and explicit fine-detail losses.",
            "Gate the candidate against current Mission42 and Z8 baselines in raw domain and rendered review, including worst-row visual inspection.",
            "Promote only with .gvid, editable DNG/GPR, ProRes, timing, memory, checkpoint, config, and hash receipts.",
        ],
        "artifacts": [
            artifact_entry("pair-derived PSF/detail receipt", psf_receipt_path, psf_receipt),
            artifact_entry("Mission 1 4K cleanup signoff", cleanup_signoff_path, cleanup_signoff),
            artifact_entry("Mission 1 8K SR promotion", sr_promotion_path, sr_promotion),
        ],
    }


def pct(value: float | None) -> str:
    if value is None:
        return "missing"
    return f"{value:.5g}"


def render_html(data: dict[str, Any], out_json: Path) -> str:
    checks = "\n".join(
        f"""<tr><td>{html.escape(check["id"])}</td><td class="{'pass' if check['passed'] else 'fail'}">{str(check['passed']).lower()}</td><td>{html.escape(check['production_meaning'])}</td></tr>"""
        for check in data["checks"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    next_actions = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    artifacts = "\n".join(
        f"""<tr><td>{html.escape(a["label"])}</td><td class="{'pass' if a['exists'] else 'fail'}">{str(a['exists']).lower()}</td><td>{html.escape(str(a.get("schema") or "missing"))}</td><td><a href="file://{html.escape(a["path"])}">{html.escape(a["path"])}</a></td></tr>"""
        for a in data["artifacts"]
    )
    psf = data["pair_derived_psf"]
    weights = ", ".join(f"{float(w):.8f}" for w in psf.get("normalized_weights") or [])
    phases = ", ".join(str(p) for p in psf.get("cfa_phases") or [])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GPR Raw Video PSF Audit</title>
  <style>
    body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f3f6f8; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 38px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 10px; font-size: 22px; }}
    p {{ color: #52606d; max-width: 850px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d8e0e6; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e4e9ed; text-align: left; vertical-align: top; }}
    th {{ color: #52606d; font-size: 12px; text-transform: uppercase; }}
    a {{ color: #075c9f; }}
    .hero {{ padding-bottom: 22px; }}
    .score {{ display: flex; align-items: end; gap: 18px; margin-top: 16px; }}
    .num {{ font-size: 58px; font-weight: 780; }}
    .label {{ color: #52606d; padding-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 18px 0; }}
    .card {{ background: white; border: 1px solid #d8e0e6; border-radius: 8px; padding: 15px; }}
    .k {{ color: #52606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .v {{ font-size: 26px; font-weight: 740; margin-top: 6px; overflow-wrap: anywhere; }}
    .section {{ margin-top: 18px; background: white; border: 1px solid #d8e0e6; border-radius: 8px; padding: 18px; }}
    .section table {{ border: 0; }}
    .pass {{ color: #16794c; font-weight: 760; }}
    .fail {{ color: #a33a32; font-weight: 760; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>Raw Video PSF / SR Audit</h1>
    <p>Approved 4K cleanup and 8K SR baselines are separated from unfinished native PSF-aware replacement work. This prevents the current useful SR path from being mistaken for a completed PSF model.</p>
    <div class="score"><div class="num">{data["readiness_percent"]}%</div><div class="label">PSF-aware video-improvement readiness; production ready: {str(data["production_ready"]).lower()}</div></div>
  </section>
  <div class="grid">
    <div class="card"><div class="k">4K cleanup baseline</div><div class="v">{str(data["summary"]["cleanup_4k_ready"]).lower()}</div></div>
    <div class="card"><div class="k">8K SR baseline</div><div class="v">{str(data["summary"]["sr_8k_ready"]).lower()}</div></div>
    <div class="card"><div class="k">PSF replacement</div><div class="v">{str(data["psf_replacement_ready"]).lower()}</div></div>
    <div class="card"><div class="k">Pair fixtures</div><div class="v">{psf["pair_count"]}</div></div>
    <div class="card"><div class="k">Best modeled kernel</div><div class="v">{html.escape(str(psf.get("best_kernel") or "missing"))}</div></div>
    <div class="card"><div class="k">Fine residual share</div><div class="v">{html.escape(pct(psf.get("fine_share_of_residual_abs")))}</div></div>
  </div>
  <section class="section">
    <h2>Pair-Derived PSF Detail Budget</h2>
    <table>
      <tr><th>metric</th><th>value</th></tr>
      <tr><td>CFA phases</td><td>{html.escape(phases or "missing")}</td></tr>
      <tr><td>sharp-edge fixtures</td><td>{psf["sharp_edge_count"]}</td></tr>
      <tr><td>texture-field fixtures</td><td>{psf["texture_field_count"]}</td></tr>
      <tr><td>normalized weights</td><td>{html.escape(weights or "missing")}</td></tr>
      <tr><td>RMSE, 14-bit scale</td><td>{html.escape(pct(psf.get("rmse_14bit")))}</td></tr>
      <tr><td>mid residual share</td><td>{html.escape(pct(psf.get("mid_share_of_residual_abs")))}</td></tr>
      <tr><td>coarse residual share</td><td>{html.escape(pct(psf.get("coarse_share_of_residual_abs")))}</td></tr>
      <tr><td>residual / target same-cell detail</td><td>{html.escape(pct(psf.get("residual_to_target_cell_detail_ratio")))}</td></tr>
    </table>
  </section>
  <section class="section">
    <h2>Production Checks</h2>
    <table><tr><th>check</th><th>passed</th><th>meaning</th></tr>{checks}</table>
  </section>
  <section class="section">
    <h2>Blockers</h2>
    <ul>{blockers}</ul>
  </section>
  <section class="section">
    <h2>Next Actions</h2>
    <ul>{next_actions}</ul>
  </section>
  <section class="section">
    <h2>Artifacts</h2>
    <table><tr><th>artifact</th><th>exists</th><th>schema</th><th>path</th></tr>{artifacts}</table>
  </section>
  <p class="meta">Generated {html.escape(data["created_utc"])}. JSON: {html.escape(str(out_json))}. Mode: {html.escape(data["mode"])}.</p>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--output-dir", type=Path, default=None)
    ap.add_argument("--psf-receipt", default=DEFAULT_PSF_RECEIPT)
    ap.add_argument("--cleanup-signoff", default=DEFAULT_4K_SIGNOFF)
    ap.add_argument("--sr-promotion", default=DEFAULT_8K_PROMOTION)
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d", time.gmtime())
        output_dir = args.external_root / "artifacts" / f"raw_video_psf_audit_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    psf_receipt_path = resolve_artifact(args.external_root, args.psf_receipt)
    cleanup_signoff_path = resolve_artifact(args.external_root, args.cleanup_signoff)
    sr_promotion_path = resolve_artifact(args.external_root, args.sr_promotion)
    data = build_audit(
        args.external_root,
        psf_receipt_path,
        cleanup_signoff_path,
        sr_promotion_path,
        synthetic=args.synthetic,
    )

    out_json = output_dir / "raw_video_psf_audit.json"
    out_html = output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, out_json), encoding="utf-8")
    print(out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
