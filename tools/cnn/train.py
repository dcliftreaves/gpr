"""Train ANE-friendly F variants.

  --variant F_ane        — 2x super-res (matches F_aa_on architecture's role)
  --variant F_ane_no_sr  — 1x clean (matches BIBO_1x_AAon_w16's role)

Same data, loss, validation methodology as train_superres_F_aa_on.py and
train_superres_F_no_sr_aa_on.py. The only thing that differs is the model
class (uses model_F_ane.NAFUNetANE with BN + SiLU in place of LN + SimpleGate).

Tile data:
  /Volumes/OWC_8TB/gpr_cnn/tiles_superres_dense.npz  (M3 path)
  /Users/dcliftreaves/gpr_data/gpr_cnn/tiles_superres_dense.npz  (M5 path, after rsync)

Held-out val: Z8_ISO64 (single source) — kept consistent with the F/BIBO trainers
so val PSNR is directly comparable to those reference numbers.
"""
import os, sys, time, argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader

# Avoid the libomp double-load OMP warning when conda + pip overlap.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import build as build_variant, build_lk, count_params

RESIDUAL_SCALE = 0.01
RAW_NORM = 16383.0
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

# Allow override via env. Default to whichever path exists.
def default_npz():
    candidates = [
        os.environ.get("SUPERRES_NPZ"),
        "/Volumes/OWC_8TB/gpr_cnn/tiles_superres_dense.npz",
        "/Users/dcliftreaves/gpr_data/gpr_cnn/tiles_superres_dense.npz",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return candidates[1]

CKPT_DIR = os.environ.get(
    "CKPT_DIR",
    "/Users/dcliftreaves/dering_proto_v2/checkpoints"
)


ROT_PERMS = {
    0: [0, 1, 2, 3],
    1: [1, 3, 0, 2],
    2: [3, 2, 1, 0],
    3: [2, 0, 3, 1],
}


class FANE(nn.Module):
    """ANE-friendly F wrapper. 2x mode uses bicubic baseline + residual (same as F).
    1x mode uses identity baseline + residual (same as BIBO_1x)."""
    def __init__(self, variant="F_ane", dw_kernel=3):
        super().__init__()
        if dw_kernel and dw_kernel > 3:
            self.backbone = build_lk(variant, dw_kernel=dw_kernel)
        else:
            self.backbone = build_variant(variant)
        self.sr2x = self.backbone.sr
        self.residual_scale = RESIDUAL_SCALE

    def forward(self, x):
        if self.sr2x:
            baseline = F.interpolate(x, scale_factor=2, mode="bicubic", align_corners=False)
            residual = self.backbone(x)
            return (baseline + self.residual_scale * residual).clamp(0, 1)
        else:
            residual = self.backbone(x)
            return (x + self.residual_scale * residual).clamp(0, 1)


def load_data(npz_path, target_val_src_name="Z8_ISO64", subsample_rate=1):
    print(f"  loading {npz_path} (subsample 1/{subsample_rate}) ...", flush=True)
    t0 = time.time()
    npz = np.load(npz_path, mmap_mode="r", allow_pickle=True)
    src = np.asarray(npz["src"])
    lookup = np.asarray(npz["src_lookup_names"])
    names = [s.decode() if isinstance(s, bytes) else s for s in lookup.tolist()]
    val_match = [i for i, n in enumerate(names) if n == target_val_src_name]
    if not val_match:
        raise RuntimeError(f"Held-out '{target_val_src_name}' not in names; got {names[:5]}")
    val_src_id = val_match[0]

    rng = np.random.RandomState(0)
    keep_mask = np.zeros(len(src), dtype=bool)
    for i in range(len(src)):
        if src[i] == val_src_id:
            keep_mask[i] = True
        elif rng.rand() < (1.0 / subsample_rate):
            keep_mask[i] = True
    print(f"  keeping {keep_mask.sum()} of {len(src)} tiles", flush=True)

    out = {}
    for k in ["codec_R", "codec_G1", "codec_G2", "codec_B",
              "tgt_R", "tgt_G1", "tgt_G2", "tgt_B"]:
        v = np.asarray(npz[k][keep_mask])
        out[k] = v
    out["src"] = src[keep_mask]
    out["_val_src_id"] = val_src_id
    print(f"  loaded in {time.time()-t0:.1f}s", flush=True)
    return out


def planes_from_mem(d, idx):
    codec = np.stack([
        d["codec_R"][idx], d["codec_G1"][idx],
        d["codec_G2"][idx], d["codec_B"][idx]], axis=0).astype(np.float32) / RAW_NORM
    tgt = np.stack([
        d["tgt_R"][idx], d["tgt_G1"][idx],
        d["tgt_G2"][idx], d["tgt_B"][idx]], axis=0).astype(np.float32) / RAW_NORM
    return codec, tgt


def rot90_4plane(arr, k):
    if k == 0:
        return arr
    rot = np.rot90(arr, k=k, axes=(-2, -1)).copy()
    return rot[ROT_PERMS[k], :, :]


class TileDS(Dataset):
    def __init__(self, mem, indices, augment=True):
        self.mem = mem; self.indices = indices; self.augment = augment

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        idx = self.indices[i]
        codec, tgt = planes_from_mem(self.mem, idx)
        if self.augment:
            if np.random.rand() < 0.5:
                codec = codec[:, :, ::-1].copy(); tgt = tgt[:, :, ::-1].copy()
                codec = codec[[1, 0, 3, 2], :, :]; tgt = tgt[[1, 0, 3, 2], :, :]
            if np.random.rand() < 0.5:
                codec = codec[:, ::-1, :].copy(); tgt = tgt[:, ::-1, :].copy()
                codec = codec[[2, 3, 0, 1], :, :]; tgt = tgt[[2, 3, 0, 1], :, :]
            k = int(np.random.randint(0, 4))
            if k != 0:
                codec = rot90_4plane(codec, k)
                tgt = rot90_4plane(tgt, k)
        return (torch.from_numpy(np.ascontiguousarray(codec)).float(),
                torch.from_numpy(np.ascontiguousarray(tgt)).float())


def downsample_tgt_to_codec_dims(tgt, ref=None):
    """For 1x training: legacy NPZs store tgt at 2x codec dims (super-res
    tile layout), so the 1x model trains against an averaged-down target.
    For new native-1x NPZs (ML-2 q=3 retrain), codec and tgt are at the
    same dims; skip the downsample if shapes already match the model
    output `ref`."""
    if ref is not None and tgt.shape[-1] == ref.shape[-1]:
        return tgt
    return F.interpolate(tgt, scale_factor=0.5, mode="area")


# μ-law (Hanji et al. SIGGRAPH Asia 2024, arxiv 2312.03640): tone-mapped
# domain L1 outperforms linear L1 by 2-9 dB on RAW restoration. τ(x) =
# sign(x) · log(1 + μ·|x|) / log(1 + μ) with μ=5000. Differentiable;
# autograd handles the inverse implicitly because we apply τ symmetrically
# to pred and target.
_MU = 5000.0


def mu_law(x):
    return torch.sign(x) * torch.log1p(_MU * x.abs()) / float(np.log1p(_MU))


def _apply_loss_domain(pred, tgt, domain):
    if domain == "linear":
        return pred, tgt
    if domain == "mu_law":
        return mu_law(pred), mu_law(tgt)
    raise ValueError(f"unknown loss_domain: {domain}")


def multiscale_l1(pred, tgt, weights=(1.0, 0.5, 0.25), domain="linear"):
    p_d, t_d = _apply_loss_domain(pred, tgt, domain)
    losses = [F.l1_loss(p_d, t_d) * weights[0]]
    p = pred; t = tgt
    for w in weights[1:]:
        p = F.avg_pool2d(p, 2); t = F.avg_pool2d(t, 2)
        p_d, t_d = _apply_loss_domain(p, t, domain)
        losses.append(F.l1_loss(p_d, t_d) * w)
    return sum(losses)


_msssim_module = {"fn": None}
def _get_msssim():
    if _msssim_module["fn"] is None:
        from pytorch_msssim import ms_ssim as _ms
        _msssim_module["fn"] = _ms
    return _msssim_module["fn"]


def training_loss(pred, tgt, loss_domain="linear"):
    """Composite loss. MSSSIM_LOSS_WEIGHT env (default 0) blends in a
    (1 - MS-SSIM) term to directly optimize the metric the gate uses.
    Tiles are 128x128 — MS-SSIM needs ≥88 px on the smallest scale, so
    we use win_size=7 (covers up to 4 scales).

    loss_domain="mu_law" applies the Hanji 2024 μ-law tone-map to BOTH
    pred and target before the L1; MS-SSIM is unaffected (operates on
    the clamped linear pixels because the metric is calibrated to that
    space)."""
    l1 = multiscale_l1(pred, tgt, domain=loss_domain)
    w = float(os.environ.get("MSSSIM_LOSS_WEIGHT", "0"))
    if w <= 0.0:
        return l1
    # 4-plane bayer; compute MS-SSIM per channel and average. pytorch_msssim
    # expects [B, C, H, W] with values in [0, 1].
    ms = _get_msssim()
    ssim_val = ms(pred.clamp(0, 1), tgt.clamp(0, 1), data_range=1.0, win_size=7)
    return (1.0 - w) * l1 + w * (1.0 - ssim_val)


def train(args):
    NPZ = default_npz()
    print(f"=== Training {args.variant} (ANE-friendly F) — AA-ON ===")
    print(f"Device: {DEVICE}  CKPT_DIR: {CKPT_DIR}  NPZ: {NPZ}")
    os.makedirs(CKPT_DIR, exist_ok=True)

    val_src = os.environ.get("VAL_SRC_NAME", "Z8_ISO64")
    d = load_data(NPZ, target_val_src_name=val_src,
                  subsample_rate=args.subsample)
    N = len(d["src"]); src = d["src"]
    val_src = {d["_val_src_id"]}
    train_idx = [i for i in range(N) if src[i] not in val_src]
    val_idx = [i for i in range(N) if src[i] in val_src]
    print(f"  unique src ids: {len(set(src.tolist()))}")
    print(f"  train tiles: {len(train_idx)}  val tiles: {len(val_idx)}")

    tr = DataLoader(TileDS(d, train_idx, augment=True), batch_size=args.batch,
                    shuffle=True, num_workers=0, drop_last=True)
    va = DataLoader(TileDS(d, val_idx, augment=False), batch_size=args.batch,
                    shuffle=False, num_workers=0)

    model = FANE(variant=args.variant, dw_kernel=args.dw_kernel).to(DEVICE)
    print(f"  Params (backbone): {count_params(model.backbone):,}")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    def evaluate():
        model.eval()
        tot_b = 0.0; tot_a = 0.0; n = 0
        with torch.no_grad():
            for inp, tgt in va:
                inp = inp.to(DEVICE); tgt = tgt.to(DEVICE)
                if model.sr2x:
                    base = F.interpolate(inp, scale_factor=2, mode="bicubic",
                                         align_corners=False).clamp(0, 1)
                    cleaned = model(inp)
                    tgt_use = tgt
                else:
                    base = inp.clamp(0, 1)
                    cleaned = model(inp)
                    tgt_use = downsample_tgt_to_codec_dims(tgt, ref=cleaned)
                mse_b = ((base - tgt_use) ** 2).mean(dim=[1, 2, 3])
                mse_a = ((cleaned - tgt_use) ** 2).mean(dim=[1, 2, 3])
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
            if model.sr2x:
                pred = model(inp); tgt_use = tgt
            else:
                pred = model(inp); tgt_use = downsample_tgt_to_codec_dims(tgt, ref=pred)
            l = training_loss(pred, tgt_use, loss_domain=args.loss_domain)
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
                "backbone_state": model.backbone.state_dict(),
                "variant": args.variant,
                "width": 16,
                "depth": 3,
                "residual_scale": RESIDUAL_SCALE,
                "raw_norm": RAW_NORM,
                "kind": "superres" if model.sr2x else "denoise",
                "epoch": ep + 1,
                "val_psnr_base": pb,
                "val_psnr_model": pa,
                "params": count_params(model.backbone),
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
    ap.add_argument("--variant", choices=["F_ane", "F_ane_no_sr", "F_ane_w24", "F_ane_w24_no_sr", "F_ane_no_sr_w24", "F_ane_w32", "F_ane_w32_no_sr", "F_ane_no_sr_w32"], required=True)
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--patience", type=int, default=25)
    ap.add_argument("--subsample", type=int, default=1)
    ap.add_argument("--ckpt-name", type=str, default=None)
    ap.add_argument("--dw-kernel", type=int, default=3,
                    help="dw kernel size for NAFBlock (3=default; 7 uses large-kernel variant)")
    ap.add_argument("--loss-domain", choices=["linear", "mu_law"], default="linear",
                    help="Apply tone-map to pred+target before L1. "
                         "mu_law = Hanji et al. SIGGRAPH Asia 2024 (μ=5000).")
    args = ap.parse_args()
    if args.ckpt_name is None:
        args.ckpt_name = (
            "BayInBayOut_2x_AAon_w16_ANE.pt" if args.variant == "F_ane"
            else "BayInBayOut_1x_AAon_w16_ANE.pt"
        )
    train(args)


if __name__ == "__main__":
    main()
