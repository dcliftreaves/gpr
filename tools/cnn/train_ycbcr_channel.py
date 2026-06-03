"""Train a single Y / Cb / Cr channel CNN (PREVIEW_CHANNEL_DECOMP_PLAN
Variant A). Bayer in (4ch half-res), single-channel out (Y or Cb or Cr) at
4x spatial scale.

Three sequential trainings produce three checkpoints that are recombined
at inference via inverse BT.709 to RGB:

  python3 tools/cnn/train_ycbcr_channel.py --variant F_ane_no_sr_w16_y      --channel Y  --ckpt-name F_ane_no_sr_w16_y.pt
  python3 tools/cnn/train_ycbcr_channel.py --variant F_ane_no_sr_w8_chroma  --channel Cb --ckpt-name F_ane_no_sr_w8_chroma_cb.pt
  python3 tools/cnn/train_ycbcr_channel.py --variant F_ane_no_sr_w8_chroma  --channel Cr --ckpt-name F_ane_no_sr_w8_chroma_cr.pt

Loss recipes (from the plan):
  Y:     multiscale_l1(pred_Y, tgt_Y) + 0.10 * LPIPS_alex(pred_Y_3ch, tgt_Y_3ch)
  Cb/Cr: l1(pred, tgt) + 0.10 * charbonnier(pred, tgt; eps=1e-3)

Targets come from `tgt_rgb` (uint8 (H, W, 3) RGB) in the NPZ; we
convert to BT.709 YCbCr at training time. The BT.709 matrix is hard-
coded so inference reuses the same forward / inverse exactly.

Best ckpt is saved by lower val LPIPS for Y; by lower val L1 for chroma
(LPIPS-alex carries no perceptual color signal, per the plan).
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
from torch.utils.data import Dataset, DataLoader

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import build as build_variant, count_params, VARIANTS

# numpy 2.0.2 on Apple Silicon issues spurious "divide by zero" /
# "overflow" / "invalid value" warnings on small float32 matmul (e.g. the
# 3x3 BT.709 colorspace conversion). Output values are correct; we
# verified the per-pixel mapping matches the analytic result.
np.seterr(all="ignore")

RAW_NORM = 16383.0
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
DEFAULT_NPZ = os.environ.get(
    "SUPERRES_NPZ", "/Users/dcliftreaves/gpr_data/tiles_ml2_q3_dec2_dmsr_gate.npz"
)
CKPT_DIR = os.environ.get("CKPT_DIR", "/Users/dcliftreaves/gpr_data")
# Comma-separated; matches train_demosaic_sr.py convention.
VAL_SRC_NAMES = os.environ.get(
    "VAL_SRC_NAMES", os.environ.get("VAL_SRC_NAME", "Z8Z_0067")
)

# BT.709 RGB → YCbCr matrix (full-range, no head/foot room).
# y  =  0.2126 R + 0.7152 G + 0.0722 B
# Cb = -0.1146 R - 0.3854 G + 0.5000 B + 0.5
# Cr =  0.5000 R - 0.4542 G - 0.0458 B + 0.5
# (Inputs and outputs in [0, 1]; the +0.5 offset moves chroma into [0, 1].)
BT709_M = np.array([
    [0.2126,  0.7152,  0.0722],
    [-0.1146, -0.3854, 0.5000],
    [0.5000, -0.4542, -0.0458],
], dtype=np.float32)
BT709_OFFSET = np.array([0.0, 0.5, 0.5], dtype=np.float32)
CHANNEL_IDX = {"Y": 0, "Cb": 1, "Cr": 2}


def rgb_to_ycbcr_chw(rgb_chw: np.ndarray) -> np.ndarray:
    """Input (3, H, W) RGB in [0, 1] → (3, H, W) YCbCr in [0, 1]."""
    hw = rgb_chw.shape[1] * rgb_chw.shape[2]
    flat = rgb_chw.reshape(3, hw).T  # (HW, 3)
    ycc = flat @ BT709_M.T + BT709_OFFSET
    return ycc.T.reshape(3, rgb_chw.shape[1], rgb_chw.shape[2]).astype(np.float32)


def load_data(npz_path, val_src_names, subsample_rate=1, input_mode="planes4x"):
    print(f"  loading {npz_path}...", flush=True)
    t0 = time.time()
    npz = np.load(npz_path, mmap_mode="r", allow_pickle=True)
    src = np.asarray(npz["src"])
    lookup = np.asarray(npz["src_lookup_names"])
    names = [s.decode() if isinstance(s, bytes) else s for s in lookup.tolist()]
    if isinstance(val_src_names, str):
        val_src_names = [n.strip() for n in val_src_names.split(",") if n.strip()]
    val_src_ids = []
    for vname in val_src_names:
        m = [i for i, n in enumerate(names) if n == vname]
        if not m:
            raise RuntimeError(f"VAL_SRC_NAME '{vname}' not in NPZ; got {names[:5]}")
        val_src_ids.append(m[0])
    print(f"  val src ids: {dict(zip(val_src_names, val_src_ids))}", flush=True)
    rng = np.random.RandomState(0)
    keep_mask = np.zeros(len(src), dtype=bool)
    val_set = set(val_src_ids)
    for i in range(len(src)):
        if src[i] in val_set or rng.rand() < (1.0 / subsample_rate):
            keep_mask[i] = True
    print(f"  keeping {keep_mask.sum()} of {len(src)} tiles", flush=True)
    out = {}
    for k in ["codec_R", "codec_G1", "codec_G2", "codec_B"]:
        out[k] = np.asarray(npz[k][keep_mask])
    if input_mode == "mosaic2x":
        if "codec_mosaic" in npz.files:
            out["codec_mosaic"] = np.asarray(npz["codec_mosaic"][keep_mask])
        else:
            # Backward-compatible reconstruction for older sidecars.
            r = out["codec_R"]
            g1 = out["codec_G1"]
            g2 = out["codec_G2"]
            b = out["codec_B"]
            n, h, w = r.shape
            mosaic = np.empty((n, h * 2, w * 2), dtype=r.dtype)
            mosaic[:, 0::2, 0::2] = r
            mosaic[:, 0::2, 1::2] = g1
            mosaic[:, 1::2, 0::2] = g2
            mosaic[:, 1::2, 1::2] = b
            out["codec_mosaic"] = mosaic
    if "tgt_rgb" not in npz.files:
        raise RuntimeError("NPZ is missing tgt_rgb — this trainer needs RGB targets.")
    out["tgt_rgb"] = np.asarray(npz["tgt_rgb"][keep_mask])
    out["src"] = src[keep_mask]
    out["src_lookup_names"] = lookup
    out["_val_src_ids"] = val_src_ids
    print(f"  loaded in {time.time() - t0:.1f}s", flush=True)
    return out


def codec_planes_from_mem(d, idx):
    codec = np.stack([d["codec_R"][idx], d["codec_G1"][idx],
                      d["codec_G2"][idx], d["codec_B"][idx]], 0)
    return codec.astype(np.float32) / RAW_NORM


def codec_mosaic_from_mem(d, idx):
    return d["codec_mosaic"][idx][None].astype(np.float32) / RAW_NORM


def tgt_channel_from_mem(d, idx, channel_idx):
    """Returns (1, H, W) float32 single YCbCr channel in [0, 1]."""
    rgb = d["tgt_rgb"][idx]  # (H, W, 3) uint8
    rgb_chw = np.transpose(rgb, (2, 0, 1)).astype(np.float32) / 255.0
    ycc = rgb_to_ycbcr_chw(rgb_chw)
    return ycc[channel_idx:channel_idx + 1]


class TileDS(Dataset):
    def __init__(self, mem, indices, channel_idx, augment=True, input_mode="planes4x"):
        self.mem = mem
        self.indices = indices
        self.channel_idx = channel_idx
        self.augment = augment
        self.input_mode = input_mode

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        idx = self.indices[i]
        if self.input_mode == "mosaic2x":
            codec = codec_mosaic_from_mem(self.mem, idx)
        else:
            codec = codec_planes_from_mem(self.mem, idx)
        tgt = tgt_channel_from_mem(self.mem, idx, self.channel_idx)
        if self.augment and self.input_mode == "planes4x":
            if np.random.rand() < 0.5:
                codec = codec[:, :, ::-1].copy()
                tgt = tgt[:, :, ::-1].copy()
                # Horizontal flip: swap R↔G1, G2↔B in codec planes; the
                # single-channel target is colorspace-agnostic to flips.
                codec = codec[[1, 0, 3, 2]]
            if np.random.rand() < 0.5:
                codec = codec[:, ::-1, :].copy()
                tgt = tgt[:, ::-1, :].copy()
                codec = codec[[2, 3, 0, 1]]
        codec_t = torch.from_numpy(np.ascontiguousarray(codec)).float()
        tgt_t = torch.from_numpy(np.ascontiguousarray(tgt)).float()
        return codec_t, tgt_t


def multiscale_l1(pred, tgt, weights=(1.0, 0.5, 0.25)):
    losses = [F.l1_loss(pred, tgt) * weights[0]]
    p, t = pred, tgt
    for w in weights[1:]:
        p = F.avg_pool2d(p, 2)
        t = F.avg_pool2d(t, 2)
        losses.append(F.l1_loss(p, t) * w)
    return sum(losses)


def charbonnier(pred, tgt, eps=1e-3):
    return torch.sqrt((pred - tgt) ** 2 + eps * eps).mean()


def _blur5(x):
    return F.avg_pool2d(x, kernel_size=5, stride=1, padding=2)


def highpass_l1(pred, tgt):
    return F.l1_loss(pred - _blur5(pred), tgt - _blur5(tgt))


def gradient_l1(pred, tgt):
    # Forward differences avoid fixed-kernel device/dtype plumbing and are
    # enough to penalize misplaced Y edges/textures.
    px = pred[..., :, 1:] - pred[..., :, :-1]
    tx = tgt[..., :, 1:] - tgt[..., :, :-1]
    py = pred[..., 1:, :] - pred[..., :-1, :]
    ty = tgt[..., 1:, :] - tgt[..., :-1, :]
    return F.l1_loss(px, tx) + F.l1_loss(py, ty)


def center_crop_pair(pred: torch.Tensor, tgt: torch.Tensor, margin: int) -> tuple[torch.Tensor, torch.Tensor]:
    if margin <= 0:
        return pred, tgt
    h, w = pred.shape[-2:]
    if h != tgt.shape[-2] or w != tgt.shape[-1]:
        raise RuntimeError(f"pred/tgt shape mismatch before center crop: {pred.shape} vs {tgt.shape}")
    if 2 * margin >= h or 2 * margin >= w:
        raise RuntimeError(f"--loss-center-margin {margin} too large for output {h}x{w}")
    return pred[..., margin:h - margin, margin:w - margin], tgt[..., margin:h - margin, margin:w - margin]


def train(args):
    channel_idx = CHANNEL_IDX[args.channel]
    print(f"=== Training {args.variant} for channel {args.channel} (idx={channel_idx}) ===")
    print(f"Input mode: {args.input_mode}")
    print(f"Device: {DEVICE}  CKPT_DIR: {CKPT_DIR}  NPZ: {DEFAULT_NPZ}")
    os.makedirs(CKPT_DIR, exist_ok=True)

    d = load_data(DEFAULT_NPZ, VAL_SRC_NAMES, subsample_rate=args.subsample,
                  input_mode=args.input_mode)
    src = d["src"]
    val_src = set(d["_val_src_ids"])
    N = len(src)
    train_idx = [i for i in range(N) if src[i] not in val_src]
    val_idx = [i for i in range(N) if src[i] in val_src]
    print(f"  train tiles: {len(train_idx)}  val tiles: {len(val_idx)}", flush=True)

    select_idx = []
    select_src_names = [n.strip() for n in args.select_src_names.split(",") if n.strip()]
    select_src_ids = []
    if select_src_names:
        names = [s.decode() if isinstance(s, bytes) else s
                 for s in np.asarray(d["src_lookup_names"]).tolist()]
        for sname in select_src_names:
            matches = [i for i, n in enumerate(names) if n == sname]
            if not matches:
                raise RuntimeError(f"--select-src-names '{sname}' not in NPZ; got {names[:5]}")
            select_src_ids.append(matches[0])
        select_set = set(select_src_ids)
        select_idx = [i for i in range(N) if src[i] in select_set]
        print(
            f"  selection src ids: {dict(zip(select_src_names, select_src_ids))} "
            f"tiles={len(select_idx)} metric={args.select_metric}",
            flush=True,
        )

    tr = DataLoader(TileDS(d, train_idx, channel_idx, augment=True,
                           input_mode=args.input_mode),
                    batch_size=args.batch, shuffle=True, num_workers=0)
    va = DataLoader(TileDS(d, val_idx, channel_idx, augment=False,
                           input_mode=args.input_mode),
                    batch_size=args.batch, shuffle=False, num_workers=0)
    sel = None
    if select_idx:
        sel = DataLoader(TileDS(d, select_idx, channel_idx, augment=False,
                                input_mode=args.input_mode),
                         batch_size=args.batch, shuffle=False, num_workers=0)

    model = build_variant(args.variant).to(DEVICE)
    print(f"  Variant: {args.variant}", flush=True)
    print(f"  Params (backbone): {count_params(model):,}", flush=True)
    if args.init_ckpt:
        if not os.path.exists(args.init_ckpt):
            raise FileNotFoundError(f"--init-ckpt not found: {args.init_ckpt}")
        ck = torch.load(args.init_ckpt, map_location=DEVICE, weights_only=False)
        model.load_state_dict(ck["backbone_state"])
        print(f"  warm-started from {args.init_ckpt}", flush=True)

    # LPIPS only for Y channel (no perceptual color signal in alex; plan §A).
    lpips_net = None
    if args.channel == "Y" and args.lpips_weight > 0:
        import lpips as lpips_lib
        lpips_net = lpips_lib.LPIPS(net="alex").to(DEVICE)
        for p in lpips_net.parameters():
            p.requires_grad_(False)
        lpips_net.eval()
        print(f"  LPIPS (alex) loaded, weight={args.lpips_weight}", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    def evaluate_loader(loader):
        model.eval()
        tot_l1 = 0.0
        tot_psnr = 0.0
        tot_lp = 0.0
        n = 0
        with torch.no_grad():
            for inp, tgt in loader:
                inp = inp.to(DEVICE)
                tgt = tgt.to(DEVICE)
                pred = model(inp).clamp(0, 1)
                pred_eval, tgt_eval = center_crop_pair(pred, tgt, args.loss_center_margin)
                tot_l1 += F.l1_loss(pred_eval, tgt_eval, reduction="sum").item() / (
                    pred_eval.shape[1] * pred_eval.shape[2] * pred_eval.shape[3]
                )
                mse = ((pred_eval - tgt_eval) ** 2).mean(dim=[1, 2, 3])
                tot_psnr += (-10 * torch.log10(mse.clamp_min(1e-12))).sum().item()
                if lpips_net is not None:
                    # Broadcast single-channel to 3ch RGB for LPIPS-alex.
                    pred_3 = pred_eval.repeat(1, 3, 1, 1)
                    tgt_3 = tgt_eval.repeat(1, 3, 1, 1)
                    lp = lpips_net(pred_3 * 2 - 1, tgt_3 * 2 - 1).flatten()
                    tot_lp += lp.sum().item()
                n += inp.shape[0]
        return tot_l1 / max(1, n), tot_psnr / max(1, n), (
            tot_lp / n if (lpips_net is not None and n > 0) else None
        )

    def evaluate():
        return evaluate_loader(va)

    best_l1 = 1e9
    best_lpips = 1e9
    best_psnr = -1e9
    best_select_score = 1e9
    best_select_l1 = 1e9
    best_select_psnr = -1e9
    best_select_lpips = None
    best_epoch = -1
    epochs_since_best = 0
    ckpt_path = os.path.join(CKPT_DIR, args.ckpt_name)
    last_ckpt_path = os.path.join(CKPT_DIR, args.save_last_name or args.ckpt_name)

    use_lpips_metric = (args.channel == "Y" and lpips_net is not None)

    l1_init, psnr_init, lp_init = evaluate()
    init_msg = f"  Initial  val_l1={l1_init:.5f}  val_psnr={psnr_init:.3f} dB"
    if lp_init is not None:
        init_msg += f"  val_lpips={lp_init:.4f}"
    print(init_msg, flush=True)

    for ep in range(args.epochs):
        model.train()
        t0 = time.time()
        loss_sum = 0.0
        nb = 0
        for inp, tgt in tr:
            inp = inp.to(DEVICE)
            tgt = tgt.to(DEVICE)
            pred = model(inp).clamp(0, 1)
            pred_loss, tgt_loss = center_crop_pair(pred, tgt, args.loss_center_margin)
            if args.channel == "Y":
                l_task = multiscale_l1(pred_loss, tgt_loss)
                if args.hf_weight > 0:
                    l_task = l_task + args.hf_weight * highpass_l1(pred_loss, tgt_loss)
                if args.grad_weight > 0:
                    l_task = l_task + args.grad_weight * gradient_l1(pred_loss, tgt_loss)
            else:
                # Chroma: L1 + 0.10 * Charbonnier (robust on outliers, smooth
                # gradient at the origin so optimizer doesn't oscillate).
                l_task = F.l1_loss(pred_loss, tgt_loss) + 0.10 * charbonnier(pred_loss, tgt_loss)
            l = l_task
            if lpips_net is not None and args.lpips_weight > 0:
                pred_3 = pred_loss.repeat(1, 3, 1, 1)
                tgt_3 = tgt_loss.repeat(1, 3, 1, 1)
                l_lpips = lpips_net(pred_3 * 2 - 1, tgt_3 * 2 - 1).mean()
                l = l + args.lpips_weight * l_lpips
            opt.zero_grad(set_to_none=True)
            l.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            loss_sum += float(l.item())
            nb += 1
        sched.step()

        l1, psnr, lp = evaluate()
        select_l1 = select_psnr = select_lp = None
        select_score = None
        if sel is not None:
            select_l1, select_psnr, select_lp = evaluate_loader(sel)
            if args.select_metric == "lpips":
                if select_lp is None:
                    raise RuntimeError("--select-metric lpips requires LPIPS to be enabled")
                select_score = select_lp
            elif args.select_metric == "l1":
                select_score = select_l1
            elif args.select_metric == "lpips_plus_ms_l1":
                if select_lp is None:
                    raise RuntimeError("--select-metric lpips_plus_ms_l1 requires LPIPS to be enabled")
                select_score = select_lp + select_l1
            else:
                raise RuntimeError(f"unsupported --select-metric {args.select_metric}")
        if select_score is not None:
            improved = select_score < best_select_score
        elif use_lpips_metric:
            improved = lp is not None and lp < best_lpips
        else:
            improved = l1 < best_l1
        marker = ""
        if improved:
            best_l1 = l1
            best_psnr = psnr
            if lp is not None:
                best_lpips = lp
            if select_score is not None:
                best_select_score = select_score
                best_select_l1 = select_l1
                best_select_psnr = select_psnr
                best_select_lpips = select_lp
            best_epoch = ep + 1
            epochs_since_best = 0
            torch.save({
                "backbone_state": model.state_dict(),
                "variant": args.variant,
                "channel": args.channel,
                "channel_idx": channel_idx,
                "matrix": "BT709",
                "width": VARIANTS[args.variant]["width"],
                "raw_norm": RAW_NORM,
                "residual_scale": 0.0,
                "kind": f"ycbcr_decomp_{args.channel.lower()}",
                "input_mode": args.input_mode,
                "hf_weight": args.hf_weight if args.channel == "Y" else 0.0,
                "grad_weight": args.grad_weight if args.channel == "Y" else 0.0,
                "loss_center_margin": args.loss_center_margin,
                "epoch": ep + 1,
                "val_l1": l1,
                "val_psnr": psnr,
                "val_lpips": lp,
                "select_src_names": select_src_names,
                "select_metric": args.select_metric if select_src_names else None,
                "select_score": select_score,
                "select_l1": select_l1,
                "select_psnr": select_psnr,
                "select_lpips": select_lp,
                "params": count_params(model),
            }, ckpt_path)
            marker = "  [SAVED]"
        else:
            epochs_since_best += 1

        line = (f"  ep {ep+1:3d}/{args.epochs}  loss={loss_sum/nb:.5f}  "
                f"val_l1={l1:.5f}  val_psnr={psnr:.3f}")
        if lp is not None:
            line += f"  val_lpips={lp:.4f}"
        if select_score is not None:
            line += f"  select_{args.select_metric}={select_score:.4f}"
            if select_lp is not None:
                line += f"  select_lpips={select_lp:.4f}"
        line += f"  t={time.time()-t0:.1f}s{marker}"
        print(line, flush=True)

        if epochs_since_best >= args.patience and ep + 1 >= 40:
            print(f"  Early stop: no improvement in {args.patience} epochs", flush=True)
            break
    if args.save_last:
        torch.save({
            "backbone_state": model.state_dict(),
            "variant": args.variant,
            "channel": args.channel,
            "channel_idx": channel_idx,
            "matrix": "BT709",
            "width": VARIANTS[args.variant]["width"],
            "raw_norm": RAW_NORM,
            "residual_scale": 0.0,
            "kind": f"ycbcr_decomp_{args.channel.lower()}",
            "input_mode": args.input_mode,
            "hf_weight": args.hf_weight if args.channel == "Y" else 0.0,
            "grad_weight": args.grad_weight if args.channel == "Y" else 0.0,
            "loss_center_margin": args.loss_center_margin,
            "epoch": ep + 1,
            "val_l1": l1,
            "val_psnr": psnr,
            "val_lpips": lp,
            "select_src_names": select_src_names,
            "select_metric": args.select_metric if select_src_names else None,
            "select_score": select_score,
            "select_l1": select_l1,
            "select_psnr": select_psnr,
            "select_lpips": select_lp,
            "params": count_params(model),
            "save_policy": "last",
        }, last_ckpt_path)
        print(f"  Last checkpoint: {last_ckpt_path}")

    print(f"\n  Best at epoch {best_epoch}:")
    print(f"    val_l1={best_l1:.5f}  val_psnr={best_psnr:.3f}", end="")
    if use_lpips_metric:
        print(f"  val_lpips={best_lpips:.4f}")
    else:
        print()
    if select_src_names:
        print(
            f"    select_{args.select_metric}={best_select_score:.4f}  "
            f"select_l1={best_select_l1:.5f}  select_psnr={best_select_psnr:.3f}",
            end="",
        )
        if best_select_lpips is not None:
            print(f"  select_lpips={best_select_lpips:.4f}")
        else:
            print()
    print(f"  Checkpoint: {ckpt_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True,
                    choices=["F_ane_no_sr_w16_y", "F_ane_no_sr_w24_y",
                             "F_ane_no_sr_w32_y", "F_ane_no_sr_w32_y_lk7",
                             "F_ane_mosaic_w32_y", "F_ane_mosaic_w48_y",
                             "F_ane_no_sr_w8_chroma"])
    ap.add_argument("--channel", required=True, choices=["Y", "Cb", "Cr"])
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--patience", type=int, default=30)
    ap.add_argument("--subsample", type=int, default=1)
    ap.add_argument("--input-mode", choices=["planes4x", "mosaic2x"], default="planes4x",
                    help="planes4x uses 4 packed Bayer phase planes and a 4x Y head; "
                         "mosaic2x uses one decoded Bayer mosaic channel and a 2x Y head.")
    ap.add_argument("--ckpt-name", type=str, required=True)
    ap.add_argument("--init-ckpt", type=str, default=None,
                    help="Optional checkpoint to warm-start from.")
    ap.add_argument("--save-last", action="store_true",
                    help="Also write the final epoch checkpoint.")
    ap.add_argument("--save-last-name", type=str, default=None,
                    help="Filename for --save-last. Defaults to --ckpt-name.")
    ap.add_argument("--lpips-weight", type=float, default=0.10,
                    help="LPIPS-alex weight for Y channel; ignored for chroma.")
    ap.add_argument("--hf-weight", type=float, default=0.0,
                    help="High-pass L1 weight for Y channel; ignored for chroma.")
    ap.add_argument("--grad-weight", type=float, default=0.0,
                    help="Gradient L1 weight for Y channel; ignored for chroma.")
    ap.add_argument("--loss-center-margin", type=int, default=0,
                    help="Ignore this many output pixels at every tile edge for "
                         "loss, validation, LPIPS, and checkpoint selection. "
                         "Use with larger training tiles to make the model see "
                         "context while optimizing the center-valid region.")
    ap.add_argument("--select-src-names", type=str, default="",
                    help="Optional comma-separated source names used only for "
                         "checkpoint selection. These tiles are evaluated even "
                         "if they are part of the training split.")
    ap.add_argument("--select-metric", choices=["lpips", "l1", "lpips_plus_ms_l1"],
                    default="lpips",
                    help="Metric used with --select-src-names.")
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()
