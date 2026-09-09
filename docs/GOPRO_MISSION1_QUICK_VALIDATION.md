# GoPro Mission 1 Quick Validation

Last refreshed: 2026-06-28

This is the shortest hardware-side path for a GoPro employee to determine
whether the current `.gvid` Mission 1 prototype is ready for firmware/Labs
integration. It assumes access to a Mission 1 development environment that can
expose raw 4096 x 3072 Bayer frames through a sensor DMA or camera ring-buffer
endpoint.

The repo already proves the Pi 5 stand-in path for the active 20 fps floor.
The remaining proof must come from the real camera source, storage writer, and
rear-display preview path. If those are not available, use the stand-in and
simulator sections below; they are useful profiling evidence, not production
camera evidence.

## Five-Minute Decision Tree

1. If the camera can expose a raw Bayer stream, run the one-command quick
   validation.
2. If the quick validation stops at the source probe, the blocker is camera
   source exposure.
3. If the source probe passes, the runner continues through the closure
   package and receipt validators.
4. If closure fails, keep the blocked receipt; the blocker should name source,
   storage, display, timing, memory, or validation.
5. If no camera stream exists, stop the camera claim and continue with the
   stand-in/simulator work below.

## One-Command Camera Validation

Run this on the Mission 1 development target after the repo and `build-closure`
tools have been staged:

```bash
python3 tools/run_gopro_mission1_quick_validation.py \
  --output-dir /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera \
  --collection-output-dir /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera_compact \
  --repo-root /mnt/ssd/gpr_work/worktrees/current_goal_sync \
  --raw /dev/mission1/sensor_dma_ring
```

This writes `quick_validation.json`, `source_probe.json`,
`camera_handoff_receipt.json`, `preview_ui_receipt.json`, and
`mission1_camera_closure_run.json`. The runner stops early if the camera source
probe fails, then records the failing step in `quick_validation.json`.

Dry-run mode is available for command review only:

```bash
python3 tools/run_gopro_mission1_quick_validation.py --dry-run
```

Dry-run output is not production evidence.

## Portable Handoff Bundle

Before sending the repo to a firmware reviewer, build the compact handoff
bundle. It packages one decode-checked 4096 x 3072 `.gvid` sample, compact stand-in
receipts, the quick-validation dry-run receipt, visual review assets, checksums,
and the firmware-facing docs:

```bash
python3 tools/build_gopro_mission1_handoff_bundle.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_handoff_bundle_current \
  --force \
  --ci-run "https://github.com/dcliftreaves/gpr/actions/runs/<run-id>" \
  --fused-decode-cli build-local/bin/fused_decode_cli \
  --require-sample-decode
```

Verify it before sharing:

```bash
python3 tools/verify_labs_bundle.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_handoff_bundle_current/manifest.json
```

The bundle remains stand-in evidence unless a GoPro employee replaces the
included receipts with camera-role receipts from the actual Mission 1
sensor/DMA, storage writer, and rear display path.

## Required Camera Inputs

| input | expected value |
|---|---|
| raw source | device/stream path for Mission 1 Bayer frames, for example `/dev/mission1/sensor_dma_ring` |
| raw source kind | `sensor_dma_capture` or `camera_ring_buffer` |
| source dimensions | 4096 x 3072 |
| stride | normally 8192 bytes for unpacked 16-bit rows |
| bit depth | camera-declared raw bit depth, typically 14 or 16 in the receipt |
| pixel format | explicit Bayer pixel format; do not infer it from payload size |
| storage path | actual camera SD/storage writer path |
| display path | actual Mission 1 rear display/compositor path |

## Quick Camera Probe

Run this first. It should not encode frames; it only confirms that the raw
camera endpoint exists and looks like a device-backed stream.

```bash
python3 tools/mission1_camera_source_probe.py \
  --target-host 192.168.16.67 \
  --target-name "Mission 1" \
  --target-role camera \
  --raw /dev/mission1/sensor_dma_ring \
  --raw-source-kind sensor_dma_capture \
  --source-width 4096 \
  --source-height 3072 \
  --stride-bytes 8192 \
  --bit-depth 14 \
  --pixel-format 1 \
  --output-json /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/source_probe.json
```

Pass condition:

```bash
python3 tools/check_mission1_camera_source_probe.py \
  /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/source_probe.json
```

If this fails because the raw endpoint is missing, the current blocker is
camera source exposure. The codec should not be evaluated as camera-ready yet.

## Quick Closure Run

After the source probe passes, run the full closure package. This validates the
camera-role target preflight, 4K Bayer `.gvid` encode, storage handoff,
1024 x 768 preview decode, preview UI receipt, and aggregate closure receipt.

```bash
python3 tools/run_mission1_target_closure_package.py \
  --output-dir /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera \
  --collection-output-dir /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera_compact \
  --repo-root /mnt/ssd/gpr_work/worktrees/current_goal_sync \
  --raw /dev/mission1/sensor_dma_ring \
  --scratch-dir /mnt/ssd/gpr_work/tmp \
  --bench build-closure/source/app/bench_fused/bench_fused \
  --labs-encoder-bench-cli build-closure/bin/labs_encoder_bench_cli \
  --fused-decode-cli build-closure/bin/fused_decode_cli \
  --preview-cli build-closure/bin/gvid_preview_rgb_cli \
  --target-name "Mission 1" \
  --target-role camera \
  --raw-source-kind sensor_dma_capture \
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
  --use-mission1-fll2-profile \
  --camera-frame-source-ready \
  --camera-storage-path-ready \
  --camera-display-path-ready \
  --sensor-dma-executed \
  --storage-handoff-executed \
  --ui-path-executed \
  --visual-checked \
  --frame-source "sensor DMA" \
  --write-path "Mission 1 camera storage .gvid path" \
  --storage-medium "Mission 1 SD path" \
  --storage-ownership "camera firmware owns write buffer through storage completion" \
  --display-surface "Mission 1 rear display" \
  --presentation-path "Mission 1 rear display presentation path" \
  --cleanup-heavy
```

Validate the resulting receipts:

```bash
python3 tools/check_labs_camera_handoff_receipt.py \
  /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera/camera_handoff_receipt.json

python3 tools/check_labs_preview_ui_receipt.py \
  /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera/preview_ui_receipt.json

python3 tools/check_mission1_camera_closure_run.py \
  /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera/mission1_camera_closure_run.json
```

Production-ready camera evidence requires:

- `target.role=camera`
- `raw_source_kind=sensor_dma_capture` or `camera_ring_buffer`
- sensor/DMA handoff executed
- storage handoff executed
- preview UI/display path executed
- zero dropped frames
- valid `.gvid`
- 20 fps or better on the active Mission 1 floor
- interrupted-tail recovery proven

## If The Camera Fails

Keep the compact JSON receipts. The expected blocker names are:

- source endpoint missing or wrong shape
- DMA/frame ownership mismatch
- storage handoff not executed
- display/UI handoff not executed
- frame timing below target
- memory high-water mark too high
- `.gvid` validation failure
- visual preview/output failure

Do not relabel a stand-in, FIFO simulator, or file-backed run as camera
evidence. The validators intentionally reject that.

## What We Can Do Without A Mission 1 Dev Kit

Without camera-source access, the remaining productive work is:

| workstream | value | camera-ready claim? |
|---|---|---|
| Pi 5 file-backed 4K Bayer encode | keeps codec timing, storage budget, recovery, and `.gvid` validity covered | no |
| deterministic DMA source simulator | replays source cadence, jitter, and backpressure profiles with separate producer/consumer processes | no |
| deterministic source-to-encoder harness | feeds FIFO-produced Mission 1-shaped Bayer frames into the real Labs encoder shim and validates the `.gvid` | no |
| 1024 x 768 preview decode | keeps the camera-back preview algorithm above the 20 fps floor on stand-in hardware | no |
| `.gvid` conformance and recovery tests | protects container correctness and interrupted-file behavior | no |
| 4K cleanup and 8K SR dashboards | improves offline/Mac post quality and keeps CNN promotion evidence current | no |
| docs, release manifest, and artifact hygiene | keeps the handoff package reviewable and reproducible | no |

The deterministic source simulator is the best substitute for camera-source
profiling until GoPro can provide real DMA timings:

```bash
python3 tools/mission1_dma_source_sim.py \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/mission1_dma_source_sim/current/receipt.json \
  --work-dir /Volumes/OWC_8TB/gpr_work/tmp/mission1_dma_source_sim \
  --source-width 4096 \
  --source-height 3072 \
  --frames 240 \
  --target-fps 20 \
  --delay-pattern-ms 0,0.5,0,1.0
```

When real Mission 1 source timings become available, replay those delay
profiles through the simulator and compare producer lateness, consumer wait,
inter-frame jitter, and complete-frame delivery against the camera receipt.

## Next Best Non-Camera Work

1. Keep the 4K Bayer `.gvid` encoder and 1024 x 768 preview path green on Pi 5
   stand-in tests.
2. Run the deterministic simulated-source-to-encoder harness on the Pi 5 for
   longer frame counts and compare it with the file-backed encoder receipts.
3. Keep 4K cleanup and 8K SR review dashboards current against Mission 1,
   Z8, X2D, and iPhone fixture compatibility.
4. Maintain release evidence manifests and artifact hashes so a GoPro reviewer
   can verify exactly which receipts support each claim.
5. Keep the main branch CI green and reject any receipt that blurs stand-in
   evidence with camera evidence.
