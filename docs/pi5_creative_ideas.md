# Pi 5 / Cortex-A76 — creative hardware-specific optimization ideas

Status of safe entropy-coding experiments after E1+E2:
- **E1** (post-pass freq increments): FLAT — reverted
- **E2** (skip normalize+build, cache encode tables): **NEGATIVE** (193ms vs 173ms baseline). Means normalize+build cost is essentially zero; pure inner-loop is the wall.

So the wall is the actual tokenize+rANS inner loops, not the table prep around them.

## Hardware inventory (BCM2712 / Cortex-A76)

- ARMv8.2-A with crypto extensions: **AES, SHA1, SHA2, PMULL, CRC32**
- NEON (Advanced SIMD), no SVE
- 4-wide superscalar OoO, 2× FP/ASIMD pipes
- 64 KB L1d (4-way), 64 KB L1i, 1 MB shared L2, no L3
- HW data prefetcher: handles strided forward; backward reads are SKETCHY
- Branch predictor: TAGE, ~good but mispredicts on bursty data-dep branches
- Cycles per op: NEON int add = 1, vmull = 3, vqtbl1q = 2, pmull = 2, aese = 2

## Hot loop anatomy (per coef in `jans_inline_row`)

At q=3, ~70% of coefs are 0. So:
- ~70% of iters: branch + `run++` (3-4 cycles, predicted)
- ~30% of iters: full tokenize (~25 cycles per nonzero)

Wall = `n_zeros × 3 + n_nonzeros × 25` ≈ `0.7N × 3 + 0.3N × 25 = 9.6N` cycles

If we eliminated 70% of zero iterations (NEON scan-ahead), wall → `0.3N × 25 = 7.5N` → 22% speedup, **~22 ms saved on tokenize**.

## Ideas ranked by expected ROI

### #1 — NEON scan-ahead for zero runs in tokenize
Load 16 coefs with `vld1q_s32 ×4`, test `vceqzq_s32 ×4`, combine with `vorrq + vmaxvq` to one scalar. If all 16 zero: `run += 16`, advance, restart. Else: find first nonzero idx via `clz`-style trick on a packed bitmask, process scalar from there.

**Cost to try**: 1-2 hours.
**Expected**: 10-25 ms reduction in tokenize (~6-15% wall).
**Risk**: NEON-scalar mode switch overhead on A76 — not huge but real.

### #2 — prfm at the rANS reverse-encode loop in emit_blob
`tokens[]` is read i = N−1 → 0 (backward), `enc[tokens[i]]` is indexed-load. HW stride prefetcher does NOT handle backward strides on A76. Add explicit `prfm pldl1keep, [tokens, i−32, lsl #1]` and a chained prefetch `prfm pldl2keep, [enc, sym, lsl #3]` for sym = tokens[i−16].

**Cost to try**: 30 minutes, one file.
**Expected**: 3-8 ms reduction (rANS scatter latency).
**Risk**: very low.

### #3 — NEON-batched rANS state update
4 interleaved rANS states already exist. Pack them into a `uint32x4_t`. All math (`q = x*rcp >> 32`, `mod = x − q*freq`, `state = (q<<14) + mod + cum_freq`) maps to NEON: `vmull_u32 + vshrn_n_u64 + vmls + vshl + vadd`. The renormalize loop (`while x >= x_max: emit byte, x >>= 8`) is the divergence problem — handle by NEON-compare to mask the lanes needing renorm, then scalar fallback for any set lane (typically ≤1).

**Cost to try**: 4-6 hours.
**Expected**: 15-30 ms reduction (rANS at ~30 ms today).
**Risk**: medium — renorm divergence may eat the gain.

### #4 — PMULL for unary / Golomb-Rice (if we switch entropy coder)
PMULL64 produces 128-bit polynomial product. The bit pattern `1 << k` for unary code of value k is `pmull(1, 1 << k)` trivially. More interesting: PMULL can compute "spread bits at given positions" which is the inverse of pdep/pext. If we move to bit-pack output of merged residuals, PMULL can fuse multiple tokens' bits with single-cycle latency.

**Cost to try**: 6-10 hours (depends on format change).
**Expected**: only matters if we switch to Golomb-Rice (E3).
**Risk**: only useful inside E3 path.

### #5 — Repurpose AES for entropy hashing
AES round is `SubBytes ∘ ShiftRows ∘ MixColumns ∘ XorKey`. It's a strong byte-permutation. Could be used to scramble token order before rANS so consecutive tokens have lower mutual information, reducing freq table effectiveness. But the freq table IS the win mechanism — scrambling DEFEATS compression. **No fit.**

### #6 — Bitbuf write fusion across multiple tokens
The current `bitbuf_write` is a 1-token-at-a-time `OR into 64-bit accum + drain 32 bits` operation. With NEON we could precompute 4 tokens' (value, bit_count) into a 128-bit reg, run a tiny prefix-sum on bit positions, then `vshlq_n_u64 + vorr` to merge them into the 64-bit accumulator with one drain.

**Cost**: 3-4 hours.
**Expected**: 5-10 ms saved.
**Risk**: low. But helps less if zero runs separate tokens.

### #7 — Software-pipelined LUT loads + NEON unpack (T2 from ffmpeg)
The unpack stage uses scalar log-curve LUT lookups interleaved with NEON. Software-pipelining the LUT loads (issue load for next iteration during current arithmetic) hides L1d latency. Unpack is 35-37 ms today.

**Cost**: 3-4 hours (assembly).
**Expected**: 4-8 ms saved.
**Risk**: low.

## Plan of attack

1. **Today**: try #2 (prfm — 30 min). Low risk, immediate measurement.
2. **Today**: try #1 (NEON zero-scan — 1-2h). Biggest potential single win.
3. **If #1 wins**: try #6 (bitbuf fusion) — complements #1 on dense regions.
4. **Stretch**: try #3 (NEON rANS). If it works, this is the biggest win on the planet.
5. **Long-tail**: #7 unpack pipelining for an extra 5-8 ms.
