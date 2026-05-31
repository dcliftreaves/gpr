#!/usr/bin/env python3
"""Train the 7-channel Lab chroma corrector.

Inputs:
  4 codec Bayer planes + y_half + a_naive_half + b_naive_half

Target:
  full-resolution Lab a/b from tgt_rgb

The model predicts normalized Lab a/b directly, with no residual connection
to the naive chroma hint. Checkpoints are compatible with model.py variant
F_ane_chroma_corrector_w12.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from skimage import color
from torch.utils.data import DataLoader, Dataset

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from model import VARIANTS, build as build_variant, count_params  # noqa: E402


RAW_NORM = 16383.0
AB_NORM = 128.0
DEFAULT_NPZ = os.environ.get(
    "SUPERRES_NPZ", "/Users/dcliftreaves/gpr_data/tiles_ml2_q3_dec2_dmsr_gate.npz"
)
DEFAULT_SIDECAR = os.environ.get(
    "CHROMA_SIDECAR_NPZ",
    "/Users/dcliftreaves/gpr_data/tiles_ml2_q3_dec2_dmsr_gate_chroma.npz",
)
CKPT_DIR = os.environ.get("CKPT_DIR", "/Users/dcliftreaves/gpr_data")
VAL_SRC_NAMES = os.environ.get("VAL_SRC_NAMES", "Z8Z_0067")
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def _names_from_lookup(lookup) -> list[str]:
    return [s.decode() if isinstance(s, bytes) else str(s) for s in lookup.tolist()]


def load_data(npz_path: str, sidecar_path: str, val_src_names: str, subsample_rate: int = 1):
    print(f"  loading {npz_path}", flush=True)
    print(f"  loading {sidecar_path}", flush=True)
    t0 = time.time()
    npz = np.load(npz_path, mmap_mode="r", allow_pickle=True)
    side = np.load(sidecar_path, mmap_mode="r", allow_pickle=True)

    required_npz = ("codec_R", "codec_G1", "codec_G2", "codec_B", "tgt_rgb", "src", "src_lookup_names")
    required_side = ("y_half", "a_naive_half", "b_naive_half", "tile_sat_score", "src")
    for k in required_npz:
        if k not in npz.files:
            raise RuntimeError(f"{npz_path} missing field {k!r}")
    for k in required_side:
        if k not in side.files:
            raise RuntimeError(f"{sidecar_path} missing field {k!r}")

    src = np.asarray(npz["src"])
    if len(side["src"]) != len(src) or not np.array_equal(np.asarray(side["src"]), src):
        raise RuntimeError("sidecar src array does not match main NPZ")

    names = _names_from_lookup(np.asarray(npz["src_lookup_names"]))
    val_names = [n.strip() for n in val_src_names.split(",") if n.strip()]
    val_src_ids = []
    for name in val_names:
        matches = [i for i, n in enumerate(names) if n == name]
        if not matches:
            raise RuntimeError(f"VAL_SRC_NAME {name!r} not in NPZ; first names={names[:5]}")
        val_src_ids.append(matches[0])
    print(f"  val src ids: {dict(zip(val_names, val_src_ids))}", flush=True)

    rng = np.random.RandomState(0)
    keep_mask = np.zeros(len(src), dtype=bool)
    val_set = set(val_src_ids)
    for i in range(len(src)):
        if src[i] in val_set or rng.rand() < (1.0 / subsample_rate):
            keep_mask[i] = True
    print(f"  keeping {int(keep_mask.sum())} of {len(src)} tiles", flush=True)

    out = {k: np.asarray(npz[k][keep_mask]) for k in ("codec_R", "codec_G1", "codec_G2", "codec_B")}
    out["tgt_rgb"] = np.asarray(npz["tgt_rgb"][keep_mask])
    out["src"] = src[keep_mask]
    out["y_half"] = np.asarray(side["y_half"][keep_mask])
    out["a_naive_half"] = np.asarray(side["a_naive_half"][keep_mask])
    out["b_naive_half"] = np.asarray(side["b_naive_half"][keep_mask])
    out["tile_sat_score"] = np.asarray(side["tile_sat_score"][keep_mask], dtype=np.float32)
    out["_val_src_ids"] = val_src_ids
    print(f"  loaded in {time.time() - t0:.1f}s", flush=True)
    return out


def codec_planes(mem, idx):
    return np.stack(
        [mem["codec_R"][idx], mem["codec_G1"][idx], mem["codec_G2"][idx], mem["codec_B"][idx]], 0
    ).astype(np.float32) / RAW_NORM


def chroma_input(mem, idx):
    codec = codec_planes(mem, idx)
    y_half = mem["y_half"][idx].astype(np.float32)[None] / 255.0
    a_half = mem["a_naive_half"][idx].astype(np.float32)[None] / AB_NORM
    b_half = mem["b_naive_half"][idx].astype(np.float32)[None] / AB_NORM
    return np.concatenate([codec, y_half, a_half, b_half], axis=0)


def lab_ab_target(mem, idx):
    rgb = mem["tgt_rgb"][idx].astype(np.float32) / 255.0
    lab = color.rgb2lab(rgb)
    ab = np.transpose(lab[..., 1:3], (2, 0, 1)).astype(np.float32) / AB_NORM
    return ab


class ChromaDS(Dataset):
    def __init__(self, mem, indices, augment: bool = True):
        self.mem = mem
        self.indices = list(indices)
        self.augment = augment

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, i):
        idx = self.indices[i]
        inp = chroma_input(self.mem, idx)
        tgt = lab_ab_target(self.mem, idx)
        if self.augment:
            if np.random.rand() < 0.5:
                inp = inp[:, :, ::-1].copy()
                tgt = tgt[:, :, ::-1].copy()
                inp[:4] = inp[[1, 0, 3, 2]]
            if np.random.rand() < 0.5:
                inp = inp[:, ::-1, :].copy()
                tgt = tgt[:, ::-1, :].copy()
                inp[:4] = inp[[2, 3, 0, 1]]
        return (
            torch.from_numpy(np.ascontiguousarray(inp)).float(),
            torch.from_numpy(np.ascontiguousarray(tgt)).float(),
        )


def expanded_train_indices(mem, train_idx, sat_pct: float, sat_oversample_factor: int):
    if sat_oversample_factor <= 1:
        return list(train_idx)
    scores = mem["tile_sat_score"][train_idx]
    cutoff = float(np.percentile(scores, 100.0 - sat_pct))
    hot = [idx for idx in train_idx if mem["tile_sat_score"][idx] >= cutoff]
    expanded = list(train_idx)
    expanded.extend(hot * (sat_oversample_factor - 1))
    print(
        f"  saturation oversample: cutoff={cutoff:.2f} hot={len(hot)} "
        f"expanded={len(expanded)}",
        flush=True,
    )
    return expanded


def windowed_hue_loss(pred_ab, tgt_ab, sat_mask, kernel: int = 8):
    pad = kernel // 2
    # avg_pool with stride=1 and even kernel pads one extra pixel; crop back.
    p = F.avg_pool2d(pred_ab, kernel, stride=1, padding=pad)[..., : pred_ab.shape[-2], : pred_ab.shape[-1]]
    t = F.avg_pool2d(tgt_ab, kernel, stride=1, padding=pad)[..., : tgt_ab.shape[-2], : tgt_ab.shape[-1]]
    dot = (p * t).sum(dim=1, keepdim=True)
    pm = torch.sqrt((p * p).sum(dim=1, keepdim=True).clamp_min(1e-8))
    tm = torch.sqrt((t * t).sum(dim=1, keepdim=True).clamp_min(1e-8))
    cos_h = (dot / (pm * tm)).clamp(-1, 1)
    return (sat_mask * (1.0 - cos_h)).mean()


def chroma_loss(pred_norm, tgt_norm, h_weight: float, de_weight: float):
    pred = pred_norm * AB_NORM
    tgt = tgt_norm * AB_NORM
    chroma = torch.sqrt((tgt * tgt).sum(dim=1, keepdim=True).clamp_min(1e-8))
    weight = 1.0 + 4.0 * (chroma / 60.0).clamp(0, 1)
    diff2 = ((pred - tgt) ** 2).sum(dim=1, keepdim=True)
    loss_l2 = (weight * diff2).mean()
    loss_de = (weight * torch.sqrt(diff2 + 1e-6)).mean()
    sat_mask = (chroma / 30.0).clamp(0, 1)
    loss_h = windowed_hue_loss(pred, tgt, sat_mask)
    return loss_l2 + h_weight * loss_h + de_weight * loss_de, {
        "l2": float(loss_l2.detach().cpu()),
        "hue": float(loss_h.detach().cpu()),
        "de": float(loss_de.detach().cpu()),
    }


def train(args):
    print(f"=== Training {args.variant} chroma corrector ===")
    print(f"Device: {DEVICE}  CKPT_DIR: {CKPT_DIR}")
    os.makedirs(CKPT_DIR, exist_ok=True)

    mem = load_data(args.npz, args.sidecar_npz, VAL_SRC_NAMES, args.subsample)
    src = mem["src"]
    val_src = set(mem["_val_src_ids"])
    train_idx = [i for i in range(len(src)) if src[i] not in val_src]
    val_idx = [i for i in range(len(src)) if src[i] in val_src]
    train_expanded = expanded_train_indices(mem, train_idx, args.sat_pct, args.sat_oversample_factor)
    print(f"  train tiles: {len(train_idx)} ({len(train_expanded)} sampled)  val tiles: {len(val_idx)}")

    tr = DataLoader(ChromaDS(mem, train_expanded, augment=True), batch_size=args.batch, shuffle=True, num_workers=0)
    va = DataLoader(ChromaDS(mem, val_idx, augment=False), batch_size=args.batch, shuffle=False, num_workers=0)

    if args.variant not in VARIANTS:
        raise RuntimeError(f"unknown model variant {args.variant!r}")
    model = build_variant(args.variant).to(DEVICE)
    print(f"  Params: {count_params(model):,}", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    ckpt_path = os.path.join(CKPT_DIR, args.ckpt_name)

    def evaluate():
        model.eval()
        totals = {"loss": 0.0, "mae_ab": 0.0, "de_proxy": 0.0}
        n = 0
        with torch.no_grad():
            for inp, tgt in va:
                inp = inp.to(DEVICE)
                tgt = tgt.to(DEVICE)
                pred = model(inp)
                loss, _ = chroma_loss(pred, tgt, args.loss_h_weight, args.loss_dE_weight)
                diff = (pred - tgt) * AB_NORM
                totals["loss"] += float(loss.item()) * inp.shape[0]
                totals["mae_ab"] += float(diff.abs().mean().item()) * inp.shape[0]
                totals["de_proxy"] += float(torch.sqrt((diff * diff).sum(dim=1).clamp_min(1e-8)).mean().item()) * inp.shape[0]
                n += inp.shape[0]
        return {k: v / max(1, n) for k, v in totals.items()}

    best = float("inf")
    best_epoch = -1
    epochs_since_best = 0
    init = evaluate()
    print(
        f"  Initial val_loss={init['loss']:.4f} val_mae_ab={init['mae_ab']:.3f} "
        f"val_dE_proxy={init['de_proxy']:.3f}",
        flush=True,
    )

    for ep in range(args.epochs):
        model.train()
        t0 = time.time()
        loss_sum = 0.0
        nb = 0
        parts = {"l2": 0.0, "hue": 0.0, "de": 0.0}
        for inp, tgt in tr:
            inp = inp.to(DEVICE)
            tgt = tgt.to(DEVICE)
            pred = model(inp)
            loss, p = chroma_loss(pred, tgt, args.loss_h_weight, args.loss_dE_weight)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            loss_sum += float(loss.item())
            for k in parts:
                parts[k] += p[k]
            nb += 1
        sched.step()

        val = evaluate()
        improved = val["de_proxy"] < best
        marker = ""
        if improved:
            best = val["de_proxy"]
            best_epoch = ep + 1
            epochs_since_best = 0
            torch.save({
                "backbone_state": model.state_dict(),
                "variant": args.variant,
                "kind": "lab_chroma_corrector",
                "trained_against_codec": "ml2_q3_dec2",
                "raw_norm": RAW_NORM,
                "ab_norm": AB_NORM,
                "epoch": ep + 1,
                "val_loss": val["loss"],
                "val_mae_ab": val["mae_ab"],
                "val_dE_proxy": val["de_proxy"],
                "loss_h_weight": args.loss_h_weight,
                "loss_dE_weight": args.loss_dE_weight,
                "sat_pct": args.sat_pct,
                "sat_oversample_factor": args.sat_oversample_factor,
                "params": count_params(model),
            }, ckpt_path)
            marker = "  [SAVED]"
        else:
            epochs_since_best += 1

        print(
            f"  ep {ep+1:3d}/{args.epochs} loss={loss_sum/max(1, nb):.4f} "
            f"l2={parts['l2']/max(1, nb):.3f} hue={parts['hue']/max(1, nb):.4f} "
            f"de={parts['de']/max(1, nb):.3f} "
            f"val_loss={val['loss']:.4f} val_mae_ab={val['mae_ab']:.3f} "
            f"val_dE_proxy={val['de_proxy']:.3f} t={time.time()-t0:.1f}s{marker}",
            flush=True,
        )

        if epochs_since_best >= args.patience and ep + 1 >= 40:
            print(f"  Early stop: no improvement in {args.patience} epochs", flush=True)
            break

    print(f"\n  Best epoch: {best_epoch}")
    print(f"  Best val_dE_proxy: {best:.3f}")
    print(f"  Checkpoint: {ckpt_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", default=DEFAULT_NPZ)
    ap.add_argument("--sidecar-npz", default=DEFAULT_SIDECAR)
    ap.add_argument("--variant", default="F_ane_chroma_corrector_w12")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--patience", type=int, default=30)
    ap.add_argument("--subsample", type=int, default=1)
    ap.add_argument("--ckpt-name", required=True)
    ap.add_argument("--sat-oversample-factor", type=int, default=3)
    ap.add_argument("--sat-pct", type=float, default=30.0)
    ap.add_argument("--loss-h-weight", type=float, default=0.3)
    ap.add_argument("--loss-dE-weight", type=float, default=0.5)
    args = ap.parse_args()
    train(args)


if __name__ == "__main__":
    main()
