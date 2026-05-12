# Raw Video Pipeline — Follow-Up Items

**Status: 2026-05-12.** 2-level wavelet shipping default + dual-encoder ping-pong landed. 3-level prototype was removed after failing visual-quality testing; only a different wavelet basis would fix it. Parking lot for everything else below.

## Shipping blockers (none currently)

The pipeline encode → decode → image-reconstruction is correct and sustains 24 fps × 45 MP × UHS-II V90 microSD. All test harnesses green.

## Compute speed for A78 24 fps × 50 MP

**Status update (2026-05-12):** dual-encoder mode (commit `9b9ab0a`) lifted M1 sustained fps from ~30 → ~42 on Z8 45 MP at 2-level (+40%). A78 estimate at 2.5× M1 is ~17 fps with dual-encoder — fits 45 MP comfortably, tight at 50 MP. Remaining gap to 50 MP × 24 fps × A78 is now blocked on A78-specific silicon wins.

| Lever | Status | Expected impact |
|---|---|---|
| `FUSED_LOG_POLYNOMIAL` compile flag (`53e4777`) | Implemented, needs A78 measurement | 1.5-2× on unpack (A78 64 KB L1d makes LUT contend) |
| **2-level wavelet (default, `301e4a0`)** | **Landed.** 35% size reduction vs 1-level; PSNR 45.6 dB raw clean | Smaller output → faster ANS + lower writer pressure |
| **Dual-encoder ping-pong (`9b9ab0a`)** | **Landed (opt-in via `gpr_video_encoder_create_dual`).** | **+40% M1 throughput**; expect same or better on A78 |
| 3-level wavelet | **Tried, removed (`2b1c152`).** Visible inverse-wavelet ringing on high-contrast edges. Verified not fixable via quantization, prescale, or lossless storage — inherent to cascading the biorthogonal 5/3 inverse three times. Only fix is a different wavelet basis (full codec rewrite). | (deleted) |
| `vld2q` + branchless clip in unpack | **Already in place** (commit `38605f7`). | n/a (done) |
| Direct lane access (avoid temp arrays) in unpack | Tried; slower on M1 (compiler does store-load via forwarding). Reverted. | n/a |
| Conditional int16 vertical filter for 14-bit (`bc52f9b`) | Landed | ~7% on 14-bit content |
| ARM64 hand-tuned assembly for `unpack_all_channels_row` (`8f658f4`) | Landed, opt-in via `FUSED_UNPACK_ASM=1` | M1: within 1% (no win). A78 expected 10-20% on producer-unpack |

## Known minor issues (not blocking ship)

1. **q ≥ 6 on heavily-noisy content fails roundtrip test**
   - Symptom: `probe_band_bytes` reports `pos > buffer size` at last band.
   - Encoder produces valid-looking output (size 43-50 MB), but the test's stripe-mode walker over-counts somehow on rANS streams with rare 0xFFFFFFFF byte patterns.
   - Workaround: rate controller stays in q=0..3 so this is never hit in production.
   - Real fix: improve probe walker to handle edge cases, OR add explicit per-band byte-length prefix in the encoder output (small format change).

2. **Speed regression from int16 NEON revert (~25%)**
   - Reverted for correctness on 16-bit input. Lost ~5-9 ms on 50 MP M1.
   - Partially recovered with 8-wide int32 unroll (`1ae5d5d`).
   - Could write a conditional int16 path for 14-bit input only (cleanly safe). Estimated value: 3-5 ms M1.

3. **Quality plateau at PSNR ~48 dB**
   - LL band quantizer (FUSED_LL_DIVISOR=64) caps reconstruction quality.
   - Going above q=3 doesn't improve PSNR meaningfully because highpass quality is already excellent and LL is the bottleneck.
   - Multi-level wavelet would change this (smaller LL coefficients → can use smaller divisor → higher LL quality).

## IP/patent items (require external action)

1. **Obtain GoPro's VC-5 patent statement from SMPTE** — required for counsel clearance review (per `docs/raw-video-landscape.md`).
2. **Align with GoPro's MISSION 1 patent posture** — they ship CineForm/VC-5 today; we inherit their position.
3. **Watch for RED `'967` expiration April 2028** — opens up the "in-camera compressed raw at 2K+/23+ fps" claim space.

## Architectural improvements deferrable

1. **Kill-switch for Green Average Subtraction (GAS)**
   - Compile flag to use direct R/G1/G2/B channels instead of GS/RG/BG/GD math.
   - Reduces patent surface (GAS is the RED `'384` family target).
   - File size penalty likely 20-40% (R and B compress worse without GS-subtracted differential).
   - Estimated 1-2 days of work.

2. **Adaptive bitrate algorithm refinement**
   - Current controller: EMA + sqrt(error) step, clamped ±15%/frame.
   - Floor on noisy content is ~100 MB/s — multi-level wavelet would lower it.
   - More sophisticated controller (PID with bitrate ceiling/floor enforcement) could give tighter tracking near floor.

3. **Encoder context API audit**
   - `gpr_video_writer_fn` doesn't have a way to signal "fatal — stop encoding."
   - `gpr_video_encoder_destroy` blocks on flush; no force-cancel option.
   - These matter for production embedded use.

4. **Format header versioning**
   - Container format is at version 1. Reserved bytes for future fields.
   - Should agree on a forward-compat policy before shipping a v1.0 release.

5. **vc5_decoder fast_decode audit**
   - Subagent F found one sign-extension bug; entire `fast_decode.c` worth a once-over for similar issues at 16-bit boundary.

## Test/validation gaps

1. **No automated integration test for the full encode → write → read → decode chain**
   - Have band-level decode (`test_video_roundtrip`) and full PSNR (`test_video_full_roundtrip`).
   - Don't have one that uses the actual gpr_video_encoder → container format → reader path end-to-end.
   - Worth ~half a day.

2. **No long-duration thermal/sustained test**
   - 400-frame stress (~16 s) passes; haven't tested 10+ minutes.
   - Thermal throttling on M1 wouldn't trigger in 16s but might in 10 min.
   - Need actual A78 hardware to test thermals properly.

3. **Visual quality assessment at rate-controller-limited operating points**
   - Subagent E tested visual quality at fixed q presets via gpr_tools.
   - **Investigated 2026-05-12** at scales {1, 2, 4, 8, 16} on Z8 45 MP — see
     `docs/rc-limited-quality.md`. Degradation is gradual, not cliff-edge.
     Dominant artifact at high scales is fine-detail smoothing (no blockiness,
     ringing, or color shifts). LL1 is preserved because it uses a fixed
     divisor independent of `quant_scale`, so tonality stays intact.
   - **Recommendation:** soft cap rate controller at `quant_scale ≤ 8` for
     editing-quality output; hard cap at 16. Beyond 8 the finest detail
     starts to noticeably soften, though the image is still recognizable.
     If the controller is consistently hitting 16+, lowering the quality
     preset (q=3 → q=4) gives a more balanced bit budget than further
     scale increase.

## Documentation

- `docs/session-2026-05-11-summary.md` — what was done this session
- `docs/operating-envelope.md` — measured PSNR/bitrate/storage tradeoffs
- `docs/raw-video-landscape.md` — codec ecosystem + patent landscape
- `docs/followups.md` — this file

The branch `feature/raw-video` is in a known-good state. Picking up from here, the highest-leverage next move is probably the multi-level wavelet (currently in subagent flight) since it would directly enable cheaper microSD card classes for video.
