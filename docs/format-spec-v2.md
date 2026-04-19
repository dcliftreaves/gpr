# GPR Format Specification v2.0

## Overview

GPR v2.0 extends the GoPro Raw (GPR) format with noise-aware adaptive quantization and ANS entropy coding. GPR files are DNG-compliant containers with VC5/CineForm compressed image data.

A GPR v2.0 file is a valid DNG file. Any DNG-compatible reader can open the container and read metadata. Only the VC5 bitstream decompression requires a v2.0-aware decoder.

## Scope

### Supported Cameras
- GoPro (Hero5-12, Fusion): 12/14-bit RGGB/GBRG Bayer
- Hasselblad X2D 100C: 16-bit RGGB Bayer, 11664x8750
- Nikon Z8: 14-bit RGGB Bayer, 8280x5520 (via DNG conversion)
- Any camera producing DNG-compatible raw data

### Bit Depths
- 12-bit, 14-bit, 16-bit per sample
- Bayer CFA patterns: RGGB, GBRG (2x2 only)

---

## File Structure

A GPR file is a DNG/TIFF container:

```
[TIFF Header]
[IFD #0 — Main Image]
  ├── Standard DNG tags (Make, Model, ColorMatrix, etc.)
  ├── VC5 compressed image data (in NewSubfileType strip)
  └── XMP metadata block
       ├── GPRNoiseSeed (uint32) — PRNG seed for noise reconstruction
       ├── GPRNoiseSigma0..3 (float64) — per-channel noise sigma
       └── GPRFpnPoly_ch0..3 (string) — FPN polynomial coefficients
[IFD #1 — Thumbnail (optional)]
```

### DNG Compliance

GPR v2.0 files preserve all standard DNG tags:
- `Make`, `Model`, `UniqueCameraModel`
- `ColorMatrix1`, `ColorMatrix2`, `ForwardMatrix1`, `ForwardMatrix2`
- `CalibrationIlluminant1`, `CalibrationIlluminant2`
- `AsShotNeutral`, `AsShotWhiteXY`
- `BlackLevel`, `WhiteLevel`
- `BayerPattern` / `CFAPattern`
- `NoiseProfile` (DNG noise_scale, noise_offset)
- `BaselineExposure`, `BaselineNoise`

Non-GoPro cameras (Hasselblad, Nikon) retain their original DNG metadata through the round-trip.

---

## VC5 Bitstream Extensions

### Version Identification

To enable graceful failure on old decoders, v2.0 files include an optional version tag in the VC5 bitstream header:

```
CODEC_TAG_FormatVersion = 201  (optional tag)
Value: 0x0200 (version 2.0)
```

Old decoders that don't recognize this tag skip it (standard optional tag behavior). They will encounter ANS-encoded bands and fail at the VLC decoder with a recognizable error pattern.

### Band Coding Method Tag

Each highpass subband may independently use VLC or ANS coding:

```
CODEC_TAG_BandCodingMethod = 200  (optional tag, per-band)
Value: 0 = VLC run-length (default, backward compatible)
       1 = ANS adaptive entropy coding
```

When this tag is absent, the band uses VLC (full backward compatibility with v1.0).

### ANS Band Data Format

When `CODEC_TAG_BandCodingMethod = 1`, the band codeblock contains:

```
[AlignBitsSegment]
[tables_size: 32 bits, big-endian]     — byte count of frequency tables
[tables_data: tables_size bytes]       — serialized ANS frequency tables
[AlignBitsSegment]
[coded_size: 32 bits, big-endian]      — byte count of ANS-coded data
[coded_data: coded_size bytes]         — rANS-encoded coefficients
```

The band codeblock is still wrapped in the standard `PushSampleSize`/`PopSampleSize` pair, so legacy parsers can skip it by size even if they can't decode the contents.

#### ANS Frequency Tables

Two tables per band: run-length distribution and magnitude distribution.

```
Table format: ANS_NUM_SYMBOLS × 2 bytes per table × 2 tables
  = (ANS_MAX_SYMBOL + 2) × 2 × 2 = 516 × 2 = 1032 bytes per band

Byte layout:
  [run_freq[0]: 16 bits big-endian] ... [run_freq[ANS_NUM_SYMBOLS-1]]
  [mag_freq[0]: 16 bits big-endian] ... [mag_freq[ANS_NUM_SYMBOLS-1]]

Frequencies sum to ANS_TABLE_SIZE (2048).
Every frequency must be >= 1 for used symbols.
```

Constants:
- `ANS_TABLE_BITS = 11`
- `ANS_TABLE_SIZE = 2048`
- `ANS_MAX_SYMBOL = 256`
- `ANS_NUM_SYMBOLS = 258` (0..256 + escape)

#### ANS Coded Data

The rANS-encoded bitstream contains interleaved run-length and magnitude symbols:

```
Coded data format:
  [pair_count: 32 bits big-endian]     — number of (run, magnitude) pairs
  [rans_size: 32 bits big-endian]      — byte count of rANS data
  [sign_bytes: 32 bits big-endian]     — byte count of sign bitstream
  [rans_data: rans_size bytes]         — rANS state + renormalization bytes
  [sign_data: sign_bytes bytes]        — packed sign bits (1 bit per non-zero value)
```

Each pair encodes:
1. A zero run-length (rANS symbol from run table)
2. A magnitude (rANS symbol from magnitude table)
3. If magnitude > 0: a sign bit from the sign bitstream

Magnitudes are cubic-companded before ANS encoding (same `ComputeCubicTable` curve as VLC) to produce values in [0, 255].

#### rANS Parameters

- Byte-aligned rANS (Giesen-style)
- `RANS_BYTE_L = 1 << 23` (renormalization threshold)
- Encoder writes forward, buffer is reversed
- Initial state: `RANS_BYTE_L`
- Final state flushed as 4 bytes (little-endian, then reversed with buffer)
- Decoder reads state from first 4 bytes (big-endian after reversal)

---

## Noise-Aware Quantization

### Encoder Behavior

When noise-aware quantization is enabled (`-D` flag), the encoder:

1. **Estimates noise** from each channel's component array (post-log-curve, pre-wavelet):
   - 4-bin signal-level-dependent MAD estimation
   - Uses middle bins (25th-75th percentile) to avoid dark-pixel bias

2. **Propagates noise through wavelet gains**:
   - Filter gain: LH/HL = √2, HH = 2.0
   - Prescale divisor: cumulative product of `2^prescale[level]`
   - Per-band sigma = raw_sigma × filter_gain / prescale_divisor

3. **Adjusts quantization tables**:
   - `quant[band] = max(default_quant, min(noise_quant, default_quant × 3))`
   - The 3× cap prevents signal destruction on any image
   - Default quant comes from the quality preset (Q0-Q8)

### Decoder Behavior

The decoder does not need special handling for noise-aware quantization. The adjusted quant values are stored in the standard `CODEC_TAG_Quantization` tags per band. The decoder applies standard inverse quantization.

### Noise Metadata (XMP)

When noise-aware encoding is used, the following XMP properties are written:

| Property | Type | Description |
|----------|------|-------------|
| `GPRNoiseSeed` | uint32 | PRNG seed for noise reconstruction |
| `GPRNoiseSigma0` | float64 | Channel 0 noise sigma |
| `GPRNoiseSigma1` | float64 | Channel 1 noise sigma |
| `GPRNoiseSigma2` | float64 | Channel 2 noise sigma |
| `GPRNoiseSigma3` | float64 | Channel 3 noise sigma |

XMP namespace: `http://ns.adobe.com/exif/1.0/aux/`

---

## Noise Remove/Restore (Optional)

An optional pixel-domain noise separation pipeline:

### Encoder (`noise_remove`)
For each raw pixel:
1. Compute sigma from DNG NoiseProfile: `sigma = sqrt(noise_scale × signal + noise_offset)`
   - NoiseProfile values are DNG-normalized [0,1]; convert to raw units: `scale_raw = scale_dng × max_val`
2. Quantize: `output = round(signal / sigma) × sigma`
3. Store seed in XMP for decoder reconstruction

### Decoder (`noise_restore`)
For each decoded pixel:
1. Compute sigma from stored NoiseProfile (same formula)
2. Add PRNG noise: `output = signal + prng_gaussian(seed, row, col) × sigma × 0.5`
3. Clamp to valid range

The decoder automatically triggers noise restoration when `GPRNoiseSeed` is present in XMP, unless `denoise_output` mode is requested.

**Note**: Pixel-domain noise removal is only beneficial with a custom entropy coder or non-wavelet compressor. With VC5's wavelet+VLC pipeline, it increases file size because quantization steps are less compressible than Gaussian noise. Use noise-aware quantization (`-D`) instead.

---

## Quality Presets

| Preset | Name | Quant Table (14-bit scaled) |
|--------|------|----------------------------|
| Q0 | Low | {1, 21, 21, 10, 55, 55, 41, 439, 439, 658} |
| Q1 | Medium | {1, 21, 21, 10, 41, 41, 27, 219, 219, 329} |
| Q2 | High | {1, 21, 21, 10, 27, 27, 21, 110, 110, 164} |
| Q3 | Filmscan-1 | {1, 21, 21, 10, 21, 21, 10, 82, 82, 123} |
| Q4 | Filmscan-X | {1, 21, 21, 10, 21, 21, 10, 55, 55, 82} |
| Q5 | Filmscan-2 | {1, 21, 21, 10, 21, 21, 10, 27, 27, 41} |
| Q6 | Filmscan-3 | {1, 10, 10, 5, 10, 10, 5, 14, 14, 21} |
| Q7 | Filmscan-4 | {1, 5, 5, 3, 10, 10, 5, 14, 14, 21} |
| Q8 | Filmscan-5 | {1, 3, 3, 2, 9, 9, 5, 14, 14, 21} |

For 16-bit data, quant values are scaled by `12/16 = 0.75`.
For 12-bit data, quant values are unscaled (table is designed for 12-bit).

Subband mapping: `[LL, L0_LH, L0_HL, L0_HH, L1_LH, L1_HL, L1_HH, L2_LH, L2_HL, L2_HH]`

---

## ANS Auto-Selection

ANS coding is automatically disabled for `internal_precision > 14` (16-bit data). For 16-bit sensors, the cubic companding maps many coefficients to the same value (255), creating a flat distribution where VLC's joint RLV encoding is more efficient.

When ANS is disabled, bands use standard VLC encoding and no `CODEC_TAG_BandCodingMethod` tag is emitted.

---

## Backward Compatibility

| Feature | v1.0 decoder behavior | v2.0 decoder behavior |
|---------|----------------------|----------------------|
| VLC-only file | Full decode | Full decode |
| ANS-encoded band | Fails at VLC decode | Reads ANS tag, uses ANS decoder |
| Noise metadata in XMP | Ignored | Reads seed/sigma for reconstruction |
| FormatVersion tag | Skipped (optional) | Reads version, validates |

A v2.0 encoder with ANS disabled and denoise disabled produces a byte-identical file to v1.0.

---

## Reference Implementation

- Encoder: `source/lib/vc5_encoder/encoder.c` — `EncodeHighpassBand()`
- Decoder: `source/lib/vc5_decoder/decoder.c` — `DecodeHighpassBand()`
- ANS coder: `source/lib/vc5_common/ans.c`
- Noise estimation: `source/lib/vc5_encoder/denoise.c`
- CLI: `source/app/gpr_tools/main.cpp` — flags `-D`, `-A`, `-R`

---

## Validation Criteria

A conforming v2.0 encoder/decoder must:

1. Round-trip any supported raw file with PSNR ≥ 40 dB (at Q3 or above)
2. Preserve all DNG metadata through the round-trip (Make, Model, ColorMatrix, NoiseProfile)
3. Produce files that open in standard DNG readers (metadata and thumbnail accessible)
4. Fail gracefully when encountering unsupported codec features (return error, don't corrupt)
5. Validate all untrusted data from the bitstream (sizes, frequencies, pair counts)
