#!/usr/bin/env python3
"""Full-gate PREVIEW L/detail donor oracle.

This diagnostic keeps the active Lab/SIPS candidate's a/b chroma and swaps in
different Lab-L/detail donors at full-image scale. It answers whether an
existing donor can clear PREVIEW, or whether the remaining blocker needs a new
teacher/source rather than another local postprocess.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import tempfile
from pathlib import Path

import cv2
import lpips
import numpy as np
import torch
from PIL import Image
from pytorch_msssim import ms_ssim
from skimage import color

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gate import compute_visual_metrics, downsample_for_metrics


Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
DASH = RUNS / "dashboard"

DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
PREVIEW = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}


def load_rgb(run_hash: str, image_id: str, kind: str) -> np.ndarray:
    path = RUNS / run_hash / f"{image_id}_{kind}.png"
    if not path.exists():
        raise FileNotFoundError(path)
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def rgb_from_lab(lab_img: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab_img) * 255.0, 0, 255).astype(np.uint8)


def downsample(rgb: np.ndarray, target_w: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    if w <= target_w:
        return rgb
    target_h = int(round(h * (target_w / w)))
    return cv2.resize(rgb, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)


def y_psnr(a: np.ndarray, b: np.ndarray) -> float:
    ay = cv2.cvtColor(a, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    by = cv2.cvtColor(b, cv2.COLOR_RGB2YCrCb)[..., 0].astype(np.float32)
    mse = float(np.mean((ay - by) ** 2))
    if mse <= 1e-12:
        return 99.0
    return float(10.0 * np.log10((255.0 * 255.0) / mse))


_LPIPS = None


def lpips_score(a: np.ndarray, b: np.ndarray) -> float:
    global _LPIPS
    if _LPIPS is None:
        _LPIPS = lpips.LPIPS(net="alex").to("cpu").eval()
    at = torch.from_numpy(a.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    bt = torch.from_numpy(b.astype(np.float32) / 127.5 - 1).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(_LPIPS(at, bt).flatten()[0])


def msssim_score(a: np.ndarray, b: np.ndarray) -> float:
    at = torch.from_numpy(a.astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
    bt = torch.from_numpy(b.astype(np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
    with torch.no_grad():
        return float(ms_ssim(at, bt, data_range=1.0))


def metrics(render: np.ndarray, ref: np.ndarray, target_w: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="preview_oracle_metrics_") as td:
        td_path = Path(td)
        ref_path = td_path / "ref.png"
        render_path = td_path / "render.png"
        Image.fromarray(ref).save(ref_path)
        Image.fromarray(render).save(render_path)
        rr = downsample_for_metrics(ref_path, target_w)
        pr = downsample_for_metrics(render_path, target_w)
    if pr.shape != rr.shape:
        hh = min(rr.shape[0], pr.shape[0])
        ww = min(rr.shape[1], pr.shape[1])
        rr, pr = rr[:hh, :ww], pr[:hh, :ww]
    return compute_visual_metrics(rr, pr)


def pass_preview(row: dict) -> bool:
    return (
        row["lpips"] <= PREVIEW["lpips"]
        and row["ms_ssim"] >= PREVIEW["ms_ssim"]
        and row["y_psnr"] >= PREVIEW["y_psnr"]
        and row["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def assemble_with_l(chroma_rgb: np.ndarray, donor_rgb: np.ndarray) -> np.ndarray:
    base = lab(chroma_rgb)
    donor = lab(donor_rgb)
    out = base.copy()
    out[..., 0] = donor[..., 0]
    return rgb_from_lab(out)


def build_rows(args: argparse.Namespace) -> list[dict]:
    rows = []
    png_dir = DASH / "preview_detail_oracle"
    png_dir.mkdir(parents=True, exist_ok=True)
    extra_donors = []
    for item in args.extra_donor:
        if "=" not in item:
            raise ValueError(f"--extra-donor must be label=run_hash, got {item!r}")
        label, run_hash = item.split("=", 1)
        extra_donors.append((label.strip(), run_hash.strip()))
    default_donors = [
        ("lab_sips", args.lab_run),
        ("s07", args.s07_run),
        ("upresable_L", args.upres_run),
        ("bido_w24_L", args.bido_run),
        ("bibo_cross_L", args.bibo_run),
    ]
    if args.skip_default_donors:
        default_donors = [("lab_sips", args.lab_run)]
    donors = [
        *default_donors,
        *extra_donors,
        ("ref_L_oracle", None),
    ]
    for image_id in args.images:
        ref = load_rgb(args.lab_run, image_id, "REF")
        chroma = load_rgb(args.chroma_run, image_id, "PIPELINE")
        for label, run_hash in donors:
            donor = ref if run_hash is None else load_rgb(run_hash, image_id, "PIPELINE")
            if label == "lab_sips":
                render = chroma
            else:
                render = assemble_with_l(chroma, donor)
            out_name = f"{image_id}_{label}.png"
            if args.write_images:
                Image.fromarray(render).save(png_dir / out_name)
            row = {
                "image_id": image_id,
                "label": label,
                **metrics(render, ref, args.target_width),
            }
            if args.write_images:
                row["png"] = f"preview_detail_oracle/{out_name}"
            row["preview_pass"] = bool(pass_preview(row))
            rows.append(row)
    return rows


def write_html(rows: list[dict], out: Path, include_images: bool) -> None:
    css = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; margin: 24px; background: #f7f7f3; color: #202124; }
h1 { font-size: 24px; margin: 0 0 8px; }
p { max-width: 1080px; color: #555; line-height: 1.45; }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: 12px; }
th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #ecece5; }
.pass { color: #0b6d2b; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; margin: 18px 0; }
figure { margin: 0; background: #fff; border: 1px solid #ddd; padding: 8px; }
img { width: 100%; display: block; }
figcaption { margin-top: 6px; font-size: 12px; color: #555; line-height: 1.35; }
"""
    figs = []
    if include_images:
        worst = sorted(rows, key=lambda r: (r["image_id"], r["lpips"]))
        for row in worst:
            if row["label"] not in ("lab_sips", "upresable_L", "bido_w24_L", "bibo_cross_L", "ref_L_oracle"):
                continue
            figs.append(
                f"<figure><img src='{html.escape(row['png'])}'><figcaption>"
                f"{html.escape(row['image_id'])}<br>{html.escape(row['label'])}<br>"
                f"LPIPS {row['lpips']:.3f} MS {row['ms_ssim']:.3f}</figcaption></figure>"
            )
    trs = []
    for row in rows:
        verdict = "PASS" if row["preview_pass"] else "FAIL"
        cls = "pass" if row["preview_pass"] else "fail"
        trs.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['image_id'])}</td>"
            f"<td class='left'>{html.escape(row['label'])}</td>"
            f"<td>{row['lpips']:.4f}</td>"
            f"<td>{row['ms_ssim']:.4f}</td>"
            f"<td>{row['y_psnr']:.2f}</td>"
            f"<td>{row['dE2000_mean']:.2f}</td>"
            f"<td class='{cls}'>{verdict}</td>"
            "</tr>"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "".join([
            "<!doctype html><html><head><meta charset='utf-8'>",
            f"<title>PREVIEW detail oracle</title><style>{css}</style></head><body>",
            "<h1>PREVIEW Detail Donor Oracle</h1>",
            "<p>Full-image gate-resolution probe. Lab/SIPS a/b chroma is fixed; only Lab L/detail changes. ",
            "This is diagnostic evidence, not a ship pipeline.</p>",
            f"<div class='grid'>{''.join(figs)}</div>" if include_images else "",
            "<table><thead><tr><th class='left'>image</th><th class='left'>donor</th>",
            "<th>LPIPS</th><th>MS-SSIM</th><th>Y-PSNR</th><th>dE mean</th><th>PREVIEW</th></tr></thead><tbody>",
            f"{''.join(trs)}</tbody></table></body></html>",
        ])
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chroma-run", default="5e7d52579ffb2d3e")
    ap.add_argument("--lab-run", default="5e7d52579ffb2d3e")
    ap.add_argument("--s07-run", default="1f1ef2ee138c51c3")
    ap.add_argument("--upres-run", default="8864c12ec0b6ce14")
    ap.add_argument("--bido-run", default="732da314adc90553")
    ap.add_argument("--bibo-run", default="73aae2672bdb19ab")
    ap.add_argument("--extra-donor", action="append", default=[],
                    help="Additional Lab-L donor as label=run_hash. May be repeated.")
    ap.add_argument("--skip-default-donors", action="store_true",
                    help="Only score lab_sips, --extra-donor entries, and ref_L_oracle.")
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument("--target-width", type=int, default=3840)
    ap.add_argument("--write-images", action="store_true")
    ap.add_argument("--output-json", type=Path, default=DASH / "preview_detail_oracle.json")
    ap.add_argument("--output-html", type=Path, default=DASH / "preview_detail_oracle.html")
    args = ap.parse_args()

    rows = build_rows(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(rows, indent=2))
    write_html(rows, args.output_html, include_images=args.write_images)
    for row in rows:
        verdict = "PASS" if row["preview_pass"] else "FAIL"
        print(
            f"{row['image_id']} {row['label']:<14} LPIPS={row['lpips']:.4f} "
            f"MS={row['ms_ssim']:.4f} Y={row['y_psnr']:.2f} "
            f"dE={row['dE2000_mean']:.2f} {verdict}"
        )
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
