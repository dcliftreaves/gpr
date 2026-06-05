# BIDO_4× distillation plan — closing the OOD / texture gap

Status: IN PROGRESS. Target pipeline:
`codec=ml2_q3_dec2+cnn=bibo_dmsr_ane_ml2_q3_dec2+demosaic=sips_via_gpr_tools`.

## 2026-06-05 Execution Notes

The plan's original `tools/cnn/train_demosaic_sr.py` name was stale. The
active trainer is `tools/cnn/train.py`; it now supports BIDO/RGB `tgt_rgb`
tiles, multiple validation source names, optional checkpoint initialization,
LPIPS-alex loss, and LPIPS validation scoring.

The named starting checkpoints (`BayInDemosaicOut_4x_AAon_w16_ANE*.pt`) were
not present after the 8 TB consolidation. The prior LPIPS fine-tune is still
documented in `docs/FULL_PIPELINE_MATRIX.md` as a failed candidate
(worst LPIPS 0.4516), so Phase A should be treated as already directionally
tested unless the missing checkpoint is recovered.

Dataset reality:

- `/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate.npz` contains
  the large 498-source RGB target set, but only `Z8Z_0067` from the current
  four-image gate.
- `/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_hardtail_t192_s96_fullref.npz`
  contains all four gate blockers with 260 tiles per image and is the right
  small set for blocker-focused smoke tests.

Smoke results:

- BIDO RGB/LPIPS sanity command completed on the hardtail set with
  `Z8Z_6693` held out:
  `/Volumes/OWC_8TB/gpr_work/checkpoints/bido_phase_a_20260605/BayInDemosaicOut_4x_AAon_w16_ANE_lpips_sanity.pt`
- Restormer teacher weights and code were verified outside the repo:
  `/Volumes/OWC_8TB/gpr_work/external/Restormer` and
  `/Volumes/OWC_8TB/gpr_work/external/restormer_real_denoising.pth`
- `tools/cnn/smoke_restormer_teacher.py --tile 128 --device auto` ran on MPS
  and wrote smoke PNGs under
  `/Volumes/OWC_8TB/gpr_work/artifacts/restormer_teacher_smoke_20260605`.
- `tools/cnn/build_restormer_teacher_targets.py` now builds Restormer teacher
  targets as a memmapped `.npy` sidecar plus manifest, avoiding a duplicate
  copy of the full training NPZ. `tools/cnn/train.py` accepts that sidecar via
  `--teacher-npz` and adds `--teacher-weight` / `--task-weight` for BIDO
  distillation.
- A one-tile teacher sidecar smoke ran from `/Volumes/OWC_8TB/gpr_work/tmp`,
  followed by a one-epoch `bido_4x` training smoke with `--teacher-weight 0.25`.
  The smoke verified the sidecar and loss path end to end; temporary artifacts
  were deleted after validation.

Next implementation step: build cached teacher targets from codec-degraded RGB
tiles for the full hardtail set, then run the beta ablation against the four
blocker images before attempting the full 498-source cache.

## 1. Problem statement

`BIDO_4×` (a.k.a. `F_ane_dm_sr` / `bido_4x`) is a 325K-param NAFBlockANE
U-Net that takes 4-channel half-resolution Bayer from the Pi 5
embedded capture path (codec `ml2_q3_dec2`) and emits 3-channel
full-resolution RGB at 4× spatial upscale. Two checkpoints exist:

| Checkpoint | Val set | Gate run (worst LPIPS) | Verdict |
|---|---|---|---|
| `BayInDemosaicOut_4x_AAon_w16_ANE.pt` (single-val) | Z8Z_0067 | 0.634 on Z8Z_6693 | FAIL VIDEO_FREEZE |
| `BayInDemosaicOut_4x_AAon_w16_ANE_wider.pt` (4-img val) | Z8Z_0067, Z8Z_5323, Z8Z_6693, Z8Z_0001 | 0.642 on Z8Z_6693 | FAIL PREVIEW (Z8Z_0067 passes) |

Tile-domain training PSNR was ~43 dB. Per-image gate ranges:

| Image | Y-PSNR (wider) | LPIPS | MS-SSIM | dE2000 | content |
|---|---|---|---|---|---|
| Z8Z_0067 | 40.9 dB | **0.097** | 0.989 | 2.19 | skin / portrait — in domain |
| Z8Z_0001 | 29.3 dB | 0.269 | 0.943 | 6.75 | high-frequency texture |
| Z8Z_5323 | 35.5 dB | 0.455 | 0.944 | 5.85 | high-saturation texture |
| Z8Z_6693 | 33.0 dB | 0.642 | 0.929 | 4.71 | hair / skin OOD |

The Y-PSNR is reasonable (33 dB) but LPIPS is 6–8× the PREVIEW threshold.
This is the classic L1-trained-network failure: **the prediction is
correct on average but lacks perceptually-credible texture**. Color
(dE2000) is also failing, which suggests color-space miscalibration in
the training target distribution, not just texture smoothing.

Two failure modes, in this order of EV:

- **F1 — L1 over-smoothing of skin/hair texture.** Multi-scale L1 has
  no incentive to produce sharp high-frequency detail. The model maps
  high-frequency input to its low-frequency expectation.
- **F2 — OOD generalization.** The training corpus is dominated by
  the barnsky_full_dngs + diverse_dngs sets (498 source DNGs, ~20K
  tiles). Z8Z_6693 (hair) and Z8Z_5323 (saturation) are not well
  represented.

The plan below targets F1 first (highest EV: a perceptual-loss change
moves all four images at once, and the NTIRE 2025 RawRTSR-L precedent
shows it's tractable) and falls back to distillation only if F1's
ceiling is below the gate threshold.

## 2. Recommended approach

**Two-phase plan, F1 first.**

### Phase A: LPIPS-aware fine-tune of current checkpoint (1.5–3 hrs M5)

Add LPIPS (alex backbone) as a loss term during a *fine-tune* of the
existing `_wider.pt` checkpoint, with cosine warmup of the LPIPS
weight. Keep multi-scale L1 as the anchor. Tune the L1↔LPIPS weight
on the 4-image val set, tracking gate LPIPS, not training-tile PSNR.

This is the literature-supported minimum-risk move:
- LPIPS as a loss term is standard in modern image restoration
  (ESRGAN, Real-ESRGAN, RawRTSR-L all use a perceptual term).
- Existing checkpoint already has 33–41 dB Y-PSNR; we are trading a
  small PSNR loss for LPIPS / texture gain.
- Cost: ~90s/epoch × 30 epochs × 1.5 (LPIPS forward is ~50% extra
  compute) ≈ 1.1 hours. With ablation on LPIPS weight ∈ {0.05, 0.1,
  0.2} we burn 3 epochs of compute total.

### Phase B (only if Phase A's worst-image LPIPS ≥ 0.15): Distill from a teacher

If Phase A gets the worst-image LPIPS into PREVIEW range (≤ 0.15) we
stop. If not, run knowledge distillation. **Teacher choice: Restormer**
(the same family as X-Restormer, the RawRTSR-L teacher) running CPU
inference inside our existing pipeline.

Justification for Restormer over alternatives:
- **Restormer** — github.com/swz30/Restormer, Apache-2.0, PyTorch.
  Authors release pretrained weights for image restoration (denoise,
  deblock) which is closer to our codec-degraded input than a pure
  super-res teacher. Runs on MPS with `PYTORCH_ENABLE_MPS_FALLBACK=1`
  for unsupported ops; CPU fallback acceptable since teacher inference
  is one-shot precomputed.
- **X-Restormer** — used by RawRTSR-L but no official weights for our
  task; would need to train the teacher first (multi-day GPU job, out
  of scope on M5 MPS).
- **Real-RawVSR** — confirmed in `docs/RESEARCH_VSR_AND_ANE.md` to not
  run on MPS (deformable conv unsupported, `grid_sample_backward`
  broken). Reject.
- **Real-ESRGAN** — RGB-domain SR teacher. Could be used post-demosaic
  but it works on 8-bit gamma-corrected images, so its output is
  already in the gate's target color space, which is convenient.
  Backup if Restormer turns out painful.

Restormer is the primary; Real-ESRGAN is the fallback we line up if
Restormer's M5-CPU inference per source exceeds 5 min.

## 3. Loss design

### Phase A loss (LPIPS-aware fine-tune)

```
L_total(pred, tgt) = L_msL1(pred, tgt) + λ_lpips · L_lpips(pred, tgt)
```

Where:
- `L_msL1` is the existing 3-scale L1 (weights 1.0, 0.5, 0.25 at 1×,
  ½, ¼) from `train_demosaic_sr.py:multiscale_l1`.
- `L_lpips` uses `lpips` package, `net='alex'`. AlexNet over VGG
  because (a) the gate itself measures LPIPS-alex, so we optimize the
  exact metric; (b) AlexNet is ~6× lighter than VGG on MPS forward —
  important on the 32 GB M5.
- `λ_lpips` schedule: 0 for warmup epochs 0–4 (let L1 stabilize after
  loading the checkpoint), then linearly ramp to target in epochs
  5–10, hold for epochs 10–30.
- LPIPS expects inputs in `[-1, 1]`; convert via `pred * 2 - 1`.
- Inputs to LPIPS must be ≥ 64 px per side. Our prediction tiles are
  512×512, so the network's full receptive field is exercised; no
  need to crop.

`λ_lpips` ablation (3 single-epoch runs followed by 30-epoch winner):

| λ_lpips | Expected outcome | Risk |
|---|---|---|
| 0.05 | Mild perceptual improvement, low risk to PSNR | Insufficient texture |
| 0.10 | Standard restoration setting | Best EV; default |
| 0.20 | Strong texture push | Checkerboard, color drift |

### Phase B loss (distillation, if Phase A fails)

**Soft-target distillation, no feature alignment.** This is what
RawRTSR-L did — teacher's output RGB becomes the student's target,
replacing (or augmenting) the sips-rendered target. Feature
distillation is risky here because the teacher (Restormer) is a
transformer and the student is a CNN U-Net; intermediate features
don't have a natural correspondence at the same spatial scale.

```
L_distill(pred, tgt_sips, tgt_teacher) =
      α · L_msL1(pred, tgt_sips)           # task anchor: never lose the gate target
    + β · L_msL1(pred, tgt_teacher)        # soft target: teacher's RGB
    + γ · L_lpips(pred, tgt_sips)          # carry forward Phase A's gain
```

Starting weights: α=1.0, β=0.5, γ=0.1. Ablate β ∈ {0.25, 0.5, 1.0} on
the 4-img val.

**Important constraint** (called out in the risks section, repeated
here): the teacher must be run on the *codec-degraded* bayer-derived
RGB, not on clean source bayer. We need the teacher to denoise +
super-res the same input distribution the student sees, so the
teacher output represents an *achievable* upper bound the student can
target. Running the teacher on clean source bayer would create an
unreachable target and the student would silently regress.

Concretely: pre-render the teacher target from `codec_output_4ch ->
bicubic_up_to_rgb_tile -> teacher_forward -> RGB teacher tile`. Cache it
as a sidecar tensor aligned to the base NPZ tile order.

## 4. Training data

**Existing data is sufficient for Phase A.** The current NPZ at
`/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate.npz` has 498
source DNGs and ~19920 tiles, with `tgt_rgb` already rendered through
the gate-aligned path (gpr_tools wrap + sips). Phase A uses this as-is.

**Phase B additionally needs teacher RGB targets.** The active path writes
those targets as a sidecar `.npy` tensor aligned to the base NPZ tile order.
This avoids duplicating the full 2.3 GB hardtail NPZ or the larger 498-source
NPZ during iteration.

Step-by-step for the teacher render:
1. For each source DNG, compute the codec-degraded 4-channel bayer
   tile (already in NPZ under `codec_R/G1/G2/B`).
2. Convert the codec tile to RGB and bicubic-upsample it to the target tile
   shape.
3. Run Restormer forward with tiled inference to control memory.
4. Write the resulting RGB at the same tile index as the existing
   `tgt_rgb` tiles, write to NPZ field `tgt_rgb_teacher` (uint8,
   shape `(N, 512, 512, 3)` matching `tgt_rgb`).

Storage: 19920 × 512 × 512 × 3 = ~14.7 GB uint8. Append to the same
NPZ (8 TB drive has headroom). Add `_has_teacher_target` flag in the
dataloader.

**Do not need new training inputs.** The codec-degraded bayer is the
same distribution; we are only adding a richer target.

**Validation set**: keep the same 4 source DNGs in `VAL_SRC_NAMES`
that the wider checkpoint used (Z8Z_0067, Z8Z_5323, Z8Z_6693,
Z8Z_0001). Do not change the val set to make Phase A look better —
the test gate uses these 4 anyway and the run is cheap.

## 5. Compute budget

All M5 MPS, batch=4, ~90 s/epoch as baseline.

| Step | Time | Notes |
|---|---|---|
| Phase A ablation (3 × 5 epochs) | 35 min | Pick best λ_lpips |
| Phase A full train (30 epochs) | 70 min | LPIPS forward = ~+50% per epoch |
| Phase A gate run | 2 min | run_gate.py |
| **Phase A total** | **~1.8 hours** | |
| Phase B teacher precompute (498 DNGs × Restormer CPU) | 2–4 hours | One-shot, cached |
| Phase B teacher → tgt_rgb_teacher tiling | 30 min | |
| Phase B distill ablation (3 × 5 epochs) | 1 hour | LPIPS + two L1 terms |
| Phase B full train (40 epochs) | 2 hours | Slightly heavier loss |
| Phase B gate run | 2 min | |
| **Phase B total** (only if Phase A fails) | **~6 hours** | |
| **Worst-case total** | **~8 hours M5 MPS** | |

Teacher inference time per image (M5 CPU, fp16-on-CPU not available so
fp32): Restormer on 8280×5520 RGB is ~2.5 minutes per image when
tiled at 256×256 with 16-px overlap (estimated from Restormer
benchmarks; verify on first 3 images before committing the full 498).

## 6. Risk assessment

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Phase A LPIPS-fine-tune introduces color drift (γ correction baked into LPIPS-alex's expected input space) | Medium | Medium | Track dE2000 in val every epoch alongside LPIPS. Reject the ablation that pushes dE2000 worse than the starting checkpoint. |
| LPIPS introduces checkerboard / GAN-style artifacts | Medium | High (sends LPIPS up while looking "sharper") | Open the worst-image visual diff PNG (CLAUDE.md ship-claim preflight) every 10 epochs and inspect via Read tool. Reject any run whose visual diff shows regular grid patterns at the PixelShuffle stride. |
| Restormer doesn't run on M5 (transformer ops with unsupported MPS backward, etc.) | Medium | Low (it's a fallback, and we only need *forward* on CPU) | We only need teacher *inference*, no backward pass. Fall back to CPU forward; or swap to Real-ESRGAN. |
| Restormer's input distribution mismatch — it expects RGB images, we have codec-degraded RGB | Low | Medium | Already addressed in §3 by running Restormer on codec→demosaic→bicubic RGB, not on source-clean RGB. |
| Distillation pushes student toward teacher artifacts | Low | Medium | Keep α=1.0 (task anchor weight on sips target) so the student cannot drift past what sips produces on the source DNG. |
| Per-image LPIPS variance hides regression on Z8Z_0067 | Low | High | Per-CLAUDE.md, worst-image governs; track per-image LPIPS, not mean. Z8Z_0067 currently passes — explicitly check it does not regress. |
| Y-PSNR drops below VIDEO_FREEZE floor (32 dB) for a previously-clearing image | Medium | High | Same: track per-image Y-PSNR every val. Roll back λ_lpips if Z8Z_0067 PSNR drops below 38 dB (current 40.9 dB → 2 dB safety margin). |
| `lpips` package not installed | Trivial | Trivial | `pip install lpips` (Apache-2.0). Already standard. |
| OOM on M5 32 GB at batch=4 with LPIPS forward | Low | Low | Reduce to batch=2 if needed. ~+30% wall clock, plan accommodates. |

The biggest watch-item is the **checkerboard artifact failure mode**
of perceptual losses. The CLAUDE.md ship-claim preflight (open worst
visual diff PNG via Read, write 6+ word concrete-noun observation)
catches this and is mandatory.

## 7. Step-by-step execution checklist

Execute in order. Each step has a gate. Stop and reassess if any gate fails.

### Phase A — LPIPS fine-tune

1. **Setup**
   - `pip install lpips` (if not present)
   - Confirm `models/BayInDemosaicOut_4x_AAon_w16_ANE_wider.pt` is the
     starting checkpoint (the wider 4-image-val one).
   - Confirm `/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate.npz`
     exists and loads.

2. **Add LPIPS loss to training script.** Edit
   `tools/cnn/train_demosaic_sr.py`:
   - Import `lpips` and instantiate `lpips.LPIPS(net='alex').to(DEVICE)`
     (freeze its params: `for p in lpips_net.parameters(): p.requires_grad_(False)`).
   - Add `--lpips-weight`, `--lpips-warmup-epochs`, `--init-ckpt` CLI args.
   - Modify `multiscale_l1` call site to:
     `loss = multiscale_l1(pred, tgt_rgb) + lpips_weight_curr * lpips_net(pred*2-1, tgt_rgb*2-1).mean()`
   - Load initial weights from `--init-ckpt` if provided.

3. **Sanity check (gate 1)** — single tile, single epoch:
   ```
   python3 tools/cnn/train_demosaic_sr.py --epochs 1 --subsample 200 \
       --lpips-weight 0.1 --init-ckpt models/BayInDemosaicOut_4x_AAon_w16_ANE_wider.pt \
       --ckpt-name BayInDemosaicOut_4x_AAon_w16_ANE_lpips_sanity.pt
   ```
   Gate: loss not NaN, val PSNR within 1 dB of starting checkpoint.

4. **λ_lpips ablation (gate 2)** — 3 × 5-epoch sweep:
   - λ = 0.05, 0.10, 0.20.
   - Track per-epoch val PSNR + LPIPS-alex on the 4-image val set.
     (LPIPS-alex on val tiles is cheap; just compute alongside PSNR
     in `evaluate()`.)
   - Pick the λ with best 4-image-mean LPIPS, provided Z8Z_0067
     LPIPS does not regress (Z8Z_0067 is the in-domain image; it should
     stay near 0.097).
   - Gate: at least one λ achieves val-tile LPIPS-alex below the
     starting checkpoint's val-tile LPIPS-alex.

5. **Full Phase A train (30 epochs).**
   ```
   python3 tools/cnn/train_demosaic_sr.py --epochs 30 \
       --lpips-weight <chosen> --lpips-warmup-epochs 5 \
       --init-ckpt models/BayInDemosaicOut_4x_AAon_w16_ANE_wider.pt \
       --ckpt-name BayInDemosaicOut_4x_AAon_w16_ANE_lpips.pt
   ```

6. **Register pipeline (gate 3).** Add registry entry for
   `cnn=bibo_dmsr_ane_ml2_q3_dec2_lpips` pointing at the new
   checkpoint. `trained_against_codec: ml2_q3_dec2`. Pipeline name:
   `codec=ml2_q3_dec2+cnn=bibo_dmsr_ane_ml2_q3_dec2_lpips+demosaic=sips_via_gpr_tools`.

7. **Gate (BLOCKING ship-claim preflight).**
   ```
   python3 tests/quality_gates/run_gate.py \
       codec=ml2_q3_dec2+cnn=bibo_dmsr_ane_ml2_q3_dec2_lpips+demosaic=sips_via_gpr_tools
   ```
   Open `tests/quality_gates/runs/<hash>/WORST_*_visual_diff.png` via
   Read tool. Write a 6+ word observation with a concrete noun about
   the worst image.

8. **Decision point.**
   - If worst-image LPIPS ≤ 0.15 → **STOP, PREVIEW gate passes**. Log
     via `run_gate.py ... --claim`.
   - If worst-image LPIPS ≤ 0.08 → **STOP, VIDEO_FREEZE gate passes**.
   - Otherwise → proceed to Phase B.

### Phase B — Restormer distillation (only if Phase A worst LPIPS > 0.15)

9. **Acquire Restormer.**
   - `git clone https://github.com/swz30/Restormer.git external/Restormer`
     (outside the gpr tree, do not commit it).
   - Download `real_denoising.pth` pretrained weight (Apache-2.0
     mirror in their releases).

10. **Smoke test (gate 4).** Run Restormer on one tile from one image
    to verify M5 MPS forward works. If MPS fails:
    - Try `PYTORCH_ENABLE_MPS_FALLBACK=1`.
    - If still failing, run on CPU. Confirm one full-res image
      forward completes in < 10 min.

11. **Teacher sidecar cache.** Run
    `tools/cnn/build_restormer_teacher_targets.py` against the hardtail NPZ:
    - Iterate over the base NPZ tile order.
    - Convert each codec-degraded tile to RGB, bicubic-upsample to the target
      tile shape, and run Restormer with tiled inference.
    - Write `/Volumes/OWC_8TB/gpr_work/cnn/teacher_restormer_hardtail_t192_s96_fullref.npy`
      plus its manifest and generated-mask sidecars.
    - Gate: visual inspection of sampled teacher tiles should show stronger
      detail placement without smoothing away target structure or adding
      ringing.

12. **Load teacher sidecar in training.** Pass
    `--teacher-npz /Volumes/OWC_8TB/gpr_work/cnn/teacher_restormer_hardtail_t192_s96_fullref.npy`
    so the dataloader returns both `tgt_rgb` and the sidecar teacher target.

13. **Add distillation loss to training script.**
    - Add `--teacher-weight` (β) and `--task-weight` (α) CLI flags.
    - Dataloader returns both `tgt_rgb` and `tgt_rgb_teacher`.
    - Loss is α·msL1(pred, tgt_sips) + β·msL1(pred, tgt_teacher)
      + γ·LPIPS(pred, tgt_sips).

14. **β ablation (gate 5)** — 3 × 5-epoch sweep, β ∈ {0.25, 0.5, 1.0},
    α=1.0, γ = Phase A's chosen λ_lpips.

15. **Full Phase B train (40 epochs).** Initialize from Phase A's
    checkpoint, not the original wider. Checkpoint name:
    `BayInDemosaicOut_4x_AAon_w16_ANE_distill.pt`.

16. **Register and gate.** New pipeline:
    `codec=ml2_q3_dec2+cnn=bibo_dmsr_ane_ml2_q3_dec2_distill+demosaic=sips_via_gpr_tools`.
    Run gate. Apply ship-claim preflight (open worst-image visual diff
    via Read tool, write 6+ word observation).

17. **Decision point.**
    - If worst-image LPIPS ≤ 0.15 → PREVIEW passes, log claim.
    - If worst-image LPIPS ≤ 0.08 → VIDEO_FREEZE passes, log claim.
    - Otherwise → write a failure-summary doc, do not push, brainstorm.

## 8. Expected outcome

### Phase A (LPIPS fine-tune) — best estimate

Calibration points:
- LPIPS-loss-trained Real-ESRGAN-like models typically drop LPIPS by
  ~40–60% relative to L1-only baselines, at a cost of 0.5–1.5 dB PSNR.
- Current wider worst-image LPIPS = 0.642. Expected after Phase A:
  **0.25–0.40** on Z8Z_6693. This is unlikely to pass PREVIEW
  (≤0.15) on the worst image — Phase B will probably be needed.
- Y-PSNR expected drop: 33.0 → 32.0 dB on Z8Z_6693; 40.9 → 39.5 dB
  on Z8Z_0067. Z8Z_0067 should still PASS PREVIEW.
- MS-SSIM and dE2000 should improve modestly (perceptual loss
  encourages structural alignment).

### Phase B (distillation) — best estimate

The RawRTSR-L precedent is +0.84 dB PSNR-Y over the L1-only baseline
in the same param class (260K vs our 325K). The AccelIR-style cranked
quant work (`docs/quant_calibration_findings.md`) showed +4.40 dB
on LH1 / +4.22 dB on HL1 sub-bands via CNN-aware calibration — that
result is for a different lever (per-subband quant) but it's our
strongest data point that distillation-adjacent techniques deliver
big single-digit dB gains in this codec.

Conservative expectation after Phase B:

| Image | Y-PSNR (now) | Y-PSNR (predicted) | LPIPS (now) | LPIPS (predicted) | Verdict |
|---|---|---|---|---|---|
| Z8Z_0067 | 40.9 | 40.0–41.0 | 0.097 | 0.05–0.08 | PASS VIDEO_FREEZE |
| Z8Z_0001 | 29.3 | 30.0–32.0 | 0.269 | 0.12–0.18 | PASS PREVIEW marginal |
| Z8Z_5323 | 35.5 | 35.0–37.0 | 0.455 | 0.18–0.25 | FAIL PREVIEW likely |
| Z8Z_6693 | 33.0 | 33.5–35.0 | 0.642 | 0.20–0.30 | FAIL PREVIEW likely |

This suggests **Phase B brings 2 of 4 images into PREVIEW range but
not 4 of 4**. If that prediction holds, the next-after-Phase-B move is
not more loss engineering; it's enlarging the training corpus with
representative texture (hair, saturated regions) — which is a data
acquisition project, not a CNN architecture project.

**If after Phase B the worst image is still LPIPS > 0.30**, the
diagnosis is that the 325K-param architecture *cannot* represent the
texture distribution. That's an architecture-budget decision (move to
w24 or w32 — already in `model.py` VARIANTS) that lives in a separate
plan.

## 9. Out of scope for this plan

- Architecture changes (width sweep w24/w32, large-kernel variants).
  These are tracked separately.
- Pipeline-level changes (codec quant, demosaic stage).
- Changes to `gates.json` or `test_set.json`.
- Training data acquisition (additional source DNGs of hair / saturation).
- Anything BIBO_1x or BIBO_2x. Plan is scoped to BIDO_4× only.

## 10. Dependencies to acquire before execution

1. **`lpips` Python package** (BSD-2-Clause). `pip install lpips`.
   First-run downloads ~6 MB AlexNet checkpoint.
2. **Restormer repo + weights** (Apache-2.0).
   - Code: `https://github.com/swz30/Restormer`
   - Pretrained weight for real-denoising (closest task): the
     `real_denoising.pth` file from the project's release page.
   - Approx 100 MB. Store outside the gpr tree
     (e.g. `/Volumes/OWC_8TB/gpr_work/external/Restormer`).
3. **(Phase B only, optional fallback) Real-ESRGAN** (BSD-3-Clause).
   - Code: `https://github.com/xinntao/Real-ESRGAN`
   - Weight: `RealESRGAN_x4plus.pth` (~64 MB).
   - Only needed if Restormer doesn't run on M5 — verify in gate 4 first.

Existing dependencies (already in repo): PyTorch with MPS, numpy,
tifffile, PIL, gpr_tools binary at
`build-local/source/app/gpr_tools/gpr_tools`.

## 11. Sanity reminders (from CLAUDE.md)

Before declaring any phase complete:
1. Run `tests/quality_gates/run_gate.py <full-pipeline-name>`.
2. Read the worst-image visual diff PNG via the Read tool.
3. Only after both (1) and (2) can ship language be used. Use
   `--claim` with a 6+ word inspection sentence (concrete noun).
4. Worst-image LPIPS governs, not mean LPIPS.
5. Do not edit `gates.json` or `test_set.json` to make a phase pass.
6. Pipeline names are full triples (`codec=...+cnn=...+demosaic=...`).
