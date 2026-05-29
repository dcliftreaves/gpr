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
from model import build as build_variant, count_params, VARIANTS

RAW_NORM = 16383.0
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
DEFAULT_NPZ = os.environ.get(
    "SUPERRES_NPZ", "/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_combined.npz"
)
CKPT_DIR = os.environ.get("CKPT_DIR",
                          "/Users/dcliftreaves/Documents/Github/gpr/models")
# Comma-separated list of source-image names to use as validation. Multiple
# entries means early-stop tracks the AVERAGE val PSNR across all of them,
# so the saved checkpoint generalizes instead of overfitting one image.
VAL_SRC_NAMES = os.environ.get("VAL_SRC_NAMES",
                                os.environ.get("VAL_SRC_NAME", "Z8Z_0067"))


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


def load_data(npz_path, val_src_names, subsample_rate=1):
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
    # Phase B distillation target (optional): Restormer-cleaned RGB.
    # Optionally accompanied by tgt_rgb_teacher_mask (1 = computed teacher,
    # 0 = fallback to tgt_rgb): for stride-subsampled teacher precomputes,
    # this lets the trainer apply the β loss only on the kept subset.
    if "tgt_rgb_teacher" in npz.files:
        out["tgt_rgb_teacher"] = np.asarray(npz["tgt_rgb_teacher"][keep_mask])
        out["_has_teacher_target"] = True
        if "tgt_rgb_teacher_mask" in npz.files:
            out["tgt_rgb_teacher_mask"] = np.asarray(
                npz["tgt_rgb_teacher_mask"][keep_mask])
            valid = int(out["tgt_rgb_teacher_mask"].sum())
            print(f"  using tgt_rgb_teacher (Restormer distillation target, "
                  f"{valid}/{len(out['tgt_rgb_teacher_mask'])} valid)",
                  flush=True)
        else:
            out["tgt_rgb_teacher_mask"] = np.ones(
                (len(out["tgt_rgb_teacher"]),), dtype=np.uint8)
            print(f"  using tgt_rgb_teacher (no mask, assuming all valid)",
                  flush=True)
    else:
        out["_has_teacher_target"] = False
    out["src"] = src[keep_mask]
    out["_val_src_ids"] = val_src_ids
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


def tgt_rgb_teacher_from_mem(d, idx):
    """Returns (3, H, W) float32 RGB in [0, 1] from teacher field (uint8)."""
    rgb = d["tgt_rgb_teacher"][idx]                              # (H, W, 3) uint8
    return np.transpose(rgb, (2, 0, 1)).astype(np.float32) / 255.0


class TileDS(Dataset):
    def __init__(self, mem, indices, augment=True,
                 exposure_aug_prob=0.0, exposure_aug_range=4.0):
        self.mem = mem; self.indices = indices; self.augment = augment
        self.has_rgb = mem.get("_has_rgb_target", False)
        self.has_teacher = mem.get("_has_teacher_target", False)
        # Random-exposure augmentation. With probability `exposure_aug_prob`,
        # multiply BOTH input (codec planes) AND target (tgt_rgb, optional
        # teacher) by a log-uniform factor f ∈ [1/R, R]. This teaches the
        # model brightness invariance — works around a brightness-skewed
        # corpus without needing to rebalance the dataset (Real-ESRGAN
        # degradation-pipeline pattern; Hanji 2024 sec 4.2). Symmetric
        # application preserves the codec→clean mapping; only the absolute
        # operating brightness shifts. Disabled by default (prob=0).
        self.exposure_aug_prob = float(exposure_aug_prob)
        self.exposure_aug_log_range = float(np.log2(max(exposure_aug_range, 1.0)))
    def __len__(self): return len(self.indices)
    def __getitem__(self, i):
        idx = self.indices[i]
        codec = codec_planes_from_mem(self.mem, idx)
        tgt = tgt_rgb_from_mem(self.mem, idx)
        tgt_teacher = tgt_rgb_teacher_from_mem(self.mem, idx) \
            if self.has_teacher else None
        teacher_mask = (int(self.mem["tgt_rgb_teacher_mask"][idx])
                        if self.has_teacher else 0)
        if self.augment:
            if np.random.rand() < 0.5:
                codec = codec[:, :, ::-1].copy(); tgt = tgt[:, :, ::-1].copy()
                # Codec channel swap on horizontal flip: R↔G1, G2↔B
                codec = codec[[1, 0, 3, 2]]
                # RGB target: horizontal flip is just spatial; channel order unchanged
                if tgt_teacher is not None:
                    tgt_teacher = tgt_teacher[:, :, ::-1].copy()
            if np.random.rand() < 0.5:
                codec = codec[:, ::-1, :].copy(); tgt = tgt[:, ::-1, :].copy()
                codec = codec[[2, 3, 0, 1]]
                if tgt_teacher is not None:
                    tgt_teacher = tgt_teacher[:, ::-1, :].copy()
            # Random-exposure augmentation (after flips so flips are
            # exposure-independent; symmetric on input + targets so the
            # codec→clean relationship is preserved).
            if (self.exposure_aug_prob > 0.0
                    and np.random.rand() < self.exposure_aug_prob):
                log_f = np.random.uniform(-self.exposure_aug_log_range,
                                          self.exposure_aug_log_range)
                f = float(2.0 ** log_f)
                # Both codec and tgt_rgb live in [0, 1] (codec divided by
                # RAW_NORM=16383; tgt_rgb divided by 255). Multiplying by
                # f then clipping to [0, 1] is equivalent to "clip to
                # sensor max" in the sensor-domain framing.
                codec = np.clip(codec * f, 0.0, 1.0).astype(codec.dtype)
                tgt = np.clip(tgt * f, 0.0, 1.0).astype(tgt.dtype)
                if tgt_teacher is not None:
                    tgt_teacher = np.clip(tgt_teacher * f, 0.0, 1.0).astype(
                        tgt_teacher.dtype)
        codec_t = torch.from_numpy(np.ascontiguousarray(codec)).float()
        tgt_t = torch.from_numpy(np.ascontiguousarray(tgt)).float()
        if tgt_teacher is not None:
            teacher_t = torch.from_numpy(np.ascontiguousarray(tgt_teacher)).float()
            mask_t = torch.tensor(float(teacher_mask), dtype=torch.float32)
            return codec_t, tgt_t, teacher_t, mask_t
        return codec_t, tgt_t


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
    d = load_data(DEFAULT_NPZ, VAL_SRC_NAMES, subsample_rate=args.subsample)
    src = d["src"]; val_src = set(d["_val_src_ids"])
    N = len(src)
    train_idx = [i for i in range(N) if src[i] not in val_src]
    val_idx   = [i for i in range(N) if src[i] in val_src]
    print(f"  train tiles: {len(train_idx)}  val tiles: {len(val_idx)}", flush=True)
    tr = DataLoader(TileDS(d, train_idx, augment=True,
                           exposure_aug_prob=args.exposure_aug_prob,
                           exposure_aug_range=args.exposure_aug_range),
                    batch_size=args.batch,
                    shuffle=True,  num_workers=0)
    va = DataLoader(TileDS(d, val_idx,   augment=False), batch_size=args.batch,
                    shuffle=False, num_workers=0)
    # Per-source val DataLoaders: enables Phase B per-image LPIPS tracking
    # (Z8Z_0067 non-regression bound is per-image, not mean).
    src_id_to_name = {}
    if isinstance(VAL_SRC_NAMES, str):
        _names = [n.strip() for n in VAL_SRC_NAMES.split(",") if n.strip()]
    else:
        _names = list(VAL_SRC_NAMES)
    for sid, sname in zip(d["_val_src_ids"], _names):
        src_id_to_name[sid] = sname
    val_idx_by_src = {sid: [i for i in val_idx if src[i] == sid]
                      for sid in d["_val_src_ids"]}
    va_per_src = {sid: DataLoader(TileDS(d, idxs, augment=False),
                                  batch_size=args.batch, shuffle=False,
                                  num_workers=0)
                  for sid, idxs in val_idx_by_src.items() if idxs}
    model = build_variant(args.variant).to(DEVICE)
    print(f"  Variant: {args.variant}", flush=True)
    print(f"  Params (backbone): {count_params(model):,}", flush=True)

    # Optional: warm-start from an existing checkpoint (Phase A fine-tune).
    if args.init_ckpt:
        if not os.path.exists(args.init_ckpt):
            raise FileNotFoundError(f"--init-ckpt not found: {args.init_ckpt}")
        ck = torch.load(args.init_ckpt, map_location=DEVICE, weights_only=False)
        model.load_state_dict(ck["backbone_state"])
        print(f"  warm-started from {args.init_ckpt}", flush=True)

    # Optional: LPIPS-aware loss term (Phase A fine-tune).
    lpips_net = None
    if args.lpips_weight > 0:
        import lpips as lpips_lib
        lpips_net = lpips_lib.LPIPS(net="alex").to(DEVICE)
        for p in lpips_net.parameters():
            p.requires_grad_(False)
        lpips_net.eval()
        print(f"  LPIPS (alex) loaded, weight={args.lpips_weight} "
              f"warmup={args.lpips_warmup_epochs} epochs", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)

    has_rgb = d.get("_has_rgb_target", False)
    has_teacher = d.get("_has_teacher_target", False)

    def _unpack(batch):
        # Dataloader returns (codec, tgt) when no teacher,
        # else (codec, tgt, teacher, teacher_valid_mask_scalar).
        if has_teacher:
            return batch[0], batch[1], batch[2], batch[3]
        return batch[0], batch[1], None, None

    def _eval_loader(loader):
        """Returns (base_psnr_sum, model_psnr_sum, lpips_sum, n) for a loader.
        lpips_sum is None if LPIPS net unavailable."""
        tot_b, tot_a, tot_lp, n = 0.0, 0.0, 0.0, 0
        with torch.no_grad():
            for batch in loader:
                inp, tgt, _, _ = _unpack(batch)
                inp = inp.to(DEVICE); tgt = tgt.to(DEVICE)
                if has_rgb:
                    tgt_rgb = tgt.clamp(0, 1)
                else:
                    tgt_rgb = bayer_4plane_to_rgb(tgt).clamp(0, 1)
                codec_rgb_lo = bayer_4plane_to_rgb(inp).clamp(0, 1)
                base = F.interpolate(codec_rgb_lo, scale_factor=2, mode="bicubic",
                                     align_corners=False).clamp(0, 1)
                pred = model(inp).clamp(0, 1)
                mse_b = ((base - tgt_rgb) ** 2).mean(dim=[1, 2, 3])
                mse_a = ((pred - tgt_rgb) ** 2).mean(dim=[1, 2, 3])
                tot_b += (-10 * torch.log10(mse_b.clamp_min(1e-12))).sum().item()
                tot_a += (-10 * torch.log10(mse_a.clamp_min(1e-12))).sum().item()
                if lpips_net is not None:
                    lp = lpips_net(pred * 2 - 1, tgt_rgb * 2 - 1).flatten()
                    tot_lp += lp.sum().item()
                n += inp.shape[0]
        lpm = tot_lp if lpips_net is not None else None
        return tot_b, tot_a, lpm, n

    def evaluate():
        """Returns (base_psnr, model_psnr, model_lpips_mean, per_src_lpips_dict).
        model_lpips_mean and per_src dict are None when LPIPS not loaded."""
        model.eval()
        tot_b, tot_a, tot_lp, n = _eval_loader(va)
        lpm = (tot_lp / n) if (lpips_net is not None and n > 0) else None
        per_src = None
        if lpips_net is not None:
            per_src = {}
            for sid, loader in va_per_src.items():
                _, _, lpsum, npr = _eval_loader(loader)
                if npr > 0 and lpsum is not None:
                    per_src[src_id_to_name.get(sid, str(sid))] = lpsum / npr
        return tot_b / n, tot_a / n, lpm, per_src

    best_gain = -1e9; best_after = -1e9; best_lpips = 1e9; best_epoch = -1
    epochs_since_best = 0
    ckpt_path = os.path.join(CKPT_DIR, args.ckpt_name)
    pb, pa, vlp, vlp_per_src = evaluate()
    # When LPIPS net is loaded, track best by LOWER val-LPIPS (perceptual focus).
    # Without LPIPS net, track best by val-PSNR gain as before.
    use_lpips_metric = lpips_net is not None

    def _fmt_per_src(d):
        if not d:
            return ""
        return "  per-src LPIPS: " + " ".join(f"{k}={v:.4f}" for k, v in d.items())

    if use_lpips_metric:
        print(f"  Initial  base PSNR={pb:.3f}  model PSNR={pa:.3f}  "
              f"gain={pa-pb:+.3f} dB  val LPIPS={vlp:.4f}"
              f"{_fmt_per_src(vlp_per_src)}", flush=True)
    else:
        print(f"  Initial  base PSNR={pb:.3f}  model PSNR={pa:.3f}  gain={pa-pb:+.3f} dB",
              flush=True)
    for ep in range(args.epochs):
        # Cosine warmup of LPIPS weight (0 → full over `lpips_warmup_epochs`).
        if lpips_net is not None:
            if args.lpips_warmup_epochs > 0 and ep < args.lpips_warmup_epochs:
                # Cosine ramp from 0 to lpips_weight
                phase = (ep + 1) / args.lpips_warmup_epochs   # 1/W .. 1
                lpips_w_curr = args.lpips_weight * (1 - np.cos(phase * np.pi / 2))
            else:
                lpips_w_curr = args.lpips_weight
        else:
            lpips_w_curr = 0.0
        model.train(); t0 = time.time(); loss_sum = 0.0; loss_l1 = 0.0; loss_lp = 0.0
        loss_teach = 0.0; nb = 0
        use_teacher = has_teacher and args.teacher_weight > 0
        for batch in tr:
            inp, tgt, tgt_teacher, teacher_mask = _unpack(batch)
            inp = inp.to(DEVICE); tgt = tgt.to(DEVICE)
            tgt_rgb = tgt.clamp(0, 1) if has_rgb else bayer_4plane_to_rgb(tgt).clamp(0, 1)
            pred = model(inp).clamp(0, 1)
            l_ms = multiscale_l1(pred, tgt_rgb)
            l = args.task_weight * l_ms
            if use_teacher and teacher_mask is not None and teacher_mask.sum() > 0:
                tgt_teacher = tgt_teacher.to(DEVICE).clamp(0, 1)
                teacher_mask_dev = teacher_mask.to(DEVICE)
                # Per-sample mask: l_teach contributes only on tiles where mask=1.
                # Use reduction='none' and weight by mask.
                diff = (pred - tgt_teacher).abs().mean(dim=[1, 2, 3])  # (B,)
                # Multi-scale weighted L1 with mask
                p, t = pred, tgt_teacher
                ms_per_sample = diff.clone()
                ws = [0.5, 0.25]
                for w in ws:
                    p = F.avg_pool2d(p, 2); t = F.avg_pool2d(t, 2)
                    d_s = (p - t).abs().mean(dim=[1, 2, 3])
                    ms_per_sample = ms_per_sample + w * d_s
                masked = (ms_per_sample * teacher_mask_dev).sum() \
                    / teacher_mask_dev.sum().clamp_min(1)
                l_teach = masked
                l = l + args.teacher_weight * l_teach
                loss_teach += float(l_teach.item())
            if lpips_net is not None and lpips_w_curr > 0:
                # LPIPS expects [-1, 1] range
                l_lpips = lpips_net(pred * 2 - 1, tgt_rgb * 2 - 1).mean()
                l = l + lpips_w_curr * l_lpips
                loss_lp += float(l_lpips.item())
            opt.zero_grad(set_to_none=True); l.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            loss_sum += l.item(); loss_l1 += l_ms.item(); nb += 1
        sched.step()
        pb, pa, vlp, vlp_per_src = evaluate()
        gain = pa - pb
        marker = ""
        # Save criterion: lower val LPIPS when LPIPS net loaded; higher val PSNR otherwise.
        improved = (vlp < best_lpips) if use_lpips_metric else (gain > best_gain)
        if improved:
            if use_lpips_metric: best_lpips = vlp
            best_gain = gain; best_after = pa; best_epoch = ep + 1
            epochs_since_best = 0
            torch.save({
                "backbone_state": model.state_dict(),
                "variant": args.variant,
                "width": VARIANTS[args.variant]["width"], "depth": 3,
                "raw_norm": RAW_NORM, "residual_scale": 0.0,
                "kind": "demosaic_sr", "epoch": ep + 1,
                "val_psnr_base": pb, "val_psnr_model": pa,
                "val_lpips": vlp,
                "val_lpips_per_src": vlp_per_src,
                "params": count_params(model),
            }, ckpt_path)
            marker = "  [SAVED]"
        else:
            epochs_since_best += 1
        teacher_str = (f"  teach={loss_teach/nb:.5f} tw={args.teacher_weight:.3f}"
                       if use_teacher else "")
        if lpips_net is not None:
            print(f"  ep {ep+1:3d}/{args.epochs}  loss={loss_sum/nb:.5f}  "
                  f"l1={loss_l1/nb:.5f}  lpips={loss_lp/nb:.5f}  lp_w={lpips_w_curr:.4f}"
                  f"{teacher_str}  base={pb:.3f}  model={pa:.3f}  gain={gain:+.3f} dB  "
                  f"val_lpips={vlp:.4f}{_fmt_per_src(vlp_per_src)}  "
                  f"t={time.time()-t0:.1f}s{marker}", flush=True)
        else:
            print(f"  ep {ep+1:3d}/{args.epochs}  loss={loss_sum/nb:.5f}"
                  f"{teacher_str}  base={pb:.3f}  model={pa:.3f}  gain={gain:+.3f} dB  "
                  f"t={time.time()-t0:.1f}s{marker}", flush=True)
        if epochs_since_best >= args.patience and ep + 1 >= 40:
            print(f"  Early stop: no improvement in {args.patience} epochs", flush=True)
            break
    if use_lpips_metric:
        print(f"\n  Best val LPIPS: {best_lpips:.4f} at epoch {best_epoch}")
        print(f"  (val PSNR at best: {best_after:.3f} dB, gain {best_gain:+.3f} dB)")
    else:
        print(f"\n  Best val PSNR gain: {best_gain:+.3f} dB at epoch {best_epoch}")
        print(f"  Best val PSNR (model): {best_after:.3f} dB")
    print(f"  Checkpoint: {ckpt_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", type=str, default="F_ane_dm_sr",
                    choices=["F_ane_dm_sr", "F_ane_dm_sr_w24", "F_ane_dm_sr_w32",
                             "bido_4x", "bido_4x_w24", "bido_4x_w32"],
                    help="BIDO variant (width=16 default, or w24/w32 capacity test).")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=4)   # smaller batch since outputs are 4× bigger
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--patience", type=int, default=25)
    ap.add_argument("--subsample", type=int, default=1)
    ap.add_argument("--ckpt-name", type=str,
                    default="BayInDemosaicOut_4x_AAon_w16_ANE.pt")
    # Phase A fine-tune (BIDO_DISTILLATION_PLAN.md):
    ap.add_argument("--init-ckpt", type=str, default=None,
                    help="Path to existing .pt to warm-start from (fine-tune).")
    ap.add_argument("--lpips-weight", type=float, default=0.0,
                    help="If >0, add λ·LPIPS-alex to the loss (frozen network).")
    ap.add_argument("--lpips-warmup-epochs", type=int, default=0,
                    help="Cosine ramp the LPIPS weight from 0 to λ over N epochs.")
    # Phase B distillation:
    ap.add_argument("--task-weight", type=float, default=1.0,
                    help="α: weight on msL1(pred, tgt_rgb). Default 1.0.")
    ap.add_argument("--teacher-weight", type=float, default=0.0,
                    help="β: weight on msL1(pred, tgt_rgb_teacher). Requires NPZ "
                         "with tgt_rgb_teacher field. 0 disables distillation.")
    # Random-exposure augmentation (Real-ESRGAN / Hanji 2024 style).
    # Disabled by default so legacy training runs are unaffected.
    ap.add_argument("--exposure-aug-prob", type=float, default=0.0,
                    help="Per-tile probability of applying a random-exposure "
                         "multiplier to BOTH input and target. 0 disables.")
    ap.add_argument("--exposure-aug-range", type=float, default=4.0,
                    help="Exposure factor sampled log-uniformly in "
                         "[1/range, range]. Default 4.0 -> [-2, +2] stops.")
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()
