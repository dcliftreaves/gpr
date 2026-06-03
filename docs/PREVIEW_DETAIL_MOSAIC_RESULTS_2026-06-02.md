# PREVIEW Detail Mosaic Candidate Results - 2026-06-02

## Scope

This pass tested whether the PREVIEW detail blocker is caused by losing Bayer
phase adjacency before the Y/detail model. Chroma is kept on the solved Lab
Chroma SIPS guardrail path. The only changed variable is the Y model input and
target:

- `mosaic_lx2_best`: decoded half-res Bayer as one spatial mosaic channel,
  trained against REF Lab L low-passed by factor 2.
- `mosaic_lx2_last`: same run, final early-stop checkpoint.
- `mosaic_fullref`: warm-started from `mosaic_lx2_best`, then fine-tuned
  against full REF Y texture with LPIPS plus high-pass/gradient loss.
- `mosaic_w48_lx2`: width-48 capacity version of the mosaic low-pass x2
  candidate.
- `mosaic_w48_lx2_last`: final checkpoint from the width-48 run, gated to
  test whether smooth-image validation selected the wrong epoch.
- `mosaic_w48_wavelet_lhf2`: width-48 blocker-selected checkpoint fine-tuned
  against a REF Lab-L target with the finest two `sym4` wavelet detail levels
  removed. This tests whether non-learnable REF luminance HF/noise was
  contaminating the learned detail target.
- `lab_l_residual_v1_wavelet_hf1_g120`: the best Lab-L residual v1 path with a
  shippable bounded Lab-L wavelet-HF synthesis hook. This tests whether the
  REF-HF oracle insight can be approximated by amplifying the candidate's own
  finest wavelet detail band instead of importing exact REF noise.
- `y_w32_t192_center512`: width-32 decoded-Bayer phase-plane Y candidates
  fine-tuned on larger 192-codec-pixel / 768-output tiles with loss and
  checkpoint selection on the 512px center region. This tests whether the
  previous failure was caused by too little tile context or edge-biased tile
  training.
- `mosaic_coord_w32_lx2`: width-32 decoded-Bayer mosaic Y candidates with
  absolute y/x coordinate channels. This tests whether the local mosaic model
  was missing full-image placement cues rather than Bayer phase adjacency.

## Receipts

| Candidate | Run | Verdict | Worst image | LPIPS | MS-SSIM | Y-PSNR | dE2000 mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| baseline `sl_q3+cnn=none` | `5e7b79b5678fdf62` | PASS | `Z8Z_6693` | 0.1003 | 0.9580 | 33.34 | 1.71 |
| packed planes, low-pass x2 target | `974222c6a6d490e5` | FAIL | `Z8Z_6693` | 0.2566 | 0.9354 | 31.51 | 2.33 |
| packed planes, low-pass x2 target, t192 center-valid aggressive | `abd069326b906a72` | FAIL | `Z8Z_6693` | 0.3988 | 0.9183 | 28.91 | 2.97 |
| packed planes, low-pass x2 target, t192 center-valid conservative | `9a30acc832b00c94` | FAIL | `Z8Z_6693` | 0.3255 | 0.9289 | 29.75 | 2.74 |
| mosaic, low-pass x2 target, best | `46bf8050492744e2` | FAIL | `Z8Z_6693` | 0.1760 | 0.9419 | 30.71 | 2.51 |
| mosaic, low-pass x2 target, Z8Z_6693-selected | `ebcfdf3a6ff3ba23` | FAIL | `Z8Z_6693` | 0.1638 | 0.9442 | 31.06 | 2.45 |
| mosaic + coordinates, low-pass x2 target, blocker-selected | `6315162afa5ed4d2` | FAIL | `Z8Z_6693` | 0.2010 | 0.9431 | 32.33 | 2.18 |
| mosaic + coordinates, low-pass x2 target, last | `f20c7651c73ea654` | FAIL | `Z8Z_6693` | 0.2437 | 0.9365 | 28.72 | 3.06 |
| mosaic + full-gate RGB residual context v1 | `ac606b54716374b2` | FAIL | `Z8Z_6693` | 0.1775 | 0.9404 | 30.64 | 2.52 |
| mosaic + full-gate Lab-L residual v1 | `5d3cf75bf1b1f44b` | FAIL | `Z8Z_6693` | 0.1532 | 0.9423 | 33.21 | 2.01 |
| mosaic + Lab-L residual v1 + wavelet HF synthesis | `b3b767e5d4d2f717` | FAIL | `Z8Z_6693` | 0.1511 | 0.9422 | 33.19 | 2.02 |
| mosaic + dilated Lab-L residual v2 | `9b1d4c8e7320de40` | FAIL | `Z8Z_6693` | 0.1910 | 0.9436 | 33.54 | 1.97 |
| mosaic, low-pass x2 target, width 48 | `f7a42b76c1f549ae` | FAIL | `Z8Z_6693` | 0.1809 | 0.9434 | 29.25 | 2.93 |
| mosaic, low-pass x2 target, width 48, blocker-selected | `e5107f994eb2dd0b` | FAIL | `Z8Z_6693` | 0.1637 | 0.9458 | 31.56 | 2.34 |
| mosaic, wavelet-denoised L target, width 48, blocker-selected | `6d7ed7f5b62f7732` | FAIL | `Z8Z_6693` | 0.3235 | 0.9415 | 30.66 | 2.54 |
| mosaic, full REF target, best | `4ae4d3cfb39632ab` | FAIL | `Z8Z_6693` | 0.1995 | 0.9392 | 29.21 | 2.94 |
| mosaic, low-pass x2 target, last | `077761916aa85fb6` | FAIL | `Z8Z_6693` | 0.2275 | 0.9383 | 26.91 | 3.76 |
| mosaic, low-pass x2 target, width 48 last | `f5b7383a00663858` | FAIL | `Z8Z_6693` | 0.2614 | 0.9300 | 24.71 | 4.71 |

The mosaic low-pass candidate is the best learned detail candidate so far:
it turns `Z8Z_5323` from failing to passing and improves the hard-tail
`Z8Z_6693` LPIPS from 0.2566 to 0.1760. It still misses the PREVIEW gate:
LPIPS must be <= 0.15 and MS-SSIM must be >= 0.95.

## Root-Cause Narrowing

The blocker is not solved chroma. The `mosaic_lx2_best` run keeps dE2000 mean
under 3.0 on all gate images, while the final checkpoint and full-REF
fine-tune show that pushing texture harder can regress dE.

The blocker is also not codec irrecoverability by itself. The existing
recoverability oracle shows `ref_L_lowpass_x2` passes the hard-tail image
(`Z8Z_6693` LPIPS about 0.0983, MS-SSIM about 0.9704), but the learned model
trained to approximate that recoverable target only reaches LPIPS 0.1760 and
MS-SSIM 0.9419 on the same image.

The current failure is therefore narrowed to the learned local Y/detail model:
the model can benefit from preserving Bayer phase adjacency, but it still
over-smooths or misplaces fine texture on the mixed-contrast crop. The full-REF
fine-tune did not fix that; it worsened the hard-tail LPIPS and introduced a
near-threshold dE regression. A width-48 version improved tile validation
LPIPS (0.0280 vs 0.0349 for width-32) but did not improve the full-image gate.
The width-48 final checkpoint regressed all four gate images, so the issue is
not just selecting a later training epoch. Simple capacity scaling and longer
training of this local tiled architecture are not sufficient.

The full-gate residual refiners narrow the failure further:

- Selecting the primary mosaic-Y checkpoint by `Z8Z_6693` tile LPIPS instead
  of `Z8Z_0067` validation LPIPS improves the blocker from LPIPS 0.1760 to
  0.1638 and MS-SSIM from 0.9419 to 0.9442, with dE still safe. That confirms
  selection pressure matters, but it is not enough to pass the full-image gate
  and it does not beat the simpler Lab-L residual near-miss.
- Combining the wider width-48 mosaic Y model with blocker-aware selection on
  `Z8Z_5323` and `Z8Z_6693` reaches essentially the same full-image blocker
  result as width-32 blocker selection: `Z8Z_6693` LPIPS 0.1637 and MS-SSIM
  0.9458. It keeps dE safe and passes `Z8Z_5323`, but does not improve over
  the Lab-L residual near-miss. That rules out "capacity plus tile-level hard
  image selection" as the missing production step for this local mosaic-Y
  architecture.
- Larger-context center-valid phase-plane training also fails as a standalone
  fix. The 192-codec-pixel / 768-output dataset was built on the external
  drive as
  `/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_hardtail_t192_s96_lx2.npz`
  (`sha256=650a41efb1c8fa60ae407da3de38cb6139ab44a8a7030db4818dde230c8d995f`).
  The aggressive checkpoint improved blocker tile selection enough to save at
  epoch 2, but full-gate `Z8Z_6693` regressed to LPIPS 0.3988 / MS-SSIM
  0.9183 and also broke `Z8Z_0001` dE/Y. A conservative lr=2e-5 variant saved
  at epoch 1 with better blocker tile LPIPS (0.1377), but full-gate
  `Z8Z_6693` still regressed to LPIPS 0.3255 / MS-SSIM 0.9289 and all four
  images failed at least one metric. This rules out "larger local tile context
  plus center-valid loss/selection" for the current phase-plane Y architecture.
- Adding absolute coordinate channels to the mosaic Y model improved the
  blocker tile-selection objective but did not transfer to the full-image gate.
  The dataset was the existing external
  `/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_hardtail_s128_lx2_mosaic.npz`
  (`sha256=d5e97d539859405f70481c43f64b8464026b2a3c2764d7a0abb89ae570c4e253`).
  The blocker-selected checkpoint saved at epoch 69 with tile `select_lpips`
  `0.0831`, but full-gate run `6315162afa5ed4d2` still failed `Z8Z_6693`
  (`LPIPS=0.2010`, `MS-SSIM=0.9431`) while passing the other three gate images.
  The final epoch-80 checkpoint regressed further in run `f20c7651c73ea654`
  (`Z8Z_6693 LPIPS=0.2437`, `MS-SSIM=0.9365`, `dE=3.06`). This rules out
  "absolute position cues plus the same local mosaic-Y architecture" as the
  missing production step.
- The wavelet target-cleanup run improved the tile-training selection metric
  (`Z8Z_5323,Z8Z_6693` LPIPS 0.0656 vs 0.0695 for the previous width-48
  blocker-selected checkpoint), but failed the full-image gate badly:
  `Z8Z_5323` LPIPS 0.1864 and `Z8Z_6693` LPIPS 0.3235 / MS-SSIM 0.9415. The
  failure is not a color regression (`Z8Z_6693` dE2000 mean 2.54). This rules
  out "remove REF HF/noise from the target, then keep the same local Y model"
  as a sufficient production step.
- The RGB residual context refiner did not improve the hard-tail blocker and
  regressed the color guardrail on `Z8Z_0001` (`dE2000_mean=3.40`).
- The Lab-L residual v1 is the best residual result so far. It improves
  `Z8Z_6693` LPIPS from 0.1760 to 0.1532 and keeps dE safe, but MS-SSIM stays
  nearly flat at 0.9423, below the 0.95 PREVIEW threshold.
- The bounded wavelet-HF synthesis hook on top of Lab-L residual v1 moves the
  blocker closer on LPIPS (`0.1532` to `0.1511`) and keeps color safe
  (`dE2000_mean=2.02`), but MS-SSIM remains flat (`0.9422`). This rejects
  "add more of the candidate's own finest HF energy" as a complete production
  fix. The remaining error is structural/mid-frequency placement, not just
  scalar HF amplitude.
- The wider/dilated Lab-L residual v2 improves Y-PSNR and slightly improves
  MS-SSIM to 0.9436, but perceptual artifacts push LPIPS backward to 0.1910.

That makes the residual-postprocess path an evidenced near-miss rather than a
solution. It can restore some local luma energy, but it does not place
full-image structure well enough to pass MS-SSIM before LPIPS regresses. The
remaining blocker is now specifically the detail-placement target/model path,
not chroma, not lack of full-gate residual training data, and not a simple
increase in residual context or strength. It is also not only checkpoint
selection on the wrong smooth validation image: Z8Z_6693-selected primary-Y
training helps but still misses both LPIPS and MS-SSIM thresholds.

The REF-HF transfer diagnostic (`ref_hf_noise_transfer_l2`) supports the
original noise hypothesis as an analysis tool, but not as a complete learned
pipeline fix. On 100% crops, the previous width-48 blocker-selected run drops
from worst LPIPS 0.4992 to 0.1686 when comparing only low-frequency Lab-L
signal, and to 0.1424 when exact REF HF is added back as an oracle. The new
wavelet-trained candidate shows the same split: original crop worst LPIPS
0.6445, signal-only 0.1342, exact REF-HF oracle 0.1268. MS-SSIM remains below
threshold in those rows, so the unresolved issue is now more precise: learn or
synthesize the right mid/high-frequency structure placement separately from
REF noise matching.

A shippable self-HF crop probe (`wavelet_hf_synthesis_current`) confirmed the
same direction before the full gate. On 100% crops, the best variants reduce
worst-crop LPIPS by roughly 0.02-0.04 on the current near-miss candidates, but
MS-SSIM is flat or slightly worse. The full gate then reproduced that pattern:
LPIPS moved to within 0.0012 of threshold, while MS-SSIM stayed 0.0078 below
threshold.

## Next Candidate

Do not continue with the full-REF warm-start recipe as-is. The next useful
candidate should change one of:

- model context: full-image/overlap-aware Y teacher/student rather than
  selecting only on tile-level validation LPIPS;
- target teacher: distill from the passing `ref_L_lowpass_x2` oracle or a
  larger full-gate teacher directly, not just tile-level RGB targets;
- target/noise split: train the signal path against denoised or oracle
  low-frequency/full-gate targets, but treat visual-equivalent HF/noise as a
  separate synthesis/injection model rather than asking the local Y model to
  memorize exact REF HF;
- selection metric: checkpoint selection should include the mixed-contrast
  blocker, not only `Z8Z_0067`; this has now been tested and should be paired
  with a stronger target/model rather than repeated alone.
- architecture: move detail placement into the primary Y/upres model or a
  stronger teacher/student with explicit full-image context; bounded residual
  postprocessing has now failed both RGB and Lab-L variants.

The objective remains a PREVIEW-detail PASS run or an evidenced failure tied
to one of those causes.
