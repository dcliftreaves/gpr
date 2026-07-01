# Production Capture Requirements

This is the committed checklist for real samples and hardware receipts that
still block the shippable product pillars from being called production-complete. The
machine-readable source is
[`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json);
generated dashboards under `/Volumes/OWC_8TB/gpr_work/artifacts` are review
surfaces over the same requirements.

## Why This Exists

The locked product paths are not the same thing as the remaining production
evidence. The 50 MP still tiers, Mission 1 Pi-stand-in `.gvid` encode/preview,
4K cleanup, and 8K SR baselines stay locked unless their own gate fails. The
requirements here are the missing real-world samples, camera receipts, and
model-promotion artifacts needed to finish the shippable product suite. PSF
capture remains useful research for a future replacement model, but it no
longer blocks release of the approved current raw-video SR workflow.

## Open Requirements

| id | pillar | required evidence | closure signal |
|---|---|---|---|
| `mission1_darkframe_stack` | RAW stills | Four matching no-scene-signal Mission 1 darkframes under one camera/ISO/CFA/dimensions key, with per-frame source provenance from original raw to extracted Bayer; current ISO232 RGGB candidate group has 2 and needs 2 more. | `gpr.camera_noise_calibration.v1` sidecar validates with `source_provenance_ready=true` and runtime policy allows exact-match noise use. |
| `iphone_cfa_darkframe_stack` | RAW stills | Four matching no-scene-signal iPhone CFA DNG darkframes, with per-frame source provenance from original raw to extracted Bayer; Linear Raw does not count. The ISO1250 RGGB candidate group has enough dark-like frames but still needs no-scene provenance. | iPhone CFA sidecar validates with `source_provenance_ready=true` and Linear Raw remains a negative fixture. |
| `mission1_camera_role_receipts` | RAW video MVP | Real Mission 1 sensor/DMA or camera ring-buffer source, SD writer, and rear-display receipts. | Camera closure validator marks camera production ready; Pi stand-in receipts are replaced by camera-role evidence. |
| `premium_still_sr_promotion_receipts` | Premium still/SR | Checkpoint/config/target hashes, `runtime_inputs`, 50 MP and 100 MP full-frame gate row counts, median and worst-row MAE reduction, editor-latitude review, editable raw, timing/memory, and noise-policy receipts. | No-REF candidate beats current still-SR baselines on 50 MP and 100 MP gates, uses no REF/source/JPEG render-time content, records seconds/frame and peak RSS, and has no severe or negative worst-row failures. |

## Optional Research Requests

These items are useful for a next-generation model, but they are not release
blockers for the current approved raw-video SR workflow.

| id | research track | requested evidence | closure signal |
|---|---|---|---|
| `controlled_mission1_psf_pairs` | PSF-aware video/SR research | Controlled high/low Mission 1 raw pair stack with source hashes, decoded Bayer hashes, exact dimensions/byte counts, extraction/settings/measurement receipt hashes, fixed settings, and negative controls. | Native PSF measurement accepts at least three pairs and produces a stable kernel for model conditioning. |

## Closed Requirements

| id | pillar | closure evidence |
|---|---|---|
| `real_grbg_fixture` | RAW stills | Closed by `/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_broad_photos_20260701/index.html`, which found real Nikon D200 GRBG fixtures. |
| `real_bggr_fixture` | RAW stills | Closed by `/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_broad_photos_20260701/index.html`, which found real Nikon D70 BGGR fixtures. |

## Guard

Run:

```sh
python3 tools/test/check_production_capture_requirements.py
```

The guard validates the schema, required IDs, statuses, minimum counts,
artifact root, validation commands, and the expected linkage to the four
product pillars. It is intentionally CI-safe and does not require private
artifacts.

## Submission Audit

When a developer, camera team, or future agent submits new fixtures, darkframes,
camera-role receipts, optional PSF research pairs, or premium still-SR promotion receipts, validate
the package by first generating a fill-in manifest template:

```sh
python3 tools/build_production_capture_submission_template.py \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/submission_template.json
```

After replacing the placeholders with real paths, hashes, metadata, timing, and
receipt flags, audit the package with:

```sh
python3 tools/check_production_capture_submission.py <submission.json> \
  --json-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/audit.json \
  --html-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/index.html
```

For a local handoff bundle where the referenced files are present, use the
strict file/hash audit:

```sh
python3 tools/check_production_capture_submission.py <submission.json> \
  --require-existing-files \
  --path-root /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date> \
  --json-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/audit.json \
  --html-out /Volumes/OWC_8TB/gpr_work/artifacts/production_capture_submission_<date>/index.html
```

The submission manifest schema is `gpr.production_capture_submission.v1`. The
checker requires source hashes, fixed camera metadata, no-scene-signal flags for
darkframes, camera-role Mission 1 receipts, and strict no-REF premium still-SR
promotion receipts. Darkframe rows must set `source_kind` to
`confirmed_darkframes`, `flat_dark_pair`, or `equivalent_no_scene_stack`, carry
the original `source_path`/`sha256`, `extracted_bayer_path` and
`extracted_bayer_sha256`, `extract_receipt_path` and
`extract_receipt_sha256`, `no_scene_signal=true`, and a non-empty
`capture_setup` or `proof`. A premium still-SR submission must name runtime
inputs, include `candidate_raw` and `camera_metadata`, exclude REF/source/JPEG
content, report 50 MP and 100 MP full-frame gate row counts, show positive
median MAE reduction for both classes, show nonnegative worst-row MAE
reduction, record seconds per 50 MP frame, seconds per 100 MP frame, peak RSS,
and prove exact sidecar-only noise policy with source residual noise forbidden.
The checker separates release closure from optional research. `all_requirements_closed`
is driven by the open release-blocking requirements above; already-closed fixture
rows and omitted optional PSF research rows are skipped. If optional PSF research
pairs are submitted, the checker still validates them and sets
`submission_valid=false` until the optional research evidence is internally clean.
When optional PSF research pairs are submitted, the checker also requires
controlled pair hashes, 8192 x 6144 and 4096 x 3072 decoded Bayer dimensions,
exact uint16 byte counts, extraction/settings/measurement receipt hashes, and
negative-control rejection reasons. With
`--require-existing-files`, every path/hash pair that appears in the manifest
must exist locally and match its SHA-256. It exits nonzero until every
release-blocking requirement is closed and every submitted optional evidence row
is valid. The template builder and
checker together are the intake tools for turning the open requirements above
into an auditable pass/fail package.

## Current Generated Handoff Views

- Raw-stills capture request:
  `/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_strict_provenance_20260701/index.html`
  This request carries the exact committed requirement IDs it closes:
  `mission1_darkframe_stack` and `iphone_cfa_darkframe_stack`.
- Optional raw-video PSF research capture request:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_capture_request_20260630/index.html`
- GoPro Mission 1 intake audit:
  `/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_capture_requirements_20260701/index.html`
- Product pillar scorecard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_ship_boundary_20260701/index.html`
