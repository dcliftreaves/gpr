# Production 100 Percent Plan

Last refreshed: 2026-07-02

This is the operational checklist for getting the four-pillar GPR goal from the
current 83 percent production-readiness estimate to 100 percent. The concise
day-to-day burn-down is [`PRODUCTION_100_PERCENT_BURNDOWN.md`](PRODUCTION_100_PERCENT_BURNDOWN.md).
The rule is simple: a row is done only when its evidence exists, validates with
the listed commands, and is linked from the product scorecard or release
evidence manifest.

## Current State

| pillar | current | 100 percent requires |
|---|---:|---|
| Best RAW stills | 92% | Mission 1 and iPhone strict-provenance darkframe sidecars before broad nonzero camera-noise removal/addback is claimed. |
| GoPro RAW video MVP | 80% | Real Mission 1 camera-role receipts from sensor/DMA or camera ring-buffer input, SD writer, rear display, valid `.gvid`, 120+ sustained frames, zero drops, timing, memory, and storage. |
| Premium still/SR | 60% | A no-REF 50 MP / 100 MP candidate that beats the current still baseline and clears worst-row, editor-latitude, timing, memory, checkpoint, and exact-sidecar-only noise-policy gates. |
| RAW video reconstruction improvement | 100% | Keep the approved 4K cleanup and 8K SR receipt set green; do not reopen it for PSF/blur research unless a replacement already beats the locked baseline with the same artifact surface. |

## Exact Next Steps To 100 Percent

These steps are intentionally narrow. A work session starts at the first open
step and stops only after producing that step's receipt, fixing failed CI, or
recording a specific blocker in the receipt named by the step. Notes, attractive
dashboards, unlinked experiments, and raw training logs are not progress unless
they feed the receipt named here.

The first open local gate is **Gate A: Premium still-SR promotion**. The next
command must either build one of the three missing Gate A receipts named below
or update the Gate A receipt with a precise blocker. Do not start optional video
SR, PSF research, or new dashboard cosmetics while Gate A has a local next
command.

| step | status | action that must happen next | receipt required before moving on |
|---:|---|---|---|
| 1 | in progress | Keep CI green for the latest `master` push. If CI fails, inspect the failing job, patch the smallest cause, rerun focused local checks, push, and watch CI again. | Passing GitHub Actions run for the latest pushed commit. |
| 2 | closed, failed promotion | The source-evidence split Premium Still/SR smoke gates ran from `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_launch_packet_source_evidence_split_20260702/launch_packet.json`. X2D passed the short smoke gate, but Z8 failed. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_source_evidence_split_teacher_x2d_smoke_20260702_next/train_receipt.json` and `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_source_evidence_split_teacher_z8_smoke_20260702_next/train_receipt.json`. |
| 3 | closed, route direction selected | The route-specialist readiness audit shows route coverage and positive full-frame metric floors for Mission 1 50 MP DNG/GPR, Z8 50 MP DNG, and X2D 100 MP DNG; it also rejects extending the failed clean-source split into long training. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_route_readiness_20260702/route_readiness.json` and `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_route_readiness_20260702/index.html`. |
| 4 | closed, rendered proxy reviewed | The route-specialist readiness audit now links the routed rendered EV-stress proxy review: 36 rows, Mission1/Z8/X2D coverage, 33 model-better rows, and 3 model-worse rows. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_route_readiness_with_rendered_20260702/route_readiness.json` and `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_route_readiness_with_rendered_20260702/index.html`. |
| 5 | closed, editor/latitude ready | Mission 1 DNG, Mission 1 GPR, Z8 DNG, and X2D DNG now all have editable DNG/GPR openability plus non-oracle rawpy/LibRaw latitude receipts. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_editor_latitude_coverage_20260702/coverage.json` is 4/4 ready routes with `production_ready=true`. |
| 6 | closed, target policy ready | The clean-signal target policy passes: every retained row has a calibrated sidecar, render-time source raw/REF/JPEG content is forbidden, and exact source-noise addback is forbidden. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_policy_gate_20260702/premium_still_sr_noise_policy_gate.json` has clean-signal policy pass. |
| 7 | closed, blocker classified | The target/degradation evidence receipt now rules out candidate-HF no-op threshold tuning, simple frame-context conditioning, and another generic raw-CFA residual long run. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_target_degradation_evidence_20260702/target_degradation_evidence.json` has `long_run_allowed=false` and `blocker_classification=target_degradation_or_route_conditioning_mismatch`. |
| 8 | closed, replacement source contract ready | The replacement target/source contract combines X2D/Z8 source evidence, target-distribution mismatch, target SNR, and the previous blocker. It allows only a paired smoke preflight: noise-aware or row-filtered residual targets, route-conditioned X2D sampling, changed Z8 degradation/source policy, candidate-only runtime inputs, and exact no-op behavior. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_replacement_target_source_contract_20260702/replacement_target_source_contract.json` has `paired_smoke_preflight_allowed=true` and `long_run_allowed=false`. |
| 9 | closed, failed smoke | The replacement-contract route-conditioned/noise-aware raw-CFA smoke ran and is blocked before long training. X2D median/worst raw MAE recovery is `-0.16833363636675505%` / `-6.051057523320477%`; Z8 is `-1.5863477181003771%` / `-55.716890568612115%`. | `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_gate9_smoke_acceptance_20260702/smoke_gate_acceptance.json` has `long_run_allowed=false`. |
| 10 | open | Build a replacement target/degradation source receipt or a materially different route-conditioning proof. Do not rerun frequency-pyramid, gated no-op residual, masked-detail/no-op, raw-CFA source-frequency, raw-CFA residual signal, candidate-HF no-op, simple frame-context, or Gate 9 route-conditioned/noise-aware U-Net smoke as production work. | A new candidate intake plus paired X2D/Z8 smoke acceptance receipt passes before any long run, or a new blocker receipt narrows the failure to source/degradation mismatch, objective/gating failure, model capacity, camera-conditioning gap, timing/memory infeasibility, or noise-policy mismatch. |
| 11 | open | Package the Mission 1/iPhone noise-sidecar capture request around strict provenance only; do not promote candidate dark-looking frames. | Capture/provenance packet listing exact missing Mission/iPhone darkframes and validation commands. |
| 12 | open | When true no-scene-signal Mission/iPhone darkframes exist, build sidecars with `build_camera_noise_calibration.py --require-source-provenance`. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` both validate. |
| 13 | external | Keep the Mission 1 camera-role runbook ready for GoPro/Mission 1 firmware owners; no local Pi stand-in can close this gate. | Real camera-role source/storage/display receipts with 120+ sustained frames, zero drops, valid `.gvid`, and 20+ fps source/encode/preview. |
| 14 | closed/protect | Keep approved 4K cleanup and 8K SR evidence locked. Run only lock-ledger/readme/manifest guards unless a locked artifact fails. | Product lock ledger, README pillar guard, and release manifest guard pass. |

The priority order is therefore fixed: CI first, Premium Still/SR smoke evidence
second, Premium Still/SR promotion or blocker third, Mission/iPhone noise
sidecar provenance fourth, real Mission 1 camera-role closure fifth. Raw-video
SR research stays parked because the current 4K cleanup and 8K SR release path
is already approved and locked.

## Work-Until-100 Step Contract

This is the day-to-day execution contract. Start at the first open local row and
do not switch lanes unless the receipt named in that row is produced, the row
becomes externally blocked, or CI/committed gates fail.

| order | row | exact action | pass/fail receipt | next move |
|---:|---|---|---|---|
| 1 | Premium still-SR source evidence | Run or inspect `tools/cnn/audit_premium_still_sr_source_evidence.py` on the t64 clean-source pair corpus for X2D and Z8 holdouts before launching a new model. | `source_evidence_audit.json` plus `index.html` for both holdouts, linked in `docs/release_evidence_manifest.json`. | X2D is actionable only if MAE and RMSE recovery exceed 1%; Z8 is actionable only after MAE also exceeds 1%. |
| 2 | Premium still-SR candidate preflight | The source-evidence split launch packet exists at `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_launch_packet_source_evidence_split_20260702/index.html`, and its X2D/Z8 smoke receipts now exist. | `candidate_preflight.json`, `preflight_audit.json`, `launch_packet.json`, and paired smoke `train_receipt.json` files. | This row is diagnostic, not promotable: X2D passes, Z8 fails. |
| 3 | Premium still-SR route readiness | Use `tools/build_premium_still_sr_route_readiness.py` to keep the route-specialist direction explicit after the failed clean-source split. | `route_readiness.json` plus `index.html`, linked in `docs/release_evidence_manifest.json`. | Route coverage and positive full-frame metric floors exist, but production blockers remain. |
| 4 | Premium still-SR promotion | Build true raw-editor latitude/openability receipts for every route, wire exact-sidecar-only noise policy, then build the production submission. | `premium_still_sr_promotion_receipts` and production submission audit. | Mark Premium still/SR 100% only if the production checker passes; otherwise record the exact blocker class. |
| 5 | Raw-stills noise sidecars | Build Mission/iPhone darkframe sidecars only from strict-provenance true darkframes. | `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack` sidecar/audit receipts. | Mark Best RAW stills 100% only after both sidecars validate with no-scene-signal provenance. |
| 6 | Mission 1 camera-role video MVP | Hand off the camera validation runbook; only a real camera-role run can close the gate. | `mission1_camera_role_receipts`. | Mark Raw video MVP 100% only after real source/storage/display receipts replace Pi stand-ins. |
| 7 | Locked raw-video reconstruction | Protect the approved 4K cleanup and 8K SR evidence. | Lock ledger, release manifest, and CI guards pass. | Do not run new video SR as production work unless a locked receipt fails. |

Failure rule: a failed experiment is progress only if it leaves a checked receipt
that narrows the blocker to source evidence, degradation synthesis, teacher
objective, camera conditioning, model capacity, timing/memory, noise policy, or
external Mission 1 camera-role access.

## 100 Percent Gate Queue

This is the unambiguous execution queue. Work should always start at the first
gate whose `status` is not `closed`, unless a gate is explicitly marked
`blocked_on_external_input`. A gate can move only by creating or validating the
named receipt. A dashboard, model run, or note that does not feed one of these
receipts is not progress toward 100 percent.

| gate | status | exact next command | receipt that moves the gate | closed only when |
|---|---|---|---|---|
| A: Premium still-SR promotion | open, local | Continue from `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_editor_latitude_coverage_20260702/index.html` and `/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_policy_gate_20260702/index.html`. Raw-editor latitude/openability is now 4/4 and the clean-target noise policy passes. The next command class is model-promotion only: produce a no-REF candidate-only model receipt that clears the 15% / 15% held-out floor, then run `check_premium_still_sr_promotion_gate.py` and `check_production_capture_submission.py`. | `premium_still_sr_promotion_receipts` | Full 50 MP / 100 MP routed gates pass, worst-row recovery is nonnegative, raw-editor latitude/openability opens for every route, timing/memory/checkpoint hashes exist, exact-sidecar-only noise policy passes, and `check_production_capture_submission.py` passes. |
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
| Premium still/SR | Open. The current scoreboard has 124 runtime-safe receipts and 0 promotable receipts. The clean-source split smoke receipts narrow one rejected path: X2D passes the short gate at `+0.008822244790194556%` median MAE and `+0.003090454316737371%` median RMSE recovery, while Z8 fails at `-0.07358643668344858%` median MAE and `-0.01893710250797187%` median RMSE. The frequency-pyramid source-evidence branch is blocked before long training: X2D median MAE is `+0.005422090158202289%` and worst-row MAE is `-4.850145322879209%`; Z8 median MAE is `-8.809287941837436%` and worst-row MAE is `-67.44360239254922%`. The gated no-op residual branch reduces Z8 damage to `-0.07770732977859413%` median MAE / `-0.9817010759922141%` worst-row MAE, and a stricter identity probe nearly reaches interpolation parity, but neither creates positive held-out recovery. The masked-detail/no-op target-objective branch also fails: X2D median/worst-row MAE is `-0.000016166284221217207%` / `-0.004217229249483704%`, Z8 median/worst-row MAE is `-0.0011404326756156245%` / `-0.009009865416027604%`, and same-camera scene smokes stay negative. The raw-CFA source-frequency branch is blocked by objective scale: X2D median/worst-row raw MAE recovery is `-4968.130415027571%` / `-10524.379064644432%`, and Z8 is `-502.5390630379172%` / `-966.3531327864554%`. The raw-CFA residual signal branch is near parity on X2D but still fails and has a severe Z8 tail: X2D median/worst-row raw MAE recovery is `-0.15178115040635068%` / `-5.352462806764585%`, and Z8 is `-5.108265406545033%` / `-178.9545417615565%`. The candidate-HF no-op gate clips Z8 to exact parity, but still fails the paired smoke: X2D median/worst-row raw MAE recovery is `-0.006290143931539378%` / `-0.23156087540736878%`, and Z8 median/worst-row recovery is `0.0%` / `0.0%`; a frame-context diagnostic also fails X2D at `-0.01923371655785397%` median. The replacement-contract route-conditioned/noise-aware smoke is also blocked: X2D median/worst raw MAE recovery is `-0.16833363636675505%` / `-6.051057523320477%`, and Z8 is `-1.5863477181003771%` / `-55.716890568612115%`. The route-specialist readiness audit identifies the production route surface: Mission 1 50 MP DNG/GPR, Z8 50 MP DNG, and X2D 100 MP DNG have route coverage and positive full-frame metric floors. The editor/latitude coverage audit is 4/4 ready and the clean-signal target noise policy passes, but no supplied model receipt clears the 15% / 15% promotion floor. | Do not start a long run from the rejected source-evidence split, frequency-pyramid, gated-residual, masked-detail/no-op, source-frequency, residual-signal, candidate-HF no-op, simple frame-context, or route-conditioned/noise-aware Gate 9 candidates. The next local action must build a replacement target/degradation source receipt or materially different route-conditioning proof before another paired smoke. | The routed candidate beats the still baseline on 50 MP and 100 MP holdouts, has nonnegative worst-row recovery, records timing/memory/checkpoint hashes, passes raw-editor latitude/openability for all four required routes, passes exact-sidecar-only noise policy, and passes production submission validation. |
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
- Candidate architecture is one of the trainer-supported production-preflight
  values, but architecture support alone is not enough: the latest
  `window_attention_pixelshuffle` smoke failed the joint X2D/Z8 gate.
- Candidate uses a plausible restoration teacher or clean-source/CFA-aware
  objective with camera conditioning and realistic RAW degradation.
- Candidate cites a current source-evidence audit. If X2D remains positive and
  Z8 remains below the 1 percent MAE floor, the manifest must use the X2D local
  signal as material supervision/objective evidence and change the Z8
  source/degradation target before long training.
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
