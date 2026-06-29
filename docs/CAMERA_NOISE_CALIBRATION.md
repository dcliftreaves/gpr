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
- metadata-only DNG `NoiseProfile` values are treated as conditioning data, not
  proof that a residual can be removed from training targets.

## Builder

For new little-endian uint16 Bayer darkframes:

```sh
python3 tools/build_camera_noise_calibration.py \
  --raw dark_000.raw --raw dark_001.raw --raw dark_002.raw --raw dark_003.raw \
  --width 8280 --height 5520 \
  --bit-depth 14 --cfa-phase RGGB --iso 1600 \
  --make Nikon --model Z8 \
  --black-level 64 --white-level 16383 \
  --out /Volumes/OWC_8TB/gpr_work/artifacts/noise_calibration/z8_iso1600.json
```

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

## Policy

Current production stills may preserve DNG `NoiseProfile`/ISO metadata and use
it as model conditioning. They should not train on nonzero denoised targets or
add synthetic texture back into final outputs unless a validated calibration
sidecar exists for the camera/ISO class.
