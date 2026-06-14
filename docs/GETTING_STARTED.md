# Getting Started — GPR Raw Video Pipeline

End-to-end walkthrough: capture (Pi 5) → `.gvid` container → playback
(M-series Mac). `.gvid` is the primary raw-video deliverable; MOV/GPR1 is a
compatibility/export wrapper.

## Prerequisites

- macOS with Xcode command-line tools (`xcode-select --install`)
- For the playback tool: Apple Silicon Mac (M1 or newer)
- For capture: Raspberry Pi 5 (Cortex-A76) running 64-bit Raspberry Pi OS
- Homebrew (for libraw and FFmpeg dependencies on Mac)

## Build

```bash
# Main library + tools
cmake -B build-local -DCMAKE_BUILD_TYPE=Release
cmake --build build-local -j$(nproc)

# Playback tool (Mac only)
cd tools/gpr2prores && make

# Optional MOV/GPR1 compatibility tools
cd ../gpraw && make
```

## Step 1: Capture (Pi 5)

The encoder takes raw Bayer frames from the sensor, or source-derived frames
from disk for testing, and produces per-frame `.gpr` payloads. Production raw
video is packed into `.gvid` after capture.

```bash
# Test with a saved bayer file (assumes you've extracted bayer from a DNG)
./build/source/app/bench_fused/bench_fused /tmp/Z8_50mp.raw 8280 5520 100
```

Pi 5 sustained rate is **storage-bound**, not compute-bound. Stock SD slot caps at ~7 fps for 50 MP frames. To hit 24 fps sustained:

- **UHS-II V90 SD card** (~$30-50) — 100-200 MB/s sustained, sufficient
- **USB 3.0 external SSD** (~$50-100) — 400+ MB/s, comfortable headroom
- **NVMe via PCIe HAT** (~$30 HAT + $50 SSD) — 500-800 MB/s

See `docs/PI_HARDWARE.md` for measured numbers and full hierarchy.

## Step 2: Pack into the `.gvid` container

If you've captured a directory of `.gpr` files, bundle them into a `.gvid`
stream:

```bash
python3 tools/gvid_pack.py /clip/gpr_dir clip.gvid \
  --width 8280 \
  --height 5520 \
  --fps 24 \
  --quality 3 \
  --pixel-format 4

# Optional: validate and attach a source metadata sidecar
python3 tools/gvid_pack.py /clip/gpr_dir clip_with_meta.gvid \
  --width 8280 \
  --height 5520 \
  --fps 24 \
  --quality 3 \
  --pixel-format 4 \
  --metadata /clip/clip.gvid.meta.json
```

The `.gvid` stream is a neutral sequence of per-frame GPR payloads with stable
frame tags. See `docs/GVID_METADATA_DISPATCH_2026-06-04.md` for metadata and
runtime dispatch details.

For compatibility workflows, `tools/gpr2prores/gpr_mov_tool` can still pack or
unpack MOV/GPR1 streams, but that wrapper is not the primary capture
deliverable.

## Step 3: Playback (M-series Mac)

The `gpr2prores` tool runs the full playback pipeline: decode → CNN → demosaic → ProRes encode.

### Fastest UHD delivery (23.5 fps on M3 Max)

```bash
./tools/gpr2prores/gpr2prores \
  --meta-dng /path/to/sample.dng \
  --ckpt /path/to/BIBO_1x_AAon_w16_weights_metal_dir \
  --cnn-backend metal --cnn-scale 1x \
  --demosaic core-image --out-resolution uhd \
  clip.gvid out_uhd.mov
```

### Best-quality 8K master (slower, 7 fps)

```bash
./tools/gpr2prores/gpr2prores \
  --meta-dng /path/to/sample.dng \
  --ckpt /path/to/F_aa_on_weights_metal_dir \
  --cnn-backend metal --cnn-scale 2x \
  --demosaic core-image --out-resolution 8k \
  clip.gvid out_8k.mov
```

See `tools/gpr2prores/USAGE.md` for all CLI flags and env vars.

## Step 4: Where to get the CNN weights

The trained weights are large (~1-2 MB each as fp16 blobs) and live outside this repo. The training pipeline that produced them is at `~/Documents/dering_proto_v2/` (separate repo, not yet public).

Production models:
- `F_aa_on.pt` — 2× super-res, 263K params, +5.7 dB rendered Y-PSNR
- `BayInBayOut_1x_AAon_w16.pt` — 1× clean, 261K params, +0.9 dB rendered

To convert a `.pt` checkpoint to the fp16 blob format used by the Metal backend:

```bash
cd tools/gpr2prores
python3 extract_F_weights_metal.py \
  --ckpt ~/Documents/dering_proto_v2/checkpoints/F_aa_on.pt \
  --out /tmp/F_aa_on_weights_metal
```

The blob directory is what `gpr2prores --ckpt` points at when `--cnn-backend metal`.

## Step 5: Common pitfalls

| Symptom | Likely cause | Fix |
|---|---|---|
| `gpr2prores` shows "demosaic mode not found" | wrong `--demosaic` value | use `metal-bilinear` or `core-image` |
| Output looks green or pink | Bayer pattern mismatch | check `--meta-dng` matches your sensor |
| Pi 5 throttling at <7 fps after 5 sec | SD card sustained write | hardware upgrade per docs/PI_HARDWARE.md |
| `.gvid` metadata attach fails | sidecar/frame tags do not match stream | rebuild the sidecar or pack without `--metadata` |
| MOV/GPR1 compatibility file will not decode in FFmpeg | unpatched ffmpeg | rebuild ffmpeg with `tools/gpraw_codec/ffmpeg_gpr.patch` |
| Build fails missing libraw | homebrew not installed | `brew install libraw` |

## Step 6: Where the workflows fit together

```
        +------------+      +---------------+      +----------------+
sensor →| GPR encode |  →   | .gvid pack    |  →   | gpr2prores     | → ProRes 422 HQ
 (Pi 5) | (libvc5)   |      | (gvid_pack.py)|      | (CNN+demosaic) |   (MOV)
        +------------+      +---------------+      +----------------+
              ↓                     ↓                       ↓
        .gpr files             .gvid stream          UHD/4K/6K/8K MOV
        (sequence)             (single stream)       (NLE-ready)
```

Or: skip the container step and feed `gpr2prores` a directory of `.gpr` files directly.

## Next steps

For deeper integration:
- **Embed in your own ObjC app**: link `tools/gpr2prores/` modules into your AVFoundation pipeline
- **Use the MOV/GPR1 wrapper**: package `.gpr` frames for compatibility workflows that need ISO BMFF/MOV
- **Train your own CNN**: see the sibling `dering_proto_v2/` training repo for the recipe (NAFBlock backbone, bicubic-baseline + residual, per-tile weighted sampling on bright-hard edges)

For known limitations and future directions, see `docs/RELEASE_NOTES_v2.1.md`.
