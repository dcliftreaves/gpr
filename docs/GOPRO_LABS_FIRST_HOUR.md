# GoPro Labs First-Hour Evaluation

This is the shortest path for a GoPro/Labs engineer to decide whether the
`.gvid` raw-video prototype is worth taking into camera firmware. It does not
claim Mission 1 firmware readiness by itself. It tells the camera team what to
run, what evidence counts, and what still blocks a production claim.

## Decision In One Page

| question | current answer |
|---|---|
| Is this real editable raw video? | Yes. The target path starts from Bayer frames, freshly encodes per-frame FUSED `.gpr` payloads, and writes them into `.gvid`. Packing original camera `.GPR` files is only a container/storage baseline and does not count as capture success. |
| What is the current capture target? | 4096 x 3072 Bayer source frames into 4096 x 3072 `.gvid`, with a 20+ fps accepted floor for the Pi 5 stand-in and Mission 1 camera-role closure. |
| What is the current preview target? | Decode the same 4096 x 3072 `.gvid` stream to full-frame 1024 x 768 RGB preview at 20+ fps. |
| What has already passed? | Pi 5 stand-in receipts prove 20+ fps native12 `.gvid` encode, zero drops, valid container/recovery, Lexar SILVER PLUS write-budget fit, and 20+ fps 1024 x 768 preview decode. |
| What is still missing? | A camera-role receipt from the real Mission 1 sensor/DMA or camera ring buffer, SD writer, and rear-display path. |

## First-Hour Steps

1. Read the product boundary:

   ```sh
   sed -n '1,180p' docs/LABS_INTAKE.md
   sed -n '1,180p' docs/LABS_FIRMWARE_API.md
   ```

2. Build or stage the target package on the camera-side Linux/RTOS integration
   host. The firmware-facing ABI is:

   ```text
   source/lib/vc5_encoder/gpr_labs_encoder.h
   ```

   Firmware should integrate through that header or an equivalent wrapper, not
   by calling FUSED internals directly.

3. Run the camera-role closure workflow with a real Bayer source endpoint:

   ```sh
   gh workflow run labs-target.yml \
     --ref master \
     -f raw_path=/dev/mission1/sensor_dma_ring \
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
     -f wavelet_levels=1
   ```

   Replace `raw_path` with the real Mission 1 sensor/DMA or camera ring-buffer
   endpoint. A file fixture can validate tools, but it is not camera-role
   evidence.

4. Collect and validate the compact receipts:

   ```sh
   python3 tools/check_labs_camera_handoff_receipt.py \
     /path/to/camera_handoff_receipt.json

   python3 tools/check_mission1_camera_closure_package.py \
     /path/to/closure_package.json
   ```

5. Submit the receipt package through the production capture checker:

   ```sh
   python3 tools/build_production_capture_submission_template.py \
     --output /path/to/submission_template.json

   python3 tools/check_production_capture_submission.py /path/to/submission.json \
     --require-existing-files \
     --path-root /path/to/submission_root \
     --json-out /path/to/audit.json \
     --html-out /path/to/index.html
   ```

## Receipt Must Prove

| field | required value |
|---|---|
| `target.role` | `camera`, not `stand-in` |
| frame source | real sensor/DMA or camera ring-buffer endpoint |
| source dimensions | 4096 x 3072 |
| source fps | >= 20 |
| encode fps | >= 20 |
| preview dimensions | 1024 x 768 |
| preview fps | >= 20 |
| drops | zero, or a named blocker with frame indices and policy |
| storage | SD writer executed, storage medium named, write MB/s recorded, budget passed |
| memory | peak RSS or firmware heap high-water mark recorded |
| output | `.gvid` SHA-256, strict validation pass, interrupted-tail recovery pass |
| provenance | source/tool snapshot hash and build flags recorded |

## What Does Not Count

| shortcut | why it is insufficient |
|---|---|
| Packing original camera `.GPR` files into `.gvid` | It tests the container, not fresh Bayer recompression. |
| Pi 5 stand-in receipt with `target.role=stand-in` | Useful prototype evidence, but not Mission 1 firmware readiness. |
| Desktop CNN/ProRes output | Validates post/review quality, not camera capture or display handoff. |
| A file fixture pretending to be the camera | Useful for deterministic debugging, but it cannot close sensor/DMA ownership or camera timing. |
| Median fps only | The receipt must include whole-run wall fps, percentiles, drops, writer behavior, storage, and memory. |

## If The First Run Blocks

Write a blocked camera handoff receipt instead of a success claim. Name the
blocker as one of:

| blocker | expected evidence |
|---|---|
| capability discovery | unsupported dimensions, bit depth, CFA, fps, or storage target rejected before capture |
| ABI mismatch | header/version/build SHA mismatch between firmware and codec package |
| sensor/DMA handoff | camera endpoint missing, wrong format, bad stride, ownership issue, or timestamp/index discontinuity |
| storage handoff | SD writer unavailable, bandwidth below target, fsync policy missing, or write callback failure |
| display handoff | 1024 x 768 preview decode runs but cannot reach the rear-display path |
| timing | encode/preview/storage below 20 fps with phase timing attached |
| memory | peak RSS/heap exceeds the camera budget |
| validation | `.gvid` parse, decode checksum, metadata, or recovery validation fails |

## Current Source Of Truth

| topic | document |
|---|---|
| Labs recommendation and prototype boundary | [`LABS_INTAKE.md`](LABS_INTAKE.md) |
| Firmware ABI and receipt contract | [`LABS_FIRMWARE_API.md`](LABS_FIRMWARE_API.md) |
| Target timing and stand-in evidence | [`LABS_TARGET_BENCH.md`](LABS_TARGET_BENCH.md) |
| Hardware execution runbook | [`LABS_MISSION1_RUNBOOK.md`](LABS_MISSION1_RUNBOOK.md) |
| Open production requirements | [`PRODUCTION_CAPTURE_REQUIREMENTS.md`](PRODUCTION_CAPTURE_REQUIREMENTS.md) |
| Product scorecard | [`PRODUCT_PILLAR_SCORECARD.md`](PRODUCT_PILLAR_SCORECARD.md) |

