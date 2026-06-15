# Changelog

All notable changes to GPR are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] — 2026-05-30

The 2.2 release adds a fourth ship class — **UPRESABLE** — that turns the
historical Pi 5 half-res capture path into editable full-res raw via a desktop
BIBO_2x super-res CNN. All four ship classes (STILL / VIDEO_FREEZE /
PREVIEW / UPRESABLE) pass their gate thresholds on the test set. Follows
v2.1.0-fused (FUSED real-time video codec, NEON Pi 5 optimizations,
gpr2prores, GPRaw container, FFmpeg patch).

Note for current `master`: later strict Labs target receipts block the Pi 5
half-res capture path at 19.98 fps median versus the 24 fps target. The older
24.93 fps number in this release section is historical.

### Added

- **UPRESABLE ship class** (`tests/quality_gates/gates.json`,
  `pipelines/registry.json`). Workflow: Pi 5 captures half-res
  `ml2_q3_dec2` (historical 24.93 fps receipt, 0.98 MB/frame); desktop M3 decodes,
  runs `bibo2x_ane_ml2_q3_dec2_diverse` super-res CNN on MPS, wraps as
  editable DNG (91 MB) + compressed `.gpr` (2–8 MB), and renders
  ProRes 422 HQ for review. Bayer PSNR vs source DNG: 37.85–43.78 dB
  on the 4 gate images. Threshold gates the workflow-native
  `bayer_psnr_final ≥ 35 dB`; rendered LPIPS / MS-SSIM / Y-PSNR /
  ΔE2000 are computed informationally but not enforced (the user grades
  the file in their NLE, so rendered comparison overconstrains).
- `tools/cnn/upresable_pipeline.py` — end-to-end Mac post-processing
  pipeline. CLI `--mode {regression,timelapse,both} --n-frames N
  --workers N`. 16-bit TIFF master frames default; `--eight-bit` flag
  opts into the legacy 8-bit path (kept for diagnostic comparison only;
  causes sky banding).
- `tests/quality_gates/build_production_dashboard.py` — HTML dashboard
  at `dashboard/index.html` aggregating ProRes timelapse, sample
  frame + 100% sky crop, full perf tables (Pi 5 + Mac M3), regression
  with run-hashes, and file-link inventory.
- 16-bit ProRes path: `sips` → 16-bit TIFF, `cv2.IMREAD_UNCHANGED`
  preserves uint16, `ffmpeg` reads `rgb48le` with `-sws_dither auto`.
  Sky patch unique levels per channel: ~5000× the previous 8-bit
  pipeline (1063–4150 vs ~25).
- `GPR_GATE_MODE`-style decode path in `test_fused_decode_roundtrip.c`
  already supported encoded + decoded sizes for the gate runner; the
  binary at `build-local/bin/test_fused_roundtrip` was rebuilt from
  that source (the older sibling `test_fused_roundtrip.c` had a stale
  band-count self-check that rejected `GPR_INCLUDE_LL=1` configs).
- `bayer_psnr_final` is now a gateable metric in `run_gate.py` —
  threshold rules in `gates.json` can reference it alongside the
  rendered-image metrics.
- Gate runner handles missing ship-class entries by issuing
  `INDETERMINATE` and logging raw metrics (instead of crashing). Null
  threshold values mean "informational only" per `$rules`.
- `tools/cnn/preview_timelapse_fast.py` and
  `tools/cnn/preview_timelapse_fast_sota.py` default to 16-bit;
  `--eight-bit` opts into the legacy path.

### Fixed

- 8-bit ProRes sky banding (root cause: `sips` rendered 8-bit PNG by
  default; PIL / imageio silently downconvert 16-bit input to uint8;
  only `cv2.IMREAD_UNCHANGED` preserves uint16). Now end-to-end 16-bit
  with dithering on 16→10-bit ProRes quantization.
- ProRes assembly hang: parallel workers + ffmpeg-stdin-pipe deadlocked
  on the moov atom. Switched to file-based ffmpeg assembly using
  symlinks into a sequence directory.
- Numpy `float32` → `json.dumps` crash at end of
  `tools/cnn/upresable_pipeline.py` (`default=lambda` handles
  numpy types).
- Gate runner now treats `bayer_psnr_codec` and `bayer_psnr_final` as
  gateable alongside rendered metrics, and skips `null`-value
  thresholds (informational mode).

### Performance

- Pi 5 capture analysis: NEON-tuned historical full-res hot paths
  hit 25.9 fps × 50 MP in-memory, while the current `.gvid` Labs path is
  tracked by `docs/LABS_TARGET_BENCH.md` and `docs/VIDEO_STATUS.md`.
- **GPRaw is the UPRESABLE primary deliverable** — wraps the full-res
  `.gpr` sequence in a MOV container with codec_tag `GPR1` (`gpr_mov_tool
  pack`, amortized 8 ms/frame). Per-frame DNG wrap is opt-in via
  `--dng-export` (legacy hand-off to Adobe CR / darktable). ProRes 422 HQ
  review file is opt-in via `--render-prores`.
- Per-frame UPRESABLE on Mac M3: **~750 ms GPRaw delivery** (decode 97 +
  BIBO_2x 435 + encode 210 + pack 8). With `--render-prores --dng-export`:
  2.9 s (the legacy path the 720-frame timelapse measured). **3.8× speedup**
  by skipping per-frame DNG wrap.
- Pi-to-Mac end-to-end UPRESABLE bench at `tools/test/bench_pi_to_mac_upresable.sh`.
  Stages: Pi encode (`ml2_q3_dec2`), USB rsync, Mac decode+CNN+encode,
  `gpr_mov_tool pack`. Bottleneck on first 120-frame run was Mac
  decode+CNN at 2.06 fps; USB at 524 MB/s is not a bottleneck.

## [Unreleased] — branch `fix/multilevel-cascade-regression` (pre-2.2)

### Added

- `tools/test/metrics.py` — visual metric stack (Y-PSNR, MS-SSIM,
  LPIPS-AlexNet, ΔE2000) computed on demosaiced RGB. Replaces bayer-PSNR
  as the primary quality metric.
- `tools/test/test_multilevel_regression.py` — tripwire that fails until
  the FUSED multi-level cascade bug is fixed.
- `tools/test/reproduce_regression.sh` — self-contained shell repro of
  the multi-level regression.
- Historical regression and session-summary artifacts were later consolidated
  into `docs/EXPERIMENT_ARCHIVE_2026-06-04.md` plus current Labs target docs.
- `FUSED_INVERSE_DESCALE` env var in `fused_decode.c` — per-level descale
  override for cascade debugging.
- `FUSED_L2_L3_PRESCALE` env var in `fused_encode.c` —
  `wavelet_decompose_buffer` prescale override.

### Walked back

- The "5-22% file-size savings from CNN-aware cranked quants" claim
  (PRs #16, #20, #21, #23, #25). The original numbers were measured
  against the broken multi-level FUSED path. Re-measured on
  single-level: equivalent cranks save 8.8% (HH×4) to 26.2%
  (LH/HL/HH×8).
- The "+5.61 dB CNN gain" and "+7.80 dB L1+L2 retrained CNN gain"
  numbers — measured against the broken multi-level baseline.

### Known issues

- **FUSED multi-level wavelet cascade has a ~10 dB PSNR regression vs
  single-level on natural images.** Root cause: Nyquist aliasing through
  the 3-level 5/3 wavelet cascade, compounded by double-rounding in
  `horizontal_filter`. Fix pending (task #172). Shipped tools
  (`gpr_tools`, default FUSED single-level) are not affected.

## [2.0.0] — 2026-05-12

GPR 2.0 turns the original stills-only VC-5 codec into a production raw-video
codec while leaving the stills API and on-disk GPR format untouched. The
work landed across 147 commits on the `feature/raw-video` branch.

### Added

- **Video encoder API** (`source/lib/vc5_encoder/gpr_video.h`):
  `gpr_video_encoder_create()` returns a pipelined caller→encoder→writer
  3-thread encoder. `_submit()` applies natural backpressure;
  `_flush()` / `_destroy()` drain pending frames; `_cancel()` provides
  force-cancel from any thread; `_set_target_bitrate()` enables the
  adaptive rate controller; `_set_denoise()` enables wavelet-domain
  BayesShrink denoise; `_get_stats()` returns wait-counter telemetry
  for diagnosing the binding constraint.
- **Dual-encoder ping-pong mode** —
  `gpr_video_encoder_create_dual(..., encoder_count=2, ...)` runs two
  `FUSED_ENCODER` contexts in parallel encoder threads, dispatched by
  `frame_tag % 2`, with the writer reordering completions into strict
  tag order. +40% encoder-bound throughput on M1.
- **Fatal writer-return + force-cancel** — `gpr_video_writer_fn` may now
  return `<0` to mark the encoder aborted; pending frames are dropped
  without invoking the writer callback, and `_flush()` / `_destroy()`
  return immediately. `gpr_video_encoder_cancel()` provides the same
  signal externally and is safe to call from any thread, including the
  writer callback. Idempotent.
- **Video container format** (`source/lib/vc5_encoder/gpr_video_format.h`):
  32-byte clip header (`'GVID'`) + 16-byte per-frame headers (`'FRM\0'`)
  wrapping a sequence of VC-5 bitstreams. Carries pixel format, quality,
  dimensions, fps, target bitrate, and a frame-count hint. Format
  version 1, with reserved bytes for forward-compatible additions.
- **Fused encoder** (`source/lib/vc5_encoder/fused_encode.{h,c}`):
  Bayer→wavelet→quantize→frequency-count in one streaming pass.
  Replaces the previous 4-stage serial pipeline with a 2-pass
  parallelized design (4 channel threads in Pass 1, 12 band threads
  in rANS Pass 2). Pass 1 is built around a shared 4-channel unpack
  ring so Bayer LUT lookups are not duplicated across per-channel
  threads. Reusable encoder context (`FUSED_ENCODER`) lets video
  callers pre-allocate band buffers, row buffers, and the output
  stream buffer so per-frame allocation overhead is amortized.
- **Adaptive bitrate rate controller** — proportional control law
  (`new_scale = scale * sqrt(actual/target)`, ±15%/frame clamp,
  EMA of recent output sizes) modulates the fused encoder's
  `quant_scale` between frames to track a target MB/s within ~7%
  above the per-content floor. Converges in ~10 frames after a
  content change.
- **Wavelet-domain BayesShrink denoise**, auto-enabled on DNG inputs
  carrying a `NoiseProfile` and hooked into the fused encoder via
  `gpr_encode_fused_set_denoise()`. Operates between Pass 1 and
  Pass 2 on each highpass band. 3-38% size win at SSIM 0.9998
  on entropy-matrix DNGs.
- **ARM64 NEON paths** in the fused encoder: vectorized color
  conversion in unpack, 8-wide vertical filter + fused quantize,
  4-wide highpass / NEON lowpass horizontal filter, 8-wide zero-skip
  in frequency counting, CLZ-based magnitude classifier, polynomial
  log curve for the unpack stage, and per-band rANS encode unrolled
  4-way for ILP. Hand-tuned ARM64 assembly for `unpack_all_channels_row`
  available behind `FUSED_UNPACK_ASM=1` for A78-class silicon.
- **Storage-bus pipeline simulator** (`source/app/test_video_pipeline_sim.c`):
  throttled writer callback with configurable MB/s ceiling and periodic
  GC stalls. Lets the pipeline be validated against UHS-I V30 →
  CFexpress B profiles without real hardware.
- **Six test binaries** in `source/app/`:
  - `test_video_roundtrip.c` — band-level decode verification
  - `test_video_full_roundtrip.c` — full encode → decode → PSNR
    against raw Bayer (with optional `DUMP_BAYER` for visual inspection)
  - `test_edge_sizes.c` — encoder works across 256×256 → 50 MP
  - `test_video_pipeline.c` and `test_video_pipeline_sim.c` —
    3-stage producer→encode→writer benchmark
  - `test_video_encoder_abort.c` — fatal writer-return and
    `_cancel()` flows
  - `test_video_full_chain.c` — end-to-end integration through the
    container format and back
  Plus `test_video_format.c` for container-header parsing.
- **Preview decoder** — standalone LL2-only decoder that emits the
  level-2 lowpass band without running the inverse wavelet. Useful
  for thumbnails and fast scrubs.
- **Container-driven I/O** — DNG metadata parse can be skipped on the
  fast path; raw input may be `mmap`-ed; output stream buffer is
  pre-faulted lazily on first use to reduce page-fault overhead.
- **Embedded encoder mode** with an arena allocator for ARM SoC
  targets that cannot afford per-frame malloc/free churn.

### Changed

- **Default wavelet levels: 2.** The fused encoder applies a 2-level
  wavelet by default (`FUSED_WAVELET_LEVELS=2`), producing files
  ~35% smaller than 1-level on clean content for ~3 dB raw-PSNR cost
  (45.6 dB vs 48.2 dB at Z8 ISO 64, q=3). Set `FUSED_WAVELET_LEVELS=1`
  at compile time for maximum-fidelity stills.
- **NEON auto-enabled on ARM64 builds.** Previously gated behind
  `-DNEON=1`. The scalar fallback is still selected on x86_64 and
  on ARM builds that disable NEON explicitly.
- **`gpr_tools` v2 flags** (already in 1.x-pre): `-D 1` enables
  noise-aware adaptive quantization; `-A 1` enables ANS entropy
  coding. Both default off, preserving v1.0 GPR-file compatibility.
- **Pipeline ring depths and stripe sizes** tuned via heuristics:
  default 128 stripe rows above 1200 band rows, 64 below; ring depth
  defaults to 3 (per `gpr_video_encoder_create`).

### Removed

- **3-level wavelet support.** Prototyped (commit `86de303`) and removed
  (commit `2b1c152`, ~1240 LOC). Visual-quality testing showed pronounced
  inverse-wavelet "comb" ringing on high-contrast edges. We exhausted
  the candidate fixes — lossless LL2 storage, per-level prescale tuning,
  HF-lossless storage — and confirmed the root cause is inherent to
  cascading the biorthogonal 5/3 inverse three times. Only a different
  wavelet basis (CDF 9/7) would fix it, which is a full codec rewrite.
  See `docs/operating-envelope.md` for the data and rationale.
- Roughly 370 lines of dead code paths in `fused_encode.c` removed
  after the fused-pass rewrite stabilized.
- Redundant frequency counting in Pass 1 (the counts were never used).

### Fixed

- **`fast_decode.c` sign-extension bug at 16-bit boundary** (commit
  `f1ba70a`). `fast_decode_lowpass` was casting big-endian 16-bit
  unsigned lowpass coefficients through `int16_t` before storing into
  the int32 `PIXEL` band; any value ≥ 32768 sign-extended to a large
  negative number. The 3-level wavelet's ~8× gain pushed level-2 LL
  coefficients regularly past that threshold (especially on the GD
  channel where `G1 = GS + GD`, `G2 = GS - GD` amplified the error),
  producing corrupt JPEG output. The serial decoder always read
  unsigned; `fast_decode.c` was the outlier. Fixed by reading as
  `uint16_t` and zero-extending.
- **int16 NEON filter overflow on 16-bit input** (commits `264f4cf`,
  `f5efb93`, `8b461b5`). The int16 fast-path NEON filter assumed
  14-bit input bounds; on 16-bit input (pixel formats 4/5),
  horizontal lowpass reached int16 boundary and vertical sums
  overflowed. The int16 vertical path was disabled outright; the
  horizontal int16 path is now conditional on `log_bits ≤ 14`.
  The int32 path was unrolled 2× to recover ~25% of the lost speed.
- **Fused encoder was emitting only highpass bands** (commit `bdeb3b3`).
  Pass 2 loops iterated bands 1..3, skipping LL entirely. Fixed by
  emitting LL with `FUSED_LL_DIVISOR=64` to bring 14/16-bit LL
  coefficients into the rANS alphabet.
- **Quality-table indexing in the fused encoder** (commit `3405287`).
  The encoder was reading entries 0..3 from the quality preset table;
  those slots are LL and level-2 coarsest divisors that barely change
  across quality presets. Fixed to read entries 7..9 (the finest level,
  which is what a single-level fused encoder actually emits). Result:
  3× smaller files at q=3 on clean Z8 content (17.6 MB → 5.8 MB
  before LL emission was added back).
- **`FAST_SINGLE_THREAD` actually disables threading** now (commit
  `7b554d5`). It was previously a no-op.
- **Windows build** — expat fallthrough, pthread guards, conditional
  `-lm` linking. Added a Windows CI workflow.
- **Static log curve tables** restored after a failed cross-platform
  consistency experiment.

### Performance

Measurements on M1 (8-core, 16 GB), Z8 45 MP sensor, quality 3, 2-level
wavelet, 24 fps target.

- **Fused encoder, single context, single 45 MP frame**: ~22 ms steady-state.
  This is the result of: parallel image unpack (4 threads), shared 4-channel
  unpack ring, NEON color conversion, 8-wide NEON vertical filter + fused
  quantize, NEON 4-wide horizontal highpass + lowpass, NEON zero-skip in
  frequency counting, division-free rANS encode with precomputed
  reciprocals + manual 4× unroll, and a TLS-reusable rANS decode buffer
  on the test path.
- **Sustained encode rate, single encoder, encoder-bound**: 29.76 fps,
  295 MB/s.
- **Sustained encode rate, dual encoder ping-pong, encoder-bound**:
  41.64 fps, 413 MB/s. **+40% over single encoder.**
- **Historical sustained pipeline simulation, 24 fps target with 200 MB/s
  simulated storage and periodic GC stalls**: 23.94-23.95 fps on both clean
  ISO 64 and noisy ISO 22800 content. 0 dropped frames across a 400-frame
  stress test. Current `.gvid` readiness uses `docs/LABS_TARGET_BENCH.md`.
- **File sizes (2-level wavelet, q=3, no rate control)**: 13.0 MB
  on Z8 ISO 64; 29.9 MB on Z8 ISO 22800. With rate control at 150 MB/s
  target, both stabilize to roughly 6.2 MB/frame.
- **Raw PSNR vs original Bayer**: 45.6 dB clean / 44.3 dB noisy at
  the default 2-level setting; 48.2 dB / 46.4 dB at 1-level for
  maximum-fidelity stills use.
- **Memory cost**: ~410 MB single encoder / ~820 MB dual at 45 MP,
  ring_depth=3.
- **Pass 1 (fused unpack + wavelet + quantize + freq count)** on the
  50 MP Z8 sensor: 15.8 ms → 7.0 ms after the shared-unpack ring
  landed (commit `38605f7`).
- **Rate controller convergence**: tracks within 7% of target above
  the per-content floor (~38 MB/s clean, ~100 MB/s noisy).

A78 estimate at 2.5× the M1's clock-for-clock budget: ~17 fps with
dual-encoder mode at 45 MP. The 50 MP × 24 fps × A78 envelope is
not yet hit on M1; remaining queued optimizations
(`FUSED_LOG_POLYNOMIAL=ON` cross-compile, ARM64 hand-asm unpack)
gate on real A78 measurement.

## [1.0.x] — historical

Original GoPro GPR release: VC-5 wavelet codec for Bayer raw stills in a
DNG-compatible container. CLI tooling via `gpr_tools`. Apache-2.0 / MIT
dual license. See pre-2.0 git history for details.

[2.0.0]: https://github.com/gopro/gpr/compare/v1.0.0...feature/raw-video
