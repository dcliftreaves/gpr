# Getting Started — Real-time Raw Video Pipeline

End-to-end walkthrough: capture (Pi 5) → container (.gpraw) → playback (M-series Mac).

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
cd ../gpraw && make

# Optional: patch FFmpeg for .gpraw decode in other tools
./tools/gpraw_codec/install_patch.sh /path/to/ffmpeg-src
cd /path/to/ffmpeg-src && ./tools/gpraw_codec/configure_and_build.sh
```

## Step 1: Capture (Pi 5)

The encoder takes raw Bayer frames from the sensor (or from disk for testing) and produces `.gpr` files or directly streams into a `.gpraw` container.

```bash
# Test with a saved bayer file (assumes you've extracted bayer from a DNG)
./build/source/app/bench_fused/bench_fused /tmp/Z8_50mp.raw 8280 5520 100
```

Pi 5 sustained rate is **storage-bound**, not compute-bound. Stock SD slot caps at ~7 fps for 50 MP frames. To hit 24 fps sustained:

- **UHS-II V90 SD card** (~$30-50) — 100-200 MB/s sustained, sufficient
- **USB 3.0 external SSD** (~$50-100) — 400+ MB/s, comfortable headroom
- **NVMe via PCIe HAT** (~$30 HAT + $50 SSD) — 500-800 MB/s

See `docs/PI_HARDWARE.md` for measured numbers and full hierarchy.

## Step 2: Pack into a container (optional)

If you've captured a directory of `.gpr` files, bundle them into a `.gpraw` container for portability:

```bash
./tools/gpr2prores/gpr_mov_tool pack /clip/gpr_dir clip.gpraw \
  --fps 24 \
  --tc-start 01:00:00:00 \           # SMPTE timecode start
  --meta-dir /clip/dng_dir \         # per-frame EXIF
  --audio /clip/audio.wav            # embed audio

# Inspect
./tools/gpr2prores/gpr_mov_tool info clip.gpraw

# Round-trip: unpack a container into individual .gpr files (byte-identical)
./tools/gpr2prores/gpr_mov_tool unpack clip.gpraw /out/dir --prefix frame
```

The `.gpraw` file is just a MOV with a `GPR1` codec_tag. Any FFmpeg-aware tool with the patch applied will recognize it.

## Step 3: Playback (M-series Mac)

The `gpr2prores` tool runs the full playback pipeline: decode → CNN → demosaic → ProRes encode.

### Fastest UHD delivery (23.5 fps on M3 Max)

```bash
./tools/gpr2prores/gpr2prores \
  --meta-dng /path/to/sample.dng \
  --ckpt /path/to/BIBO_1x_AAon_w16_weights_metal_dir \
  --cnn-backend metal --cnn-scale 1x \
  --demosaic core-image --out-resolution uhd \
  clip.gpraw out_uhd.mov
```

### Best-quality 8K master (slower, 7 fps)

```bash
./tools/gpr2prores/gpr2prores \
  --meta-dng /path/to/sample.dng \
  --ckpt /path/to/F_aa_on_weights_metal_dir \
  --cnn-backend metal --cnn-scale 2x \
  --demosaic core-image --out-resolution 8k \
  clip.gpraw out_8k.mov
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
| FFmpeg won't decode .gpraw | unpatched ffmpeg | rebuild ffmpeg with `tools/gpraw_codec/ffmpeg_gpr.patch` |
| Build fails missing libraw | homebrew not installed | `brew install libraw` |

## Step 6: Where the workflows fit together

```
        +------------+      +---------------+      +----------------+
sensor →| GPR encode |  →   | .gpraw pack   |  →   | gpr2prores     | → ProRes 422 HQ
 (Pi 5) | (libvc5)   |      | (gpr_mov_tool)|      | (CNN+demosaic) |   (MOV)
        +------------+      +---------------+      +----------------+
              ↓                     ↓                       ↓
        .gpr files             .gpraw file           UHD/4K/6K/8K MOV
        (sequence)             (single MOV)          (NLE-ready)
```

Or: skip the container step and feed `gpr2prores` a directory of `.gpr` files directly.

## Next steps

For deeper integration:
- **Embed in your own ObjC app**: link `tools/gpr2prores/` modules into your AVFoundation pipeline
- **Use the FFmpeg patch**: pipe `.gpraw` through your existing FFmpeg-based workflow once you've rebuilt with the patch
- **Train your own CNN**: see the sibling `dering_proto_v2/` training repo for the recipe (NAFBlock backbone, bicubic-baseline + residual, per-tile weighted sampling on bright-hard edges)

For known limitations and future directions, see `docs/RELEASE_NOTES_v2.1.md`.
