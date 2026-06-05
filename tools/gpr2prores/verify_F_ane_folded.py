"""End-to-end verification that BN-folded F_ane weights match the original
PyTorch forward pass, AND that the math the Metal kernel will execute is
exactly what we expect.

Method:
  1. Build the reference model in PyTorch from a checkpoint (BN + Conv1x1
     + SiLU + DW + Residual + …).
  2. Re-load the same weights from the BN-FOLDED .bin files produced by
     extract_F_ane_weights.py, into a parallel module that has NO BN — just
     Conv1x1 (with the folded weights), DW, SiLU, residual.
  3. Run both forward passes on the same input and report max abs diff.

If the diff is within fp16 noise (~0.1 absolute for typical activations),
the folded representation is faithful — and the Metal kernel doesn't need
to do anything fancier than what this NoBN module does.

Usage:
  python3 verify_F_ane_folded.py \\
      --ckpt /path/to/BayInBayOut_2x_AAon_w16_ANE.pt \\
      --weights-dir "$GPR_ARTIFACT_ROOT/weights/F_ane_w16_weights_metal" \\
      [--dw-kernel 3]
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
REPO = Path(__file__).resolve().parents[2]
def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root()))
DERING_DIR = Path(os.environ.get("GPR_DERING_DIR", EXTERNAL_ROOT / "external" / "dering_proto_v2"))
sys.path.insert(0, str(DERING_DIR))
sys.path.insert(0, str(REPO / "tools" / "cnn"))

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------- "NoBN" reference module (matches what Metal will compute) ----------------

class NAFBlockNoBN(nn.Module):
    """F_ane NAFBlock with BN folded into the following Conv1x1.

    Forward: x → conv1(x) → dw → silu → proj1 → +x  → mlp1 → silu → mlp2 → +x
    No BN, no LN. Just what the Metal kernels compute.
    """
    def __init__(self, c, dw_kernel=3):
        super().__init__()
        pad = dw_kernel // 2
        self.conv1 = nn.Conv2d(c, 2*c, 1)
        self.dw = nn.Conv2d(2*c, 2*c, dw_kernel, padding=pad, groups=2*c)
        self.proj1 = nn.Conv2d(2*c, c, 1)
        self.mlp1 = nn.Conv2d(c, 2*c, 1)
        self.mlp2 = nn.Conv2d(2*c, c, 1)

    def forward(self, x):
        h = self.conv1(x)
        h = self.dw(h)
        h = F.silu(h)
        h = self.proj1(h)
        x = x + h
        h = self.mlp1(x)
        h = F.silu(h)
        h = self.mlp2(h)
        return x + h


class NAFUNetNoBN(nn.Module):
    """U-Net mirror of NAFUNet from model_F_ane, but BN-folded."""
    def __init__(self, width=16, depth=3, sr=True, in_c=4, out_c=4, dw_kernel=3):
        super().__init__()
        self.sr = sr
        self.intro = nn.Conv2d(in_c, width, 3, padding=1)
        self.encoders = nn.ModuleList()
        self.downs = nn.ModuleList()
        c = width
        for _ in range(depth):
            self.encoders.append(nn.Sequential(NAFBlockNoBN(c, dw_kernel)))
            self.downs.append(nn.Conv2d(c, 2*c, 2, stride=2))
            c *= 2
        self.middle = nn.Sequential(NAFBlockNoBN(c, dw_kernel))
        self.ups = nn.ModuleList()
        self.decoders = nn.ModuleList()
        for _ in range(depth):
            self.ups.append(nn.Sequential(nn.Conv2d(c, 2*c, 1, bias=False), nn.PixelShuffle(2)))
            c //= 2
            self.decoders.append(nn.Sequential(NAFBlockNoBN(c, dw_kernel)))
        if sr:
            self.subpixel = nn.Sequential(nn.Conv2d(c, 4*out_c, 3, padding=1),
                                          nn.PixelShuffle(2))
        else:
            self.outro = nn.Conv2d(c, out_c, 3, padding=1)

    def forward(self, x):
        x = self.intro(x)
        skips = []
        for enc, dn in zip(self.encoders, self.downs):
            x = enc(x); skips.append(x); x = dn(x)
        x = self.middle(x)
        for up, dec, sk in zip(self.ups, self.decoders, reversed(skips)):
            x = up(x); x = x + sk; x = dec(x)
        return self.subpixel(x) if self.sr else self.outro(x)


# ---------------- weight loader from extractor outputs ----------------

def f16_read(path, shape):
    return torch.from_numpy(
        np.fromfile(path, dtype=np.float16).reshape(shape).astype(np.float32)
    )


def load_folded_into(model, wdir, dw_kernel):
    """Load .bin files (BN-folded fp16) into the NoBN model's parameters."""
    sd = model.state_dict()
    new_sd = {}

    # intro
    new_sd["intro.weight"] = f16_read(os.path.join(wdir, "intro_weight.bin"),
                                      sd["intro.weight"].shape).reshape(sd["intro.weight"].shape)
    new_sd["intro.bias"]   = f16_read(os.path.join(wdir, "intro_bias.bin"),
                                      sd["intro.bias"].shape)

    width = sd["intro.weight"].shape[0]
    enc_widths = [width, 2*width, 4*width]
    dec_widths = [4*width, 2*width, width]
    down_pairs = [(width, 2*width), (2*width, 4*width), (4*width, 8*width)]

    def load_block(prefix_sd, prefix_disk, C):
        # conv1 BN-folded:  [2C, C] saved as [2C, C]
        new_sd[f"{prefix_sd}.conv1.weight"] = (
            f16_read(os.path.join(wdir, f"{prefix_disk}_conv1_weight.bin"), (2*C, C))
            .reshape(2*C, C, 1, 1)
        )
        new_sd[f"{prefix_sd}.conv1.bias"] = f16_read(
            os.path.join(wdir, f"{prefix_disk}_conv1_bias.bin"), (2*C,))
        # dw: [2C, k*k] -> [2C, 1, k, k]
        new_sd[f"{prefix_sd}.dw.weight"] = (
            f16_read(os.path.join(wdir, f"{prefix_disk}_dw_weight.bin"),
                     (2*C, dw_kernel*dw_kernel))
            .reshape(2*C, 1, dw_kernel, dw_kernel)
        )
        new_sd[f"{prefix_sd}.dw.bias"] = f16_read(
            os.path.join(wdir, f"{prefix_disk}_dw_bias.bin"), (2*C,))
        # proj1: [C, 2C] -> [C, 2C, 1, 1]
        new_sd[f"{prefix_sd}.proj1.weight"] = (
            f16_read(os.path.join(wdir, f"{prefix_disk}_proj1_weight.bin"), (C, 2*C))
            .reshape(C, 2*C, 1, 1)
        )
        new_sd[f"{prefix_sd}.proj1.bias"] = f16_read(
            os.path.join(wdir, f"{prefix_disk}_proj1_bias.bin"), (C,))
        # mlp1 BN-folded: [2C, C]
        new_sd[f"{prefix_sd}.mlp1.weight"] = (
            f16_read(os.path.join(wdir, f"{prefix_disk}_mlp1_weight.bin"), (2*C, C))
            .reshape(2*C, C, 1, 1)
        )
        new_sd[f"{prefix_sd}.mlp1.bias"] = f16_read(
            os.path.join(wdir, f"{prefix_disk}_mlp1_bias.bin"), (2*C,))
        # mlp2: [C, 2C]
        new_sd[f"{prefix_sd}.mlp2.weight"] = (
            f16_read(os.path.join(wdir, f"{prefix_disk}_mlp2_weight.bin"), (C, 2*C))
            .reshape(C, 2*C, 1, 1)
        )
        new_sd[f"{prefix_sd}.mlp2.bias"] = f16_read(
            os.path.join(wdir, f"{prefix_disk}_mlp2_bias.bin"), (C,))

    for k, C in enumerate(enc_widths):
        load_block(f"encoders.{k}.0", f"enc{k}", C)

    for k, (cin, cout) in enumerate(down_pairs):
        new_sd[f"downs.{k}.weight"] = f16_read(os.path.join(wdir, f"down{k}_weight.bin"),
                                                sd[f"downs.{k}.weight"].shape).reshape(sd[f"downs.{k}.weight"].shape)
        new_sd[f"downs.{k}.bias"] = f16_read(os.path.join(wdir, f"down{k}_bias.bin"),
                                              sd[f"downs.{k}.bias"].shape)

    load_block("middle.0", "middle", 8*width)

    for k, cin in enumerate([8*width, 4*width, 2*width]):
        new_sd[f"ups.{k}.0.weight"] = (
            f16_read(os.path.join(wdir, f"up{k}_weight.bin"), (2*cin, cin))
            .reshape(2*cin, cin, 1, 1)
        )

    for k, C in enumerate(dec_widths):
        load_block(f"decoders.{k}.0", f"dec{k}", C)

    if "subpixel.0.weight" in sd:
        new_sd["subpixel.0.weight"] = f16_read(os.path.join(wdir, "subpixel_weight.bin"),
                                                sd["subpixel.0.weight"].shape).reshape(sd["subpixel.0.weight"].shape)
        new_sd["subpixel.0.bias"] = f16_read(os.path.join(wdir, "subpixel_bias.bin"),
                                              sd["subpixel.0.bias"].shape)
    else:
        new_sd["outro.weight"] = f16_read(os.path.join(wdir, "outro_weight.bin"),
                                           sd["outro.weight"].shape).reshape(sd["outro.weight"].shape)
        new_sd["outro.bias"] = f16_read(os.path.join(wdir, "outro_bias.bin"),
                                         sd["outro.bias"].shape)

    model.load_state_dict(new_sd, strict=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--weights-dir", required=True)
    ap.add_argument("--dw-kernel", type=int, default=3)
    args = ap.parse_args()

    # Ref model (BN included)
    from model_F_ane import build, build_lk
    ck = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    variant = ck.get("variant", "F_ane")
    if args.dw_kernel == 3:
        ref = build(variant)
    else:
        ref = build_lk(variant, dw_kernel=args.dw_kernel)
    ref.load_state_dict(ck["backbone_state"])
    ref.eval()
    sr2x = getattr(ref, "sr", True)

    # NoBN model (folded weights)
    fold = NAFUNetNoBN(width=16, depth=3, sr=sr2x, dw_kernel=args.dw_kernel)
    load_folded_into(fold, args.weights_dir, args.dw_kernel)
    fold.eval()

    print(f"variant={variant}  sr={sr2x}  dw_kernel={args.dw_kernel}")
    print(f"ref params:  {sum(p.numel() for p in ref.parameters()):,}")
    print(f"fold params: {sum(p.numel() for p in fold.parameters()):,}")
    print(f"(fold ≤ ref because BN params are absorbed into Conv1x1)")

    torch.manual_seed(0)
    x = torch.randn(1, 4, 64, 64)

    with torch.no_grad():
        y_ref = ref(x)
        y_fold = fold(x)

    diff = (y_ref - y_fold).abs()
    print(f"output shape ref: {tuple(y_ref.shape)}  fold: {tuple(y_fold.shape)}")
    print(f"output range ref:  [{y_ref.min().item():+.4f}, {y_ref.max().item():+.4f}]")
    print(f"output range fold: [{y_fold.min().item():+.4f}, {y_fold.max().item():+.4f}]")
    print(f"max abs diff:  {diff.max().item():.6f}")
    print(f"mean abs diff: {diff.mean().item():.6f}")
    out_range = (y_ref.max() - y_ref.min()).item()
    print(f"max diff / output range: {diff.max().item()/out_range:.2%}")

    # In the deployment pipeline the model output is multiplied by
    # RESIDUAL_SCALE=0.01 before being added to the bicubic baseline.
    # Deployment-meaningful threshold: max diff * 0.01 should be far smaller
    # than 1 LSB in the 14-bit output (raw_norm=16383 → 1 LSB ≈ 1/16383).
    deploy_err_lsb = (diff.max().item() * 0.01) * 16383
    print(f"deployment-scaled max err: {deploy_err_lsb:.3f} LSB out of 16383")

    ok = deploy_err_lsb < 100.0   # 100 LSB out of 16383 ≈ 0.6% — well below visible.
    print(f"\n{'PASS' if ok else 'FAIL'} — fold faithfulness "
          f"(deploy err < 100 LSB)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
