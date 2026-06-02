# Chroma corrector CNN — spec

## Problem statement

The PREVIEW gate has a hard `dE_p95 <= 3.0` rule. With codec=ml2_q3_dec2 + the current VA-Y + Gaussian-unsharp SOTA, three of four gate images fail on dE_p95 alone (LPIPS, MS-SSIM, Y-PSNR all pass on most). Trace numbers from `tests/quality_gates/runs/dashboard/chroma_trace/trace_summary.json`:

| image     | cnn=none a_p95 | cnn=none b_p95 | sota a_p95 | sota b_p95 |
|-----------|----------------|----------------|------------|------------|
| Z8Z_0001  | 4.90           | **8.50**       | 4.99       | 8.20       |
| Z8Z_0067  | 1.32           | 1.26           | 1.37       | 1.29       |
| Z8Z_5323  | 1.52           | 2.82           | 1.58       | 2.83       |
| Z8Z_6693  | 1.66           | 2.62           | 1.73       | 2.66       |

The b-channel error on Z8Z_0001 (foliage) is the dominant contributor. The diff visualization shows the error is **regional / saturated-region**, not uniform desaturation — global chroma boost (the C-family experiments in `chroma_boost.py`) cannot help because the median chroma magnitude already matches REF.

The Y channel is excellent (LPIPS pass). This spec proposes a small learned **chroma-only corrector** that touches a, b only.

## 1. Architecture

**Family**: F_ane (NAFUNet-ANE) — same backbone family as VA-Y. Reuse `model.py:NAFUNetANE` so the ANE export path is unchanged.

**New variant** `F_ane_chroma_corrector_w12`, added to `tools/cnn/model.py`:

```python
"F_ane_chroma_corrector_w12": dict(
    width=12, enc=[1, 1, 1], dec=[1, 1, 1], mid=1,
    sr=False, sr4x=True, in_c=7, out_c=2),
```

- `in_c=7`: 4ch half-res codec Bayer (R, G1, G2, B as in train_ycbcr_channel) + 3ch — the **half-res Y prediction from the existing VA-Y CNN** (downsampled 4x → matches the 4-plane spatial resolution) plus 2ch of "naive a, b from sips full-res demosaic, downsampled 4x". All inputs at half-res Bayer resolution (codec native), and the `sr4x=True` head pixel-shuffles up to full-res 2 channels.
- `out_c=2`: corrected (a, b) at full-res. NOT a residual on the chroma input — direct prediction (we saw earlier that residual scaling caused over-smoothing on OOD; clean output is safer).
- `width=12`: gives **~110–130 K params** (between Cb/Cr w=8 at 84K and Y w=16 at 324K). Halfway between the existing chroma and Y nets, since this network has to do more than per-channel chroma did but the output dimensionality is still 2 (vs 3 for full RGB).

**Inputs in detail** (all delivered as a (B, 7, H, W) half-res tensor):
1. `codec_R, codec_G1, codec_G2, codec_B` — uint16 → float32 / 16383.
2. `Y_half` — VA-Y CNN's full-res Y prediction, area-pool 4x down (single channel, [0, 1]). This anchors the corrector to the same luma the post-assembly will use; the network learns chroma *consistent with that luma*.
3. `a_naive_half, b_naive_half` — the cnn=none full-res Lab a, b channels (computed from sips full-res RGB), area-pool 4x down (two channels, in their native Lab units, but normalized: divide by 128 to roughly fit [-1, 1]). This gives the corrector the current-SOTA chroma as a starting hint.

**Open question (resolve before training)**: should we also feed the half-res RGB from gpr_tools→sips on the codec's half-res Bayer as 3 extra input channels? Adds 3 channels (in_c=10), ~25K more params. My recommendation: **no for v1**, ship v1, then ablate if dE_p95 isn't reaching the gate.

**Output assembly** at inference time, replacing the current LAB-swap step in run_gate's `cnn=ycbcr_decomp_*` and SOTA paths:
1. Run VA-Y CNN → full-res Y (Lab L equivalent via BT.709→Lab).
2. Run chroma corrector → full-res (a, b).
3. Combine `(L, a, b)` → RGB via `skimage.color.lab2rgb`, clip to [0, 255].

This is a drop-in replacement for `sota_assemble_lab()` in `codec_anchored_proper.py:250`.

## 2. Loss function

The loss has three terms.

**(a) Lab L2 with chroma weighting (primary)**

For pixel `i` with target `(L*, a*, b*)` and predicted `(a_hat, b_hat)`:

```
C_ref_i = sqrt(a*_i^2 + b*_i^2)               # reference chroma magnitude
w_i     = 1 + 4 * (C_ref_i / 60).clip(0, 1)   # 1.0 in neutrals, up to 5.0 in saturated
loss_L2 = mean( w_i * ((a_hat_i - a*_i)^2 + (b_hat_i - b*_i)^2) )
```

The 60-LAB-unit anchor is roughly where saturated foliage / red apparel sits; reaches the cap at deep saturation.

**(b) Hue (angle) penalty in saturated regions (regional)**

Hue error is what makes saturated b-channel drift catastrophic visually. Compute the differentiable cosine distance of (a, b) vectors:

```
dot     = a_hat * a* + b_hat * b*
mag_hat = sqrt(a_hat^2 + b_hat^2 + eps)
mag_ref = sqrt(a*^2     + b*^2     + eps)
cos_h   = dot / (mag_hat * mag_ref)
sat_mask = (C_ref / 30).clip(0, 1)            # 0 at neutral, 1 at C* >= 30
loss_h  = mean( sat_mask * (1 - cos_h) )
```

**(c) CIEDE2000 anchor (final term — exact gate metric, low weight)**

The exact gate metric is CIEDE2000. We don't differentiate it directly (the formula has multiple branches), but we add an L1 surrogate computed on the *Lab values* themselves with the saturation weighting above. This makes the loss well-behaved while still pushing toward the gate metric. Optionally, every K epochs we evaluate (non-differentiable) CIEDE2000 on the val set for monitoring; the differentiable proxy we train against is

```
loss_dE_proxy = mean( w_i * sqrt( (a_hat - a*)^2 + (b_hat - b*)^2 + eps ) )
```

This is dimensionally a Lab chroma-distance — when L is fixed (we don't train it), `sqrt(dC*^2)` is the dominant term in CIEDE2000.

**Combined**

```
loss = loss_L2 + 0.3 * loss_h + 0.5 * loss_dE_proxy
```

Weights chosen so that at init (random) `loss_L2` and `loss_dE_proxy` are within ~2x of each other; `loss_h` is bounded in [0, 1] and gets 0.3 to keep it from dominating when saturated tiles are over-sampled.

**Open question**: should `loss_h` operate on a discriminator/window-pooled hue average (less noisy on a per-pixel basis) instead of pixelwise? My recommendation: **pixelwise for v1**, average-pool within a window only if v1 over-fits hue noise.

## 3. Training data

Reuse what already exists. No new tile builds required:

- **Source pairs**: `/Volumes/OWC_8TB/gpr_work/cnn/pairs_ml2_q3_dec2/` (400 barnsky pairs, 200 unique source DNGs) + `/Volumes/OWC_8TB/gpr_work/cnn/pairs_ml2_q3_dec2_diverse/` (596 pairs across 298 NEFs from 10 dates Jan–Oct 2025).
- **NPZ used for VA Y/Cb/Cr**: `/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate.npz` — has codec_R/G1/G2/B (uint16, 128×128) + tgt_rgb (uint8, 512×512) + src/src_lookup_names. **Exactly what we need.**
- **Gate test exclusion**: already excluded by the `tiles_ml2_q3_dec2_dmsr_gate.npz` build path (see `build_tiles_dmsr_gate_aligned.py`); val uses `Z8Z_0067` only by convention. The trainer keeps `VAL_SRC_NAMES=Z8Z_0067` so the four gate images (Z8Z_0001, Z8Z_5323, Z8Z_6693, Z8Z_0067) are all out of train. Z8Z_0067 stays as val anchor; the other three stay completely held out.

**Additional inputs the dataset doesn't yet have** (needed at train time):
- `Y_half` — VA-Y CNN's prediction at half-res Bayer resolution. Two options:
  - **Online**: load VA-Y ckpt, run forward, then area-pool down. Adds ~5× the per-tile compute (Y forward inside dataloader). Painful.
  - **Offline precompute (recommended)**: one-time pass over all tiles to populate a new NPZ field `y_half` (N, 128, 128) uint8. Build script: `tools/cnn/build_y_half_field.py` — loads `tiles_ml2_q3_dec2_dmsr_gate.npz`, runs `F_ane_no_sr_w16_y` on each codec tile, takes the central 128×128 of the 512×512 output area-pooled 4x. Roughly 30 minutes on M5 for 19,920 tiles. Write to a sidecar `tiles_ml2_q3_dec2_dmsr_gate_chroma.npz` so we don't bloat the original.
- `a_naive_half, b_naive_half` — precomputed codec-only chroma hints. The implemented v1 sidecar (`tools/cnn/build_chroma_corrector_sidecar.py`) reconstructs a cheap RGB hint from the four codec planes, converts to Lab, and stores half-res Lab a/b. This deliberately avoids target leakage. A future exact sidecar can replace this with the slower gpr_tools→sips render path if v1 misses the gate.

The chroma corrector's *target* is `tgt_rgb` → Lab → (a, b) — computed in the dataloader, no precompute needed.

## 4. Tile sampling strategy

The chroma error is concentrated in saturated tiles, but most tiles are low-chroma. We need to **bias training toward saturated tiles** without losing the neutrals (which keep the corrector calibrated on whites/grays).

**Saturation score per tile** (computed once during NPZ-build, cached):

```python
# tgt_rgb is (H=512, W=512, 3) uint8
lab = skimage.color.rgb2lab(tgt_rgb / 255.0)
a, b = lab[..., 1], lab[..., 2]
C = np.sqrt(a**2 + b**2)
sat_score = float(np.percentile(C, 95))     # 95th-pctile chroma per tile
```

Store as `tile_sat_score` (N,) float32 in the sidecar NPZ.

**Sampling**: in each epoch, draw two passes:

1. **Uniform pass** — all N tiles in standard random order. Keeps the corrector calibrated on the full distribution.
2. **Saturated pass** — re-iterate the top 30% of tiles by `tile_sat_score` (typically `sat_score > 25` LAB units), but with weights proportional to `tile_sat_score / median(tile_sat_score)` so the most saturated tiles see ~3× the typical exposure.

Concretely, in `__init__` of the dataset we build an index list `expanded_indices` that is `list(range(N)) + [i for i in top30 with weighted repetition]` and shuffle each epoch. Net effect: saturated tiles see roughly 2-3× more gradient steps than neutral ones.

**Open question**: should saturated-pass operate on `(a, b)` *direction* rather than chroma magnitude, so that we cover hue space evenly (red foliage + green foliage + blue sky)? My recommendation: **magnitude for v1**, but log per-tile hue histograms so we can decide.

## 5. Eval procedure

After each epoch, evaluate on the **val subset** (Z8Z_0067 tiles in train NPZ). Track:
- val_l1(a, b) — primary save criterion.
- val_dE_proxy — `mean( sqrt((a_hat-a*)^2 + (b_hat-b*)^2) )`.
- val_h_loss — pixelwise hue cosine distance on saturated mask.

**Then after best ckpt is saved**, every 10 epochs run a **gate-mimic eval** on the four gate images (not as training signal — purely a probe):

1. Encode each `Z8Z_0001/0067/5323/6693.dng` via `coeff_io_tool` → half-res Bayer (exactly what `codec_anchored_proper.py` does).
2. Run VA-Y CNN → full-res Y.
3. Run chroma corrector → full-res (a, b).
4. Combine via `lab2rgb` → full-res RGB.
5. Compute against REF PNG (REF_RUN=732da314adc90553):
   - **dE_p95** (CIEDE2000) — the gate metric. Pass = <= 3.0 per image.
   - **MS-SSIM, LPIPS-alex, Y-PSNR** — all gate metrics.
6. Compare each metric to current SOTA: load `runs/dashboard/codec_anchored_proper/metrics.json` and the SOTA pipeline.

A run is a **win** iff: all 4 images pass dE_p95 AND no metric on any image is more than 1% worse than the current SOTA.

This piggybacks on the eval helpers in `codec_anchored_proper.py:212-247` — share the helpers via a `tools/cnn/eval_chroma_corrector.py` module.

## 6. Concrete commands

### 6a. Pre-stage on Mac (build sidecar NPZ)

```
# Builds y_half / a_naive_half / b_naive_half / tile_sat_score into a sidecar.
KMP_DUPLICATE_LIB_OK=TRUE \
  python3 /Users/dcliftreaves/Documents/Github/gpr/tools/cnn/build_chroma_corrector_sidecar.py \
    --in-npz /Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate.npz \
    --y-ckpt /Users/dcliftreaves/gpr_data/F_ane_no_sr_w16_y.pt \
    --out-npz /Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_chroma.npz
```

Then rsync both NPZs to M5:

```
rsync -avP /Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate.npz \
           gpr-m5:/Users/dcliftreaves/gpr_data/
rsync -avP /Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_chroma.npz \
           gpr-m5:/Users/dcliftreaves/gpr_data/
```

### 6b. Kick off training on M5

```
ssh gpr-m5 'cd ~/gpr && nohup env \
  KMP_DUPLICATE_LIB_OK=TRUE \
  SUPERRES_NPZ=/Users/dcliftreaves/gpr_data/tiles_ml2_q3_dec2_dmsr_gate.npz \
  CHROMA_SIDECAR_NPZ=/Users/dcliftreaves/gpr_data/tiles_ml2_q3_dec2_dmsr_gate_chroma.npz \
  CKPT_DIR=/Users/dcliftreaves/gpr_data \
  VAL_SRC_NAMES=Z8Z_0067 \
  python3 tools/cnn/train_chroma_corrector.py \
    --variant F_ane_chroma_corrector_w12 \
    --epochs 100 \
    --batch 8 \
    --lr 5e-4 \
    --patience 30 \
    --ckpt-name F_ane_chroma_corrector_w12.pt \
    --sat-oversample-factor 3 \
    --sat-pct 30 \
    --loss-h-weight 0.3 \
    --loss-dE-weight 0.5 \
  > /tmp/train_chroma_corrector.log 2>&1 &'
```

Then monitor:

```
ssh gpr-m5 'tail -f /tmp/train_chroma_corrector.log'
```

### 6c. Pull artifact + register

After training completes:

```
scp gpr-m5:/Users/dcliftreaves/gpr_data/F_ane_chroma_corrector_w12.pt \
    /Volumes/OWC_8TB/gpr_work/artifacts/chroma_corrector/F_ane_chroma_corrector_w12.pt

# Also commit a copy to models/ as the registry entry expects, OR add a
# disk-resident entry. Final artifact path on SSD:
#   /Volumes/OWC_8TB/gpr_work/artifacts/chroma_corrector/F_ane_chroma_corrector_w12.pt
```

Add to `pipelines/registry.json` under cnns:

```
"chroma_corrector_w12": {
  "$doc": "...",
  "ckpt_path": "/Volumes/OWC_8TB/gpr_work/artifacts/chroma_corrector/F_ane_chroma_corrector_w12.pt",
  "cnn_arch_variant": "F_ane_chroma_corrector_w12",
  "depends_on_cnn": "ycbcr_decomp_y_w16_cb_w8_cr_w8"
}
```

Plus a composite pipeline `codec=ml2_q3_dec2+cnn=va_y_plus_chroma_corrector+demosaic=sips_via_gpr_tools` that runs VA-Y for L, chroma corrector for (a, b), and `lab2rgb` for assembly (no LAB-swap with cnn=none chroma).

## Acceptance criteria

Drop-in replacement for the current SOTA passes the PREVIEW gate on all four gate images: `dE_p95 <= 3.0`, `MS-SSIM >= 0.95`, `Y-PSNR >= 28`, `LPIPS <= 0.15`. No regression vs current SOTA on Z8Z_0067.

## Implementation status (2026-05-31)

- `tools/cnn/model.py` has `F_ane_chroma_corrector_w12`.
- `tools/cnn/build_chroma_corrector_sidecar.py` builds the no-leak sidecar fields.
- `tools/cnn/train_chroma_corrector.py` trains direct Lab a/b output with saturation oversampling, weighted Lab L2, windowed hue loss, and dE proxy.
- Not done yet: gate-run inference integration and registry entry. Those should be added only after a trained checkpoint exists.

## Architectural decisions (resolved 2026-05-30)

1. **in_c = 7** (no extra sips RGB inputs). Keep input minimal: 4 Bayer planes + 1 half-res Y + 2 half-res naive (a, b). Re-evaluate as ablation only if v1 misses the gate.
2. **`loss_h` is windowed (8×8 mean-pool of (a, b) before cosine distance).** User's intuition was windowed; this matches how the dE_p95 errors actually cluster (regional, not single-pixel). Implementation:
   ```python
   a_hat_w = F.avg_pool2d(a_hat, 8, stride=1, padding=4)
   b_hat_w = F.avg_pool2d(b_hat, 8, stride=1, padding=4)
   a_ref_w = F.avg_pool2d(a_ref, 8, stride=1, padding=4)
   b_ref_w = F.avg_pool2d(b_ref, 8, stride=1, padding=4)
   # then cosine distance on the window-averaged vectors
   ```
3. **Saturation sampling by chroma magnitude.** Simple `C* = sqrt(a² + b²)` percentile per tile.
4. **Direct output of (a, b)** at full resolution. No residual on the input naive chroma. Cleaner gradient, no risk of inheriting the naive chroma's bias.
