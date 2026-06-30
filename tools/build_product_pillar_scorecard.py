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
            "lock_ledger_paths": [
                "STILL smallest",
                "STILL primary",
                "STILL archival",
            ],
            "open_production_gates": [
                "Broad real-camera Bayer phase coverage",
                "Mission 1 and iPhone nonzero noise addback",
            ],
            "locked_artifacts": [
                "production STILL q0/q3/q8 tiers",
                "12/14/16-bit still roundtrip support",
                "real X2D 100MP DNG to GPR to DNG visual audit",
                "synthetic RGGB/GBRG/GRBG/BGGR conformance",
            ],
            "claim": "Production-gated still tiers for the currently tested normal Bayer surface, including 12/14/16-bit, 50 MP, real X2D 100MP-class visual evidence, and real RGGB plus GoPro/Mission GBRG fixture coverage.",
            "done_evidence": [
                "50 MP still tiers average 9.80 MB, 15.05 MB, and 27.17 MB while passing the committed visual gate.",
                "Capability and still-matrix coverage include 12 MP, 23 MP, 50 MP, 100 MP-class rows and RGGB/GBRG/GRBG/BGGR synthetic conformance.",
                "Real fixture compatibility covers Mission 1, Z8, X2D, and iPhone CFA DNG/GPR surfaces.",
                "The targeted 3,000-file GoPro/Mission DNG/GPR scan parses every file as normal Bayer and finds 2,892 GBRG plus 108 RGGB fixtures; GRBG/BGGR are still missing as real fixtures.",
                "A real X2D 100MP DNG to GPR to DNG visual audit records 11,664 x 8,750 Bayer roundtrip evidence with 100% crop panels and 49.21 dB full-image raw PSNR.",
                "X2D and Z8 darkframe-derived noise sidecars are validated and ready for conditioning experiments.",
                "The camera-noise coverage audit confirms calibrated noise sidecars for X2D and Z8, and explicitly marks Mission 1/iPhone as missing validated darkframe sidecars.",
                "The camera-noise runtime policy enables nonzero denoised targets/noise addback only for exact X2D/Z8 sidecar ISOs and forces Mission 1/iPhone to metadata-conditioning-only until their sidecars validate.",
                "The targeted Mission DNG darkframe candidate audit found 9 Mission 1 dark-looking frames, but no same-camera/ISO/CFA group has the required four-frame production stack.",
                "The stills fixture gap plan turns the phase/noise receipts into a concrete capture checklist and identifies the lowest-lift Mission darkframe top-up: ISO232 RGGB has two candidates and needs two more matching frames.",
                "The raw-stills capture request converts that checklist into handoff-ready sample requests, validation commands, and promotion criteria.",
            ],
            "open_work": [
                "Fulfill the raw-stills capture request: add real GRBG and BGGR camera fixtures, then collect or locate same-ISO Mission 1 and CFA iPhone darkframe stacks.",
                "Keep nonzero noise removal/addback disabled for cameras without validated darkframe sidecars.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("still/video ship decision", "docs/SHIP_DECISION.md"),
                    repo_ref("local fixture compatibility", "docs/LOCAL_FIXTURE_COMPATIBILITY.md"),
                    repo_ref("camera noise calibration contract", "docs/CAMERA_NOISE_CALIBRATION.md"),
                    artifact_ref("stills visual dashboard", "artifacts/visual_compare_20260525_final/index.html"),
                    artifact_ref("X2D 100MP still visual audit", "artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html"),
                    artifact_ref("real Bayer phase discovery", "artifacts/bayer_phase_fixture_discovery_20260630_rawpy/index.html"),
                    artifact_ref("targeted 3,000-file Bayer phase scan", "artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/index.html"),
                    artifact_ref("camera noise coverage audit", "artifacts/camera_noise_coverage_audit_20260630/index.html"),
                    artifact_ref("camera noise runtime policy", "artifacts/camera_noise_runtime_policy_20260630/index.html"),
                    artifact_ref("Mission/iPhone darkframe candidate audit", "artifacts/darkframe_candidate_audit_mission_iphone_20260630/index.html"),
                    artifact_ref("targeted Mission DNG darkframe scan", "artifacts/darkframe_candidate_audit_targeted_dng_20260630/index.html"),
                    artifact_ref("stills fixture gap plan", "artifacts/stills_fixture_gap_plan_20260630/index.html"),
                    artifact_ref("raw-stills capture request", "artifacts/stills_capture_request_20260630/index.html"),
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
            "lock_ledger_paths": [
                "VIDEO_FREEZE",
                "UPRESABLE editable raw",
                "Mission 1 Pi stand-in raw-video encode",
                "Mission 1 Pi stand-in preview",
            ],
            "open_production_gates": [
                "Real Mission 1 camera-role raw-video closure",
            ],
            "locked_artifacts": [
                "VIDEO_FREEZE desktop/post raw-video path",
                "UPRESABLE half-resolution capture to editable full-resolution raw",
                "Pi 5 stand-in 4K Bayer .gvid encode receipts above the accepted 20 fps floor",
                "Pi 5 stand-in 1024 x 768 preview receipts above the accepted 20 fps floor",
                ".gvid validation, metadata dispatch, and interrupted-tail recovery checks",
                "Labs handoff docs and quick-validation tooling",
            ],
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
            "readiness_percent": 60,
            "status": "research_loop_working_candidate_not_promoted",
            "production_ready": False,
            "lock_ledger_paths": [
                "Mission 1 4K cleanup",
                "Mission 1 8K SR",
            ],
            "open_production_gates": [
                "Premium still-SR promotion",
            ],
            "locked_artifacts": [
                "matched 1x CNN support for committed STILL q0/q3 visual gates",
                "routed specialist infrastructure and fixture manifests",
                "approved Mission 1 4K cleanup and 8K SR outputs as source candidates for expensive still/post workflows",
                "raw-CFA target construction over the expanded 351-row set",
                "editor-openability and rendered review receipts for diagnostics",
            ],
            "claim": "The offline still-SR machinery is broad and reproducible, but the current no-REF texture model is not good enough to promote.",
            "done_evidence": [
                "Matched 1x CNN lets q0/q3 still tiers pass the visual gate.",
                "Routed X2D, Z8, and Mission 1 specialists have fixture manifests, full-frame receipts, rendered review, and editor-openability evidence.",
                "X2D high-frequency residual targets and multiscale/noise-conditioned probes isolate the remaining +2 EV texture gap.",
                "Latest scene-held-out X2D residual probe improves only 2.56 percent, which is useful diagnosis rather than production quality.",
                "The blocker audit now ranks the next still-SR failure axes: metric gap, target coverage, runtime feature sufficiency, noise policy, and missing full promotion gate.",
                "The target expansion plan selected 10 additional X2D/Z8 scenes with validated noise sidecars, and the expanded target executor built the 13-scene / 351-row merged HF target set.",
                "Expanded target band analysis confirms the remaining residual is still fine-band dominated, with median fine-band residual share about 0.981x.",
                "The first expanded rendered-context training passes have run: the weighted w96 model was unstable and the conservative w64 control landed near zero holdout recovery, so target coverage alone is not sufficient.",
                "The expanded raw-CFA target rebuild now has complete candidate_raw_cfa4 coverage for all 351 rows / 13 scenes.",
                "The raw-CFA gated model beats matched RGB ablations on expanded Z8 and X2D scene holdouts, but the best broad holdout remains only 2.92 percent median MAE recovery and is not promotable.",
                "A matched dilated raw-CFA gated variant has also run: it improves the weak Z8 holdout from 1.04 to 1.30 percent median MAE recovery, but trails the X2D gated baseline at 2.86 versus 2.92 percent and leaves severe negative worst rows.",
                "A calibrated noise-clean target sweep now exists for the X2D raw-CFA smoke target; it shows ISO 200 sidecar noise is far below the HF residual, so sensor-noise removal alone is not the current still-SR blocker.",
                "A 351-row raw-CFA residual audit compares rendered HF supervision with source-minus-candidate same-color raw residuals; median absolute correlation is 0.691 and median best-phase correlation is 0.922, making true raw-domain residual supervision the next model target.",
                "The 351-row raw-CFA residual target NPZ has now been built for training: candidate raw-CFA, candidate raw-HF, source raw-HF, rendered-HF luma review, and source-minus-candidate same-color raw-HF residual arrays are hashed and receipted.",
                "The first true raw-CFA residual trainer now runs against that NPZ with candidate-only runtime inputs. A stabilized w32/2000-step pass is mildly positive on held-out Z8 at about 0.50 percent median raw-residual MAE recovery, but held-out X2D remains negative at about -0.21 percent.",
                "Follow-up X2D probes show a wider/block17 model barely clears zero at about 0.02 percent median recovery, while stored candidate-HF features and naive one-sigma noise soft-thresholding remain negative. This is blocker evidence rather than a production checkpoint.",
            ],
            "open_work": [
                "Replace the weak first raw-CFA residual learner with a model/objective that clears both Z8 and X2D held-out raw-residual gates; the current blocker is X2D/domain generalization and low recovery, not target construction.",
                "Pass dedicated 50 MP and 100 MP still-SR gates with editor-latitude and worst-row visual evidence.",
                "Use calibrated noise sidecars as conditioning, then add back only noise proven separate from signal.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("premium still-SR contract", "docs/PREMIUM_STILL_SR.md"),
                    artifact_ref("premium still-SR readiness", "artifacts/premium_still_sr_readiness_20260630/index.html"),
                    artifact_ref("premium still-SR experiment scoreboard", "artifacts/premium_still_sr_experiment_scoreboard_20260630/index.html"),
                    artifact_ref("premium still-SR blocker audit", "artifacts/premium_still_sr_blocker_audit_20260630/index.html"),
                    artifact_ref("premium still-SR target expansion plan", "artifacts/premium_still_sr_target_expansion_plan_20260630/index.html"),
                    artifact_ref("premium still-SR expanded target build", "artifacts/premium_still_sr_expanded_hf_targets_20260630/expanded_target_build_receipt.json"),
                    artifact_ref("premium still-SR expanded target receipt", "artifacts/premium_still_sr_expanded_hf_targets_20260630/merged/merge_receipt.json"),
                    artifact_ref("premium still-SR expanded band analysis", "artifacts/premium_still_sr_expanded_hf_residual_band_analysis_20260630/index.html"),
                    artifact_ref("premium still-SR expanded unstable w96 receipt", "artifacts/premium_still_sr_expanded_render_context_model_sceneholdout_w96_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR expanded stable w64 receipt", "artifacts/premium_still_sr_expanded_render_context_model_sceneholdout_stable_w64_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA smoke target", "artifacts/premium_still_sr_rawcfa_smoke_targets_20260630/2025_10_oct_austin_0626/hf_residual_targets.json"),
                    artifact_ref("premium still-SR raw-CFA probe receipt", "artifacts/premium_still_sr_rawcfa_probe_model_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR RGB ablation receipt", "artifacts/premium_still_sr_rawcfa_ablation_rgb_model_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA gated probe receipt", "artifacts/premium_still_sr_rawcfa_gated_probe_w48_1000_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR expanded raw-CFA target build", "artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/expanded_target_build_receipt.json"),
                    artifact_ref("premium still-SR expanded raw-CFA merge receipt", "artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630/merged/merge_receipt.json"),
                    artifact_ref("premium still-SR expanded raw-CFA gated Z8 holdout", "artifacts/premium_still_sr_expanded_rawcfa_gated_model_z8holdout_w48_1000_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR expanded raw-CFA gated X2D holdout", "artifacts/premium_still_sr_expanded_rawcfa_gated_model_x2dholdout_w48_1000_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR expanded raw-CFA dilated gated Z8 holdout", "artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_z8holdout_matched_w48_1000_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR expanded raw-CFA dilated gated X2D holdout", "artifacts/premium_still_sr_expanded_rawcfa_dilated_gated_model_x2dholdout_matched_w48_1000_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR noise-clean sweep", "artifacts/premium_still_sr_noise_clean_sweep_x2d_smoke_20260630/index.html"),
                    artifact_ref("premium still-SR raw-CFA residual audit", "artifacts/premium_still_sr_raw_cfa_residual_audit_20260630/index.html"),
                    artifact_ref("premium still-SR raw-CFA residual targets", "artifacts/premium_still_sr_raw_cfa_residual_targets_20260630/index.html"),
                    artifact_ref("premium still-SR raw-CFA residual Z8 holdout model", "artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_w32_2000_lowlr_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D holdout model", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w32_2000_lowlr_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D wider-context model", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w64_5000_block17_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D stored-HF model", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_storedhf_w32_2000_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D noise-threshold model", "artifacts/premium_still_sr_raw_cfa_signal_residual_model_x2dholdout_w32_2000_thr1_20260630/train_receipt.json"),
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
            "readiness_percent": 44,
            "status": "approved_baseline_psf_replacement_open",
            "production_ready": False,
            "lock_ledger_paths": [
                "Mission 1 4K cleanup",
                "Mission 1 8K SR",
            ],
            "open_production_gates": [
                "PSF-aware raw-video replacement",
            ],
            "locked_artifacts": [
                "approved Mission native12 4K cleanup offline/review baseline",
                "approved candidate-aware 8K SR offline/reconstruction baseline",
                "continuous 8K no-CNN versus CNN ProRes review media",
                "8K .gvid, editable raw, and ProRes review receipts",
                "first native Mission 1 PSF measurement run as blocker evidence",
            ],
            "claim": "4K cleanup and 8K SR are approved offline baselines, while formal native PSF/blur-aware replacement work remains open.",
            "done_evidence": [
                "Mission native12 4K cleanup is approved for offline/review scope.",
                "Candidate-aware 8K SR passes broad Mission42 and Z8 full-frame gates with .gvid, editable raw, and ProRes receipts.",
                "A true continuous-scene 8K ProRes A/B now compares a no-CNN 4096 x 3072 raw Bayer baseline display-upscaled to 8192 x 6144 against the approved 4K cleanup plus 8K SR CNN raw Bayer path.",
                "Pair-derived PSF/detail budget over 1,024 real-fixture tiles fits a 2x2 same-color Bayer box model.",
                "The residual budget shows the 4K-to-8K gap is almost entirely same-cell fine detail, not coarse blur.",
                "The native Mission 1 high/low pair inventory now indexes near-time 8192 x 6144 and 4096 x 3072 capture candidates for a measured PSF pass.",
                "The native PSF measurement plan selects the best decoded high/low pairs and defines the alignment, edge/texture mining, kernel fitting, and promotion gates required next.",
                "The first native PSF measurement run executed on the selected Mission 1 pairs: 2 of 3 pairs passed scene/alignment vetting with 1,409 sharp-edge and 1,381 texture-field tiles, but the kernel is unstable and rejected for model conditioning.",
                "The raw-video PSF audit separates approved 4K/8K baselines from the unfinished native PSF replacement claim.",
                "The raw-video PSF gap plan now turns that failed native measurement into a concrete capture, measurement, model-gate, and promotion checklist.",
                "The native PSF corpus audit hashes the current near-time candidate pairs and records zero strict controlled pairs, because ISO/settings are not fixed tightly enough, fixed camera-setting metadata and negative controls are missing, and the existing measurement still accepts only two pairs with an unstable kernel.",
                "The controlled-capture request now requires source GPR/DNG hashes, decoded little-endian uint16 Bayer hashes, fixed ISO/exposure/WB/lens/sharpening settings, and negative controls before a measured kernel can be promoted.",
                "The SR/detail candidate scoreboard indexes historical Mission/Z8 decisions and finds zero current-scale promotion rows.",
            ],
            "open_work": [
                "Follow the raw-video PSF gap plan: capture or locate controlled same-scene Mission 1 high/low pairs with source hashes, decoded Bayer hashes, fixed settings, and negative controls so at least three pairs pass scene vetting and produce a stable measured native PSF kernel.",
                "Train PSF-conditioned SR against CFA-aware high-res targets with explicit fine-detail reconstruction losses.",
                "Promote only if Mission42 and Z8 all24 gates beat the current approved baseline and worst rows stay clean.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("Bayer resize PSF policy", "docs/BAYER_RESIZE_PSF.md"),
                    repo_ref("CNN product scorecard", "docs/CNN_PRODUCT_SCORECARD_2026-06-29.md"),
                    artifact_ref("4K cleanup visual signoff", "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"),
                    artifact_ref("8K SR promotion receipt", "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json"),
                    artifact_ref("continuous 8K no-CNN vs CNN ProRes review", "artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/receipt.json"),
                    artifact_ref("Mission42 8K dashboard", "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_broad_fullframe/index.html"),
                    artifact_ref("PSF xlarge detail budget", "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/bayer_resize_psf_receipt.json"),
                    artifact_ref("Mission 1 native high/low pair inventory", "artifacts/mission1_native_psf_pair_inventory_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF measurement plan", "artifacts/mission1_native_psf_measurement_plan_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF measurement", "artifacts/mission1_native_psf_measurement_20260630/index.html"),
                    artifact_ref("raw-video PSF audit", "artifacts/raw_video_psf_audit_20260630/index.html"),
                    artifact_ref("raw-video PSF gap plan", "artifacts/raw_video_psf_gap_plan_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF corpus audit", "artifacts/mission1_native_psf_corpus_audit_20260630/index.html"),
                    artifact_ref("raw-video PSF controlled capture request", "artifacts/raw_video_psf_capture_request_20260630/index.html"),
                    artifact_ref("raw-video SR/detail candidate scoreboard", "artifacts/raw_video_sr_candidate_scoreboard_20260630/index.html"),
                ],
                external_root,
            ),
        },
    ]
    four_pillar_percent = int(sum(p["readiness_percent"] for p in pillars) / len(pillars) + 0.5)
    return {
        "schema": "gpr.product_pillar_scorecard.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": str(external_root),
        "production_ready": all(bool(p["production_ready"]) for p in pillars),
        "four_pillar_completion_percent": four_pillar_percent,
        "interpretation": "This is an execution scorecard. It is intentionally not a release claim while any pillar has open production work.",
        "score_semantics": {
            "kind": "readiness_burndown_estimate",
            "not_a_quality_metric": True,
            "not_a_locked_artifact_regression_signal": True,
            "denominator": (
                "The denominator is the four-pillar production suite: raw stills, raw video MVP, "
                "premium still/SR, and PSF-aware video/SR. Scores move only when the scope or "
                "evidence for those pillars changes, not when an approved artifact is re-reviewed."
            ),
            "policy": (
                "Readiness percentages summarize remaining production evidence, fixture, hardware, and promotion work. "
                "They must not be interpreted as a regression of locked algorithms. A locked artifact regresses only if "
                "its own committed gate, receipt, hash, or CI guard fails."
            ),
            "locked_artifact_examples": [
                "production STILL q0/q3/q8 tiers",
                "Mission 1 4K cleanup offline/review checkpoint",
                "Mission 1 candidate-aware 8K SR offline checkpoint",
                "Mission 1 Pi-stand-in raw-video/preview receipts",
            ],
        },
        "pillars": pillars,
        "next_actions": [
            "Replace the GoPro-facing Mission 1 stand-in intake bundle with camera-role sensor/DMA, storage, and rear-display receipts when a dev kit is available.",
            "Fulfill the raw-stills capture request: add real GRBG/BGGR fixtures and collect same-ISO Mission 1/CFA iPhone darkframes before promoting nonzero noise addback; the current lowest-lift Mission top-up is ISO232 RGGB with two matching frames still needed.",
            "Continue premium still-SR from the current raw-CFA residual blocker: held-out Z8 is mildly positive, hard X2D is only barely positive after wider context, and stored-HF/noise-threshold probes did not solve it.",
            "Follow the raw-video PSF gap plan: capture controlled same-scene Mission 1 high/low pairs, rerun native measurement until the kernel is stable, then gate a PSF-conditioned SR model against the current 4K/8K baselines.",
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
        ledger_paths = "\n".join(f"<li>{html.escape(item)}</li>" for item in pillar["lock_ledger_paths"])
        open_gates = "\n".join(f"<li>{html.escape(item)}</li>" for item in pillar["open_production_gates"])
        locked = "\n".join(f"<li>{html.escape(item)}</li>" for item in pillar["locked_artifacts"])
        done = "\n".join(f"<li>{html.escape(item)}</li>" for item in pillar["done_evidence"])
        open_work = "\n".join(f"<li>{html.escape(item)}</li>" for item in pillar["open_work"])
        refs = "\n".join(render_link(ref) for ref in pillar["evidence"])
        sections.append(
            f"""<section class="detail">
  <h2>{html.escape(pillar["title"])}</h2>
  <div class="status-line"><strong>{pillar["readiness_percent"]}%</strong> / {html.escape(pillar["status"])} / production ready: {str(pillar["production_ready"]).lower()}</div>
  <div class="cols">
    <div><h3>Lock ledger paths</h3><ul>{ledger_paths}</ul></div>
    <div><h3>Locked artifacts</h3><ul>{locked}</ul></div>
    <div><h3>Open production gates</h3><ul>{open_gates}</ul></div>
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
    .semantics {{ margin-top: 16px; padding: 12px 14px; background: #fff; border: 1px solid #dce2e7; border-left: 5px solid #1267a3; border-radius: 8px; max-width: 920px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; min-height: 150px; }}
    .card.strong {{ border-top: 5px solid #16794c; }}
    .card.partial {{ border-top: 5px solid #b87900; }}
    .card.open {{ border-top: 5px solid #a33a32; }}
    .eyebrow {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .pct {{ font-size: 36px; font-weight: 760; margin-top: 6px; }}
    .detail {{ margin-top: 18px; background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 18px; }}
    .status-line {{ color: #53606d; margin-bottom: 12px; }}
    .cols {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px; }}
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
    <p class="semantics"><strong>Readiness percentages are not quality metrics.</strong> They summarize remaining production evidence, fixture, hardware, and promotion work. Locked algorithms regress only when their own committed gate, receipt, hash, or CI guard fails.</p>
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
