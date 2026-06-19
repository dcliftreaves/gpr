# Labs Mission 1 Evidence Runbook

Last refreshed: 2026-06-17

This runbook is the remaining hardware execution path for the Labs `.gvid`
prototype. It converts the current review package from Pi 5 proxy evidence to
actual Mission 1 camera evidence, or produces a blocked receipt with a named
cause.

## Current State

The Pi 5 proxy package is verified:

```bash
python3 tools/verify_labs_bundle.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/manifest.json
python3 tools/check_labs_camera_handoff_receipt.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/receipts/pi5_proxy_camera_handoff_receipt.json
```

That proxy receipt validates 14,400 frames, 0 drops, valid `.gvid`, and
interrupted-tail recovery at 19.98 fps median. It is enough to continue camera
integration. It is not a firmware-ready claim.

Newer native 12MP Mission 1 still evidence is documented in
`docs/VIDEO_STATUS.md`, `docs/LABS_TARGET_BENCH.md`, and
`docs/LABS_READINESS_REVIEW.md`. The current corrected
Pi 5 stand-in evidence splits into these paths:

- Native camera `.GPR` payloads in `.gvid` are a container/storage baseline
  only. They preserve an already-compressed camera raw payload, carry explicit
  `payload_kind: camera_gpr` metadata/dispatch, and pack 1,440 native 12MP
  frames at 48.83 fps wall rate on the Pi 5 stand-in. They do not prove fresh
  Bayer recompression.
- Native 12MP FLL2 T2 fused re-encode is the current true Bayer
  recompression candidate. It starts from Bayer pixels, uses q8 exact
  predictive LL plus hard T2 highpass dead-zone, and clears the active 20+ fps
  floor on all three native 12MP Mission 1 examples with valid `.gvid`, zero
  drops, interrupted-tail recovery, and the conservative Lexar SILVER PLUS
  128GB-1TB 205/150 write budget with 0.90 margin. The compact profile is
  `tools/mission1_native12_fll2_t2_profile.py`.
- Older native 12MP q3, 3-level multi-level fused receipts remain timing-only
  evidence. A decoded visual audit found severe native-resolution fused
  roundtrip artifacts, so those receipts are not production quality evidence.

Do not use the older pixel-format-4 recipe for current native 12MP Mission 1
raws.

Actual Mission 1 still `.GPR` source files are available locally at:

```text
/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P
```

Inventory receipt:
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616/media_summary.json`.
The corpus contains 42 Mission 1 50MP triples and 3 native 12MP Mission 1
triples. Use the 4096 x 3072 native 12MP raws for the capture target receipt;
use the 8192 x 6144 files for still quality and optional upres training.

## Required Mission 1 Run

Run the actual Bayer recompression handoff on a self-hosted target runner with
the camera frame source. The receipt must show that Bayer pixels are freshly
compressed to native 4096 x 3072 raw and that the output passes quality and
timing. The native camera payload path below is retained only as the
container/storage baseline.

The native-payload tool sequence is:

```bash
python3 tools/gvid_metadata.py from-native-gpr-sequence \
  /mnt/ssd/gpr_work/fixtures/mission1_gpr \
  /mnt/ssd/gpr_work/artifacts/mission1_native_gpr/native12.gvid.meta.json \
  --width 4096 \
  --height 3072 \
  --fps 24

python3 tools/gvid_pack.py \
  /mnt/ssd/gpr_work/fixtures/mission1_gpr \
  /mnt/ssd/gpr_work/artifacts/mission1_native_gpr/native12.gvid \
  --width 4096 \
  --height 3072 \
  --fps 24 \
  --quality 0 \
  --pixel-format 1 \
  --payload-kind camera_gpr \
  --metadata /mnt/ssd/gpr_work/artifacts/mission1_native_gpr/native12.gvid.meta.json

python3 tools/gvid_metadata.py runtime-dispatch \
  /mnt/ssd/gpr_work/artifacts/mission1_native_gpr/native12.gvid.meta.json \
  --gvid /mnt/ssd/gpr_work/artifacts/mission1_native_gpr/native12.gvid \
  --output /mnt/ssd/gpr_work/artifacts/mission1_native_gpr/native12.gvid.dispatch.json
```

The FLL2 avg7555-fast P2-pin fused-target workflow is the current true Bayer
recompression path for the 20+ fps Pi 5 / Mission 1 stand-in floor. The profile
checker records the exact environment, bench arguments, and validation
thresholds:

```bash
python3 tools/mission1_native12_fll2_t2_profile.py describe
python3 tools/mission1_native12_fll2_t2_profile.py validate \
  --quality-summary /Volumes/OWC_8TB/gpr_work/artifacts/mission1_fll2_T2_native12_quality_20260617/summary.json \
  --target-summary /Volumes/OWC_8TB/gpr_work/artifacts/mission1_fll2_avg7555_fast_pinp2_native12_1440f_20fps_20260617/native12_1440f_20fps_summary.json
```

For one target raw on the Pi stand-in, generate the exact benchmark command:

```bash
python3 tools/mission1_native12_fll2_t2_profile.py command \
  --bench /mnt/ssd/gpr_work/build_mission1_fll2_20260617/source/app/bench_fused/bench_fused \
  --raw /mnt/ssd/mission1_native12/GP017602.raw \
  --output-dir /mnt/ssd/gpr_work/artifacts/mission1_fll2_avg7555_fast_pinp2_GP017602_1440f_20fps \
  --tmpdir /mnt/ssd/gpr_work/tmp
```

The actual camera handoff still needs sensor/DMA and camera storage integration
evidence. For that path, run `.github/workflows/labs-target.yml` on a
Run `.github/workflows/labs-target.yml` on a self-hosted target runner with the
actual camera frame source and the real camera storage writer. The workflow
writes:

- `labs_target_bench.json`
- `camera_handoff_receipt.json`
- `labs_target_bench_stdout.txt`

The heavy `.gvid` and frame payloads stay on the external target drive. GitHub
Actions uploads only compact receipts and stdout.

Example dispatch for a real camera handoff using the FLL2 T2 20+ fps profile:

```bash
gh workflow run labs-target.yml \
  --ref master \
  -f raw_path=/mnt/ssd/gpr_work/fixtures/mission1/GP017601.raw \
  -f output_dir=/mnt/ssd/gpr_work/artifacts/labs_target_bench_mission1_native12 \
  -f scratch_dir=/mnt/ssd/gpr_work/tmp \
  -f source_provenance_root=/mnt/ssd/gpr_work/worktrees/current_sync_YYYYMMDD \
  -f frames=14400 \
  -f target_fps=20 \
  -f source_width=4096 \
  -f source_height=3072 \
  -f capture_width=4096 \
  -f capture_height=3072 \
  -f quality=8 \
  -f wavelet_levels=1 \
  -f no_decimate=true \
  -f pixel_format=1 \
  -f direct_gvid=true \
  -f mission1_native12_fll2_profile=true \
  -f storage_target_name="Lexar Professional SILVER PLUS SDXC/microSDXC UHS-I (128GB-1TB)" \
  -f storage_target_read_mbps=205 \
  -f storage_target_write_mbps=150 \
  -f storage_target_safety_margin=0.90 \
  -f storage_target_note="Published 128GB-1TB SILVER PLUS profile: 205 MB/s read, 150 MB/s write; 64GB microSD is 205/100." \
  -f target_name="Mission 1" \
  -f target_role=camera \
  -f frame_source="sensor DMA" \
  -f memory_ownership="synchronous submit; caller owns input through return" \
  -f write_path="camera storage .gvid path" \
  -f sensor_dma_executed=true \
  -f storage_handoff_executed=true \
  -f storage_medium="Mission 1 SD path" \
  -f storage_ownership="camera firmware owns write buffer through storage completion" \
  -f blocker_cause="none"
```

If the run is still file-backed or uses a userland storage stand-in, set:

```bash
-f target_name="Pi 5 stand-in"
-f target_role=stand-in
-f frame_source="file-backed Bayer stand-in"
-f write_path="bench_fused target-bench .gvid path"
-f sensor_dma_executed=false
-f storage_handoff_executed=false
-f storage_medium="target-bench filesystem stand-in"
-f storage_ownership="OS/page-cache writeback; not camera firmware DMA"
-f blocker_cause="camera sensor/DMA or storage handoff not executed"
```

## Pass Criteria

`camera_handoff_receipt.json` can claim `verdict.firmware_ready=true` only when
all of these are true:

- `target.role` is `camera`.
- `integration.sensor_dma_handoff.executed` is `true`.
- `integration.storage_handoff.executed` is `true`.
- `timing.fps_median >= input_frame.target_fps`.
- `capture.dropped_frames == 0`.
- `.gvid` validation passes.
- interrupted-tail recovery is proven.

For the current native 12MP FLL2 avg7555-fast P2-pin fused path, the local harness
form is:

```bash
FUSED_PIN=1 \
FUSED_PIN_P2=1 \
GPR_INCLUDE_LL=1 \
FUSED_RAW_LL=1 \
FUSED_LL_PREDICT=1 \
FUSED_LL_PREDICTOR=avg \
FUSED_LL_RICE_KS=7,5,5,5 \
FUSED_LL_RICE_FAST=1 \
FUSED_LL_ASSUME_U16=1 \
FUSED_INLINE_TOKENIZE=1 \
FUSED_DEFER_RANS=1 \
GPR_BENCH_GVID_SCATTER=1 \
FUSED_REFERENCE_HORIZONTAL=1 \
FUSED_STRIPE_ROWS=384 \
GPR_INLINE_DENOISE_HARD=1 \
GPR_INLINE_DENOISE_T_LH=2 \
GPR_INLINE_DENOISE_T_HL=3 \
GPR_INLINE_DENOISE_T_HH=3 \
python3 tools/run_labs_target_bench.py \
  --bench build/bin/bench_fused \
  --raw /mnt/ssd/gpr_work/fixtures/mission1/GP017601.raw \
  --frames 1440 \
  --target-fps 20 \
  --source-width 4096 \
  --source-height 3072 \
  --capture-width 4096 \
  --capture-height 3072 \
  --quality 8 \
  --wavelet-levels 1 \
  --no-decimate \
  --pixel-format 1 \
  --direct-gvid \
  --source-provenance-root /mnt/ssd/gpr_work/worktrees/current_sync_YYYYMMDD \
  --output-dir /mnt/ssd/gpr_work/artifacts/labs_target_bench_mission1_native12
```

Validate locally after downloading the compact artifact:

```bash
python3 tools/check_labs_camera_handoff_receipt.py camera_handoff_receipt.json
python3 tools/test/check_labs_target_receipts.py
```

## Blocked Criteria

If the camera run cannot claim firmware readiness, keep
`verdict.firmware_ready=false` and set `blocker.cause` to one specific cause:

- `sensor_dma_integration_missing`
- `storage_handoff_missing`
- `storage_path_below_target_fps`
- `thermal_or_power_throttle`
- `memory_budget_exceeded`
- `codec_timing_below_target_fps`
- `output_validation_failed`
- `interruption_recovery_failed`

Attach the compact receipts to the final artifact bundle and update:

- `docs/LABS_READINESS_REVIEW.md`
- `docs/LABS_TARGET_BENCH.md`
- `docs/LABS_ARTIFACT_BUNDLE.md`
- `docs/release_evidence_manifest.json`

Do not promote the Labs package past prototype review until those docs point to
the actual camera receipt or to the blocked camera receipt with the named cause.
