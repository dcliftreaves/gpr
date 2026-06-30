# Production Capture Requirements

This is the committed checklist for real samples and hardware receipts that
still block the four product pillars from being called production-complete. The
machine-readable source is
[`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json);
generated dashboards under `/Volumes/OWC_8TB/gpr_work/artifacts` are review
surfaces over the same requirements.

## Why This Exists

The locked product paths are not the same thing as the remaining production
evidence. The 50 MP still tiers, Mission 1 Pi-stand-in `.gvid` encode/preview,
4K cleanup, and 8K SR baselines stay locked unless their own gate fails. The
requirements here are the missing real-world samples, camera receipts, and
model-promotion artifacts needed to finish the wider product suite.

## Open Requirements

| id | pillar | required evidence | closure signal |
|---|---|---|---|
| `real_grbg_fixture` | RAW stills | One original real-camera GRBG raw fixture with source hash and metadata receipt. | Fixture inventory sees real GRBG and normal Bayer still tests continue to pass. |
| `real_bggr_fixture` | RAW stills | One original real-camera BGGR raw fixture with source hash and metadata receipt. | Fixture inventory sees real BGGR and normal Bayer still tests continue to pass. |
| `mission1_darkframe_stack` | RAW stills | Four matching no-scene-signal Mission 1 darkframes under one camera/ISO/CFA/dimensions key. | `gpr.camera_noise_calibration.v1` sidecar validates and runtime policy allows exact-match noise use. |
| `iphone_cfa_darkframe_stack` | RAW stills | Four matching no-scene-signal iPhone CFA DNG darkframes; Linear Raw does not count. | iPhone CFA sidecar validates and Linear Raw remains a negative fixture. |
| `mission1_camera_role_receipts` | RAW video MVP | Real Mission 1 sensor/DMA or camera ring-buffer source, SD writer, and rear-display receipts. | Camera closure validator marks camera production ready; Pi stand-in receipts are replaced by camera-role evidence. |
| `controlled_mission1_psf_pairs` | PSF-aware video/SR | Controlled high/low Mission 1 raw pair stack with source hashes, decoded Bayer hashes, fixed settings, and negative controls. | Native PSF measurement accepts at least three pairs and produces a stable kernel for model conditioning. |
| `premium_still_sr_promotion_receipts` | Premium still/SR | Checkpoint, target, full-frame/editor-latitude, editable raw, timing/memory, and noise-policy receipts. | No-REF candidate beats current still-SR baselines on 50 MP and 100 MP gates without severe worst-row failures. |

## Guard

Run:

```sh
python3 tools/test/check_production_capture_requirements.py
```

The guard validates the schema, required IDs, statuses, minimum counts,
artifact root, validation commands, and the expected linkage to the four
product pillars. It is intentionally CI-safe and does not require private
artifacts.

## Current Generated Handoff Views

- Raw-stills capture request:
  `/Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_20260630/index.html`
- Raw-video PSF capture request:
  `/Volumes/OWC_8TB/gpr_work/artifacts/raw_video_psf_capture_request_20260630/index.html`
- GoPro Mission 1 intake audit:
  `/Volumes/OWC_8TB/gpr_work/artifacts/gopro_mission1_intake_audit_20260630/index.html`
- Product pillar scorecard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/product_pillar_scorecard_20260630/index.html`
