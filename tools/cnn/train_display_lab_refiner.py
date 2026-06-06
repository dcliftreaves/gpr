#!/usr/bin/env python3
"""Train a display-space Lab residual refiner for preview diagnostics.

The model maps candidate display crops to REF-aligned Lab crops using only
candidate pixels, crop coordinates, and candidate image statistics at runtime.
Artifacts are intentionally external to the repo.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
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


Image.MAX_IMAGE_PIXELS = None
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics  # noqa: E402


DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
PREVIEW = {"lpips": 0.15, "ms_ssim": 0.95, "y_psnr": 28.0, "dE2000_mean": 3.0}
LAB_SCALE = np.asarray([100.0, 128.0, 128.0], dtype=np.float32)
DELTA_SCALE = np.asarray([20.0, 32.0, 32.0], dtype=np.float32)


@dataclass(frozen=True)
class Pair:
    image_id: str
    ref: Path
    candidate: Path
    size: tuple[int, int]


class LabRefinerCNN(nn.Module):
    def __init__(self, width: int, in_channels: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=2, dilation=2),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=4, dilation=4),
            nn.GELU(),
            nn.Conv2d(width, width, 3, padding=1),
            nn.GELU(),
            nn.Conv2d(width, 3, 3, padding=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def discover_pairs(frames_dir: Path, candidate_suffix: str) -> list[Pair]:
    pairs = []
    for ref in sorted(frames_dir.glob("*_REF.png")):
        image_id = ref.name[: -len("_REF.png")]
        candidate = frames_dir / f"{image_id}_{candidate_suffix}.png"
        if not candidate.exists():
            continue
        with Image.open(ref) as im:
            size = im.size
        pairs.append(Pair(image_id, ref, candidate, size))
    if not pairs:
        raise FileNotFoundError(f"no REF/{candidate_suffix} pairs in {frames_dir}")
    return pairs


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab.astype(np.float32)) * 255.0, 0, 255).astype(np.uint8)


def grad_mag(arr: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(arr.astype(np.float32))
    return np.sqrt(gx * gx + gy * gy).astype(np.float32)


def fixed_boxes(pair: Pair, crop: int, count: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    w, h = pair.size
    crop = min(crop, w, h)
    coords = [
        ("center", ((w - crop) // 2, (h - crop) // 2)),
        ("upper_left", (w // 6, h // 6)),
        ("lower_right", (max(0, w - w // 6 - crop), max(0, h - h // 6 - crop))),
        ("upper_right", (max(0, w - w // 6 - crop), h // 6)),
        ("lower_left", (w // 6, max(0, h - h // 6 - crop))),
    ]
    out = []
    for label, (x0, y0) in coords[:count]:
        x0 = min(max(0, x0), w - crop)
        y0 = min(max(0, y0), h - crop)
        out.append((label, (x0, y0, x0 + crop, y0 + crop)))
    return out


def random_box(pair: Pair, crop: int, rng: random.Random) -> tuple[int, int, int, int]:
    w, h = pair.size
    x0 = rng.randrange(0, w - crop + 1)
    y0 = rng.randrange(0, h - crop + 1)
    return x0, y0, x0 + crop, y0 + crop


def crop_from_array(arr: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = box
    return arr[y0:y1, x0:x1]


def make_input(
    cand_lab: np.ndarray,
    box: tuple[int, int, int, int],
    image_size: tuple[int, int],
    global_mean: np.ndarray,
    global_std: np.ndarray,
) -> np.ndarray:
    h, w = cand_lab.shape[:2]
    full_w, full_h = image_size
    x0, y0, _, _ = box
    yy = (np.arange(y0, y0 + h, dtype=np.float32) / max(1.0, full_h - 1))[None, :]
    xx = (np.arange(x0, x0 + w, dtype=np.float32) / max(1.0, full_w - 1))[None, :]
    y_plane = np.broadcast_to(yy.T, (h, w))
    x_plane = np.broadcast_to(xx, (h, w))
    lab_norm = cand_lab / LAB_SCALE
    mean_planes = np.broadcast_to((global_mean / LAB_SCALE).reshape(1, 1, 3), (h, w, 3))
    std_planes = np.broadcast_to((global_std / LAB_SCALE).reshape(1, 1, 3), (h, w, 3))
    g = grad_mag(cand_lab[..., 0])[..., None] / 20.0
    features = np.concatenate(
        [
            lab_norm,
            mean_planes.astype(np.float32),
            std_planes.astype(np.float32),
            g.astype(np.float32),
            x_plane[..., None],
            y_plane[..., None],
        ],
        axis=2,
    )
    return np.transpose(features.astype(np.float32), (2, 0, 1))


def build_cache(args: argparse.Namespace, pairs: list[Pair]) -> None:
    if args.cache.exists() and not args.rebuild_cache:
        return
    rng = random.Random(args.seed + 17)
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    image_ids: list[str] = []
    boxes: list[tuple[int, int, int, int]] = []
    t0 = time.time()
    for pair in pairs:
        cand_rgb = np.asarray(Image.open(pair.candidate).convert("RGB"), dtype=np.uint8)
        ref_rgb = np.asarray(Image.open(pair.ref).convert("RGB"), dtype=np.uint8)
        cand_lab_full = rgb_to_lab(cand_rgb)
        ref_lab_full = rgb_to_lab(ref_rgb)
        global_mean = cand_lab_full.reshape(-1, 3).mean(axis=0).astype(np.float32)
        global_std = cand_lab_full.reshape(-1, 3).std(axis=0).astype(np.float32)
        all_boxes = [box for _, box in fixed_boxes(pair, args.crop, args.fixed_crops_per_image)]
        all_boxes.extend(random_box(pair, args.crop, rng) for _ in range(args.random_crops_per_image))
        for box in all_boxes:
            cand_lab = crop_from_array(cand_lab_full, box)
            ref_lab = crop_from_array(ref_lab_full, box)
            x = make_input(cand_lab, box, pair.size, global_mean, global_std)
            delta = (ref_lab - cand_lab) / DELTA_SCALE
            xs.append(x.astype(np.float16))
            ys.append(np.transpose(delta.astype(np.float32), (2, 0, 1)).astype(np.float16))
            image_ids.append(pair.image_id)
            boxes.append(box)
        print(f"cached {pair.image_id}: {len(xs)} crops total t={time.time() - t0:.1f}s", flush=True)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        args.cache,
        x=np.stack(xs),
        y=np.stack(ys),
        image_id=np.asarray(image_ids),
        box=np.asarray(boxes, dtype=np.int32),
        lab_scale=LAB_SCALE,
        delta_scale=DELTA_SCALE,
    )
    print(f"wrote {args.cache}", flush=True)


class CacheDataset:
    def __init__(self, path: Path) -> None:
        z = np.load(path)
        self.x = z["x"].astype(np.float32)
        self.y = z["y"].astype(np.float32)
        self.image_id = z["image_id"].astype(str)
        self.indices = np.arange(len(self.x), dtype=np.int64)

    def batch(self, batch: int, rng: random.Random) -> tuple[torch.Tensor, torch.Tensor]:
        idx = np.asarray([self.indices[rng.randrange(0, len(self.indices))] for _ in range(batch)])
        return torch.from_numpy(self.x[idx]).to(DEVICE), torch.from_numpy(self.y[idx]).to(DEVICE)


def evaluate_loss(model: LabRefinerCNN, ds: CacheDataset, max_items: int = 256) -> float:
    model.eval()
    losses = []
    with torch.no_grad():
        for start in range(0, min(max_items, len(ds.indices)), 16):
            idx = ds.indices[start : start + 16]
            pred = model(torch.from_numpy(ds.x[idx]).to(DEVICE)).cpu().numpy()
            losses.extend(np.sqrt((pred - ds.y[idx]) ** 2 + 1e-8).mean(axis=(1, 2, 3)).tolist())
    model.train()
    return float(np.mean(losses))


def grad_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    dxp = pred[..., :, 1:] - pred[..., :, :-1]
    dxt = target[..., :, 1:] - target[..., :, :-1]
    dyp = pred[..., 1:, :] - pred[..., :-1, :]
    dyt = target[..., 1:, :] - target[..., :-1, :]
    return torch.sqrt((dxp - dxt) ** 2 + 1e-8).mean() + torch.sqrt((dyp - dyt) ** 2 + 1e-8).mean()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def train(args: argparse.Namespace, pairs: list[Pair]) -> dict[str, Any]:
    build_cache(args, pairs)
    ds = CacheDataset(args.cache)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    model = LabRefinerCNN(args.width, in_channels=ds.x.shape[1]).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    best = float("inf")
    best_step = 0
    t0 = time.time()
    for step in range(1, args.steps + 1):
        x, y = ds.batch(args.batch, rng)
        pred = model(x)
        loss = torch.sqrt((pred - y) ** 2 + 1e-8).mean() + args.grad_weight * grad_loss(pred[:, :1], y[:, :1])
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            score = evaluate_loss(model, ds)
            marker = ""
            if score < best:
                best = score
                best_step = step
                args.out.parent.mkdir(parents=True, exist_ok=True)
                torch.save(
                    {
                        "kind": "display_lab_refiner",
                        "state_dict": model.state_dict(),
                        "width": args.width,
                        "in_channels": ds.x.shape[1],
                        "lab_scale": LAB_SCALE,
                        "delta_scale": DELTA_SCALE,
                        "candidate_suffix": args.candidate_suffix,
                        "frames_dir": str(args.frames_dir),
                        "step": step,
                        "score": best,
                    },
                    args.out,
                )
                marker = " [SAVED]"
            print(
                f"step {step:5d}/{args.steps} loss={loss.item():.6f} eval={score:.5f} "
                f"t={time.time() - t0:.1f}s{marker}",
                flush=True,
            )
    sidecar = {
        "kind": "display_lab_refiner",
        "checkpoint": str(args.out),
        "checkpoint_sha256": sha256(args.out),
        "cache": str(args.cache),
        "frames_dir": str(args.frames_dir),
        "candidate_suffix": args.candidate_suffix,
        "steps": args.steps,
        "batch": args.batch,
        "crop": args.crop,
        "width": args.width,
        "lr": args.lr,
        "weight_decay": args.weight_decay,
        "grad_weight": args.grad_weight,
        "best_score": best,
        "best_step": best_step,
        "device": str(DEVICE),
        "image_ids": [p.image_id for p in pairs],
    }
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(sidecar, indent=2))
    return sidecar


def load_crop(path: Path, box: tuple[int, int, int, int]) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.crop(box).convert("RGB"), dtype=np.uint8)


def pass_preview(m: dict[str, float]) -> bool:
    return (
        m["lpips"] <= PREVIEW["lpips"]
        and m["ms_ssim"] >= PREVIEW["ms_ssim"]
        and m["y_psnr"] >= PREVIEW["y_psnr"]
        and m["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def render_refined(
    model: LabRefinerCNN,
    pair: Pair,
    box: tuple[int, int, int, int],
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray]:
    cand_rgb = load_crop(pair.candidate, box)
    cand_lab = rgb_to_lab(cand_rgb)
    full_cand = np.asarray(Image.open(pair.candidate).convert("RGB"), dtype=np.uint8)
    full_lab = rgb_to_lab(full_cand)
    global_mean = full_lab.reshape(-1, 3).mean(axis=0).astype(np.float32)
    global_std = full_lab.reshape(-1, 3).std(axis=0).astype(np.float32)
    x = make_input(cand_lab, box, pair.size, global_mean, global_std)
    with torch.no_grad():
        delta = model(torch.from_numpy(x[None]).to(DEVICE)).cpu().numpy()[0]
    delta_lab = np.transpose(delta, (1, 2, 0)) * DELTA_SCALE * float(args.strength)
    delta_lab[..., 0] = np.clip(delta_lab[..., 0], -args.max_l_delta, args.max_l_delta)
    delta_lab[..., 1:] = np.clip(delta_lab[..., 1:], -args.max_ab_delta, args.max_ab_delta)
    out_lab = cand_lab + delta_lab
    out_lab[..., 0] = np.clip(out_lab[..., 0], 0.0, 100.0)
    out_lab[..., 1:] = np.clip(out_lab[..., 1:], -128.0, 128.0)
    return cand_rgb, lab_to_rgb(out_lab)


def metric_row(ref: np.ndarray, test: np.ndarray) -> dict[str, Any]:
    m = compute_visual_metrics(ref, test)
    m["preview_pass"] = pass_preview(m)
    return m


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for variant in sorted({r["variant"] for r in rows if r["variant"] != "REF"}):
        group = [r for r in rows if r["variant"] == variant]
        out[variant] = {
            "count": len(group),
            "pass_count": sum(1 for r in group if r["preview_pass"]),
            "pass_rate": sum(1 for r in group if r["preview_pass"]) / max(1, len(group)),
            "worst_lpips": max(float(r["lpips"]) for r in group),
            "median_lpips": float(np.median([r["lpips"] for r in group])),
            "worst_ms_ssim": min(float(r["ms_ssim"]) for r in group),
            "worst_y_psnr": min(float(r["y_psnr"]) for r in group),
            "worst_dE2000_mean": max(float(r["dE2000_mean"]) for r in group),
        }
    return out


def write_html(rows: list[dict[str, Any]], summary: dict[str, Any], args: argparse.Namespace) -> None:
    css = """
body { margin:18px; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif; background:#f5f5f1; color:#202124; }
h1 { font-size:22px; margin:0 0 8px; } h2 { font-size:18px; margin:24px 0 10px; }
table { border-collapse:collapse; background:#fff; font-size:12px; margin:12px 0 20px; }
th,td { border:1px solid #d8d8d1; padding:6px 8px; text-align:right; } th.left,td.left { text-align:left; } th { background:#e8e8e1; }
.pass { color:#0a6f2a; font-weight:650; } .fail { color:#9b1c1c; font-weight:650; }
.grid { display:grid; grid-template-columns:repeat(3,minmax(240px,1fr)); gap:10px; }
.tile { background:#fff; border:1px solid #d8d8d1; padding:8px; } .tile img { width:100%; display:block; }
.cap { font-size:11px; color:#555; margin-top:4px; }
"""
    parts = ["<!doctype html><meta charset='utf-8'><title>Display Lab Refiner</title>", f"<style>{css}</style>", "<h1>Display Lab Refiner</h1>"]
    parts.append("<table><tr><th class='left'>Variant</th><th>Count</th><th>Pass</th><th>Pass rate</th><th>Worst LPIPS</th><th>Median LPIPS</th><th>Worst MS</th><th>Worst dE</th></tr>")
    for variant, s in summary["variants"].items():
        parts.append(
            f"<tr><td class='left'>{html.escape(variant)}</td><td>{s['count']}</td><td>{s['pass_count']}</td>"
            f"<td>{100*s['pass_rate']:.1f}%</td><td>{s['worst_lpips']:.4f}</td><td>{s['median_lpips']:.4f}</td>"
            f"<td>{s['worst_ms_ssim']:.4f}</td><td>{s['worst_dE2000_mean']:.3f}</td></tr>"
        )
    parts.append("</table>")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["image_id"], row["crop_label"]), []).append(row)
    for (image_id, crop_label), group in grouped.items():
        parts.append(f"<h2>{html.escape(image_id)} / {html.escape(crop_label)}</h2><div class='grid'>")
        for row in sorted(group, key=lambda r: ["REF", "candidate", "refined"].index(r["variant"])):
            metric = ""
            if row["variant"] != "REF":
                klass = "pass" if row["preview_pass"] else "fail"
                metric = f"<span class='{klass}'>LPIPS {row['lpips']:.4f}, MS {row['ms_ssim']:.4f}, Y {row['y_psnr']:.2f}, dE {row['dE2000_mean']:.2f}</span>"
            parts.append(f"<div class='tile'><img src='{html.escape(row['png'])}'><div class='cap'>{html.escape(row['variant'])}<br>{metric}</div></div>")
        parts.append("</div>")
    args.dashboard_html.write_text("\n".join(parts))


def evaluate_dashboard(args: argparse.Namespace, pairs: list[Pair], sidecar: dict[str, Any]) -> dict[str, Any]:
    ck = torch.load(str(args.out), map_location="cpu", weights_only=False)
    model = LabRefinerCNN(int(ck["width"]), int(ck["in_channels"])).to(DEVICE)
    model.load_state_dict(ck["state_dict"])
    model.eval()
    args.dashboard_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        for label, box in fixed_boxes(pair, args.dashboard_crop, args.dashboard_crops_per_image):
            ref = load_crop(pair.ref, box)
            cand, refined = render_refined(model, pair, box, args)
            variants = {"REF": ref, "candidate": cand, "refined": refined}
            for variant, rgb in variants.items():
                png = args.dashboard_dir / f"{pair.image_id}_{label}_{variant}.png"
                Image.fromarray(rgb).save(png)
                row: dict[str, Any] = {"image_id": pair.image_id, "crop_label": label, "variant": variant, "png": png.name}
                if variant != "REF":
                    row.update(metric_row(ref, rgb))
                rows.append(row)
    summary = {**sidecar, "rows": rows, "variants": summarize(rows), "dashboard_html": str(args.dashboard_html)}
    args.dashboard_json.write_text(json.dumps(summary, indent=2))
    write_html(rows, summary, args)
    print(json.dumps({"variants": summary["variants"], "dashboard_html": str(args.dashboard_html)}, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_multi_env/frames"))
    ap.add_argument("--candidate-suffix", default="SOTA")
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dashboard-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--fixed-crops-per-image", type=int, default=5)
    ap.add_argument("--random-crops-per-image", type=int, default=192)
    ap.add_argument("--dashboard-crop", type=int, default=512)
    ap.add_argument("--dashboard-crops-per-image", type=int, default=2)
    ap.add_argument("--width", type=int, default=48)
    ap.add_argument("--lr", type=float, default=8e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--grad-weight", type=float, default=0.10)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260606)
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--max-l-delta", type=float, default=24.0)
    ap.add_argument("--max-ab-delta", type=float, default=32.0)
    ap.add_argument("--rebuild-cache", action="store_true")
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()
    pairs = discover_pairs(args.frames_dir, args.candidate_suffix)
    sidecar = json.loads(args.out.with_suffix(args.out.suffix + ".json").read_text()) if args.eval_only else train(args, pairs)
    evaluate_dashboard(args, pairs, sidecar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
