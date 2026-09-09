#!/usr/bin/env python3
"""Classify finest Lab-L wavelet energy as likely noise or signal.

This probe is a guard before training on a denoised REF target. It should catch
the failure mode where "remove HF/noise" actually removes coherent texture.

Noise is treated as finest-scale Lab-L wavelet energy that is weakly supported
by structure:

  - low edge/gradient support in the REF low-frequency image
  - low cross-scale support from the next coarser wavelet band
  - low signed local coherence, which random grain lacks but edges keep
  - optional weak candidate support

The output is a soft noise mask, not a hard delete of the whole finest band.
It reports both the structure-gated result and the naive all-finest-band
removal so the target cleanup decision is visible.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import cv2
import numpy as np
import pywt
from PIL import Image
from skimage import color


Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
DASH = RUNS / "dashboard"
sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics  # noqa: E402


DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
DEFAULT_CANDIDATES = (
    "near_miss=b3b767e5d4d2f717",
    "lab_sips=5e7d52579ffb2d3e",
    "lowpass_unet=5b0b0588f497a0cf",
)
PREVIEW = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}


def load_rgb(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(path)
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def to_lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def from_lab(lab_img: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab_img.astype(np.float32)) * 255.0, 0, 255).astype(np.uint8)


def assemble_l(base_lab: np.ndarray, l_chan: np.ndarray) -> np.ndarray:
    out = base_lab.copy()
    out[..., 0] = np.clip(l_chan, 0.0, 100.0)
    return from_lab(out)


def parse_candidate(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        return raw, raw
    label, run_hash = raw.split("=", 1)
    return label.strip(), run_hash.strip()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def crop_path(run_hash: str, image_id: str, kind: str, crop: str) -> Path:
    return RUNS / run_hash / f"{image_id}_{kind}_{crop}.png"


def selected_hf(l_chan: np.ndarray, wavelet: str, levels: int, hf_levels: int) -> np.ndarray:
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


def robust_sigma(x: np.ndarray) -> float:
    med_abs = float(np.median(np.abs(x.astype(np.float32))))
    return max(med_abs / 0.67448975, 1e-6)


def blur(x: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(x.astype(np.float32), (0, 0), sigma).astype(np.float32)


def norm_support(x: np.ndarray, percentile: float = 95.0) -> np.ndarray:
    x = np.maximum(x.astype(np.float32), 0.0)
    scale = float(np.percentile(x, percentile))
    if scale <= 1e-8:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip(x / scale, 0.0, 1.0).astype(np.float32)


def gradient_support(l_chan: np.ndarray) -> np.ndarray:
    lx = cv2.Sobel(l_chan.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    ly = cv2.Sobel(l_chan.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    return norm_support(blur(np.sqrt(lx * lx + ly * ly), 1.0))


def signed_local_coherence(hf: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    numerator = np.abs(blur(hf, sigma))
    denominator = blur(np.abs(hf), sigma) + 1e-6
    return np.clip(numerator / denominator, 0.0, 1.0).astype(np.float32)


def candidate_hf_support(
    candidates: list[np.ndarray],
    ref_hf: np.ndarray,
    wavelet: str,
    levels: int,
) -> np.ndarray:
    if not candidates:
        return np.zeros_like(ref_hf, dtype=np.float32)
    supports = []
    ref_scale = float(np.percentile(np.abs(ref_hf), 95)) + 1e-6
    for lab_img in candidates:
        cand_hf = selected_hf(lab_img[..., 0], wavelet, levels, 1)
        mag_support = np.clip(np.abs(cand_hf) / ref_scale, 0.0, 1.0)
        sign_support = (np.sign(cand_hf) == np.sign(ref_hf)).astype(np.float32)
        supports.append(mag_support * (0.35 + 0.65 * sign_support))
    return np.max(np.stack(supports, axis=0), axis=0).astype(np.float32)


def classify_ref_noise(
    ref_lab: np.ndarray,
    candidate_labs: list[np.ndarray],
    args: argparse.Namespace,
) -> dict[str, np.ndarray | float]:
    ref_l = ref_lab[..., 0].astype(np.float32)
    finest_hf = selected_hf(ref_l, args.wavelet, args.levels, 1)
    two_level_hf = selected_hf(ref_l, args.wavelet, args.levels, min(2, args.levels))
    coarser_hf = two_level_hf - finest_hf
    ref_lf = ref_l - finest_hf

    edge = gradient_support(ref_lf)
    cross = norm_support(blur(np.abs(coarser_hf), 1.2))
    signed = signed_local_coherence(finest_hf, 1.0)
    local_energy = norm_support(blur(np.abs(finest_hf), 1.0))
    cand = candidate_hf_support(candidate_labs, finest_hf, args.wavelet, args.levels)

    signal_score = (
        args.edge_weight * edge
        + args.cross_weight * cross
        + args.coherence_weight * signed
        + args.local_weight * local_energy
        + args.candidate_weight * cand
    )
    weight_sum = (
        args.edge_weight
        + args.cross_weight
        + args.coherence_weight
        + args.local_weight
        + args.candidate_weight
    )
    signal_score = np.clip(signal_score / max(weight_sum, 1e-6), 0.0, 1.0).astype(np.float32)

    sigma = robust_sigma(finest_hf)
    activity = np.clip(np.abs(finest_hf) / (sigma * args.activity_sigma), 0.0, 1.0)
    structure_gate = np.clip(
        (args.signal_cutoff - signal_score) / max(args.signal_cutoff, 1e-6),
        0.0,
        1.0,
    )
    noise_weight = activity * np.power(1.0 - signal_score, args.noise_power) * structure_gate
    noise_weight = blur(noise_weight, args.mask_blur)
    noise_weight = np.clip(noise_weight, 0.0, args.max_noise_weight).astype(np.float32)

    predicted_noise = finest_hf * noise_weight
    retained_signal_hf = finest_hf - predicted_noise
    ref_signal_l = ref_l - predicted_noise
    naive_signal_l = ref_l - finest_hf

    hf_energy = float(np.sum(finest_hf * finest_hf) + 1e-9)
    removed_energy = float(np.sum(predicted_noise * predicted_noise))
    retained_energy = float(np.sum(retained_signal_hf * retained_signal_hf))
    removed_signal_risk = float(
        np.sum((predicted_noise * predicted_noise) * signal_score) / (removed_energy + 1e-9)
    )

    return {
        "ref_l": ref_l,
        "finest_hf": finest_hf,
        "coarser_hf": coarser_hf,
        "edge_support": edge,
        "cross_scale_support": cross,
        "signed_coherence": signed,
        "local_energy": local_energy,
        "candidate_support": cand,
        "signal_score": signal_score,
        "structure_gate": structure_gate,
        "noise_weight": noise_weight,
        "predicted_noise": predicted_noise,
        "retained_signal_hf": retained_signal_hf,
        "ref_signal_l": ref_signal_l,
        "naive_signal_l": naive_signal_l,
        "hf_sigma": sigma,
        "hf_rms": float(np.sqrt(np.mean(finest_hf * finest_hf))),
        "predicted_noise_rms": float(np.sqrt(np.mean(predicted_noise * predicted_noise))),
        "retained_signal_hf_rms": float(np.sqrt(np.mean(retained_signal_hf * retained_signal_hf))),
        "removed_energy_frac": removed_energy / hf_energy,
        "retained_energy_frac": retained_energy / hf_energy,
        "mean_signal_score": float(np.mean(signal_score)),
        "mean_structure_gate": float(np.mean(structure_gate)),
        "mean_noise_weight": float(np.mean(noise_weight)),
        "removed_signal_risk": removed_signal_risk,
        "noise_like_pass": bool(
            removed_energy / hf_energy <= args.max_removed_energy_frac
            and removed_signal_risk <= args.max_removed_signal_risk
        ),
    }


def pass_preview(m: dict) -> bool:
    return (
        m["lpips"] <= PREVIEW["lpips"]
        and m["ms_ssim"] >= PREVIEW["ms_ssim"]
        and m["y_psnr"] >= PREVIEW["y_psnr"]
        and m["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def metric_row(ref: np.ndarray, test: np.ndarray) -> dict:
    h = min(ref.shape[0], test.shape[0])
    w = min(ref.shape[1], test.shape[1])
    m = compute_visual_metrics(ref[:h, :w], test[:h, :w])
    m["preview_pass"] = pass_preview(m)
    return m


def signed_vis(x: np.ndarray) -> np.ndarray:
    scale = float(np.percentile(np.abs(x), 99.0))
    scale = max(scale, 1e-6)
    y = np.clip(0.5 + 0.5 * x.astype(np.float32) / scale, 0.0, 1.0)
    return np.repeat((y * 255.0).astype(np.uint8)[..., None], 3, axis=2)


def gray_vis(x: np.ndarray) -> np.ndarray:
    y = np.clip(x.astype(np.float32), 0.0, 1.0)
    return np.repeat((y * 255.0).astype(np.uint8)[..., None], 3, axis=2)


def save_visuals(image_id: str, ref_lab: np.ndarray, c: dict, out_dir: Path) -> dict[str, str]:
    assets = {
        "ref_signal": assemble_l(ref_lab, c["ref_signal_l"]),
        "naive_no_finest": assemble_l(ref_lab, c["naive_signal_l"]),
        "finest_hf": signed_vis(c["finest_hf"]),
        "predicted_noise": signed_vis(c["predicted_noise"]),
        "retained_signal_hf": signed_vis(c["retained_signal_hf"]),
        "signal_score": gray_vis(c["signal_score"]),
        "structure_gate": gray_vis(c["structure_gate"]),
        "noise_weight": gray_vis(c["noise_weight"]),
        "edge_support": gray_vis(c["edge_support"]),
        "cross_scale_support": gray_vis(c["cross_scale_support"]),
        "signed_coherence": gray_vis(c["signed_coherence"]),
    }
    rels = {}
    for key, img in assets.items():
        path = out_dir / f"{image_id}_{key}.png"
        Image.fromarray(img).save(path)
        rels[key] = str(path.relative_to(DASH))
    return rels


def collect(args: argparse.Namespace) -> tuple[list[dict], list[dict], dict[str, dict[str, str]]]:
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = [parse_candidate(c) for c in args.candidate]
    classifier_rows: list[dict] = []
    metric_rows: list[dict] = []
    assets_by_image: dict[str, dict[str, str]] = {}

    for image_id in args.images:
        ref_rgb = load_rgb(crop_path(args.ref_run, image_id, "REF", args.crop))
        ref_lab = to_lab(ref_rgb)
        Image.fromarray(ref_rgb).save(out_dir / f"{image_id}_REF_original.png")
        candidate_labs = []
        candidate_rgbs: list[tuple[str, str, np.ndarray, np.ndarray]] = []
        for label, run_hash in candidates:
            pipe_rgb = load_rgb(crop_path(run_hash, image_id, "PIPELINE", args.crop))
            pipe_lab = to_lab(pipe_rgb)
            candidate_labs.append(pipe_lab)
            candidate_rgbs.append((label, run_hash, pipe_rgb, pipe_lab))

        classified = classify_ref_noise(ref_lab, candidate_labs, args)
        assets = save_visuals(image_id, ref_lab, classified, out_dir)
        assets["ref_original"] = str((out_dir / f"{image_id}_REF_original.png").relative_to(DASH))
        assets_by_image[image_id] = assets

        ref_signal_rgb = assemble_l(ref_lab, classified["ref_signal_l"])
        naive_rgb = assemble_l(ref_lab, classified["naive_signal_l"])
        for variant, rgb in (("ref_signal_denoised", ref_signal_rgb), ("ref_naive_no_finest", naive_rgb)):
            m = metric_row(ref_rgb, rgb)
            metric_rows.append({
                "image_id": image_id,
                "candidate": "REF",
                "run_hash": args.ref_run,
                "variant": variant,
                "png": assets["ref_signal"] if variant == "ref_signal_denoised" else assets["naive_no_finest"],
                **m,
            })

        classifier_rows.append({
            "image_id": image_id,
            "hf_sigma": classified["hf_sigma"],
            "hf_rms": classified["hf_rms"],
            "predicted_noise_rms": classified["predicted_noise_rms"],
            "retained_signal_hf_rms": classified["retained_signal_hf_rms"],
            "removed_energy_frac": classified["removed_energy_frac"],
            "retained_energy_frac": classified["retained_energy_frac"],
            "mean_signal_score": classified["mean_signal_score"],
            "mean_structure_gate": classified["mean_structure_gate"],
            "mean_noise_weight": classified["mean_noise_weight"],
            "removed_signal_risk": classified["removed_signal_risk"],
            "noise_like_pass": classified["noise_like_pass"],
            "ref_signal_lpips": metric_rows[-2]["lpips"],
            "ref_signal_ms_ssim": metric_rows[-2]["ms_ssim"],
            "naive_no_finest_lpips": metric_rows[-1]["lpips"],
            "naive_no_finest_ms_ssim": metric_rows[-1]["ms_ssim"],
        })

        predicted_noise = classified["predicted_noise"]
        for label, run_hash, pipe_rgb, pipe_lab in candidate_rgbs:
            original = metric_row(ref_rgb, pipe_rgb)
            metric_rows.append({
                "image_id": image_id,
                "candidate": label,
                "run_hash": run_hash,
                "variant": "original_vs_ref",
                "png": f"../{run_hash}/{image_id}_PIPELINE_{args.crop}.png",
                **original,
            })
            vs_signal = metric_row(ref_signal_rgb, pipe_rgb)
            metric_rows.append({
                "image_id": image_id,
                "candidate": label,
                "run_hash": run_hash,
                "variant": "candidate_vs_ref_signal",
                "png": f"../{run_hash}/{image_id}_PIPELINE_{args.crop}.png",
                **vs_signal,
                "delta_lpips_vs_original": vs_signal["lpips"] - original["lpips"],
                "delta_ms_ssim_vs_original": vs_signal["ms_ssim"] - original["ms_ssim"],
            })
            exact_noise_rgb = assemble_l(pipe_lab, pipe_lab[..., 0] + args.noise_gain * predicted_noise)
            name = f"{image_id}_{safe_name(label)}_exact_pred_noise_added.png"
            Image.fromarray(exact_noise_rgb).save(out_dir / name)
            exact = metric_row(ref_rgb, exact_noise_rgb)
            metric_rows.append({
                "image_id": image_id,
                "candidate": label,
                "run_hash": run_hash,
                "variant": "exact_pred_noise_added",
                "png": str((out_dir / name).relative_to(DASH)),
                **exact,
                "delta_lpips_vs_original": exact["lpips"] - original["lpips"],
                "delta_ms_ssim_vs_original": exact["ms_ssim"] - original["ms_ssim"],
            })
    return classifier_rows, metric_rows, assets_by_image


def summarize_metrics(rows: list[dict]) -> list[dict]:
    out = []
    keys = sorted({(r["candidate"], r["variant"]) for r in rows})
    for candidate, variant in keys:
        group = [r for r in rows if r["candidate"] == candidate and r["variant"] == variant]
        worst = max(group, key=lambda r: (r["lpips"], -r["ms_ssim"]))
        out.append({
            "candidate": candidate,
            "variant": variant,
            "count": len(group),
            "pass_count": sum(1 for r in group if r["preview_pass"]),
            "worst_image": worst["image_id"],
            "worst_lpips": max(float(r["lpips"]) for r in group),
            "median_lpips": float(np.median([r["lpips"] for r in group])),
            "worst_ms_ssim": min(float(r["ms_ssim"]) for r in group),
            "median_ms_ssim": float(np.median([r["ms_ssim"] for r in group])),
            "worst_y_psnr": min(float(r["y_psnr"]) for r in group),
            "worst_dE2000_mean": max(float(r["dE2000_mean"]) for r in group),
            "mean_delta_lpips": float(np.mean([r.get("delta_lpips_vs_original", 0.0) for r in group])),
            "mean_delta_ms_ssim": float(np.mean([r.get("delta_ms_ssim_vs_original", 0.0) for r in group])),
        })
    return out


def fmt(v: object, digits: int = 4) -> str:
    if v is None:
        return "-"
    if isinstance(v, str):
        return html.escape(v)
    if isinstance(v, bool):
        return "PASS" if v else "FAIL"
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return str(v)
    return f"{float(v):.{digits}f}"


def write_html(
    classifier_rows: list[dict],
    metric_rows: list[dict],
    summary: list[dict],
    assets_by_image: dict[str, dict[str, str]],
    args: argparse.Namespace,
) -> None:
    args.output_html.parent.mkdir(parents=True, exist_ok=True)
    css = """
body { margin: 18px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background: #f5f5f1; color: #202124; }
h1 { font-size: 22px; margin: 0 0 6px; }
h2 { font-size: 18px; margin: 28px 0 10px; }
p { max-width: 1160px; line-height: 1.45; color: #555; }
table { border-collapse: collapse; background: #fff; font-size: 12px; margin: 12px 0 20px; }
th, td { border: 1px solid #d8d8d1; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #e8e8e1; }
.pass { color: #0a6f2a; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
.strip { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 14px; }
.card { flex: 0 0 536px; width: 536px; box-sizing: border-box; background: white; border: 1px solid #d6d6cf; border-radius: 6px; padding: 10px; }
.title { font-size: 13px; font-weight: 700; line-height: 1.3; min-height: 34px; }
.meta { font-size: 12px; color: #555; line-height: 1.35; margin: 6px 0; min-height: 76px; }
img { display: block; width: 512px; height: 512px; max-width: none; border: 1px solid #cfcfca; background: #111; object-fit: contain; }
"""
    class_rows = []
    for row in classifier_rows:
        cls = "pass" if row["noise_like_pass"] else "fail"
        class_rows.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['image_id'])}</td>"
            f"<td class='{cls}'>{fmt(row['noise_like_pass'])}</td>"
            f"<td>{fmt(row['removed_energy_frac'])}</td><td>{fmt(row['removed_signal_risk'])}</td>"
            f"<td>{fmt(row['mean_signal_score'])}</td><td>{fmt(row['mean_structure_gate'])}</td><td>{fmt(row['mean_noise_weight'])}</td>"
            f"<td>{fmt(row['hf_rms'])}</td><td>{fmt(row['predicted_noise_rms'])}</td>"
            f"<td>{fmt(row['retained_signal_hf_rms'])}</td>"
            f"<td>{fmt(row['ref_signal_lpips'])}</td><td>{fmt(row['ref_signal_ms_ssim'])}</td>"
            f"<td>{fmt(row['naive_no_finest_lpips'])}</td><td>{fmt(row['naive_no_finest_ms_ssim'])}</td>"
            "</tr>"
        )

    sum_rows = []
    for row in summary:
        cls = "pass" if row["pass_count"] == row["count"] else "fail"
        sum_rows.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['candidate'])}</td>"
            f"<td class='left'>{html.escape(row['variant'])}</td>"
            f"<td class='{cls}'>{row['pass_count']}/{row['count']}</td>"
            f"<td class='left'>{html.escape(row['worst_image'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td><td>{fmt(row['median_lpips'])}</td>"
            f"<td>{fmt(row['worst_ms_ssim'])}</td><td>{fmt(row['median_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'], 2)}</td><td>{fmt(row['worst_dE2000_mean'], 2)}</td>"
            f"<td>{fmt(row['mean_delta_lpips'])}</td><td>{fmt(row['mean_delta_ms_ssim'])}</td>"
            "</tr>"
        )

    sections = []
    for image_id in args.images:
        assets = assets_by_image[image_id]
        cards = []
        for title, key, note in (
            ("REF original", "ref_original", "Original crop."),
            ("REF signal target", "ref_signal", "Only structure-gated predicted noise removed."),
            ("Naive no finest band", "naive_no_finest", "Whole finest wavelet band removed."),
            ("Finest HF", "finest_hf", "Signed visualization of the full finest wavelet band."),
            ("Predicted noise", "predicted_noise", "Signed visualization of removed HF."),
            ("Retained signal HF", "retained_signal_hf", "Signed visualization of HF kept as signal."),
            ("Signal score", "signal_score", "White means coherent/structured."),
            ("Structure gate", "structure_gate", "White means low structure and eligible for removal."),
            ("Noise weight", "noise_weight", "White means final removal weight."),
            ("Edge support", "edge_support", "Low-frequency gradient support."),
            ("Cross-scale support", "cross_scale_support", "Next-coarser wavelet support."),
            ("Signed coherence", "signed_coherence", "Local signed coherence."),
        ):
            cards.append(
                "<article class='card'>"
                f"<div class='title'>{html.escape(title)}</div>"
                f"<div class='meta'>{html.escape(note)}</div>"
                f"<img src='{html.escape(assets[key])}'></article>"
            )
        for row in [r for r in metric_rows if r["image_id"] == image_id and r["candidate"] != "REF"]:
            cls = "pass" if row["preview_pass"] else "fail"
            cards.append(
                "<article class='card'>"
                f"<div class='title'>{html.escape(row['candidate'])}<br>{html.escape(row['variant'])}</div>"
                f"<div class='meta'><code>{html.escape(row['run_hash'])}</code><br>"
                f"<span class='{cls}'>LPIPS {row['lpips']:.4f} / MS {row['ms_ssim']:.4f}</span><br>"
                f"Y {row['y_psnr']:.2f} / dE {row['dE2000_mean']:.2f}<br>"
                f"dLPIPS {fmt(row.get('delta_lpips_vs_original'))} / dMS {fmt(row.get('delta_ms_ssim_vs_original'))}"
                "</div>"
                f"<img src='{html.escape(row['png'])}'></article>"
            )
        sections.append(f"<h2>{html.escape(image_id)} 100% crops</h2><div class='strip'>{''.join(cards)}</div>")

    args.output_html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Noise/signal HF classifier</title>"
        f"<style>{css}</style></head><body>"
        "<h1>Noise/signal HF classifier</h1>"
        "<p>This is the pre-training guard for cleaned REF targets. The structure-gated target should remove only stochastic finest-scale Lab-L energy. "
        "If the naive no-finest-band image is visibly smoother or has much worse metrics than the structure-gated target, blindly removing that band is too aggressive. "
        f"Wavelet <code>{html.escape(args.wavelet)}</code>, levels <code>{args.levels}</code>, activity sigma <code>{args.activity_sigma}</code>.</p>"
        "<table><thead><tr><th class='left'>image</th><th>noise-like</th><th>removed energy</th><th>removed risk</th>"
        "<th>mean signal</th><th>mean gate</th><th>mean weight</th><th>HF RMS</th><th>noise RMS</th><th>kept RMS</th>"
        "<th>target LPIPS</th><th>target MS</th><th>naive LPIPS</th><th>naive MS</th></tr></thead><tbody>"
        f"{''.join(class_rows)}</tbody></table>"
        "<table><thead><tr><th class='left'>candidate</th><th class='left'>variant</th><th>pass</th><th class='left'>worst image</th>"
        "<th>worst LPIPS</th><th>median LPIPS</th><th>worst MS</th><th>median MS</th><th>worst Y</th><th>worst dE</th>"
        "<th>mean dLPIPS</th><th>mean dMS</th></tr></thead><tbody>"
        f"{''.join(sum_rows)}</tbody></table>"
        f"{''.join(sections)}</body></html>"
    )


class _ImageSrcParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.srcs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        src = dict(attrs).get("src")
        if src:
            self.srcs.append(src)


def validate_html_images(html_path: Path) -> None:
    parser = _ImageSrcParser()
    parser.feed(html_path.read_text())
    missing = []
    for src in parser.srcs:
        if not (html_path.parent / src).resolve().exists():
            missing.append(src)
    if missing:
        preview = ", ".join(missing[:8])
        extra = "" if len(missing) <= 8 else f", ... +{len(missing) - 8} more"
        raise RuntimeError(f"{html_path} references {len(missing)} missing image(s): {preview}{extra}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ref-run", default="5e7d52579ffb2d3e")
    ap.add_argument("--candidate", action="append", default=None)
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument("--crop", default="crop_A_detail")
    ap.add_argument("--wavelet", default="sym4")
    ap.add_argument("--levels", type=int, default=3)
    ap.add_argument("--activity-sigma", type=float, default=0.8)
    ap.add_argument("--noise-power", type=float, default=1.35)
    ap.add_argument("--signal-cutoff", type=float, default=0.35,
                    help="Only HF below this structure score is eligible for noise removal.")
    ap.add_argument("--mask-blur", type=float, default=0.5)
    ap.add_argument("--max-noise-weight", type=float, default=0.95)
    ap.add_argument("--noise-gain", type=float, default=1.0)
    ap.add_argument("--edge-weight", type=float, default=0.30)
    ap.add_argument("--cross-weight", type=float, default=0.25)
    ap.add_argument("--coherence-weight", type=float, default=0.25)
    ap.add_argument("--local-weight", type=float, default=0.10)
    ap.add_argument("--candidate-weight", type=float, default=0.10)
    ap.add_argument("--max-removed-energy-frac", type=float, default=0.35)
    ap.add_argument("--max-removed-signal-risk", type=float, default=0.30)
    ap.add_argument("--output-dir", type=Path, default=DASH / "noise_signal_classifier")
    ap.add_argument("--output-json", type=Path, default=DASH / "noise_signal_classifier.json")
    ap.add_argument("--output-html", type=Path, default=DASH / "noise_signal_classifier.html")
    args = ap.parse_args()
    if args.candidate is None:
        args.candidate = list(DEFAULT_CANDIDATES)
    args.output_dir = args.output_dir.resolve()
    args.output_json = args.output_json.resolve()
    args.output_html = args.output_html.resolve()

    classifier_rows, metric_rows, assets = collect(args)
    summary = summarize_metrics(metric_rows)
    payload = {
        "thresholds": PREVIEW,
        "args": {
            "ref_run": args.ref_run,
            "candidate": args.candidate,
            "images": args.images,
            "crop": args.crop,
            "wavelet": args.wavelet,
            "levels": args.levels,
            "activity_sigma": args.activity_sigma,
            "noise_power": args.noise_power,
            "signal_cutoff": args.signal_cutoff,
            "max_removed_energy_frac": args.max_removed_energy_frac,
            "max_removed_signal_risk": args.max_removed_signal_risk,
        },
        "classifier_rows": classifier_rows,
        "summary": summary,
        "metric_rows": metric_rows,
    }
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(classifier_rows, metric_rows, summary, assets, args)
    validate_html_images(args.output_html)
    for row in classifier_rows:
        verdict = "PASS" if row["noise_like_pass"] else "FAIL"
        print(
            f"{row['image_id']:<8} {verdict:<4} removed={row['removed_energy_frac']:.3f} "
            f"risk={row['removed_signal_risk']:.3f} target_lpips={row['ref_signal_lpips']:.4f} "
            f"naive_lpips={row['naive_no_finest_lpips']:.4f}"
        )
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
