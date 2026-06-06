#!/usr/bin/env python3
"""Train and evaluate a small display-luma high-frequency detail sidecar.

This is a production-shaped diagnostic for the PREVIEW blocker: it learns the
REF Lab-L high-frequency residual from candidate display crops, without copying
REF phase at runtime. Checkpoints and dashboards are written outside the repo.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from skimage import color

try:
    import pywt
except Exception as exc:  # pragma: no cover
    pywt = None
    _PYWT_ERROR = exc
else:
    _PYWT_ERROR = None


Image.MAX_IMAGE_PIXELS = None
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics  # noqa: E402


DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "dE2000_mean": 3.0}


@dataclass(frozen=True)
class Pair:
    image_id: str
    ref: Path
    candidate: Path
    size: tuple[int, int]


class DisplayHFDetailCNN(nn.Module):
    def __init__(self, width: int, in_channels: int = 6) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=4, dilation=4),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, 1, 3, padding=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def discover_pairs(frames_dir: Path, candidate_suffix: str) -> list[Pair]:
    pairs: list[Pair] = []
    for ref in sorted(frames_dir.glob("*_REF.png")):
        image_id = ref.name[: -len("_REF.png")]
        cand = frames_dir / f"{image_id}_{candidate_suffix}.png"
        if not cand.exists():
            continue
        with Image.open(ref) as im:
            size = im.size
        pairs.append(Pair(image_id, ref, cand, size))
    if not pairs:
        raise FileNotFoundError(f"no *_REF.png / *_{candidate_suffix}.png pairs in {frames_dir}")
    return pairs


def load_crop(path: Path, box: tuple[int, int, int, int]) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.crop(box).convert("RGB"), dtype=np.uint8)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab.astype(np.float32)) * 255.0, 0, 255).astype(np.uint8)


def split_luma_hf(l_chan: np.ndarray, wavelet: str, levels: int, hf_levels: int) -> tuple[np.ndarray, np.ndarray]:
    if pywt is None:
        raise RuntimeError(f"pywt is required: {_PYWT_ERROR}")
    coeffs = pywt.wavedec2(l_chan.astype(np.float32), wavelet, level=levels)
    low = [coeffs[0]]
    high = [np.zeros_like(coeffs[0])]
    first_hf = max(1, len(coeffs) - hf_levels)
    for idx, detail in enumerate(coeffs[1:], start=1):
        if idx >= first_hf:
            low.append(tuple(np.zeros_like(c) for c in detail))
            high.append(detail)
        else:
            low.append(detail)
            high.append(tuple(np.zeros_like(c) for c in detail))
    lf = pywt.waverec2(low, wavelet).astype(np.float32)
    hf = pywt.waverec2(high, wavelet).astype(np.float32)
    return lf[: l_chan.shape[0], : l_chan.shape[1]], hf[: l_chan.shape[0], : l_chan.shape[1]]


def grad_mag(arr: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(arr.astype(np.float32))
    return np.sqrt(gx * gx + gy * gy).astype(np.float32)


def make_features(
    candidate_rgb: np.ndarray,
    ref_rgb: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, dict[str, float], np.ndarray]:
    cand_lab = rgb_to_lab(candidate_rgb)
    ref_lab = rgb_to_lab(ref_rgb)
    cand_lf, cand_hf = split_luma_hf(cand_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
    _, ref_hf = split_luma_hf(ref_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
    features = np.stack(
        [
            cand_lab[..., 0] / 100.0,
            cand_lf / 100.0,
            cand_hf / args.hf_norm,
            cand_lab[..., 1] / 128.0,
            cand_lab[..., 2] / 128.0,
            grad_mag(cand_lf) / args.hf_norm,
        ],
        axis=0,
    ).astype(np.float32)
    if args.target_mode == "ref_hf":
        target_hf = ref_hf
    elif args.target_mode == "delta_hf":
        target_hf = ref_hf - cand_hf
    else:
        raise ValueError(f"unknown target mode {args.target_mode!r}")
    target = (target_hf[None] / args.hf_norm).astype(np.float32)
    stats = {
        "ref_hf_rms": float(np.sqrt(np.mean(ref_hf * ref_hf))),
        "candidate_hf_rms": float(np.sqrt(np.mean(cand_hf * cand_hf))),
    }
    return features, target, stats, cand_lab


def render_with_hf(candidate_rgb: np.ndarray, pred_hf: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    cand_lab = rgb_to_lab(candidate_rgb)
    cand_lf, _ = split_luma_hf(cand_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
    out_lab = cand_lab.copy()
    pred_hf = pred_hf.astype(np.float32) * float(args.detail_strength)
    if args.target_mode == "ref_hf":
        out_lab[..., 0] = np.clip(cand_lf + pred_hf, 0.0, 100.0)
    elif args.target_mode == "delta_hf":
        out_lab[..., 0] = np.clip(cand_lab[..., 0] + pred_hf, 0.0, 100.0)
    else:
        raise ValueError(f"unknown target mode {args.target_mode!r}")
    return lab_to_rgb(out_lab)


def render_signal_only(candidate_rgb: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    cand_lab = rgb_to_lab(candidate_rgb)
    cand_lf, _ = split_luma_hf(cand_lab[..., 0], args.wavelet, args.levels, args.hf_levels)
    out_lab = cand_lab.copy()
    out_lab[..., 0] = np.clip(cand_lf, 0.0, 100.0)
    return lab_to_rgb(out_lab)


def pass_preview(m: dict[str, float]) -> bool:
    return (
        m["lpips"] <= PREVIEW["lpips"]
        and m["ms_ssim"] >= PREVIEW["ms_ssim"]
        and m["y_psnr"] >= PREVIEW["y_psnr"]
        and m["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def crop_box(pair: Pair, crop: int, rng: random.Random) -> tuple[int, int, int, int]:
    w, h = pair.size
    if crop > w or crop > h:
        raise ValueError(f"crop {crop} exceeds {pair.image_id} size {w}x{h}")
    x0 = rng.randrange(0, w - crop + 1)
    y0 = rng.randrange(0, h - crop + 1)
    return (x0, y0, x0 + crop, y0 + crop)


def fixed_boxes(pair: Pair, crop: int, count: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    w, h = pair.size
    crop = min(crop, w, h)
    candidates = [
        ("center", ((w - crop) // 2, (h - crop) // 2)),
        ("upper_left", (w // 6, h // 6)),
        ("lower_right", (max(0, w - w // 6 - crop), max(0, h - h // 6 - crop))),
        ("upper_right", (max(0, w - w // 6 - crop), h // 6)),
        ("lower_left", (w // 6, max(0, h - h // 6 - crop))),
    ]
    out = []
    for label, (x0, y0) in candidates[:count]:
        x0 = min(max(0, x0), w - crop)
        y0 = min(max(0, y0), h - crop)
        out.append((label, (x0, y0, x0 + crop, y0 + crop)))
    return out


def random_batch(
    pairs: list[Pair],
    batch: int,
    crop: int,
    rng: random.Random,
    args: argparse.Namespace,
) -> tuple[torch.Tensor, torch.Tensor]:
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for _ in range(batch):
        pair = rng.choice(pairs)
        box = crop_box(pair, crop, rng)
        ref = load_crop(pair.ref, box)
        cand = load_crop(pair.candidate, box)
        x, y, _, _ = make_features(cand, ref, args)
        if rng.random() < 0.5:
            x = x[:, :, ::-1].copy()
            y = y[:, :, ::-1].copy()
        if rng.random() < 0.5:
            x = x[:, ::-1, :].copy()
            y = y[:, ::-1, :].copy()
        xs.append(x)
        ys.append(y)
    return torch.from_numpy(np.stack(xs)).to(DEVICE), torch.from_numpy(np.stack(ys)).to(DEVICE)


def build_pair_cache(args: argparse.Namespace, pairs: list[Pair]) -> None:
    if args.pair_cache is None:
        return
    if args.pair_cache.exists() and not args.rebuild_cache:
        return
    rng = random.Random(args.seed + 1234)
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    image_ids: list[str] = []
    boxes: list[tuple[int, int, int, int]] = []
    holdout_set = set(args.holdout)
    holdout: list[bool] = []
    t0 = time.time()
    for pair in pairs:
        for _ in range(args.cache_crops_per_image):
            box = crop_box(pair, args.crop, rng)
            ref = load_crop(pair.ref, box)
            cand = load_crop(pair.candidate, box)
            x, y, _, _ = make_features(cand, ref, args)
            xs.append(x.astype(np.float16))
            ys.append(y.astype(np.float16))
            image_ids.append(pair.image_id)
            boxes.append(box)
            holdout.append(pair.image_id in holdout_set)
        print(
            f"cached {pair.image_id}: {len(xs)} crops total "
            f"t={time.time() - t0:.1f}s",
            flush=True,
        )
    args.pair_cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        args.pair_cache,
        x=np.stack(xs),
        y=np.stack(ys),
        image_id=np.asarray(image_ids),
        box=np.asarray(boxes, dtype=np.int32),
        holdout=np.asarray(holdout, dtype=bool),
        crop=np.asarray([args.crop], dtype=np.int32),
        wavelet=np.asarray([args.wavelet]),
        levels=np.asarray([args.levels], dtype=np.int32),
        hf_levels=np.asarray([args.hf_levels], dtype=np.int32),
        hf_norm=np.asarray([args.hf_norm], dtype=np.float32),
        target_mode=np.asarray([args.target_mode]),
    )
    print(f"wrote cache {args.pair_cache} ({len(xs)} crops)", flush=True)


class CachedPairDataset:
    def __init__(self, path: Path) -> None:
        z = np.load(path)
        self.x = z["x"].astype(np.float32)
        self.y = z["y"].astype(np.float32)
        self.image_id = z["image_id"].astype(str)
        self.holdout = z["holdout"].astype(bool)
        if len(self.x) == 0:
            raise ValueError(f"{path} contains no crop pairs")

    def random_batch(self, indices: np.ndarray, batch: int, rng: random.Random) -> tuple[torch.Tensor, torch.Tensor]:
        pick = np.asarray([indices[rng.randrange(0, len(indices))] for _ in range(batch)], dtype=np.int64)
        return torch.from_numpy(self.x[pick]).to(DEVICE), torch.from_numpy(self.y[pick]).to(DEVICE)


def evaluate_loss_cached(
    model: DisplayHFDetailCNN,
    dataset: CachedPairDataset,
    indices: np.ndarray,
    max_items: int = 96,
) -> dict[str, float]:
    model.eval()
    losses = []
    with torch.no_grad():
        for start in range(0, min(len(indices), max_items), 16):
            idx = indices[start : start + 16]
            pred = model(torch.from_numpy(dataset.x[idx]).to(DEVICE)).cpu().numpy()
            target = dataset.y[idx]
            losses.extend(np.sqrt((pred - target) ** 2 + 1e-8).mean(axis=(1, 2, 3)).astype(float).tolist())
    model.train()
    return {"mean_hf_l1": float(np.mean(losses)) if losses else float("inf")}


def evaluate_loss(model: DisplayHFDetailCNN, pairs: list[Pair], args: argparse.Namespace) -> dict[str, float]:
    model.eval()
    rng = random.Random(args.seed + 77)
    losses = []
    with torch.no_grad():
        for pair in pairs:
            for _, box in fixed_boxes(pair, args.eval_crop, min(args.eval_crops_per_image, 2)):
                ref = load_crop(pair.ref, box)
                cand = load_crop(pair.candidate, box)
                x, y, _, _ = make_features(cand, ref, args)
                pred = model(torch.from_numpy(x[None]).to(DEVICE)).cpu().numpy()[0]
                losses.append(float(np.sqrt((pred - y) ** 2 + 1e-8).mean()))
        for _ in range(max(0, args.eval_random_crops)):
            pair = rng.choice(pairs)
            box = crop_box(pair, args.eval_crop, rng)
            ref = load_crop(pair.ref, box)
            cand = load_crop(pair.candidate, box)
            x, y, _, _ = make_features(cand, ref, args)
            pred = model(torch.from_numpy(x[None]).to(DEVICE)).cpu().numpy()[0]
            losses.append(float(np.sqrt((pred - y) ** 2 + 1e-8).mean()))
    model.train()
    return {"mean_hf_l1": float(np.mean(losses)) if losses else float("inf")}


def tensor_grad_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    dx_p = pred[..., :, 1:] - pred[..., :, :-1]
    dx_t = target[..., :, 1:] - target[..., :, :-1]
    dy_p = pred[..., 1:, :] - pred[..., :-1, :]
    dy_t = target[..., 1:, :] - target[..., :-1, :]
    return torch.sqrt((dx_p - dx_t) ** 2 + 1e-8).mean() + torch.sqrt((dy_p - dy_t) ** 2 + 1e-8).mean()


def checkpoint_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def train(args: argparse.Namespace, pairs: list[Pair], train_pairs: list[Pair], holdout_pairs: list[Pair]) -> dict[str, Any]:
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    cached: CachedPairDataset | None = None
    train_idx: np.ndarray | None = None
    holdout_idx: np.ndarray | None = None
    if args.pair_cache is not None:
        build_pair_cache(args, pairs)
        cached = CachedPairDataset(args.pair_cache)
        train_idx = np.flatnonzero(~cached.holdout)
        holdout_idx = np.flatnonzero(cached.holdout)
        if len(train_idx) == 0:
            raise ValueError("pair cache has no training crops")
        if len(holdout_idx) == 0:
            holdout_idx = train_idx
    model = DisplayHFDetailCNN(args.width).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    best_score = float("inf")
    best_eval: dict[str, Any] | None = None
    t0 = time.time()
    for step in range(1, args.steps + 1):
        if cached is None:
            x, y = random_batch(train_pairs, args.batch, args.crop, rng, args)
        else:
            assert train_idx is not None
            x, y = cached.random_batch(train_idx, args.batch, rng)
        pred = model(x)
        loss = torch.sqrt((pred - y) ** 2 + 1e-8).mean() + args.grad_weight * tensor_grad_loss(pred, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            if cached is None:
                train_eval = evaluate_loss(model, train_pairs, args)
                holdout_eval = evaluate_loss(model, holdout_pairs, args) if holdout_pairs else train_eval
            else:
                assert train_idx is not None and holdout_idx is not None
                train_eval = evaluate_loss_cached(model, cached, train_idx)
                holdout_eval = evaluate_loss_cached(model, cached, holdout_idx)
            score = holdout_eval["mean_hf_l1"]
            marker = ""
            if score < best_score:
                best_score = score
                best_eval = {"train": train_eval, "holdout": holdout_eval}
                args.out.parent.mkdir(parents=True, exist_ok=True)
                torch.save(
                    {
                        "kind": "display_luma_hf_detail_cnn",
                        "state_dict": model.state_dict(),
                        "width": args.width,
                        "in_channels": 6,
                        "hf_norm": args.hf_norm,
                        "wavelet": args.wavelet,
                        "levels": args.levels,
                        "hf_levels": args.hf_levels,
                        "target_mode": args.target_mode,
                        "candidate_suffix": args.candidate_suffix,
                        "frames_dir": str(args.frames_dir),
                        "train_ids": [p.image_id for p in train_pairs],
                        "holdout_ids": [p.image_id for p in holdout_pairs],
                        "step": step,
                        "score": best_score,
                    },
                    args.out,
                )
                marker = " [SAVED]"
            print(
                f"step {step:5d}/{args.steps} loss={loss.item():.6f} "
                f"train_hf_l1={train_eval['mean_hf_l1']:.5f} "
                f"holdout_hf_l1={holdout_eval['mean_hf_l1']:.5f} "
                f"t={time.time() - t0:.1f}s{marker}",
                flush=True,
            )
    sha = checkpoint_sha256(args.out)
    sidecar = {
        "kind": "display_luma_hf_detail_cnn",
        "checkpoint": str(args.out),
        "checkpoint_sha256": sha,
        "frames_dir": str(args.frames_dir),
        "pair_cache": str(args.pair_cache) if args.pair_cache else None,
        "candidate_suffix": args.candidate_suffix,
        "steps": args.steps,
        "batch": args.batch,
        "crop": args.crop,
        "width": args.width,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "grad_weight": args.grad_weight,
        "wavelet": args.wavelet,
        "levels": args.levels,
        "hf_levels": args.hf_levels,
        "hf_norm": args.hf_norm,
        "target_mode": args.target_mode,
        "detail_strength": args.detail_strength,
        "device": str(DEVICE),
        "all_ids": [p.image_id for p in pairs],
        "train_ids": [p.image_id for p in train_pairs],
        "holdout_ids": [p.image_id for p in holdout_pairs],
        "best_score": best_score,
        "best_eval": best_eval,
    }
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(sidecar, indent=2))
    return sidecar


def load_model(args: argparse.Namespace) -> tuple[DisplayHFDetailCNN, dict[str, Any]]:
    ck = torch.load(str(args.out), map_location="cpu", weights_only=False)
    model = DisplayHFDetailCNN(int(ck["width"]), in_channels=int(ck.get("in_channels", 6))).to(DEVICE)
    model.load_state_dict(ck["state_dict"])
    model.eval()
    return model, ck


def metric_row(ref: np.ndarray, test: np.ndarray) -> dict[str, Any]:
    m = compute_visual_metrics(ref, test)
    m["preview_pass"] = pass_preview(m)
    return m


def write_dashboard(rows: list[dict[str, Any]], summary: dict[str, Any], args: argparse.Namespace) -> None:
    args.dashboard_dir.mkdir(parents=True, exist_ok=True)
    css = """
body { margin: 18px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background: #f5f5f1; color: #202124; }
h1 { font-size: 22px; margin: 0 0 6px; }
h2 { font-size: 18px; margin: 26px 0 10px; }
p { max-width: 1120px; line-height: 1.45; color: #555; }
table { border-collapse: collapse; background: #fff; font-size: 12px; margin: 12px 0 20px; }
th, td { border: 1px solid #d8d8d1; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #e8e8e1; }
.pass { color: #0a6f2a; font-weight: 650; }
.fail { color: #9b1c1c; font-weight: 650; }
.grid { display: grid; grid-template-columns: repeat(4, minmax(220px, 1fr)); gap: 10px; align-items: start; }
.tile { background: #fff; border: 1px solid #d8d8d1; padding: 8px; }
.tile img { width: 100%; image-rendering: auto; display: block; }
.cap { font-size: 11px; color: #555; margin-top: 4px; }
"""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["image_id"], row["crop_label"]), []).append(row)
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Display HF Detail Candidate</title>",
        f"<style>{css}</style>",
        "<h1>Display HF Detail Candidate</h1>",
        "<p>Small CNN trained to synthesize Lab-L high-frequency detail from candidate display crops. "
        "The REF exact-HF oracle remains the ceiling; this dashboard tests whether learned, conditioned HF beats the candidate without copying REF detail.</p>",
        "<h2>Summary</h2>",
        "<table><tr><th class='left'>Variant</th><th>Count</th><th>Pass</th><th>Worst LPIPS</th><th>Median LPIPS</th><th>Worst MS-SSIM</th><th>Worst dE</th></tr>",
    ]
    for variant, s in summary["variants"].items():
        parts.append(
            "<tr>"
            f"<td class='left'>{html.escape(variant)}</td>"
            f"<td>{s['count']}</td><td>{s['pass_count']}</td>"
            f"<td>{s['worst_lpips']:.4f}</td><td>{s['median_lpips']:.4f}</td>"
            f"<td>{s['worst_ms_ssim']:.4f}</td><td>{s['worst_dE2000_mean']:.3f}</td>"
            "</tr>"
        )
    parts.append("</table>")
    parts.append(
        "<table><tr><th class='left'>Checkpoint</th><th class='left'>Train IDs</th><th class='left'>Holdout IDs</th></tr>"
        f"<tr><td class='left'>{html.escape(summary['checkpoint'])}</td>"
        f"<td class='left'>{html.escape(', '.join(summary['train_ids']))}</td>"
        f"<td class='left'>{html.escape(', '.join(summary['holdout_ids']))}</td></tr></table>"
    )
    for (image_id, crop_label), group in grouped.items():
        parts.append(f"<h2>{html.escape(image_id)} / {html.escape(crop_label)}</h2><div class='grid'>")
        order = ["REF", "candidate", "signal_only", "predicted_hf", "guarded_hf"]
        for row in sorted(group, key=lambda r: order.index(r["variant"])):
            klass = "pass" if row.get("preview_pass") else "fail"
            metric = "" if row["variant"] == "REF" else (
                f"<span class='{klass}'>LPIPS {row['lpips']:.4f}, MS {row['ms_ssim']:.4f}, "
                f"Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span>"
            )
            parts.append(
                "<div class='tile'>"
                f"<img src='{html.escape(row['png'])}' alt='{html.escape(row['variant'])}'>"
                f"<div class='cap'>{html.escape(row['variant'])}<br>{metric}</div>"
                "</div>"
            )
        parts.append("</div>")
    args.dashboard_html.write_text("\n".join(parts))


def evaluate_dashboard(args: argparse.Namespace, pairs: list[Pair], sidecar: dict[str, Any]) -> dict[str, Any]:
    model, _ = load_model(args)
    args.dashboard_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for pair in pairs:
            for crop_label, box in fixed_boxes(pair, args.dashboard_crop, args.dashboard_crops_per_image):
                ref = load_crop(pair.ref, box)
                cand = load_crop(pair.candidate, box)
                x, target, stats, _ = make_features(cand, ref, args)
                pred = model(torch.from_numpy(x[None]).to(DEVICE)).cpu().numpy()[0, 0] * args.hf_norm
                pred = np.clip(pred, -args.max_hf_delta, args.max_hf_delta)
                signal = render_signal_only(cand, args)
                predicted = render_with_hf(cand, pred, args)
                variants = {
                    "REF": ref,
                    "candidate": cand,
                    "signal_only": signal,
                    "predicted_hf": predicted,
                }
                if args.guard_candidate_hf_rms is not None:
                    guarded = predicted if stats["candidate_hf_rms"] <= args.guard_candidate_hf_rms else cand
                    variants["guarded_hf"] = guarded
                for variant, rgb in variants.items():
                    png = args.dashboard_dir / f"{pair.image_id}_{crop_label}_{variant}.png"
                    Image.fromarray(rgb).save(png)
                    row: dict[str, Any] = {
                        "image_id": pair.image_id,
                        "crop_label": crop_label,
                        "variant": variant,
                        "png": png.name,
                        "ref_hf_rms": stats["ref_hf_rms"],
                        "candidate_hf_rms": stats["candidate_hf_rms"],
                    }
                    if variant != "REF":
                        row.update(metric_row(ref, rgb))
                    rows.append(row)
    variants_summary: dict[str, Any] = {}
    for variant in sorted({r["variant"] for r in rows if r["variant"] != "REF"}):
        group = [r for r in rows if r["variant"] == variant]
        variants_summary[variant] = {
            "count": len(group),
            "pass_count": sum(1 for r in group if r["preview_pass"]),
            "worst_lpips": max(float(r["lpips"]) for r in group),
            "median_lpips": float(np.median([r["lpips"] for r in group])),
            "worst_ms_ssim": min(float(r["ms_ssim"]) for r in group),
            "worst_y_psnr": min(float(r["y_psnr"]) for r in group),
            "worst_dE2000_mean": max(float(r["dE2000_mean"]) for r in group),
        }
    summary = {
        **sidecar,
        "rows": rows,
        "variants": variants_summary,
        "dashboard_dir": str(args.dashboard_dir),
        "dashboard_html": str(args.dashboard_html),
    }
    args.dashboard_json.write_text(json.dumps(summary, indent=2))
    write_dashboard(rows, summary, args)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_multi_env/frames"))
    ap.add_argument("--candidate-suffix", default="SOTA")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dashboard-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument("--holdout", action="append", default=["Z8Z_6680", "Z8Z_7955"])
    ap.add_argument("--pair-cache", type=Path, default=None)
    ap.add_argument("--cache-crops-per-image", type=int, default=96)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--crop", type=int, default=192)
    ap.add_argument("--eval-crop", type=int, default=256)
    ap.add_argument("--eval-crops-per-image", type=int, default=2)
    ap.add_argument("--eval-random-crops", type=int, default=4)
    ap.add_argument("--dashboard-crop", type=int, default=512)
    ap.add_argument("--dashboard-crops-per-image", type=int, default=2)
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--lr", type=float, default=8e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--grad-weight", type=float, default=0.15)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260606)
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=3)
    ap.add_argument("--hf-levels", type=int, default=3)
    ap.add_argument("--hf-norm", type=float, default=12.0)
    ap.add_argument("--max-hf-delta", type=float, default=18.0)
    ap.add_argument("--detail-strength", type=float, default=1.0)
    ap.add_argument("--target-mode", choices=("delta_hf", "ref_hf"), default="delta_hf")
    ap.add_argument("--guard-candidate-hf-rms", type=float, default=None)
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()

    pairs = discover_pairs(args.frames_dir, args.candidate_suffix)
    holdout_set = set(args.holdout)
    train_pairs = [p for p in pairs if p.image_id not in holdout_set]
    holdout_pairs = [p for p in pairs if p.image_id in holdout_set]
    if not train_pairs:
        raise ValueError("no training pairs remain after holdout selection")
    if args.eval_only:
        sidecar = json.loads(args.out.with_suffix(args.out.suffix + ".json").read_text())
    else:
        sidecar = train(args, pairs, train_pairs, holdout_pairs)
    summary = evaluate_dashboard(args, pairs, sidecar)
    print(json.dumps({"variants": summary["variants"], "dashboard_html": str(args.dashboard_html)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
