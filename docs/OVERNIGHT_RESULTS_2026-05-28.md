# Overnight test results — 2026-05-28 night

Executed the queue in `docs/OVERNIGHT_PLAN_2026-05-28.md`. T1 and T2 both
finished and were gate-tested; both FAILed against their predicted-win
thresholds. T3 was skipped per the plan's stop-condition ("don't bang on
failed approaches without something material to change") — the focal-L1
weighting hypothesis was already lower-EV than T2 and the corpus/loss-domain
axes proved less load-bearing than the architecture-or-coverage gap.

## T1 — BIDO retrain WITH 77-DNG OOD corpus

### What was built

Files modified:
- `tools/cnn/build_dataset_ml2_q3_dec2.py` — added `DNG_DIRS` env override
  so the OOD set can be encoded into its own pair dir without re-touching
  the historical pairs.
- `tools/cnn/build_tiles_dmsr_rgb.py` — added `IN_NPZ`, `OUT_NPZ`,
  `SOURCE_DIRS` env overrides so the dmsr RGB-target NPZ can be built
  against a different bayer NPZ and an additional source-DNG directory.

Files created:
- `/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3_dec2_ood/` — 77 codec/target
  pair files from the OOD corpus. **Z8Z_6693 was excluded** (it is in the
  gate test set, would constitute test-set leakage).
- `/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_combined_with_ood.npz` —
  23,000 bayer tiles from 575 sources (498 existing + 77 OOD-minus-Z8Z_6693).
- `/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_dmsr_with_ood.npz` — same
  23,000 tiles, with sips-rendered RGB targets at 512×512.

Registry entries added:
- `bibo_4x_ane_ml2_q3_dec2_ood_retrain` CNN.
- `codec=ml2_q3_dec2+cnn=bido_4x_ane_ml2_q3_dec2_ood_retrain+demosaic=sips_via_gpr_tools`
  pipeline. ship_class PREVIEW, role `exp-T1-bido-ood-corpus-retrain`.

### Training time

- OOD pair build: 60 s (77 DNGs × roundtrip).
- Bayer-tile NPZ #1: ~140 s assemble. Rebuilt to exclude Z8Z_6693 leak:
  another ~135 s.
- Dmsr RGB NPZ build: ~720 s (~12 min, dominated by 77 new sips renders
  of OOD DNGs and the 23k tile-position image-crop loop).
- Training: 4 epochs × 8 min/epoch = ~32 min wall (under restormer-subagent
  MPS contention; M3 Max MPS sole tenant after ~ep1). Stopped at ep4 to
  free MPS for the gate runs and the morning report.

### Gate verdicts (codec=ml2_q3_dec2+cnn=bido_4x_ane_ml2_q3_dec2_ood_retrain+demosaic=sips_via_gpr_tools)

Run hash `3851bfe0cdaedee4` (T1 ep4 ckpt).

| Image     | LPIPS  | Y-PSNR | MS-SSIM | ΔE     | Verdict | Δ vs wider baseline |
|-----------|--------|--------|---------|--------|---------|---------------------|
| Z8Z_6693  | 0.6135 | 29.49  | 0.8923  | 6.29   | FAIL    | −0.0284 (slightly better) |
| Z8Z_5323  | 0.4790 | 28.23  | 0.8867  | 7.32   | FAIL    | +0.0241 (slightly worse)  |
| Z8Z_0001  | 0.4559 | 21.29  | 0.7226  | 9.69   | FAIL    | +0.1868 (REGRESS)         |
| Z8Z_0067  | 0.1978 | 18.79  | 0.9205  | 9.52   | FAIL    | +0.1009 (REGRESS)         |

Earlier ep3 ckpt gate (run hash `b194a8438cc7fb28`) shows the same
character: worst LPIPS 0.6410, all 4 FAIL.

Wider baseline (run hash `a1bad19d0791cc99`) for reference:
- Z8Z_6693: 0.6419 FAIL, Z8Z_5323: 0.4549 FAIL, Z8Z_0001: 0.2691 FAIL,
  Z8Z_0067: 0.0969 PASS.

### Visual diff observation (Z8Z_6693, the worst image)

The T1 pipeline crop shows desaturated washed-out skin texture with a
grey color cast versus the reference's vivid red-brown skin with crisp
fine pore detail — the model has produced an over-smoothed, posterized
rendering that loses both color saturation and high-frequency texture.
File: `tests/quality_gates/runs/3851bfe0cdaedee4/WORST_Z8Z_6693_visual_diff.png`.

### Decision

**FAIL → DROP.** Worst LPIPS 0.6135 ≫ 0.30 threshold from the plan's
T1 decision rule. The corpus axis did not help; it actively hurt the
non-OOD images. Per the plan: *"the gap may be fundamentally architectural
(the BIDO 325K param ceiling)."*

The training-time validation LPIPS dropped monotonically
(0.1216 init → 0.0606 ep1 → 0.0567 ep2 → 0.0561 ep3 → 0.0543 ep4) while
the gate LPIPS on the same image (Z8Z_0067) ROSE from 0.0969 (wider
baseline) → 0.1978 (T1 ep4). This is exactly the `feedback_no_eval_laundering`
pattern: tile-domain val ≠ gate metric. The training is finding a local
minimum in tile-LPIPS that does not generalize to the gate's
full-image crops.

### Honest assessment vs predicted outcome

Plan predicted: "worst-image LPIPS 0.20-0.30 — moves the needle from 0.45
(current FAIL) toward PREVIEW (0.15 ceiling) but probably doesn't quite
clear."

Actual: worst-image LPIPS 0.6135 — **moved the needle the wrong direction
on 3 of 4 images.** The hypothesis is falsified: adding more "representative
texture" via the same-session OOD DNGs did not close the gap. It widened
it on the diverse-content gate images, which suggests the OOD corpus is
biasing the model away from the broader distribution rather than enriching
it.

## T2 — μ-law / log-domain L1 retrain

### What was built

Files modified:
- `tools/cnn/train.py` — added `--loss-domain {linear,mu_law}` CLI flag and
  the `mu_law()` differentiable tone-map (Hanji 2024). Applied symmetrically
  to pred and target before L1 in `multiscale_l1`; MS-SSIM term unaffected.

Files created:
- `models/BayInBayOut_1x_AAon_w16_ANE_ML2_q3_mu_law.pt` — BIBO_1x retrained
  on `tiles_ml2_q3.npz` with `--loss-domain mu_law`.

Registry entries added:
- `bibo1x_ane_ml2_q3_mu_law` CNN.
- `codec=ml2_q3+cnn=bibo1x_ane_ml2_q3_mu_law+demosaic=sips_via_gpr_tools`
  pipeline. ship_class VIDEO_FREEZE, role `exp-T2-mu-law-loss-domain`.

### Training time

3 epochs completed under heavy MPS contention with the Restormer subagent's
in-flight gate runs (~204s, 223s, 190s per epoch — 3x normal). Halted at
ep3 (gain plateau detected: +1.166 dB → +1.466 dB → +1.607 dB; gain dipped
at ep4 = +1.522 dB, ep5 = +1.588 dB before kill).

The matched-CNN baseline historically peaks at ~+1.7 dB on the same val
src after 75 epochs, so the trained mu_law ckpt is roughly at its ceiling
in terms of tile-PSNR gain. Halting at ep3 saved ~4 hours of wall time
for T1.

### Gate verdict (codec=ml2_q3+cnn=bibo1x_ane_ml2_q3_mu_law+demosaic=sips_via_gpr_tools)

Run hash `57675cdf58b348d0`.

| Image     | LPIPS  | Y-PSNR | MS-SSIM | ΔE     | Verdict |
|-----------|--------|--------|---------|--------|---------|
| Z8Z_6693  | 0.1107 | 34.31  | 0.9584  | 1.59   | FAIL (LPIPS>0.085, MS-SSIM<0.965) |
| Z8Z_5323  | 0.0611 | 37.50  | 0.9783  | 1.15   | PASS    |
| Z8Z_0067  | 0.0396 | 48.90  | 0.9969  | 0.59   | PASS    |
| Z8Z_0001  | 0.0306 | 39.30  | 0.9953  | 1.20   | PASS    |

Current matched-CNN (linear L1, `bibo1x_ane_ml2_q3`) gate baseline for
comparison: worst-image LPIPS = **0.068** (Z8Z_6693).

### Decision

**FAIL → DROP.** Worst LPIPS 0.1107 > current 0.068 (linear L1 baseline).
μ-law did not improve over linear L1 in our regime. The training was
halted early (ep3 of 80) under contention, but the trajectory was already
plateauing at +1.6 dB gain — the same ballpark as the linear-trained
matched CNN — so longer training is unlikely to invert the gate verdict.

### Honest assessment vs predicted outcome

Plan predicted: "0.5-1.5 dB Y-PSNR gain (less dramatic than the literature's
2-9 dB because our problem is less shadow/highlight-skewed than HDR
restoration). Most likely improvement on Z8Z_6693 (the worst image) since
hair grain spans both tone tails."

Actual: Z8Z_6693 worst LPIPS 0.1107 vs linear 0.068 — *worse by 63%.* The
Hanji 2024 finding does not transfer to our regime, presumably because
our codec output has the Cineon-like log curve already applied on encode,
so applying μ-law a second time over-emphasizes the dark end and is a net
loss for our scene distributions. Halting at ep3 means this verdict is on
a less-converged ckpt than the linear baseline (which was 75-epoch trained);
even so the trajectory was already at the linear baseline's terminal-gain
plateau, suggesting the FAIL would persist with more training.

## T3 — skipped

Per plan: "Only run if T1 and T2 both finish with substantial wall budget
remaining." T1 and T2 both FAILed. Per the plan's anti-laundering and
"don't retry failed approaches without changing something material" rules,
the right next move is to document and stop, not to add a 3rd axis
(focal-L1 weighting) on top of two falsified hypotheses.

## Overall: which thread moved the needle?

- **Corpus axis (T1):** moved the needle the wrong direction on the
  embedded-preview gate. Three of four images regressed. The 77-DNG
  same-session OOD set biases the model toward the OOD distribution at
  the expense of generalization. Confirms `BIDO_DISTILLATION_PLAN.md`'s
  Plan-A→Plan-B→Plan-C → Phase-A→Phase-B sequence: corpus and loss tweaks
  on a 325K-param BIDO have hit a ceiling. **The plausible next axis is
  architectural** (larger BIDO, e.g. the w24 BIDO that M5 is still training
  as of ~02:00 ETA, OR a Restormer-class post-RGB filter as the desktop
  decoder), not more corpus or different L1 loss.
- **Loss-domain axis (T2):** flat / mildly negative. μ-law tone-mapping
  the L1 doesn't help when the codec output already lives in a perceptually-
  warped domain (Cineon-like log applied on encode).
- **Focal-weighting axis (T3):** not attempted.

The morning verdict: **none of the three tested research threads cleared
the gate.** The architecture-or-decoder axis (w24 BIDO on M5 in flight;
Restormer-as-decoder subagent ran multiple cranked-quant gate
combinations during the night) remains the open lead.

## Artifacts

- Run hashes: `57675cdf58b348d0` (T2 gate), `b194a8438cc7fb28` (T1 ep3
  gate), `3851bfe0cdaedee4` (T1 ep4 gate, final).
- Training logs: `/tmp/t2_mu_law_train.log`, `/tmp/t1_bido_ood_train.log`.
- Build logs: `/tmp/t1_build_ood_pairs.log`, `/tmp/t1_tile_bayer.log`,
  `/tmp/t1_tile_bayer2.log`, `/tmp/t1_build_dmsr.log`.
- Checkpoints: `models/BayInBayOut_1x_AAon_w16_ANE_ML2_q3_mu_law.pt` (T2),
  `models/BayInDemosaicOut_4x_AAon_w16_ANE_ood_retrain.pt` (T1 ep4).
