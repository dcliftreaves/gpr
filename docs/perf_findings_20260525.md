# Playback perf pass — 2026-05-25

Sustained playback at 24 fps × UHD with the merged stack (CNN +
multi-level + decimate=2) currently averages **~26.1 fps**. This pass
identifies the next concrete bottleneck and what it is (and isn't)
worth doing about it.

## Baseline

Hardware: M1 Pro (MacBook 14"), macOS 15.7.7.

Command:

    ./tools/gpr2prores/gpr2prores \
      --meta-dng .../Z8Z_1330.dng \
      --cnn-backend mpsgraph \
      --ckpt .../F_ane_1x_weights_metal \
      --cnn-scale 1x --demosaic metal-bilinear --out-resolution uhd \
      --timing barn_sky_ml_hh2x2.mov out.mov

Steady-state per-frame (frames 4–23, 20 frames):

| stage    | ms   |
|----------|-----:|
| read     |  0.1 |
| decode   | 22.5 |
| cnn      | 34.7 |
| demosaic |  3.1 |
| write    |  0.1 |
| total (4-deep pipeline latency) | 142 |

**Effective fps = 26.18** (24 frames in 916 ms).

The slowest stage is the CNN at ~34.7 ms — pipelined steady-state
throughput cap is 1/34.7 ms = 28.8 fps. The 26.18 fps measured leaves
~10 % of the gap to overhead/serialization that is not on the CNN
critical path.

## Sample profile (`sample <pid> 8`, after warmup)

| thread                        | active samples | wait samples | self-time |
|-------------------------------|---------------:|-------------:|----------:|
| `gpr2prores.reader` (decode)  |            396 |          119 | 77 %      |
| `gpr2prores.cnn`              |             11 |          541 | 2 % encode / 97 % GPU wait |
| `gpr2prores.demosaic`         |             14 |           38 | 27 % active / 73 % GPU wait |

The CNN thread spends **97 %** of its wall time in
`MTLCommandBuffer waitUntilCompleted`. The MPSGraph encode itself is
~11 samples — already minimal. The CNN is **GPU compute-bound**, not
encode-bound.

## Per-stage GPU profile (`SUPERRES_PROFILE=1`, hybrid backend)

Hybrid backend exposes per-block GPU timing via `[cb commit; wait;
read GPUStartTime/EndTime]` between every stage:

| stage              | GPU ms |
|--------------------|-------:|
| unpack (A)         |  0.19  |
| G1 intro           |  0.00  |
| NAF enc0 C=16      |  6.37  |
| G2 down0           |  0.50  |
| NAF enc1 C=32      |  5.28  |
| G3 down1           |  0.27  |
| NAF enc2 C=64      |  9.58  |
| NAF dec0 C=64      |  9.92  |
| NAF dec1 C=32      |  5.14  |
| NAF dec2 C=16      |  6.03  |
| G7 head            |  0.97  |
| **sum**            | **44** |

(Hybrid backend is ~52 ms vs MPSGraph 34.7 ms — MPSGraph is the
production winner. Per-stage proportions transfer though: the four
NAF blocks at the wider C are the bulk of the cost.)

## Optimization candidates that did NOT pan out

### A. CoreML / ANE for the CNN

The CoreML mlpackage at `/tmp/F_ane_1x.mlpackage` (1×4×1384×2072 fp16
input) is intact. Pure CoreML inference timings (Python harness, 20
runs warm):

| compute units      | ms/frame | fps   |
|--------------------|---------:|------:|
| `ALL` (auto)       |   367.0  |  2.7  |
| `CPU_AND_GPU`      |    42.0  | 23.8  |
| `CPU_AND_NE` (ANE) |   113.8  |  8.8  |
| `CPU_ONLY`         |   288.4  |  3.5  |

For comparison, **MPSGraph on the same model is 34.5 ms** — already
22 % faster than CoreML+GPU, and 3.3× faster than CoreML+ANE. The ANE
is the wrong unit for this model on this hardware (likely because the
hourglass topology with NAFBlocks and PixelShuffle keeps falling off
the ANE's optimized op set and the slow-path eats the benefit).

Note: `ALL` (auto) at 367 ms is almost certainly CoreML thrashing the
graph between units (this is a documented gotcha — explicit `CPU_AND_GPU`
or `CPU_AND_NE` is always preferred over `ALL`).

**Outcome: no win available from routing to CoreML/ANE.** Keep
MPSGraph.

### B. Pipeline inbox capacity tuning

Hypothesis: maybe steady-state is limited by reader/decoder stalls
waiting for the CNN. New env vars `GPR2PRORES_CNN_INBOX`,
`GPR2PRORES_DEMOSAIC_INBOX`, `GPR2PRORES_WRITER_INBOX` were added to
tune the pipeline depth.

| cnn_inbox | demo_inbox | writer_inbox | fps   |
|----------:|-----------:|-------------:|------:|
| 2         | 2          | 4            | 25.98 |
| 4         | 2          | 4            | 25.90 |
| 4         | 4          | 8            | 25.70 |
| 6         | 2          | 4            | 26.06 |
| 8         | 2          | 4            | 25.72 |

Zero meaningful effect (run-to-run variance is larger than any signal).
Confirms the CNN is the throughput governor, not pipeline depth.

### C. Pre-compile MPSGraph to MPSGraphExecutable

Hypothesis: `MPSGraph encodeToCommandBuffer:feeds:` may be doing
per-frame specialization work that a once-compiled MPSGraphExecutable
would skip. Added `compileWithDevice:feeds:targetTensors:` at init and
switched the per-frame encode to `MPSGraphExecutable encodeToCommandBuffer:`.

A/B (3 trials each, 24-frame run):

| trial | plain MPSGraph fps | executable fps |
|------:|-------------------:|---------------:|
| 1     | 25.83              | 25.97          |
| 2     | 25.98              | 26.09          |
| 3     | 25.91              | 25.94          |
| mean  | **25.91**          | **26.00**      |

~+0.3 %. Within noise. PNG-of-frame-0 comparison shows bit-identical
output (max abs diff = 0). Kept as a defensive change (no harm, may
help slightly on cold first-frame timing).

## What's actually limiting throughput

The CNN is genuinely GPU compute-bound. At 34.5 ms/frame on M1 Pro's
G15X GPU, the breakdown is the four NAF blocks at the deepest
channels (C=64 enc2/dec0 ≈ 20 ms combined, C=32 enc1/dec1 ≈ 10 ms,
C=16 enc0/dec2 ≈ 12 ms). Anything that does not change one of these
will not move steady-state fps.

## Avenues that would actually move the needle (architecture-level)

None are in scope for this pass — all change either the model or the
bitstream:

1. **Smaller CNN width (w=12 or w=8)**. The hybrid kernels already
   scale; we'd need new weights. Expected: linear-ish reduction in
   GPU time (w=12 → ~25 ms, w=8 → ~17 ms). Quality cost unknown until
   retrained.
2. **Encode-time downscale to half-res, decode-time CNN at full
   spatial dims (no decimate=2 on input)**. Currently decimate=2
   already halves the spatial budget; we're at the floor for the
   current network.
3. **Replace the NAF-block conv1×1 → DW → conv1×1 sandwich with a
   lighter motif**. E.g. one residual block per scale instead of one
   block at C=2w. Requires retraining.
4. **Move the bicubic-baseline + combine + rebayer into the MPSGraph**
   itself (currently it's a separate Metal pass at the tail). Saves
   one command buffer commit-and-wait. Tiny win, maybe 0.5–1 ms.
5. **GPU-side input/output bridge** between CNN and demosaic. Already
   done for the CIRAWFilter path via `_bayerSharePool`. Metal-bilinear
   demosaic does its own CPU bridge; unifying could shave ~3 ms but
   that's the demosaic budget, not the CNN bottleneck.

## What's in this branch (`perf/profile-pass`)

- `GPR2PRORES_{CNN,DEMOSAIC,WRITER}_INBOX` env-var tunables on the
  pipeline inboxes (default behavior unchanged).
- `MPSGraphExecutable` pre-compile at SuperResMetal init, used by the
  MPSGraph backend encode (opt out with
  `GPR2PRORES_NO_EXEC_COMPILE=1`). Bit-identical output; no measurable
  steady-state win, defensive change.
- This findings document.

## Honest summary

Sustained playback is **CNN-GPU-bound**. The CNN already uses the
right backend on this hardware (MPSGraph beats CoreML+GPU by 22 %
and beats ANE by 3.3×). MPSGraph executable pre-compile is +0.3 %
(noise). Pipeline depth tuning is 0 %. **No 5 %+ win is available
without changing the model architecture or the bitstream.**
