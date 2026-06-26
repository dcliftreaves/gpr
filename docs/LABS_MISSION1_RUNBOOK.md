# Labs Mission 1 Evidence Runbook

Last refreshed: 2026-06-25

This runbook is the remaining hardware execution path for the Labs `.gvid`
prototype. It converts the current review package from Pi 5 proxy evidence to
actual Mission 1 camera evidence, or produces a blocked receipt with a named
cause.

## Current State

The current Mission 1 numbered-list audit is the top-level snapshot for the
active 4K Bayer `.gvid`, camera-back preview, CNN output, and ProRes review
deliverables:

```bash
python3 tools/mission1_numbered_list_readiness.py \
  --external-root /Volumes/OWC_8TB/gpr_work
```

Audit artifact:
`/Volumes/OWC_8TB/gpr_work/artifacts/mission1_numbered_list_readiness_20260625/readiness.json`.

Current audited results:

- 4K Bayer `.gvid`: 420 frames, 4096 x 3072, zero drops, 24.32 fps whole-run
  wall, 25.29 fps loop median, and conservative Lexar SILVER PLUS write-budget
  pass on the Pi 5 stand-in.
- Selected aggregate Pi closure rerun on 2026-06-25:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_standin_followup/labs_target_bench.json`
  records 1,440 frames, 4096 x 3072, zero drops, valid `.gvid`, 20.50 fps
  whole-run wall, 21.52 fps median loop timing, and the same conservative
  storage-budget pass.
- Stand-in camera-handoff blocker receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/camera_handoff_receipt.json`
  validates the current Pi 5 run, records `firmware_ready=false`, and names the
  remaining blocker as camera sensor/DMA plus camera storage handoff not
  executed.
- Camera-back preview: the same 4096 x 3072 `.gvid` decodes to 1024 x 768 RGB
  at 25.85 fps whole-run wall including extract process, with 36.23 fps median
  decode-plus-target timing.
- Selected aggregate preview rerun:
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_standin_followup/preview_decode_1024x768/receipt.json`
  records 24.20 fps whole-run wall including extract/process and 43.86 fps
  median decode-plus-target timing.
- 4K CNN cleanup and 8K SR: `.gvid` packaging and ProRes review receipts
  exist. The 4K cleanup signoff passes the intended high-res CFA raw guard; the
  older clean-low Bayer comparison is retained as a diagnostic. 8K editable
  packaging, 8K metadata transplant, visual review, and 8K offline-production
  promotion receipts exist for offline/post scope.
- Follow-up target preparation on 2026-06-25 synced the current closure source
  to `192.168.16.67:/mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup`,
  built the closure-path binaries in `build-closure`, and ran
  `test_labs_encoder_api` successfully. The stand-in preflight now passes from
  that tree; the camera-role preflight fails only because the actual camera
  frame source, camera storage path, and camera display path have not been
  asserted/executed.
- The latest camera-role preflight against the required sensor-ring endpoint is
  indexed at
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_sensor_ring_20260625.json`.
  It proves SSH, repo/build paths, writable SSD output/scratch paths, and
  required binaries; it intentionally remains blocked because
  `/dev/mission1/sensor_dma_ring` is not present on the Pi target yet and the
  three real camera assertions have not been executed.
- The narrower source-endpoint probe is indexed at
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_preflight_20260625/source_probe_192_168_16_67_camera_sensor_ring_20260625.json`.
- The latest follow-up source-endpoint probe is indexed at
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_preflight_20260625/source_probe_192_168_16_67_camera_sensor_ring_followup_20260625.json`
  with SHA256
  `1400868bc33fe4da52da3aa17ca588a3775845fcb6ddfd43c19bad111859614d`.
  It repeats the current blocker: SSH works, but
  `/dev/mission1/sensor_dma_ring` is missing and therefore not device-like.
- The latest discovery source-endpoint probe is indexed at
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_preflight_20260625/source_probe_192_168_16_67_discovery_20260625.json`
  with SHA256
  `cd28624fc5865e546df4ebdde87f617b47c3f87d0e284381fe836f41f07ff8fd`.
  It still blocks on the missing `/dev/mission1/sensor_dma_ring`, but records
  29 device-like V4L/media candidates including `pispbe-input`,
  `pispbe-output*`, `pispbe-config`, and `/dev/media*`; DRM display nodes
  including `/dev/dri/card0`, `/dev/dri/card1`, and `/dev/dri/renderD128`;
  and the mounted `/mnt/ssd` ext4 storage path. Treat these as discovery
  candidates for firmware handoff, not as proof that any one node is already a
  raw Bayer frame source.
- Follow-up target capability snapshots are indexed at
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_discovery_20260625/v4l_media_capabilities_192_168_16_67_20260625.txt`
  and
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_discovery_20260625/rpicam_capabilities_192_168_16_67_20260625.txt`.
  The Pi target has `v4l2-ctl`, `media-ctl`, `libcamera-hello`,
  `rpicam-hello`, and `rpicam-raw`. The V4L/media snapshot shows PiSP backend
  nodes with default YU12 1920 x 1080 formats on selected nodes; both
  `rpicam-hello --list-cameras` and `libcamera-hello --list-cameras` report
  `No cameras available!`. That narrows the current closure blocker to camera
  sensor enumeration/handoff, not SSD availability or missing target tooling.
- The structured hardware audit is indexed at
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_discovery_20260625/hardware_audit_192_168_16_67_20260625.json`
  with SHA256
  `0be23aaf6fdc21a331bb29e122a5b51f1013d3e553608c64d2a3b45522fef57d`.
  It records `hardware_ready_for_camera_source=false`,
  `camera_enumerated=false`, zero sensor-like V4L nodes, and one blocker:
  no camera sensor is enumerated by rpicam/libcamera/V4L.
  A non-dry camera-ready host-to-target closure run is also indexed at
  `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/remote_closure_summary.json`.
  That run passed dispatch input validation, failed the required
  `camera_hardware_audit` step with returncode 2, copied back
  `target_closure_package_run.json` and `hardware_audit_receipt.json`, and did
  not run encode, storage, preview, or final collection stages.
  Run the probe first when firmware exposes a Mission camera source endpoint;
  it does not read frames, it only verifies that the endpoint exists and is a
  device-like stream rather than a fixture file.
- A follow-up aggregate stand-in closure run from the same tree wrote 1,440
  frames with valid `.gvid`, zero drops, 20.50 fps whole-run wall, 21.52 fps
  median loop timing, 24.20 fps preview wall, and 43.86 fps median
  decode-plus-target. The heavy generated `.gvid` payloads were removed from
  the Pi after compact receipts were collected.

This proves the active Pi 5 stand-in evidence for the numbered list. It still
does not claim Mission 1 firmware readiness because sensor/DMA input, camera UI
preview integration, and camera storage handoff receipts have not been executed
on the actual camera path.

Historical Pi 5 proxy evidence remains useful for audit context:

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
self-hosted target runner with the actual camera frame source and the real
camera storage writer. The workflow writes:

- `target_preflight_receipt.json`
- `labs_target_bench.json`
- `camera_handoff_receipt.json`
- `camera_closure_run/preview_ui_receipt.json`
- `camera_closure_run/mission1_camera_closure_run.json`
- `labs_target_bench_stdout.txt`

The heavy `.gvid` and frame payloads stay on the external target drive. GitHub
Actions uploads only compact receipts and stdout.

Example dispatch for a real camera handoff using the FLL2 T2 20+ fps profile:

```bash
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
  -f wavelet_levels=1 \
  -f no_decimate=true \
  -f pixel_format=1 \
  -f direct_gvid=true \
  -f bench_binary=bench_fused \
  -f mission1_native12_fll2_profile=true \
  -f storage_target_name="Lexar Professional SILVER PLUS SDXC/microSDXC UHS-I (128GB-1TB)" \
  -f storage_target_read_mbps=205 \
  -f storage_target_write_mbps=150 \
  -f storage_target_safety_margin=0.90 \
  -f storage_target_note="Published 128GB-1TB SILVER PLUS profile: 205 MB/s read, 150 MB/s write; 64GB microSD is 205/100." \
  -f target_name="Mission 1" \
  -f target_role=camera \
  -f raw_source_kind=sensor_dma_capture \
  -f frame_source="sensor DMA" \
  -f memory_ownership="synchronous submit; caller owns input through return" \
  -f write_path="camera storage .gvid path" \
  -f sensor_dma_executed=true \
  -f storage_handoff_executed=true \
  -f storage_medium="Mission 1 SD path" \
  -f storage_ownership="camera firmware owns write buffer through storage completion" \
  -f blocker_cause="none"
```

Use `bench_binary=bench_fused` for production timing evidence. Use
`bench_binary=labs_encoder_bench_cli` when the purpose is to prove the
firmware-facing `gpr_labs_encoder` shim can emit a valid `.gvid` through the
same receipt harness; that shim receipt is integration evidence unless it also
meets the FPS target on the camera runner.

If the run is still file-backed or uses a userland storage stand-in, set:

```bash
-f target_name="Pi 5 stand-in"
-f target_role=stand-in
-f raw_source_kind=file_standin
-f frame_source="file-backed Bayer stand-in"
-f write_path="bench_fused target-bench .gvid path"
-f sensor_dma_executed=false
-f storage_handoff_executed=false
-f storage_medium="target-bench filesystem stand-in"
-f storage_ownership="OS/page-cache writeback; not camera firmware DMA"
-f blocker_cause="camera sensor/DMA or storage handoff not executed"
```

`target_role=camera` is an assertion, not a descriptive label. The receipt
builders now fail fast if camera-role dispatches still use stand-in evidence:
stand-in target names, file-backed frame labels, `bench_fused` write paths,
filesystem/page-cache storage ownership, off-camera preview presentation, or
missing source provenance. Use `target_role=stand-in` until the actual
sensor/DMA, firmware SD writer, rear-display preview path, and visual display
check have all run.
The aggregate closure runner applies the same policy: camera-role runs cannot
use `--simulate-target-bench`, and copied receipts must already have a matching
`target.role=camera`. Stand-in receipts cannot be reused inside a camera-role
closure command. The GitHub Actions dispatch path uses
`tools/check_mission1_camera_dispatch_inputs.py` for the same preflight rule.

## Pass Criteria

`camera_handoff_receipt.json` can claim `verdict.firmware_ready=true` only when
all of these are true:

- `target.role` is `camera`.
- `integration.raw_source_kind` is `sensor_dma_capture` or
  `camera_ring_buffer`.
- `integration.sensor_dma_handoff.executed` is `true`.
- `integration.storage_handoff.executed` is `true`.
- `timing.fps_median >= input_frame.target_fps`.
- `capture.dropped_frames == 0`.
- `.gvid` validation passes.
- interrupted-tail recovery is proven.

For the current native 12MP FLL2 avg7555-fast P2-pin fused path, the local
file-backed stand-in harness form is:

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

The preferred closure path is the one-command target-side package runner. It
validates camera/stand-in labels, runs the camera hardware enumeration audit
for camera-role runs, writes the target preflight receipt, runs the aggregate
closure runner, optionally writes a compact collection receipt, and can remove
heavy transient `.gvid` payloads after receipts are durable:

From the host, use the remote launcher to execute the target-side package over
SSH and collect compact receipts back to the 8TB artifact tree. Start with a
dry run:

```bash
python3 tools/run_mission1_remote_closure_package.py \
  --dry-run \
  --camera-ready \
  --summary-json /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json
```

That dry run is indexed at
`artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json`
and proves the host can invoke the target-side package on `192.168.16.67`.
It is still command-shape evidence only, not production evidence.
The dry-run package now includes a `camera_hardware_audit` step before target
preflight. A real camera-role run must clear that audit first; on the current
Pi target it fails because no camera sensor is enumerated by
rpicam/libcamera/V4L.

The latest real non-dry attempt is preserved as a blocked receipt, not a
production receipt:

```text
artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/remote_closure_summary.json
artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/target_closure_package_run.json
artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/hardware_audit_receipt.json
```

Its exact blocker is `no camera sensor is enumerated by rpicam/libcamera/V4L`.
Until that changes, the Mission 1 camera-source capture and camera-back UI
items remain blocked even though the Pi stand-in encode/preview timing receipts
remain valid.

When the real Mission 1 sensor/DMA, storage writer, and rear display paths are
wired, remove `--dry-run` and keep `--camera-ready`; the launcher will run the
target-side closure package and then call
`tools/collect_mission1_target_closure.py --include-timing-receipts` to copy
compact receipts back to the local artifact root.

Before the full closure run, check the camera source endpoint shape:

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
  --output-json /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_target_preflight_20260625/source_probe_192_168_16_67_camera_sensor_ring_followup_20260625.json
```

```bash
python3 tools/run_mission1_remote_closure_package.py \
  --camera-ready \
  --summary-json /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_run.json
```

This host-side command is preferred for final closure because it launches the
target package on `192.168.16.67`, then copies the compact closure receipts and
timing receipts back to `/Volumes/OWC_8TB/gpr_work/artifacts`.

```bash
python3 tools/run_mission1_target_closure_package.py \
  --output-dir /mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera \
  --collection-output-dir /mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera_compact \
  --repo-root /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup \
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

Use `--dry-run` first to validate the command shape without launching encode or
decode. Do not add `--camera-frame-source-ready`,
`--camera-storage-path-ready`, `--camera-display-path-ready`, or the executed
camera flags until those real camera paths have run.
When `--collection-output-dir` is set, the package runner collects the compact
closure receipts, including `hardware_audit_receipt.json` and
`labs_target_bench.json` so the aggregate validator can prove the handoff and
preview receipts came from the same `.gvid`. With `--include-timing-receipts`,
it also collects
`preview_decode_1024x768/receipt.json` for the numbered-list readiness audit.
A camera-role dry-run launch package for the command above is indexed at
`artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json`.
It is generated from the target-side codex-followup worktree and uses
`/mnt/ssd/...` command paths; the release verifier rejects Mac-local launch
paths. It proves command shape only and includes the camera hardware-audit
gate; it is not camera production evidence.

The lower-level aggregate runner remains useful for debugging because it
validates the capture handoff and preview UI receipts together and writes
`mission1_camera_closure_run.json`:

Before running the aggregate closure command, run the target preflight. This
checks target reachability, repo/build paths, the camera frame source,
scratch/output writeability, and the three operator assertions that distinguish
camera evidence from Pi stand-in evidence. Use fixture `.raw` paths only for
stand-in/debug runs; camera-role runs must use the actual Mission 1 frame
source, such as `/dev/mission1/sensor_dma_ring`.

```bash
python3 tools/mission1_camera_target_preflight.py \
  --target-host 192.168.16.67 \
  --repo-root /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup \
  --raw /dev/mission1/sensor_dma_ring \
  --raw-source-kind sensor_dma_capture \
  --output-dir /mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera \
  --scratch-dir /mnt/ssd/gpr_work/tmp \
  --bench /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/build-closure/source/app/bench_fused/bench_fused \
  --labs-encoder-bench-cli /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/build-closure/bin/labs_encoder_bench_cli \
  --fused-decode-cli /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/build-closure/bin/fused_decode_cli \
  --preview-cli /mnt/ssd/gpr_work/worktrees/current_goal_sync_20260625_codex_followup/build-closure/bin/gvid_preview_rgb_cli \
  --frame-source "sensor DMA ring buffer" \
  --write-path "Mission 1 camera storage writer path" \
  --storage-medium "Mission 1 SD card" \
  --display-surface "Mission 1 rear display" \
  --presentation-path "Mission 1 rear display presentation path" \
  --output-json /mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json
```

Do not add `--camera-frame-source-ready`, `--camera-storage-path-ready`, or
`--camera-display-path-ready` until those real camera paths have run. Once
those flags are set, the preflight requires concrete non-stand-in labels for
the frame source, storage path, and display path.
The aggregate closure run can claim `verdict.production_ready=true` only when
the target preflight reports both `target_preflight_ready=true` and
`camera_closure_possible=true`, the camera handoff receipt reports
`verdict.firmware_ready=true`, and the preview UI receipt reports
`verdict.ui_ready=true`. The direct camera closure runner enforces this
ordering: `--target-role camera` refuses to run unless
`--target-preflight-receipt` is present, camera-role, uses
`sensor_dma_capture` or `camera_ring_buffer`, matches the requested raw
endpoint, and is already ready.

```bash
python3 tools/run_mission1_camera_closure.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera \
  --target-preflight-receipt /mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json \
  --target-name "Mission 1" \
  --target-role camera \
  --target-fps 20 \
  --pixel-format 1 \
  --raw /dev/mission1/sensor_dma_ring \
  --raw-source-kind sensor_dma_capture \
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
  --source-width 4096 \
  --source-height 3072 \
  --capture-width 4096 \
  --capture-height 3072 \
  --quality 8 \
  --wavelet-levels 1 \
  --no-decimate \
  --direct-gvid \
  --use-mission1-fll2-profile

python3 tools/check_mission1_camera_closure_run.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/mission1_camera_closure_run.json
```

After a target run, collect only the compact receipts back to the external
artifact tree and validate them locally:

```bash
python3 tools/collect_mission1_target_closure.py \
  --target-host 192.168.16.67 \
  --remote-dir /mnt/ssd/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera \
  --include-timing-receipts
```

Run the camera-back preview path as a separate receipt. The current stand-in
receipt is a 4096 x 3072 `.gvid` decoded to 1024 x 768 RGB above 20 fps, but
camera readiness requires presentation through the Mission 1 UI/display path:

```bash
python3 tools/build_labs_preview_ui_receipt.py \
  --target-bench labs_target_bench.json \
  --preview-receipt preview_decode_1024x768/receipt.json \
  --output preview_ui_receipt.json
python3 tools/check_labs_preview_ui_receipt.py preview_ui_receipt.json
```

`preview_ui_receipt.json` can claim `verdict.ui_ready=true` only when all of
these are true:

- `target.role` is `camera`.
- `integration.ui_path_executed` is `true`.
- `preview.full_frame_downsample` is `true`.
- `timing.fps_median >= preview.target_fps`.
- `validation.output_valid` is `true`.
- `validation.no_drops` is `true`.
- `validation.visual_checked` is `true` on the camera display.

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

If the preview UI run cannot claim UI readiness, keep
`verdict.ui_ready=false` and set `blocker.cause` to one specific cause:

- `preview_ui_path_not_executed`
- `preview_buffer_ownership_missing`
- `preview_timing_below_target_fps`
- `preview_visual_signoff_missing`
- `preview_output_validation_failed`
- `display_surface_integration_missing`

Attach the compact receipts to the final artifact bundle and update:

- `docs/LABS_READINESS_REVIEW.md`
- `docs/LABS_TARGET_BENCH.md`
- `docs/LABS_ARTIFACT_BUNDLE.md`
- `docs/release_evidence_manifest.json`

Do not promote the Labs package past prototype review until those docs point to
the actual camera target-preflight, handoff, and preview UI receipts, or to
blocked camera/preview receipts with named causes.
