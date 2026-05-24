# ANE-friendly F retrain — results (May 23, 2026)

## What we did

Per `docs/ANE_FRIENDLY_F_PLAN.md`, trained two variants of the F backbone with
op swaps designed to run on Apple Neural Engine:

- **F_ane** (2× super-res, replaces F_aa_on.pt): NAFBlock with `BatchNorm2d` in
  place of `LayerNorm2d`, `SiLU` in place of `SimpleGate`. 316,800 params.
- **F_ane_no_sr** (1× clean, replaces BIBO_1x_AAon_w16.pt): same with 1× output
  head. 315,060 params.

Training ran in parallel on M3 Max (1× variant) and M5 Max (2× variant). Each
80 epochs. M5 was 2.6× faster per epoch than M3 on identical workload.

Checkpoints saved as:
- `~/dering_proto_v2/checkpoints/BayInBayOut_2x_AAon_w16_ANE.pt`
- `~/dering_proto_v2/checkpoints/BayInBayOut_1x_AAon_w16_ANE.pt`

## Quality result — wins on canonical 8K rendered Y-PSNR

| Model | Val tile gain | Rendered Y-PSNR (Z8_ISO64) | vs reference |
|---|---|---|---|
| codec baseline | — | 31.06 dB | — |
| F_aa_on (original, BN/LN) | +4.13 dB | 36.31 dB | reference |
| **F_ane** (BN+SiLU) | **+4.19 dB** | **36.57 dB** | **+0.26 dB better** |
| BIBO_1x (original) | +10.93 dB | 31.95 dB | reference |
| **F_ane_no_sr** (BN+SiLU) | **+11.42 dB** | **31.96 dB** | ~same |

The BN+SiLU swap **improves** the 2× super-res variant slightly, matches the 1× variant. No quality cost.

## Speed result — ANE doesn't help at this resolution

Inference timings on M3 Max for the 1384×2072 codec-plane input (i.e. 2.87M
output pixels for 1× mode, 11.5M for 2× super-res):

| Backend | F_ane (2×) | F_ane_no_sr (1×) |
|---|---|---|
| CoreML ALL (ANE+GPU+CPU) | 378 ms | 360 ms |
| CoreML ANE-preferred | 145 ms | 124 ms |
| **Metal hybrid (existing, LN+SimpleGate)** | **~37 ms** | **~33 ms** |
| Python MPS (F_ane variant) | 83 ms | 78 ms |

**Why ANE didn't win:**
- PiperSR (the reference real-time ANE SR model) runs at 21 ms for 360p→720p
  (691K output pixels)
- Our pipeline produces 17× more pixels (8K bayer output)
- 17 × 21 ≈ 357 ms — matches our CoreML ALL measurement
- ANE per-pixel throughput is lower than the M3 GPU at large tensor sizes
- GPU wins at the resolutions we care about; ANE wins at smaller tile sizes

The architecture swap was successful for ANE-readability but the bottleneck
moved: ANE just doesn't have the throughput to win on 8K-bayer-sized tensors.

## What this means for deployment

**No ANE deployment.** The Metal hybrid backend remains the fastest path. The
ANE-friendly checkpoints CANNOT be loaded by the existing Metal hybrid (it has
hand-rolled kernels for LayerNorm + SimpleGate, not BN + SiLU). To use these
checkpoints we'd need to:

1. Either write new Metal kernels for BN + SiLU (real engineering, ~half day)
2. Or keep the existing F_aa_on and BIBO_1x models for deployment (current ship)

Given the **quality is the same**, the existing checkpoints are good enough.
**No deployment change needed.**

## Useful side findings

1. **M5 Max** is 2.6× faster per epoch than M3 Max for our F-backbone training.
   For future training work, use M5.
2. **BN+SiLU vs LN+SimpleGate** is a real quality improvement on the 2× super-res
   variant (+0.26 dB rendered). If we ever rewrite the Metal kernels, the new
   weights are quality-superior.
3. **Tiling strategy could revive ANE** — if we process the image in e.g. 360×360
   tiles, ANE might hit its sweet spot. Tile overlap + memory cost vs the speed
   win is the open question. Not pursued in this experiment.
4. **CoreML conversion of BN+SiLU works cleanly** — no manual fixes needed.
   Same conversion path applies to other architectures we might try later.

## Net session takeaway

The training experiment **confirmed the architecture swap is valid and even
slightly better on quality**. The speed lever it was supposed to unlock (ANE)
turned out to be a wash at our pixel count. The lesson is "match the platform
to the resolution" — ANE is for small tensors, GPU is for huge ones.

Sources:
- [PiperSR repo](https://github.com/ModelPiper/PiperSR)
- See also `docs/ANE_FRIENDLY_F_PLAN.md` for the original spec
- See also `docs/RESEARCH_VSR_AND_ANE.md` for the prior-art survey
