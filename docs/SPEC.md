# GPR Bitstream Specification

**Status:** v1 (FUSED), draft. Document target: an independent implementer
producing a compatible encoder or decoder from this document alone.

**Sources of truth (read alongside this spec):**

| Topic | File |
|---|---|
| FUSED bitstream wrapper | `source/lib/vc5_encoder/fused_encode.h` |
| FUSED encoder reference | `source/lib/vc5_encoder/fused_encode.c` |
| FUSED decoder reference | `source/lib/vc5_decoder/fused_decode.c`, `fused_decode.h` |
| Legacy VC5 encoder | `source/lib/vc5_encoder/encoder.c`, `vc5_encoder.h` |
| Log / companding curves | `source/lib/vc5_common/logcurve.c`, `companding.c` |
| rANS entropy coder | `source/lib/vc5_common/ans_joint.h`, `ans_joint.c` |
| GPRaw container | `tools/gpraw/include/gpraw.h`, `tools/gpr2prores/GPRFileReader.h` |
| Quant calibration data | `docs/quant_calibration_findings.md` |
| Env-var disposition | `docs/ENV_VAR_CLEANUP.md` |

If this document and the source disagree, the source wins. File a bug.

---

## 1. Overview

GPR (GoPro Raw) is a wavelet codec for Bayer-pattern raw imagery. The
codec produces a compressed representation of a single Bayer plane,
suitable for either still images (one frame per file) or video (a stream
of frames packaged in a MOV container). GPR is **not** a CNN-aware
post-processor; the CNN deblock / super-res steps used during playback
operate on the decoded Bayer output and are documented separately
(`docs/architecture.md`, `tools/gpr2prores/SuperResCNN.h`).

Two encoder topologies coexist in the repo:

* **Multi-level wavelet (3 levels deep).** Used by the production
  encoder (`vc5_encoder_process`) and by the FUSED encoder when
  `multi_level=1`. Three cascaded 2D 5/3 wavelet decompositions
  remove inter-band correlation; the deepest lowpass band (LL3) is
  preserved, the nine highpass bands are quantized + entropy-coded.

* **Single-level wavelet + LL.** A simpler topology produced by the
  FUSED encoder when `multi_level=0` and `GPR_INCLUDE_LL=1` is set. One
  2D wavelet decomposition is run; both the lowpass (LL1) and the
  three highpass bands (LH1/HL1/HH1) are quantized + entropy-coded.
  Produces ~2× larger files than multi-level at the same quality but is
  the fast path for embedded / live-preview use.

Both topologies run after a Bayer→4-channel color-space transform
(`GS/RG/BG/GD`) and a log-curve transform (12/14/16-bit input → 12/14/16-bit
log-domain).

There is also a degenerate **single-level, no-LL** mode (`num_bands=12`,
`multi_level=0`, `include_ll=0`). It is **not decodable** — the decoder
rejects it with `-5`. It exists only for the "discard everything, measure
HP entropy" calibration path and is not part of the conformance surface.

This document specifies:

1. The **FUSED wrapper format** — the byte layout produced by
   `gpr_encode_fused_frame` and consumed by `gpr_decode_fused`.
2. The **color transform**, **log curve**, **wavelet**, **quantization**,
   and **entropy coding** stages that produce each band's payload.
3. The **legacy VC5 bitstream** (briefly) — produced by
   `vc5_encoder_process` and embedded inside DNG containers by
   `gpr_tools`. The legacy bitstream is documented in
   `docs/format-spec-v2.md`; this section is a pointer + delta.
4. The **GPRaw container** that wraps a stream of FUSED frames in a
   MOV file for video.

---

## 2. FUSED bitstream wrapper format

A FUSED bitstream is a self-describing byte buffer with the layout:

```
+----------------------------+   offset 0
| FUSED_HEADER (48 bytes)    |
+----------------------------+   offset 48
| band_size[0..N-1]          |   N * 4 bytes
| (uint32_t little-endian)   |
+----------------------------+   offset 48 + 4*N
| band_data[0]               |   band_size[0] bytes
+----------------------------+
| band_data[1]               |   band_size[1] bytes
+----------------------------+
| ...                        |
+----------------------------+
| band_data[N-1]             |   band_size[N-1] bytes
+----------------------------+   total size = 48 + 4*N + sum(band_size)
```

`N` (the value in `FUSED_HEADER.num_bands`) is 16 (single-level + LL),
40 (multi-level), or 12 (single-level no-LL — not decodable; reserved).

All multi-byte integer fields are **little-endian**. There is no
alignment padding: `band_data[k]` starts immediately after `band_data[k-1]`.
The struct contains 12 `uint32_t` fields with no implicit padding on any
supported ABI — `sizeof(FUSED_HEADER)` is exactly 48 bytes (4 * 12). The
encoder and decoder both rely on this and use `sizeof(FUSED_HEADER)` to
walk the header.

### 2.1 FUSED_HEADER

```c
typedef struct {
    uint32_t magic;          // offset  0
    uint32_t version;        // offset  4
    uint32_t width;          // offset  8
    uint32_t height;         // offset 12
    uint32_t pixel_format;   // offset 16
    uint32_t quality;        // offset 20
    uint32_t is_rggb;        // offset 24
    uint32_t log_bits;       // offset 28
    uint32_t prescale;       // offset 32
    uint32_t multi_level;    // offset 36
    uint32_t num_bands;      // offset 40
    uint32_t decimate;       // offset 44
} FUSED_HEADER;              // sizeof = 48 bytes on every supported ABI
```

| Field | Valid values | Meaning |
|---|---|---|
| `magic` | `0x44535546` (`'FUSD'` little-endian) | File-format identifier. Decoder must reject anything else with error `-3`. |
| `version` | `1` | Bitstream version. Decoder rejects mismatch with `-4`. Future versions must change this number when adding non-backward-compatible fields. |
| `width` | 1..65535 (pixels) | Bayer-plane width before any decimation. The encoded bands describe a `width/decimate` × `height/decimate` Bayer image; the output Bayer (and the value the container advertises as `decWidth`) is at the decimated size. |
| `height` | 1..65535 (pixels) | Bayer-plane height before any decimation. |
| `pixel_format` | 0..5 | Bayer pattern + bit-depth tag. See §2.2. |
| `quality` | 0..11 | Quality preset index. See §6.1 for the quant tables; values ≥12 cause the decoder to return `-7`. Values 9, 10 are reserved and mirror 8. |
| `is_rggb` | 0 or 1 | 1 = top-left 2×2 is `R G / G B` (RGGB). 0 = top-left 2×2 is `G B / R G` (GBRG). All other patterns are unsupported. |
| `log_bits` | 12, 14, or 16 | Bit depth used for the encoder log-curve domain AND the decoder output bit depth. 12 and 14 share `DecoderLogCurve14`; 16 uses `DecoderLogCurve16`. |
| `prescale` | 2 (in practice) | Level-1 prescale shift used by the wavelet. The encoder always emits 2. Decoder passes this through to the inverse-wavelet `descale` argument. |
| `multi_level` | 0 or 1 | 1 = 3-level wavelet (`num_bands=40`). 0 = single-level (`num_bands=16` with LL, or 12 without; only =16 is decodable). |
| `num_bands` | 16, 40 (12 = reserved/invalid) | Length of the `band_size[]` array immediately following the header. Decoder rejects unknown values with `-6`. |
| `decimate` | 0, 1, or 2 | Channel-space decimation factor. 0 or 1: no decimation, bands describe `width × height` Bayer. 2: 2×2 channel-space decimation was applied; bands describe `width/2 × height/2` Bayer and the decoder produces output at those reduced dims. |

### 2.2 pixel_format encoding

```text
0  RGGB_12   (uint16 little-endian samples, top-left = R)   → log_bits=14
1  RGGB_14   (uint16 little-endian samples, top-left = R)   → log_bits=14
2  GBRG_12   (uint16 little-endian samples, top-left = G)   → log_bits=14
3  GBRG_14   (uint16 little-endian samples, top-left = G)   → log_bits=14
4  RGGB_16   (uint16 little-endian samples, top-left = R)   → log_bits=16
5  GBRG_16   (uint16 little-endian samples, top-left = G)   → log_bits=16
```

The wire format always stores samples as `uint16_t` (high bits zero
for 12/14-bit inputs). The FUSED encoder maps `pixel_format` to two
canonical log bit-depths: `log_bits = 16` if `pixel_format >= 4`, else
`log_bits = 14`. 12-bit inputs are processed at the 14-bit log
table; this is intentional (the encoder has historically combined
the 12-bit and 14-bit code paths). `is_rggb` is `1` iff
`pixel_format ∈ {0, 1, 4}`.

The header field `log_bits` carries the operative log/decode bit depth
and the decoder always trusts it over `pixel_format`.

Open spec note: the legacy `vc5_encoder.h` enum
(`VC5_ENCODER_PIXEL_FORMAT`) includes packed-12 variants (`RGGB_12P`,
`GBRG_12P`) that route through the legacy VC5 encoder. FUSED does not
accept packed-12 input; this is the `gpr_tools` /
`vc5_encoder_process` API boundary. Mapping from the legacy enum
(values 0-6) to the FUSED `pixel_format` field (values 0-5) is not 1:1;
until a dedicated delta table is added, `vc5_encoder_process` in
`vc5_encoder.c` is the source of truth.

### 2.3 Band manifest

Immediately after the header, the encoder writes `num_bands` consecutive
`uint32_t` (little-endian) values. Each value is the **byte length of
the corresponding band's rANS payload**. The k-th band's payload starts
at file offset `sizeof(FUSED_HEADER) + 4*num_bands + sum(band_size[0..k-1])`
(= `48 + 4*num_bands + sum(band_size[0..k-1])`).

A band size of **0** is legal and means "this band is all zeros." The
decoder fills the band with zeros without invoking the rANS decoder.
This is the encoded form of `GPR_DROP_HIGHPASS=1` (highpass bands not
encoded; the decoder reconstructs them as zero).

A band size **<64 bytes** triggers the rANS decoder's "small-band
memset" fast path: the band is treated as all zeros. The encoder
guarantees that a non-trivial band is never smaller than this; if it
were, the rANS framing overhead alone would exceed it. (See
`fused_band_decode_runner` for the threshold; if this changes the spec
must be revised.)

### 2.4 Band data ordering — slot maps

The band ordering depends on `multi_level` and is fixed by the encoder.
Both the encoder and decoder iterate channels in the outer loop (0..3)
and slots in the inner loop. **Slot order in the bitstream differs
from the slot order of the quant-table index** in multi-level mode;
this is an unfortunate-but-load-bearing detail.

#### 2.4.1 Single-level + LL — `num_bands=16`

4 channels × 4 bitstream slots = 16 bands. Each band is at
`band_width × band_height = (ch_width/2) × (ch_height/2)` where
`ch_width  = width/decimate/2` and `ch_height = height/decimate/2`.

| Slot | Subband | Notes |
|---|---|---|
| 0 | LL1 | Encoded with quant divisor `qt[0] × 16` (see §6.2 LL-magnitude trick) |
| 1 | LH1 | quant divisor `qt[1]` |
| 2 | HL1 | quant divisor `qt[2]` |
| 3 | HH1 | quant divisor `qt[3]` |

Channel order:

| Channel | Name | Meaning |
|---|---|---|
| 0 | GS | Green sum, `(G1+G2)>>1` |
| 1 | RG | Red minus green, `((R-GS)+mid2)>>1` |
| 2 | BG | Blue minus green, `((B-GS)+mid2)>>1` |
| 3 | GD | Green difference, `((G1-G2)+mid2)>>1` |

Band index in the bitstream: `band_idx = ch * 4 + slot`.

#### 2.4.2 Multi-level — `num_bands=40`

4 channels × 10 bitstream slots = 40 bands. Slot dimensions cascade:

```text
bw1, bh1 = ch_width/2, ch_height/2             // level-1 highpass
bw2, bh2 = (bw1+1)/2,  (bh1+1)/2               // level-2 highpass
bw3, bh3 = (bw2+1)/2,  (bh2+1)/2               // level-3 highpass + LL3
```

The `+1` rounding-up is load-bearing: odd intermediate widths must not
silently drop the right column. The encoder uses the same odd-width
boundary handler in `horizontal_filter` (output last column is the
unpaired pixel doubled, no highpass contribution).

**Bitstream slot order** (the order in the file, from
`fused_encode.c::gpr_encode_fused_frame_multilevel`):

| Slot | Subband | Dims | Quant-table index |
|---|---|---|---|
| 0 | LH1 | bw1×bh1 | qt[7] |
| 1 | HL1 | bw1×bh1 | qt[8] |
| 2 | HH1 | bw1×bh1 | qt[9] |
| 3 | LH2 | bw2×bh2 | qt[4] |
| 4 | HL2 | bw2×bh2 | qt[5] |
| 5 | HH2 | bw2×bh2 | qt[6] |
| 6 | LH3 | bw3×bh3 | qt[1] |
| 7 | HL3 | bw3×bh3 | qt[2] |
| 8 | HH3 | bw3×bh3 | qt[3] |
| 9 | LL3 | bw3×bh3 | qt[0] × 16 (LL-magnitude trick) |

**Quant-table index order** (used by `quality_tables[][10]` and by the
decoder's `q_l1` / `q_l2` / `q_l3` arrays):

| qt index | Subband |
|---|---|
| 0 | LL3 |
| 1 | LH3 |
| 2 | HL3 |
| 3 | HH3 |
| 4 | LH2 |
| 5 | HL2 |
| 6 | HH2 |
| 7 | LH1 |
| 8 | HL1 |
| 9 | HH1 |

Band index in the bitstream: `band_idx = ch * 10 + slot`.

### 2.5 Conformance

A compliant decoder MUST:

* Reject files with `magic != 0x44535546` (return `-3` or equivalent).
* Reject files with `version != 1` (return `-4`).
* Reject `multi_level=0, num_bands=12` (return `-5` — not decodable).
* Reject `num_bands ∉ {16, 40}` (return `-6`).
* Reject `quality >= 12` (return `-7`).
* Treat `band_size[k] == 0` as a zero band.
* Walk `band_size[k] < 64` past the rANS payload but produce a zero
  band (the encoder's small-band sentinel).

---

## 3. Color transform

Bayer pixels are read in 2×2 blocks (one R, two G, one B per block).
Before any wavelet, the encoder converts each block to a 4-channel
representation. Each output channel is a separate scalar plane the
same size as `ch_width × ch_height` (where `ch_width = width / 2` and
`ch_height = height / 2`).

### 3.1 Forward (encoder)

Given a 2×2 Bayer block, four logged pixel values
`(R, G1, G2, B) = (log_table[R_raw], log_table[G1_raw], …)`
are converted via:

```c
GS = (G1 + G2) >> 1;
RG = ((R - GS)  + mid2) >> 1;
BG = ((B - GS)  + mid2) >> 1;
GD = ((G1 - G2) + mid2) >> 1;
```

Where `mid2 = log_max` (the maximum value for the log table, i.e.
`(1 << log_bits) - 1`). The `+mid2` and `>>1` together bias the chroma
differences into a non-negative range that maps cleanly to int16
storage. `GS` is **not** biased (it is unsigned anyway).

Source: `fused_encode.c::unpack_all_channels_row`, lines ~870-963.

### 3.2 Inverse (decoder)

After dequant + inverse wavelet, the decoder has four channels at
`ch_width × ch_height`. For each pixel position (after clamping
each channel to `[0, log_max]`):

```c
rg -= midpoint;   // midpoint = 1 << (log_bits - 1)
bg -= midpoint;
gd -= midpoint;

r  = (rg << 1) + gs;
b  = (bg << 1) + gs;
g1 = gs + gd;
g2 = gs - gd;

// clamp each output to [0, log_max]
// apply inverse log curve: x_out = log_table[x] >> (16 - log_bits)
```

Then write `(r, g1, g2, b)` into the Bayer output. For RGGB:

```text
row 0 column 2x:     R          row 0 column 2x+1:   G1
row 1 column 2x:     G2         row 1 column 2x+1:   B
```

For GBRG:

```text
row 0 column 2x:     G1         row 0 column 2x+1:   B
row 1 column 2x:     R          row 1 column 2x+1:   G2
```

Note: the decoder uses `midpoint = 1 << (log_bits - 1)` (NOT
`(1 << log_bits) - 1`). The encoder uses `mid2 = log_max`. Despite the
asymmetric names, the arithmetic balances: encoder adds `log_max` then
`>>1` (effectively adding `log_max/2 ≈ midpoint`), decoder subtracts
`midpoint` then `<<1`. Round-trip is bit-identical for in-range inputs.

Source: `fused_decode.c::decode_fused_single_level_ll` and
`gpr_decode_fused_impl`, lines ~940-1005.

---

## 4. Log curve

Both encoder and decoder operate in a logarithmic intensity domain.
The encoder applies a log curve to each Bayer sample **before** the
color transform; the decoder applies the inverse log curve **after**
reversing the color transform. The log-curve domain matches
`log_bits` (12, 14, or 16); 12 and 14 share the same LUT structure but
different table sizes.

### 4.1 Encoder log curve (forward)

```c
y = max_out * log10(x / max_in * 112 + 1) / log10(113)
```

Where `max_in = max_out = (1 << log_bits) - 1`. The function maps
`[0, max_in] → [0, max_out]` monotonically with concentration near zero
(gives more code values to shadows). The 112 / 113 constants are
historic CineForm; do not change them.

The LUT is computed once at startup by `SetupEncoderLogCurve` (file
`source/lib/vc5_common/logcurve.c`). The fused encoder can also use a
NEON polynomial approximation (`FUSED_LOG_POLYNOMIAL`) that is
guaranteed ≤1 LSB error vs. the LUT across the 14-bit and 16-bit
input ranges.

### 4.2 Decoder log curve (inverse)

```c
x = max_out * (10^(y/max_in * log10(113)) - 1) / 112
```

The decoder normalizes the input to `[0,1]`, applies `pow(10, ...)`,
then renormalizes. The result is clipped to `[0, max_out]` and stored
as `uint16_t`. The LUT is computed by `SetupDecoderCurve` at startup.

The decoder always reads from `DecoderLogCurve14` if `log_bits <= 14`,
or `DecoderLogCurve16` if `log_bits == 16`. The 12-bit table exists
for the legacy VC5 path but is not used by the FUSED decoder.

Output bit-depth scaling: the decoder shifts the LUT output right by
`16 - log_bits` to produce final sample values at the declared bit
depth.

---

## 5. Wavelet

The codec uses a **5/3 lifted 2D wavelet** with a 1-tap prediction
(highpass) and 2-tap update (lowpass), applied separably (horizontal
then vertical). The same lifting structure is shared by the encoder
and decoder.

### 5.1 Horizontal filter (encoder)

For an input row `input[0..width-1]` and prescale `p` (always 2):

```c
prescale_rounding = (1 << p) - 1;
#define PS(v) (((v) + prescale_rounding) >> p)

// Left boundary (i=0):
lowpass[0]  = PS(input[0]) + PS(input[1]);
highpass[0] = PS(input[0]) - PS(input[1]);

// Interior (1 <= i < half - 1):
e0       = PS(input[2*i]);
o0       = PS(input[2*i + 1]);
e_prev   = PS(input[2*i - 2]) + PS(input[2*i - 1]);
e_next   = PS(input[2*i + 2]) + PS(input[2*i + 3]);
lowpass[i]  = e0 + o0;
highpass[i] = ((e_next - e_prev + 4) >> 3) + (e0 - o0);

// Right boundary (i = half - 1):
lowpass[half-1]  = PS(input[2*(half-1)])   + PS(input[2*(half-1) + 1]);
highpass[half-1] = PS(input[2*(half-1)])   - PS(input[2*(half-1) + 1]);

// Odd-width tail: if (width & 1) {
//   PIXEL last = PS(input[width-1]);
//   lowpass[half]  = last + last;
//   highpass[half] = 0;
// }
```

The `+4 >> 3` is the rounding for the centered prediction (1/8). The
left/right boundaries use symmetric mirroring (no prediction term).

Source: `fused_encode.c::horizontal_filter`, lines ~299-405.

### 5.2 Vertical filter (encoder)

For 6 consecutive horizontal-filter output rows
`rows[0..5]` (each `lowpass` or `highpass`), and column `c`:

```c
// Middle rows (!is_top && !is_bottom):
r0 = rows[0][c]; r1 = rows[1][c]; r2 = rows[2][c];
r3 = rows[3][c]; r4 = rows[4][c]; r5 = rows[5][c];
low  = r2 + r3;
high = ((r4 + r5 - r0 - r1 + 4) >> 3) + (r2 - r3);

// Top rows / bottom rows use the same boundary mirroring as horizontal:
// is_top  : low = r0 + r1;
// is_bot  : low = r2 + r3;  (and high uses the truncated halo)
```

The vertical filter is run twice per row pair: once on the LP rows
(producing LL + LH for that row pair) and once on the HP rows
(producing HL + HH).

After each vertical output, `quantize_scalar(value, midpoint, multiplier)`
is applied:

```c
mag       = (value < 0) ? -value : value;
q         = (int32_t)(((int64_t)(mag + midpoint) * multiplier) >> 16);
quantized = (value < 0) ? -q : q;

// where:
midpoint   = (divisor > 1) ? (divisor >> 1) - 1 : 0;
multiplier = (divisor > 0) ? ((1 << 16) / divisor) : 0;
```

This is fixed-point integer division by `divisor`, with a deadzone
around 0 of `±midpoint`. Equivalent to `round(value / divisor)` for
small magnitudes, with sign-symmetric rounding.

Source: `fused_encode.c::quantize_scalar` and
`vertical_filter_quantize_row`, lines ~285-660.

### 5.3 Multi-level recursion

In multi-level mode the encoder runs the wavelet 3 times:

* **Level 1**: input is the channel-space-decimated 4-channel image,
  output is `(LL1, LH1, HL1, HH1)`.
* **Level 2**: input is LL1, output is `(LL2, LH2, HL2, HH2)`.
* **Level 3**: input is LL2, output is `(LL3, LH3, HL3, HH3)`.

The `prescale=2` is reapplied at every level (so the cumulative
prescale at the LL3 output is 2^6 = 64). The decoder reverses this by
passing `descale=2` to `InvertSpatialQuantDescale16s` at each inverse
level.

### 5.4 Inverse wavelet (decoder)

The decoder reverses the lifting. Per row pair `(even_row, odd_row)`,
per column:

```c
// Interior, 3 rows of LP + 1 row of HP:
even = ((r0 - r2 + 4) >> 3 + r1 + hp) >> 1;
odd  = ((-r0 + r2 + 4) >> 3 + r1 - hp) >> 1;
```

Then the horizontal inverse runs over `(even, odd)`. Boundary handling
mirrors the encoder's boundary handling.

`InvertSpatialQuantDescale16s` dequantizes-by-multiplication (negative
quant convention; see §6.3) before the lifting math, and shifts the
horizontal output left by `descale - 1` = 1 to restore magnitude.

Source: `source/lib/vc5_decoder/inverse.c::InvertSpatialQuantDescale16s`.

---

## 6. Quantization

### 6.1 Quality presets

The codec ships 12 quality presets. The table is identical between the
FUSED encoder (`fused_encode.c::quality_tables`) and the legacy VC5
encoder (`vc5_encoder.c`); a mismatch would break decoder
compatibility.

| q | Name | Quant divisors `[LL3, LH3, HL3, HH3, LH2, HL2, HH2, LH1, HL1, HH1]` |
|---|---|---|
| 0 | Low | 1, 24, 24, 12, 64, 64, 48, 512, 512, 768 |
| 1 | Medium | 1, 24, 24, 12, 48, 48, 32, 256, 256, 384 |
| 2 | High | 1, 24, 24, 12, 32, 32, 24, 128, 128, 192 |
| 3 | Filmscan-1 (default) | 1, 24, 24, 12, 24, 24, 12, 96, 96, 144 |
| 4 | Filmscan-X | 1, 24, 24, 12, 24, 24, 12, 64, 64, 96 |
| 5 | Filmscan-2 | 1, 24, 24, 12, 24, 24, 12, 32, 32, 48 |
| 6 | Filmscan-3 | 1, 12, 12, 6, 12, 12, 6, 16, 16, 24 |
| 7 | Filmscan-4 | 1, 6, 6, 4, 12, 12, 6, 16, 16, 24 |
| 8 | Filmscan-5 | 1, 4, 4, 2, 10, 10, 6, 16, 16, 24 |
| 9 | Reserved | mirrors q=8 |
| 10 | Reserved | mirrors q=8 |
| 11 | CNN-aware | 1, 24, 24, 12, 24, 24, 12, 192, 192, 576 |

Each row is indexed by **quant-table index** (see §2.4.2). In
single-level mode only slots 0..3 are used (LL1 dequantization
re-purposes slot 0; LH1/HL1/HH1 use slots 1/2/3).

Each divisor is in units of "denominator of the quantization step". A
divisor of 1 is a pass-through; a divisor of 24 means the post-wavelet
coefficient magnitude is shrunk by ~24× and re-expanded by the decoder.

### 6.2 LL-magnitude trick (class-15 ceiling)

The wavelet output is stored as `int16_t` and entropy-coded via the
rANS coder whose magnitude classes (`JANS_MAG_CLASSES = 16`) cover
magnitudes up to **2047** (class 15 covers `mag = 1024..2047` with 10
extra residual bits). Magnitudes above 2047 are clamped at encode time
and dequantize incorrectly — visible as PSNR collapse.

The legacy VC5 path has a different ceiling: its VLC codebook
(`ComputeCubicTable`, see §6.3) covers only `mag = 0..1023`. This is
the constraint that drives the legacy-encoder quant floor.

After three levels of 5/3 wavelet with `prescale=2`, the **LL3** band
magnitude on 14-bit input can reach ~16k. The encoder works around
this by dividing LL3 by an extra factor:

```c
#define FUSED_LL3_EXTRA_DIVISOR 16
int ll3_div = qt[0] * 16;          // effective quant divisor for LL3
```

The decoder must multiply LL3 by the same factor before passing it to
the inverse wavelet:

```c
int ll3_dequant = qt[0] * 16;
for each LL3 coefficient: p *= ll3_dequant;
```

The same trick is applied to **LL1** in single-level + LL mode (slot 0
of the 16-band manifest): the encoder uses `qt[0] * 16` and the
decoder multiplies by `qt[0] * 16` to undo it. See
`fused_encode.c::setup_channel_state` (line ~3110) and
`fused_decode.c::decode_fused_single_level_ll` (line ~1232).

### 6.3 Per-band quant floor (legacy VC5 only)

The legacy VC5 encoder applies a per-band **minimum quant divisor** to
prevent magnitude overflow at the high-quality presets (q=7, q=8).
After the bit-depth scaling step (which divides divisors by `12 / bits`
for `bits > 12`), the encoder floors each divisor:

```c
static const QUANT min_quant[10] = { 0, 14, 14, 8, 1, 11, 1, 1, 1, 1 };
//                                   LL3 LH3 HL3 HH3 LH2 HL2 HH2 LH1 HL1 HH1
```

This is the result of investigation in `encoder.c` PRs #16 and #20 /
tasks #159 and #162. Without the floor, deep-level highpass bands at
q=7/q=8 produce post-quant magnitudes >1023 on real photographic
content; the encoder clamps to 1023, the decoder dequantizes to
`1023 * quant` instead of the true value, and PSNR collapses by 5-10
dB on dark scenes.

The **FUSED encoder** does NOT apply this floor — its preset table is
already chosen so that magnitudes stay below the ceiling at every q,
and there is no bit-depth scaling step. (At q=8 the FUSED preset has
the same `[..., 4, 4, 2, 10, 10, 6, 16, 16, 24]` as the legacy table,
which already meets `min_quant`.)

Decoders MUST NOT apply the quant floor on the decode side — the
encoder bakes it into the divisors it actually used and writes that to
the file (legacy VC5 transmits per-subband quant via tag-value pairs;
see §8).

### 6.4 Encoder→decoder quant convention (FUSED)

The decoder's `DequantizeBandRow16s` interprets a **positive** `QUANT`
as "VC5 companded + quantized" (applies the cubic uncompanding curve
before multiplying by the quant). The FUSED encoder does **not**
compand, so the decoder passes **negated** quants (`-qt[k]`) to
`InvertSpatialQuantDescale16s`, signalling "dequantize-by-multiply only,
no companding."

Code authors implementing a new decoder may simplify this by skipping
the negation and inlining a `value *= |q|` step — the result is
bit-identical.

### 6.5 GPR_QUANT_OVERRIDE (dev-only)

The encoder reads an environment variable `GPR_QUANT_OVERRIDE` whose
value is a comma-separated `slot:value,slot:value,...` list (e.g.
`"7:144,8:144,9:216"`). Each `slot` indexes into the 10-entry quant
table; matching slot is overridden with `value` before the encoder
initializes per-channel divisors.

This is a **calibration / development knob** only. It is not part of
the bitstream — the bitstream records `quality`, not the per-slot
overrides. The decoder reads the same env var and reconstructs the
override-aware quant table from `quality` AND the env. **A mismatched
override between encoder and decoder produces garbage output.**

Disposition: this knob will be removed before the spec is considered
shippable (see `docs/ENV_VAR_CLEANUP.md`). The same effect should be
achievable by adding new quality preset rows (e.g. q=11 was added for
the CNN-aware preset; q=12+ slots are available).

### 6.6 Rate control hook

The encoder exposes `gpr_encode_fused_set_quant_scale(ctx, scale)` for
per-frame rate control. Scale is clamped to `[0.25, 16.0]`; the
encoder multiplies each level-1 quant divisor (LL/LH/HL/HH) by `scale`
before recomputing midpoint/multiplier. In multi-level mode, L2/L3
quants are unaffected (matching the legacy encoder's per-frame RC
behavior).

The bitstream records only the original `quality`; the decoder
reconstructs `qt[k]` from the preset table and must NOT apply the
scale (the encoder bakes it into the divisor it actually used and the
per-band magnitudes are stored at the scaled units).

Open spec note: this is a leaky abstraction because the bitstream loses
the information about what the actual divisors were. The decoder still
works because the quant value only affects the **dequant** step
(multiply by `qt[k]`), and the encoder's quantized magnitudes are
already at the scaled units. But this means a file encoded with
`scale != 1.0` cannot be reproduced from its bitstream without external
knowledge of the scale. This needs to become an explicit per-band quant
table in the file before the FUSED spec is considered shippable. See
`docs/ENV_VAR_CLEANUP.md`.

---

## 7. rANS entropy coding

Each band's quantized coefficients are entropy-coded with a **4-way
interleaved rANS coder** that emits a self-describing byte blob. The
encoder and decoder functions are:

```c
int jans_encode_band_x4(uint8_t *out, size_t out_cap,
                         const int32_t *data, int width, int height, int pitch);
int jans_decode_band_x4(const uint8_t *in,  size_t in_size,
                         int32_t *data, int width, int height, int pitch);
```

The band blob is opaque from this spec's perspective — an implementer
should use the reference `jans_decode_band_x4` and pair it with an
encoder that produces bit-identical output. Brief structural notes:

* The coder packs (run-length, magnitude class, sign) triples into a
  **single ANS symbol** per coefficient (run-length-value coding). 128
  joint symbols (`JANS_RUN_CLASSES * JANS_MAG_CLASSES = 10 * 16`) plus
  a 1-symbol end-of-band marker.
* Symbol frequencies are histogrammed in Pass 1 (encoder) and
  serialized as part of the band blob header.
* The `decode_info` table is sized at `JANS_TABLE_BITS = 11` →
  `JANS_TABLE_SIZE = 2048` entries (plenty for 128 symbols).
* When the inline encoder is in stripe mode, it can emit a multi-blob
  form gated by the sentinel value `0xFFFFFFFF` as the first
  `uint32_t` of the band payload; the decoder recognizes the
  marker and walks per-stripe.

The **class-15 magnitude ceiling** (2047 for rANS; 1023 for the
legacy VLC) is the constraint that drives the LL-magnitude trick
(§6.2) and the legacy-encoder quant floor (§6.3). Encoders that
produce out-of-range magnitudes will see the rANS coder clamp them,
causing visible artifacts on decode.

Reference: `source/lib/vc5_common/ans_joint.{h,c}`. Bit layout of the
blob itself is not duplicated here; an implementer producing a
new coder must regression-test against `jans_decode_band_x4`.

Open spec note: the rANS blob layout (header bytes, frequency-table
serialization, stripe-mode framing) still needs a dedicated subsection.
Until that is written, the reference C code is the source of truth.

---

## 8. Legacy VC5 path

The legacy `gpr_tools` codec uses `vc5_encoder_process` (in
`source/lib/vc5_encoder/vc5_encoder.c`). It is a substantially different
code path:

* **Wavelet**: 3-level (same lifting math, same prescale = 2).
* **Color transform**: same GS/RG/BG/GD.
* **Log curve**: same (12-bit, 14-bit, or 16-bit LUT).
* **Quantization**: same preset table (`vc5_encoder.c` lines 84-106)
  but with an extra "per-bit-depth scaling" step (`bits > 12`: scale
  divisors by `12 / bits`, then floor at `min_quant`).
* **Entropy coding**: legacy VLC (variable-length code) by default; ANS
  is selectable via `encoder->ans_enabled` and recorded in the
  bitstream via a `CODEC_TAG_BandCodingMethod` tag.
* **Bitstream**: tag-value pair stream wrapped inside a DNG container
  (see `docs/format-spec-v2.md`). Tag IDs in `encoder.c` include
  `CODEC_TAG_ChannelCount`, `CODEC_TAG_ImageWidth`,
  `CODEC_TAG_ImageHeight`, `CODEC_TAG_PrescaleShift`,
  `CODEC_TAG_SubbandNumber`, `CODEC_TAG_Quantization`,
  `CODEC_TAG_LargeCodeblock`, etc.

The legacy VC5 stream is **NOT** the FUSED stream. They share the
wavelet, color transform, log curve, and (mostly) the quant tables,
but the wrapper formats are mutually unintelligible. A decoder for one
will not decode the other.

For full VC5 bitstream documentation, refer to:

* `source/lib/vc5_encoder/syntax.c` and `source/lib/vc5_decoder/syntax.c`
  for the tag-value layer.
* `source/lib/vc5_encoder/encoder.c::EncodeImage` for the top-level
  ordering of header tags + per-channel encode.
* `docs/format-spec-v2.md` for the DNG container framing.

Open spec note: this section is intentionally light. The full legacy
VC5 bitstream syntax (tag-value sequence, codeblock structure, VLC
codebooks) is substantial and should live in its own document. Until
that exists, the source files above are the spec.

---

## 9. Container — GPRaw MOV

For video, FUSED frames are wrapped in an ISO BMFF / MOV container with
a custom `codec_tag`. The wire format is described in
`tools/gpraw/include/gpraw.h`.

| Field | Value |
|---|---|
| Container | `.mov`, ISO BMFF, `movflags=frag_keyframe+empty_moov` |
| Video codec_tag | `'GPRr'` = `0x47 0x50 0x52 0x72` (`GPRAW_CODEC_TAG`) |
| AVCodecID | `AV_CODEC_ID_NONE` (tag-only) |
| Frame payload | One AVPacket per video frame; payload starts with `FUSED_MAGIC` and contains the full FUSED bitstream as documented in §2 |
| Frame timing | Monotonic PTS/DTS at the requested fps; each GPR frame is a keyframe |

NOTE: an older internal version of the writer (`GPRMovWriter.m`) uses
the four-character tag `'GPR1'`. The shipping `tools/gpraw` library
uses `'GPRr'`. Readers should accept either; writers should emit
`'GPRr'`.

The video stream advertises **output (decimated) dimensions** in its
sample-description box — i.e. `width = FUSED_HEADER.width / decimate`
and `height = FUSED_HEADER.height / decimate`. This matches what the
decoder will produce. The full / pre-decimation Bayer dimensions are
recoverable only by parsing the in-payload FUSED_HEADER.

### 9.1 Track metadata (moov.udta, written via AVStream.metadata)

```text
gpr.codec_version      e.g. "vc5/2.0+gpr"
gpr.quality            0..11
gpr.cfa_pattern        "RGGB" or "GBRG"
gpr.bit_depth          14 or 16
gpr.black_level        integer (min channel)
gpr.white_level        integer
gpr.encoder_settings   JSON blob, env-var equivalents
gpr.source_dng_path    optional traceability
gpr.color_matrix       9 comma-separated floats (XYZ if known)
```

### 9.2 Per-frame metadata

Stored as `AV_PKT_DATA_STRINGS_METADATA` packet side data
(NUL-separated `key=value` pairs):

```text
gpr.frame_timestamp    nanoseconds from start
gpr.iso                ISO speed
gpr.shutter            shutter angle (degrees)
gpr.wb_neutral         "R,G,B" as-shot WB neutrals
```

### 9.3 Reserved tracks

The writer reserves slots for an audio track (PCM s16-LE,
codec_tag passthrough) and a timecode track (`'tmcd'`). These are
optional and may be absent.

---

## 10. Conformance

There is currently **no formal conformance suite**. The pragmatic
definition of conformance is:

> A FUSED encoder is conformant if, given the same input Bayer plane and
> the same `(width, height, pixel_format, quality, multi_level,
> decimate, include_ll)` configuration, it produces byte-identical
> output to `gpr_encode_fused_frame` from the reference C
> implementation at the same commit.

> A FUSED decoder is conformant if, given any byte-identical output of
> the reference encoder, it produces a Bayer plane that is
> byte-identical to `gpr_decode_fused`'s output at the same commit.

Two practical tests live in the repo:

* `tools/test/test_capabilities.py` — encoder/decoder round-trip
  regression matrix across the supported `(pixel_format, quality,
  multi_level, decimate)` configurations on a fixed corpus.
* `tools/test/test_still_matrix.sh` — DNG-domain image regression
  for the still-image (gpr_tools / legacy VC5) path.

A future conformance suite should publish:

1. A small reference corpus of Bayer planes (one per `pixel_format`).
2. A bit-exact reference bitstream per `(corpus_entry, quality, mode)`.
3. A Bayer-output reference per reference bitstream, for decoder
   conformance.
4. A tolerance budget for the inverse log curve (currently bit-exact;
   the polynomial-log encoder path is guaranteed ≤1 LSB error in the
   forward direction, but the decoder always uses the LUT).

---

## 11. Open spec questions

The following encoder/decoder behaviors are controlled by environment
variables (`docs/ENV_VAR_CLEANUP.md`) and are NOT recorded in the
bitstream. A file produced under one set of env-var settings is not
generally reproducible from its bitstream alone:

| Env var | Effect | Promote-to-API plan |
|---|---|---|
| `GPR_QUANT_OVERRIDE` | Per-subband quant divisor override | Dev-only; remove or replace with new quality preset rows |
| Rate-controller `scale` (via `gpr_encode_fused_set_quant_scale`) | Multiplies level-1 divisors per frame | Promote to a per-band quant table in the header |
| `GPR_DENOISE_AUTO` | Auto-enable wavelet BayesShrink based on DNG NoiseProfile | Promote to `gpr_parameters.denoise_auto` |
| `FUSED_MULTI_LEVEL` | Selects multi-level vs single-level | Promote to API; bitstream already records this via `multi_level` field |
| `GPR_INCLUDE_LL` | Selects single-level + LL vs single-level no-LL | Auto-derive from `multi_level=0` (single-level no-LL is not decodable) |
| `GPR_ROW_DECIMATE`, `GPR_COL_DECIMATE` | 2× channel-space decimation | Bitstream already records this via `decimate` field. Promote env→API. |
| `GPR_DROP_HIGHPASS` | Encode HP bands as size=0 | Bitstream already records this (HP size=0). Promote env→API. |
| `GPR_DECODE_LL_ONLY` | Discard HP at decode (fast playback path) | Decoder-side flag; not part of the file format |
| `GPR_DECODE_HPSYNTH` | Synthesize HP from LL gradients when missing | Experimental polish; not part of the file format |

The spec will be considered complete after each of these env vars has
either been removed or moved to an explicit API parameter. The
bitstream format itself is not expected to change during this cleanup;
the field names and semantics in §2 are stable.

### 11.1 Things deliberately left out of v1

* No per-band quant table in the bitstream (only the `quality` index).
  This means the rate-controller scale (§6.6) leaks across encode →
  decode unless both sides agree.
* No bitstream version of the BayesShrink denoise state. Denoise is a
  pre-quant transform on the encoder side; the decoder is oblivious.
* No noise-reconstruction state (the DNG NoiseProfile lives in the
  DNG container or in `gpr.encoder_settings` track metadata).
* The `pixel_format` field encodes both Bayer ordering AND a nominal
  bit depth, but the operative bit depth is `log_bits`. This
  redundancy is harmless but a v2 should consider unifying them.
* No CRC / integrity check over the band manifest or the band data.
  Errors propagate as decode failures (return codes), not as detected
  corruption.
