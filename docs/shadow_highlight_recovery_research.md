# Shadow & Highlight Recovery for GPR — Prior Art Survey

## 1. Problem framing

GPR's encoder pushes 14-bit linear raw through a log-curve (bijective on its own)
and then a scalar quantizer + rANS entropy coder. Although the log curve preserves
information in principle, the *quantizer* downstream of it allocates code-points
non-uniformly across luminance: shadows and bright highlights end up with materially
fewer surviving precision bits than midtones. On Z8 ISO64 the codec roundtrip Y-PSNR
collapses from 35.3 dB in deep shadow to 8.5 dB in highlights (Y>230). Our existing
F_ane CNN (uniform L1) recovers +5.6 dB in bright/hi but slightly *regresses*
shadows (-0.4 dB) because uniform L1 on linear pixels is dominated by midtones.
We need a loss/training recipe that recovers detail in *both* tails without
sacrificing the midtone gains, and we want to do it with the architecture we
already have rather than redesigning the network. This survey looks for what
the literature has already found about exactly this class of problem.

## 2. What works in the literature

### 2.1 Perceptual pre-encoding of pixels beats reweighting losses

The single strongest result we found is from **Hanji et al., "Training Neural
Networks on RAW and HDR Images for Restoration Tasks"** (SIGGRAPH Asia 2024,
arxiv 2312.03640). They benchmarked 6 architectures × multiple loss configurations
on RAW/HDR restoration. Their headline finding: training with **regular L1 on
PQ-, PU21-, or μ-law-encoded pixels** *outperformed* training with custom loss
functions on linear pixels by **2-9 dB PSNR** across tasks. Linear + perceptual
loss was consistently worse than perceptual encoding + L1.

Why this matters for us: the GPR codec already applies a log curve. The decoded
output is *almost* in the right domain, but it's then converted back to linear
before the network sees it. **If we train the CNN on the *log-domain* tensor
directly (or a μ-law / PU21 re-encoding of the linear output), uniform L1 on
that representation is already an implicit shadow+highlight-weighted loss**,
because equal L1 errors in PU/PQ-space correspond to roughly equal perceptual
errors regardless of luminance. (https://arxiv.org/html/2312.03640v3)

The μ-law form they use is τ(H)=log(1+μH)/log(1+μ) with μ≈5000 — cheap,
differentiable, no LUTs. PU21 is more accurate but uses a piecewise rational
function (https://github.com/gfxdisp/pu21).

### 2.2 Focal-style adaptive weighting (Focal Frequency Loss → Focal L1)

**Jiang et al., "Focal Frequency Loss for Image Reconstruction and Synthesis"**
(ICCV 2021, arxiv 2012.12821). Down-weights "easy" frequencies and up-weights
hard ones via a weight matrix `w(u,v) = |F_r(u,v) - F_f(u,v)|^α`, normalized
to [0,1] with the **gradient through w stopped** (treated as a static weight in
each step). α=1 is the default; larger α concentrates more aggressively.
Repos: https://github.com/EndlessSora/focal-frequency-loss .

The spatial-domain analog of this is **dynamic focal L1**: weight each pixel by
`|y_pred - y_target|^α` with stop-gradient. This is exactly what the OHEM /
focal-regression literature has shown to be more stable than a fixed manual
weight table — the weighting adapts to current residual rather than being
hand-tuned at 12× for highlights. (See **Shrivastava et al. 2016 OHEM**,
arxiv 1604.03540, and **dynamic focal regression** discussed in
https://www.emergentmind.com/topics/online-hard-example-mining-ohem .)

Applicable to GPR: a stop-grad self-adaptive weight is much less likely to
"thrash" than fixed weight=12 on a luminance bucket. The bucket can shift mid-
training, but `|residual|^α` cannot — it always points at the current worst pixels.

### 2.3 Hybrid loss: log-domain + tone-mapped + spatial mask

**Eilertsen et al., HDRCNN** (SIGGRAPH Asia 2017, arxiv 1710.07480 — the
foundational single-exposure HDR-from-LDR paper). Their loss is computed in
**log-luminance space** with a **saturation mask** that focuses the network
only on pixels whose linear value was clipped or near-clipped. The masked
log-space L2 is what made the network actually learn highlight content
instead of being dominated by midtone gradients.

**Santos et al. 2020** (arxiv 2005.07335, "Single Image HDR Reconstruction
Using a CNN with Masked Features and Perceptual Loss") extends this with a
*soft* mask that grows smoothly from 0 to 1 as the input value approaches
saturation, plus a VGG perceptual term computed on tone-mapped output.

Applicable to GPR: we have **per-pixel Y-bucket information** at training
time. A soft mask of the form `mask(y) = w_shadow * (y<25) + w_hi * (y>192)
+ 1.0` is the equivalent of HDRCNN's saturation mask but generalized to both
tails. The literature consistently uses **masked log-space loss**, not
mask-on-linear, which lines up with the PU/PQ finding above.

### 2.4 SID's pragmatic recipe: amplify-then-L1

**Chen et al., "Learning to See in the Dark"** (CVPR 2018, arxiv 1805.01934).
The recipe that became canonical for raw-domain restoration: subtract black
level, multiply by amplification ratio, **L1 loss in the amplified domain**.
The amplification is the key trick — it makes shadow pixels carry midtone-
magnitude L1 weight automatically. Github: https://github.com/cchen156/Learning-to-See-in-the-Dark .

Applicable to GPR: directly. Our shadow problem is identical structurally —
small absolute values in a domain where uniform L1 is dominated by larger
midtones. The equivalent for highlights is "amplify the residual from the
clip-point" — i.e. compute the loss on `(highlight_max - y)`, not `y`.

### 2.5 Charbonnier / robust losses (low-grade but uncontroversial)

**Charbonnier loss** = √(x² + ε²) — smooth approximation of L1 that has
been adopted as the default in **Restormer** (arxiv 2111.09881),
**NAFNet** (arxiv 2204.04676), and most of the modern transformer/CNN
restoration models. It does not directly address shadow/highlight asymmetry,
but it's strictly better than pure L1 for stability — and any region-weighted
or mask-weighted loss is more stable in Charbonnier form. **MS-SSIM + L1**
hybrid (Zhao, Gallo, Frosio, Kautz 2017, arxiv 1511.08861) is the other
default — MS-SSIM preserves high-frequency contrast where L1 over-smooths,
which is relevant in highlights where contrast is what we lost.

## 3. What the literature warns about

### 3.1 Hallucination in fully-saturated regions

The **highlight-recovery survey** (https://yage.ai/share/highlight-recovery-vs-low-light-survey-en-20260325.html) is blunt: when all three raw channels are
clipped, the information is *gone*. CNN methods "hallucinate plausible textures"
but those don't correspond to scene content. **For GPR this is not our case** —
our highlights aren't physically clipped, they're quantizer-clipped — but the
warning still applies: if the *codec* destroyed the information completely, no
CNN can invent it back. The Y>230 bucket at 8.5 dB PSNR is in this danger zone.
We should measure how much information actually survives before declaring a
recovery target.

### 3.2 Switching loss mid-training is unstable

The curriculum-learning literature (e.g. **SuperLoss**, NeurIPS 2020;
https://proceedings.neurips.cc/paper/2020/file/2cfa8f9e50e0f510ede9d12338a5f564-Paper.pdf)
consistently recommends **gradual** schedule transitions, not hard switches.
The user's observation of "thrashing on warm-start regression" is the classic
symptom of swapping uniform L1 for weighted L1 in one step — the optimizer was
sitting in a midtone-favorable local minimum that is highly disfavored under
the new loss. Recommended fix in the literature is **loss interpolation over
N epochs**: `L(t) = (1-α(t))·L_uniform + α(t)·L_weighted`, α ramped linearly
or cosine-annealed.

### 3.3 Don't fix L1 with bigger weights — fix the *domain*

Hanji et al.'s explicit warning: linear + custom perceptual loss
underperforms perceptual encoding + plain L1. Translation: **if uniform L1
favors midtones, that means we're in the wrong representation, not that we
need bigger weights.** Reweighting linear-domain L1 by 12× is fighting the
symptom; training on log/μ-law-domain pixels removes the cause.

### 3.4 SSIM/MS-SSIM is insensitive to brightness shifts

Common pitfall noted in **Zhao et al. 2017**: SSIM-family losses don't penalize
uniform brightness/color shifts in a region, which lets a network silently
shift highlight levels while keeping SSIM high. Use SSIM as an *auxiliary*
term, never alone.

### 3.5 Highlight recovery is fundamentally harder than shadow recovery

Across the survey literature this is a near-universal finding. Shadow signal is
weak but present; the codec compressed it into 1-2 quantization levels but
spatial neighbors give context. Highlight signal is *suppressed* by the log
curve at exactly the place where the quantizer step is widest. You should
expect highlight Y-PSNR ceilings to be 5-10 dB below shadow Y-PSNR ceilings
even with optimal training. Don't set targets that match shadow recovery in
the highlight bucket — they may be unreachable.

## 4. Three concrete recommendations (ranked by ROI)

### Rec #1 (highest ROI): Train the CNN in μ-law / log-domain pixel space

- **Loss:** plain L1 (or Charbonnier) on `μ(y)` where `μ(y) = log(1+μ·y/y_max)/log(1+μ)`, μ=5000. Same loss applied to both prediction and target.
- **Training schedule:** Cold-start fresh weights. No curriculum needed — this is just a re-parametrization of the existing F_ane training.
- **Expected improvement:** Based on Hanji et al.'s benchmark, **2-9 dB** of effective PSNR (when measured in the perceptually-encoded space). In linear-PSNR terms this trades a small loss in midtones (the bucket that was being over-fit) for big gains in shadows and highlights symmetrically.
- **Risk:** Lowest of the three. This is a battle-tested technique with a SIGGRAPH 2024 benchmark behind it. The main risk is that our linear-domain PSNR metric will look slightly worse even though perceptual quality is up — we need to also report PSNR in μ-law or PU21 space to see the win.
- **Implementation cost:** ~10 lines in the training loss. No architecture change.

### Rec #2 (medium ROI): Dynamic focal L1 with stop-gradient weighting

- **Loss:** `L = mean(|r|^(1+α) / (|r|.detach()^α + ε))` where r is residual. Equivalent to per-pixel weight `|r|^α` with gradient stopped on the weight. Default α=1 (this is just `r²/(|r|+ε)` ≈ Huber-ish but auto-focusing).
- **Training schedule:** Warm-start from the existing F_ane checkpoint. Linearly ramp α from 0 (= plain L1) to 1 over 5 epochs to avoid the thrash the user observed. Then constant.
- **Expected improvement:** +1-3 dB in the bright/hi bucket and shadow bucket, without manual weight tables. The focal mechanism finds whatever the network is currently bad at, which may shift from highlight to shadow as training proceeds.
- **Risk:** Moderate. Focal-style losses can over-fit to outlier pixels (single dead pixels, demosaic artifacts) if α is too large. Stay at α=1; do not go above α=2.
- **Implementation cost:** ~5 lines in the loss. Stop-gradient must be correct (a common bug).

### Rec #3 (highest potential, highest variance): HDRCNN-style soft saturation mask + log-domain hybrid

- **Loss:** `L = L1(log(y_pred), log(y_target)) + λ_hi · mask_hi(y_target) · L1(y_pred, y_target) + λ_lo · mask_lo(y_target) · L1(y_pred, y_target)`. Soft masks: `mask_hi(y) = sigmoid((y - 192)/8)`, `mask_lo(y) = sigmoid((25 - y)/8)`. Start with λ_hi = λ_lo = 1.0 (the *log* term already does most of the shadow+hi reweighting; the masks add a small further nudge).
- **Training schedule:** This is the most aggressive of the three; *cold start*, not warm. Optionally add a final fine-tune phase with VGG perceptual loss on the tone-mapped output for high-frequency texture in highlights (Santos et al. 2020).
- **Expected improvement:** +3-5 dB in highlights if the data isn't quantizer-clipped past recovery. Matches or exceeds Rec #1 in worst-case regions but with more risk of midtone regression.
- **Risk:** Highest. Multiple weighted terms = multiple hyperparameters = more brittle. Recommend doing #1 first, only escalating to #3 if #1's highlight bucket is still underperforming.
- **Implementation cost:** Moderate. Several knobs to tune.

**My recommendation:** Start with Rec #1 (μ-law L1, fresh checkpoint). It is the lowest-risk and best-evidence-supported step, and it directly addresses the user's "shadow & highlight asymmetry" complaint at the representation level instead of patching it with weight tables. If Rec #1 plateaus, escalate to Rec #2 (dynamic focal) layered on top.

## Sources

- [Hanji et al., Training Neural Networks on RAW and HDR Images for Restoration Tasks (SIGGRAPH Asia 2024)](https://arxiv.org/abs/2312.03640)
- [Jiang et al., Focal Frequency Loss (ICCV 2021)](https://arxiv.org/abs/2012.12821) — [code](https://github.com/EndlessSora/focal-frequency-loss)
- [Eilertsen et al., HDR image reconstruction from a single exposure (SIGGRAPH Asia 2017)](https://arxiv.org/abs/1710.07480) — [code](https://github.com/gabrieleilertsen/hdrcnn)
- [Santos et al., Single Image HDR Reconstruction with Masked Features and Perceptual Loss (2020)](https://arxiv.org/abs/2005.07335)
- [Chen et al., Learning to See in the Dark (CVPR 2018)](https://arxiv.org/abs/1805.01934) — [code](https://github.com/cchen156/Learning-to-See-in-the-Dark)
- [Chen et al., NAFNet (ECCV 2022)](https://arxiv.org/abs/2204.04676) — [code](https://github.com/megvii-research/NAFNet)
- [Zamir et al., Restormer (CVPR 2022)](https://arxiv.org/abs/2111.09881) — [code](https://github.com/swz30/Restormer)
- [Zhao, Gallo, Frosio, Kautz, Loss Functions for Image Restoration with Neural Networks (TCI 2017)](https://arxiv.org/abs/1511.08861)
- [Mantiuk & Azimi, PU21 Perceptually Uniform Encoding (2021)](https://www.cl.cam.ac.uk/~rkm38/pdfs/mantiuk2021_PU21.pdf) — [code](https://github.com/gfxdisp/pu21)
- [Shrivastava, Gupta, Girshick, OHEM (CVPR 2016)](https://arxiv.org/abs/1604.03540)
- [Castells et al., SuperLoss: A Generic Loss for Robust Curriculum Learning (NeurIPS 2020)](https://proceedings.neurips.cc/paper/2020/file/2cfa8f9e50e0f510ede9d12338a5f564-Paper.pdf)
- [Highlight Recovery vs Low-Light Survey (2026)](https://yage.ai/share/highlight-recovery-vs-low-light-survey-en-20260325.html)
- [Conde et al., NTIRE 2025 RAW Image Restoration and Super-Resolution Challenge](https://arxiv.org/abs/2506.02197)
- [DnCNN: Zhang et al., Beyond a Gaussian Denoiser (TIP 2017)](https://arxiv.org/abs/1608.03981)
- [Wang et al., Uformer (CVPR 2022)](https://arxiv.org/abs/2106.03106)
