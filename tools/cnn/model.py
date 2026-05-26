"""F-arch backbone, ANE-friendly variant.

Same 3-level UNet skeleton as F (NAFNetTiny w=16). Two ops swapped vs the
original NAFBlock so the converted CoreML model can run on Apple Neural
Engine at peak throughput:

  LayerNorm2d (per-pixel mean+var) → BatchNorm2d (folds into preceding conv at inference)
  SimpleGate (chunk + multiply halves) → SiLU (single ANE-native op)

Channel sizes are preserved (16/32/64/128 across the U-net). The SimpleGate
removal means the "halving" effect now lives in the proj1 / mlp2 convs which
go 2c → c (vs c → c in the original). Net ~+25% params per block.

See docs/ANE_FRIENDLY_F_PLAN.md in the main gpr repo for the rationale.
"""
import torch
import torch.nn as nn


def count_params(m):
    return sum(p.numel() for p in m.parameters() if p.requires_grad)


class NAFBlockANE(nn.Module):
    """NAFBlock with LayerNorm → BatchNorm and SimpleGate → SiLU."""
    def __init__(self, c):
        super().__init__()
        # Attention branch
        self.bn1 = nn.BatchNorm2d(c)
        self.conv1 = nn.Conv2d(c, 2*c, 1)
        self.dw = nn.Conv2d(2*c, 2*c, 3, padding=1, groups=2*c)
        self.act1 = nn.SiLU()
        self.proj1 = nn.Conv2d(2*c, c, 1)

        # MLP branch
        self.bn2 = nn.BatchNorm2d(c)
        self.mlp1 = nn.Conv2d(c, 2*c, 1)
        self.act2 = nn.SiLU()
        self.mlp2 = nn.Conv2d(2*c, c, 1)

    def forward(self, x):
        # Attention residual
        h = self.bn1(x)
        h = self.conv1(h)
        h = self.dw(h)
        h = self.act1(h)
        h = self.proj1(h)
        x = x + h
        # MLP residual
        h = self.bn2(x)
        h = self.mlp1(h)
        h = self.act2(h)
        h = self.mlp2(h)
        return x + h


class NAFUNetANE(nn.Module):
    """3-level U-Net of NAFBlockANE — drop-in compute replacement for the F
    architecture (width=16, enc=[1,1,1], dec=[1,1,1], mid=1) with ANE-friendly
    ops. `sr` toggles between 2× super-res (subpixel head) and 1× clean (outro
    Conv3x3) — same conditional as F's NAFUNet."""
    def __init__(self, width=16, enc_blocks=(1, 1, 1), dec_blocks=(1, 1, 1),
                 mid_blocks=1, sr=True, in_c=4, out_c=4):
        super().__init__()
        self.sr = sr
        self.intro = nn.Conv2d(in_c, width, 3, padding=1)

        self.encoders = nn.ModuleList()
        self.downs = nn.ModuleList()
        c = width
        for nb in enc_blocks:
            self.encoders.append(nn.Sequential(*[NAFBlockANE(c) for _ in range(nb)]))
            self.downs.append(nn.Conv2d(c, 2*c, 2, stride=2))
            c *= 2

        self.middle = nn.Sequential(*[NAFBlockANE(c) for _ in range(mid_blocks)])

        self.ups = nn.ModuleList()
        self.decoders = nn.ModuleList()
        for nb in dec_blocks:
            self.ups.append(nn.Sequential(nn.Conv2d(c, 2*c, 1, bias=False),
                                           nn.PixelShuffle(2)))
            c //= 2
            self.decoders.append(nn.Sequential(*[NAFBlockANE(c) for _ in range(nb)]))

        if sr:
            self.subpixel = nn.Sequential(
                nn.Conv2d(c, 4*out_c, 3, padding=1),
                nn.PixelShuffle(2),
            )
        else:
            self.outro = nn.Conv2d(c, out_c, 3, padding=1)

    def forward(self, x):
        x = self.intro(x)
        skips = []
        for enc, dn in zip(self.encoders, self.downs):
            x = enc(x); skips.append(x); x = dn(x)
        x = self.middle(x)
        for up, dec, sk in zip(self.ups, self.decoders, reversed(skips)):
            x = up(x)
            x = x + sk
            x = dec(x)
        if self.sr:
            return self.subpixel(x)
        return self.outro(x)


VARIANTS = {
    "F_ane":       dict(width=16, enc=[1, 1, 1], dec=[1, 1, 1], mid=1, sr=True),
    "F_ane_no_sr": dict(width=16, enc=[1, 1, 1], dec=[1, 1, 1], mid=1, sr=False),
}


def build(tag):
    cfg = VARIANTS[tag]
    return NAFUNetANE(width=cfg["width"], enc_blocks=cfg["enc"],
                      dec_blocks=cfg["dec"], mid_blocks=cfg["mid"],
                      sr=cfg["sr"])


if __name__ == "__main__":
    for tag in VARIANTS:
        m = build(tag)
        n = count_params(m)
        print(f"{tag:15s}  params={n:>10,}")
    # smoke test on MPS
    import os
    if "KMP_DUPLICATE_LIB_OK" not in os.environ:
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"device: {device}")
    m = build("F_ane").to(device).eval()
    x = torch.randn(1, 4, 1384, 2072, device=device)
    import time
    # Warm up
    with torch.no_grad():
        for _ in range(3):
            _ = m(x)
    if device.type == "mps":
        torch.mps.synchronize()
    t0 = time.time()
    with torch.no_grad():
        for _ in range(10):
            y = m(x)
    if device.type == "mps":
        torch.mps.synchronize()
    t1 = time.time()
    print(f"F_ane forward 10x on {tuple(x.shape)}: avg {(t1-t0)/10*1000:.1f} ms  out {tuple(y.shape)}")


# --- Wider / large-kernel variants for research-driven experiments ---
# These extend the VARIANTS dict with arch variations to test what actually
# moves rendered PSNR (as opposed to cosmetic op-swaps).

import torch.nn as _nn


class NAFBlockANE_LK(_nn.Module):
    """NAFBlockANE but with dw 7x7 (large kernel) in the attention path.
    Adaptation of SMFFRaw's large-kernel attention idea — wider receptive
    field per layer."""
    def __init__(self, c, dw_kernel=7):
        super().__init__()
        pad = dw_kernel // 2
        self.bn1 = _nn.BatchNorm2d(c)
        self.conv1 = _nn.Conv2d(c, 2*c, 1)
        self.dw = _nn.Conv2d(2*c, 2*c, dw_kernel, padding=pad, groups=2*c)
        self.act1 = _nn.SiLU()
        self.proj1 = _nn.Conv2d(2*c, c, 1)
        self.bn2 = _nn.BatchNorm2d(c)
        self.mlp1 = _nn.Conv2d(c, 2*c, 1)
        self.act2 = _nn.SiLU()
        self.mlp2 = _nn.Conv2d(2*c, c, 1)

    def forward(self, x):
        h = self.bn1(x); h = self.conv1(h); h = self.dw(h); h = self.act1(h); h = self.proj1(h)
        x = x + h
        h = self.bn2(x); h = self.mlp1(h); h = self.act2(h); h = self.mlp2(h)
        return x + h


class NAFUNetANE_LK(NAFUNetANE):
    """U-Net with large-kernel NAFBlockANE_LK at every level."""
    def __init__(self, width=16, enc_blocks=(1, 1, 1), dec_blocks=(1, 1, 1),
                 mid_blocks=1, sr=True, in_c=4, out_c=4, dw_kernel=7):
        # Initialize NAFUNetANE first so all the layers exist, then swap blocks
        super().__init__(width=width, enc_blocks=enc_blocks, dec_blocks=dec_blocks,
                         mid_blocks=mid_blocks, sr=sr, in_c=in_c, out_c=out_c)
        # Replace every NAFBlockANE with NAFBlockANE_LK(dw_kernel=dw_kernel)
        def _channel_of(seq):
            return seq[0].bn1.weight.shape[0]
        for i, enc in enumerate(self.encoders):
            c = _channel_of(enc)
            self.encoders[i] = _nn.Sequential(*[NAFBlockANE_LK(c, dw_kernel) for _ in range(enc_blocks[i])])
        mid_c = _channel_of(self.middle)
        self.middle = _nn.Sequential(*[NAFBlockANE_LK(mid_c, dw_kernel) for _ in range(mid_blocks)])
        for i, dec in enumerate(self.decoders):
            c = _channel_of(dec)
            self.decoders[i] = _nn.Sequential(*[NAFBlockANE_LK(c, dw_kernel) for _ in range(dec_blocks[i])])


# Extend VARIANTS with research-driven variants
VARIANTS.update({
    "F_ane_w24":       dict(width=24, enc=[1, 1, 1], dec=[1, 1, 1], mid=1, sr=True),
    "F_ane_w24_no_sr": dict(width=24, enc=[1, 1, 1], dec=[1, 1, 1], mid=1, sr=False),
    "F_ane_w32":       dict(width=32, enc=[1, 1, 1], dec=[1, 1, 1], mid=1, sr=True),
    "F_ane_w32_no_sr": dict(width=32, enc=[1, 1, 1], dec=[1, 1, 1], mid=1, sr=False),
})


def build_lk(tag, dw_kernel=7):
    """Build a large-kernel variant. tag is one of the standard F_ane variants;
    the dw kernel size is added separately."""
    cfg = VARIANTS[tag]
    return NAFUNetANE_LK(width=cfg["width"], enc_blocks=cfg["enc"],
                         dec_blocks=cfg["dec"], mid_blocks=cfg["mid"],
                         sr=cfg["sr"], dw_kernel=dw_kernel)
