# gpr2prores — Usage

Real-time playback tool: reads GPR / DNG / GPRaw raw video, runs a CNN, demosaics, encodes ProRes 422 HQ.

## Quick start

```bash
# Decode a .gvid container at UHD with the production CNN
gpr2prores \
  --meta-dng /path/to/sample.dng \
  --ckpt /path/to/weights_metal_dir \
  --cnn-backend metal --cnn-scale 1x \
  --demosaic core-image --out-resolution uhd \
  /path/to/clip.gvid /path/to/out.mov
```

## Input formats

| Format | Notes |
|---|---|
| `.gpr` | Single-frame GPR file |
| Directory of `.gpr` | Frame sequence (sorted lexicographically) |
| `.dng` / directory of `.dng` | Encode + decode roundtrip in one pass (for validation) |
| `.gvid` | Neutral raw-video stream of per-frame `.gpr` payloads; auto-unpacked to temp dir |
| `.mov` / `.gpraw` / `.gprv` | GPRaw container (auto-unpacked to temp dir) |

`--meta-dng` is required for `.gpr`, `.gvid`, and GPRaw/MOV input
(color/wb metadata source). For `.dng` input it's auto-discovered.

## CNN modes (`--cnn-scale`)

| Flag | Model | Output dims | Quality | Speed (UHD) |
|---|---|---|---|---|
| `--cnn-scale 2x` (default) | F super-res | 8K bayer → demosaic → UHD | +5.7 dB rendered | ~19 fps |
| `--cnn-scale 1x` | BIBO_1x clean | 4K bayer → demosaic → UHD | +0.9 dB rendered | ~23.5 fps |
| `--no-cnn` | (none) | codec bayer → demosaic → UHD | baseline | ~28 fps |

For 4K delivery prefer `--cnn-scale 1x`. For native 8K masters prefer `--cnn-scale 2x`.

## CNN backends (`--cnn-backend`)

| Backend | Notes |
|---|---|
| `metal` | Hand-rolled Metal hybrid (NAFBlock kernels + MPSGraph middle). Fastest. Requires a directory of fp16 .bin blobs (extracted via `extract_F_weights.py`). |
| `coreml` | MLPackage path. Slower (~6×) — NAFBlock ops aren't ANE-native. |
| `mpsgraph` | Pure MPSGraph path. Reference for hybrid correctness. |

## Demosaic backends (`--demosaic`)

| Backend | Notes |
|---|---|
| `metal-bilinear` (default) | Hand-rolled bilinear demosaic. Fastest but lowest quality. |
| `core-image` | CIRAWFilter via `filterWithCVPixelBuffer:properties:`. Apple AHD-quality. ~28-48 ms at UHD. |

## Output resolution (`--out-resolution`)

Width-fixed, height preserves source aspect:
- `2k` (2048×—)
- `uhd` (3840×—) — recommended UHD 4K delivery
- `4k` (4096×—)
- `6k` (6144×—)
- `8k` — native source dims, no scale

## Performance flags

- `--timing` — per-frame, per-stage breakdown to stderr
- `--max-frames N` — process at most N frames
- `--skip-errors` — continue past per-frame decode/CNN failures

## Environment variables

- `SUPERRES_PROFILE=1` — per-NAFBlock GPU timing (commits between stages, breaks pipelining)
- `CNN_COREML_UNITS={cpu,gpu,ane,all}` — override CoreML compute units (default `all`)
- `SUPERRES_NOFUSE_POST=1` — use the legacy 2-kernel post-processing path (for A/B)
- `TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp` — place auto-unpacked `.gvid` /
  GPRaw frame directories on the external work drive.

## Examples

```bash
# Native 8K master via F super-res
gpr2prores --meta-dng src.dng --ckpt /tmp/F_aa_on_weights_metal \
  --cnn-backend metal --cnn-scale 2x \
  --demosaic core-image --out-resolution 8k \
  clip.gvid master_8k.mov

# Fast UHD daily via BIBO_1x
gpr2prores --meta-dng src.dng --ckpt /tmp/BIBO_1x_AAon_w16_weights_metal \
  --cnn-backend metal --cnn-scale 1x \
  --demosaic core-image --out-resolution uhd \
  clip.gvid daily.mov

# Validation roundtrip on a DNG sequence (no codec, no CNN, just demosaic)
gpr2prores --no-codec --no-cnn \
  --demosaic core-image --out-resolution uhd \
  /clip/dngs/ validation.mov

# Per-stage GPU profile (debug only)
SUPERRES_PROFILE=1 gpr2prores --max-frames 8 --timing \
  --meta-dng src.dng --ckpt /tmp/BIBO_1x_AAon_w16_weights_metal \
  --cnn-backend metal --cnn-scale 1x \
  --demosaic core-image --out-resolution uhd \
  clip.gvid /tmp/profile.mov 2>&1 | grep profile
```

## Companion tool: gpr_mov_tool

Packs/unpacks `.gpraw` containers:

```bash
# Pack a directory of .gpr frames into a container with EXIF + timecode + audio
gpr_mov_tool pack /clip/gpr_dir clip.gpraw \
  --fps 24 \
  --tc-start 01:00:00:00 \
  --meta-dir /clip/dng_dir \
  --audio /clip/audio.wav

# Inspect a container
gpr_mov_tool info clip.gpraw

# Unpack back to .gpr files (round-trip is byte-identical)
gpr_mov_tool unpack clip.gpraw /out/dir --prefix frame
```

## Building

```bash
cd tools/gpr2prores && make
```

Requires the main gpr build at `../../build-local/`. Links against Metal, MetalPerformanceShadersGraph, CoreImage, IOSurface, VideoToolbox, AVFoundation, CoreML, ImageIO, libraw.
