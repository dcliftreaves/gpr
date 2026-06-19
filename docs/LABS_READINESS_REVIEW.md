# Labs Readiness Review

Last refreshed: 2026-06-18

## Decision

Go for Labs prototype exploration of `.gvid` raw capture plus desktop
review/export, with native 12MP Mission 1 FLL2 T2 as the current true Bayer
recompression candidate for the 20+ fps stand-in floor.

No-go for direct firmware merge until target hardware integration exists and
actual Mission 1 capture proves sensor/DMA handoff on camera hardware. The
current Pi 5 stand-in receipts are acceptable as conservative 20+ fps proxy
evidence for firmware-handoff review. Strict 24 fps with the 90% SD-card write
margin remains open.

## Ready Now

| area | evidence |
|---|---|
| Media shape | `.gvid` clip/frame format, Python packer, metadata sidecars |
| Desktop review path | `gpr2prores` accepts `.gvid` and validates runtime dispatch |
| Source-level safety | hosted CI validates headers, streams, release evidence, registry consistency |
| Format hardening | C reader rejects malformed v1 headers, truncated headers/payloads, zero-frame streams, duplicate or out-of-order frame tags, and whole-stream corruption; C writer rejects non-finite, negative, overflowing, or rate-control-rounds-to-zero FPS/bitrate fields |
| Portable source/media bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` |
| Portable target-proxy bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` and includes the strict 10-minute Pi proxy receipt plus normalized camera-handoff receipt |
| Target receipt harness | `tools/run_labs_target_bench.py` produces `labs_target_bench.json` with timing, structured `fused_timing`, storage, memory, drop, `.gvid`, and interruption fields |
| Strict Pi 5 target receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` proves 14,400 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, and a 19.98 fps median that is acceptable as a conservative 20 fps Pi proxy |
| Native 12MP Mission 1 true Bayer recompression | `tools/mission1_native12_fll2_t2_profile.py` defines the current q8 FLL2 avg7555-fast P2-pin T233 profile. `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_fll2_T2_native12_quality_20260617/summary.json` records unchanged q8/T2 quality for GP017601/602/603, and `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_prescale2_refh_neon_native12_1440f_20fps_20260617/summary.json` records current 1,440-frame Pi receipts after the byte-exact prescale-2 reference-horizontal NEON path. All three pass 20 fps, valid `.gvid`, 0 drops, interruption recovery, and the conservative Lexar SILVER PLUS 128GB-1TB 205/150 write budget with 0.90 margin. GP017602 also fits the strict-24 storage budget at 133.71 MB/s, but not the strict-24 total timing budget. |
| Native 12MP strict-24 blocker receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_prescale2_refh_neon_GP017602_1440f_24fps_20260617/labs_target_bench.json` proves the current hard-frame failure mode: storage/gvid/drops/recovery pass at 24 fps, but `fps_target_met=false`; total median is 44.42 ms, encode median 40.72 ms, write median 3.56 ms |
| Hardened native 12MP strict-24 blocker receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_hardened_fps_gate_lh3_k6656_GP017602_120f_24fps_20260618/labs_target_bench.json` proves the current hard-gate failure mode: storage/gvid/drops/recovery pass, but `fps_median_target_met=false`, `fps_wall_target_met=false`, and `fps_target_met=false`; median timing is 43.50 ms / 22.99 fps and whole-run throughput is 22.40 fps |
| Current source-provenance native 12MP sustained receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_provenance_t236_GP017602_240f_20260618/labs_target_bench.json` proves the current target build writes valid 4096 x 3072 `.gvid` for 240 frames with no drops and interruption recovery. Median timing is 43.49 ms / 23.00 fps, with encode median 39.82 ms and write median 3.53 ms. The receipt records source provenance SHA-256 `eac88f91c8717d40f0bf5197422f9e03fd6c50c15af1b209565c16403f08ce6d` and binary SHA-256 `e034bcc62f1733cff3878234622a8378f1707e4d0e38b32b732e21d2f7321994`. Payload size still fits the conservative Lexar SILVER PLUS 24 fps budget, so the remaining strict-24 miss is timing, not storage capacity or media validity. |
| Writer-handoff strict-24 receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_writer_handoff_t236_GP017602_60f_20260618/labs_target_bench.json` uses the updated receipt schema with `writer_handoff`: no deferred writer drain is present, loop median is 23.38 fps, whole-run wall throughput is 22.37 fps, encode median is 39.48 ms, write median is 3.39 ms, storage still fits the Lexar 24 fps budget, and strict 24 fps still fails by about 1.11 ms/frame |
| Explicit loop/wall gap receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_gap_receipt_t236_GP017602_240f_20260618/labs_target_bench.json` reruns the T236 quality-boundary path with the current receipt wrapper for 240 frames. It records valid `.gvid`, zero drops, storage-budget pass, 43.58 ms loop median, 44.10 ms/frame whole-run wall time, `loop_target_gap_ms=1.91`, `wall_target_gap_ms=2.44`, and `bottleneck_target_gap_ms=2.44`; this confirms the remaining strict-24 blocker is still timing/handoff, not payload size or deferred writer drain. |
| Inline jANS frequency saturation fix | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_freq_saturate_t236_GP017602_summary_20260618/summary.json` accepts the inline `JANS_FREQ_INC` fix as correctness/payload work, not a strict-24 timing fix. The profile showed stripe symbol counts above the 16-bit frequency-table ceiling; the inline path now matches the non-inline saturating frequency increment. The sustained 240-frame receipt is valid, has 0 drops and storage pass, reduces payload from 5483.862 to 5388.797 KiB/frame versus the prior explicit-gap receipt, but still misses strict 24 at 44.46 ms median and 22.26 fps wall. A branchless 32-bit side-table follow-up was rejected: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_freq32_t236_GP017602_summary_20260618/summary.json` kept the same payload but regressed to 45.89 ms median and 20.57 fps wall on the 120-frame target receipt. |
| Inline jANS residual-tail correctness fix | `source/app/test_jans_inline_tail_flush.c` verifies that inline jANS preserves high-magnitude scalar-tail coefficients and flushes every pending residual byte in single-blob, immediate-stripe, and deferred-stripe modes. `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_tail_flush_sanity_GP017602_30f_20260618/summary.json` records the Pi sanity result: valid `.gvid`, zero drops, storage pass, 46.67 ms median, 19.61 fps wall, and only +0.048 KiB/frame versus the prior timing-detail payload. This is accepted as a correctness fix, not a strict-24 timing closure. |
| Current stripe retune after saturation | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/summary.json` sweeps `FUSED_STRIPE_ROWS=256/264/320/384` on the accepted saturation binary. `stripe264` is best in this set at 44.005 ms median and 22.29 fps wall, with valid `.gvid`, zero drops, interruption recovery, and storage pass, but still misses strict 24 by 3.19 ms/frame wall. This rejects stripe retuning as the strict-24 closure path. |
| Accepted LL bitwriter32 timing fix | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_ll_bitwriter32_probe_GP017602_20260618/summary.json` accepts the FLL2 sideband bitwriter change as a byte-identical timing improvement, not a strict-24 closure. The short `.gvid` hash is unchanged, and the 240-frame same-session target comparison improves from 43.64 ms median / 21.80 fps wall on backup binary `7bf776d2ac58ccdebe5fbdaf458169e674d904575bc610b826fee883737aca30` to 42.77 ms median / 23.11 fps wall on candidate binary `dd6214c666d62b1b62c864b59ef8e387c76c61e2e4d2ba2461e8bbc74e4e3c26`. Valid `.gvid`, zero drops, interruption recovery, and storage pass remain intact; strict 24 still fails by 1.61 ms/frame wall. |
| Rejected LL bitwriter32 pinning probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_ll_bitwriter32_pin_probe_GP017602_20260618/summary.json` re-tests `FUSED_PIN=1,FUSED_PIN_P2=1` on the accepted LL bitwriter32 binary. The pinned 120-frame run records 43.15 ms median / 22.62 fps wall, only 0.225 ms faster than the order-neighbor no-pin repeat, and remains below the accepted no-pin 240-frame evidence; pinning stays rejected for strict-24 closure. |
| Post-bitwriter timing detail and PGO probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_ll_bitwriter32_timing_detail_GP017602_30f_20260618/labs_target_bench.json` refreshes the timing-detail profile after the native-resolution receipt metadata fix: valid 4096 x 3072 `.gvid`, encode median 44.00 ms, write median 3.73 ms, Pass1 median 38.5 ms, Pass2 median 6.05 ms, tokenization median 15.15 ms, and unpack median 9.65 ms. `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_pgo_ofast_probe_GP017602_20260618/summary.json` rejects GCC `-Ofast` PGO/code layout for this path: the candidate is byte-identical but regresses from 43.425 ms median / 22.34 fps wall to 47.02 ms median / 20.86 fps wall on the same-session 120-frame A/B. |
| Rejected jANS NEON lane-extract probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_jans_lane_extract_probe_GP017602_20260618/summary.json` proves the scalar-reload-to-`vgetq_lane_s32` tokenizer change is byte-identical on the short `.gvid` hash check, but slower on target. The accepted backup binary records 43.17 ms median / 22.68 fps wall on the 120-frame A/B, while candidate runs record 43.835 ms and 43.785 ms median; the probe is rejected and the Pi binary is restored to SHA-256 `7bf776d2ac58ccdebe5fbdaf458169e674d904575bc610b826fee883737aca30`. |
| Current write/cache contention summary | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_write_contention_summary_20260618/summary.json` records the latest visual-neutral strict-24 work: the 240-frame source-provenance receipt misses strict 24 by 1.83 ms median and records 22.46 fps wall; the explicit 240-frame loop/wall receipt narrows the current gap to 1.91 ms loop median and 2.44 ms whole-run wall; indexed `writev` improved the order-reversed 240-frame probe by 0.375 ms total / 0.257 ms write; and older coalesced-prefix/indexed-writev evidence remained a near-miss. A current-source opt-in `GPR_BENCH_GVID_COALESCE_PREFIX=1` A/B now has `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_coalesce_prefix_source_probe_GP017602_120f_summary_20260618/summary.json` and is rejected for strict-24 closure: candidate-first measured 43.585 ms, effectively equal to the latest 43.579 ms sustained baseline, while baseline-first regressed to 44.225 ms. A jANS 32-coefficient zero-scan tokenization probe is also rejected: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_jans_zero_scan32_probe_GP017602_summary_20260618/summary.json` records a sustained 240-frame candidate at 44.515 ms median and 21.18 fps wall. A fused hard-threshold tokenizer probe is rejected and removed from live source: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_jans_fused_hardt_probe_GP017602_summary_20260618/summary.json` records byte-identical `.gvid` output but regresses loop median by 2.05 ms and encode median by 2.13 ms across both A/B orders. The cleaned-source follow-up receipt `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_clean_baseline_GP017602_240f_after_fused_hardt_reject_20260618/labs_target_bench.json` remains valid but misses strict 24 at 45.09 ms median and 21.02 fps wall. Rejected follow-ups include frame-prefix/current-prefix coalescing, jANS zero-scan32, fused hard-threshold tokenization, `-Ofast`, LTO, PGO/code-layout, pwritev, sync_range, dontneed, ionice, preallocation, ping-pong, async-copy, and scheduler pinning. |
| Live Pi sync-range refresh | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_live_t236_exact_sync_range_ab_GP017602_60f_20260619/summary.json` re-checks the recorded T236 exact profile on the live Pi. The machine is in performance governor at 2.4 GHz with no current throttling, but the 60-frame comparable baseline is 44.165 ms median / 22.64 fps and the manual sync-range smoke is 45.229 ms median over 3 frames. This keeps `sync_range` rejected and reinforces that the remaining strict-24 gap is not solved by kernel writeback hints. |
| Older native 12MP timing-only receipts | Older q3, 3-level multi-level receipts remain historical timing-only evidence. A decoded visual audit found severe native-resolution fused roundtrip artifacts, so those runs are not production quality evidence. |
| Native 12MP camera `.GPR` payload path | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native_gpr_payload_pi_explicit_1440f_20260616/receipt.json` proves explicit `payload_kind: camera_gpr` `.gvid` metadata/dispatch for 1,440 already-compressed native 4096 x 3072 Mission 1 frames on the Pi 5 stand-in at 48.83 fps wall rate. This is a container/storage baseline only; it does not prove Bayer recompression |
| Pi 5 regression probe | `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md` records current, historical-doc, environment, runtime-knob, compiler-flag, quality, highpass-bound, timing, producer-guard, polynomial-log, u16 log-scratch, prescale-2 fixed-shift, lazy scratch allocation, prefetch, LUT-unroll, luma-pair shared-unpack, rejected luma-pair handoff, current-head direct `.gvid` rehearsal, and corrected pixel-format probes; best short direct-container near-miss is 23.54 fps median with luma-pair plus stripe64/deferred rANS, while the productionizable channel0-to-channel3 handoff version regressed to 12.05 fps, the corrected pixel-format direct `.gvid` receipt is 19.85 fps median, and diagnostic highpass dropping reaches 30.35 fps but is not valid output |
| Historical 50MP half-res rehearsal | The current-head direct rehearsal at 16.00 fps remains historical blocker context for the older 50MP-to-half-res target; native 12MP is now the preferred Mission 1 capture shape |
| Reproducible target timing build | CMake exposes `-DFUSED_TIMING=ON -DFUSED_TIMING_DETAIL=ON`; the target receipt harness parses diagnostics into `fused_timing`, and a local smoke verifies per-channel unpack/horizontal/vertical/tokenize detail plus Pass1/Pass2 summaries without editing source |
| Current overview | README is media-focused; detailed proof lives in docs |
| Native 12MP 8K SR boundary | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_tailflush_refresh_GP017346_GP017349_20260618/summary.json` proves the current guardrail-light SR checkpoint is not yet production-closed for the current corrected codec/source contract. `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_current_contract_summary_20260618/summary.json` records the follow-up current-contract rebuild and retrain attempts: Mission42 and Z8-all24 pairs now include resampler/tool/profile provenance, but no checkpoint is promoted. Hardfocus 128-tile training improves `GP017346`/`GP017349` Mission rows and nearly closes `GP017349`, but it overfits Mission and regresses regenerated Z8 guardrails. Balanced 128-tile Mission hard2 + Z8 train19 training recovers Z8 RMSE/PSNR versus hardfocus-only, but still misses Mission hard/detail floors. A residual-scale sweep is also rejected, so the current blocker is detail placement/loss/data balance rather than a simple residual amplitude setting. Hard full-frame tile mining is useful for targeting failures, but hard-only finetuning regresses `GP017349` and Z8. The best mixed hard-tile + balanced-corpus checkpoint improves Z8 versus balanced and gets `GP017347` over the gradient floor, but still misses `GP017346`, `GP017349`, and `GP017600`, so it is not promoted. The detail-residual sidecar path is the first reconstruction direction that recovers the missing low-source detail in oracle/prototype form; `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q3q4_sr_gate_20260619/summary.json` shows q4/t2 still clears the focused Mission hard rows after sidecar-size reduction, `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_q4t2_direct_20260619/summary.json` records 4-thread native compact encode at 41.867 ms mean / 38.113 ms median for 4.467 MiB/frame, and `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/summary.json` records the broad Mission42/Z8 all24 q4/t2 SR gate. That broad gate is strong on Mission42 and Z8 RMSE/PSNR, but Z8 gradient/detail lift remains shallow, so treat the current SR checkpoint and sidecar path as offline/future-bitstream evidence until fused codec timing and a detail-placement pass close. |

## Not Ready Yet

| area | missing evidence |
|---|---|
| Firmware capture integration | sensor/DMA handoff and memory ownership have not been executed on target; current receipts use Pi stand-in file input |
| Sustained target run | native 12MP FLL2 avg7555-fast P2-pin T233 true Bayer recompression clears the active 20+ fps Pi stand-in floor across GP017601/602/603, with current median 22.70-24.35 fps and 104.0-111.4 MB/s required write at 20 fps against the 135 MB/s conservative Lexar SILVER PLUS 128GB-1TB payload budget. Actual Mission 1 sensor/DMA capture remains unproven, and strict 24 fps total timing remains open |
| Strict 24 fps production proof | current T236/T238 boundary work shows quality/storage can fit the 24 fps payload budget, but the sustained real-write path remains below 24 fps on the Pi stand-in. The current 240-frame source-provenance receipt is 43.49 ms / 23.00 fps median with 22.46 fps wall throughput; the strict-24 frame budget is 41.67 ms. The blocker is target-platform encode/write handoff margin, not visual quality, `.gvid` validity, or SD-card payload size. |
| Production-closed 8K SR | the registered guardrail-light checkpoint remains useful offline review evidence, but the current-codec refresh shows it is tied to an earlier SR pair/codec artifact contract. Current-contract Mission42/Z8 pairs now exist, but retrain attempts did not produce a promotable checkpoint: hardfocus gains regress Z8 guardrails, the balanced Mission hard2 + Z8 train19 candidate still misses Mission detail floors, the hard-tile-only finetune regresses `GP017349`/Z8, and the mixed hard-tile + balanced-corpus checkpoint still misses `GP017346`, `GP017349`, and `GP017600`. The q4/t2 detail-residual sidecar broad gate improves Mission42 and Z8 RMSE/PSNR, but Z8 detail/gradient lift remains shallow. Production SR now needs fused sidecar timing and a targeted detail/edge objective that raises Mission and Z8 texture placement, followed by fullframe/packaging/timing receipts before promotion. |
| Final camera artifact bundle | Pi target-proxy bundle exists; final bundle still needs actual camera-firmware evidence |

## Current Risk

The main risk is no longer whether `.gvid` can represent, validate, and recover
the media. The native 12MP Mission 1 receipts now split cleanly:
camera-native `.GPR` payloads inside `.gvid` remain a container/storage
baseline, while FLL2 T233 starts from Bayer pixels and has passing 20+ fps
stand-in evidence. The remaining firmware risk is actual Mission 1
sensor/DMA/storage integration and any decision to require strict 24 fps with
the conservative 90% SD-card write margin.

## Next Work

1. Promote the current FLL2 avg7555-fast P2-pin stand-in path through the firmware-handoff
   package using `tools/mission1_native12_fll2_t2_profile.py`, while keeping
   the production claim bounded to the proven 20+ fps Pi stand-in scope.
2. Treat native `.GPR` payload wrapping only as a storage/container baseline.
   It is useful evidence that `.gvid` can carry bytes fast enough, but it is
   not a compression result.
3. Run the FLL2 avg7555-fast P2-pin path from the actual Mission 1 sensor/DMA
   frame source and camera storage path, then produce a camera handoff receipt.
   If either the frame source or storage path is still file-backed/userland
   stand-in work, keep `target.role=stand-in` and do not claim firmware
   readiness.
4. Continue strict-24 CPU optimization only if 24 fps remains a requirement.
   FLL2 avg7555-fast P2-pin passes 20+ fps and fits the conservative 24 fps
   storage budget on GP017602. The latest sustained current-source T236 receipt
   measures 43.49 ms median / 23.00 fps over 240 frames, with 39.82 ms encode,
   3.53 ms write, and 22.46 fps whole-run wall throughput. The writer-handoff
   receipt separately shows no hidden
   deferred writer drain. Current T236 follow-up evidence narrows the remaining
   strict-24 gap to encode/write ownership: indexed writev and older
   scatter-prefix coalescing were near-miss evidence, but the current-source
   opt-in coalesced-prefix A/B does not close the gap and is not promoted.
   Copy-based async handoff and cheap Linux writeback/code-layout knobs have
   also been rejected on total frame time.
5. Continue current-code Pass1/highpass optimization only if the hardware
   receipt shows Pi-side compute remains the limiting factor. A 2026-06-15
   search did not find a separate
   recoverable `be0328a` source tree in the consolidated 8TB work area, the
   archived branch does not contain a missing codec speed delta, and the
   polynomial-log, u16 log-scratch, and prescale-2 fixed-shift probes were
   slower than the LUT/default path. The invalid producer+decimate path was
   removed rather than kept as a supported mode; a fresh decimation-aware
   producer scratch probe regressed on full-frame Pi timing, and a lazy scratch
   allocation probe was byte-identical but also slower on Pi. A col-decimate
   prefetch probe and an 8-entry LUT-unroll probe were also byte-identical but
   regressed target timing. A luma-pair shared-unpack scratch candidate improved
   the best short direct-container median to 23.54 fps only with
   stripe64/deferred rANS, but still missed the 24 fps target and was not
   committed. A later channel0-to-channel3 luma handoff implementation was
   byte-identical locally but regressed to 12.05 fps on Pi, so cross-channel
   row handoff is rejected. The corrected pixel-format direct `.gvid` receipt
   also misses at 19.85 fps median, with timing detail again pointing to Pass1
   channel unpack.
6. Replace or supplement the stand-in bundle with a passing target-capture
   receipt.
7. Add target/self-hosted CI jobs or documented manual receipts for media
   behavior hosted CI cannot exercise.
8. Re-run the readiness review with target bundle hashes and bench receipts attached.
9. Continue the current-contract 12MP-to-8K SR pass by integrating the q4/t2
   detail-residual stream into the codec-side path and adding a gate-aligned
   detail-placement objective around Mission42 plus Z8 all24. The next
   model/loss or reconstruction experiment must keep the broad Mission42 RMSE
   lift while improving Z8 gradient/detail placement, then rerun fullframe
   Mission, Z8 all24, packaging, `.gvid`, and timing receipts before promoting
   SR beyond offline review.
