# Production 100 Percent Plan

Last refreshed: 2026-07-02

This is the operational checklist for getting the four-pillar GPR goal from the
current 83 percent production-readiness estimate to 100 percent. The rule is
simple: a row is done only when its evidence exists, validates with the listed
commands, and is linked from the product scorecard or release evidence manifest.

## Current State

| pillar | current | 100 percent requires |
|---|---:|---|
| Best RAW stills | 92% | Mission 1 and iPhone strict-provenance darkframe sidecars before broad nonzero camera-noise removal/addback is claimed. |
| GoPro RAW video MVP | 80% | Real Mission 1 camera-role receipts from sensor/DMA or camera ring-buffer input, SD writer, rear display, valid `.gvid`, 120+ sustained frames, zero drops, timing, memory, and storage. |
| Premium still/SR | 60% | A no-REF 50 MP / 100 MP candidate that beats the current still baseline and clears worst-row, editor-latitude, timing, memory, checkpoint, and exact-sidecar-only noise-policy gates. |
| RAW video reconstruction improvement | 100% | Keep the approved 4K cleanup and 8K SR receipt set green; do not reopen it for PSF/blur research unless a replacement already beats the locked baseline with the same artifact surface. |

## 100 Percent Gate Queue

This is the unambiguous execution queue. Work should always start at the first
gate whose `status` is not `closed`, unless a gate is explicitly marked
`blocked_on_external_input`. A gate can move only by creating or validating the
named receipt. A dashboard, model run, or note that does not feed one of these
receipts is not progress toward 100 percent.

| gate | status | exact next command | receipt that moves the gate | closed only when |
|---|---|---|---|---|
| A: Premium still-SR promotion | open, local | `python3 tools/build_premium_still_sr_candidate_preflight_template.py --output /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_preflight_<date>/candidate_preflight.json`, then edit the manifest with a concrete material source/architecture/degradation change and run `python3 tools/build_premium_still_sr_launch_packet.py --manifest /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_preflight_<date>/candidate_preflight.json --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_launch_packet_<date> --require-launchable` | `premium_still_sr_promotion_receipts` | Launch preflight passes, X2D and Z8 smoke holdouts beat same-color Bayer interpolation, full 50 MP / 100 MP gate passes, worst-row recovery is nonnegative, editor-latitude review opens, timing/memory/checkpoint hashes exist, and `check_production_capture_submission.py` passes. |
| B: Mission/iPhone noise sidecars | open, sample/provenance | `python3 tools/build_stills_capture_request.py --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_<date>` and then, only after true darkframe files/provenance exist, run the `build_darkframe_candidate_audit.py`, `check_darkframe_source_provenance.py`, and `build_camera_noise_calibration.py --require-source-provenance` commands listed below. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` | Mission 1 and iPhone each have four same-camera/same-ISO true no-scene-signal CFA frames, source/extraction hashes, `no_scene_signal=true` provenance, and production-ready `gpr.camera_noise_calibration.v1` sidecars. |
| C: Mission 1 camera-role raw-video MVP | blocked_on_external_camera_role | `python3 tools/run_gopro_mission1_quick_validation.py --target-role camera --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_validation_<date>` on real Mission 1 firmware/hardware. | `mission1_camera_role_receipts` | Real sensor/DMA or camera ring-buffer source, actual SD/storage writer, actual rear display, valid `.gvid`, zero drops, 4096 x 3072 source, 1024 x 768 preview, 20+ fps source/encode/preview, memory receipt, and 120+ sustained frames validate. |
| D: Locked raw-video reconstruction | closed, protect | `python3 tools/test/check_product_lock_ledger.py && python3 tools/test/check_readme_product_pillars.py && python3 tools/test/check_release_evidence_manifest.py` | existing 4K cleanup and 8K SR release receipts | The approved 4K cleanup and 8K SR receipt set remains green. PSF/blur or replacement SR work is optional research and cannot reopen this gate by itself. |

Default rule for a work session: if Gate C cannot run because there is no real
Mission 1 camera-role access, spend local compute on Gate A. If Gate A cannot
launch because the proposal fails preflight, update the rejection evidence and
move to Gate B capture/provenance packaging. Do not run raw-video SR research
while Gate A or Gate B has a local next command.

## Execution Order

| order | lane | owner | can move now? | completion evidence |
|---:|---|---|---|---|
| 1 | Premium still/SR promotion | CNN researcher | yes | `premium_still_sr_promotion_receipts` validates through the production submission checker, with no REF/source/JPEG image content at render time. |
| 2 | Mission/iPhone camera-noise sidecars | sample curator | partly; capture/provenance may need new samples | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` validate with four same-camera/same-ISO no-scene-signal CFA frames and unique provenance-ready raw hashes. |
| 3 | Mission 1 camera-role raw-video closure | GoPro firmware engineer | no, requires real Mission 1 camera-role access | `mission1_camera_role_receipts` validates with real camera source/storage/display receipts and 120+ sustained frames. |
| 4 | Locked raw-video reconstruction | release owner | protect only | Existing 4K cleanup and 8K SR receipts, dashboards, ProRes media, editable raw outputs, hashes, registry, and CI remain valid. |

## Active Burn-Down State

These are the only rows allowed to move the current 83 percent production suite
toward 100 percent. Anything else is maintenance unless it repairs a failing
receipt, failing CI, or a broken public artifact.

| row | current status | next unambiguous action | done when |
|---|---|---|---|
| Premium still/SR | Open. The teacher-first smoke candidate is rejected: X2D median MAE recovery was `+0.0038058604915690002%`, Z8 median MAE recovery was `-0.16182462980465134%`, and the 97-receipt scoreboard still has 0 promotable receipts. The rejected relaunch guard now blocks `teacher_first_fullframe_raw_sr_smoke_v1` and the reused X2D/Z8 smoke output directories before another long run can start. | Launch a materially different no-REF candidate only after the preflight proves it is not another scalar-loss/local-residual rerun or rejected teacher-first relaunch. | The candidate beats the still baseline on 50 MP and 100 MP holdouts, has nonnegative worst-row recovery, records timing/memory/checkpoint hashes, and passes production submission validation. |
| Mission/iPhone noise sidecars | Open. The refreshed review packet has 29 candidate sources, extracted Bayer receipts for 2 Mission 1 frames and 4 iPhone candidates, and `production_sidecar_ready=false`. The blocker audit confirms the known Mission source root has 49 unique frame stems and no extra GPR-only frames. | For Mission 1, capture two more matching ISO232 RGGB true darkframes or recapture a fresh four-frame stack. For iPhone, confirm no-scene provenance for four ISO1250 RGGB CFA candidates or recapture true darkframes. | Both `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` pass `check_darkframe_source_provenance.py` with `minimum-count 4`, then `build_camera_noise_calibration.py --require-source-provenance`, then `check_production_capture_submission.py`. |
| Mission 1 camera-role video MVP | Externally blocked. Pi 5 stand-ins are good enough for the current handoff, but they do not prove Mission 1 firmware production. | Give GoPro/Mission 1 firmware owners the first-hour runbook and require a camera-role run from real sensor/DMA or camera ring-buffer source, SD writer, and rear display. | Camera-role receipts validate with 4096 x 3072 source, 1024 x 768 preview, 20+ fps source/encode/preview, zero drops, valid `.gvid`, actual storage medium, memory, and 120+ sustained frames. |
| Raw-video reconstruction | Closed for this release. Approved 4K cleanup and 8K SR are locked. | Keep the release evidence manifest and lock ledger green. | No reopened SR/PSF work is needed unless a locked receipt fails or a replacement already beats the same full artifact surface. |

## Step 1: Premium Still/SR Promotion

Goal: make the slow, spend-compute-for-quality still path real, not just
experimental.

Required evidence:

- Candidate runtime inputs include `candidate_raw` and `camera_metadata`.
- Runtime inputs exclude `REF`, `source_raw`, `source_rgb`, `source_hf`, JPEG/JPG targets, and gate metrics.
- Candidate is materially different from the failed scalar-loss, stored-HF,
  same-color pair, simple capacity, frame-stat, and global-context probes.
- Candidate id and smoke output paths are new; the preflight rejects
  `teacher_first_fullframe_raw_sr_smoke_v1` and the committed 20260702
  teacher-first X2D/Z8 smoke directories.
- Candidate uses a plausible restoration teacher or clean-source/CFA-aware
  objective with camera conditioning and realistic RAW degradation.
- 50 MP and 100 MP gates have positive median MAE/RMSE recovery.
- Worst-row 50 MP and 100 MP recovery is nonnegative, with no severe tone or
  texture failures.
- Editor-latitude review opens and remains useful as editable raw.
- Timing and memory receipts record seconds/frame and peak RSS.
- Exact-sidecar-only noise policy passes; source residual noise is forbidden.

Commands:

```bash
python3 tools/build_premium_still_sr_candidate_preflight_template.py \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_preflight_<date>/candidate_preflight.json

python3 tools/check_premium_still_sr_candidate_preflight.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_preflight_<date>/candidate_preflight.json

python3 tools/build_premium_still_sr_launch_packet.py \
  --manifest /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_candidate_preflight_<date>/candidate_preflight.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_launch_packet_<date> \
  --require-launchable

python3 tools/build_premium_still_sr_gate_receipt.py \
  --help

python3 tools/check_production_capture_submission.py /path/to/submission.json \
  --require-existing-files \
  --path-root /path/to/submission_root
```

Stop condition:

- Promote only if the production submission checker passes and the scorecard
  can move `premium_still_sr` to 100 percent.
- If it fails, stop only after the failure is assigned to data/teacher mismatch,
  objective, crop/full-image context, camera conditioning, model capacity,
  timing/memory infeasibility, or noise/degradation mismatch.

## Step 2: Mission/iPhone Camera-Noise Sidecars

Goal: make camera-noise-aware still compression/addback safe beyond the existing
X2D/Z8 sidecars.

Current packet:
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_provenance_review_packet_100_percent_20260702/index.html`.
Extraction progress:
`/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_provenance_review_packet_100_percent_20260702/darkframe_extraction_progress.json`.
Current blocker audit:
`/Volumes/OWC_8TB/gpr_work/artifacts/raw_stills_noise_blocker_audit_20260702/index.html`.

Required evidence:

- Four Mission 1 true darkframes under one camera/ISO/CFA/dimension key.
- Four iPhone CFA true darkframes under one camera/ISO/CFA/dimension key.
- Original source hashes, extracted Bayer hashes, extraction receipt hashes,
  `no_scene_signal=true`, and capture proof for every frame.
- `gpr.darkframe_source_provenance_audit.v1` passes with
  `ready_frame_count>=4`, `production_ready=true`, and `linear_raw=false`.
- `gpr.camera_noise_calibration.v1` sidecars pass with `production_ready=true`,
  unique provenance-ready raw hashes, per-plane sigma, and
  `separates_noise_from_signal=true`.

Commands:

```bash
python3 tools/build_darkframe_candidate_audit.py \
  --source-kind confirmed_darkframes \
  --provenance-manifest <darkframe_source_provenance.json> \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_<camera>_<date> \
  <darkframe roots>

python3 tools/extract_raw_bayer_u16.py \
  --input <darkframe.dng> \
  --output <darkframe.raw> \
  --write-receipt <extract_receipt.json>

python3 tools/check_darkframe_source_provenance.py \
  <darkframe_raw_source_provenance.json> \
  --minimum-count 4 \
  --require-existing-files \
  --json-out <darkframe_source_provenance_audit.json>

python3 tools/build_camera_noise_calibration.py \
  --raw <darkframe0.raw> --raw <darkframe1.raw> --raw <darkframe2.raw> --raw <darkframe3.raw> \
  --out <sidecar.json> \
  --make <make> --model <model> --iso <iso> \
  --width <w> --height <h> --bit-depth <bits> \
  --black-level <black> --white-level <white> --cfa-phase <phase> \
  --source-provenance-manifest <darkframe_raw_source_provenance.json> \
  --require-source-provenance
```

Stop condition:

- Promote nonzero Mission/iPhone noise removal/addback only after the production
  submission checker accepts both sidecars.

## Step 3: Mission 1 Camera-Role Raw Video MVP

Goal: convert the Pi 5 stand-in proof into actual Mission 1 firmware evidence.

Required evidence:

- `target_preflight_receipt.json` with `target.role=camera`.
- `labs_target_bench.json` from a real Mission 1 sensor/DMA or camera
  ring-buffer source.
- `camera_handoff_receipt.json` proving sensor/DMA handoff, storage handoff,
  zero drops, valid `.gvid`, 4096 x 3072 source, and 120+ sustained frames.
- `preview_decode_1024x768/receipt.json` proving decode from the same `.gvid`.
- `preview_ui_receipt.json` proving full-frame rear-display preview at 1024 x
  768, 20+ fps, and 120+ sustained frames.
- `mission1_camera_closure_run.json` tying all camera-role receipts together.
- Storage medium names the actual camera SD/internal writer, not Pi/SSD/tmpfs.

Commands:

```bash
python3 tools/run_gopro_mission1_quick_validation.py \
  --target-role camera \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_validation_<date>

python3 tools/check_mission1_camera_closure_run.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_validation_<date>/mission1_camera_closure_run.json

python3 tools/check_production_capture_submission.py /path/to/submission.json \
  --require-existing-files \
  --path-root /path/to/submission_root
```

Stop condition:

- Mark raw-video MVP 100 percent only when real camera-role source, storage, and
  display receipts validate. Pi stand-ins, wrapped `.GPR` payloads, JPEG-derived
  media, and tiny smoke runs do not close this step.

## Step 4: Protect Locked Raw-Video Reconstruction

Goal: avoid wasting another day reopening approved video SR.

Required evidence:

- Current approved 4K cleanup and 8K SR dashboards remain linked.
- `.gvid`, editable DNG/GPR, ProRes review outputs, objective visual review,
  manual signoff, registry, release manifest, timing, memory, and hashes remain
  valid.
- PSF/blur work remains optional replacement research unless it already beats
  the locked baseline with the same receipt surface.

Commands:

```bash
python3 tools/test/check_product_lock_ledger.py
python3 tools/test/check_readme_product_pillars.py
python3 tools/test/check_release_evidence_manifest.py
```

Stop condition:

- Do not run another raw-video SR experiment as production work unless a locked
  raw-video reconstruction receipt fails or the replacement already clears the
  same production gate.

## Done Means

The high-level goal is 100 percent only when:

1. `docs/PRODUCTION_CAPTURE_REQUIREMENTS.json` has no open release-blocking
   requirements.
2. `docs/PRODUCT_PILLAR_SCORECARD.md`, the generated scorecard, README, lock
   ledger, release evidence manifest, and this plan agree on all four pillars.
3. `tools/test/check_product_burndown_contract.py`,
   `tools/test/check_high_level_goal_contract.py`,
   `tools/test/check_readme_product_pillars.py`, and CI pass on `master`.
