# RAW Stills Noise First-Hour Closure

This is the shortest path to close the remaining RAW-stills noise blockers:
`mission1_darkframe_stack` and `iphone_cfa_darkframe_stack`. It is for capture,
provenance, and sidecar promotion. It does not change the current product
status by itself.

## Decision In One Page

| question | current answer |
|---|---|
| Why is this still open? | X2D and Z8 have validated darkframe sidecars. Mission 1 and iPhone do not, so nonzero noise removal/addback must stay disabled for those cameras. |
| What proves Mission 1? | Four matching true no-scene-signal Mission 1 frames under one camera/ISO/CFA/dimensions key, with original-source hashes, extracted Bayer hashes, extraction receipts, and a passing production provenance audit. |
| What proves iPhone? | Four matching true no-scene-signal iPhone CFA DNG frames, not Linear Raw, with the same strict source-to-Bayer provenance chain. |
| What is the lowest-lift Mission path? | The current Mission 1 ISO232 RGGB candidate group has two dark-like frames and needs two more matching true darkframes, or a fresh four-frame same-settings stack. |
| What is the lowest-lift iPhone path? | The current iPhone ISO1250 RGGB group has enough dark-like candidates, but those frames still need confirmed no-scene-signal provenance before sidecar construction. |

## First-Hour Steps

1. Read the requirement IDs and current blocker text:

   ```sh
   sed -n '1,120p' docs/PRODUCTION_CAPTURE_REQUIREMENTS.md
   sed -n '1,220p' docs/CAMERA_NOISE_CALIBRATION.md
   ```

2. Build the fill-in production submission template:

   ```sh
   python3 tools/build_production_capture_submission_template.py \
     --output /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/submission_template.json
   ```

3. For each candidate darkframe, extract visible Bayer and keep the receipt:

   ```sh
   python3 tools/extract_raw_bayer_u16.py \
     --input <darkframe.dng> \
     --output /Volumes/OWC_8TB/gpr_work/artifacts/noise_calibration_<date>/<darkframe>.raw \
     --write-receipt /Volumes/OWC_8TB/gpr_work/artifacts/noise_calibration_<date>/<darkframe>_extract.json
   ```

4. Fill a strict source-provenance manifest with one row per promoted frame.
   Each row must include:

   | field | requirement |
   |---|---|
   | `raw_path` | extracted little-endian uint16 Bayer path |
   | `raw_sha256` | SHA-256 of `raw_path` |
   | `original_path` | original DNG/GPR source path |
   | `original_sha256` | SHA-256 of the original source |
   | `extract_receipt` | extraction receipt path |
   | `extract_receipt_sha256` | SHA-256 of the extraction receipt |
   | `make`, `model`, `iso` | camera and ISO metadata, either per row or in the manifest-level `camera` object |
   | `width`, `height`, `bit_depth` | extracted Bayer dimensions and bit depth, either per row or in the manifest-level `camera` object |
   | `black_level`, `white_level`, `cfa_phase` | raw level metadata and one of `RGGB`, `GRBG`, `GBRG`, or `BGGR`, either per row or in the manifest-level `camera` object |
   | `no_scene_signal` | `true` |
   | `capture_setup` or `proof` | non-empty proof that the frame is a darkframe or equivalent no-scene-signal capture |

   The provenance checker rejects mixed camera/ISO/CFA/dimension/bit-depth/level
   metadata and duplicate original-source hashes. Four rows must prove four
   distinct original captures under one matching metadata key.

5. Validate the provenance before building any sidecar:

   ```sh
   python3 tools/check_darkframe_source_provenance.py \
     <darkframe_raw_source_provenance.json> \
     --minimum-count 4 \
     --require-existing-files \
     --json-out <darkframe_source_provenance_audit.json>
   ```

6. Build the camera-noise sidecar only after the provenance audit passes:

   ```sh
   python3 tools/build_camera_noise_calibration.py \
     --raw <darkframe0.raw> --raw <darkframe1.raw> --raw <darkframe2.raw> --raw <darkframe3.raw> \
     --out <sidecar.json> \
     --make <make> --model <model> --iso <iso> \
     --width <w> --height <h> --bit-depth <bits> \
     --black-level <black> --white-level <white> --cfa-phase <phase> \
     --source-provenance-manifest <darkframe_raw_source_provenance.json> \
     --require-source-provenance
   ```

7. Submit the sidecar and provenance audit through the production capture
   checker:

   ```sh
   python3 tools/check_production_capture_submission.py <submission.json> \
     --require-existing-files \
     --path-root /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date> \
     --json-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/audit.json \
     --html-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/index.html
   ```

## Mission 1 Capture Target

| field | required value |
|---|---|
| camera | GoPro Mission 1 |
| frame count | at least four |
| grouping | same camera, ISO, CFA phase, dimensions, bit depth, black/white levels, and exposure class |
| current lowest-lift group | ISO232 RGGB has two dark-like candidates and needs two more matching true darkframes |
| source kind | `confirmed_darkframes`, `flat_dark_pair`, or `equivalent_no_scene_stack` |
| proof | lens/body cap, sealed no-light capture, or equivalent no-scene-signal setup |

## iPhone Capture Target

| field | required value |
|---|---|
| camera | iPhone CFA raw DNG |
| frame count | at least four |
| grouping | same camera, ISO, CFA phase, dimensions, bit depth, black/white levels, and exposure class |
| current lowest-lift group | Apple iPhone 7 Plus ISO1250 RGGB has enough dark-like candidates but lacks no-scene-signal provenance |
| negative fixture | Linear Raw does not count |
| proof | lens cover/dark enclosure/no-light capture proof, or equivalent no-scene-signal setup |

## What Does Not Count

| shortcut | why it is insufficient |
|---|---|
| A normal noisy photo | It mixes scene signal and sensor noise. |
| A single dark-looking frame | The sidecar requires at least four matching frames. |
| Metadata-only DNG `NoiseProfile` | Useful conditioning metadata, not proof that residual noise can be removed or added back. |
| iPhone Linear Raw | It is not a normal CFA Bayer fixture for this sidecar path. |
| Candidate-discovery dashboard alone | Candidate discovery finds frames to inspect; it does not prove no-scene-signal provenance. |
| REF/source/JPEG residuals | Those are forbidden as render-time noise content for production promotion. |

## Promotion Signal

A Mission 1 or iPhone noise sidecar can move from blocked to production only
when all of these are true:

| requirement | closure signal |
|---|---|
| source provenance | `gpr.darkframe_source_provenance_audit.v1` reports `production_ready=true` and at least four ready frames |
| sidecar | `gpr.camera_noise_calibration.v1` validates with `source_provenance_ready=true` and `separates_noise_from_signal=true` |
| runtime policy | exact camera/ISO class is allowed for nonzero denoised targets and calibrated noise addback |
| production submission | `tools/check_production_capture_submission.py` accepts the requirement row with existing-file/hash validation |

## Current Source Of Truth

| topic | document or artifact |
|---|---|
| Noise sidecar policy and builder | [`CAMERA_NOISE_CALIBRATION.md`](CAMERA_NOISE_CALIBRATION.md) |
| Open requirement IDs | [`PRODUCTION_CAPTURE_REQUIREMENTS.md`](PRODUCTION_CAPTURE_REQUIREMENTS.md) and [`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json) |
| Darkframe provenance review packet | `/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_provenance_review_packet_100_percent_20260702/index.html` |
| Darkframe extraction progress | `/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_provenance_review_packet_100_percent_20260702/darkframe_extraction_progress.json` |
| Raw-stills capture request | `/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_strict_provenance_20260701/index.html` |
| Current camera-noise coverage | `/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/index.html` |
| Runtime policy | `/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_runtime_policy_20260630/index.html` |
