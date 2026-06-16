# Labs Mission 1 Evidence Runbook

Last refreshed: 2026-06-15

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

Actual Mission 1 still `.GPR` source files are available locally at:

```text
/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P/GoProMission1
```

Inventory receipt:
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_source_inventory_20260615/summary.json`.
The folder contains 40 Mission 1 `.GPR` files at 8192 x 6144, 16-bit RGGB,
plus 4 older HERO10 files that should not be mixed into Mission 1 target
receipts. `GP017517.GPR` decodes through the current `gpr_tools` GPR->RAW path
to a 100,663,296 byte Bayer file with SHA-256
`8ab2a9772cc813b2036e30c122315ae605111ef2c14be6dab004c5de5ad44f03`.
The `DNG/` subdirectory contains 40 matching Mission 1 DNG conversions plus
2 HERO10 DNGs. Those Mission 1 DNGs expose useful sidecar metadata: black level
16, white level 16383, 16-bit RGGB, JPEG raw compression, four gain-map
opcodes, and DNG `NoiseProfile`. `GP017517.dng` also decodes to RAW, but it is
not byte-identical to the camera `.GPR` extraction: 88.2% of pixels match and
the rest are exactly one count lower, so use camera `.GPR` -> RAW for timing
receipts and use the DNG sidecar for metadata/noise-profile work. The current
`gpr_tools` parameter dump and DNG->GPR encode paths still throw
`dng_exception` on Mission 1 files, so editable-DNG metadata compatibility
remains a separate fix.

## Required Mission 1 Run

Run `.github/workflows/labs-target.yml` on a self-hosted target runner with the
actual camera frame source. The workflow writes:

- `labs_target_bench.json`
- `camera_handoff_receipt.json`
- `labs_target_bench_stdout.txt`

The heavy `.gvid` and frame payloads stay on the external target drive. GitHub
Actions uploads only compact receipts and stdout.

Example dispatch for a real camera handoff:

```bash
gh workflow run labs-target.yml \
  --ref master \
  -f raw_path=/mnt/ssd/gpr_work/fixtures/mission1_frame_source.raw \
  -f output_dir=/mnt/ssd/gpr_work/artifacts/labs_target_bench_mission1 \
  -f scratch_dir=/mnt/ssd/gpr_work/tmp \
  -f frames=14400 \
  -f target_fps=24 \
  -f source_width=8192 \
  -f source_height=6144 \
  -f capture_width=8192 \
  -f capture_height=6144 \
  -f quality=3 \
  -f pixel_format=4 \
  -f target_name="Mission 1" \
  -f target_role=camera \
  -f frame_source="sensor DMA" \
  -f memory_ownership="synchronous submit; caller owns input through return" \
  -f write_path="camera storage .gvid path" \
  -f sensor_dma_executed=true \
  -f blocker_cause="none"
```

If the run is still file-backed rather than sensor/DMA-backed, set:

```bash
-f target_name="Pi 5 stand-in"
-f target_role=stand-in
-f frame_source="file-backed Bayer stand-in"
-f sensor_dma_executed=false
-f blocker_cause="camera sensor/DMA handoff not executed"
```

## Pass Criteria

`camera_handoff_receipt.json` can claim `verdict.firmware_ready=true` only when
all of these are true:

- `target.role` is `camera`.
- `integration.sensor_dma_handoff.executed` is `true`.
- `timing.fps_median >= input_frame.target_fps`.
- `capture.dropped_frames == 0`.
- `.gvid` validation passes.
- interrupted-tail recovery is proven.

Validate locally after downloading the compact artifact:

```bash
python3 tools/check_labs_camera_handoff_receipt.py camera_handoff_receipt.json
python3 tools/test/check_labs_target_receipts.py
```

## Blocked Criteria

If the camera run cannot claim firmware readiness, keep
`verdict.firmware_ready=false` and set `blocker.cause` to one specific cause:

- `sensor_dma_integration_missing`
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
