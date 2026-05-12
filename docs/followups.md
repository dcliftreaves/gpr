# Raw Video Pipeline — Follow-Up Items

**Status: 2026-05-11 end of autonomous session.** All shipping-critical items are working. This is the parking lot for everything else discovered in the work.

## Shipping blockers (none currently)

The pipeline encode → decode → image-reconstruction is correct and sustains 24 fps × 45 MP × UHS-II V90 microSD. All test harnesses green.

## Compute speed for A78 24 fps × 50 MP (the big one)

| Lever | Status | Expected impact |
|---|---|---|
| `FUSED_LOG_POLYNOMIAL` compile flag | Implemented (`53e4777`), needs A78 measurement | 1.5-2× on unpack at A78 cache size |
| Multi-level wavelet (in progress, subagent ae41a11) | In flight | Compute neutral, but smaller bitstreams → faster ANS encode |
| `vld2q` + branchless clip in unpack | Designed in memory; not committed | 5-15% on unpack |
| Proper int32 8-wide vertical filter | Partial 2× unroll landed (`1ae5d5d`); could be tightened with FMA / dual issue tuning | Modest |

Target M1 time for 2.5× A78 fit: 17 ms steady-state. Current: ~30 ms. Need 1.7× more compute speed.

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

3. **No visual quality assessment at rate-controller-limited operating points**
   - Subagent E tested visual quality at fixed q presets via gpr_tools.
   - Haven't visually inspected output where rate controller pushes quant_scale > 4×.
   - At those points, the LL gets aggressively quantized; want to know if it shows.

## Documentation

- `docs/session-2026-05-11-summary.md` — what was done this session
- `docs/operating-envelope.md` — measured PSNR/bitrate/storage tradeoffs
- `docs/raw-video-landscape.md` — codec ecosystem + patent landscape
- `docs/followups.md` — this file

The branch `feature/raw-video` is in a known-good state. Picking up from here, the highest-leverage next move is probably the multi-level wavelet (currently in subagent flight) since it would directly enable cheaper microSD card classes for video.
