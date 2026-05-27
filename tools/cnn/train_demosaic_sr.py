"""Train the F_ane_dm_sr variant: 4-channel half-res bayer in, 3-channel
full-res RGB out. The model learns demosaic + super-res in one pass,
avoiding the per-channel bayer-plane bicubic upscale that produces
artifacts in the BIBO_2x path on out-of-distribution content
(see SHIP_DECISION.md 2026-05-26).

Training data: existing tiles_ml2_q3_dec2_combined.npz (codec 128×128
4ch, target 256×256 4ch). At dataloader time we deinterleave the target
back into a 512×512 bayer plane and bilinear-demosaic it into a 512×512
3ch RGB tile. The CNN learns to produce this RGB from the codec's 4ch
bayer half-res input.
"""
from __future__ import annotations
import os, sys, time, argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import build as build_variant, count_params

RAW_NORM = 16383.0
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
DEFAULT_NPZ = os.environ.get(
    "SUPERRES_NPZ", "/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_combined.npz"
)
CKPT_DIR = os.environ.get("CKPT_DIR",
                          "/Users/dcliftreaves/Documents/Github/gpr/models")
VAL_SRC_NAME = os.environ.get("VAL_SRC_NAME", "Z8Z_0067")


def bayer_4plane_to_rgb(planes: torch.Tensor) -> torch.Tensor:
    """Reconstruct full-res bilinear-demosaiced RGB from 4 deinterleaved
    bayer planes. Input: (B, 4, H, W) representing R / G1 / G2 / B planes
    of a 2H × 2W bayer image. Output: (B, 3, 2H, 2W) RGB.

    Reassembly:
      bayer[0::2, 0::2] = R; bayer[0::2, 1::2] = G1;
      bayer[1::2, 0::2] = G2; bayer[1::2, 1::2] = B.
    Bilinear demosaic: G at R sites = avg of 4 neighbor G's; R at non-R
    sites = bilinear; etc. Implemented as conv with fixed RGGB kernels.
    """
    B, _, H, W = planes.shape
    bayer = torch.zeros((B, 1, 2*H, 2*W), device=planes.device, dtype=planes.dtype)
    bayer[:, 0, 0::2, 0::2] = planes[:, 0]  # R
    bayer[:, 0, 0::2, 1::2] = planes[:, 1]  # G1
    bayer[:, 0, 1::2, 0::2] = planes[:, 2]  # G2
    bayer[:, 0, 1::2, 1::2] = planes[:, 3]  # B
    # Build channel masks (1 where that color is sampled)
    mR  = torch.zeros_like(bayer); mR[:, :, 0::2, 0::2] = 1
    mG1 = torch.zeros_like(bayer); mG1[:, :, 0::2, 1::2] = 1
    mG2 = torch.zeros_like(bayer); mG2[:, :, 1::2, 0::2] = 1
    mB  = torch.zeros_like(bayer); mB[:, :, 1::2, 1::2] = 1
    sR  = bayer * mR
    sG  = bayer * (mG1 + mG2)
    sB  = bayer * mB
    # Bilinear interpolation kernels.
    # R/B at 1/4 of sites → 3x3 kernel [[1,2,1],[2,4,2],[1,2,1]]/4
    # G at 1/2 of sites → cross kernel [[0,1,0],[1,4,1],[0,1,0]]/4
    k_rb = torch.tensor([[1, 2, 1], [2, 4, 2], [1, 2, 1]],
                        dtype=bayer.dtype, device=bayer.device) / 4.0
    k_g  = torch.tensor([[0, 1, 0], [1, 4, 1], [0, 1, 0]],
                        dtype=bayer.dtype, device=bayer.device) / 4.0
    k_rb = k_rb.view(1, 1, 3, 3); k_g = k_g.view(1, 1, 3, 3)
    R = F.conv2d(sR, k_rb, padding=1)
    G = F.conv2d(sG, k_g, padding=1)
    Bc = F.conv2d(sB, k_rb, padding=1)
    return torch.cat([R, G, Bc], dim=1)


def load_data(npz_path, val_src_name, subsample_rate=1):
    print(f"  loading {npz_path}...", flush=True)
    t0 = time.time()
    npz = np.load(npz_path, mmap_mode="r", allow_pickle=True)
    src = np.asarray(npz["src"])
    lookup = np.asarray(npz["src_lookup_names"])
    names = [s.decode() if isinstance(s, bytes) else s for s in lookup.tolist()]
    val_match = [i for i, n in enumerate(names) if n == val_src_name]
    if not val_match:
        raise RuntimeError(f"VAL_SRC_NAME '{val_src_name}' not in NPZ; got {names[:5]}")
    val_src_id = val_match[0]
    rng = np.random.RandomState(0)
    keep_mask = np.zeros(len(src), dtype=bool)
    for i in range(len(src)):
        if src[i] == val_src_id or rng.rand() < (1.0 / subsample_rate):
            keep_mask[i] = True
    print(f"  keeping {keep_mask.sum()} of {len(src)} tiles", flush=True)
    out = {}
    for k in ["codec_R", "codec_G1", "codec_G2", "codec_B"]:
        out[k] = np.asarray(npz[k][keep_mask])
    # Two NPZ schemas supported:
    #   1) New dmsr schema: tgt_rgb (N, 512, 512, 3) uint8 — sips-rendered RGB
    #   2) Old super-res schema: tgt_R/G1/G2/B 4-channel bayer (we bilinear-
    #      demosaic at dataloader time, sensor RGB — wrong target color space)
    if "tgt_rgb" in npz.files:
        out["tgt_rgb"] = np.asarray(npz["tgt_rgb"][keep_mask])
        out["_has_rgb_target"] = True
        print(f"  using NEW tgt_rgb (sips-rendered targets)", flush=True)
    else:
        for k in ["tgt_R", "tgt_G1", "tgt_G2", "tgt_B"]:
            out[k] = np.asarray(npz[k][keep_mask])
        out["_has_rgb_target"] = False
        print(f"  using LEGACY tgt_bayer (bilinear-demosaic; WRONG color space)",
              flush=True)
    out["src"] = src[keep_mask]
    out["_val_src_id"] = val_src_id
    print(f"  loaded in {time.time() - t0:.1f}s", flush=True)
    return out


def codec_planes_from_mem(d, idx):
    codec = np.stack([d["codec_R"][idx], d["codec_G1"][idx],
                      d["codec_G2"][idx], d["codec_B"][idx]], 0)
    return codec.astype(np.float32) / RAW_NORM


def tgt_rgb_from_mem(d, idx):
    """Returns (3, H, W) float32 RGB in [0, 1]."""
    if d.get("_has_rgb_target", False):
        rgb = d["tgt_rgb"][idx]                                  # (H, W, 3) uint8
        return np.transpose(rgb, (2, 0, 1)).astype(np.float32) / 255.0
    # Legacy: bilinear-demosaic from target bayer planes (sensor RGB).
    tgt = np.stack([d["tgt_R"][idx], d["tgt_G1"][idx],
                    d["tgt_G2"][idx], d["tgt_B"][idx]], 0).astype(np.float32) / RAW_NORM
    return tgt  # caller does bayer_4plane_to_rgb if legacy


class TileDS(Dataset):
    def __init__(self, mem, indices, augment=True):
        self.mem = mem; self.indices = indices; self.augment = augment
        self.has_rgb = mem.get("_has_rgb_target", False)
    def __len__(self): return len(self.indices)
    def __getitem__(self, i):
        idx = self.indices[i]
        codec = codec_planes_from_mem(self.mem, idx)
        tgt = tgt_rgb_from_mem(self.mem, idx)
        if self.augment:
            if np.random.rand() < 0.5:
                codec = codec[:, :, ::-1].copy(); tgt = tgt[:, :, ::-1].copy()
                # Codec channel swap on horizontal flip: R↔G1, G2↔B
                codec = codec[[1, 0, 3, 2]]
                # RGB target: horizontal flip is just spatial; channel order unchanged
            if np.random.rand() < 0.5:
                codec = codec[:, ::-1, :].copy(); tgt = tgt[:, ::-1, :].copy()
                codec = codec[[2, 3, 0, 1]]
        return torch.from_numpy(np.ascontiguousarray(codec)).float(), \
               torch.from_numpy(np.ascontiguousarray(tgt)).float()


def multiscale_l1(pred, tgt, weights=(1.0, 0.5, 0.25)):
    losses = [F.l1_loss(pred, tgt) * weights[0]]
    p, t = pred, tgt
    for w in weights[1:]:
        p = F.avg_pool2d(p, 2); t = F.avg_pool2d(t, 2)
        losses.append(F.l1_loss(p, t) * w)
    return sum(losses)


def train(args):
    print(f"=== Training F_ane_dm_sr (joint demosaic + super-res) ===")
    print(f"Device: {DEVICE}  CKPT_DIR: {CKPT_DIR}  NPZ: {DEFAULT_NPZ}")
    os.makedirs(CKPT_DIR, exist_ok=True)
    d = load_data(DEFAULT_NPZ, VAL_SRC_NAME, subsample_rate=args.subsample)
    src = d["src"]; val_src = {d["_val_src_id"]}
    N = len(src)
    train_idx = [i for i in range(N) if src[i] not in val_src]
    val_idx   = [i for i in range(N) if src[i] in val_src]
    print(f"  train tiles: {len(train_idx)}  val tiles: {len(val_idx)}", flush=True)
    tr = DataLoader(TileDS(d, train_idx, augment=True),  batch_size=args.batch,
                    shuffle=True,  num_workers=0)
    va = DataLoader(TileDS(d, val_idx,   augment=False), batch_size=args.batch,
                    shuffle=False, num_workers=0)
    model = build_variant("F_ane_dm_sr").to(DEVICE)
    print(f"  Params (backbone): {count_params(model):,}", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    has_rgb = d.get("_has_rgb_target", False)
    def evaluate():
        model.eval()
        tot_b, tot_a, n = 0.0, 0.0, 0
        with torch.no_grad():
            for inp, tgt in va:
                inp = inp.to(DEVICE); tgt = tgt.to(DEVICE)
                if has_rgb:
                    tgt_rgb = tgt.clamp(0, 1)              # already RGB in [0, 1]
                else:
                    tgt_rgb = bayer_4plane_to_rgb(tgt).clamp(0, 1)
                # Baseline: bilinear-demosaic the codec bayer + bicubic 2x.
                # Same path the gate's cnn=none variant uses (modulo Apple's
                # demosaic flavor); useful for "is the CNN doing real work".
                codec_rgb_lo = bayer_4plane_to_rgb(inp).clamp(0, 1)
                base = F.interpolate(codec_rgb_lo, scale_factor=2, mode="bicubic",
                                     align_corners=False).clamp(0, 1)
                pred = model(inp).clamp(0, 1)
                mse_b = ((base - tgt_rgb) ** 2).mean(dim=[1, 2, 3])
                mse_a = ((pred - tgt_rgb) ** 2).mean(dim=[1, 2, 3])
                tot_b += (-10 * torch.log10(mse_b.clamp_min(1e-12))).sum().item()
                tot_a += (-10 * torch.log10(mse_a.clamp_min(1e-12))).sum().item()
                n += inp.shape[0]
        return tot_b / n, tot_a / n

    best_gain = -1e9; best_after = -1e9; best_epoch = -1
    epochs_since_best = 0
    ckpt_path = os.path.join(CKPT_DIR, args.ckpt_name)
    pb, pa = evaluate()
    print(f"  Initial  base PSNR={pb:.3f}  model PSNR={pa:.3f}  gain={pa-pb:+.3f} dB",
          flush=True)
    for ep in range(args.epochs):
        model.train(); t0 = time.time(); loss_sum = 0.0; nb = 0
        for inp, tgt in tr:
            inp = inp.to(DEVICE); tgt = tgt.to(DEVICE)
            tgt_rgb = tgt.clamp(0, 1) if has_rgb else bayer_4plane_to_rgb(tgt).clamp(0, 1)
            pred = model(inp).clamp(0, 1)
            l = multiscale_l1(pred, tgt_rgb)
            opt.zero_grad(set_to_none=True); l.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); loss_sum += l.item(); nb += 1
        sched.step()
        pb, pa = evaluate()
        gain = pa - pb
        marker = ""
        if gain > best_gain:
            best_gain = gain; best_after = pa; best_epoch = ep + 1
            epochs_since_best = 0
            torch.save({
                "backbone_state": model.state_dict(),
                "variant": "F_ane_dm_sr",
                "width": 16, "depth": 3, "raw_norm": RAW_NORM, "residual_scale": 0.0,
                "kind": "demosaic_sr", "epoch": ep + 1,
                "val_psnr_base": pb, "val_psnr_model": pa,
                "params": count_params(model),
            }, ckpt_path)
            marker = "  [SAVED]"
        else:
            epochs_since_best += 1
        print(f"  ep {ep+1:3d}/{args.epochs}  loss={loss_sum/nb:.5f}  "
              f"base={pb:.3f}  model={pa:.3f}  gain={gain:+.3f} dB  "
              f"t={time.time()-t0:.1f}s{marker}", flush=True)
        if epochs_since_best >= args.patience and ep + 1 >= 40:
            print(f"  Early stop: no improvement in {args.patience} epochs", flush=True)
            break
    print(f"\n  Best val PSNR gain: {best_gain:+.3f} dB at epoch {best_epoch}")
    print(f"  Best val PSNR (model): {best_after:.3f} dB")
    print(f"  Checkpoint: {ckpt_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=4)   # smaller batch since outputs are 4× bigger
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--patience", type=int, default=25)
    ap.add_argument("--subsample", type=int, default=1)
    ap.add_argument("--ckpt-name", type=str,
                    default="BayInBayOut_DMSR_AAon_w16_ANE.pt")
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()
