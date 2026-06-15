# GPR 2.1 (draft) — Real-time raw video pipeline

A draft of release notes for when the `feature/neon-assembly` PR (#4) merges.

## Highlights

- **`gpr2prores`** — new ObjC playback tool: GPR → CNN super-res / clean → demosaic → ProRes 422 HQ. Ships two CNN modes (2× super-res, 1× clean) and three demosaic backends (Metal bilinear, CIRAWFilter, Core Image).
- **GPRaw container** — single-file MOV wrapper for GPR sequences with the `GPR1` codec_tag, plus optional embedded audio, SMPTE timecode track, and per-frame EXIF. 0.005% size overhead.
- **FFmpeg patch** — adds `AV_CODEC_ID_GPR` to libavcodec so any FFmpeg-aware tool can decode `.gpraw` natively. Measured 182 fps decode on M3 Max.
- **Pi 5 encoder optimizations** — NEON-tuned hot paths. Historical full-res
  planning bench hit 25.9 fps × 50 MP in-memory; sustained full-res capture on
  the tested storage setup was storage-bound (see Pi hardware notes). Current
  `.gvid`/Labs target receipts are tracked in `docs/LABS_TARGET_BENCH.md`.

## Real-time performance (M3 Max playback)

| Mode | UHD throughput | Quality vs codec baseline |
|---|---|---|
| No CNN | 28 fps | reference |
| BIBO_1x (1× clean) | **23.5 fps** | +0.9 dB rendered Y-PSNR |
| F super-res 2× | 19 fps | +5.7 dB rendered Y-PSNR |

ProRes 422 HQ encoder is hardware-accelerated via VTCompressionSession. All stages 4-deep pipelined.

## Pi 5 capture rate

| Test | fps | Notes |
|---|---|---|
| Encoder kernel (in-RAM, LL-only-fast) | 25.9 | compute ceiling on stock Pi 5 |
| Sensor → SD card burst (≤4 sec) | 21.3 | absorbed by page cache |
| Sensor → SD card sustained | 6.88 | **bottlenecked by SD card 33 MB/s write** |

For this historical full-res planning case, sustained 24 fps × 50 MP capture
needed a measured storage path above 84 MB/s, such as USB SSD or NVMe. Current
half-res `.gvid`/Labs receipts use the target bench docs instead of this draft
release-note budget.

## New tools and files

```
tools/gpr2prores/      — real-time playback (gpr2prores binary)
tools/gpr2prores/gpr_mov_tool — pack/unpack/info for .gpraw containers
tools/gpraw/           — standalone libgpraw + gpraw_pack/unpack
tools/gpraw_codec/     — FFmpeg patch and roundtrip test harness
```

## Tooling notes for users

```bash
# Build everything
cmake -B build-local -DCMAKE_BUILD_TYPE=Release && cmake --build build-local -j$(nproc)
cd tools/gpr2prores && make
cd tools/gpraw && make

# Patch FFmpeg for .gpraw decode
./tools/gpraw_codec/install_patch.sh /path/to/ffmpeg-src
cd /path/to/ffmpeg-src && ./tools/gpraw_codec/configure_and_build.sh

# Use the playback tool (see tools/gpr2prores/USAGE.md)
./gpr2prores \
  --meta-dng sample.dng --ckpt /path/to/weights_metal_dir \
  --cnn-backend metal --cnn-scale 1x \
  --demosaic core-image --out-resolution uhd \
  clip.gpraw out.mov
```

## Documentation

- `tools/gpr2prores/USAGE.md` — CLI reference, all flags and env vars
- `docs/PI_HARDWARE.md` — storage requirements for Pi 5 capture
- `docs/RESEARCH_VSR_AND_ANE.md` — literature survey of related work
- `docs/ANE_FRIENDLY_F_PLAN.md` + `docs/ANE_TRAINING_RESULTS.md` — ANE-friendly F retraining (negative result on ANE inference speed at our resolution; positive on quality)

## Known limitations

- The CNN weights are not in this repo — they live in a sibling training repo and ship as separate downloads.
- Apple Neural Engine inference doesn't outperform the M-series GPU at 8K bayer dimensions. The Metal hybrid backend is the fastest path; CoreML/ANE remains available as a fallback for smaller-input workloads.
- VSR (multi-frame super-resolution) was explored but plateaued without explicit motion alignment. Real-RawVSR and similar architectures use deformable convolutions which currently don't run efficiently on Apple's MPS backend. See `docs/RESEARCH_VSR_AND_ANE.md` for the lit survey.

## Credits

Hand-rolled Metal hybrid CNN backend, CIRAWFilter zero-copy demosaic, and the GPRaw container were built across a sustained collaboration with Claude (Anthropic).
