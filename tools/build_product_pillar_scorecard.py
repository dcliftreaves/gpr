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
            "readiness_percent": 92,
            "status": "strong_current_surface",
            "production_ready": False,
            "lock_ledger_paths": [
                "STILL smallest",
                "STILL primary",
                "STILL archival",
                "Broad real-camera Bayer phase coverage",
            ],
            "open_production_gates": [
                "Mission 1 and iPhone nonzero noise addback",
            ],
            "locked_artifacts": [
                "production STILL q0/q3/q8 tiers",
                "12/14/16-bit still roundtrip support",
                "real X2D 100MP DNG to GPR to DNG visual audit",
                "real RGGB/GBRG/GRBG/BGGR fixture coverage",
            ],
            "claim": "Production-gated still tiers for the tested normal Bayer surface, including 12/14/16-bit, 50 MP, real X2D 100MP-class visual evidence, and real RGGB/GBRG/GRBG/BGGR fixture coverage.",
            "done_evidence": [
                "50 MP still tiers average 9.80 MB, 15.05 MB, and 27.17 MB while passing the committed visual gate.",
                "Capability and still-matrix coverage include 12 MP, 23 MP, 50 MP, 100 MP-class rows and RGGB/GBRG/GRBG/BGGR conformance.",
                "Real fixture compatibility covers Mission 1, Z8, X2D, and iPhone CFA DNG/GPR surfaces.",
                "The targeted 3,000-file GoPro/Mission DNG/GPR scan parses every file as normal Bayer and finds 2,892 GBRG plus 108 RGGB fixtures.",
                "The broad old-photo scan adds 120 real GRBG Nikon D200 fixtures and 80 real BGGR Nikon D70 fixtures, closing the real normal-Bayer phase coverage gap when combined with the GoPro/Mission scan.",
                "A real X2D 100MP DNG to GPR to DNG visual audit records 11,664 x 8,750 Bayer roundtrip evidence with 100% crop panels and 49.21 dB full-image raw PSNR.",
                "X2D and Z8 darkframe-derived noise sidecars are validated and ready for conditioning experiments.",
                "The camera-noise coverage audit confirms calibrated noise sidecars for X2D and Z8, and explicitly marks Mission 1/iPhone as missing validated darkframe sidecars.",
                "The camera-noise runtime policy enables nonzero denoised targets/noise addback only for exact X2D/Z8 sidecar ISOs and forces Mission 1/iPhone to metadata-conditioning-only until their sidecars validate.",
                "The full-manifest Mission/iPhone darkframe candidate audit parses 1,997 of 2,000 bounded manifest rows, finds 59 dark-like frames and four iPhone same-ISO candidate stacks, but keeps production sidecar readiness false because candidate-discovery scene frames still need confirmed no-scene-signal provenance.",
                "The stills fixture gap plan now reports all real normal Bayer phases ready and identifies per-family lowest-lift paths: Mission ISO232 RGGB has two candidates and needs two more matching frames; iPhone ISO1250 RGGB has 27 dark-like candidates but needs no-scene provenance before promotion.",
                "The raw-stills capture request now asks only for Mission 1 and iPhone darkframe stacks, with per-family lowest-lift follow-ups, validation commands, and promotion criteria.",
            ],
            "open_work": [
                "Fulfill the raw-stills capture request: top up/confirm the Mission ISO232 RGGB stack and prove whether the iPhone ISO1250 RGGB dark-like candidate set is true no-scene-signal data or must be recaptured.",
                "Keep nonzero noise removal/addback disabled for cameras without validated darkframe sidecars.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("still/video ship decision", "docs/SHIP_DECISION.md"),
                    repo_ref("local fixture compatibility", "docs/LOCAL_FIXTURE_COMPATIBILITY.md"),
                    repo_ref("camera noise calibration contract", "docs/CAMERA_NOISE_CALIBRATION.md"),
                    repo_ref("production capture requirements", "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md"),
                    artifact_ref("stills visual dashboard", "artifacts/visual_compare_20260525_final/index.html"),
                    artifact_ref("X2D 100MP still visual audit", "artifacts/x2d_100mp_still_visual_audit_roundtrip_20260630/index.html"),
                    artifact_ref("real Bayer phase discovery", "artifacts/bayer_phase_fixture_discovery_20260630_rawpy/index.html"),
                    artifact_ref("targeted 3,000-file Bayer phase scan", "artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/index.html"),
                    artifact_ref("broad old-photo Bayer phase scan", "artifacts/bayer_phase_fixture_discovery_broad_photos_20260701/index.html"),
                    artifact_ref("camera noise coverage audit", "artifacts/camera_noise_coverage_audit_20260630/index.html"),
                    artifact_ref("camera noise runtime policy", "artifacts/camera_noise_runtime_policy_20260630/index.html"),
                    artifact_ref("Mission/iPhone full-manifest darkframe candidate audit", "artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701/index.html"),
                    artifact_ref("targeted Mission DNG darkframe scan", "artifacts/darkframe_candidate_audit_targeted_dng_20260630/index.html"),
                    artifact_ref("stills fixture gap plan", "artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/index.html"),
                    artifact_ref("raw-stills capture request", "artifacts/stills_capture_request_noise_fullmanifest_20260701/index.html"),
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
                    repo_ref("production capture requirements", "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md"),
                    artifact_ref("GoPro Mission 1 intake audit", "artifacts/gopro_mission1_intake_audit_capture_requirements_20260630/index.html"),
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
                "The 351-row raw-CFA residual target NPZ has now been built for training: candidate raw-CFA, candidate raw-HF, source raw-HF, rendered-HF luma review, and source-minus-candidate same-color raw-HF residual arrays are hashed and receipted. A duplicate-target audit shows those 351 rows collapse to 117 unique scene/crop raw-domain rows because the raw arrays are identical across -2/0/+2 EV while rendered review residuals vary. The deduplicated raw-supervision NPZ is now materialized with 117 raw rows, zero raw conflicts, preserved rendered EV review metadata, and the same trainer-facing array names for the next teacher pass.",
                "The first deduped-target RCAB teacher smoke receipt now runs on that NPZ with stored candidate-HF features, residual channel attention, multiscale band loss, and Fourier magnitude loss. It is path evidence, not promotion evidence: the bounded 8-row X2D holdout median raw MAE recovery is only about 0.069 percent.",
                "A scaled deduped-target RCAB teacher pass has also run with width 32, depth 6, 700 steps, scene-balanced sampling, 256 px patches, multiscale band loss, and Fourier magnitude loss. It is a rejection receipt: 24-row X2D holdout median raw MAE recovery is only about 0.034 percent, best holdout-probe selection occurs at step 1, and the train split regresses by about -3.45 percent median.",
                "A simple NAF-style teacher pass has also run with SimpleGate/attention blocks, width 32, depth 6, 700 steps, scene-balanced sampling, 256 px patches, multiscale band loss, and Fourier magnitude loss. It is another rejection receipt: 24-row X2D holdout median raw MAE recovery is about -0.059 percent, the best holdout probe is step 1 at only about 0.081 percent, and the train split regresses by about -101.16 percent median.",
                "The first true raw-CFA residual trainer now runs against that NPZ with candidate-only runtime inputs. A stabilized w32/2000-step pass is mildly positive on held-out Z8 at about 0.50 percent median raw-residual MAE recovery, but held-out X2D remains negative at about -0.21 percent.",
                "Follow-up X2D probes show a wider/block17 model barely clears zero at about 0.02 percent median recovery, while stored candidate-HF features, naive one-sigma noise soft-thresholding, larger-patch high-residual-weighted local training, first pooled raw-context features, combined stored-HF/context features, a simple multiscale band-loss objective, an X2D-only train-domain filter, camera-balanced sampling, and 32px context padding alone remain negative. A bounded small U-Net/multiscale raw-domain probe is the first branch to move the hard X2D holdout directionally positive at about 0.10 percent median MAE recovery. Diagnostic holdout-probe checkpoint selection raises that U-Net branch to about 0.13 percent, but it remains below the best 0.16 percent X2D smoke-row result and far below promotion. A same-scene center-crop candidate-signal audit still regresses the hard X2D center rows by about -3.67 percent median MAE, so low-order candidate features are not enough even when neighboring crops from the same scene are available. A per-CFA-plane frequency filter from candidate HF to the raw residual also regresses that split by about -4.29 percent median MAE, so the missing detail is not a simple frequency response of candidate HF. Literature review plus the scaled RCAB and simple NAF-style rejections now point the next pass away from another small/local/RCAB/NAF scale-up and toward a stronger deduplicated-target CFA-aware teacher/objective with camera/noise/PSF conditioning, progressive patch sizing, and spatial + Fourier losses. Adding absolute crop-position/full-crop scalar frame context to that U-Net does not improve X2D and trails the existing Z8 baseline. A bounded full-crop U-Net pass trains on whole target crops and is runtime-safe, but reaches only about 0.06 percent median MAE recovery on the hard X2D scene while regressing the train split. Adding stored candidate-HF plus pooled candidate context to a bounded full-crop U-Net reaches only about 0.02 percent median MAE recovery, adding a global spectral-magnitude objective reaches only about 0.03 percent while regressing train, the larger raw-context full-crop U-Net reaches only about 0.06 percent, the deeper gated pyramid U-Net reaches only about 0.03 percent, a bounded global-context U-Net reaches only about 0.0166 percent, and a candidate-only nearest-neighbor residual patch dictionary regresses the holdout by about -0.80 percent MAE, so current candidate-only local/full-crop/global-context statistics are not enough for simple CNN, frequency-filter, or retrieval transfer.",
                "The next-experiment contract now locks the next premium still-SR pass to the canonical 351-row / 13-scene raw-CFA residual target, forbids REF/source/JPEG content at render time, and records failed local/context/noise/sampling-only probes that should not be repeated as the primary approach.",
            ],
            "open_work": [
                "Follow the next-experiment contract: train against the deduplicated raw target and replace the weak first raw-CFA residual learner with a stronger CFA-aware teacher/objective that clears both Z8 and X2D held-out raw-residual gates; the current blocker is X2D raw-detail recovery strength, not target construction, stored-HF features, naive noise subtraction, local loss-weight tuning, simple pooled-context feature concatenation, combined local-feature concatenation, multiscale band-loss reweighting, camera-domain filtering, camera-balanced sampling, 32px context padding, a small U-Net alone, frame-context scalar planes alone, bounded full-crop sampling alone, bounded full-crop stored-HF/context U-Net training, bounded full-crop spectral-loss U-Net training, larger full-crop raw-context U-Net training, deeper gated pyramid U-Net training, bounded global-context U-Net training, RCAB-only scale-up, simple NAF-style scale-up, or nearest-neighbor residual patch retrieval over current candidate features.",
                "Pass dedicated 50 MP and 100 MP still-SR gates with editor-latitude and worst-row visual evidence.",
                "Use calibrated noise sidecars as conditioning, then add back only noise proven separate from signal.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("premium still-SR contract", "docs/PREMIUM_STILL_SR.md"),
                    repo_ref("production capture requirements", "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md"),
                    artifact_ref("premium still-SR readiness", "artifacts/premium_still_sr_readiness_20260630/index.html"),
                    artifact_ref("premium still-SR experiment scoreboard", "artifacts/premium_still_sr_experiment_scoreboard_20260630/index.html"),
                    artifact_ref("premium still-SR blocker audit", "artifacts/premium_still_sr_blocker_audit_20260630/index.html"),
                    artifact_ref("premium still-SR next-experiment contract", "artifacts/premium_still_sr_next_experiment_contract_20260701/index.html"),
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
                    artifact_ref("premium still-SR deduplicated raw-CFA target", "artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_20260701/index.html"),
                    artifact_ref("premium still-SR deduped RCAB teacher smoke", "artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/index.html"),
                    artifact_ref("premium still-SR scaled RCAB teacher rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/index.html"),
                    artifact_ref("premium still-SR simple NAF teacher rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/index.html"),
                    artifact_ref("premium still-SR raw-CFA residual Z8 holdout model", "artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_w32_2000_lowlr_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D holdout model", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w32_2000_lowlr_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D wider-context model", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w64_5000_block17_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D stored-HF model", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_storedhf_w32_2000_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D noise-threshold model", "artifacts/premium_still_sr_raw_cfa_signal_residual_model_x2dholdout_w32_2000_thr1_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D loss-weight probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_w48_1600_abs6_patch256_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D pooled-context probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_context_w40_1800_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D combined stored-HF/context probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextstoredhf_w40_1800_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D band-loss probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_bandloss_w40_1800_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D-only domain probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_x2donly_w48_2200_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D camera-balanced sampler probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_camera_balanced_w48_2200_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D context-padding probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_contextpad32_w48_1200_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_unet_w32_1200_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D frame-context U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_framectx_unet_w32_1200_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual Z8 frame-context U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_z8holdout_framectx_unet_w32_1200_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D full-crop U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_unet_w16_160_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D full-crop stored-HF/context U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_contextstoredhf_unet_w24_360_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D full-crop spectral U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2d1742_fullcrop_spectral_unet_w24_420_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D full-crop raw-context U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_fullcrop_rawcontext_unet_w32_900_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D pyramid raw-context U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dholdout_pyramid_rawcontext_w24_700_20260630/train_receipt.json"),
                    artifact_ref("premium still-SR patch dictionary probe", "artifacts/premium_still_sr_patch_dictionary_x2dholdout_20260630/patch_dictionary_probe.json"),
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
                "Standalone 8K ProRes A/B review media now compares no-CNN baselines against the approved 4K cleanup plus 8K SR CNN path on Z8, the broad 42-frame Mission 1 sequence, and the stricter Mission 1 GP017497 through GP017508 scene.",
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
                    repo_ref("production capture requirements", "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md"),
                    artifact_ref("4K cleanup visual signoff", "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json"),
                    artifact_ref("8K SR promotion receipt", "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json"),
                    artifact_ref("Z8 continuous 8K no-CNN vs CNN ProRes review", "artifacts/z8_continuous_8k_no_cnn_vs_cnn_20260630/receipt.json"),
                    artifact_ref("Mission 1 broad 8K no-CNN vs CNN ProRes review", "artifacts/mission1_8k_true_no_cnn_vs_cnn_20260630/receipt.json"),
                    artifact_ref("Mission 1 sequential-scene 8K no-CNN vs CNN ProRes review", "artifacts/mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630/receipt.json"),
                    artifact_ref("Mission42 8K dashboard", "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission42_broad_fullframe/index.html"),
                    artifact_ref("PSF xlarge detail budget", "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/bayer_resize_psf_receipt.json"),
                    artifact_ref("Mission 1 native high/low pair inventory", "artifacts/mission1_native_psf_pair_inventory_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF measurement plan", "artifacts/mission1_native_psf_measurement_plan_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF measurement", "artifacts/mission1_native_psf_measurement_20260630/index.html"),
                    artifact_ref("raw-video PSF audit", "artifacts/raw_video_psf_audit_20260630/index.html"),
                    artifact_ref("raw-video PSF gap plan", "artifacts/raw_video_psf_gap_plan_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF corpus audit", "artifacts/mission1_native_psf_corpus_audit_20260630/index.html"),
                    artifact_ref("raw-video PSF controlled capture request", "artifacts/raw_video_psf_capture_request_20260630/index.html"),
                    artifact_ref("raw-video SR/detail candidate scoreboard", "artifacts/raw_video_sr_candidate_scoreboard_20260701/index.html"),
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
            "Fulfill the raw-stills capture request: collect same-ISO Mission 1/CFA iPhone darkframes before promoting nonzero noise addback; current lowest-lift paths are Mission ISO232 RGGB with two matching frames still needed and iPhone ISO1250 RGGB with enough dark-like candidates but unconfirmed no-scene provenance.",
            "Continue premium still-SR from the current raw-CFA residual blocker: held-out Z8 is mildly positive, hard X2D is only barely positive after wider context, and stored-HF/noise-threshold/pooled-context/combined-context/band-loss/X2D-only-domain probes did not solve it.",
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
