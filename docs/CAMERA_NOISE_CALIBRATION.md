# Camera Noise Calibration

The stills and CNN paths may use camera noise only when it is calibrated from
source data that separates sensor noise from scene signal. A single normal
photograph, REF residual, or visually noisy crop is not enough evidence.

## Receipt

Noise evidence is recorded as a `gpr.camera_noise_calibration.v1` JSON sidecar
and validated by:

```sh
python3 tools/check_product_pillar_receipts.py path/to/noise_calibration.json
```

The sidecar is keyed by camera make/model, dimensions, bit depth, CFA phase,
black level, white level, ISO, source kind, source hash, and per-plane noise
statistics. Per-plane values are named `r`, `g1`, `b`, and `g2`; `g1` and `g2`
are the two green sites in row-major CFA order for the recorded phase.

For production training targets, the receipt must prove:

- the source is a darkframe, flat/dark pair, or equivalent no-scene-signal
  stack;
- at least four frames contributed to the calibration;
- the noise/signal audit marks `separates_noise_from_signal=true`;
- new Mission 1, iPhone, or other promoted camera sidecars use strict
  per-frame source provenance so every extracted Bayer frame is linked to its
  original raw file, extraction receipt, and no-scene-signal capture proof;
- metadata-only DNG `NoiseProfile` values are treated as conditioning data, not
  proof that a residual can be removed from training targets.

## Builder

First extract each original raw/DNG/GPR darkframe to little-endian uint16 Bayer
and keep the extraction receipt:

```sh
python3 tools/extract_raw_bayer_u16.py \
  --input dark_000.dng \
  --output /Volumes/OWC_8TB/gpr_work/artifacts/noise_calibration/dark_000.raw \
  --write-receipt /Volumes/OWC_8TB/gpr_work/artifacts/noise_calibration/dark_000_extract.json
```

Then build the sidecar from at least four matching little-endian uint16 Bayer
darkframes. Production promotion should pass a source-provenance manifest and
`--require-source-provenance`:

```sh
python3 tools/build_camera_noise_calibration.py \
  --raw dark_000.raw --raw dark_001.raw --raw dark_002.raw --raw dark_003.raw \
  --width 8280 --height 5520 \
  --bit-depth 14 --cfa-phase RGGB --iso 1600 \
  --make Nikon --model Z8 \
  --black-level 64 --white-level 16383 \
  --source-provenance-manifest /Volumes/OWC_8TB/gpr_work/artifacts/noise_calibration/z8_iso1600_source_provenance.json \
  --require-source-provenance \
  --out /Volumes/OWC_8TB/gpr_work/artifacts/noise_calibration/z8_iso1600.json
```

The source-provenance manifest must contain one `frames` row per `--raw` input
with `raw_path`, `raw_sha256`, `original_path`, `original_sha256`,
`extract_receipt`, `no_scene_signal=true`, and `capture_setup` or `proof`.
Strict mode refuses promotion if any extracted raw hash does not match the file
contents, any original source hash is missing or malformed, or any frame lacks
no-scene-signal proof.

The builder estimates black-frame sigma per Bayer plane and writes a
NoiseProfile-compatible offset term. The scale term is intentionally zero for
darkframes because black frames do not measure shot-noise slope across signal
levels. A future flat/dark or frame-stack calibration can fill that slope, but
it must keep the same receipt contract.

## Legacy Calibration Converter

Older darkframe-calibration artifacts can be converted only when their selected
source frames can be recovered and hashed:

```sh
python3 tools/convert_darkframe_calibration_to_noise_sidecars.py \
  --legacy-json /Volumes/OWC_8TB/gpr_work/artifacts/darkframe_calibration_x2d_full_20260605/darkframe_calibration.json \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_sidecars_20260629/x2d
```

The converter writes one sidecar per camera/ISO/exposure group plus a
`camera_noise_calibration_index.json`. Each sidecar points to a
`*_source_manifest.json` that hashes the selected darkframes and the legacy
calibration JSON.

Current converted receipts:

| camera | ISO / frames | sidecar root |
|---|---:|---|
| Hasselblad X2D 100C | ISO 64 / 64, ISO 200 / 50, ISO 800 / 50, ISO 3200 / 50, ISO 12800 / 49 | `/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_sidecars_20260629/x2d/` |
| Nikon Z 8 | ISO 500 / 32 | `/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_sidecars_20260629/z8/` |

Current coverage dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_coverage_audit_20260630/index.html
```

Current runtime policy dashboard:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/camera_noise_runtime_policy_20260630/index.html
```

Coverage status: X2D and Z8 are ready for calibrated noise conditioning and
controlled addback experiments. Mission 1 and iPhone have real still fixtures,
but they do not yet have validated darkframe sidecars; for those cameras,
nonzero denoised targets and synthetic noise addback remain blocked until a
darkframe stack, flat/dark pair, or equivalent no-scene-signal evidence is
collected and converted.

The runtime policy is the artifact renderers and trainers should consume. It
allows nonzero denoised targets and calibrated noise addback only for exact
camera/ISO classes with production-ready sidecars. Missing camera families or
missing ISOs fall back to metadata conditioning only: preserve source metadata,
do not remove residual content from targets, and do not add generated noise at
render time.

## Darkframe Candidate Audit

Use the discovery audit before promoting new camera noise sidecars. It scans
bounded DNG sets in raw space, flags frames that are dark enough to inspect as
possible darkframes, and groups them by camera/ISO/CFA. It deliberately does
not create production sidecars from ordinary photos or single dark-looking
frames:

```sh
TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp \
/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python \
  tools/build_darkframe_candidate_audit.py \
  --manifest /Volumes/OWC_8TB/gpr_work/tmp/darkframe_candidate_manifest_20260630.txt \
  --max-files 2000 \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701
```

Current Mission 1 / iPhone candidate audit:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission_iphone_fullmanifest_20260701/index.html
```

The current full-manifest scan saw 2,000 bounded manifest rows, parsed 1,997,
and found 59 darkframe-like frames. Mission 1 still has only a two-frame ISO232
RGGB candidate group. iPhone has a 27-frame ISO1250 RGGB candidate group, but
those candidate-discovery frames still need confirmed no-scene-signal
provenance before they can become a production sidecar.

The current compact Mission 1 DNG root has also been rescanned directly:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_mission1_dng_full_20260701/index.html
```

That scan parses all 49 Mission 1 DNGs and finds five dark-like RGGB frames.
It still does not close the Mission sidecar: the best same-ISO group remains
`GoPro|MISSION 1|ISO232|RGGB` with two frames, so the lowest-lift path is two
more matching true darkframes with provenance, or a fresh four-frame
same-settings stack.

When the source root is known to contain true darkframes, rerun the audit with
confirmed provenance instead of candidate discovery:

```sh
python3 tools/build_darkframe_candidate_audit.py \
  --source-kind confirmed_darkframes \
  --provenance-manifest <darkframe_source_provenance.json> \
  --root <confirmed darkframe root> \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/darkframe_candidate_audit_confirmed_<date>
```

The provenance manifest must include one row per promoted frame with `path`,
`sha256`, `no_scene_signal=true`, and a non-empty `capture_setup` or `proof`.
Without that manifest, the audit stays discovery-only and cannot mark a
production stack ready.

For the current Mission/iPhone candidate sets, first build the review packet:

```sh
python3 tools/build_darkframe_provenance_review_packet.py \
  --capture-request /Volumes/OWC_8TB/gpr_work/artifacts/stills_capture_request_strict_provenance_20260701/stills_capture_request.json \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/darkframe_provenance_review_packet_<date>
```

That packet hashes the lowest-lift candidate DNGs and emits a fill-in
provenance template. It is not a production sidecar; it exists to decide
whether the candidate frames can be confirmed as true no-scene-signal
darkframes or must be recaptured.

After extracting the promoted frames, carry the same provenance into the final
noise sidecar builder with:

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

## Policy

Current production stills may preserve DNG `NoiseProfile`/ISO metadata and use
it as model conditioning. They should not train on nonzero denoised targets or
add synthetic texture back into final outputs unless a validated calibration
sidecar exists for the exact camera/ISO class and the runtime policy marks that
camera/ISO as allowed.
