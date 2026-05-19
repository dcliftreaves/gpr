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

## Ablation breakdown of tokenize wall (Pi 6.6.51, post-P3)

Phase=N runs jans_inline_row with parts of the nonzero body conditionally
disabled, then runs emit_blob normally (token_count=0 ⇒ rANS skipped):

| Phase | Body executed | Wall ms | Δ vs prev |
|---|---|---|---|
| 1 | zero scan + abs(val) only | 86 | floor |
| 2 | + class lookups (run_to_class + mag_to_class) | 94 | +8 |
| 3 | + freq[sym]++ | 101 | +7 |
| 4 | + tokens[]= write **and the rANS encode in emit_blob** | 150 | **+49** |
| 5 | + bitbuf_write of merged residuals (= full) | 182 | **+32** |

Therefore on textured Z8 at q=3 the wall is:
- ~86 ms unavoidable scan + abs floor
- ~30 ms rANS encode in emit_blob (after P3)
- ~30 ms bitbuf_write of merged residuals
- ~15 ms class lookups + freq[]++ + tokens[]= store

This kills "just cleverly skim zeros" — the 86 ms floor IS the iteration cost
on textured data. The two big targets above 86 ms are rANS encode and
bitbuf_write.

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

### P1 — prfm hints in rANS reverse-encode loop
**Result: FLAT/SLIGHT NEGATIVE**. Added explicit `__builtin_prefetch` for `tokens[i-32]` and chained `enc[tokens[i-16]]` in the 4-way unrolled rANS body. Tight A/B: −1.5 ms (regression). HW stride prefetcher on A76 evidently handles even backward tokens[] reads within the working set. Reverted.

### P2 — NEON zero-skim in tokenize
**Result: NEGATIVE (+5 ms)**. After hitting a zero, scan-ahead 4 lanes via `vld1q_s32 + vmaxvq_u32` to skip all-zero chunks. The cross-lane reduce (~7 cycles) costs more on textured Z8 than it earns — zero-clusters between nonzeros are short. P2v2 scalar 64-bit pair-probe variant: +3 ms (also negative, less bad). Both reverted.

### Ablation (env-gated GPR_TOKEN_PHASE)
Critical methodology step: added a phase-controlled bypass of work inside `jans_inline_row` body to attribute time to specific operations. See the ablation table above. This identified bitbuf_write as ~32 ms/ch wall — leading to P3.

### P3 — BITBUF locals across jans_inline_row (commit 53fd870)
**Result: WIN −20 ms wall (180→160 ms)**. Hoisted `bb->accum / accum_bits / byte_pos` into row-local registers via a `BB_WRITE_FAST` macro. Previously each bitbuf_write call read those fields from memory, ORed in new bits, and wrote them back — forming a per-call serial RMW chain through L1d. With locals the compiler keeps them in registers across all ~1.6M calls per channel. Also drops the dead `if (bits==0)` and `bits>=32` branches since neither triggers in the hot path. **Byte-identical output.**

### P4 — packed-LDR enc loads + 8-way unroll on rANS encode
**Result: marginal (~1-2 ms, within noise)**. Forced `memcpy`-style 8-byte loads of `JANS_ENC_ENTRY` (compiler now emits `ldr x` + bit-extracts instead of 3 separate `ldrh/ldrh/ldr`), then 8-way unrolled the 4-way state machine (2 rounds per loop iteration). The asm IS cleaner (12 loads → 4 per 4-token block) but throughput-limited elsewhere; A76 had enough OoO headroom that load count wasn't the bottleneck. Reverted.

## Session result

Wall time: **180 → 162 ms** (committed P3 only). ~10 ms repeatable improvement on Z8 50 MP RGGB q=3, byte-identical output. 5.8 → 6.2 fps. Target remains 42 ms (24 fps); the remaining gap is unreachable without format change (E3 Golomb-Rice or E4 raw bands + LZ4) or fundamentally different architecture (pipeline frames, offload).


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
