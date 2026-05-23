# Research: VSR and ANE-friendly architectures (May 2026)

Captured during the VSR exploration to avoid re-doing this lit search.

## What we learned

### 1. NTIRE 2025 RAW 2× Super-Resolution Challenge

The most relevant benchmark for our exact problem (raw Bayer 2× upscale with codec-induced degradation).

**Efficient track (<200K params):**
| Model | Team | PSNR | SSIM | Params |
|---|---|---|---|---|
| SMFFRaw-S | XJTU | **42.12 dB** | 0.9433 | 180K |
| RawRTSR | Samsung | 41.74 dB | 0.9417 | 190K |
| NAFBN | NJU | 40.67 dB | 0.9347 | 190K |

**General track:**
| Model | Team | PSNR | SSIM | Params |
|---|---|---|---|---|
| (winner) | USTC-VIDAR | **42.70 dB** | 0.9479 | 1.94M |
| SMFFRaw-S | XJTU | 42.60 dB | 0.9467 | 1.99M |
| RawRTSR-L | Samsung | 42.58 dB | 0.9475 | **0.26M** |

**Key takeaway**: 260K params *is enough* to do raw 2× SR at near-state-of-the-art quality (Samsung). Our F backbone at 263K is in the right ballpark; what's wrong is the architecture choice, not the parameter count.

**Top approaches** (efficient tier):
- Hybrid attention CNN blocks (SMFFRaw)
- Knowledge distillation from a heavy teacher (RawRTSR — distilled from X-Restormer)
- Streamlined transformers with InceptionNeXt feature extraction (USTC)

Code at https://github.com/mv-lab/AISP. Individual team weights mostly not released publicly yet.

### 2. PiperSR — proven real-time SR on Apple Neural Engine

`https://github.com/ModelPiper/PiperSR` — first SR model purpose-built for ANE.

Architecture recipe:
- 6-block residual CNN
- 64 channels
- **BatchNorm + SiLU**
- PixelShuffle upsampling
- 453K params, 928 KB FP16 mlpackage
- Single-image SR (not video)

Performance:
- **48 FPS at 360p → 720p on M2 Max ANE**
- 20.8 ms / frame on ANE alone

License: AGPL-3.0 code, weights bundled. Image-domain only.

### 3. Real-RawVSR (ECCV 2022) — closest to what we wanted

`https://github.com/zmzhang1998/Real-RawVSR` — raw bayer video super-resolution.

- Two-branch network (packed RGGB + raw Bayer)
- Uses **deformable convolutions** for alignment
- ⚠ **Will not run on MPS without major work** — DCN is not MPS-native; even after CPU fallback, `grid_sample_backward` itself is broken on MPS (we hit this in our Phase 2 attempt)
- Pretrained weights via Google Drive in their README

### 4. Real-ESRGAN → Core ML

- 78× speedup vs CPU PyTorch on Apple Silicon
- Image super-resolution, no temporal coherence
- Useful pattern for proving the Core ML pipeline works at speed

### 5. FlashVSR (CVPR 2026)

- Diffusion-based streaming VSR, sparse attention, tiny conditional decoder
- Real-time on workstation GPUs
- Too heavy for M3 Max real-time

## Why our hand-rolled VSR went sideways

**Phase 1** (3-frame channel concat, no alignment) plateaued at +1.49 dB val tile gain on motion-rich val. The literature confirms this — without alignment, multi-frame aggregation is a small win at best.

**Phase 2** (explicit per-pixel flow + warp) hit two MPS bugs in sequence:
1. `padding_mode="border"` unsupported on MPS — switched to `"zeros"`, worked
2. `grid_sampler_2d_backward` not implemented for MPS — required `PYTORCH_ENABLE_MPS_FALLBACK=1` which moves the backward pass to CPU. Training works but ~3× slower per epoch.

Even with both fixed, the literature suggests our naive flow head is far weaker than the deformable-conv approaches every serious VSR paper uses. We'd be chasing a +2 dB improvement at most.

## Why our CoreML conversion ran slowly

Our F architecture uses:
- `LayerNorm2d` (per-pixel mean+var) — not ANE-native
- `SimpleGate` (chunk + element-wise multiply) — not ANE-native
- Depthwise conv 3×3 — ANE-supported but lower throughput than regular conv

Result: CoreML conversion ran at 370 ms / frame, vs 35 ms on our Metal hybrid backend. PiperSR with a purpose-built ANE arch hits 20 ms.

## The implication

If we want to keep pushing throughput on M3 Max, the highest-leverage move is **redesigning F to be ANE-friendly**, not adding multi-frame complexity that the platform can't accelerate.

Sources:
- [Real-RawVSR (zmzhang1998/Real-RawVSR)](https://github.com/zmzhang1998/Real-RawVSR)
- [Real-RawVSR paper (ECCV 2022)](https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136660597.pdf)
- [NTIRE 2025 RAW Restoration Challenge](https://arxiv.org/html/2506.02197v1)
- [mv-lab/AISP repo](https://github.com/mv-lab/AISP)
- [PiperSR — ANE-native SR](https://github.com/ModelPiper/PiperSR)
- [Apple Core ML — WWDC 2024](https://developer.apple.com/videos/play/wwdc2024/10161/)
- [Apple PyTorch MPS](https://developer.apple.com/metal/pytorch/)
- [Optimized AI Upscaling on Apple Silicon (Regev, Medium)](https://medium.com/@ronregev/optimized-ai-image-video-upscaling-on-macs-with-apple-silicon-m1-m2-m3-m4-a248e128cdc6)
