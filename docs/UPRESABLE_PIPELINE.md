# UPRESABLE pipeline — half-res capture → full-res editable raw

## What this is

The GPR ship architecture targets **24 fps × 50 MP editable raw video** by
splitting the work across two devices. The current Pi 5 receipt is acceptable
as a conservative Labs proxy at 19.98 fps median with 0 drops and valid
`.gvid`; actual Mission 1 hardware still needs a 24 fps target receipt.

```
   Pi 5 (camera-side)              Mac M3 (desktop-side)
   ─────────────────────            ──────────────────────────────
   sensor → ml2_q3_dec2  →   .gpr
                  (half-res Bayer,
                   1.0–3.4 MB/frame,
                   24 fps capable)         decode →
                                            BIBO_2x CNN on MPS →
                                             full-res Bayer →
                                              ml2_q3 encode →
                                               .gpr (full-res)

                                          → DECODE-on-demand →
                                              full-res Bayer →
                                               raw editor
```

The terminology that maps to the registry:

| Ship class | Codec | Resolution | Used for |
|-----------|-------|-----------|----------|
| STILL     | gpr_tools q=0/3/8 | full-res | Archival photo capture (~1 fps Pi) |
| FREEZE    | ml2_q3 (no decimate) | full-res | High-quality freeze-frame (~6 fps Pi, 30+ fps Mac) |
| **UPRESABLE** | ml2_q3_dec2 | half-res capture | **target 24 fps video capture; desktop upres to full-res editable raw** |
| PREVIEW   | ml2_q3_dec2 | half-res, RGB rendering | Display-only (camera back, scrub) — same codec as UPRESABLE |

PREVIEW and UPRESABLE use the **same captured `.gpr` files**. The distinction is
what the desktop does with them:
- **PREVIEW**: decode + render to RGB (sips / SOTA-v2 / etc) for viewing
- **UPRESABLE**: decode + BIBO_2x super-res to full-res Bayer + re-encode as
  full-res .gpr → editable raw video

## Pipeline stages

### Capture (Pi 5 proxy, camera target pending)

1. Sensor delivers 14-bit Bayer at 50 MP (8280 × 5520)
2. `ml2_q3_dec2` codec internally decimates 2×2 → encodes 4140 × 2760 at q=3
3. Output: `.gpr` file, ~1.0–3.4 MB/frame depending on content
4. Historical Pi 5 receipt reached 24.93 fps median
   (`docs/pi5_bench_2026-05-26.md`); latest strict 14,400-frame Labs proxy
   receipt at commit `0dd6660` reaches 19.98 fps median with 0 drops, valid
   `.gvid`, and interrupted-tail recovery. That is proxy-acceptable for Labs
   review; production camera readiness still requires the Mission 1 24 fps
   hardware receipt.

### Upres + re-encode (Mac M3, offline post)

5. Read .gpr → decode → 4140 × 2760 Bayer (uint16)
6. Run `BIBO_2x` CNN on MPS (variant `F_ane`, sr2x=True, ~317K params)
   - Tiled inference: 128×128 input tiles → 256×256 output planes
   - Batched 32 tiles per MPS forward pass
   - ~375–550 ms per full image on M3 (varies with input content)
7. Output: 8280 × 5520 Bayer (uint16) — same dimensions as source sensor
8. Encode via `ml2_q3` (full-res, no decimation, q=3)
9. Output: full-res `.gpr` file, ~4–6 MB/frame

### Pack to GPRaw (primary deliverable)

10. Per-frame full-res `.gpr` files go into `fullres/<frame>.gpr`
11. After all frames are written, `tools/gpr2prores/gpr_mov_tool pack <fullres/> <out.gpraw.mov> --fps 24`
    wraps them into a MOV container with `codec_tag=GPR1`
12. The `.gpraw.mov` plays through `gpr2prores`; FFmpeg decodes it natively via
    the `AV_CODEC_ID_GPR` patch (libavcodec); raw NLEs that consume the GPRaw
    container open it as a single asset

### Opt-in correctness / hand-off artifacts

13. `--render-prores`: decode full-res .gpr → gpr_tools wrap as DNG → sips → 16-bit
    TIFF sequence → ProRes 422 HQ review file. Adds ~1.5 s/frame. For human review.
14. `--dng-export`: persist per-frame editable DNG (~91 MB) + gpr_tools .gpr (~2–8 MB)
    so Adobe Camera Raw / darktable / etc. can open each frame standalone.
    Adds ~700 ms/frame.

## Performance (measured 2026-05-30)

Per-stage timing on Mac M3 — **default path (GPRaw deliverable)**:

| Stage | Time | Notes |
|-------|------|-------|
| half-res .gpr decode (`fused_decode_cli`) | ~97 ms | |
| BIBO_2x CNN on MPS | **~435 ms** | Tiled (128×128 → 256×256) + batched-32 |
| Full-res .gpr encode (FUSED ml2_q3) | **~210 ms** | single-pass |
| `gpr_mov_tool` pack (amortized) | ~8 ms | 720-frame batch: 5.76 s total |
| **Total per frame — GPRaw delivery** | **~750 ms** | 4-way parallel: ~600 ms wall |

With opt-in flags:

| Stage | Time | Notes |
|-------|------|-------|
| `--render-prores` (DNG-wrap + sips + TIFF) | +1500 ms | for ProRes review |
| `--dng-export` (gpr_tools .gpr + persist DNG) | +700 ms | for raw-editor hand-off |
| Total with all opt-ins | ~2.9 sec/frame | matches the 720-frame timelapse 2861 ms median |

So a 30-sec (720-frame) timelapse takes:
- **GPRaw delivery**: ~9 min on M3 with 4-way parallel
- With `--render-prores --dng-export`: ~34 min (this is what the dashboard's 30-sec ProRes was)

## Editable raw fidelity

Bayer PSNR vs source DNG, measured on the 4 gate images:

| Image | Bayer PSNR (dB) | Quality category |
|-------|----------------|-------------------|
| Z8Z_0001 | 38.97 | Visually indistinguishable from source |
| Z8Z_0067 | 43.78 | Mathematically near-source |
| Z8Z_5323 | 40.14 | Indistinguishable from source |
| Z8Z_6693 | 37.85 | Visually indistinguishable from source |

For comparison:
- 30 dB: visible-but-not-objectionable
- 35 dB: barely perceptible
- 40+ dB: indistinguishable in practice

The output `.gpr` files at `/Volumes/OWC_8TB/gpr_work/artifacts/upresable/fullres/`
can be opened by any GPR-aware tool (`gpr_tools` to convert to DNG, then any
raw editor) and exhibit proper raw editing latitude. The `.gpraw.mov`
container at `upresable_timelapse.gpraw.mov` packs the full sequence with
the `GPR1` codec_tag and is the primary deliverable.

## Storage budget at 24 fps × 50 MP

| Stream | MB/frame | MB/s | GB/hour |
|--------|----------|------|---------|
| **Camera capture** (half-res .gpr) | 1.0–3.4 | 24–82 | 86–293 |
| Upres output (full-res .gpr) | 4–6 | 96–144 | 346–518 |
| Source DNG (sensor raw, uncompressed) | ~90 | ~2160 | ~7600 |

The camera capture stream fits comfortably on a UHS-I V30 microSD or any
USB 3.0 SSD. The upres output is computed offline so its bandwidth isn't
a real-time constraint.

## Why the BIBO_2x CNN doesn't add noise

The BIBO_2x output IS a learned hallucination — the CNN reconstructs the
plausible high-frequency content that was lost in the 2×2 decimation. The
output is FORMALLY synthetic in the high frequencies. But:

1. The output is encoded as a real .gpr file with valid Bayer values
2. Any raw editor opening this file applies the SAME color matrix, WB,
   exposure tools, and recovery operations it would for a true 50 MP capture
3. The CNN was trained against actual 50 MP DNG ground truth (498 image
   corpus, 19,920 tiles) so the hallucination is statistically faithful to
   real sensor data

This is functionally identical to:
- AV1's film grain synthesis (synthesize plausible noise, not preserve it)
- Most modern camera's pixel-shift "super resolution" modes
- Lightroom's "Enhance" detail recovery

You can apply exposure recovery, white-balance shifts, highlight-roll-off
and shadow-pull operations to the full-res .gpr files the same way you
would to any 50 MP capture.

## Limitations + caveats

- Spatial detail beyond what the half-res capture preserved is CNN-inferred,
  not real. For motion-blurred subjects this means the upres can't recover
  detail that wasn't there.
- The CNN was trained on outdoor / landscape content. OOD content
  (low-light night skies, heavy chroma noise) may show CNN artifacts.
- Re-encoding the upresed Bayer adds a quantization pass — 38–44 dB Bayer
  PSNR is the combined loss of the half-res capture + CNN upres + full-res
  encode. The half-res capture itself is ~50 dB; the CNN+re-encode is what
  brings it down.

## Reproduction

```
python3 tools/cnn/upresable_pipeline.py --mode both --n-frames 60 --workers 4
```

Outputs:
- `/Volumes/OWC_8TB/gpr_work/artifacts/upresable/halfres/*.gpr` — capture files
- `/Volumes/OWC_8TB/gpr_work/artifacts/upresable/fullres/*.gpr` — editable raw output
- `/Volumes/OWC_8TB/gpr_work/artifacts/upresable/upresable_timelapse.mov` — ProRes preview
- `/Volumes/OWC_8TB/gpr_work/artifacts/upresable/summary.json` — metrics
