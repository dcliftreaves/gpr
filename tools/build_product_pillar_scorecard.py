#!/usr/bin/env python3
"""Build the four-pillar GPR product scorecard.

This is a summary and audit layer over committed docs plus large external
receipts. It deliberately keeps the overall product "production ready" false
while real Mission 1 camera closure, Mission/iPhone noise sidecars, and premium
still-SR promotion are open. Native PSF/blur work is tracked as optional
replacement research and must not block the approved current 4K/8K raw-video
reconstruction workflow.
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
                "The raw-stills noise sidecar readiness receipt consolidates the coverage audit, runtime policy, darkframe candidate audit, fixture gap plan, and capture request into one product-facing verdict: X2D/Z8 are enabled; Mission/iPhone are blocked.",
                "The full-manifest Mission/iPhone darkframe candidate audit parses 1,997 of 2,000 bounded manifest rows, finds 59 dark-like frames and four iPhone same-ISO candidate stacks, but keeps production sidecar readiness false because candidate-discovery scene frames still need confirmed no-scene-signal provenance.",
                "A fresh full scan of the compact Mission 1 DNG root parses 49/49 files and finds five dark-like RGGB frames, but the best same-ISO group remains the two-frame ISO232 candidate stack, so Mission 1 still needs two matching no-scene-signal frames or a fresh four-frame stack.",
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
                    artifact_ref("raw-stills noise sidecar readiness", "artifacts/raw_stills_noise_sidecar_readiness_20260701/index.html"),
                    artifact_ref("Mission/iPhone full-manifest darkframe candidate audit", "artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701/index.html"),
                    artifact_ref("Mission 1 current DNG darkframe candidate audit", "artifacts/darkframe_candidate_audit_mission1_dng_full_20260701/index.html"),
                    artifact_ref("targeted Mission DNG darkframe scan", "artifacts/darkframe_candidate_audit_targeted_dng_20260630/index.html"),
                    artifact_ref("stills fixture gap plan", "artifacts/stills_fixture_gap_plan_noise_fullmanifest_20260701/index.html"),
                    artifact_ref("raw-stills capture request", "artifacts/stills_capture_request_strict_provenance_20260701/index.html"),
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
                    artifact_ref("GoPro Mission 1 intake audit", "artifacts/gopro_mission1_intake_audit_capture_requirements_20260701/index.html"),
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
                "A raw-target SNR audit now compares those 117 rows with calibrated camera-noise sidecars. All rows have sidecar coverage, but the target is mixed by camera: X2D is mostly signal-dominated, with 59/81 rows above the noise floor and about 5.34x median target RMSE/noise sigma, while Z8 is mostly noise-floor/mixed, with 28/36 rows at the noise floor and about 0.48x median target RMSE/noise sigma.",
                "A raw-target distribution audit now quantifies the hard X2D scene split: 2024_April_X2D_1742 has 3.45x the X2D train-median target residual energy and 6 of 9 holdout rows above the train p90, even though it is not above the training maximum.",
                "The first deduped-target RCAB teacher smoke receipt now runs on that NPZ with stored candidate-HF features, residual channel attention, multiscale band loss, and Fourier magnitude loss. It is path evidence, not promotion evidence: the bounded 8-row X2D holdout median raw MAE recovery is only about 0.069 percent.",
                "A scaled deduped-target RCAB teacher pass has also run with width 32, depth 6, 700 steps, scene-balanced sampling, 256 px patches, multiscale band loss, and Fourier magnitude loss. It is a rejection receipt: 24-row X2D holdout median raw MAE recovery is only about 0.034 percent, best holdout-probe selection occurs at step 1, and the train split regresses by about -3.45 percent median.",
                "A simple NAF-style teacher pass has also run with SimpleGate/attention blocks, width 32, depth 6, 700 steps, scene-balanced sampling, 256 px patches, multiscale band loss, and Fourier magnitude loss. It is another rejection receipt: 24-row X2D holdout median raw MAE recovery is about -0.059 percent, the best holdout probe is step 1 at only about 0.081 percent, and the train split regresses by about -101.16 percent median.",
                "A corrected-distribution X2D-scene NAF probe trains only on X2D rows while holding out 2024_April_X2D_1742. It fixes the worst train/holdout camera mismatch, but still reaches only about 0.107 percent median raw MAE recovery on the 9-row X2D scene holdout, keeps holdout RMSE recovery negative, and selects step 1 as best.",
                "A matched X2D-scene U-Net SNR-filter batch tests the SNR audit as a hard row-filtering control. It shows binary row removal is not the fix: signal-only training reaches about 0.112 percent median MAE recovery, signal-or-mixed reaches about 0.119 percent, and unfiltered X2D-only reaches about 0.149 percent on the same 9-row X2D scene holdout.",
                "A matched X2D-scene U-Net SNR-weighting batch then keeps all rows and tests simple row-weighting controls. Broad signal-emphasis and continuous-SNR weighting trail the unfiltered branch at about 0.135 and 0.129 percent, while noise-floor-only downweighting is only slightly positive at about 0.153 percent and keeps RMSE negative.",
                "Two obvious follow-up controls also fail: adding stored candidate-HF to the noise-floor-weighted U-Net regresses the same X2D scene to about 0.110 percent median MAE recovery, and a broader pyramid U-Net without stored HF reaches only about 0.131 percent.",
                "Target-energy weighting controls also fail: emphasizing high-energy rows reaches only about 0.118 percent median MAE recovery, while inverse-energy weighting reaches about 0.133 percent, both below the current noise-floor-only U-Net branch.",
                "Fourier/band-loss objective controls also fail: adding explicit multiscale residual-band plus FFT-magnitude loss regresses the same X2D scene to about -0.386 percent median MAE recovery, and a lighter version still regresses to about -0.139 percent.",
                "Candidate-HF target-scale controls are runtime-safe but also fail: full-strength candidate-HF output scaling reaches only about 0.052 percent median MAE recovery, and half-strength scaling regresses to about -0.137 percent.",
                "Source-HF target-representation controls also fail strongly: predicting source raw HF directly then converting back to residual space regresses the same X2D scene to about -241.62 percent median MAE recovery without stored candidate HF and about -862.69 percent with stored candidate HF.",
                "A matched frame-context/noise-floor control also fails: adding crop position, camera one-hot, full-crop raw statistics, and candidate-HF statistics to the X2D-scene U-Net reaches only about 0.001 percent median MAE recovery and negative RMSE recovery.",
                "The latest matched global-context and fixed non-box PSF/CFA controls are now first-class rejection evidence: global context trails the current noise-floor U-Net branch at about 0.149 percent median MAE recovery, and a known asymmetric [0.52, 0.23, 0.17, 0.08] PSF/CFA NAF diagnostic reaches about 0.130 percent. Those results keep the blocker on real row-level PSF/camera variation plus a stronger teacher/objective rather than another global scalar or fixed-kernel repeat.",
                "Two first PSF-conditioned X2D scene-holdout controls now exist. A local noise-floor U-Net with near-box PSF scalar planes reaches about 0.106 percent median exact raw MAE recovery versus the non-PSF 0.153 percent baseline, while a full-crop raw-context PSF U-Net reaches about 0.064 percent. The PSF metadata gap audit then confirms 0 of 117 deduplicated target rows have row-level PSF metadata. The row-level PSF sidecar contract now gives the trainer an executable --psf-sidecar bridge, but the current artifact still has 0 of 117 camera-specific PSF assignments, 117 of 117 global fallback assignments, all rows near-box, and only one unique kernel. The current blocker is not missing PSF plumbing; it is missing per-row/per-camera PSF variation or a stronger teacher/objective.",
                "The first true raw-CFA residual trainer now runs against that NPZ with candidate-only runtime inputs. A stabilized w32/2000-step pass is mildly positive on held-out Z8 at about 0.50 percent median raw-residual MAE recovery, but held-out X2D remains negative at about -0.21 percent.",
                "Follow-up X2D probes show a wider/block17 model barely clears zero at about 0.02 percent median recovery, while stored candidate-HF features, naive one-sigma noise soft-thresholding, larger-patch high-residual-weighted local training, first pooled raw-context features, combined stored-HF/context features, a simple multiscale band-loss objective, an X2D-only train-domain filter, camera-balanced sampling, and 32px context padding alone remain negative. A bounded small U-Net/multiscale raw-domain probe is the first branch to move the hard X2D holdout directionally positive at about 0.10 percent median MAE recovery. Diagnostic holdout-probe checkpoint selection raises that U-Net branch to about 0.13 percent, but it remains below the best 0.16 percent X2D smoke-row result and far below promotion. same-scene candidate-signal and frequency-filter probes regress: a same-scene center-crop candidate-signal audit regresses the hard X2D center rows by about -3.67 percent median MAE, and a per-CFA-plane frequency filter from candidate HF to the raw residual regresses that split by about -4.29 percent median MAE. Literature review plus the raw-target SNR split and the scaled RCAB/simple NAF-style rejections now point the next pass away from another small/local/RCAB/NAF scale-up and toward a materially different deduplicated-target CFA-aware teacher/objective with camera conditioning, PSF conditioning, progressive patch sizing, and learned multiscale texture priors. The corrected X2D-scene NAF run confirms distribution matters but still trails the weak U-Net branch; the matched SNR-filtered U-Net batch shows hard row removal also trails unfiltered X2D-only training, the SNR-weighted batch shows simple row weighting is only a tiny noise-floor-only gain, and the stored-HF/pyramid/target-energy/Fourier-band/candidate-scale/source-HF/frame-context controls show candidate-HF, simple capacity, scalar target-energy row weighting, scalar spatial/Fourier loss shaping, candidate-side scalar output scaling, full-HF target replacement, and frame-stat concatenation are not enough. Adding absolute crop-position/full-crop scalar frame context to that U-Net does not improve X2D and trails the existing Z8 baseline. A bounded full-crop U-Net pass trains on whole target crops and is runtime-safe, but reaches only about 0.06 percent median MAE recovery on the hard X2D scene while regressing the train split. Adding stored candidate-HF plus pooled candidate context to a bounded full-crop U-Net reaches only about 0.02 percent median MAE recovery, adding a global spectral-magnitude objective reaches only about 0.03 percent while regressing train, the larger raw-context full-crop U-Net reaches only about 0.06 percent, the deeper gated pyramid U-Net reaches only about 0.03 percent, a bounded global-context U-Net reaches only about 0.0166 percent, and a candidate-only nearest-neighbor residual patch dictionary regresses the holdout by about -0.80 percent MAE, so current candidate-only local/full-crop/global-context/masked-context statistics are not enough for simple CNN, frequency-filter, or retrieval transfer.",
                "The current next-experiment contract now records the 12k window-attention rejection and the clean-signal U-Net rejection, then points the next primary model pass toward self-supervised clean-source RAW SR pairs from real 50 MP / 100 MP sources, realistic degradation/noise modeling, and candidate-only distillation only after the clean-source teacher beats same-color interpolation on held-out X2D/Z8 images.",
                "The first real-fixture clean-source RAW SR pair smoke now runs on Mission 1, Z8, and X2D DNG fixtures and records the nearest same-color 2x interpolation baseline: 6 tiles, 4 CFA planes, 48x48 inputs, 96x96 targets, median MAE about 19.24, median RMSE about 49.47, and median PSNR about 50.43 dB.",
                "The first dedicated clean-source pair model smoke now trains and evaluates through tools/cnn/train_premium_still_sr_clean_source_pairs.py, but it is correctly rejected: with x2d_100mp_dng held out, median MAE gain is about -0.087 percent and median RMSE gain is about -0.049 percent versus nearest same-color 2x.",
                "The broader routed clean-source RAW SR pair set now covers 75 images and 1200 tiles across Mission 1, Z8, and X2D. It is the current premium still-SR pair baseline, with nearest same-color 2x median MAE about 12.40 and RMSE about 23.10 overall.",
                "Two routed clean-source teacher probes are now rejection receipts, not promotion evidence: the 1500-step X2D holdout run improves train MAE by about 14.54 percent but regresses held-out X2D by about -5.07 percent, and the matched Z8 holdout run improves train MAE by about 12.86 percent but regresses held-out Z8 MAE by about -4.82 percent.",
                "The raw-CFA trainer now exposes model_arch=window_attention_teacher: a shifted-window attention, overlap-convolution, downsampled-context teacher path. A 2-step real-target smoke receipt proves it runs on the canonical 117-row deduplicated target with PSF and CFA conditioning and no REF/source/JPEG runtime inputs, but the bounded 2-row X2D holdout median raw MAE recovery is only about 0.142 percent, so this is path evidence rather than promotion evidence.",
                "The raw-CFA trainer now also has explicit overlapped-tile final evaluation and seam diagnostics. The first real-target overlap smoke uses the window-attention path on the canonical deduplicated target with 64 px eval overlap and 8 px seam bands; it records about 0.448 percent bounded X2D holdout median MAE recovery, overlap-vs-plain median MAE around 1.65e-5, and seam-band delta around 7.04e-5. This is validation machinery and seam-risk evidence, not a model promotion.",
                "The refreshed premium still-SR experiment scoreboard now scans 82 rendered-HF and raw-CFA residual training receipts. It records 82 runtime-safe rows, zero promotable rows, and a best runtime-safe holdout of 4.03 percent MAE / 3.75 percent RMSE recovery, far below the 15 percent / 15 percent promotion threshold.",
            ],
            "open_work": [
                "Follow the current next-experiment contract: build self-supervised clean-source RAW SR pairs from real 50 MP / 100 MP Bayer sources, prove a clean-source teacher beats same-color interpolation on held-out X2D/Z8 images, then distill into a candidate-only still path and run the still/editor-latitude gate. The current blocker is a target/objective and runtime-signal gap, not stored-HF features, naive noise subtraction, local loss-weight tuning, simple pooled-context feature concatenation, combined local-feature concatenation, multiscale band-loss reweighting, camera-domain filtering, camera-balanced sampling, 32px context padding, scalar target-energy row weighting, scalar Fourier/band loss shaping, candidate-side scalar output scaling, direct source-HF target replacement, frame-context scalar concatenation, a small U-Net alone, bounded full-crop sampling alone, bounded full-crop stored-HF/context U-Net training, bounded full-crop spectral-loss U-Net training, larger full-crop raw-context U-Net training, deeper gated pyramid U-Net training, bounded global-context U-Net training, RCAB-only scale-up, simple NAF-style scale-up, clean-signal residual gating plus the same small U-Net family, or nearest-neighbor residual patch retrieval over current candidate features.",
                "Pass dedicated 50 MP and 100 MP still-SR gates with editor-latitude and worst-row visual evidence.",
                "Use calibrated noise sidecars as conditioning, then add back only noise proven separate from signal.",
            ],
            "evidence": annotate_refs(
                [
                    repo_ref("premium still-SR contract", "docs/PREMIUM_STILL_SR.md"),
                    repo_ref("production capture requirements", "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md"),
                    artifact_ref("premium still-SR readiness", "artifacts/premium_still_sr_readiness_20260630/index.html"),
                    artifact_ref("premium still-SR experiment scoreboard", "artifacts/premium_still_sr_experiment_scoreboard_20260701/index.html"),
                    artifact_ref("premium still-SR blocker audit", "artifacts/premium_still_sr_blocker_audit_20260630/index.html"),
                    artifact_ref("premium still-SR current next-experiment contract", "artifacts/premium_still_sr_self_supervised_raw_sr_contract_20260702/index.html"),
                    artifact_ref("premium still-SR clean-source RAW SR pair audit smoke", "artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_smoke_20260702/index.html"),
                    artifact_ref("premium still-SR clean-source pair model smoke", "artifacts/premium_still_sr_clean_source_pair_model_smoke_20260702/index.html"),
                    artifact_ref("premium still-SR routed clean-source pair audit", "artifacts/premium_still_sr_self_supervised_raw_sr_pair_audit_routed_t16_20260702/index.html"),
                    artifact_ref("premium still-SR routed X2D holdout rejection", "artifacts/premium_still_sr_clean_source_pair_model_routed_x2dholdout_w48_1500_20260702/index.html"),
                    artifact_ref("premium still-SR routed Z8 holdout rejection", "artifacts/premium_still_sr_clean_source_pair_model_routed_z8holdout_w48_1500_20260702/index.html"),
                    artifact_ref("premium still-SR superseded transformer-teacher contract", "artifacts/premium_still_sr_next_experiment_contract_transformer_teacher_20260701/index.html"),
                    artifact_ref("premium still-SR window-attention teacher smoke", "artifacts/premium_still_sr_raw_cfa_residual_model_dedup_window_attention_teacher_smoke_20260701/index.html"),
                    artifact_ref("premium still-SR window-attention overlap/seam eval smoke", "artifacts/premium_still_sr_window_attention_overlap_eval_smoke_20260701/index.html"),
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
                    artifact_ref("premium still-SR raw-CFA residual targets", "artifacts/premium_still_sr_raw_cfa_residual_targets_cfa_20260701/index.html"),
                    artifact_ref("premium still-SR deduplicated raw-CFA target", "artifacts/premium_still_sr_raw_cfa_residual_targets_dedup_cfa_20260701/index.html"),
                    artifact_ref("premium still-SR raw-target SNR audit", "artifacts/premium_still_sr_raw_target_snr_audit_20260701/index.html"),
                    artifact_ref("premium still-SR target distribution audit", "artifacts/premium_still_sr_target_distribution_audit_20260701/index.html"),
                    artifact_ref("premium still-SR deduped RCAB teacher smoke", "artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_smoke_20260701/index.html"),
                    artifact_ref("premium still-SR scaled RCAB teacher rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_dedup_rcab_teacher_w32_700_20260701/index.html"),
                    artifact_ref("premium still-SR simple NAF teacher rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_dedup_naf_teacher_w32_700_20260701/index.html"),
                    artifact_ref("premium still-SR corrected-distribution X2D NAF rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_naf_teacher_w32_700_20260701/index.html"),
                    artifact_ref("premium still-SR signal-only X2D U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrfiltered_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR signal-or-mixed X2D U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrmixed_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR unfiltered X2D U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_x2dall_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR signal-emphasis weighted X2D U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_signal_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR continuous-SNR weighted X2D U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_continuous_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR noise-floor weighted X2D U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_snrweighted_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR stored-HF noise-floor X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_storedhf_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR pyramid noise-floor X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_noisefloor_pyramid_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR high-energy weighted X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyweighted_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR inverse-energy weighted X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_energyinverse_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR Fourier/band-loss X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fourierband_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR light Fourier/band-loss X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_lightfourierband_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR candidate-HF scaled X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR half candidate-HF scaled X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_candhfscale0p5_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR source-HF X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR source-HF stored-HF X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_sourcehf_storedhf_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR frame-context X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_framectx_noisefloor_unet_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR matched global-context X2D U-Net rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_globalctx_matched_w32_1200_20260701/index.html"),
                    artifact_ref("premium still-SR fixed non-box PSF/CFA NAF rejection", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_nonboxpsf_cfa_naf_w32_800_20260701/index.html"),
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
                    artifact_ref("premium still-SR raw-CFA residual X2D PSF noise-floor U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_psf_noisefloor_unet_w32_1200_20260701/train_receipt.json"),
                    artifact_ref("premium still-SR raw-CFA residual X2D full-crop raw-context PSF U-Net probe", "artifacts/premium_still_sr_raw_cfa_residual_model_x2dsceneholdout_fullcrop_rawcontext_psf_unet_w32_900_20260701/train_receipt.json"),
                    artifact_ref("premium still-SR PSF metadata gap audit", "artifacts/premium_still_sr_psf_metadata_gap_20260701/index.html"),
                    artifact_ref("premium still-SR PSF sidecar contract", "artifacts/premium_still_sr_psf_sidecar_contract_20260701/index.html"),
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
            "id": "raw_video_reconstruction",
            "title": "4. RAW video reconstruction improvement",
            "readiness_percent": 100,
            "status": "approved_offline_reconstruction_psf_research_optional",
            "production_ready": True,
            "lock_ledger_paths": [
                "Mission 1 4K cleanup",
                "Mission 1 8K SR",
            ],
            "open_production_gates": [],
            "locked_artifacts": [
                "approved Mission native12 4K cleanup offline/review baseline",
                "approved candidate-aware 8K SR offline/reconstruction baseline",
                "continuous 8K no-CNN versus CNN ProRes review media",
                "8K .gvid, editable raw, and ProRes review receipts",
            ],
            "claim": "4K cleanup and 8K SR are approved offline/post baselines with packaging, editable raw, ProRes, continuous review, objective review, and manual signoff evidence. Formal native PSF/blur-aware replacement work is optional research, not a release blocker.",
            "done_evidence": [
                "Mission native12 4K cleanup is approved for offline/review scope.",
                "Candidate-aware 8K SR passes broad Mission42 and Z8 full-frame gates with .gvid, editable raw, and ProRes receipts.",
                "Standalone 8K ProRes A/B review media now compares no-CNN baselines against the approved 4K cleanup plus 8K SR CNN path on Z8, the broad 42-frame Mission 1 sequence, and the stricter Mission 1 GP017497 through GP017508 scene.",
                "The approved current continuation has registry-driven .gvid decode-to-SR, editable DNG/GPR, 2K ProRes, Mission metadata-transplant receipts, 42-frame full-sequence .gvid packaging, continuous 8K ProRes review, objective visual-review, and manual visual signoff receipts.",
                "The release boundary is now explicit: the approved 4K/8K reconstruction path is frozen unless its own gate, receipt, hash, CI check, or manual review fails.",
            ],
            "open_work": [
                "No release blocker remains for the approved offline/post 4K cleanup and 8K SR workflow; keep it frozen and guarded unless its own committed gate, receipt, hash, CI guard, or manual review fails.",
                "Optional research: follow the raw-video PSF gap plan only when controlled same-scene Mission 1 high/low pairs with source hashes, decoded Bayer hashes, fixed settings, and negative controls are available.",
                "Optional replacement promotion: train PSF-conditioned SR only if it can beat the locked Mission42 and Z8 all24 baselines with clean worst rows.",
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
                    artifact_ref("42-frame decode-to-SR receipt", "artifacts/mission1_native120_gvid_to_8k_sr_coord_detail_psf_focus_step0075_42f_20260701/receipt.json"),
                    artifact_ref("42-frame .gvid and ProRes packaging receipt", "artifacts/mission1_native120_gvid_to_8k_sr_coord_detail_psf_focus_step0075_sequence_packaging_42f_20260701/receipt.json"),
                    artifact_ref("objective visual review", "artifacts/mission1_8k_sr_coord_detail_psf_focus_step0075_visual_review_20260701/visual_review.json"),
                    artifact_ref("review candidate audit", "artifacts/mission1_8k_sr_coord_detail_psf_focus_step0075_review_candidate_audit_20260701/review_candidate_audit.json"),
                ],
                external_root,
            ),
            "research_evidence": annotate_refs(
                [
                    artifact_ref("PSF xlarge detail budget", "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/bayer_resize_psf_receipt.json"),
                    artifact_ref("Mission 1 native high/low pair inventory", "artifacts/mission1_native_psf_pair_inventory_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF measurement plan", "artifacts/mission1_native_psf_measurement_plan_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF measurement", "artifacts/mission1_native_psf_measurement_20260630/index.html"),
                    artifact_ref("raw-video PSF audit", "artifacts/raw_video_psf_audit_20260630/index.html"),
                    artifact_ref("raw-video PSF gap plan", "artifacts/raw_video_psf_gap_plan_20260630/index.html"),
                    artifact_ref("Mission 1 native PSF corpus audit", "artifacts/mission1_native_psf_corpus_audit_20260630/index.html"),
                    artifact_ref("raw-video PSF controlled capture request", "artifacts/raw_video_psf_capture_request_20260630/index.html"),
                    artifact_ref("raw-video SR/detail candidate scoreboard", "artifacts/raw_video_sr_candidate_scoreboard_psf_detail_20260701/index.html"),
                    artifact_ref("raw-video PSF detail metric audit", "artifacts/raw_video_psf_detail_metric_audit_rerun_20260701/index.html"),
                    artifact_ref("raw-video PSF gradient/detail blocker audit", "artifacts/raw_video_psf_gradient_detail_blocker_audit_20260701/index.html"),
                    artifact_ref("focused PSF gradient continuation", "artifacts/current_goal_sr_psf_gradient_focus_20260701/psf_gradient_focus_from_detail_s400_fw6_gw12_s300_decision.json"),
                    artifact_ref("coord/detail PSF-focus registry-review decision", "artifacts/current_goal_sr_coord_detail_context_20260701/coord_detail_from_psf_focus_s150_step000075_decision.json"),
                    artifact_ref("focused PSF SR scoreboard", "artifacts/raw_video_sr_candidate_scoreboard_psf_gradient_focus_20260701/index.html"),
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
                "The denominator is the shippable production suite: raw stills, raw video MVP, "
                "premium still/SR, and approved raw-video reconstruction. PSF-aware replacement "
                "work is optional research unless it later beats and replaces the approved baseline."
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
            "Continue premium still-SR from the current raw-CFA residual blocker: held-out Z8 is mildly positive, hard X2D is only barely positive after wider context, and stored-HF/noise-threshold/pooled-context/combined-context/band-loss/X2D-only-domain/target-energy weighting/Fourier-band/candidate-scale probes did not solve it.",
            "Do not reopen approved raw-video SR for the current release. PSF-conditioned video work is optional replacement research and starts only after controlled native high/low pairs exist or a locked 4K/8K gate fails.",
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
        research_refs = "\n".join(render_link(ref) for ref in pillar.get("research_evidence", []))
        research_block = (
            f"<h3>Research Parking Lot</h3><ul class=\"refs research\">{research_refs}</ul>"
            if research_refs
            else ""
        )
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
  {research_block}
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
