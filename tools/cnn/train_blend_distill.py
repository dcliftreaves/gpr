"""Distill the guided-filter chroma post-process into a single BIDO CNN.

Background (commit ddda2d6):
  The two-CNN + guided-filter pipeline -- BIDO_4x_w24 for luma, cnn=none
  (bicubic + sips) for chroma, He 2010 guided filter to smooth chroma
  using BIDO's Y as the edge guide -- beats both BIDO and cnn=none on
  three of four gate images at full-res. The cost: two CNN inferences
  plus a guided filter per frame.

This trainer teaches a single BIDO_4x_w16 model to produce the SAME
output in one inference. We do not regenerate the blend target as a
new NPZ -- instead, for each training tile, we:

  1. Read the codec planes from the existing tiles_ml2_q3_dec2_dmsr_gate.npz
     (input).
  2. Run the frozen BIDO_4x_w24 teacher on those planes -> "teacher RGB"
     (the source of luma in the blend).
  3. Read tgt_rgb from the NPZ -- this is the sips-rendered RGB which is
     exactly what the cnn=none pipeline produces. It is the source of
     chroma in the blend.
  4. Apply the He 2010 guided filter inside YCbCr: keep BIDO Y, replace
     Cb and Cr with guided-filtered tgt_rgb Cb/Cr (BIDO Y as guide).
  5. Train the student BIDO_4x_w16 against this blend target with the
     same msL1 + LPIPS recipe used in Phase A.

Reuses TileDS / NPZ loaders / multiscale loss from train_demosaic_sr.py
so we don't fork the entire trainer.

The frozen teacher runs on the same MPS device as the student. Per-step
overhead: one extra forward + four box-filter passes per tile. Wall
clock estimate on M3 Max at batch 4 / 19,920 tiles / 80 epochs: ~3-4 hr.

Output checkpoint:
  models/BayInDemosaicOut_4x_AAon_w16_ANE_blend_distill.pt
"""
from __future__ import annotations
import os
import sys
import time
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import build as build_variant, count_params, VARIANTS
from train_demosaic_sr import (
    load_data, TileDS, multiscale_l1, RAW_NORM,
    bayer_4plane_to_rgb,
)

DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
DEFAULT_NPZ = os.environ.get(
    "SUPERRES_NPZ", "/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate.npz"
)
CKPT_DIR = os.environ.get("CKPT_DIR",
                          "/Users/dcliftreaves/Documents/Github/gpr/models")
VAL_SRC_NAMES = os.environ.get("VAL_SRC_NAMES",
                                os.environ.get("VAL_SRC_NAME", "Z8Z_0067"))


# --- BT.601 YCbCr conversions (full-range 0..1) ----------------------------
# Matches cv2.cvtColor(COLOR_RGB2YCrCb) used in tools/cnn/guided_filter_post_process.py
# (OpenCV uses Y in [0..1], Cr/Cb in [0..1] with offset 0.5 in 8-bit, but in
# float here we keep the same coefficients). For a perceptual-edge guide the
# constants don't need to match cv2 bit-exact -- we just need a sensible Y.
_BT601_RGB2Y = (0.299, 0.587, 0.114)


def rgb_to_ycbcr(rgb):
    """rgb: (B, 3, H, W) in [0, 1]. Returns (Y, Cb, Cr), each (B, 1, H, W).
    Centered chroma in [-0.5, 0.5] (BT.601 full-range)."""
    r, g, b = rgb[:, 0:1], rgb[:, 1:2], rgb[:, 2:3]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = -0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 0.5 * r - 0.418688 * g - 0.081312 * b
    return y, cb, cr


def ycbcr_to_rgb(y, cb, cr):
    """Inverse of rgb_to_ycbcr. Inputs (B, 1, H, W). Returns (B, 3, H, W) in [0, 1]."""
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    return torch.cat([r, g, b], dim=1).clamp(0.0, 1.0)


# --- guided filter (He et al. 2010) ----------------------------------------
def _box(x, r):
    """Box filter with reflect padding; matches cv2.boxFilter for square kernel."""
    k = 2 * r + 1
    pad = r
    x_p = F.pad(x, (pad, pad, pad, pad), mode="reflect")
    return F.avg_pool2d(x_p, kernel_size=k, stride=1, padding=0)


def guided_filter(guide, src, radius=8, eps=1e-3):
    """Single-channel guided filter. guide and src: (B, 1, H, W) float."""
    mean_I = _box(guide, radius)
    mean_p = _box(src, radius)
    corr_Ip = _box(guide * src, radius)
    cov_Ip = corr_Ip - mean_I * mean_p
    var_I = _box(guide * guide, radius) - mean_I * mean_I
    a = cov_Ip / (var_I + eps)
    b = mean_p - a * mean_I
    mean_a = _box(a, radius)
    mean_b = _box(b, radius)
    return mean_a * guide + mean_b


def blend_guided_torch(teacher_rgb, chroma_rgb, radius=8, eps=1e-3):
    """Replicates blend_guided() from tools/cnn/guided_filter_post_process.py
    on tensors. teacher_rgb supplies Y + edge guide; chroma_rgb supplies the
    Cb/Cr that get guided-filtered. Both (B, 3, H, W) in [0, 1]."""
    y_t, _, _ = rgb_to_ycbcr(teacher_rgb)
    _, cb_c, cr_c = rgb_to_ycbcr(chroma_rgb)
    cb_filt = guided_filter(y_t, cb_c, radius=radius, eps=eps)
    cr_filt = guided_filter(y_t, cr_c, radius=radius, eps=eps)
    return ycbcr_to_rgb(y_t, cb_filt, cr_filt)


# --- training --------------------------------------------------------------
def _load_teacher(ckpt_path, device):
    if not os.path.exists(ckpt_path):
        raise FileNotFoundError(f"--teacher-ckpt not found: {ckpt_path}")
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    variant = ck.get("variant", "F_ane_dm_sr_w24")
    m = build_variant(variant).to(device).eval()
    m.load_state_dict(ck["backbone_state"])
    for p in m.parameters():
        p.requires_grad_(False)
    return m, variant


def train(args):
    print(f"=== Train blend-distill BIDO_4x_w16 ===")
    print(f"Device: {DEVICE}  CKPT_DIR: {CKPT_DIR}  NPZ: {DEFAULT_NPZ}")
    print(f"Teacher: {args.teacher_ckpt}  guided radius={args.guided_radius} "
          f"eps={args.guided_eps}", flush=True)
    os.makedirs(CKPT_DIR, exist_ok=True)
    d = load_data(DEFAULT_NPZ, VAL_SRC_NAMES, subsample_rate=args.subsample)
    src = d["src"]; val_src = set(d["_val_src_ids"])
    N = len(src)
    train_idx = [i for i in range(N) if src[i] not in val_src]
    val_idx = [i for i in range(N) if src[i] in val_src]
    print(f"  train tiles: {len(train_idx)}  val tiles: {len(val_idx)}",
          flush=True)

    tr = DataLoader(TileDS(d, train_idx, augment=True),
                    batch_size=args.batch, shuffle=True, num_workers=0)
    va = DataLoader(TileDS(d, val_idx, augment=False),
                    batch_size=args.batch, shuffle=False, num_workers=0)

    # Teacher CNN
    teacher, teacher_variant = _load_teacher(args.teacher_ckpt, DEVICE)
    print(f"  teacher variant: {teacher_variant}  "
          f"params: {count_params(teacher):,}", flush=True)

    # Student CNN
    model = build_variant(args.variant).to(DEVICE)
    print(f"  student variant: {args.variant}  "
          f"params: {count_params(model):,}", flush=True)

    if args.init_ckpt:
        if not os.path.exists(args.init_ckpt):
            raise FileNotFoundError(f"--init-ckpt not found: {args.init_ckpt}")
        ck = torch.load(args.init_ckpt, map_location=DEVICE, weights_only=False)
        model.load_state_dict(ck["backbone_state"])
        print(f"  warm-started student from {args.init_ckpt}", flush=True)

    # LPIPS loss
    lpips_net = None
    if args.lpips_weight > 0:
        import lpips as lpips_lib
        lpips_net = lpips_lib.LPIPS(net="alex").to(DEVICE)
        for p in lpips_net.parameters():
            p.requires_grad_(False)
        lpips_net.eval()
        print(f"  LPIPS (alex) loaded, weight={args.lpips_weight} "
              f"warmup={args.lpips_warmup_epochs}", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    has_rgb = d.get("_has_rgb_target", False)
    if not has_rgb:
        raise RuntimeError("NPZ lacks tgt_rgb; this trainer requires an "
                            "RGB-target dmsr NPZ.")

    def _compute_blend_target(inp, tgt_rgb):
        """inp: (B, 4, H, W) codec planes; tgt_rgb: (B, 3, 4H, 4W) sips RGB.
        Returns blend_target: (B, 3, 4H, 4W) in [0, 1]."""
        with torch.no_grad():
            teacher_pred = teacher(inp).clamp(0, 1)
            blend = blend_guided_torch(
                teacher_pred, tgt_rgb, radius=args.guided_radius,
                eps=args.guided_eps).clamp(0, 1)
        return blend, teacher_pred

    def _eval():
        """Returns (val_psnr_vs_blend, val_lpips_vs_blend, val_psnr_vs_sips)."""
        model.eval()
        tot_psnr_blend, tot_psnr_sips, tot_lp, n = 0.0, 0.0, 0.0, 0
        with torch.no_grad():
            for batch in va:
                inp, tgt = batch[0].to(DEVICE), batch[1].to(DEVICE)
                tgt_rgb = tgt.clamp(0, 1)
                blend, _ = _compute_blend_target(inp, tgt_rgb)
                pred = model(inp).clamp(0, 1)
                mse_b = ((pred - blend) ** 2).mean(dim=[1, 2, 3])
                mse_s = ((pred - tgt_rgb) ** 2).mean(dim=[1, 2, 3])
                tot_psnr_blend += (-10 * torch.log10(
                    mse_b.clamp_min(1e-12))).sum().item()
                tot_psnr_sips += (-10 * torch.log10(
                    mse_s.clamp_min(1e-12))).sum().item()
                if lpips_net is not None:
                    lp = lpips_net(pred * 2 - 1, blend * 2 - 1).flatten()
                    tot_lp += lp.sum().item()
                n += inp.shape[0]
        lp = (tot_lp / n) if (lpips_net is not None and n > 0) else None
        return (tot_psnr_blend / n, tot_psnr_sips / n, lp)

    best_lpips = 1e9; best_psnr = -1e9; best_epoch = -1
    epochs_since_best = 0
    ckpt_path = os.path.join(CKPT_DIR, args.ckpt_name)
    use_lpips_metric = lpips_net is not None
    pb, ps, vlp = _eval()
    print(f"  Initial  val_psnr_vs_blend={pb:.3f}  "
          f"val_psnr_vs_sips={ps:.3f}  "
          f"val_lpips_vs_blend={'%.4f' % vlp if vlp is not None else 'N/A'}",
          flush=True)
    for ep in range(args.epochs):
        if lpips_net is not None:
            if args.lpips_warmup_epochs > 0 and ep < args.lpips_warmup_epochs:
                phase = (ep + 1) / args.lpips_warmup_epochs
                lpips_w_curr = args.lpips_weight * (1 - np.cos(phase * np.pi / 2))
            else:
                lpips_w_curr = args.lpips_weight
        else:
            lpips_w_curr = 0.0
        model.train(); t0 = time.time()
        loss_sum, loss_l1, loss_lp, nb = 0.0, 0.0, 0.0, 0
        for batch in tr:
            inp, tgt = batch[0].to(DEVICE), batch[1].to(DEVICE)
            tgt_rgb = tgt.clamp(0, 1)
            blend, _ = _compute_blend_target(inp, tgt_rgb)
            pred = model(inp).clamp(0, 1)
            l_ms = multiscale_l1(pred, blend)
            l = l_ms
            if lpips_net is not None and lpips_w_curr > 0:
                l_lpips = lpips_net(pred * 2 - 1, blend * 2 - 1).mean()
                l = l + lpips_w_curr * l_lpips
                loss_lp += float(l_lpips.item())
            opt.zero_grad(set_to_none=True); l.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            loss_sum += float(l.item()); loss_l1 += float(l_ms.item()); nb += 1
        sched.step()
        pb, ps, vlp = _eval()
        marker = ""
        improved = (vlp is not None and vlp < best_lpips) if use_lpips_metric \
            else (pb > best_psnr)
        if improved:
            if use_lpips_metric: best_lpips = vlp
            best_psnr = pb; best_epoch = ep + 1
            epochs_since_best = 0
            torch.save({
                "backbone_state": model.state_dict(),
                "variant": args.variant,
                "width": VARIANTS[args.variant]["width"], "depth": 3,
                "raw_norm": RAW_NORM, "residual_scale": 0.0,
                "kind": "demosaic_sr_blend_distill", "epoch": ep + 1,
                "val_psnr_vs_blend": pb, "val_psnr_vs_sips": ps,
                "val_lpips_vs_blend": vlp,
                "teacher_ckpt": args.teacher_ckpt,
                "teacher_variant": teacher_variant,
                "guided_radius": args.guided_radius,
                "guided_eps": args.guided_eps,
                "params": count_params(model),
            }, ckpt_path)
            marker = "  [SAVED]"
        else:
            epochs_since_best += 1
        if lpips_net is not None:
            print(f"  ep {ep+1:3d}/{args.epochs}  loss={loss_sum/nb:.5f}  "
                  f"l1={loss_l1/nb:.5f}  lpips={loss_lp/nb:.5f}  "
                  f"lp_w={lpips_w_curr:.4f}  "
                  f"val_psnr_blend={pb:.3f}  val_lpips_blend={vlp:.4f}  "
                  f"t={time.time()-t0:.1f}s{marker}", flush=True)
        else:
            print(f"  ep {ep+1:3d}/{args.epochs}  loss={loss_sum/nb:.5f}  "
                  f"val_psnr_blend={pb:.3f}  "
                  f"t={time.time()-t0:.1f}s{marker}", flush=True)
        if epochs_since_best >= args.patience and ep + 1 >= 40:
            print(f"  Early stop: no improvement in {args.patience} epochs",
                  flush=True)
            break
    print(f"\n  Best val LPIPS vs blend: {best_lpips:.4f} at epoch {best_epoch}")
    print(f"  Checkpoint: {ckpt_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", type=str, default="bido_4x",
                    choices=["F_ane_dm_sr", "bido_4x",
                             "F_ane_dm_sr_w24", "bido_4x_w24"])
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--patience", type=int, default=30)
    ap.add_argument("--subsample", type=int, default=1)
    ap.add_argument("--ckpt-name", type=str,
                    default="BayInDemosaicOut_4x_AAon_w16_ANE_blend_distill.pt")
    ap.add_argument("--init-ckpt", type=str,
                    default="/Users/dcliftreaves/Documents/Github/gpr/models/"
                            "BayInDemosaicOut_4x_AAon_w16_ANE_lpips.pt")
    ap.add_argument("--teacher-ckpt", type=str,
                    default="/Users/dcliftreaves/Documents/Github/gpr/models/"
                            "BayInDemosaicOut_4x_AAon_w24_ANE.pt")
    ap.add_argument("--guided-radius", type=int, default=8)
    ap.add_argument("--guided-eps", type=float, default=1e-3)
    ap.add_argument("--lpips-weight", type=float, default=0.10)
    ap.add_argument("--lpips-warmup-epochs", type=int, default=5)
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()
