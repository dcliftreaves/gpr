# Raw Video Codec Landscape & Patent Considerations

**Date:** 2026-05-11
**Author:** Research compiled for MISSION 1 raw video pipeline shipping decisions
**Status:** Internal research doc — not legal advice. All patent claims described are landscape sketches that a clearance attorney would want to confirm independently.

---

## TL;DR

- **MISSION 1 already ships GoPro's GPR/VC-5 wavelet pipeline.** That product decision implies GoPro has internally cleared the base codec for its own products. Our pipeline is built on top of that base.
- **The dominant patent risk in compressed-raw-video is RED's portfolio** — specifically, the `'960`, `'933`, `'314`, `'384` and successor patents covering (a) capturing raw Bayer data at ≥2K/23 fps with ≥6:1 visually lossless compression and (b) "Green Average Subtraction" (GAS) pre-processing before compression. RED was acquired by Nikon in March 2024, so the same portfolio now belongs to Nikon. Patents in this family expire from **April 2028** (the original `'967` "Video camera") out to **2034–2035** for successor GAS patents.
- **Our code performs GAS-style green subtraction** (`source/lib/vc5_encoder/raw.c`: `RG = R1 - GS`, `BG = B1 - GS`). This is **inherited unchanged from GoPro's open-sourced CineForm/GPR**, which has been on the market in some form since 2005 — pre-dating RED's earliest priority date (Dec 2007). CineForm was cited as prior art in RED patent prosecution and in Apple's challenge.
- **Apache 2.0's patent grant (from GoPro)** transfers patent rights GoPro itself holds in the contributed VC-5/GPR code. It does *not* transfer rights from third parties (RED/Nikon, etc.). The grant terminates if the licensee sues anyone over the work.
- **SMPTE ST 2073 (VC-5) is a published standard, but it is not part of a royalty-free patent pool.** GoPro has filed a patent statement under SMPTE's IP policy; the actual terms have to be requested. Anecdotal numbers from CineForm's open-source announcement put hardware RAW VC-5 licenses at around $20/camera in the professional market.
- **Lower-risk extensions** (the streaming pipeline, adaptive bitrate via QP modulation, per-band quantization tweaks, denoise in the wavelet domain) are old, broadly-practiced techniques. Risk is not zero — there are individual rate-control patents — but these are not the long pole.
- **Highest-risk extensions** are anything that touches the RED claim wedge: pre-compression Bayer transforms, "visually lossless" claims at specific compression ratios, and on-camera compression of raw at 2K+/23+ fps. Our pipeline currently inherits *all three* from upstream GPR.
- **Recommended posture (caller decides):** keep the codec bit-stream conformant to VC-5/ST 2073 so a fallback to "we are implementing a published SMPTE standard" remains available; treat extensions (adaptive bitrate, denoise, rate control) as cleanly separable modules with a kill-switch; obtain a written legal read of the GoPro patent statement at SMPTE and a freedom-to-operate analysis against the active RED/Nikon patents listed below before high-volume shipping.

---

## 1. Raw Video Capture Codecs in the Market

### 1.1 REDCODE RAW (R3D)
- **Owner:** RED Digital Cinema (now owned by Nikon as of March 2024) ([Nikon press release](https://www.nikon.com/company/news/2024/0307_01.html))
- **Tech:** Originally JPEG 2000–style wavelet (CDF 9/7 lossy) applied to pre-processed Bayer raw. Newer cameras (e.g. Komodo class) moved to DCT-based compression ([Y.M. Cinema](https://ymcinema.com/2018/07/07/a-thesis-red-8k-reduces-data-rate-and-file-size/)).
- **Pre-processing:** "Green Average Subtraction" (GAS) and "pre-emphasis" log curve applied before wavelet/DCT. These pre-processing steps are at the heart of RED's patent moat ([CineD analysis](https://www.cined.com/redcode-raw-codec-dissected-by-jinni-tech-tough-accusations-against-red-in-new-video/)).
- **Compression ratios:** Marketed from 2:1 to ~22:1; Netflix caps at 8:1 for Approved Camera workflows ([REDUSER thread](https://reduser.net/threads/redcode-what-ratio-pros-cons.77936/)).
- **Licensing:** Proprietary. Apple was found to need to pay RED royalties for ProRes RAW after losing IPR challenges; DJI removed ProRes RAW from the Ronin 4D rather than license; Kinefinity removed CinemaDNG and similar formats from its cameras for the same reason ([DPReview](https://www.dpreview.com/news/3429948804/apple-loses-patent-lawsuit-will-have-to-pay-red-royalties-for-prores-raw-format), [Newsshooter](https://www.newsshooter.com/2022/02/15/dji-removes-prores-raw-from-ronin-4d-and-lowers-price/)).
- **Used in:** RED cameras (Komodo, V-Raptor, Helium, Monstro etc.).

### 1.2 ARRIRAW + Codex HDE
- **Owner:** ARRI; Codex (subsidiary of X2X)
- **Tech:** ARRIRAW is uncompressed Bayer. Codex HDE (High Density Encoding) is a *lossless* compressor applied during offload from the magazine, not in-camera; bit-exact reconstruction with ~40% size reduction ([Codex docs](https://help.codex.online/content/high-density-encoding)).
- **Notable:** HDE side-steps "in-camera compressed raw" patent claims by applying compression after capture during ingest. Variable bit rate, lossless.
- **Used in:** ALEXA family, ALEXA Mini LF, AMIRA, ALEXA 35.

### 1.3 Apple ProRes RAW / ProRes RAW HQ
- **Owner:** Apple
- **Tech:** Lossy compressed raw codec, partially-debayered, designed for HDR (16-bit float internal) ([Library of Congress format description](https://www.loc.gov/preservation/digital/formats/fdd/fdd000528.shtml)).
- **Licensing:** Proprietary; Apple licensees pay RED/Nikon royalties for the compressed-raw patent family (per the dismissed IPR ruling).
- **Used in:** DJI Zenmuse X9 (internal), Nikon Z9/Z8, external recorders (Atomos), MAVO Edge (later removed).

### 1.4 Blackmagic RAW (BRAW)
- **Owner:** Blackmagic Design
- **Tech:** *Partially de-mosaicked* "raw," not pure CFA data. Blackmagic explicitly markets this as a feature ("advanced de-mosaic in camera, edge-reconstruction, noise reduction"). Compression is not publicly documented — externally analyzed as wavelet-ish — and the partial debayer is widely believed to be a deliberate work-around of RED's compressed-raw claims ([Premiumbeat overview](https://www.premiumbeat.com/blog/what-is-blackmagic-raw/), [OWC](https://www.owc.com/blog/blackmagic-raw-explained)).
- **Compression:** Constant Bitrate 3:1, 5:1, 8:1, 12:1; Constant Quality Q0/Q1/Q3/Q5.
- **Licensing:** Proprietary, no public spec; SDK is GPU/CPU accelerated and is the only legitimate way to decode.
- **Used in:** Blackmagic Pocket Cinema, URSA, Cinema 6K/12K.

### 1.5 CinemaDNG
- **Origin:** Adobe-led open spec (2009), now ISO 12234-3 ([Wikipedia](https://en.wikipedia.org/wiki/CinemaDNG)).
- **Tech:** Sequence of DNG frames (lossless or lossy JPEG / JPEG XR / lossless JPEG variants in DNG container) optionally wrapped in MXF; multi-channel audio and 3D supported.
- **Licensing:** Adobe DNG specification is published royalty-free; ISO standard since 2025 ([CineD](https://www.cined.com/dng-is-now-an-international-iso-standard-what-it-means-for-filmmakers-and-raw-workflows/)). However, *in-camera compressed* CinemaDNG implementations may still read on RED's compressed-raw claims regardless of the container — that is what allegedly drove Kinefinity to drop CinemaDNG from MAVO LF/MAVO 6K/TERRA 4K.
- **Used in:** Blackmagic (legacy), Kinefinity (legacy), DJI Zenmuse X5 / X7, Ikonoskop A-Cam dII.

### 1.6 Sony X-OCN
- **Owner:** Sony
- **Tech:** Wavelet-based compressed raw, 16-bit ([Newsshooter](https://www.newsshooter.com/2023/05/09/sony-x-ocn-explained/)). LT/ST/XT tiers. Stored as bayer-pattern data so files are ~1/3 the size of equivalent ProRes 4444.
- **Licensing:** Proprietary. Sony was sued by RED in 2013 over compressed raw (settled).
- **Used in:** VENICE, VENICE 2, BURANO.

### 1.7 Phase One IIQ
- **Owner:** Phase One
- **Tech:** Still-photo focused but used for stop-motion / timelapse video pipelines. IIQ-L (lossless) and IIQ-S (smart / near-lossless). Container is a TIFF with raw embedded in MakerNote ([Phase One docs](https://www.phaseone.com/imaging-quality-performance/intelligent-image-quality-iiq/), [LibRaw](https://www.libraw.org/node/2555)).
- **Compression:** ~8–10× smaller than 16-bit TIFF.
- **Used in:** Phase One IQ4, XF, XT.

### 1.8 Z CAM ZRAW
- **Owner:** Z CAM
- **Tech:** Often described as "H.265+ with extra bitrate," i.e. a high-bitrate HEVC stream after partial debayering, not a true wavelet raw ([CineD comparison](https://www.cined.com/z-cam-zraw-vs-blackmagic-raw-which-one-is-better-our-lab-test/), [Newsshooter](https://www.newsshooter.com/2019/08/14/z-cam-adds-zraw-with-e2-firmware-update/)). 8:1 typical, 1.2 Gbps fixed.
- **Licensing:** Proprietary; inherits HEVC pool licensing on the encoder side.
- **Used in:** Z CAM E2 series.

### 1.9 Kinefinity KineRAW (KRW)
- **Owner:** Kinefinity
- **Tech:** Proprietary lossy compressed raw, ~3:1. Replaced CinemaDNG/ProRes RAW on MAVO Edge and others ([CineD](https://www.cined.com/kinefinity-release-kineraw-compressed-raw-codec/), [CineD removal](https://www.cined.com/kinefinity-removes-cinemadng-and-other-raw-codecs-from-its-cameras/)).
- **Strategic context:** Kinefinity's pivot away from CinemaDNG and ProRes RAW correlates with RED's litigation campaign.

### 1.10 DJI ProRes RAW (Zenmuse X9)
- **Owner:** Apple ProRes RAW licensed to DJI for the X9 sensor block on Ronin 4D.
- **Status:** DJI *removed* this feature from shipping Ronin 4Ds in early 2022, reportedly due to patent issues with RED ([Newsshooter](https://www.newsshooter.com/2022/02/15/dji-removes-prores-raw-from-ronin-4d-and-lowers-price/)).

### 1.11 GPR (GoPro) — our base
- **Owner:** GoPro
- **Tech:** VC-5/CineForm wavelet (single-level CDF-style biorthogonal, integer reversible 2-6 / 5-3 region) applied to GAS-transformed Bayer channels. Entropy coding is variable-length codes (the open-source code uses a custom VLC; some forks use rANS). Stored in DNG container ([GPR README](https://github.com/gopro/gpr), [GPR site](https://gopro.github.io/gpr/)).
- **Compression:** Marketed 10:1 to 4:1; the codebase reaches ~3.5:1 visually-lossless on the test corpus.
- **Licensing:** Apache 2.0 + MIT dual-license at the SDK level. The codec bit-stream conforms to SMPTE ST 2073-1..-3.
- **Used in:** HERO cameras (stills GPR mode), GoPro MISSION 1 (announced 2026) ([GoPro press](https://gopro.com/en/us/news/gopro-announces-three-cameras-mission-1-2026)).

---

## 2. Patent Landscape for Wavelet Video Codecs

### 2.1 The CDF / Le Gall 5/3 biorthogonal wavelet (the one we use)

- **Origin:** Le Gall & Tabatabai (1988); Cohen-Daubechies-Feauveau (1992) ([Wikipedia CDF](https://en.wikipedia.org/wiki/Cohen%E2%80%93Daubechies%E2%80%93Feauveau_wavelet)).
- **Patent status:** No known active core patents on the *math* of 5/3 or 9/7 biorthogonal wavelet transforms. These were published in mainstream academic journals in 1988 and 1992 — any 1990s-era US patents on the transform itself have aged out (20-year term from filing).
- **JPEG 2000:** The core coding system of JPEG 2000 (which uses 5/3 lossless and 9/7 lossy) was declared royalty-free by ~17 contributors. The JPEG committee's official position: "implementable in their baseline form without payment of royalty and license fees" ([Wikipedia JPEG 2000](https://en.wikipedia.org/wiki/JPEG_2000)). Caveat: extensions (Parts 2+) may require licenses, and undisclosed third-party patents are always a theoretical risk.
- **Lifting scheme:** Published by Sweldens (1996) and earlier theoretical roots. Specific *implementation* patents on lifting variants do exist (Texas Instruments, IBM, others), but all 20-year terms from the mid-1990s have expired or are very close to expiring. The technique itself is a textbook method.
- **Our exposure:** Low for the math; we use 5/3 lifting. Common, old, taught in every wavelet textbook.

### 2.2 CineForm / VC-5 / GoPro

- **Repository:** [gopro/cineform-sdk](https://github.com/gopro/cineform-sdk) and [gopro/gpr](https://github.com/gopro/gpr), both Apache-2.0 + MIT dual license.
- **Standardization:** SMPTE ST 2073 ("VC-5 Video Essence") since 2015 ([SMPTE landing page](https://www.smpte.org/standards/st2073-landing-page), [4kshooters](https://www.4kshooters.net/2015/06/22/gopros-cineform-is-now-smpte-standardized-and-officially-an-open-codec-standard/)).
- **GoPro-held patents on the codec:** GoPro has *patent statements* on file with SMPTE for ST 2073 ("Patent_Statement_GoPro_VC-5" — referenced from the [SMPTE patent statements page](https://www.smpte.org/patent-statements)). These statements have not been published as part of any patent pool; the actual terms have to be requested from SMPTE.
- **What CineForm's lead engineer (David Newman) said publicly** in 2017 ([CineForm blog comments](http://cineform.blogspot.com/2017/10/cineform-goes-open-source.html)):
  - Apache 2.0 grants RAW patent rights *for users of the SDK software*.
  - For hardware implementations doing RAW, separate VC-5 licensing applies; quoted figure was "$20 per camera in the professional market."
  - 4:2:2 and 4:4:4 paths are "completely patent free" per Newman.
- **Our exposure:** We're using the SDK source directly. Apache 2.0's patent grant covers what *GoPro* can grant. The grant terminates if the licensee sues anyone over the Work (the patent retaliation clause; [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)). That covers GoPro's own VC-5 patents and is the cleanest path to legitimacy on the VC-5 core. Third-party patents are not covered.

### 2.3 RED / Nikon compressed-raw patents (the big one)

RED maintains a public patent list ([red.com/legal/patent](https://www.red.com/legal/patent)). The patents repeatedly asserted in litigation include:

| Patent | Title | Priority | Expected expiry | Key claim |
|---|---|---|---|---|
| US 7,830,967 | Video camera | 2007-04-11 | 2028-04-11 | Compressed raw Bayer at ≥2K and ≥23 fps, visually lossless |
| US 8,174,560 | Video camera | 2007-04-11 | 2028-04-11 | Mosaiced data compressed visually-losslessly |
| US 8,358,357 | Video camera | 2007-04-11 | 2028-04-11 | Continuation |
| US 8,872,933 | Video camera | 2007-04-11 | 2028-04-11 | Continuation |
| US 9,230,299 | (continuation) | 2007-04-11 | 2028-04-11 | |
| US 9,245,314 | (continuation) | 2007-04-11 | 2028-04-11 | The "Apple" case — modifying R/B based on G then compressing |
| US 9,436,976 | Video camera | 2007-04-11 | 2028-04-11 | |
| US 9,479,749 | Video camera | 2007-04-11 | 2028-04-11 | |
| US 9,521,384 | Green Average Subtraction in Image Data | 2013-02-14 | 2034-02-13 | Explicit GAS claim |
| US 9,716,866 | Green Image Data Processing | 2013-02-14 | 2034-02-13 | |
| US 9,787,878 | (continuation) | | ~2028 | |
| US 10,582,168 | Green Image Data Processing | 2013-02-14 | 2034-02-13 | Most recent in the GAS family |

**Critical claim shape:**
1. The **'967 family** (priority 2007-04-11, all expire **April 2028**) covers the *concept* of taking raw Bayer data at 2K+/23+ fps and compressing it visually-losslessly on camera, with optional pre-processing where R and B are modified based on G.
2. The **'384 / '866 / '168 family** (priority 2013-02-14, all expire **February 2034**) covers GAS specifically: subtracting an averaged green channel from R and B before compression.

**Litigation history:**
- RED v. Sony (2013, settled).
- RED v. Kinefinity (3 patents, led to Kinefinity dropping CinemaDNG).
- Apple v. RED IPR (Apple tried to invalidate; **Apple lost** — RED's compressed-raw patent was upheld; Apple now pays royalties on ProRes RAW) ([DPReview](https://www.dpreview.com/news/3429948804/apple-loses-patent-lawsuit-will-have-to-pay-red-royalties-for-prores-raw-format)).
- RED v. Nikon (7 patents, filed 2022, dismissed April 2023; resolved by Nikon's full acquisition of RED in March 2024).

**Prior art question (CineForm):**
CineForm RAW publicly existed in 2005 (used in the Silicon Imaging SI-2K). It does Bayer-pattern wavelet compression with green-channel subtraction. The [Silicon Imaging CineForm RAW Technology Overview PDF](https://www.siliconimaging.com/DigitalCinema/Files/CineForm_RAW_TechOverview.pdf) is dated August 2007 (metadata) and there are older public references. Jinni.Tech's argument and Nikon's counter-claims rest on this prior-art theory ([CineD](https://www.cined.com/redcode-raw-codec-dissected-by-jinni-tech-tough-accusations-against-red-in-new-video/), [DPReview](https://www.dpreview.com/news/9301564383/nikon-denies-red-s-lawsuit-concerning-compressed-raw-patents)).

Despite the prior-art arguments, Apple's IPR challenge failed and the patents remain enforceable. The PTAB found RED's claims novel enough to survive even with CineForm cited as prior art. This is the most important factual point for the safe-path analysis: **the patents are still enforceable** even though CineForm did the same thing first, because the USPTO and courts have not invalidated them.

**Our exposure:**
- The GPR code in `source/lib/vc5_encoder/raw.c` performs:
  - `GS = (G1 + G2) >> 1` (green average)
  - `RG = R1 - GS` (R minus green)
  - `BG = B1 - GS` (B minus green)
  - `GD = G1 - G2` (green difference)
  - Plus a `ApplyEncoderCurve` log curve (CineForm "Protune") that is functionally similar to RED's "pre-emphasis."
- These operations match the literal language of US 9,521,384 claims, and the broader '967-family claims about R/B modification based on G.
- However: this code came from GoPro CineForm, which predates RED's priority dates. GoPro made the strategic decision to ship MISSION 1 with this exact code path.
- Reading on a patent ≠ infringing it. Defenses include prior art (CineForm), implicit/exhaustion via Apache patent grant, license (if GoPro has one from RED/Nikon), and challenge to validity. A clearance attorney would want to read GoPro's licensing posture before assuming any of these.

### 2.4 SMPTE patent policy

- SMPTE's IP policy is **not royalty-free by default.** It is the standard SDO model: members declare essential patents and commit to either royalty-free or RAND (reasonable and non-discriminatory) terms ([SMPTE IP Policy](https://www.smpte.org/hubfs/Images/2020%20Site%20Files/Sections/SMPTE_IP_Policy_2013-08.pdf) — linked from the patent statements page).
- **There is a "Patent_Statement_GoPro_VC-5" on file** but the text is not on the public web; SMPTE provides such statements on request. Until that statement is read, it should not be assumed to be a royalty-free grant.
- Anecdotal pricing (Newman, 2017): ~$20/camera for hardware RAW VC-5 licenses in the professional market. This is a 9-year-old data point.

### 2.5 Range coding / rANS / ANS

- **ANS (Asymmetric Numeral Systems):** Invented by Jarek Duda (Jagiellonian University), published 2007–2014 ([arXiv 1311.2540](https://arxiv.org/abs/1311.2540)).
- **Duda's stance:** Intentionally placed in the public domain. Successfully challenged Google's 2015 ANS patent application ("Mixed boolean-token ans coefficient coding"), and Google abandoned it in 2018 ([ESP wiki](https://wiki.endsoftwarepatents.org/wiki/Asymmetric_numeral_systems)).
- **Microsoft 2022:** US patent granted on "Features of range asymmetric number system encoding and decoding" despite prior-art objections ([The Register](https://www.theregister.com/2022/02/17/microsoft_ans_patent/)). The scope of this patent over generic rANS is contested but not invalidated.
- **Range coding (classical):** Pasco/Rissanen 1976 prior art; IBM's arithmetic-coding patents from the 1980s have all expired. Range coding is widely treated as patent-free today ([Wikipedia](https://en.wikipedia.org/wiki/Range_coding)).
- **Our exposure:** Low if we use generic range coding or rANS in straightforward forms; the Microsoft patent narrows down to specific tableau / range layout tricks that we would want a clearance pass on if we copy from rygorous's `ryg_rans` or similar references. The VC-5 standard's own entropy coding is a custom VLC (not rANS), so the cleanest path is to use the VC-5 entropy stage as-shipped.

### 2.6 Adaptive bitrate / rate control

- **Patent activity:** Heavy in the H.264/HEVC space (Intel, Qualcomm, Samsung, Apple, Google all have rate-control families). Examples surfaced: US 7,986,731, US 8,175,147, US 2015/0288965, EP 2,951,994 ([Google Patents](https://patents.google.com/?q=%22adaptive+bitrate%22+%22quantization%22)).
- **Note:** These patents generally cover specific innovations (e.g. complexity-aware frame-hierarchy quantization, scene-change detection coupled with QP adjustment, bit-allocation algorithms tied to motion estimation).
- **Older art that's safe:**
  - MPEG TM5 rate control (1993, openly published) — bit allocation, virtual buffer, adaptive quantization. ~20-year-old; expired if patented.
  - Lagrangian rate-distortion optimization (Sullivan & Wiegand 1998).
  - PID-style buffer-fullness feedback (pre-1995, broadcast video).
  - JPEG 2000-style post-encode bit-truncation (covered by the JPEG 2000 royalty-free grant).
- **Our approach:** "Adjust the quantization vector based on a quality target and recent encoded sizes, with hysteresis." This is fundamentally MPEG TM5-style closed-loop rate control on per-band quantizers. The technique is decades old; the specific algorithm we use should be checked against currently-active patents but is unlikely to read on anything narrow.
- **Risk:** Low-to-moderate. The biggest risk would be if we copied an algorithm from x264/x265/etc. that itself was derived from a specific patent (e.g. Apple's ABR for HLS).

### 2.7 Other things in the wavelet space

- **Dirac/Schroedinger (BBC):** Royalty-free wavelet video codec, deliberately designed to avoid third-party patents. BBC let its own Dirac patent applications lapse ([Wikipedia](https://en.wikipedia.org/wiki/Dirac_(video_compression_format))). Useful as a reference point showing wavelets can be implemented patent-free given care.
- **JPEG XS (ISO/IEC 21122):** Low-latency wavelet codec, but **not royalty-free**. Licensed via the Vectis-administered JPEG XS Patent Pool on RAND terms ([jpegxspool.com](https://www.jpegxspool.com), [Vectis](https://www.vectis.com/media/vectis-announces-broader-jpeg-xs-patent-pool-license-at-no-additional-cost)). Patent holders include Fraunhofer IIS and intoPIX. We are not using JPEG XS, but it is worth noting that "wavelet codec from a standards body" is not automatically royalty-free.
- **JPEG XL:** Royalty-free, uses rANS for entropy coding. Patent grants from Google and Cloudinary ([libjxl PATENTS](https://github.com/libjxl/libjxl/blob/main/PATENTS)). Good reference for what an explicit royalty-free grant looks like.

---

## 3. The "Safe Path" for Our Codec to Ship

### 3.1 Does using VC-5 inherit GoPro's patent grant?

**Partially yes, with two scopes:**
1. **Apache 2.0 grant from the gopro/gpr and gopro/cineform-sdk repos.** This is a perpetual, worldwide, royalty-free, irrevocable patent license from GoPro covering claims *necessarily infringed* by their *Contributions* alone or combined with the Work. Terminates if we sue someone over the Work. ([Apache 2.0 §3](https://www.apache.org/licenses/LICENSE-2.0))
   - This covers GoPro's own VC-5 / CineForm / GAS-related patents — what GoPro can grant.
   - It does **not** grant patent rights from RED/Nikon, Microsoft (ANS), or any other third party.
2. **GoPro's SMPTE ST 2073 patent statement.** Filed but not public-spec; would need to be obtained from SMPTE and read by counsel.

### 3.2 Does SMPTE ST 2073 come with a patent pool / FRAND commitment?

No public patent pool exists for VC-5. SMPTE collects patent statements per its IP policy; the GoPro statement is on file. Until the statement text is read, we should not assume the terms are royalty-free or that they cover RAW (Newman's 2017 comments suggest hardware RAW is *not* free).

### 3.3 Are commodity adaptive-bitrate techniques old enough to be safe?

**Generally yes for the core ideas:**
- Closed-loop quantizer modulation against a target bitrate or quality metric — published 1993 (MPEG TM5).
- Per-band (subband) weighted quantization — published in early wavelet image-coding literature (1989-1995).
- Buffer-fullness feedback — broadcast video literature pre-1990.

**Specific algorithms to avoid copying line-for-line:**
- x264/x265 ABR implementations (those may track specific patent claims from the H.264/HEVC pools).
- Apple HLS-style ABR (covered by specific Apple patents).
- Anything labeled "perceptual rate control" or "frame-hierarchy QP" without checking patents.

Our `gpr_video_encoder` rate controller (per `project_fused_encoder.md` notes) modulates per-band quantizers against a target frame size with a PID-ish hysteresis. That is a generic technique; the specific tuning is unlikely to be a patentable narrow claim, but a clearance check should run against active rate-control patents owned by Apple, Qualcomm, Intel, and Samsung.

### 3.4 Specific patents a clearance attorney would want to look at

Priority list, roughly in order of probable exposure:

1. **RED/Nikon `'967` family** — every claim about on-camera Bayer compression at 2K+/23+fps visually lossless. Expires April 2028. This is the dominant near-term risk.
2. **RED/Nikon `'384 / '866 / '168` GAS family** — every claim about pre-compression green-channel subtraction. Expires Feb 2034. Our code does this literally.
3. **GoPro's own VC-5 patent statement at SMPTE** — to confirm whether the Apache grant + the statement combine to cover camera-RAW usage in our shipping product.
4. **Microsoft ANS patent (US 11,234,030 family)** — only relevant if we replace VC-5's VLC entropy stage with rANS. If we stick with the VC-5-native VLC, this is moot.
5. **Adaptive rate-control patents** owned by Apple/Qualcomm/Intel/Samsung — narrow scope, but worth a quick FTO read.
6. **JPEG 2000 Part 2+ patents** — only relevant if our extensions read on Part 2 (we believe they do not; our wavelet is single-level integer 5/3 and our entropy is VC-5 native).
7. **Texas Instruments / Sharp / Mitsubishi wavelet IP** from late-1990s JPEG 2000 standardization — most likely expired; verify expirations only if litigation surfaces.

### 3.5 What our codec is NOT exposed to (good news)

- **No DCT** → no MPEG/H.26x pool exposure.
- **No motion compensation** → no HEVC/AV1 pool exposure.
- **No intra/inter prediction** → no MPEG prediction-tree patent exposure.
- **Single-level wavelet, no zerotrees / EBCOT** → no SPIHT or JPEG 2000 Part-2 reading.
- **No entropy coding patents in active use** if we keep VC-5's native VLC.

The patent surface area of this codec is unusually narrow for a video codec. The exposure is almost entirely concentrated in the "compressed raw Bayer + green-channel pre-processing" cluster, which is exactly the RED/Nikon portfolio.

---

## 4. Strategic Recommendations

These are framings for the team and counsel to discuss; not legal advice.

### 4.1 Lowest-risk shipping configuration
- **Stay bit-stream conformant to SMPTE ST 2073-1..-3.** That preserves the "we are implementing a published standard" defense.
- **Use the unmodified VC-5 entropy stage** (custom VLC) so we don't touch ANS patents.
- **Keep our extensions in clearly separable modules** (rate controller, denoise, pipeline) so they can be turned off without breaking decode. A pure-VC-5 fallback mode is a useful kill-switch if a specific extension ever draws fire.
- **Document what we did *not* do** (no motion comp, no prediction, no DCT, no zerotree). Useful both for negotiations and for defensive publications.

### 4.2 Should extensions be optional / disable-able?
**Yes.** Specifically:
- Adaptive bitrate: ship with a "constant QP" mode so the rate controller can be disabled at runtime if a specific ABR patent ever turns up.
- Wavelet-domain denoise: ship with an "off" path so we can fall back to raw VC-5 output if any image-processing patent claim arises against the denoise.
- Fused unpack pipeline: this is a software-engineering optimization, not a codec feature. It's unlikely to read on any patent, but keeping it factored cleanly makes it removable.
- Per-band quantization tweaks: parameterize so we can revert to default VC-5 tables if needed.

### 4.3 Patent-holders to consider reaching out to preemptively

This is a *business* decision, not a legal one, but the candidates are:

- **Nikon (was RED).** Holds the compressed-raw + GAS patent family. The base-rate cost of *not* talking to them is that they could litigate. The base-rate cost of *talking* to them is that they may demand a license fee even where one might not otherwise be required. GoPro's own posture (it ships MISSION 1) implies a position on this question that we should align with.
- **SMPTE.** Request the GoPro VC-5 patent statement under their IP policy. This is a paperwork step, not a license negotiation.
- **No other obvious preemptive targets** unless we move into JPEG XS or DCT-based codecs.

### 4.4 Alternative codec families as a fallback

If wavelet/RAW becomes legally untenable, alternatives in rough preference order:

1. **DNG-only, no compression beyond DEFLATE/LJPEG.** Codec patents don't bite; storage cost is the tradeoff. CinemaDNG-style.
2. **JPEG 2000 Part 1 only, single-level 5/3 lossless.** Royalty-free per JPEG committee; covers most of what VC-5 does for visually-lossless workflows.
3. **Dirac/Schroedinger** as a reference royalty-free wavelet codec, though abandoned in practice (no active community).
4. **JPEG XL** for stills + per-frame container; uses royalty-free rANS, mature decoder ecosystem. Not designed for high-bit-rate camera output but technically capable.
5. **Codex HDE-style** — lossless compression applied at ingest, not in-camera. Avoids the entire "compressed in camera" claim wedge.

None of these are drop-in replacements for our current pipeline. They're listed as eject-button options.

---

## Open questions for counsel

1. What is the text of the GoPro patent statement at SMPTE for ST 2073? Does it cover RAW compression, or only 4:2:2/4:4:4 paths?
2. Has GoPro acquired a license from RED/Nikon, or does GoPro rely on a non-infringement / invalidity / exhaustion theory for shipping MISSION 1?
3. Does the Apache 2.0 grant from GoPro's gopro/gpr repo cover the GAS pre-processing in `source/lib/vc5_encoder/raw.c` such that downstream users (us, third parties) inherit any GoPro-held patent rights that apply?
4. Is the prior-art argument (CineForm 2005 ≫ RED priority Dec 2007) defensible enough that a clearance attorney can sign off, given that Apple already lost an IPR challenge?
5. For each shipping extension (rate control, denoise, pipeline), what is the freedom-to-operate read?

---

## Source list

- [GoPro CineForm Insider blog — Open Source announcement (2017)](http://cineform.blogspot.com/2017/10/cineform-goes-open-source.html)
- [GitHub: gopro/cineform-sdk](https://github.com/gopro/cineform-sdk)
- [GitHub: gopro/gpr](https://github.com/gopro/gpr)
- [GPR documentation site](https://gopro.github.io/gpr/)
- [VC-5 Codec site (vc5codec.org)](https://vc5codec.org/)
- [SMPTE ST 2073 landing page](https://www.smpte.org/standards/st2073-landing-page)
- [SMPTE Patent Statements page](https://www.smpte.org/patent-statements)
- [SMPTE IP Policy PDF](https://www.smpte.org/hubfs/Images/2020%20Site%20Files/Sections/SMPTE_IP_Policy_2013-08.pdf)
- [Apache License 2.0 text](https://www.apache.org/licenses/LICENSE-2.0)
- [RED Digital Cinema legal/patent page](https://www.red.com/legal/patent)
- [Patent US 7,830,967 — Video camera](https://patents.google.com/patent/US7830967)
- [Patent US 8,174,560 — Video camera](https://patents.google.com/patent/US8174560B2/en)
- [Patent US 8,358,357 — Video camera](https://patents.google.com/patent/US8358357B2/en)
- [Patent US 8,872,933 — Video camera](https://patents.google.com/patent/US8872933B2/en)
- [Patent US 9,245,314 — Video camera (Apple-IPR patent)](https://patents.google.com/patent/US9245314B2/en)
- [Patent US 9,521,384 — Green Average Subtraction in Image Data](https://patents.google.com/patent/US9521384)
- [Patent US 10,582,168 — Green Image Data Processing](https://patents.google.com/patent/US10582168)
- [Nikon press release — RED acquisition (March 2024)](https://www.nikon.com/company/news/2024/0307_01.html)
- [Newsshooter — Nikon acquires RED (March 2024)](https://www.newsshooter.com/2024/03/06/nikon-acquires-red/)
- [DPReview — Apple loses patent challenge to RED](https://www.dpreview.com/news/3429948804/apple-loses-patent-lawsuit-will-have-to-pay-red-royalties-for-prores-raw-format)
- [DPReview — Nikon denies RED's compressed raw lawsuit](https://www.dpreview.com/news/9301564383/nikon-denies-red-s-lawsuit-concerning-compressed-raw-patents)
- [Y.M. Cinema — The Patent War for RAW (Aug 2022)](https://ymcinema.com/2022/08/09/the-patent-war-for-raw/)
- [Y.M. Cinema — RED v. Nikon dismissed (Apr 2023)](https://ymcinema.com/2023/04/27/red-vs-nikon-case-dismissed/)
- [CineD — REDCODE dissected by Jinni.Tech](https://www.cined.com/redcode-raw-codec-dissected-by-jinni-tech-tough-accusations-against-red-in-new-video/)
- [Silicon Imaging CineForm RAW Technology Overview (2007)](https://www.siliconimaging.com/DigitalCinema/Files/CineForm_RAW_TechOverview.pdf)
- [Wikipedia — CineForm](https://en.wikipedia.org/wiki/CineForm)
- [Wikipedia — Cohen-Daubechies-Feauveau wavelet](https://en.wikipedia.org/wiki/Cohen%E2%80%93Daubechies%E2%80%93Feauveau_wavelet)
- [Wikipedia — JPEG 2000](https://en.wikipedia.org/wiki/JPEG_2000)
- [Wikipedia — Asymmetric numeral systems](https://en.wikipedia.org/wiki/Asymmetric_numeral_systems)
- [Wikipedia — Dirac video compression](https://en.wikipedia.org/wiki/Dirac_(video_compression_format))
- [Wikipedia — Range coding](https://en.wikipedia.org/wiki/Range_coding)
- [Wikipedia — CinemaDNG](https://en.wikipedia.org/wiki/CinemaDNG)
- [The Register — Microsoft ANS patent (Feb 2022)](https://www.theregister.com/2022/02/17/microsoft_ans_patent/)
- [ESP Wiki — Asymmetric numeral systems patent status](https://wiki.endsoftwarepatents.org/wiki/Asymmetric_numeral_systems)
- [libjxl PATENTS file](https://github.com/libjxl/libjxl/blob/main/PATENTS)
- [JPEG XS Patent Pool (Vectis)](https://www.jpegxspool.com)
- [Codex HDE documentation](https://help.codex.online/content/high-density-encoding)
- [Newsshooter — DJI removes ProRes RAW from Ronin 4D (2022)](https://www.newsshooter.com/2022/02/15/dji-removes-prores-raw-from-ronin-4d-and-lowers-price/)
- [CineD — Kinefinity removes CinemaDNG and other raw codecs](https://www.cined.com/kinefinity-removes-cinemadng-and-other-raw-codecs-from-its-cameras/)
- [Newsshooter — Sony X-OCN explained](https://www.newsshooter.com/2023/05/09/sony-x-ocn-explained/)
- [PremiumBeat — Everything about Blackmagic RAW](https://www.premiumbeat.com/blog/what-is-blackmagic-raw/)
- [Phase One — IIQ overview](https://www.phaseone.com/imaging-quality-performance/intelligent-image-quality-iiq/)
- [GoPro press release — MISSION 1 announcement](https://gopro.com/en/us/news/gopro-announces-three-cameras-mission-1-2026)
- [Y.M. Cinema — GoPro MISSION 1 model breakdown](https://ymcinema.com/2026/04/19/gopro-mission-1-which-model-to-buy/)
- [Library of Congress — ProRes RAW format description](https://www.loc.gov/preservation/digital/formats/fdd/fdd000528.shtml)
- [CineD — DNG is now an international ISO standard](https://www.cined.com/dng-is-now-an-international-iso-standard-what-it-means-for-filmmakers-and-raw-workflows/)
