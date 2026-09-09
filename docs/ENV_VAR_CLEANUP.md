# Environment variable cleanup — pre-spec contribution checklist

When GPR is ready to contribute back to GoPro's open-source codec (see
the project framing note), every env-var-controlled encoder/decoder
behavior needs to either:

1. Become a proper API parameter in the public header (visible in
   `gpr_parameters` / `vc5_encoder_parameters` / `FUSED_HEADER`).
2. Be moved into a private/dev-only namespace and documented as
   non-shippable.
3. Be removed.

This doc inventories every env var as of 2026-05-25, with proposed
disposition. **Most of these are debt against a clean spec contribution.**
Some are load-bearing for the calibration / exploration workflow and
need to be retained until that work is fully landed; others are dev
toggles that can be removed today.

## Encoder env vars

| Name | File | What it does | Proposed disposition |
|---|---|---|---|
| `FUSED_MULTI_LEVEL` | fused_encode.c:3480 | Selects 3-level wavelet (40 bands) vs single-level + LL (16 bands) | **Promote to API**: `gpr_encode_fused_create_with_mode(..., multi_level=1)`. Default to 1 (current PR #15 sets the fixture builder to use it). |
| `FUSED_MULTI_LEVEL_STREAMING` | fused_encode.c:3495 | Streams level-2/3 inline with level-1 vs split-pass | Dev-only. Document as `GPR_DEV_*`. |
| `FUSED_INLINE_TOKENIZE` | fused_encode.c:3466 | Inline vs split tokenize for the rANS encoder | Dev-only. |
| `GPR_INCLUDE_LL` | fused_encode.c:3075 | In single-level mode, emit a 16-band stream with LL preserved (instead of 12-band without LL) | **Promote to API** OR make the codec auto-include LL whenever single-level is selected. Currently load-bearing for the single-ll path. |
| `GPR_COL_DECIMATE`, `GPR_ROW_DECIMATE` | fused_encode.c:3066, 3068 | 2× channel-space decimation per axis | **Promote to API**: `gpr_encode_fused_create_with_dims(..., decimate=2)`. Header field `hdr.decimate` already records it (PR #11). |
| `GPR_QUANT_OVERRIDE` | fused_encode.c:242 | Per-subband quant divisor override (calibration knob) | **Dev-only**. Calibration tool, not for shipped code. Document as `GPR_DEV_QUANT_OVERRIDE` or remove entirely once the q=11 preset and any future CNN-aware presets are merged. |
| `GPR_DROP_HIGHPASS` | fused_encode.c:2229 (and others) | Zero all highpass bands — produces LL-only stream | Dev-only. Useful for "LL-only fast decode" testing. Document. |
| `GPR_DECIMATE_AA`, `GPR_AA_LUMA_ONLY` | fused_encode.c:2219, 2224 | Anti-alias filter on decimation pass | **Promote to API** if the AA filter ships; otherwise dev-only. |
| `FUSED_FUSE_LP_OFF`, `FUSED_LUMA_FUSED_OFF` | fused_encode.c multiple | Internal fast-path toggles | Dev-only. Used during the FUSED rewrite for A/B testing; should be removed entirely now that the fast path is the default. |
| `FUSED_USE_ASM` | fused_encode.c:1148 | Use ARM64 asm path vs C reference | Dev-only. Could be removed (asm should always win on ARM64). |
| `FUSED_PIN` / `GPR_PIN_AFFINITY` | fused_encode.c:55-56 | Thread affinity hints | Dev-only. |
| `GPR_DENOISE_AUTO` | gpr.cpp denoise path | Auto-flip wavelet denoise on DNGs with NoiseProfile | **Promote to API**: `gpr_parameters.denoise_auto`. Default to current behavior (1). |
| `GPR_BENCH_DENOISE`, `GPR_BENCH_NOISE_SCALE`, `GPR_BENCH_NOISE_OFFSET`, `GPR_BENCH_DUMP`, `GPR_BENCH_WRITE_ALL`, `GPR_BENCH_GVID_COALESCE_PREFIX` | bench_fused.c | Benchmark-only knobs in the test app | Keep — bench_fused is a dev tool, not part of the shipped codec. `GPR_BENCH_GVID_COALESCE_PREFIX` is a receipt-disambiguated write-layout probe, not a production API. |
| `Q162_DUMP` | encoder.c (was instrumentation, removed in PR #20) | Per-band coefficient histogram dumper | Removed already; mentioned here so future agents don't reinstate it. |

Rejected target probes:

- `JANS_INLINE_FUSED_HARDT`: fused hard highpass dead-zone thresholding into
  inline jANS tokenization. It was byte-identical on local/Pi receipts, but
  slower on Mission 1 12MP Pi A/B runs, so the live env hook was removed.

## Decoder env vars

| Name | File | What it does | Proposed disposition |
|---|---|---|---|
| `GPR_DECODE_TIMING` | fused_decode.c | Print per-stage timing | Keep — dev tool. |
| `GPR_DECODE_LL_ONLY` | fused_decode.c | Discard HP bands during decode (fast path) | **Promote to API** as a decode-mode flag. Used by FFmpeg / fast preview paths. |
| `GPR_DECODE_HPSYNTH` | fused_decode.c | Synthesize HP from LL gradients when bands are zero | Keep dev-only; this is an experimental polish path. |
| `GPR_DECODE_FUSED_STREAM_STRIPS` | fused_stream_decode.c | Tune row-strip parallelism | Dev-only. |
| `GPR_QUANT_OVERRIDE` | fused_decode.c | Mirror of encoder's override; must match | Same disposition as encoder side. |
| `GPR_TIMING_TOLERANCE` | test_capabilities.py | Loosen ms ceilings in Debug builds | Keep — test-only. |

## SDK-side (gpr_tools / gpr_sdk)

The legacy `gpr_tools` accepts CLI flags (`--ANS`, `--DenoiseAuto`, `--noise-strength`, etc.). Those are already proper API; nothing to clean up except documenting them in a unified manpage when we get to the spec contribution.

## Action plan (when ready)

This cleanup is **not on the critical path** for the GoPro contribution
exploration phase. Most env vars are load-bearing for calibration /
exploration work that's still active. The right time to do this pass:

1. After the multi-level codec is locked as the default and not changing
2. After the CNN-aware quant presets (q=11, possibly more) are merged
3. After any further BIBO_1x / BIBO_2x retraining experiments
4. Before any pre-spec doc work that lists encoder behaviors

Estimated effort when the time comes: ~half day for the env-vars-to-API
promotions (FUSED_MULTI_LEVEL, GPR_COL_DECIMATE, GPR_ROW_DECIMATE,
GPR_INCLUDE_LL, GPR_DECODE_LL_ONLY, GPR_DENOISE_AUTO). The dev-only
toggles are a half-day to namespace under `GPR_DEV_*` or remove.

## Why this doc exists

Agents working on this codebase have short context windows. Without this
file, an agent that lands a env-var-cleanup commit would have no way to
know which knobs are load-bearing for ongoing calibration work and which
can be removed safely. This file is the durable memory.
