# Upstream review and attribution

Reviewed against `gopro/gpr` master `446c736a38fb14f51343605c0780d347dc602f89` and the open pull requests fetched on 2026-11-21. The integration preserves the original dual Apache-2.0/MIT licensing and upstream authorship notices.

| Upstream work | Disposition in this fork |
|---|---|
| [#68 — Improvements to GPR](https://github.com/gopro/gpr/pull/68), Adeel Abbas, head `1a65057da0c594243cba5c586bc072b5b481b00b` | Selected port of camera color/illuminant/Bradford rendering, tone curve, lens shading, black subtraction, 8/16-bit agreement, JPEG orientation and growable output, complete WarpRectilinear metadata, baseline tags and argument-parser path initialization. Thread-local render LUTs and input bounds were added during integration. The original codec APIs and RAW path remain intact. |
| [#59 — Image description size](https://github.com/gopro/gpr/pull/59), `757d81370dbbf44c66adad94bc4246734f7c09a2` | Increase the SDK image-description capacity from 32 to 64. This contributes to the SDK rebuild requirement. |
| [#53 — ARM64 byte order](https://github.com/gopro/gpr/pull/53), `783770ad57232cfba8a94d2f2c6460e650425d1b` | The fork already detects byte order through compiler macros on ARM64. Do not import the PR's unrelated reduction of the 65×65 gain-map buffer to 16000 bytes. Pi 5 SDK builds exercise the endian behavior. |
| [#51 — Windows build](https://github.com/gopro/gpr/pull/51), `2a12c93f81e9ff2b26355b9f805eec96b223f30e` | Port portable `strings.h`/`stricmp` handling and Expat fallthrough macros. Keep the larger gain-map buffer. Portable codec CI includes Windows; POSIX capture frontends do not claim native Windows support. |
| [#48 — Submodule compatibility](https://github.com/gopro/gpr/pull/48), `3147c9aad44d45091a03bac1140995a20372905a` | Use this project's source directory instead of the embedding application's root. Verify a downstream `add_subdirectory` build and relocated package clients. |
| [#74 — Help text](https://github.com/gopro/gpr/pull/74), `f576785c82a8de0c4babb4117a730c17d1df1365` | Apply the spelling corrections to this fork's extended command help. |
| [#34 — HERO10 sample](https://github.com/gopro/gpr/pull/34), `db9cacfd1f9234ffe2501870989d5872c50876f9` | Not imported in this pass. Existing six bundled camera samples and private 12/50/100 MP fixtures supplied the current coverage. Additional independently licensed camera/RAW+JPEG fixtures remain welcome. |
| [#73 — ARM encoding](https://github.com/gopro/gpr/pull/73) and [#75 — Decoding](https://github.com/gopro/gpr/pull/75) | Their stock-compatible work is already incorporated in the consolidated runtime lineage, followed by streaming, aligned memory and bounded capture work. Historical PRs remain open; this master integration does not close them. |

## Why #68 matters

[The HERO9 user report](https://github.com/gopro/gpr/pull/68#issuecomment-5922684588) describes corrected horizontal orientation and colors similar to camera JPGs. That motivated testing the actual implementation, not importing the claim as a universal guarantee.

We independently built #68's head and compared the fork's port on all six bundled samples: HERO5, HERO6, HERO7, HERO9 and the two Fusion lenses. Four reduced resolutions and 8/16-bit PPM output produced **48 pixel-identical comparisons on the M5**. The comparison checks implementation parity, not colorimetric accuracy against unavailable paired camera JPEGs. The small numerical receipt is included with the release evidence; the photos were already public repository samples.

Default DNG export continues to preserve the original GainMap samples. Apple's requirement for identical green maps is exposed through an explicit `--apple-compatible-dng` SDK export policy. This intentionally differs from applying the upstream normalization unconditionally: a compatibility rendition should not silently replace measured calibration. Synthetic tests use shuffled opcode order to verify CFA-based green selection and preserve non-green opcodes and headers.

The selected port includes full radial/tangential warp coefficients, optical center, plane count and flags, plus BaselineExposure/Noise/Sharpness, including their JSON representation. Existing two-coefficient SDK inputs remain a fallback. This is not a port of #68's entire expanded CLI, synthesized camera lens profiles, high-black-level normalization, crop policy or new Ultra quantizer. Those need their own API, image-quality and compatibility review. The stock codec retains its existing six quality presets.

The copied Adobe ACR3 tone-curve table retains its original BSD notice. That notice ships even in stripped codec packages without the DNG SDK.

The new display renderer leaves the low-level legacy RGB decoder's historical output available. This avoids silently changing existing preview contracts or compression bytes while providing the corrected SDK render path.
