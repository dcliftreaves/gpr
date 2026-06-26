# Raw Video Pipeline — Follow-Up Items

**Status: 2026-05-12.** 2-level wavelet shipping default + dual-encoder ping-pong landed. 3-level prototype was removed after failing visual-quality testing; only a different wavelet basis would fix it. Parking lot for everything else below.

**Current repo status: 2026-06-15.** This file is an archival raw-video parking
lot, not the release readiness source of truth. Current production status,
receipts, and blockers live in `README.md`, `docs/FULL_PIPELINE_MATRIX.md`,
`docs/VIDEO_STATUS.md`, `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md`, and
`tests/quality_gates/audit_production_readiness.py`.

## Historical raw-video blockers

As of 2026-05-12, the raw-video pipeline encode -> decode ->
image-reconstruction was believed to sustain 24 fps × 45 MP under the older
storage model. That statement is historical. It does not cover newer
2K/4K/8K raw target perceptual proxy work, the current `.gvid` Labs proxy
receipts, or the Mission 1 hardware receipt still needed for firmware
readiness.

## Compute speed for A78 24 fps × 50 MP

**Status update (2026-05-12):** dual-encoder mode (commit `9b9ab0a`) lifted M1 sustained fps from ~30 → ~42 on Z8 45 MP at 2-level (+40%). A78 estimate at 2.5× M1 is ~17 fps with dual-encoder — fits 45 MP comfortably, tight at 50 MP. Remaining gap to 50 MP × 24 fps × A78 is now blocked on A78-specific silicon wins.

| Lever | Status | Expected impact |
|---|---|---|
| `FUSED_LOG_POLYNOMIAL` compile flag (`53e4777`) | Implemented, measured and rejected for the current Pi 5 half-res Labs path on 2026-06-15 | Slower than LUT/default on normal write-all output; keep default OFF unless a new target-specific receipt proves otherwise |
| **2-level wavelet (default, `301e4a0`)** | **Landed.** 35% size reduction vs 1-level; PSNR 45.6 dB raw clean | Smaller output → faster ANS + lower writer pressure |
| **Dual-encoder ping-pong (`9b9ab0a`)** | **Landed (opt-in via `gpr_video_encoder_create_dual`).** | **+40% M1 throughput**; expect same or better on A78 |
| 3-level wavelet | **Tried, removed (`2b1c152`).** Visible inverse-wavelet ringing on high-contrast edges. Verified not fixable via quantization, prescale, or lossless storage — inherent to cascading the biorthogonal 5/3 inverse three times. Only fix is a different wavelet basis (full codec rewrite). | (deleted) |
| `vld2q` + branchless clip in unpack | **Already in place** (commit `38605f7`). | n/a (done) |
| Direct lane access (avoid temp arrays) in unpack | Tried; slower on M1 (compiler does store-load via forwarding). Reverted. | n/a |
| Conditional int16 vertical filter for 14-bit (`bc52f9b`) | Landed | ~7% on 14-bit content |
| ARM64 hand-tuned assembly for the removed shared-unpack producer path (`8f658f4`) | Removed from the production source after Pi 5 target regressions | Historical result: M1 within 1% and no durable A76 win |

## Done since the original parking-lot

- **Encoder API: fatal-writer + force-cancel** (`029ed4f`) — writer return <0 aborts cleanly, `gpr_video_encoder_cancel()` for caller-driven stop, destroy() skips flush on abort. Covered by `test_video_encoder_abort`.
- **Format header versioning policy** (`dc63e91`) — v1 forward-compat rules documented in `gpr_video_format.h`.
- **`vc5_decoder/fast_decode.c` audit** (no commit, 2026-05-12) — clean. No further sign-extension bugs beyond the one fixed at `f1ba70a`.
- **Full encode → container → reader → decode integration test** (`9bbb5c7`) — `test_video_full_chain.c`. Caught a documented frame_tag-must-be-sequential gotcha during development.
- **Visual quality at RC-limited operating points** (`4d7bea0`) — assessed at `quant_scale` ∈ {1..16}. No cliff; recommend soft cap at 8, hard cap at 16. See `docs/rc-limited-quality.md`.
- **q ≥ 6 noisy roundtrip bug** — not reproducible under current 2-level default (inline_mode=0 path doesn't emit stripe-format magic). Walker fragility remains a latent risk if inline_mode + 1-level is ever re-enabled.

## Known minor issues (not blocking ship)

1. **Speed regression from int16 NEON revert (~25%)** — reverted for correctness on 16-bit input. Partially recovered with 8-wide int32 unroll (`1ae5d5d`). Conditional int16 path for 14-bit-only input would buy ~3-5 ms M1.

2. **Quality plateau at PSNR ~48 dB** — LL quantizer (`FUSED_LL_DIVISOR=64`) caps reconstruction quality. Going above q=3 doesn't move the needle. A different (wider-bitwidth lossless) LL would change this; see 3-level investigation for why we didn't pursue.

3. **q ≥ 6 walker latent risk** — if inline_mode is ever re-enabled (sub-6-core path or `FUSED_INLINE_TOKENIZE=1`), `probe_band_bytes` in `test_video_full_roundtrip.c` can mis-read rANS payloads that start with `0xFFFFFFFF`. Fix: add lookahead validation. Not reachable under current defaults.

## Test/validation gaps

1. **No long-duration thermal/sustained test** — 400-frame stress (~16 s) passes; haven't tested 10+ minutes. Needs A78 hardware to test thermals properly.

## Documentation

- `docs/operating-envelope.md` — measured PSNR/bitrate/storage tradeoffs
- `docs/rc-limited-quality.md` — visual quality at high `quant_scale`
- `docs/v2-migration-guide.md` — upgrading from stills-only GPR
- `docs/followups.md` — this file

Branch `feature/raw-video` is shippable. The remaining items above are either
A78-hardware-gated (thermal, hand-asm unpack) or speed-optional (int16 14-bit
path) - none block 2.0. The log-polynomial lead is no longer queued for the
current Labs half-res path because the 2026-06-15 Pi 5 probe was slower than
the LUT/default path.
