# Pi 5 optimization log (Cortex-A76, kernel 6.12.87)

## Baseline / target

- Hardware: Raspberry Pi 5, Cortex-A76 quad-core @ 2.4 GHz, 64 KB L1d / 1 MB shared L2, LPDDR4x ~10 GB/s
- Workload: 50 MP Z8 raw Bayer (8280×5520), q=3, RGGB, single-level
- Target: 24 fps = **42 ms/frame**
- Baseline at session start (kernel 6.6.51): **70 ms** / 14 fps
- Baseline after auto-upgrade to kernel 6.12.87: **170 ms** / 5.9 fps — 2.4× regression, root cause unclear
- Current (after this session's commits): **163.8 ms** / 6.10 fps

## Approaches that worked on Pi (kept)

| Commit | Pi delta | What |
|---|---|---|
| `2a917ca` | −5 ms | Pack `{freq, cum_freq, rcp_freq}` into per-symbol entry — one 8 B load per rANS token instead of three scattered |
| `0144379` | −0.5 ms | Hoist `s->table.freq` + `&s->bb` to function-local pointers in `jans_inline_row` |
| `58a9e25` | −1.2 ms | Pre-baked `sym_run_bits` / `sym_total_bits` LUTs — eliminates one int load + add per nonzero coef |
| `c9c37e2` | −1 ms | 8-wide vertical filter (ported from abandoned worktree) |
| `bc10841` | −0.5 ms | Force-inline `horizontal_filter` |
| `53fd870` | **−20 ms** | Hoist BITBUF accum/accum_bits/byte_pos to row-locals via `BB_WRITE_FAST` macro — breaks per-call RMW dependency through memory. Big single win. |

## Approaches that failed on Pi (reverted)

| Approach | Pi result | Why it failed |
|---|---|---|
| `FUSED_PRODUCER_UNPACK=1` (shared-unpack ring) | **2.6× SLOWER** (188 ms) | Doubles memory traffic; LPDDR4x can't absorb |
| Leader-rotation unpack pool | **1.25× SLOWER** (90 ms) | Serializes unpack across rows |
| Stripe-parallel pass1 | **1.4× SLOWER** | 384 KB stripe working set vs 64 KB L1d |
| 16-wide unpack unroll | regression | Register spill |
| NEON `vld2q` horizontal filter | regression | Shuffles weren't the bottleneck |
| NEON zero-skip in `jans_inline_row` | flat | A76 branch predictor already cheap on val==0 |
| Prefetch raw rows | flat | HW stride prefetcher covers it |
| Packed `sym_info` (run_bits, mag_bits) | regression | Compiler was already optimizing small const tables |
| `uint8` versions of run/mag_class_min/bits | regression | `ldrb` scheduling worse than `ldr` here |
| Hoist all `.rodata` table pointers to locals | regression | Interfered with reg allocation |
| Remove redundant `mb` load via `tb−1` | regression | Made dep chain longer (parallel loads beat scalar sub) |
| MALLOC_ARENA_MAX=1 | flat | Not a libc issue |

## Current open hot regions (perf on Pi 6.12)

- `jans_inline_row` — 43%
- `pass1_channel_thread` (includes inlined unpack + horiz) — 24%
- `jans_inline_emit_blob` (rANS encode) — 22%
- `vertical_filter_quantize_row` — 7%

## Key revelation (2026-05-19)

**Tokenize is 60% of the work**, not unpack. Earlier session readings showing
21–22 % were misread or from cleaner inputs. On real-world textured Z8 50 MP
at q=3 on Pi 6.6.51 (fresh OS, no Docker/GUI, performance governor):

| Stage           | Per-channel ms |
|---              |---             |
| unpack          | 48             |
| horiz           | 11             |
| vert + quant    | 13             |
| **tokenize**    | **105**        |
| total / channel | 177 (= wall)   |

Hardware floor probe confirms 24 fps (42 ms) budget:
- I/O alone (read 91 MB + write ~17 MB output): 13 ms
- I/O + NEON deinterleave + clip: 21 ms
- I/O + log curve unpack: 23 ms
- (est) + wavelet horiz + vert + quant: ~42 ms — right at the budget
- Current code with entropy: 173 ms — 4× over

**The wall is the entropy coder, not the wavelet or unpack.** All four
channels' wavelet+quant comfortably fits in budget; rANS-with-adaptive-freq
+ run-length encoding does not.

## Plan: entropy-coding speedup experiments (in order)

Each preserves byte identity OR documents the bitstream change.
Each gets a real attempt with measurement on Pi before moving on.

### E1. Eliminate inline `freq[sym]++` — do it as a post-pass over `tokens[]`
- Skip the random-access freq increment in the hot tokenize loop.
- After all coefs in a stripe are tokenized, scan `tokens[]` linearly once,
  populating freq[] in cache-friendly sequential order.
- Saves ~3 cycles per nonzero × ~3.5 M nonzeros per channel = ~4 ms.
- Byte-identical (freq table is the same value at finalize).
- Risk: low.

### E2. Static frequency table (skip both inline `freq[sym]++` AND `normalize_freq`/`build_encode_tables`)
- Pre-compute a representative freq distribution from one calibration encode.
- Bake it into the codec; skip per-stripe freq build entirely.
- Bitstream: no freq table in blob (smaller header) — header version change.
- Speed: cuts ~30–50 % of tokenize cost.
- Risk: medium (compression ratio loss if static table mismatches real content;
  measure on representative Z8 / X2D inputs).

### E3. Replace rANS-with-adaptive-freq with Golomb-Rice (or static-Huffman)
- Golomb-Rice: unary `q` + `k` raw bits per coef. No freq table at all.
- Inner loop: branch-free encode in ~5 cycles per coef.
- Bitstream: full format change.
- Speed: ~5–10× faster on tokenize.
- Risk: bigger format break; compression ratio ~10–15 % worse.

### E4. Skip entropy entirely — emit quantized wavelet bands raw
- Write quantized coefs as packed bitstream (no run-length, no rANS).
- Optionally wrap whole frame in LZ4 (which is single-threaded ~3 GB/s).
- Bitstream: full format change.
- Speed: tokenize gone (~105 ms → ~5 ms).
- Risk: largest format break; output ~2× larger.

## Execution log

### E1 — eliminate inline freq[sym]++ via post-pass linear scan
**Result: FLAT** (176-178 ms vs 173-176 baseline). The linear post-pass over tokens[] cost roughly what the inline increment saved. Reverted.

### E2 — static freq table (skip normalize_freq + build_encode_tables)
**Result: NEGATIVE (193 ms vs 173 ms baseline)**. Bypassed per-blob `normalize_freq + build_encode_tables`, used a single cached table built once. Tokenize went 101→112 ms/ch — the per-emit memcpy of the static `JANS_TABLE` into `s->table` costs MORE than the build it replaces.

Key inference: `normalize_freq + build_encode_tables` cost is essentially **zero**. The 173 ms wall is the actual `jans_inline_row` (tokenize) and `jans_inline_emit_blob` rANS core loops. Reverted. **Kills E3 as well if its only motivation was skipping table build.** Static-freq codecs only win if combined with a fundamentally cheaper symbol encode (Golomb-Rice).

See `pi5_creative_ideas.md` for the next round of Pi-specific ideas.


## ffmpeg techniques applied / available

T1 (`tbl`-based gather in NEON regs): N/A — 32 KB log curve doesn't fit, byte-identity requirement.
T2 (software-pipelined LUT load + NEON): planned for unpack asm.
T3 (`.p2align 4` on backward branches): already done by clang at -O3.
T4 (ldp + tbl instead of vld2q): tried earlier, regression on Pi.
T5 (ldp-pair scalar loads): planned for unpack asm.
T6 (prfm at row boundaries only): tried, flat.
T7 (orr+lsl bit-packing for output): not yet applied — could help in `jans_inline_row` merged-write step.
T8 (keep rANS as scalar GPR): confirmed by ffmpeg cabac.h — already this way.

## Notes on the 6.12 kernel regression

Same source + flags, kernel 6.6.51 → 6.12.87 caused **2.4× slowdown** specifically in inline-tokenize path (`jans_inline_row` + `jans_inline_emit_blob`). Multi-level path (split-mode tokenize) saw NO regression. Tried disabling NUMA fake nodes, mempolicy interleave, sched autogroup, spectre mitigations — no effect.

Reverting to 6.6 via apt-managed downgrade was not attempted (two bricks via raw kernel image swap; bootloader EEPROM likely tied to 6.12). Path forward is to either: (a) accept 6.12 baseline and squeeze what's available, (b) controlled `apt-get install linux-image-6.6.51+rpt-rpi-2712` reinstall with proper postinst hook, or (c) move to a different platform.
