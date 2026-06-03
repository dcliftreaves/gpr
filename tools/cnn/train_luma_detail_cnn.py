#!/usr/bin/env python3
"""Train a bounded Lab-L residual CNN from full-gate REF/PIPELINE pairs."""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color
from skimage.filters import gaussian

try:
    import cv2
except Exception:  # pragma: no cover - optional for structure-gated targets
    cv2 = None

try:
    import pywt
except Exception:  # pragma: no cover - optional for structure-gated targets
    pywt = None

import torch
import torch.nn.functional as F
from pytorch_msssim import ms_ssim

try:
    import lpips
except Exception:
    lpips = None

from run_lab_chroma_corrector import LumaDetailCNN, LumaDetailUNet


Image.MAX_IMAGE_PIXELS = None

DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def lab_l_norm(path: Path) -> np.ndarray:
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    return np.clip(color.rgb2lab(rgb)[..., 0] / 100.0, 0.0, 1.0).astype(np.float32)


def signal_target(l_norm: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0.0:
        return l_norm
    return gaussian(l_norm, sigma=sigma, preserve_range=True).astype(np.float32)


def selected_hf(l_chan: np.ndarray, wavelet: str, levels: int, hf_levels: int) -> np.ndarray:
    if pywt is None:
        raise RuntimeError("PyWavelets is required for --target-noise-mode structure_gated")
    coeffs = pywt.wavedec2(l_chan.astype(np.float32), wavelet, level=levels)
    out: list[object] = [np.zeros_like(coeffs[0])]
    first_selected = max(1, len(coeffs) - hf_levels)
    for idx, detail in enumerate(coeffs[1:], start=1):
        if idx >= first_selected:
            out.append(detail)
        else:
            out.append(tuple(np.zeros_like(c) for c in detail))
    rec = pywt.waverec2(out, wavelet).astype(np.float32)
    return rec[: l_chan.shape[0], : l_chan.shape[1]]


def blur(x: np.ndarray, sigma: float) -> np.ndarray:
    if cv2 is None:
        raise RuntimeError("opencv-python is required for --target-noise-mode structure_gated")
    return cv2.GaussianBlur(x.astype(np.float32), (0, 0), sigma).astype(np.float32)


def norm_support(x: np.ndarray, percentile: float = 95.0) -> np.ndarray:
    x = np.maximum(x.astype(np.float32), 0.0)
    scale = float(np.percentile(x, percentile))
    if scale <= 1e-8:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip(x / scale, 0.0, 1.0).astype(np.float32)


def robust_sigma(x: np.ndarray) -> float:
    med_abs = float(np.median(np.abs(x.astype(np.float32))))
    return max(med_abs / 0.67448975, 1e-6)


def gradient_support(l_chan: np.ndarray) -> np.ndarray:
    lx = cv2.Sobel(l_chan.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    ly = cv2.Sobel(l_chan.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    return norm_support(blur(np.sqrt(lx * lx + ly * ly), 1.0))


def signed_local_coherence(hf: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    numerator = np.abs(blur(hf, sigma))
    denominator = blur(np.abs(hf), sigma) + 1e-6
    return np.clip(numerator / denominator, 0.0, 1.0).astype(np.float32)


def structure_gated_signal_target(
    ref_l: np.ndarray,
    candidate_l: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, dict[str, float]]:
    finest_hf = selected_hf(ref_l, args.target_noise_wavelet, args.target_noise_levels, 1)
    two_level_hf = selected_hf(
        ref_l, args.target_noise_wavelet, args.target_noise_levels,
        min(2, args.target_noise_levels),
    )
    coarser_hf = two_level_hf - finest_hf
    ref_lf = ref_l - finest_hf

    edge = gradient_support(ref_lf)
    cross = norm_support(blur(np.abs(coarser_hf), 1.2))
    signed = signed_local_coherence(finest_hf, 1.0)
    local_energy = norm_support(blur(np.abs(finest_hf), 1.0))

    cand_hf = selected_hf(candidate_l, args.target_noise_wavelet, args.target_noise_levels, 1)
    ref_scale = float(np.percentile(np.abs(finest_hf), 95)) + 1e-6
    cand_mag = np.clip(np.abs(cand_hf) / ref_scale, 0.0, 1.0)
    cand_sign = (np.sign(cand_hf) == np.sign(finest_hf)).astype(np.float32)
    cand = cand_mag * (0.35 + 0.65 * cand_sign)

    signal_score = (
        args.target_noise_edge_weight * edge
        + args.target_noise_cross_weight * cross
        + args.target_noise_coherence_weight * signed
        + args.target_noise_local_weight * local_energy
        + args.target_noise_candidate_weight * cand
    )
    weight_sum = (
        args.target_noise_edge_weight
        + args.target_noise_cross_weight
        + args.target_noise_coherence_weight
        + args.target_noise_local_weight
        + args.target_noise_candidate_weight
    )
    signal_score = np.clip(signal_score / max(weight_sum, 1e-6), 0.0, 1.0).astype(np.float32)

    sigma = robust_sigma(finest_hf)
    activity = np.clip(
        np.abs(finest_hf) / (sigma * args.target_noise_activity_sigma),
        0.0,
        1.0,
    )
    structure_gate = np.clip(
        (args.target_noise_signal_cutoff - signal_score)
        / max(args.target_noise_signal_cutoff, 1e-6),
        0.0,
        1.0,
    )
    noise_weight = activity * np.power(
        1.0 - signal_score, args.target_noise_power) * structure_gate
    noise_weight = np.clip(
        blur(noise_weight, args.target_noise_mask_blur),
        0.0,
        args.target_noise_max_weight,
    ).astype(np.float32)

    predicted_noise = finest_hf * noise_weight
    hf_energy = float(np.sum(finest_hf * finest_hf) + 1e-9)
    removed_energy = float(np.sum(predicted_noise * predicted_noise))
    removed_signal_risk = float(
        np.sum((predicted_noise * predicted_noise) * signal_score) / (removed_energy + 1e-9)
    )
    return (ref_l - predicted_noise).astype(np.float32), {
        "hf_sigma": sigma,
        "hf_rms": float(np.sqrt(np.mean(finest_hf * finest_hf))),
        "predicted_noise_rms": float(np.sqrt(np.mean(predicted_noise * predicted_noise))),
        "removed_energy_frac": removed_energy / hf_energy,
        "removed_signal_risk": removed_signal_risk,
        "mean_signal_score": float(np.mean(signal_score)),
        "mean_noise_weight": float(np.mean(noise_weight)),
    }


def load_pairs(
    run_dir: Path,
    image_ids: list[str],
    target_lowpass_sigma: float,
    target_noise_mode: str,
    args: argparse.Namespace,
) -> list[tuple[str, np.ndarray, np.ndarray]]:
    out = []
    if target_noise_mode != "none" and target_lowpass_sigma > 0.0:
        raise ValueError("--target-noise-mode and --target-lowpass-sigma are mutually exclusive")
    for image_id in image_ids:
        ref = run_dir / f"{image_id}_REF.png"
        pipe = run_dir / f"{image_id}_PIPELINE.png"
        if not ref.exists() or not pipe.exists():
            raise FileNotFoundError(
                f"{image_id}: missing full-res REF/PIPELINE PNGs in {run_dir}. "
                "Run the baseline gate with --keep-fullres-pngs first."
            )
        print(f"loading {image_id}...", flush=True)
        ref_l = lab_l_norm(ref)
        pipe_l = lab_l_norm(pipe)
        h = min(ref_l.shape[0], pipe_l.shape[0])
        w = min(ref_l.shape[1], pipe_l.shape[1])
        pipe_l = pipe_l[:h, :w]
        ref_l = ref_l[:h, :w]
        if target_noise_mode == "none":
            target_l = signal_target(ref_l, target_lowpass_sigma)
        elif target_noise_mode == "structure_gated":
            target_l, stats = structure_gated_signal_target(ref_l, pipe_l, args)
            print(
                f"  target noise gate {image_id}: removed_energy={stats['removed_energy_frac']:.6f} "
                f"risk={stats['removed_signal_risk']:.6f} mean_signal={stats['mean_signal_score']:.4f} "
                f"noise_rms={stats['predicted_noise_rms']:.6f}",
                flush=True,
            )
        else:
            raise ValueError(f"unsupported target_noise_mode {target_noise_mode!r}")
        out.append((image_id, pipe_l, np.clip(target_l, 0.0, 1.0).astype(np.float32)))
    return out


def build_luma_model(arch: str, width: int, dilations: tuple[int, ...]) -> torch.nn.Module:
    if arch == "cnn":
        return LumaDetailCNN(width=width, dilations=dilations)
    if arch == "unet":
        return LumaDetailUNet(width=width)
    raise ValueError(f"unsupported --arch {arch!r}")


def to_gray_rgb(x: torch.Tensor) -> torch.Tensor:
    return x.repeat(1, 3, 1, 1)


def random_batch(
    pairs: list[tuple[str, np.ndarray, np.ndarray]],
    batch: int,
    crop: int,
    rng: random.Random,
) -> tuple[torch.Tensor, torch.Tensor]:
    xs, ys = [], []
    for _ in range(batch):
        _, pipe_l, ref_l = rng.choice(pairs)
        h, w = pipe_l.shape
        y0 = rng.randrange(0, h - crop + 1)
        x0 = rng.randrange(0, w - crop + 1)
        xs.append(pipe_l[y0:y0 + crop, x0:x0 + crop])
        ys.append(ref_l[y0:y0 + crop, x0:x0 + crop])
    x = torch.from_numpy(np.stack(xs)[:, None]).to(DEVICE)
    y = torch.from_numpy(np.stack(ys)[:, None]).to(DEVICE)
    return x, y


def eval_fixed(
    model: LumaDetailCNN,
    pairs: list[tuple[str, np.ndarray, np.ndarray]],
    crop: int,
    residual_limit: float,
) -> dict:
    model.eval()
    rows = {}
    with torch.no_grad():
        for image_id, pipe_l, ref_l in pairs:
            h, w = pipe_l.shape
            coords = [
                (max(0, h // 2 - crop // 2), max(0, w // 2 - crop // 2)),
                (min(h - crop, 2000), min(w - crop, 3000)),
                (min(h - crop, 2800), min(w - crop, 4000)),
            ]
            vals = []
            for y0, x0 in coords:
                x = torch.from_numpy(pipe_l[y0:y0 + crop, x0:x0 + crop][None, None]).to(DEVICE)
                y = torch.from_numpy(ref_l[y0:y0 + crop, x0:x0 + crop][None, None]).to(DEVICE)
                pred = (x + model(x).clamp(-residual_limit, residual_limit)).clamp(0, 1)
                l1 = F.l1_loss(pred, y).item()
                ms = ms_ssim(to_gray_rgb(pred), to_gray_rgb(y), data_range=1.0, win_size=11).item()
                vals.append((l1, ms))
            rows[image_id] = {
                "l1": float(np.mean([v[0] for v in vals])),
                "ms_ssim": float(np.mean([v[1] for v in vals])),
            }
    model.train()
    return rows


def train(args: argparse.Namespace) -> None:
    image_ids = [s.strip() for s in args.images.split(",") if s.strip()]
    dilations = tuple(int(s.strip()) for s in args.dilations.split(",") if s.strip())
    if not dilations:
        raise ValueError("--dilations must contain at least one integer")
    pairs = load_pairs(args.run_dir, image_ids, args.target_lowpass_sigma, args.target_noise_mode, args)
    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)

    model = build_luma_model(args.arch, args.width, dilations).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    lpips_net = None
    if args.lpips_weight > 0:
        if lpips is None:
            raise RuntimeError("lpips package is required for --lpips-weight > 0")
        lpips_net = lpips.LPIPS(net="alex").to(DEVICE).eval()
        for p in lpips_net.parameters():
            p.requires_grad_(False)

    best_score = float("inf")
    best_step = 0
    last_stats = {}
    t0 = time.time()
    for step in range(1, args.steps + 1):
        x, y = random_batch(pairs, args.batch, args.crop, rng)
        residual = model(x).clamp(-args.residual_limit, args.residual_limit)
        pred = (x + residual).clamp(0, 1)
        l_charb = torch.sqrt((pred - y) ** 2 + 1e-6).mean()
        loss = args.l1_weight * l_charb
        l_ms = 1.0 - ms_ssim(to_gray_rgb(pred), to_gray_rgb(y), data_range=1.0, win_size=11)
        loss = loss + args.msssim_weight * l_ms
        l_lpips = torch.tensor(0.0, device=DEVICE)
        if lpips_net is not None and step > args.lpips_warmup:
            l_lpips = lpips_net(to_gray_rgb(pred) * 2 - 1, to_gray_rgb(y) * 2 - 1).mean()
            loss = loss + args.lpips_weight * l_lpips

        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % args.log_every == 0 or step == 1:
            rows = eval_fixed(model, pairs, args.eval_crop, args.residual_limit)
            score = float(np.mean([v["l1"] + (1.0 - v["ms_ssim"]) for v in rows.values()]))
            if score < best_score:
                best_score = score
                best_step = step
                args.out.parent.mkdir(parents=True, exist_ok=True)
                torch.save({
                    "kind": "lab_luma_detail_cnn",
                    "arch": args.arch,
                    "state_dict": model.state_dict(),
                    "width": args.width,
                    "dilations": list(dilations),
                    "residual_limit": args.residual_limit,
                    "train_run": str(args.run_dir),
                    "train_images": image_ids,
                    "target_lowpass_sigma": args.target_lowpass_sigma,
                    "target_noise_mode": args.target_noise_mode,
                    "target_noise": target_noise_metadata(args),
                    "step": step,
                    "score": score,
                    "loss": float(loss.item()),
                    "l1": float(l_charb.item()),
                    "ms_ssim_loss": float(l_ms.item()),
                    "lpips_loss": float(l_lpips.item()),
                }, args.out)
                marker = " [SAVED]"
            else:
                marker = ""
            print(
                f"step {step:5d}/{args.steps} loss={loss.item():.5f} "
                f"l1={l_charb.item():.5f} msssim={l_ms.item():.5f} "
                f"lpips={l_lpips.item():.5f} eval={score:.5f} "
                f"t={time.time() - t0:.1f}s{marker}",
                flush=True,
            )
        last_stats = {
            "step": step,
            "loss": float(loss.item()),
            "l1": float(l_charb.item()),
            "ms_ssim_loss": float(l_ms.item()),
            "lpips_loss": float(l_lpips.item()),
        }

    if args.save_final:
        torch.save({
            "kind": "lab_luma_detail_cnn",
            "arch": args.arch,
            "state_dict": model.state_dict(),
            "width": args.width,
            "dilations": list(dilations),
            "residual_limit": args.residual_limit,
            "train_run": str(args.run_dir),
            "train_images": image_ids,
            "target_lowpass_sigma": args.target_lowpass_sigma,
            "target_noise_mode": args.target_noise_mode,
            "target_noise": target_noise_metadata(args),
            "step": args.steps,
            "score": None,
            **last_stats,
        }, args.out)
        best_step = args.steps
        best_score = float(last_stats.get("loss", 0.0))

    sidecar = args.out.with_suffix(args.out.suffix + ".json")
    sidecar.write_text(json.dumps({
        "kind": "lab_luma_detail_cnn",
        "arch": args.arch,
        "checkpoint": str(args.out),
        "train_run": str(args.run_dir),
        "train_images": image_ids,
        "target_lowpass_sigma": args.target_lowpass_sigma,
        "target_noise_mode": args.target_noise_mode,
        "target_noise": target_noise_metadata(args),
        "width": args.width,
        "dilations": list(dilations),
        "residual_limit": args.residual_limit,
        "steps": args.steps,
        "best_step": best_step,
        "best_score": best_score,
        "loss": {
            "l1_weight": args.l1_weight,
            "msssim_weight": args.msssim_weight,
            "lpips_weight": args.lpips_weight,
            "lpips_warmup": args.lpips_warmup,
        },
    }, indent=2))
    print(f"wrote {args.out}", flush=True)
    print(f"wrote {sidecar}", flush=True)


def target_noise_metadata(args: argparse.Namespace) -> dict[str, float | int | str]:
    return {
        "mode": args.target_noise_mode,
        "wavelet": args.target_noise_wavelet,
        "levels": args.target_noise_levels,
        "signal_cutoff": args.target_noise_signal_cutoff,
        "activity_sigma": args.target_noise_activity_sigma,
        "noise_power": args.target_noise_power,
        "mask_blur": args.target_noise_mask_blur,
        "max_weight": args.target_noise_max_weight,
        "edge_weight": args.target_noise_edge_weight,
        "cross_weight": args.target_noise_cross_weight,
        "coherence_weight": args.target_noise_coherence_weight,
        "local_weight": args.target_noise_local_weight,
        "candidate_weight": args.target_noise_candidate_weight,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--images", default=",".join(DEFAULT_IMAGES))
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--crop", type=int, default=384)
    ap.add_argument("--eval-crop", type=int, default=384)
    ap.add_argument("--width", type=int, default=8)
    ap.add_argument("--arch", choices=("cnn", "unet"), default="cnn",
                    help="Refiner architecture. 'unet' is the full-context candidate.")
    ap.add_argument("--dilations", default="1,1",
                    help="Comma-separated dilation schedule for hidden Lab-L residual convolutions.")
    ap.add_argument("--residual-limit", type=float, default=0.08)
    ap.add_argument("--target-lowpass-sigma", type=float, default=0.0,
                    help="Gaussian sigma applied to REF Lab-L before training, to remove non-learnable HF/noise from the signal target.")
    ap.add_argument("--target-noise-mode", choices=("none", "structure_gated"), default="none",
                    help="Optional structure-gated finest-wavelet cleanup. Removes only HF that lacks edge, cross-scale, coherence, energy, and candidate support.")
    ap.add_argument("--target-noise-wavelet", default="sym4")
    ap.add_argument("--target-noise-levels", type=int, default=3)
    ap.add_argument("--target-noise-signal-cutoff", type=float, default=0.35)
    ap.add_argument("--target-noise-activity-sigma", type=float, default=2.5)
    ap.add_argument("--target-noise-power", type=float, default=2.0)
    ap.add_argument("--target-noise-mask-blur", type=float, default=0.8)
    ap.add_argument("--target-noise-max-weight", type=float, default=0.85)
    ap.add_argument("--target-noise-edge-weight", type=float, default=1.0)
    ap.add_argument("--target-noise-cross-weight", type=float, default=1.0)
    ap.add_argument("--target-noise-coherence-weight", type=float, default=1.0)
    ap.add_argument("--target-noise-local-weight", type=float, default=0.75)
    ap.add_argument("--target-noise-candidate-weight", type=float, default=0.75)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--l1-weight", type=float, default=1.0)
    ap.add_argument("--msssim-weight", type=float, default=0.25)
    ap.add_argument("--lpips-weight", type=float, default=0.10)
    ap.add_argument("--lpips-warmup", type=int, default=300)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--save-final", action="store_true",
                    help="Write the final weights instead of the best L1/MS-SSIM eval checkpoint.")
    ap.add_argument("--seed", type=int, default=20260601)
    train(ap.parse_args())


if __name__ == "__main__":
    main()
