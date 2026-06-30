#!/usr/bin/env python3
"""Build the four-pillar GPR product scorecard.

This is a summary and audit layer over committed docs plus large external
receipts. It deliberately keeps "production ready" false while real Mission 1
camera closure, premium still-SR promotion, and formal native PSF evidence are
open.
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


def repo_ref(label: str, path: str) -> dict[str, Any]:
    return {"label": label, "kind": "repo", "path": path}


def artifact_ref(label: str, path: str) -> dict[str, Any]:
    return {"label": label, "kind": "artifact", "path": path}


def resolve_ref(ref: dict[str, Any], external_root: Path) -> Path:
    path = Path(str(ref["path"]))
    if path.is_absolute():
        return path
    if ref["kind"] == "repo":
        return ROOT / path
    return external_root / path


def annotate_refs(refs: list[dict[str, Any]], external_root: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for ref in refs:
        resolved = resolve_ref(ref, external_root)
        annotated = dict(ref)
        annotated["resolved_path"] = str(resolved)
        annotated["exists"] = resolved.exists()
        result.append(annotated)
    return result


def build_scorecard(external_root: Path) -> dict[str, Any]:
    pillars = [
        {
            "id": "raw_stills",
            "title": "1. Best RAW stills",
            "readiness_percent": 90,
            "status": "strong_current_surface",
            "production_ready": False,
            "claim": "Production-gated still tiers for the currently tested normal Bayer surface, including 12/14/16-bit, 50 MP, real X2D 100MP-class visual evidence, and real RGGB plus Mission 1 GBRG fixture coverage.",
            "done_evidence": [
                "50 MP still tiers average 9.80 MB, 15.05 MB, and 27.17 MB while passing the committed visual gate.",
                "Capability and still-matrix coverage include 12 MP, 23 MP, 50 MP, 100 MP-class rows and RGGB/GBRG/GRBG/BGGR synthetic conformance.",
                "Real fixture compatibility covers Mission 1, Z8, X2D, and iPhone CFA DNG/GPR surfaces.",
                "The real Bayer phase discovery covers canonical plus broader local Mission 1/Z8/X2D/iPhone DNG pools and finds 70 RGGB plus 4 Mission 1 GBRG normal-Bayer fixtures.",
                "A real X2D 100MP DNG to GPR to DNG visual audit records 11,664 x 8,750 Bayer roundtrip evidence with 100% crop panels and 49.21 dB full-image raw PSNR.",
                "X2D and Z8 darkframe-derived noise sidecars are validated and ready for conditioning experiments.",
                "The camera-noise coverage audit confirms calibrated noise sidecars for X2D and Z8, and explicitly marks Mission 1/iPhone as missing validated darkframe sidecars.",
                "The Mission/iPhone darkframe candidate audit found 9 Mission 1 dark-looking frames, but no same-camera/ISO/CFA group has the required four-frame production stack.",
            ],
            "open_work": [
                "Add real GRBG and BGGR camera fixtures so alternate Bayer support is fully backed by real cameras, not only synthetic cells.",
                "Collect or locate same-ISO Mission 1 and CFA iPhone darkframe stacks, then apply camera-noise calibration before promoting nonzero noise removal/addback for those cameras.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("still/video ship decision", "docs/SHIP_DECISION.md"),
                    repo_ref("local fixture compatibility", "docs/LOCAL_FIXTURE_COMPATIBILITY.md"),
                    repo_ref("camera noise calibration contract", "docs/CAMERA_NOISE_CALIBRATION.md"),
                    artifact_ref("stills visual dashboard", "artifacts/visual_compare_20260525_final/index.html"),
                    artifact_ref("X2D 100MP still visual audit", "artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html"),
                    artifact_ref("real Bayer phase discovery", "artifacts/bayer_phase_fixture_discovery_20260630_rawpy/index.html"),
                    artifact_ref("camera noise coverage audit", "artifacts/camera_noise_coverage_audit_20260630/index.html"),
                    artifact_ref("Mission/iPhone darkframe candidate audit", "artifacts/darkframe_candidate_audit_mission_iphone_20260630/index.html"),
                    artifact_ref("camera noise sidecars", "artifacts/camera_noise_sidecars_20260629"),
                    artifact_ref("real fixture compatibility", "artifacts/real_fixture_compatibility"),
                ],
                external_root,
            ),
        },
        {
            "id": "raw_video_mvp",
            "title": "2. GoPro RAW video MVP",
            "readiness_percent": 80,
            "status": "pi_stand_in_pass_camera_handoff_open",
            "production_ready": False,
            "claim": "True 4096 x 3072 Bayer frames can be recompressed into .gvid and previewed above the accepted 20 fps Pi 5 stand-in floor.",
            "done_evidence": [
                ".gvid stores per-frame FUSED .gpr Bayer payloads rather than packed original camera files.",
                "Pi 5 stand-in capture has valid .gvid, zero-drop, interrupted-tail, and Lexar SILVER PLUS write-budget evidence.",
                "1024 x 768 camera-back preview decodes from the same 4K .gvid stream above 20 fps on the Pi stand-in.",
                "Labs handoff docs, quick validation scripts, target closure package, and conformance tests exist.",
                "The GoPro Mission 1 intake audit verifies the portable handoff bundle, required firmware docs, 4K .gvid sample, quick-validation dry run, and stand-in receipts while keeping camera-production readiness false.",
            ],
            "open_work": [
                "Run the same path from real Mission 1 sensor/DMA or camera ring-buffer source.",
                "Collect SD writer and rear-display/UI receipts from actual Mission 1 firmware.",
                "Only chase strict 24 fps after real camera source timing is known; current accepted floor is 20+ fps.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("Mission 1 quick validation", "docs/GOPRO_MISSION1_QUICK_VALIDATION.md"),
                    repo_ref("Mission 1 stream source timing", "docs/MISSION1_STREAM_SOURCE_TIMING_2026-06-28.md"),
                    repo_ref("GVID conformance", "docs/GVID_CONFORMANCE.md"),
                    artifact_ref("GoPro Mission 1 intake audit", "artifacts/gopro_mission1_intake_audit_20260630/index.html"),
                    artifact_ref("Pi stream source receipts", "artifacts/mission1_stream_source_encoder_20260628_pi_compact"),
                    artifact_ref("preview timing receipt", "artifacts/mission1_preview_rgb_c_1024x768_72f_20260624/receipt.json"),
                    artifact_ref("Z8 preview media", "artifacts/z8_timelapse_readme_gif_frame800_20260624"),
                ],
                external_root,
            ),
        },
        {
            "id": "premium_still_sr",
            "title": "3. Spend-time-for-quality still/SR",
            "readiness_percent": 45,
            "status": "research_loop_working_candidate_not_promoted",
            "production_ready": False,
            "claim": "The offline still-SR machinery is broad and reproducible, but the current no-REF texture model is not good enough to promote.",
            "done_evidence": [
                "Matched 1x CNN lets q0/q3 still tiers pass the visual gate.",
                "Routed X2D, Z8, and Mission 1 specialists have fixture manifests, full-frame receipts, rendered review, and editor-openability evidence.",
                "X2D high-frequency residual targets and multiscale/noise-conditioned probes isolate the remaining +2 EV texture gap.",
                "Latest scene-held-out X2D residual probe improves only 2.56 percent, which is useful diagnosis rather than production quality.",
            ],
            "open_work": [
                "Replace weak no-REF residual probe with a larger-context/raw-domain texture model or change the still-SR target/loss.",
                "Pass dedicated 50 MP and 100 MP still-SR gates with editor-latitude and worst-row visual evidence.",
                "Use calibrated noise sidecars as conditioning, then add back only noise proven separate from signal.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("premium still-SR contract", "docs/PREMIUM_STILL_SR.md"),
                    artifact_ref("premium still-SR readiness", "artifacts/premium_still_sr_readiness_20260630/index.html"),
                    artifact_ref("premium still-SR experiment scoreboard", "artifacts/premium_still_sr_experiment_scoreboard_20260630/index.html"),
                    artifact_ref("routed rendered review", "artifacts/premium_still_sr_rendered_review_routed_20260630/index.html"),
                    artifact_ref("X2D latitude review", "artifacts/premium_still_sr_x2d_latitude_review_synthetic_hf_20260630/index.html"),
                    artifact_ref("noise-conditioned residual dashboard", "artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/index.html"),
                    artifact_ref("specialist router plan", "artifacts/premium_still_sr_router_plan_20260630/index.html"),
                ],
                external_root,
            ),
        },
        {
            "id": "raw_video_psf_sr",
            "title": "4. RAW video improvement / PSF-aware resize",
            "readiness_percent": 42,
            "status": "approved_baseline_psf_replacement_open",
            "production_ready": False,
            "claim": "4K cleanup and 8K SR are approved offline baselines, while formal native PSF/blur-aware replacement work remains open.",
            "done_evidence": [
                "Mission native12 4K cleanup is approved for offline/review scope.",
                "Candidate-aware 8K SR passes broad Mission42 and Z8 full-frame gates with .gvid, editable raw, and ProRes receipts.",
                "Pair-derived PSF/detail budget over 1,024 real-fixture tiles fits a 2x2 same-color Bayer box model.",
                "The residual budget shows the 4K-to-8K gap is almost entirely same-cell fine detail, not coarse blur.",
                "The native Mission 1 high/low pair inventory now indexes near-time 8192 x 6144 and 4096 x 3072 capture candidates for a measured PSF pass.",
                "The raw-video PSF audit separates approved 4K/8K baselines from the unfinished native PSF replacement claim.",
                "The SR/detail candidate scoreboard indexes historical Mission/Z8 decisions and finds zero current-scale promotion rows.",
            ],
            "open_work": [
                "Measure native camera/sensor/display PSF from real high-res-to-native-low-res pairs.",
                "Train PSF-conditioned SR against CFA-aware high-res targets with explicit fine-detail reconstruction losses.",
                "Promote only if Mission42 and Z8 all24 gates beat the current approved baseline and worst rows stay clean.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("Bayer resize PSF policy", "docs/BAYER_RESIZE_PSF.md"),
                    repo_ref("CNN product scorecard", "docs/CNN_PRODUCT_SCORECARD_2026-06-29.md"),
                    artifact_ref("4K cleanup visual signoff", "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"),
                    artifact_ref("8K SR promotion receipt", "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json"),
                    artifact_ref("Mission42 8K dashboard", "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_broad_fullframe/index.html"),
                    artifact_ref("PSF xlarge detail budget", "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/bayer_resize_psf_receipt.json"),
                    artifact_ref("Mission 1 native high/low pair inventory", "artifacts/mission1_native_psf_pair_inventory_20260630/index.html"),
                    artifact_ref("raw-video PSF audit", "artifacts/raw_video_psf_audit_20260630/index.html"),
                    artifact_ref("raw-video SR/detail candidate scoreboard", "artifacts/raw_video_sr_candidate_scoreboard_20260630/index.html"),
                ],
                external_root,
            ),
        },
    ]
    four_pillar_percent = round(sum(p["readiness_percent"] for p in pillars) / len(pillars))
    return {
        "schema": "gpr.product_pillar_scorecard.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": str(external_root),
        "production_ready": all(bool(p["production_ready"]) for p in pillars),
        "four_pillar_completion_percent": four_pillar_percent,
        "interpretation": "This is an execution scorecard. It is intentionally not a release claim while any pillar has open production work.",
        "pillars": pillars,
        "next_actions": [
            "Replace the GoPro-facing Mission 1 stand-in intake bundle with camera-role sensor/DMA, storage, and rear-display receipts when a dev kit is available.",
            "Add real GRBG/BGGR fixtures and collect same-ISO Mission 1/CFA iPhone darkframes before promoting nonzero noise addback for those cameras.",
            "Replace premium still-SR residual probes with a larger-context raw-domain texture/noise model before claiming an amazing-still product.",
            "Run alignment, edge/texture mining, and measured PSF estimation on the Mission 1 native high/low candidate pairs, then gate against current 4K/8K baselines.",
        ],
    }


def status_class(pillar: dict[str, Any]) -> str:
    pct = int(pillar["readiness_percent"])
    if pct >= 75:
        return "strong"
    if pct >= 50:
        return "partial"
    return "open"


def render_link(ref: dict[str, Any]) -> str:
    label = html.escape(str(ref["label"]))
    path = html.escape(str(ref["resolved_path"]))
    state = "ok" if ref.get("exists") else "missing"
    return f'<li><a href="file://{path}">{label}</a> <span class="{state}">{state}</span></li>'


def render_html(data: dict[str, Any], out_json: Path) -> str:
    cards = []
    sections = []
    for pillar in data["pillars"]:
        klass = status_class(pillar)
        cards.append(
            f"""<section class="card {klass}">
  <div class="eyebrow">{html.escape(pillar["title"])}</div>
  <div class="pct">{pillar["readiness_percent"]}%</div>
  <p>{html.escape(pillar["claim"])}</p>
</section>"""
        )
        done = "\n".join(f"<li>{html.escape(item)}</li>" for item in pillar["done_evidence"])
        open_work = "\n".join(f"<li>{html.escape(item)}</li>" for item in pillar["open_work"])
        refs = "\n".join(render_link(ref) for ref in pillar["evidence"])
        sections.append(
            f"""<section class="detail">
  <h2>{html.escape(pillar["title"])}</h2>
  <div class="status-line"><strong>{pillar["readiness_percent"]}%</strong> / {html.escape(pillar["status"])} / production ready: {str(pillar["production_ready"]).lower()}</div>
  <div class="cols">
    <div><h3>What is proven</h3><ul>{done}</ul></div>
    <div><h3>What remains</h3><ul>{open_work}</ul></div>
  </div>
  <h3>Evidence</h3>
  <ul class="refs">{refs}</ul>
</section>"""
        )
    next_actions = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GPR Product Pillar Scorecard</title>
  <style>
    body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #101418; background: #f4f6f7; }}
    main {{ max-width: 1220px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 38px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 8px; font-size: 23px; }}
    h3 {{ margin: 14px 0 8px; font-size: 14px; text-transform: uppercase; color: #53606d; }}
    p {{ margin: 8px 0 0; }}
    ul {{ margin: 0; padding-left: 20px; }}
    li {{ margin: 4px 0; }}
    a {{ color: #075c9f; }}
    .hero {{ padding: 22px 0 26px; }}
    .sub {{ max-width: 860px; color: #56616d; font-size: 17px; }}
    .headline {{ display: flex; gap: 20px; align-items: end; flex-wrap: wrap; margin-top: 18px; }}
    .overall {{ font-size: 54px; font-weight: 760; }}
    .overall-label {{ color: #56616d; padding-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; min-height: 150px; }}
    .card.strong {{ border-top: 5px solid #16794c; }}
    .card.partial {{ border-top: 5px solid #b87900; }}
    .card.open {{ border-top: 5px solid #a33a32; }}
    .eyebrow {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .pct {{ font-size: 36px; font-weight: 760; margin-top: 6px; }}
    .detail {{ margin-top: 18px; background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 18px; }}
    .status-line {{ color: #53606d; margin-bottom: 12px; }}
    .cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 24px; }}
    .refs {{ columns: 2; column-gap: 30px; }}
    .ok {{ color: #16794c; font-weight: 700; }}
    .missing {{ color: #a33a32; font-weight: 700; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>GPR Product Pillar Scorecard</h1>
    <p class="sub">{html.escape(data["interpretation"])}</p>
    <div class="headline">
      <div class="overall">{data["four_pillar_completion_percent"]}%</div>
      <div class="overall-label">four-pillar completion; production ready: {str(data["production_ready"]).lower()}</div>
    </div>
  </section>
  <div class="grid">
    {''.join(cards)}
  </div>
  {''.join(sections)}
  <section class="detail">
    <h2>Next Actions</h2>
    <ul>{next_actions}</ul>
  </section>
  <p class="meta">Generated {html.escape(data["created_utc"])}. JSON: {html.escape(str(out_json))}. External root: {html.escape(data["external_root"])}.</p>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--output-dir", type=Path, default=None)
    args = ap.parse_args()

    external_root = args.external_root
    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d", time.gmtime())
        output_dir = external_root / "artifacts" / f"product_pillar_scorecard_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    data = build_scorecard(external_root)
    out_json = output_dir / "scorecard.json"
    out_html = output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, out_json), encoding="utf-8")
    print(out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
