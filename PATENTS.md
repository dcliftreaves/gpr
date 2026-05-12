# Patent Posture

This document is a public summary of the patent landscape that GPR 2.0
operates within. It is provided for informational purposes only and is
**not legal advice**. Anyone considering commercial deployment of GPR 2.0
— particularly in-camera raw video at 2K-and-above resolutions and 24-and-above
frame rates — should consult patent counsel and obtain an independent
freedom-to-operate analysis. The fuller research, including links to the
specific patents and litigation history, is in
[`docs/raw-video-landscape.md`](docs/raw-video-landscape.md).

## The Apache-2.0 / MIT grant from GoPro

GPR is released by GoPro under a dual Apache-2.0 / MIT license. The
[Apache-2.0 patent grant](https://www.apache.org/licenses/LICENSE-2.0)
(section 3) gives every recipient a perpetual, worldwide, royalty-free,
irrevocable license to patent claims **necessarily infringed by GoPro's
Contributions, taken alone or combined with the Work**. That covers:

- GoPro's own VC-5 / CineForm patents to the extent the code reads on them.
- The GAS-style green-channel pre-processing in
  `source/lib/vc5_encoder/raw.c`, which is inherited unchanged from upstream
  CineForm/GPR and predates the priority dates of RED's GAS patents.
- The wavelet transform, quantization, rANS / VLC entropy coding, and
  container code as written.

The grant **terminates** if the licensee files a patent suit alleging
the Work infringes a patent — the standard Apache-2.0 retaliation
clause. The grant does **not** convey any rights from third-party
patent holders.

GoPro has filed a patent statement on file with SMPTE for ST 2073
("Patent_Statement_GoPro_VC-5"). That statement is not published on the
public web and would need to be requested from SMPTE under their IP
policy. Until it is read, it should not be assumed to convey royalty-free
terms for hardware raw use; anecdotal pricing in the open-source
announcement put hardware raw VC-5 licenses near $20/camera in the
professional market (2017 data, may be stale).

## Notable third-party patents

Two patent families are the dominant exposure for in-camera compressed
raw video. Both are held by Nikon following its March 2024 acquisition
of RED Digital Cinema.

### RED / Nikon `'967` family — "in-camera compressed raw video"

- Family head: **US 7,830,967** ("Video camera"), priority **2007-04-11**.
- Continuations: US 8,174,560, US 8,358,357, US 8,872,933, US 9,230,299,
  US 9,245,314, US 9,436,976, US 9,479,749.
- All expected to expire on or about **April 11, 2028** (20-year term
  from the earliest priority date).
- Claim shape: capturing raw Bayer data at 2K-or-higher resolution and
  23-or-higher frames per second and compressing it visually losslessly
  on the camera, with optional pre-processing that modifies R and B
  channels based on G.
- Litigation history includes RED v. Sony (settled 2013), RED v.
  Kinefinity (led Kinefinity to drop CinemaDNG), the Apple ProRes RAW
  IPR challenge that Apple lost (now pays royalties), and RED v. Nikon
  (dismissed after Nikon's full acquisition of RED).

### RED / Nikon `'384` family — "Green Average Subtraction"

- Family head: **US 9,521,384** ("Green Average Subtraction in Image
  Data"), priority **2013-02-14**.
- Related: US 9,716,866, US 10,582,168 ("Green Image Data Processing").
- Expected to expire on or about **February 13, 2034**.
- Claim shape: subtracting an averaged green channel from R and B prior
  to compression — `GS = (G1+G2)/2`, `RG = R1 - GS`, `BG = B1 - GS`
  with `GD = G1 - G2`.

### GPR 2.0's exposure

GPR's encoder performs the literal GAS math in
`source/lib/vc5_encoder/raw.c`. That code is inherited from GoPro
CineForm, which has been on the market in some form since 2005 and
publicly documented in [the Silicon Imaging SI-2K technical overview
(2007)](https://www.siliconimaging.com/DigitalCinema/Files/CineForm_RAW_TechOverview.pdf).
Prior-art arguments have been raised in litigation and rejected by the
PTAB; despite the prior art, **the patents remain enforceable** until
they expire or are invalidated by a court.

GPR 2.0 is designed to enable in-camera raw video at 24 fps × 45 MP
on consumer storage (see `docs/operating-envelope.md`). That deployment
target sits squarely within the `'967` claim space. Reading on a patent
is not the same as infringing it — defenses include prior art,
license, exhaustion via Apache-2.0 grant, and challenge to validity —
but counsel review is the only way to confirm which defenses apply to
a given product.

## What GPR 2.0 is *not* exposed to

GPR's patent surface area is unusually narrow for a video codec:

- **No DCT** — no MPEG / H.26x patent-pool exposure.
- **No motion compensation, no prediction** — no HEVC / AV1 pool
  exposure.
- **2-level wavelet, no zerotrees or EBCOT** — no SPIHT or JPEG 2000
  Part-2 reading.
- **VC-5 native entropy coding** can be selected — no Microsoft ANS
  patent exposure on that path. (rANS paths exist in 2.0 and would
  need a separate clearance check against US 11,234,030 if used in
  shipping product.)

## Posture and recommended deployment notes

These framings are starting points for discussion with counsel and
business stakeholders, not legal opinions.

- **Bit-stream conformance to SMPTE ST 2073-1..-3 is preserved.** That
  keeps the "implementing a published SMPTE standard" defense
  available.
- **Extensions are factored as separable modules** with kill-switches:
  rate control, denoise, dual-encoder mode, and adaptive bitrate can
  all be disabled at runtime or compile time without breaking decode.
  This lets a deployer respond to any narrow patent claim by removing
  the affected feature rather than the whole codec.
- **A GAS kill-switch is on the follow-up list** (`docs/followups.md`,
  item "Kill-switch for Green Average Subtraction"). Building the
  codec with direct R/G1/G2/B channels instead of GS/RG/BG/GD would
  reduce file efficiency by an estimated 20-40% but remove the `'384`
  claim-family exposure.
- **The `'967` family expires in April 2028.** After that date the
  in-camera compressed-raw claim space is open.

## How to report a patent concern

If you believe GPR 2.0's code reads on a patent you hold, please open
an issue or contact the maintainers privately (see `SECURITY.md` for
the reporting channel). We will engage in good faith.

## See also

- [`docs/raw-video-landscape.md`](docs/raw-video-landscape.md) — full
  research with patent links, litigation history, and sources.
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) —
  the relevant patent-grant text.
- [RED's published patent list](https://www.red.com/legal/patent).
- [SMPTE Patent Statements page](https://www.smpte.org/patent-statements).
