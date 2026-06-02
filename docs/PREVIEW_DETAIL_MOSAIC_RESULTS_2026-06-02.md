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

## Receipts

| Candidate | Run | Verdict | Worst image | LPIPS | MS-SSIM | Y-PSNR | dE2000 mean |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| baseline `sl_q3+cnn=none` | `5e7b79b5678fdf62` | PASS | `Z8Z_6693` | 0.1003 | 0.9580 | 33.34 | 1.71 |
| packed planes, low-pass x2 target | `974222c6a6d490e5` | FAIL | `Z8Z_6693` | 0.2566 | 0.9354 | 31.51 | 2.33 |
| mosaic, low-pass x2 target, best | `46bf8050492744e2` | FAIL | `Z8Z_6693` | 0.1760 | 0.9419 | 30.71 | 2.51 |
| mosaic, low-pass x2 target, width 48 | `f7a42b76c1f549ae` | FAIL | `Z8Z_6693` | 0.1809 | 0.9434 | 29.25 | 2.93 |
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

## Next Candidate

Do not continue with the full-REF warm-start recipe as-is. The next useful
candidate should change one of:

- model context: full-image/overlap-aware Y teacher/student rather than
  selecting only on tile-level validation LPIPS;
- target teacher: distill from the passing `ref_L_lowpass_x2` oracle or a
  larger full-gate teacher directly, not just tile-level RGB targets;
- selection metric: checkpoint selection should include the mixed-contrast
  blocker, not only `Z8Z_0067`.

The objective remains a PREVIEW-detail PASS run or an evidenced failure tied
to one of those causes.
