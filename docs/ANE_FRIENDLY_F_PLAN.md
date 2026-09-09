# ANE-friendly F architecture — plan

Replace LayerNorm2d + SimpleGate inside the F backbone with ops Apple's Neural Engine actually accelerates. Goal: drop CNN inference from ~35 ms (Metal hybrid) to **~15-20 ms (ANE)** by routing through CoreML at ANE compute units.

Reference baseline: PiperSR shows 453K param image SR runs at 20.8 ms on ANE for 360p→720p. Our F is 263K params at codec dims (similar work) — should land below 20 ms if architecture is ANE-friendly.

## Op-by-op changes

| Current (F) | ANE-friendly replacement | Notes |
|---|---|---|
| `LayerNorm2d` (per-pixel mean+var) | `BatchNorm2d` | Folded into preceding Conv at inference. ANE-native. |
| `SimpleGate` (chunk + multiply halves) | `SiLU` activation | Single ANE-native op. Channel halving moves to the following `proj` conv. |
| `Conv2d 1x1` (conv1, proj1, mlp1, mlp2) | unchanged | ANE-native |
| `Conv2d 3x3 groups=2c` (depthwise) | **option A**: keep as-is | ANE supports depthwise but throughput lower than regular conv |
| | **option B**: replace with regular `Conv2d 3x3` at narrower channels | Equivalent expressive power if channels drop; simpler ANE graph |
| `Conv2d 3x3` head (subpixel/outro) | unchanged | ANE-native |
| `PixelShuffle` upsample | unchanged | ANE-native |

## Proposed NAFBlock-equivalent (ANE-friendly)

```python
class NAFBlockANE(nn.Module):
    def __init__(self, c):
        super().__init__()
        # Attention branch (was: LN1 → Conv1x1 c→2c → DW3x3 → SimpleGate → Proj1 c→c → residual)
        self.bn1 = nn.BatchNorm2d(c)
        self.conv1 = nn.Conv2d(c, 2*c, 1)
        self.dw = nn.Conv2d(2*c, 2*c, 3, padding=1, groups=2*c)  # keep depthwise
        self.act1 = nn.SiLU()
        self.proj1 = nn.Conv2d(2*c, c, 1)   # 2c → c (since SiLU doesn't halve channels)

        # MLP branch (was: LN2 → mlp1 c→2c → SimpleGate → mlp2 c→c → residual)
        self.bn2 = nn.BatchNorm2d(c)
        self.mlp1 = nn.Conv2d(c, 2*c, 1)
        self.act2 = nn.SiLU()
        self.mlp2 = nn.Conv2d(2*c, c, 1)    # 2c → c

    def forward(self, x):
        h = self.bn1(x); h = self.conv1(h); h = self.dw(h); h = self.act1(h); h = self.proj1(h)
        x = x + h
        h = self.bn2(x); h = self.mlp1(h); h = self.act2(h); h = self.mlp2(h)
        return x + h
```

Param count change:
- Old NAFBlock at c=16: ~2200 params (proj1 16→16, mlp2 16→16)
- New NAFBlockANE at c=16: ~2800 params (proj1 32→16, mlp2 32→16) — +27%
- Same for c=32, c=64: ~+27% each

Total F backbone: 263K → ~335K params. Still well under PiperSR's 453K.

## What to keep from the F architecture

- **3-level UNet skeleton** (encoder×3 + middle + decoder×3) — works on ANE
- **Width progression** 16→32→64→128 — works on ANE
- **PixelShuffle 2× super-res head** OR **3×3 conv 1× head** (existing BIBO_1x variant) — both ANE-native
- **Residual scale 0.01** for stable training — unchanged
- **Bayer plane layout** (4 channels in / 4 channels out at codec dims) — unchanged

## Training plan

Goal: produce two checkpoints matching the existing two production models, but ANE-friendly:
- `BayInBayOut_2x_AAon_w16_ANE.pt` — replaces F_aa_on.pt (2× super-res)
- `BayInBayOut_1x_AAon_w16_ANE.pt` — replaces BayInBayOut_1x_AAon_w16.pt (1× clean)

**Initialization**: not from the existing F checkpoint (incompatible state_dicts due to BN vs LN). Train from scratch with the existing tile data. Expected ~50-80 epochs (similar to F_aa_on which converged at ep 40).

**Quality targets**:
- Match F_aa_on within 0.3 dB on rendered Z8_ISO64 (currently +5.69 dB)
- Match BIBO_1x within 0.2 dB on rendered Z8_ISO64 (currently +0.89 dB)

If we miss the quality bar by a lot, the architecture change is wrong. If we miss by 0.1-0.3 dB, that's a reasonable tradeoff for the 2× speed.

## Deployment

1. Train PyTorch model with the new NAFBlockANE.
2. Convert to CoreML via `coremltools.convert(..., compute_precision=ct.precision.FLOAT16)` with `convert_to="mlprogram"`.
3. Verify the converted model lands on ANE: bench with `CNN_COREML_UNITS=ane` env var (already wired in `SuperResCNN.m`).
4. Compare timing to the existing Metal hybrid backend.
5. If ANE wins by ≥5 ms, switch the default to CoreML+ANE. Keep Metal hybrid as a fallback.

## Why this is worth doing vs. shipping at 23.5 fps

- **Frees the GPU for CIRAWFilter** — currently CNN and demosaic both compete for the M3 GPU. ANE inference unloads the CNN entirely.
- **Pipeline ceiling lifts** — if CNN moves to ANE at 15-20 ms AND demosaic stays at 37 ms on GPU (now uncontested), pipeline max stage drops to ~37 ms → 27+ fps with no other changes.
- **Energy improvement** — ANE is much more power-efficient than the GPU for the same op count, useful if this ever runs on a portable Mac.

## Risk / what could go wrong

1. **CoreML quirks**: BatchNorm folding can break if eval mode isn't set right at conversion time. Mitigation: call `model.eval()` before export; verify `BatchNormalization` ops are present in the converted graph.
2. **ANE precision**: ANE uses FP16 throughout. May see 0.1-0.3 dB rendered PSNR drop vs FP32 PyTorch training. Acceptable for the speed win.
3. **Depthwise conv on ANE**: lower throughput than regular conv. If profile shows depthwise dominating, swap to grouped conv (groups=4 or 8) instead of fully-depthwise.

## Estimate of effort

- Implement NAFBlockANE + variant constructor: **1 hour**
- Set up training script (copy of train_superres_F_aa_on.py): **1 hour**
- Train 2× super-res variant (60-80 epochs at ~80 sec/epoch on MPS): **80-110 minutes**
- Train 1× variant: **80-110 minutes** (could be parallel via two M3-Max GPU sessions)
- CoreML conversion + ANE bench: **1 hour**
- Integration with gpr2prores: **1 hour** (the `SuperResCNN.m` CoreML backend already exists)

Total: **~half a day of focused work**, mostly waiting for training.

## Open questions before starting

1. Are we OK with BatchNorm vs LayerNorm? BN is data-dependent during training; train/eval mode matters at conversion. PiperSR uses BN and ships, so it works in practice.
2. Should the head also change (PixelShuffle currently)? Probably no — PixelShuffle is ANE-native.
3. Knowledge distillation from F_aa_on as teacher? Plausible improvement but adds complexity. Skip for v1, revisit if quality drops by more than 0.3 dB.
