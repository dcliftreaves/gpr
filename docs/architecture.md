# Architecture

## Data paths

| Workflow | Processing |
|---|---|
| Stills | DNG/raw input -> legacy VC5 encoder -> DNG/GPR container -> VC5 decode -> editable Bayer |
| Raw-video capture | Unpacked Bayer -> FUSED encoder -> per-frame payloads -> `.gvid` writer |
| Camera-back preview | Same native 4K `.gvid` -> decode/downsample -> full-frame 1024 x 768 RGB -> display integration |
| Desktop reconstruction | Decode Bayer -> matched optional CNN -> editable raw packaging or demosaic/render -> ProRes |

The camera encodes raw frames and prepares preview. CNN restoration and
super-resolution run on the desktop, independently of the camera capture
budget. A container's declared playback fps is not encoder or CNN throughput.

## Interfaces

| Responsibility | Source |
|---|---|
| Public still conversion API | `source/lib/gpr_sdk/public/gpr.h` |
| Legacy encoder | `source/lib/vc5_encoder/vc5_encoder.h` |
| FUSED payload definition | `source/lib/vc5_encoder/fused_encode.h` |
| FUSED decoder | `source/lib/vc5_decoder/fused_decode.h` |
| Video queue and rate control | `source/lib/vc5_encoder/gpr_video.h` |
| Firmware-facing shim | `source/lib/vc5_encoder/gpr_labs_encoder.h` |
| Raw-video container | `source/lib/vc5_encoder/gpr_video_format.h` |
| Desktop review/export | `tools/gpr2prores/` |

The FUSED pipeline transforms Bayer into four channels, applies a log curve,
wavelet decomposition and quantization, then entropy-codes bands. Its wrapper
carries the parameters required for decode. Legacy VC5 has a different
bitstream and DNG integration. Consult [SPEC](SPEC.md) and
[Format Specification v2](format-spec-v2.md) before changing either format.

## Integration constraints

Use the public headers as the API authority rather than copying old example
structures. Firmware must supply declared input layout, bounded buffer
ownership, storage error handling, and capture metadata. See
[Labs Firmware API](LABS_FIRMWARE_API.md).

Models must match the codec, preprocessing, Bayer phase, and scale used by
their evidence. Packaging and rendering cannot repair incompatible model
selection. [Reconstruction](RECONSTRUCTION.md) records availability and
promotion requirements.

Historical architecture comparisons and tuning experiments are in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
