# Labs Target Bench

Last refreshed: 2026-06-19

This page defines the target-style evidence required for Labs prototype review.
It separates current Pi 5 stand-in evidence from the still-missing camera
firmware evidence.

## Current Evidence

| item | current evidence | status |
|---|---|---|
| Current Mission 1 numbered-list audit | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_numbered_list_readiness_20260625/readiness.json` records the active 4K Bayer `.gvid`, 1024 x 768 preview, CNN output, and ProRes review evidence. The best 420-frame 4K `.gvid` receipt is 24.32 fps whole-run wall / 25.29 fps loop median with zero drops and Lexar SILVER PLUS write-budget pass. The selected 1,440-frame aggregate Pi closure rerun records 20.50 fps wall / 21.52 fps median for 4K `.gvid` and 24.20 fps wall / 43.86 fps median decode-plus-target for 1024 x 768 preview, with validated stand-in blocker receipts at `artifacts/mission1_camera_closure_run_20260625/current_standin_followup/`. | active numbered-list Pi 5 stand-in evidence; firmware/UI handoff still pending |
| Labs shim Pi receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_labs_shim_pi_standin_20260625/run_120f_dual/labs_target_bench.json` validates the public `gpr_labs_encoder` shim on the Pi 5 stand-in: valid 4096 x 3072 `.gvid`, 120 frames, zero drops, interrupted-tail recovery, and Lexar write-budget fit. It reaches 15.40 fps median / 14.33 fps wall, so it is functional integration evidence, not the current production-speed capture path. | shim integration evidence; performance gap remains |
| Historical half-res `.gvid` capture budget | `docs/pi5_bench_2026-05-26.md` reports 24.93 fps median on an older Pi branch/run | historical stand-in evidence |
| Current strict 10 minute Pi 5 target run | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` reports 14,400 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, 19.98 fps median | proxy-acceptable Pi stand-in; camera 24 fps pending |
| Current half-res variant probe | `docs/LABS_PI_CAPTURE_REGRESSION_2026-06-15.md` reports current, historical-doc, environment, runtime-knob, compiler-flag, quality, producer, highpass-bound, target-rehearsal, direct-container, and luma-pair probes; the best short direct-container near-miss is luma-pair plus stripe64/deferred rANS at 23.54 fps median | regression evidence |
| Corrected pixel-format direct `.gvid` probe | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_direct_gvid_pf4_120f_e16357f_20260615/labs_target_bench.json` reports commit `e16357f`, 120 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, and 19.85 fps median with pixel format 4 applied to the encoder context | target-performance blocker |
| Hardened native 12MP wall-FPS probe | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_hardened_fps_gate_lh3_k6656_GP017602_120f_24fps_20260618/labs_target_bench.json` reports 120 GP017602 native 12MP true-Bayer frames, 0 drops, valid `.gvid`, interrupted-tail recovery, storage-budget pass, 22.99 fps median, and 22.40 fps whole-run wall throughput | target-performance blocker |
| Native 12MP strict-24 quality/storage boundary | `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_t236_ch2lh3_quality_dashboard_20260618/summary.json` and `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_threshold_quality_matrix_20260618/summary.json` show T236 is the first swept profile that passes GP017601/602/603 quality and the strict-24 Lexar storage budget. T236 is boundary evidence, not the currently registered production profile. T468 passes `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_t468_ch2lh4_GP017602_120f_24fps_20260618/labs_target_bench.json` at 27.74 wall fps, but fails quality and is speed-tier only. | strict-24 production timing still open for quality profile |
| Native 12MP T236 P2 ordering probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_probe_t236_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` keeps the T236 payload unchanged at 5483.862 KiB and records 43.23 ms median encode after band-major worker-pool execution order, but total median remains 47.19 ms / 21.19 fps with strict-24 failure. | accepted scheduler cleanup; not sufficient for strict 24 fps |
| Native 12MP inline jANS frequency-saturation fix | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_freq_saturate_t236_GP017602_summary_20260618/summary.json` accepts the inline `JANS_FREQ_INC` fix as correctness/payload work. The sustained 240-frame receipt validates `.gvid`, 0 drops, and storage pass, and reduces payload to 5388.797 KiB/frame, but still misses strict 24 at 44.46 ms median / 22.26 fps wall. | accepted correctness/payload fix; strict-24 timing still open |
| Native 12MP post-saturation stripe retune | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618/summary.json` sweeps `FUSED_STRIPE_ROWS=256/264/320/384` on the accepted saturation binary. The best wall result is `stripe264` at 44.005 ms median / 22.29 fps wall, with valid `.gvid`, 0 drops, interruption recovery, and storage pass. | rejected as strict-24 closure; encode timing still open |
| Native 12MP accepted LL bitwriter32 timing fix | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_ll_bitwriter32_probe_GP017602_20260618/summary.json` keeps the FLL2 sideband bitstream byte-identical while flushing complete low-order bytes in 32-bit chunks. Same-session 240-frame evidence improves from 43.64 ms median / 21.80 fps wall on the accepted backup binary to 42.77 ms median / 23.11 fps wall on the candidate; valid `.gvid`, 0 drops, interruption recovery, and storage pass remain intact. | accepted timing improvement; strict-24 timing still open |
| Native 12MP rejected LL bitwriter32 pinning probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_ll_bitwriter32_pin_probe_GP017602_20260618/summary.json` re-tests `FUSED_PIN=1,FUSED_PIN_P2=1` after the LL bitwriter32 improvement. The pinned 120-frame run is only 0.225 ms faster than the order-neighbor no-pin repeat and still below the accepted no-pin 240-frame wall result. | rejected as strict-24 fix |
| Native 12MP post-bitwriter timing-detail refresh | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_ll_bitwriter32_timing_detail_GP017602_30f_20260618/labs_target_bench.json` reruns the timing-detail profile after the accepted LL bitwriter32 path and the native-resolution receipt metadata fix. The refreshed 30-frame profile reports valid 4096 x 3072 `.gvid`, encode median 44.00 ms, write median 3.73 ms, Pass1 median 38.5 ms, Pass2 median 6.05 ms, tokenization median 15.15 ms, and unpack median 9.65 ms. This noisy short run does not supersede the better 240-frame timing receipt, but it keeps the remaining bottleneck pointed at Pass1 tokenization/unpack rather than storage. | diagnostic evidence; strict-24 timing still open |
| Native 12MP rejected PGO/code-layout probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_pgo_ofast_probe_GP017602_20260618/summary.json` tests GCC PGO/code layout using the same `-Ofast -mcpu=native` production flags. The candidate is byte-identical to the accepted binary on the 120-frame `.gvid` hash, but regresses from 43.425 ms median / 22.34 fps wall to 47.02 ms median / 20.86 fps wall, so PGO is rejected for this encode path. | rejected as strict-24 fix |
| Native 12MP rejected jANS NEON lane-extract probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_jans_lane_extract_probe_GP017602_20260618/summary.json` replaces scalar reloads after the NEON nonzero test with `vgetq_lane_s32` extraction. The candidate is byte-identical on a short `.gvid` hash check, but the 120-frame target A/B regresses by 0.64 ms median on average versus the accepted backup binary. | rejected as strict-24 fix |
| Native 12MP rejected inline 32-bit frequency side-table probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_inline_freq32_t236_GP017602_summary_20260618/summary.json` replaces hot-loop saturating increments with a 32-bit side table and clamp-on-emit. It keeps payload at 5388.797 KiB/frame but regresses target timing to 45.89 ms median / 20.57 fps wall on the 120-frame receipt. | rejected as strict-24 fix |
| Native 12MP rejected fused hard-threshold tokenizer probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_jans_fused_hardt_probe_GP017602_summary_20260618/summary.json` records byte-identical `.gvid` output but regresses loop median by 2.05 ms and encode median by 2.13 ms across both A/B orders. The live source hook was removed; cleaned-source follow-up `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_clean_baseline_GP017602_240f_after_fused_hardt_reject_20260618/labs_target_bench.json` remains valid but misses strict 24 at 45.09 ms median / 21.02 fps wall. | rejected as strict-24 fix |
| Native 12MP rejected writer-core pinning probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_writer_core_probe_GP017602_60f_20260619_t236s264_recorded/summary.json` tests ping-pong writer placement on core 0 and core 3 against the scatter baseline. Scatter remains fastest at 44.487 ms median / 21.38 wall fps, while ping-pong variants land at 47.954-49.356 ms median and all miss strict 24 fps. | rejected as strict-24 fix |
| Native 12MP rejected live sync-range refresh | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_live_t236_exact_sync_range_ab_GP017602_60f_20260619/summary.json` reruns the recorded T236 exact profile on the live Pi target after confirming performance governor, 2.4 GHz clocks, no current throttling, and SSD-backed output. The comparable 60-frame baseline is 44.165 ms median / 22.64 fps, slower than the best historical T236 near-miss; a manual `GPR_BENCH_GVID_SYNC_RANGE=1` smoke completes at 45.229 ms median over 3 frames. | rejected; writeback hint still shows no strict-24 signal |
| Native 12MP T238 P2 ordering probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_probe_t238_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` re-measures the quality-valid HH=8 boundary on the current worker-order build. It records 42.51 ms median encode, 46.46 ms median total, 21.53 fps median, valid `.gvid`, no drops, interruption recovery, and strict-24 storage pass. | quality/storage boundary remains strict-24 timing fail |
| Native 12MP LL predictor/build-mode probes | Left-predictor T236/T238 receipts (`current_probe_t236_leftpred_p2order...`, `current_probe_t238_leftpred_p2order...`) are quality-neutral but fail strict-24 storage. T238 avg/K6555 (`current_probe_t238_avg_k6555_p2order...`) improves payload to 5.27 MiB/frame and storage margin but still records only 47.04 ms median total / 21.26 fps. Ping-pong writer, async writer, and `-Ofast` follow-ups all regress timing. | rejected as strict-24 fixes |
| Mission 1 still source corpus | `/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P` contains 42 Mission 1 50MP JPG/GPR/DNG triples and 3 native 12MP Mission 1 JPG/GPR/DNG triples. Inventory lives at `/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/media_summary.json`; decoded native 12MP raws live under `/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/raw12_decode/`. See `docs/VIDEO_STATUS.md` and `docs/LABS_READINESS_REVIEW.md`. | real source corpus; native 12MP file-backed target input ready |
| Native 12MP Mission 1 Pi receipts | `docs/VIDEO_STATUS.md` and `docs/LABS_READINESS_REVIEW.md` summarize the current q8 FLL2 T2 avg7555-fast P2-pin true-Bayer profile for `GP017601`, `GP017602`, and `GP017603`. All three clear the 20 fps Pi stand-in floor, validate `.gvid`, prove interruption recovery, drop 0 frames, and fit the conservative Lexar SILVER PLUS 128GB-1TB 205/150 MB/s target at 20 fps. Older q3, 3-level receipts remain timing-only because visual audit found severe native-resolution roundtrip artifacts. | 20+ fps true-Bayer stand-in pass; strict 24 fps total timing still open |
| Current T233 storage/CPU phase probe | `/Volumes/OWC_8TB/gpr_work/artifacts/current_probe_t233_GP017602_pi_20260618/ssd_labs_target_bench.json` and `/Volumes/OWC_8TB/gpr_work/artifacts/current_probe_t233_GP017602_pi_20260618/sdwrite_labs_target_bench.json` use the current source build on the Pi. SSD direct `.gvid` records 48.10 ms median total, 44.33 ms encode, 3.81 ms write; SSD-read to SD-write records 48.70 ms total, 44.76 ms encode, 3.93 ms write. Matching scatter encode-only stderr records 44.38 ms median, about 22.5 fps. | 20 fps floor is CPU/encode-bound; strict 24 cannot be solved by storage alone |
| Current T233 P2-order follow-up | `/Volumes/OWC_8TB/gpr_work/artifacts/current_probe_t233_p2order_GP017602_120f_ssd_20260618_labs_target_bench.json` uses the same registered T233-style profile after the Pass-2 worker-order cleanup. It records 47.73 ms median total, 43.58 ms encode, 4.18 ms write, valid `.gvid`, no drops, interruption recovery, and 20.95 fps median against the active 20 fps target. | accepted scheduler cleanup; still CPU/encode-bound and not strict 24 |
| Fresh T233 strict-24 target refresh | `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_refresh_t233_GP017602_120f_24fps_20260618/labs_target_bench.json` reruns the current Pi build through the registered T233 profile with a strict 24 fps target. It records valid `.gvid`, no drops, interruption recovery, storage pass, 47.52 ms median total, 43.47 ms encode, 4.20 ms write, and 21.04 fps median. | current target-access evidence; CPU encode remains the strict-24 blocker |
| Current-head tracked sweep | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_03eaa4d_120f_20260615T112841Z/labs_perf_sweep.json` reports commit `03eaa4d`, 120-frame direct `.gvid` variants, 0 drops, valid `.gvid`, and no passing variant; baseline is best at 21.54 fps median and stripe64/deferred regresses to 18.52 fps median. Timing receipt `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_timing_3c48f2f_30f_20260615T113211Z/labs_target_bench.json` reports Pass1 median 33.5 ms, Pass2 median 11.6 ms, and unpack mean 20.6 ms | current-head target-performance blocker |
| Rejected luma-pair handoff candidate | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_lumapair_dirty_120f_20260615T114724Z/labs_perf_sweep.json` reports a dirty-source opt-in channel0-to-channel3 luma handoff probe; patched baseline is best at 20.44 fps, luma-pair alone regresses to 12.05 fps, and luma-pair plus stripe64/deferred reaches only 18.54 fps | rejected performance candidate |
| Current-head Pi 5 direct `.gvid` rehearsal | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_direct_1440f_1b934a4_20260615/labs_target_bench.json` reports commit `1b934a4`, 1,440 frames, 0 drops, valid `.gvid`, interrupted-tail recovery, and 16.00 fps median; timing-detail receipt `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_timing_detail_30f_1b934a4_20260615/labs_target_bench.json` reports Pass1 median 38.90 ms and unpack mean 22.79 ms | current-head target-performance blocker |
| 2K live/camera-back raw target | `docs/RAW_RESOLUTION_TARGETS_2026-06-14.md` reports `2k_raw_0p5x_l2hh` at 29.85 fps median, 37.1 ms p95 | stand-in evidence |
| Desktop review PREVIEW | `docs/VIDEO_STATUS.md` reports q8 three-way PREVIEW quality pass at 13.65 s/image on Mac/MPS | offline-only evidence |
| Format validation | `test_video_format`, `test_labs_encoder_api`, `test_labs_encoder_bench_cli.sh`, and `test_video_full_chain` validate headers, the firmware-facing shim, target-bench receipt path, streams, and real encoded `.gvid` files | committed CI evidence |
| Portable source/media bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` | source/media stand-in bundle |
| Portable target-proxy bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` and carries the strict 10-minute Pi proxy receipt | Pi proxy bundle |
| Target receipt harness | `tools/run_labs_target_bench.py` wraps `bench_fused` for production timing evidence or `labs_encoder_bench_cli` for public-shim integration evidence, packs a strict `.gvid`, validates truncation behavior, parses bench timing output, and writes `labs_target_bench.json` | committed harness |

## Required Target Run

Before claiming firmware readiness, run a sustained target-style capture:

| metric | required receipt |
|---|---|
| duration | 10 minutes or explicit shorter-run blocker |
| fps | median, p95, p99, min, whole-run wall fps |
| encode | median/p95/p99 ms/frame |
| storage | target card read/write speeds, required write MB/s, fsync/flush policy |
| memory | RSS or firmware heap high-water mark |
| CPU | utilization per core or firmware equivalent |
| thermal | temperature over time and throttle state |
| drops | count, frame indices, policy taken |
| output validity | C stream validation, metadata validation, decode checksum |
| interruption | normal stop and simulated interrupted-file recovery result |

Run the target-style receipt harness on the Pi 5 stand-in with the actual
`bench_fused` binary and raw input:

```bash
export GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts
export TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp

python3 tools/run_labs_target_bench.py \
  --bench build/bin/bench_fused \
  --raw /path/to/source_bayer.raw \
  --frames 14400 \
  --target-fps 24 \
  --storage-target-name "Lexar Professional SILVER PLUS SDXC/microSDXC UHS-I (128GB-1TB)" \
  --storage-target-read-mbps 205 \
  --storage-target-write-mbps 150 \
  --storage-target-safety-margin 0.90 \
  --storage-target-note "Published 128GB-1TB SILVER PLUS profile: 205 MB/s read, 150 MB/s write; 64GB microSD is 205/100." \
  --output-dir "$GPR_ARTIFACT_ROOT/labs_target_bench_pi5_10min_YYYYMMDD"
```

For a receipt that measures the actual sequential `.gvid` write path instead
of staging one `.gpr` file per frame and packing afterward, add
`--direct-gvid`. This mode requires a `bench_fused` binary that supports
`GPR_BENCH_GVID`; the receipt validates the emitted container and records
`fsync_policy: bench_fused sequential .gvid fwrite`. The wrapper passes
`--target-fps` through as `GPR_BENCH_GVID_FPS`, so the direct `.gvid` header
must validate with `gvid.validation.fps_x1000 == round(target.fps * 1000)`.
Metadata-only Pi evidence for the 20 fps proxy path lives at
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_t233_direct_gvid_fps_metadata_probe_20260618/labs_target_bench.json`;
it validates 4096x3072, `GPR_BENCH_GVID_FPS=20.000000`, and
`fps_x1000=20000`. It is not a sustained throughput receipt because the
12-frame run is too short for wall-FPS gating.

The receipt must include timing percentiles, whole-run wall throughput,
dropped-frame accounting, wrapper and child-process RSS, storage throughput,
basic CPU load, thermal samples when `vcgencmd` is available, relevant encoder
env knobs, `bench_fused` binary hash and CMake/C flags when available, strict
`.gvid` validation, and interrupted-tail recovery. `verdict.fps_target_met`
requires both `verdict.fps_median_target_met` and
`verdict.fps_wall_target_met`; this prevents a batched writer or deferred final
drain from looking realtime when total capture wall time misses the target.
Receipts also include `writer_handoff`, which separates the loop median FPS
from whole-run wall FPS and records any `async_drain` or `pingpong_drain`
phase emitted by `bench_fused`. A writer variant is not production-ready at
24 fps unless the wall-FPS verdict passes, even if the loop median alone clears
the target. The handoff section also records `target_frame_ms`,
`loop_target_gap_ms`, `wall_target_gap_ms`, and
`bottleneck_target_gap_ms`, so the remaining strict-24 miss is expressed as a
per-frame millisecond gap instead of only as aggregate FPS.
For direct scatter `.gvid` probes, `GPR_BENCH_GVID_COALESCE_PREFIX=1` enables
the visual-neutral write-layout candidate that combines the `.gvid` frame
header with the fused scatter prefix before `writev`. The receipt records this
environment variable so strict-24 target runs can distinguish baseline scatter
from the coalesced-prefix path.
The `--quality`, `--wavelet-levels`, decimation,
and `--pixel-format` arguments are passed through to `bench_fused` as
`FUSED_QUALITY`, `FUSED_WAVELET_LEVELS`, `GPR_COL_DECIMATE`,
`GPR_ROW_DECIMATE`, and `GPR_BENCH_PIXEL_FORMAT` when applicable. Native 12MP
Mission 1 true-Bayer receipts use the FLL2 T2 profile in
`tools/mission1_native12_fll2_t2_profile.py`: `--wavelet-levels 1
--no-decimate --quality 8 --pixel-format 1`, with `FUSED_RAW_LL=1`,
`FUSED_LL_PREDICT=1`, `FUSED_LL_PREDICTOR=avg`,
`FUSED_LL_RICE_KS=7,5,5,5`, `FUSED_REFERENCE_HORIZONTAL=1`,
`FUSED_STRIPE_ROWS=384`, `GPR_INLINE_DENOISE_HARD=1`, and per-band highpass
thresholds `GPR_INLINE_DENOISE_T_LH=2`,
`GPR_INLINE_DENOISE_T_HL=3`, and `GPR_INLINE_DENOISE_T_HH=3`.
The current registered production profile remains T233 because it owns the
20+ fps Pi stand-in evidence and the registered 8K SR checkpoint was trained
against it. T236 is separate boundary evidence for the stricter 24 fps storage
target: it changes the exploratory evidence profile to
`FUSED_LL_RICE_KS=6,6,5,6`, `GPR_INLINE_DENOISE_T_HH=6`, and
`GPR_INLINE_DENOISE_T_CH2_LH=3`, but it is not yet a strict-24 timing pass and
is not the registry production profile. T468 (`LH=4,HL=6,HH=8,CH2_LH=4`) is a
valid speed receipt only, not the production quality profile.
The default storage target is the Lexar Professional SILVER PLUS
SDXC/microSDXC UHS-I 128GB-1TB 205/150 profile: 205 MB/s advertised read and
150 MB/s advertised write. Capture verdicts use the write side with the
configured safety margin, giving a 135 MB/s default payload budget; read speed
is recorded for decode/playback evidence. The 64GB SILVER PLUS microSD SKU is
a different 205/100 profile, so runs on that card must override
`--storage-target-write-mbps 100` and record the exact SKU/capacity. Official
Lexar product pages are the source of truth for the advertised speeds:
`https://americas.lexar.com/product/lexar-professional-silver-plus-sdxc-uhs-i-card/`
and
`https://americas.lexar.com/product/lexar-professional-silver-plus-microsdxc-uhs-i-card/`.
The receipt records the effective bench environment, so the encoded payload and
receipt/container fields match. CI runs only the simulated schema smoke:
`bash tools/test/test_labs_target_bench_smoke.sh`.

`verdict.target_evidence` is intentionally narrower than "not simulated."
The wrapper sets it automatically only on Linux ARM target-like hosts, or when
`--target-evidence` is supplied for an explicitly selected lab target. Local
Mac or workstation runs remain useful correctness/throughput probes, but they
must not be used as Pi 5 / Mission 1 timing evidence.

## Timing-Diagnostic Build

When a target receipt misses 24 fps, rebuild `bench_fused` with the opt-in
timing hooks instead of carrying a scratch source patch:

```bash
cmake -S . -B build-labs-timing \
  -DCMAKE_BUILD_TYPE=Release \
  -DFUSED_TIMING=ON \
  -DFUSED_TIMING_DETAIL=ON
cmake --build build-labs-timing --target bench_fused -j"$(nproc)"
```

`FUSED_TIMING` prints Pass1/Pass2 stage summaries. `FUSED_TIMING_DETAIL`
also prints per-channel unpack, horizontal, vertical/quantize, tokenize, wait,
and other timing. `FUSED_TIMING_DETAIL` implies `FUSED_TIMING` in CMake.
When those lines are present, `tools/run_labs_target_bench.py` records a
structured `fused_timing` object in `labs_target_bench.json` with summarized
`stage_ms`, `channel_component_ms`, `channel_component_by_channel_ms`,
`producer_ms`, and dominant mean-cost keys. This is the reviewer-facing receipt
field for identifying whether the current blocker is unpack, horizontal
filtering, vertical/quantize, tokenization, wait time, Pass2, or producer
overhead.

Diagnostic timing builds are blocker evidence, not production throughput
claims. Keep the production receipt tied to a normal Release build unless the
diagnostic build is explicitly being used to narrow a blocker. The
`tools/run_labs_target_bench.py` receipt stores the `bench_fused` binary hash,
CMake build root, build type, C flags, structured `fused_timing`, and stderr
tail, so timing lines remain attached to the compact JSON evidence.

Target receipts also include `source_provenance`, a deterministic digest of
the source/tool snapshot used by the run. On a Pi or camera stand-in where the
source was copied without `.git`, pass the snapshot root explicitly:

```bash
python3 tools/run_labs_target_bench.py \
  --source-provenance-root /mnt/ssd/gpr_work/worktrees/current_sync_YYYYMMDD \
  ...
```

`repo_commit` remains useful when the target source is a Git checkout, but
production evidence should be reproducible from `source_provenance.sha256`,
`bench.build.binary_sha256`, build flags, runtime environment overrides, and
the retained receipt hash even when `repo_commit` is unavailable.

## Variant Sweep Wrapper

Use `tools/run_labs_perf_sweep.py` for short, reproducible target A/B probes.
It runs multiple `tools/run_labs_target_bench.py` variants into separate
receipt directories and writes a ranked `labs_perf_sweep.json` summary:

```bash
GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts \
python3 tools/run_labs_perf_sweep.py \
  --bench build/bin/bench_fused \
  --raw /path/to/source_bayer.raw \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/labs_perf_sweep_YYYYMMDD \
  --frames 120 \
  --direct-gvid \
  --variant baseline \
  --variant stripe64_defer:FUSED_STRIPE_ROWS=64,FUSED_DEFER_RANS=1
```

Sweep summaries are comparison evidence only. The wrapper records
`production_claim: false`; a sweep winner can promote only after a separate
sustained target receipt proves fps, no drops, valid `.gvid`,
interrupted-tail recovery, timing, memory, and storage behavior.

For native 12MP Mission 1 sweeps, pass the same target-shape flags used by the
corrected sustained timing receipt. Current Mission 1 native 12MP raws are
stored in 16-bit words but contain 14-bit-range sensor values, so use
`--pixel-format 1` (`RGGB14`) for this corpus. The older pixel-format-4 probes
are audit-only and should not be used for production candidate selection.

```bash
python3 tools/run_labs_perf_sweep.py \
  --bench build/bin/bench_fused \
  --raw /path/to/GP017603.raw \
  --frames 300 \
  --target-fps 24 \
  --source-width 4096 \
  --source-height 3072 \
  --capture-width 4096 \
  --capture-height 3072 \
  --quality 3 \
  --wavelet-levels 3 \
  --no-decimate \
  --pixel-format 1 \
  --direct-gvid
```

## Current Gap

The current repo evidence is enough for a Labs prototype conversation, but not
enough for direct firmware readiness. The latest strict Pi 5 stand-in receipt
at commit `0dd6660` proves the container/recovery path on a 14,400-frame run
and is acceptable as conservative 20 fps proxy evidence. It still does not
prove the actual Mission 1 24 fps camera path.

The newer native 12MP Mission 1 receipts change the most likely target shape:
12MP should be captured natively at 4096 x 3072, not produced by downsampling a
50MP sensor frame on the Pi path. Older q3/3-level native-resolution receipts
were quality-blocked by severe decoded visual artifacts and remain historical
timing-only evidence. The current q8 FLL2/T233 true-Bayer profile fixes that
class of blocker for the 20+ fps Pi stand-in floor: it has quality dashboards,
valid `.gvid`, 0-drop receipts, interruption recovery, and conservative
Lexar SILVER PLUS storage-budget evidence. The current all-42 4K Bayer
numbered-list audit supersedes the older per-image timing summary for the
active 20+ fps floor. It is still not final firmware readiness because actual
Mission 1 sensor/DMA/storage handoff remains open; strict 24 fps total timing
is open only if it is reinstated as a hard product requirement.

Historical 50MP/half-res evidence remains below for audit context:

| metric | latest strict Pi 5 receipt |
|---|---|
| receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json` |
| frames | 14,400 requested / 14,400 written |
| drops | 0 |
| median fps | 19.98 fps |
| mean fps | 19.23 fps |
| median encode | 50.04 ms/frame |
| p95 encode | 66.01 ms/frame |
| max encode | 239.47 ms/frame |
| `.gvid` | valid, 14,400 frames, 13.73 GB payload |
| recovery | truncated-tail rejected; 14,399 complete frames recovered |
| memory | wrapper 29.0 MB RSS, child 137.5 MB RSS |
| thermal | 60.9 C start, 75.2 C end |

Additional direct-container probes:

| metric | 2026-06-15 current-head direct `.gvid` default probe |
|---|---|
| receipt | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_default_nodrop_120f_ede0e07_20260615/labs_target_bench.json` |
| commit | `ede0e078eae4a5643efd24b1a6a5ebec4844a826` |
| mode | `--direct-gvid`, default LUT path, highpass-preserving no-drop path |
| frames | 120 requested / 120 written |
| median fps | 21.36 fps |
| median encode+write | 46.83 ms/frame |
| p95 encode+write | 49.44 ms/frame |
| `.gvid` | valid |
| dominant timing | Pass1 mean 37.45 ms; unpack mean 22.37 ms across channel workers |

| metric | 2026-06-15 direct `.gvid` polynomial diagnostic |
|---|---|
| receipt | `/mnt/ssd/gpr_work/artifacts/labs_target_direct_gvid_poly_nodrop_120f_20260615/labs_target_bench.json` |
| mode | `--direct-gvid`, `FUSED_LOG_POLYNOMIAL=ON`, highpass-preserving no-drop path |
| frames | 120 requested / 120 written |
| median fps | 13.39 fps |
| median encode+write | 74.71 ms/frame |
| p95 encode+write | 86.88 ms/frame |
| `.gvid` | valid, 114,392,072 bytes |

| metric | 2026-06-15 luma-pair shared-unpack near miss |
|---|---|
| receipts | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_lumapair_probe_20260615/baseline_120f.json`, `/Volumes/OWC_8TB/gpr_work/artifacts/labs_lumapair_probe_20260615/lumapair_stripe64_defer_120f.json` |
| mode | scratch luma-pair shared unpack, `FUSED_STRIPE_ROWS=64`, `FUSED_DEFER_RANS=1`, direct `.gvid` |
| frames | 120 requested / 120 written |
| baseline median | 45.49 ms / 21.99 fps |
| luma-pair median | 42.48 ms / 23.54 fps |
| luma-pair p95 | 44.23 ms/frame |
| `.gvid` | valid |
| status | best short near miss; below 24 fps target; scratch source not committed |

Current-head direct `.gvid` rehearsal:

| metric | 2026-06-15 current-head direct `.gvid` rehearsal |
|---|---|
| receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_direct_1440f_1b934a4_20260615/labs_target_bench.json` |
| commit | `1b934a41e0e9dee8f2189e67442e310ed6aa866a` |
| frames | 1,440 requested / 1,440 written |
| drops | 0 |
| median fps | 16.00 fps |
| median encode+write | 62.48 ms/frame |
| p95 encode+write | 73.21 ms/frame |
| `.gvid` | valid, 1.43 GB container, interrupted-tail recovery proven |
| target state | performance governor, 2.4 GHz, `throttled=0x0`, SSD ext4 `rw,noatime,stripe=8191` |
| timing receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_current_head_timing_detail_30f_1b934a4_20260615/labs_target_bench.json` |
| timing finding | Pass1 median 38.90 ms, Pass2 median 9.20 ms, unpack mean 22.79 ms |

Corrected pixel-format direct `.gvid` probe:

| metric | 2026-06-15 corrected pixel-format direct `.gvid` probe |
|---|---|
| receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_direct_gvid_pf4_120f_e16357f_20260615/labs_target_bench.json` |
| commit | `e16357f7984315ec86ae5173fded94d057b1030f` |
| mode | `--direct-gvid`, pixel format 4 applied to `bench_fused` encoder context |
| frames | 120 requested / 120 written |
| drops | 0 |
| median fps | 19.85 fps |
| median encode+write | 50.38 ms/frame |
| p95 encode+write | 57.23 ms/frame |
| `.gvid` | valid, interrupted-tail recovery proven |
| timing receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_direct_gvid_pf4_timing_30f_e16357f_20260615/labs_target_bench.json` |
| timing finding | Pass1 median 34.60 ms, Pass2 median 11.60 ms, unpack mean 21.82 ms |

Commit `e16357f` fixed the bench harness so `GPR_BENCH_PIXEL_FORMAT` reaches
the encoder context, not just the `.gvid` header. Pre-fix receipts remain
useful as container and blocker evidence, but they should not be treated as
exact RGGB16 timing evidence when the requested pixel format was 4.

Current-head tracked sweep:

| metric | 2026-06-15 current-head tracked sweep |
|---|---|
| sweep | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_03eaa4d_120f_20260615T112841Z/labs_perf_sweep.json` |
| commit | `03eaa4d1da923d1217dccbc7d98411c606e9a06b` |
| mode | `--direct-gvid`, pixel format 4, q3, 2-level decimate=2 |
| variants | baseline; `FUSED_STRIPE_ROWS=64 FUSED_DEFER_RANS=1` |
| frames | 120 per variant, 0 drops, valid `.gvid`, interrupted-tail recovery proven |
| best variant | baseline |
| best median fps | 21.54 fps |
| best median encode+write | 46.43 ms/frame |
| best p95 encode+write | 52.94 ms/frame |
| stripe64/deferred median | 18.52 fps / 53.99 ms/frame |
| timing receipt | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_target_timing_3c48f2f_30f_20260615T113211Z/labs_target_bench.json` |
| timing finding | Pass1 median 33.5 ms, Pass2 median 11.6 ms, unpack mean 20.6 ms; luma unpack channels 0 and 3 are 22.04 ms and 21.86 ms mean |
| status | below 24 fps target; stripe64/deferred no longer reproduces the older scratch near miss on current head |

Rejected luma-pair handoff candidate:

| metric | 2026-06-15 dirty-source luma-pair handoff sweep |
|---|---|
| sweep | `/Volumes/OWC_8TB/gpr_work/artifacts/pi5_current_head_20260615/labs_perf_sweep_lumapair_dirty_120f_20260615T114724Z/labs_perf_sweep.json` |
| mode | dirty-source opt-in `FUSED_LUMA_PAIR=1`, direct `.gvid`, pixel format 4, q3, 2-level decimate=2 |
| frames | 120 per variant, 0 drops, valid `.gvid`, interrupted-tail recovery proven |
| patched baseline | 20.44 fps / 48.92 ms median |
| luma-pair handoff | 12.05 fps / 83.00 ms median |
| luma-pair handoff + stripe64/deferred | 18.54 fps / 53.94 ms median |
| status | rejected; the channel0 producer/channel3 consumer handoff loses channel parallelism and adds synchronization/copy overhead |

The direct default receipts improve measurement fidelity and rule out the
earlier 13 fps result as a polynomial-log diagnostic, not the default target
path. The current-head 1,440-frame rehearsal is slower than short probes and
confirms that short-run medians cannot be promoted as sustained target
evidence. The luma-pair shared-unpack scratch probe is the strongest short-run
lead so far, but it still does not remove the camera-performance question: the
highpass-preserving half-res path is proxy-acceptable on the strict Pi 5
stand-in receipt, while actual Mission 1 24 fps capture remains unproven.
The fresh luma-pair handoff integration attempt shows that sharing luma work
through a cross-channel row handoff is not the right production shape; any
future shared-luma work must preserve parallel row execution or remove work
inside existing channel workers without forcing channel 3 to wait on channel 0.

Remaining missing receipts:

- actual camera sensor/DMA handoff,
- sustained thermal/power behavior,
- storage behavior on the intended camera media path,
- an actual Mission 1 camera-hardware receipt that proves the half-res encoder
  at >= 24 fps, or identifies the hardware bottleneck.

Until those exist, Pi 5 numbers must be labeled as stand-in evidence.

The current Labs bundle includes the 120-frame Pi 5 stand-in receipt
`receipts/pi5_2k_l2hh_120f_standin.json`; it does not replace the required
10 minute target-style run.
