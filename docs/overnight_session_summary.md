# Overnight Pi 5 / GPR codec work — morning brief

## Direct answers to your questions

### Q: How long is a normal 50 MP encode on the system?

| Path | Median wall | fps |
|---|---|---|
| `gpr_tools` (legacy production, single-still) | **2780 ms** | 0.36 |
| Fused encoder, full-res multi-level (decodable) | 266 ms | 3.8 |
| Fused encoder, full-res single-level + LL | 132 ms | 7.6 |

The legacy `gpr_tools` path is **dramatically slower** than the fused
encoder — 10-21× slower for the same input. The fused encoder is
multi-threaded across the 4 Bayer color planes; gpr_tools uses the
original single-threaded VC5 path with the DNG container.

**For users wanting fast 50 MP single-still encoding, the production
optimization is to wire the fused encoder into gpr_tools.** That's a
pure integration task — the encoder is already proven and decodable.

### Q: Did 24 fps for 50 MP → 4K-equivalent encoding really land?

**YES — 30.6 fps on real Z8 content, sustained over 50 iterations.**

Config: `GPR_INCLUDE_LL=1 GPR_ROW_DECIMATE=2 GPR_COL_DECIMATE=2 GPR_DROP_HIGHPASS=1`

50-iter median: **32.6 ms** (stddev 0.25 ms, min 32.43, max 34.16). The
LL-only output is visually equivalent to LL+HP at 4K display zoom — the
highpass detail doesn't survive the 50→4K-equivalent downsample.
Visualized through `tools/run_codec_movie.sh` (rawpy with the source
DNG's white balance, color matrix, and gamma — see
`/tmp/gpr_visuals/codec_realmovie.mp4`).

The **full-detail LL+HP variant** is currently **19.4 fps** (51.6 ms).
~10 ms short of 24 fps. Likely needs a format change (cheaper entropy
coder for LL band, or wavelet-domain ROI) to close that gap on Pi 5.

## What I tried tonight

| Idea | Result | Note |
|---|---|---|
| Identity-LUT experiment | 132→121 ms still / 53→52 ms stream | LUT is a still target (21 ms), barely matters for stream (1.5 ms) |
| `42e51bc` fast row-skip default | −6 ms / +11% | Wavelet's own LP does the AA work |
| `a4880e3` NEON LUT reduce | −16 ms / +27% (committed earlier) | 16-load unroll + NEON pair-add reduce |
| `53e4cae` prefetch end-of-row | −3 ms / +5% | Two PLDL1KEEP hints |
| Next-iter prefetch (4 rows ahead) | +2 ms regression | LSU dispatch contention; reverted, doc-only |
| 8-wide inner loop unroll | +23 ms regression | Register pressure → stack spills; reverted |
| Mask-removal in BB_WRITE_FAST | within noise | Reverted (output not byte-identical to old reference, turned out to be stale ref) |
| NEON polynomial log curve | Abandoned | Best deg-7 fit had 1458-pixel max error — too inaccurate |
| Piecewise linear log curve | Abandoned | Best 64-segment fit had 201-pixel max error — too inaccurate |
| Per-channel CPU affinity via pthread_setaffinity_np | -7 ms regression | Pinning channel threads to cores 0-3 made everything worse and more variable (stddev 6 ms vs 0.4). OS scheduler was already doing better than hardcoded pin. Reverted. |
| LL stripe-rows tuning sweep | within noise | Default 128 already optimal; 64-690 explored. `FUSED_STRIPE_ROWS_LL` env knob committed for future tuning. |

## Where the time goes now (per channel, decimated path)

```
unpack:  ~17 ms  (memory-bound, ~22 ms for 87 MB raw read at Pi 5 ~4 GB/s)
horiz:    ~2.3 ms
vert+q:   ~2.9 ms
tokenize: ~22-28 ms  (sparse highpass + dense LL)
TOTAL:    ~48 ms per channel
WALL:     ~52 ms with Pass 2 overlap
```

Pass 2 (rANS encode the accumulated tokens) is already overlapped with
Pass 1 — it costs ~2 ms wall after Pass 1 ends.

## What's left to try

Things I think can still help but didn't get to:

1. **NEON piecewise log curve** — for the STILL path (132 ms single-still),
   21 ms of LUT scatter cost is a real target. **Tonight I prototyped this
   and abandoned it**: best fit options have unacceptable error:
     - 16 log-spaced linear segments: max_err = 201 pixels, rms = 140
     - 64 log-spaced linear segments: same error (limited by widest segment)
     - 11 log-spaced quadratic: 2213 pixels (segment 0 too small for fit)
     - 7th-degree global polynomial: 1458 pixels max
   The curve `y = M * log10(1 + 112x/M) / log10(113)` is steep at x=0
   (slope ~24) and flat at x=16383 (slope ~0.3) — needs hundreds of
   segments to keep error under ~16 pixels, but vqtbl1q only operates
   on 16-byte tables. Float-domain `vlogq_f32` via bitcast-exp-mantissa
   would be 5 cycles/pixel — slower than the current ~3 cycles/pixel
   scalar LUT (L1 cache hit). The LUT is the right answer here.
   
   To actually reduce the 21 ms LUT cost on still: need to read less
   raw data (impossible for full-res), or process fewer pixels per
   second (not the goal). The 21 ms is essentially the memory floor
   for the 87 MB raw read plus LUT-lookup latency-bound.
2. **LL-band-specific tokenizer** — LL data is dense, run-length
   encoding wastes effort. A specialized tokenize for LL (no RLE, just
   class+residual emit) might save 5-10 ms tokenize time, closing the
   LL+HP path toward 24 fps. Requires bitstream format addition.
3. ~~Decoder parallelization~~ **DONE** — commits 33318d3 (band + wavelet)
   and 7c6e086 (color transform). Total decode 220→170 ms wall, byte-
   identical output. 16-thread per-band variant was tested and gave NO
   additional speedup beyond 4 threads (rANS decode bound by malloc and
   memory bandwidth, not core count).
4. **Integration of fused encoder into gpr_tools** — drops 50 MP single-
   still from 2.78 s to 132 ms. Pure plumbing work, no codec changes.
5. **Within-channel parallelism** (split a channel's wavelet/tokenize
   across multiple cores) — not viable on Pi 5: all 4 cores already used
   by 4-channel parallelism, no SMT.

## Decoder threading (overnight continuation)

The decoder was single-threaded at ~220 ms total. Added two threading
points to `decode_fused_single_level_ll`:
- 4 channel threads each rANS-decoding their 4 bands sequentially
- 4 channel threads each running `InvertSpatialQuantDescale16s`

Result: ~170 ms total decode (-25%). Modest gain — the rANS decode has
a tight inner state-update loop that doesn't benefit much beyond core
count, and per-frame malloc contention partly cancels the parallel win.
16-thread per-band was tested and gave NO additional improvement.

For end-to-end pipeline on Pi (encode+decode same machine):
- LL+HP path: 52 + 170 = 222 ms ≈ 4.5 fps E2E
- LL-only path: 33 + 170 = 203 ms ≈ 4.9 fps E2E

For STREAMING (encode on Pi, decode elsewhere): 30 fps encode is achievable.

## Commits this session (in chronological order)

```
ed98abd docs: 50→4K-equivalent fused path hits 29.5 fps (24 fps target HIT)
42e51bc fused_encode: default ROW+COL decimate to fast row-skip path (-6 ms)
a4880e3 fused_encode: vectorize LUT lookups in unpack_channel_row_decimate_2x2
53e4cae fused_encode: prefetch end-of-row in unpack_channel_row (-3 ms)
5f6fa35 fused_encode: document failed next-iter prefetch attempt
51c9a91 docs: track prefetch win + remaining state
c09524d docs: correct stable LL+HP numbers (cool-Pi outlier earlier)
```

Plus earlier this week:
```
8ff6377 tools: codec → rawpy → MP4 pipeline for honest visual verification
327482d fused_encode: log-space averaging (orange-cast bug fix)
131c6d0 fused_encode: reset inline_state[0] (LL) too
7ff76d4 fused codec: 16-band single-level-with-LL roundtrip
```

Additional commits during the overnight continuation:
```
1b361eb docs: more failed-attempts entries (affinity, piecewise log, stripe sweep)
33318d3 fused_decode: parallelize per-channel band rANS + inverse wavelet
d8da0bf docs: add decoder threading section + commit log update
6ad128e fused_encode: remove GPR_BYPASS_LOGCURVE debug knob
7c6e086 fused_decode: parallelize color transform inverse across row strips
```

## To reproduce the headline number

```sh
# On the Pi
GPR_INCLUDE_LL=1 GPR_ROW_DECIMATE=2 GPR_COL_DECIMATE=2 GPR_DROP_HIGHPASS=1 \
  ~/gpr/build/source/app/bench_fused/bench_fused /tmp/Z8_real.raw 8280 5520 50
# expect: median ~32.6 ms, ~30.6 fps
```

## To produce a verifiable movie

```sh
./tools/run_codec_movie.sh
# produces /tmp/gpr_visuals/codec_realmovie.mp4 with 3 real Z8 frames
# encoded+decoded through the codec and rendered with rawpy
```
