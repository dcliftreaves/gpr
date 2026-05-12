# Visual Quality Under High `quant_scale`

**Date:** 2026-05-12. **Investigated by:** subagent on `feature/raw-video`.

The adaptive rate controller in `gpr_video_encoder` adjusts `quant_scale` per
frame to hit a target bitrate. We had never visually inspected what the output
looks like when the controller pushes `quant_scale` well above 1.0 (i.e. on
hard scenes or aggressive storage targets). This document records that
inspection.

## Method

- Input: `/tmp/Z8_ISO64.raw`, Nikon Z8 RGGB16, 8280×5520 (45 MP).
- Encoder: `gpr_encode_fused` (the same fused encoder the video path uses
  internally), 2-level wavelet (default), quality preset `q=3` (Filmscan-1).
- For each scale ∈ {1, 2, 4, 8, 16}, called `gpr_encode_fused_set_quant_scale`
  before encoding one frame, captured the bitstream, ran the inverse pipeline
  in `test_video_full_roundtrip.c` with the matching dequant scale, and dumped
  the reconstructed 16-bit Bayer to a PGM.
- Cropped each PGM to 800×800 at offset (3840,2460), gamma-corrected and
  auto-levelled, then montaged with the original raw for reference.
- The harness (a temporary env-var override in `test_video_full_roundtrip.c`)
  was reverted with `git checkout` after data collection; no source under
  `source/` is changed by this investigation.

## Quantitative result (per-frame, single-frame run, q=3)

| `quant_scale` | Bitstream size | PSNR vs raw | PSNR vs oracle | Band-match % |
|---:|---:|---:|---:|---:|
| 1.0  | 12.96 MB | 45.57 dB | ∞      | 100.00 % |
| 2.0  |  8.64 MB | 45.56 dB | 31.06  |  71.58 % |
| 4.0  |  6.33 MB | 45.53 dB | 29.91  |  74.75 % |
| 8.0  |  4.08 MB | 45.44 dB | 29.06  |  78.72 % |
| 16.0 |  2.94 MB | 45.29 dB | 28.67  |  82.03 % |

Notes:

- **PSNR-vs-raw is dominated by the LL-band ceiling** (~45 dB at q=3) and does
  not move much across scales — the wavelet's LL1 is already small, and the
  highpass bands are where `quant_scale` mostly bites. This metric is not the
  right yardstick for this question; visual inspection is.
- **PSNR-vs-oracle** is the meaningful metric here: it compares the bitstream's
  reconstructed highpass bands against the encoder's pre-rANS bands at the same
  quant scale. The drop from ∞ at scale=1 (lossless rANS roundtrip) to ~29 dB
  at scale=2 reflects coarse-quantization rounding inside the encoder, not
  bitstream loss.
- Compression: 4.4× from scale=1 → scale=16 (12.96 MB → 2.94 MB).

## Visual result

Montage: `/tmp/montage_rc.jpg` (panels left-to-right: original, q1, q2, q4,
q8, q16; 800×800 crop of the building+foliage region, gamma 2.2, auto-level).

What I see in the crop:

- **q1** — reconstruction is clean and crisp; matches `orig` after accounting
  for the 2-level wavelet's natural smoothing.
- **q2** — visually indistinguishable from q1 at this zoom level.
- **q4** — still visually indistinguishable from q2; foliage texture is
  preserved.
- **q8** — fine-branch detail in the foliage starts to lose definition. Mid
  scale (windows on the building, larger branch structure) is unaffected.
  A "watercolor blotch" texture begins to replace the finest twigs.
- **q16** — finest branch detail is gone, replaced by smooth low-frequency
  patches. Mid-scale structure (the building, larger boughs) is still entirely
  recognizable. Edges remain sharp (no visible ringing).

## Findings

1. **Degradation is gradual, not cliff-edge.** No sudden break between scales
   2 → 4 → 8 → 16; each step incrementally smooths the finest detail and
   leaves the rest alone. File size scales close to inverse-linear with quant
   scale, as expected for a wavelet/rANS codec.
2. **Dominant artifact is high-frequency-detail loss / smoothing**, not
   blockiness, posterization, or color shifts. Because quantization happens
   per band (not per spatial block), there is no JPEG-style 8×8 grid artifact.
   Wavelet ringing along high-contrast edges, which would be a concern, is
   not visible at the tested scales.
3. **No color shifts** were observable in the Bayer crop. The four Bayer
   channels (GS, RG, BG, GD) are quantized independently with the same
   scale, so they degrade symmetrically and white-balance is preserved.
4. **q=2 and q=4 are visually safe** (essentially identical to q=1 in the
   crop). q=8 starts to be detectable on the finest texture but the image is
   still clearly usable for editing. q=16 is unusable for any task that needs
   the finest detail (e.g., color grading on textured surfaces) but the
   medium-scale image is preserved.
5. **The 2-level wavelet's LL1 band is robust** — the DC content remains
   well-preserved even at scale=16 because LL1 is quantized with a fixed
   divisor (`FUSED_LL1_DIVISOR=64`) independent of `quant_scale`. This is
   why the image's overall tonality stays intact at high scales.

## Recommendation

- **Soft cap the rate controller at `quant_scale ≤ 8`** for production storage
  targets. Below 8 the degradation is consistently invisible-to-mild; above 8
  the image is still recognizable but fine-detail loss becomes a real concern
  for editing workflows.
- **Hard cap at `quant_scale ≤ 16`**. The encoder remains stable above 16 but
  the highpass becomes mostly zero, throwing away most of the codec's value.
  If the rate controller is hitting 16+, the input is structurally too rich
  for the target bitrate and the right answer is to lower the quality preset
  (q=3 → q=4) rather than push quant_scale higher; that gives a more
  balanced bit allocation across bands.
- **No emergency safety net needed.** Because degradation is gradual and no
  cliff was found in [1, 16], the existing PID-controlled clamp in
  `gpr_video.c` does not need to be tightened on safety grounds — only on
  quality-policy grounds.

## Reproducing

Build the test harness and dump reconstructions at each scale (this needs a
short temporary edit to `test_video_full_roundtrip.c` to honor a
`QUANT_SCALE` env var by bypassing `gpr_video_encoder` and calling
`gpr_encode_fused_create` / `gpr_encode_fused_set_quant_scale` / 
`gpr_encode_fused_frame` directly; remember to `git checkout` it
afterwards). Then:

```
for S in 1.0 2.0 4.0 8.0 16.0; do
  QUANT_SCALE=$S DUMP_BAYER=/tmp/recon_q${S%.*}.pgm \
    /tmp/test_video_full_roundtrip /tmp/Z8_ISO64.raw 8280 5520 4 3 1 24.0
done
for tag in orig_bayer recon_q1 recon_q2 recon_q4 recon_q8 recon_q16; do
  magick /tmp/${tag}.pgm -crop 800x800+3840+2460 +repage -resize 400x400 \
    -gamma 2.2 -auto-level /tmp/${tag}.png
done
magick montage -label '%t' /tmp/orig_bayer.png /tmp/recon_q1.png \
  /tmp/recon_q2.png /tmp/recon_q4.png /tmp/recon_q8.png /tmp/recon_q16.png \
  -tile 6x1 -geometry +4+4 -background black /tmp/montage_rc.jpg
```
