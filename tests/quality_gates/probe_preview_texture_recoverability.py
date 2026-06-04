#!/usr/bin/env python3
"""PREVIEW texture/detail recoverability probe.

This diagnostic keeps the active Lab/SIPS a/b chroma fixed and asks a narrower
question than the donor-blend oracle: is the remaining hard-tail PREVIEW
failure caused by missing bandwidth in the half-res capture substrate, or by
the current models/objectives failing to place recoverable detail?

It scores:
  - current candidate L donors,
  - full-reference L oracle,
  - reference L low-passed to 2x / 4x / 8x bandwidth and re-upsampled.

If 2x-lowpass reference L passes but 4x-lowpass reference L fails, the needed
detail is within the half-res Bayer sample grid but above a naive packed-plane
low-pass view. That points at phase-aware/full-context modeling or a different
decoded-Bayer detail path, not another local single-channel Y tile head.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage import color

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gate import compute_visual_metrics  # noqa: E402


Image.MAX_IMAGE_PIXELS = None

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "tests/quality_gates/runs"
DASH = RUNS / "dashboard"

DEFAULT_IMAGES = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")
DEFAULT_DONORS = (
    "lab_sips=5e7d52579ffb2d3e",
    "sl_dec2_y=105573235badb6f2",
    "upresable=8864c12ec0b6ce14",
    "bibo_cross=73aae2672bdb19ab",
)
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


def to_lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def from_lab(lab_img: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab_img) * 255.0, 0, 255).astype(np.uint8)


def downsample_rgb(rgb: np.ndarray, target_width: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    if w <= target_width:
        return rgb
    th = int(round(h * (target_width / w)))
    return cv2.resize(rgb, (target_width, th), interpolation=cv2.INTER_LANCZOS4)


def resize_l(l_chan: np.ndarray, factor: int) -> np.ndarray:
    h, w = l_chan.shape
    small = cv2.resize(
        l_chan,
        (max(1, w // factor), max(1, h // factor)),
        interpolation=cv2.INTER_AREA,
    )
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)


def assemble(base_lab: np.ndarray, l_chan: np.ndarray) -> np.ndarray:
    out = base_lab.copy()
    out[..., 0] = np.clip(l_chan, 0.0, 100.0)
    return from_lab(out)


def score(render: np.ndarray, ref: np.ndarray, target_width: int) -> dict:
    rr = downsample_rgb(ref, target_width)
    pr = downsample_rgb(render, target_width)
    h = min(rr.shape[0], pr.shape[0])
    w = min(rr.shape[1], pr.shape[1])
    return compute_visual_metrics(rr[:h, :w], pr[:h, :w])


def passes(m: dict) -> bool:
    return (
        m["lpips"] <= PREVIEW["lpips"]
        and m["ms_ssim"] >= PREVIEW["ms_ssim"]
        and m["y_psnr"] >= PREVIEW["y_psnr"]
        and m["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def band_stats(ref_l: np.ndarray, cand_l: np.ndarray, target_width: int) -> dict:
    ref = downsample_rgb(np.repeat(ref_l[..., None], 3, axis=2).astype(np.uint8), target_width)[..., 0]
    cand = downsample_rgb(np.repeat(cand_l[..., None], 3, axis=2).astype(np.uint8), target_width)[..., 0]
    ref = ref.astype(np.float32)
    cand = cand.astype(np.float32)
    h = min(ref.shape[0], cand.shape[0])
    w = min(ref.shape[1], cand.shape[1])
    ref = ref[:h, :w]
    cand = cand[:h, :w]

    out: dict[str, float] = {}
    for sigma in (1.5, 3.0, 6.0):
        r_hp = ref - cv2.GaussianBlur(ref, (0, 0), sigma)
        c_hp = cand - cv2.GaussianBlur(cand, (0, 0), sigma)
        r0 = r_hp - float(r_hp.mean())
        c0 = c_hp - float(c_hp.mean())
        denom = float(np.sqrt(np.sum(r0 * r0) * np.sum(c0 * c0))) + 1e-9
        corr = float(np.sum(r0 * c0) / denom)
        rms_ratio = float((np.sqrt(np.mean(c_hp * c_hp)) + 1e-9) / (np.sqrt(np.mean(r_hp * r_hp)) + 1e-9))
        out[f"hp_corr_s{sigma:g}"] = corr
        out[f"hp_rms_ratio_s{sigma:g}"] = rms_ratio

    rgx = cv2.Sobel(ref, cv2.CV_32F, 1, 0, ksize=3)
    rgy = cv2.Sobel(ref, cv2.CV_32F, 0, 1, ksize=3)
    cgx = cv2.Sobel(cand, cv2.CV_32F, 1, 0, ksize=3)
    cgy = cv2.Sobel(cand, cv2.CV_32F, 0, 1, ksize=3)
    rmag = np.sqrt(rgx * rgx + rgy * rgy)
    cmag = np.sqrt(cgx * cgx + cgy * cgy)
    dot = rgx * cgx + rgy * cgy
    orient = dot / (rmag * cmag + 1e-6)
    weight = np.minimum(rmag, cmag)
    out["grad_mag_ratio"] = float((cmag.mean() + 1e-9) / (rmag.mean() + 1e-9))
    out["grad_orient_coherence"] = float(np.sum(orient * weight) / (np.sum(weight) + 1e-9))
    return out


def parse_donor(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ValueError(f"donor must be label=run_hash, got {raw!r}")
    label, run_hash = raw.split("=", 1)
    return label.strip(), run_hash.strip()


def collect(args: argparse.Namespace) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    missing: list[str] = []
    donors = [parse_donor(d) for d in args.donor]
    for image_id in args.images:
        print(f"[recoverability] {image_id}", flush=True)
        ref = load_rgb(args.ref_run, image_id, "REF")
        chroma = load_rgb(args.chroma_run, image_id, "PIPELINE")
        h = min(ref.shape[0], chroma.shape[0])
        w = min(ref.shape[1], chroma.shape[1])
        ref = ref[:h, :w]
        chroma = chroma[:h, :w]
        ref_l = to_lab(ref)[..., 0]
        base_lab = to_lab(chroma)

        candidates: list[tuple[str, np.ndarray]] = [
            ("ref_L_oracle", ref_l),
            ("ref_L_lowpass_x2", resize_l(ref_l, 2)),
            ("ref_L_lowpass_x4", resize_l(ref_l, 4)),
            ("ref_L_lowpass_x8", resize_l(ref_l, 8)),
        ]
        for label, run_hash in donors:
            try:
                donor = load_rgb(run_hash, image_id, "PIPELINE")[:h, :w]
            except FileNotFoundError as exc:
                missing.append(str(exc))
                continue
            candidates.append((label, to_lab(donor)[..., 0]))

        for label, cand_l in candidates:
            render = assemble(base_lab, cand_l)
            m = score(render, ref, args.target_width)
            row = {
                "image_id": image_id,
                "candidate": label,
                **m,
                **band_stats(ref_l, cand_l, args.signal_width),
            }
            row["preview_pass"] = passes(row)
            rows.append(row)
            print(
                f"  {label:<18} LPIPS={row['lpips']:.4f} "
                f"MS={row['ms_ssim']:.4f} HPcorr={row['hp_corr_s3']:.3f} "
                f"{'PASS' if row['preview_pass'] else 'FAIL'}",
                flush=True,
            )
    return rows, sorted(set(missing))


def aggregate(rows: list[dict]) -> list[dict]:
    out = []
    for cand in sorted({r["candidate"] for r in rows}):
        cr = [r for r in rows if r["candidate"] == cand]
        worst = max(cr, key=lambda r: (r["lpips"], -r["ms_ssim"]))
        out.append({
            "candidate": cand,
            "all_pass": all(r["preview_pass"] for r in cr),
            "worst_image": worst["image_id"],
            "worst_lpips": worst["lpips"],
            "worst_ms_ssim": min(r["ms_ssim"] for r in cr),
            "worst_y_psnr": min(r["y_psnr"] for r in cr),
            "worst_dE2000_mean": max(r["dE2000_mean"] for r in cr),
            "mean_hp_corr_s3": float(np.mean([r["hp_corr_s3"] for r in cr])),
            "worst_hp_corr_s3": min(r["hp_corr_s3"] for r in cr),
        })
    out.sort(key=lambda r: (not r["all_pass"], r["worst_lpips"], -r["mean_hp_corr_s3"]))
    return out


def conclusion(summary: list[dict]) -> str:
    by = {r["candidate"]: r for r in summary}
    low2 = by.get("ref_L_lowpass_x2")
    low4 = by.get("ref_L_lowpass_x4")
    if not low2 or not low4:
        return "Low-pass reference rows were not produced."
    if low2["all_pass"] and not low4["all_pass"]:
        return (
            "x2 bandwidth-limited reference L passes, but x4 bandwidth-limited "
            "reference L fails on the hard-tail images. The missing detail is "
            "within the half-res Bayer sample grid, but not in a naive packed-"
            "plane low-pass representation. The next candidate should be "
            "phase-aware/full-context over decoded Bayer or use a different "
            "detail path, not another local Y tile head or fixed donor blend."
        )
    if low2["all_pass"] and low4["all_pass"]:
        return (
            "x2 and x4 bandwidth-limited reference L both pass the PREVIEW gate "
            "with the solved Lab/SIPS chroma. The blocker is model/context/loss "
            "detail placement, not capture bandwidth."
        )
    if low4["all_pass"]:
        return (
            "x4 bandwidth-limited reference L passes the PREVIEW gate with the "
            "solved Lab/SIPS chroma. The half-res bandwidth is not the primary "
            "blocker; current learned candidates are failing model/context/loss "
            "detail placement."
        )
    return (
        "Even x2 bandwidth-limited reference L does not pass the PREVIEW gate "
        "with the solved Lab/SIPS chroma. The hard-tail blocker needs either a "
        "different capture/downsample substrate or an explicit hallucinated-"
        "detail objective beyond recoverable half-res signal."
    )


def write_html(rows: list[dict], summary: list[dict], missing: list[str], out: Path) -> None:
    def fmt(v: float) -> str:
        return f"{v:.4f}" if abs(v) < 10 else f"{v:.2f}"

    css = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; margin: 24px; background: #f7f8f5; color: #202124; }
h1 { font-size: 24px; margin: 0 0 8px; }
p { max-width: 1120px; color: #555; line-height: 1.45; }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: 12px; margin: 16px 0; }
th, td { border: 1px solid #d8dde1; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #edf0eb; }
.pass { color: #0b6d2b; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
.note { padding: 12px 14px; background: #fff; border-left: 4px solid #6a7f8f; margin: 16px 0; }
"""
    summary_rows = []
    for row in summary:
        cls = "pass" if row["all_pass"] else "fail"
        summary_rows.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['candidate'])}</td>"
            f"<td class='{cls}'>{'PASS' if row['all_pass'] else 'FAIL'}</td>"
            f"<td class='left'>{html.escape(row['worst_image'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td>"
            f"<td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td>"
            f"<td>{fmt(row['worst_dE2000_mean'])}</td>"
            f"<td>{fmt(row['mean_hp_corr_s3'])}</td>"
            f"<td>{fmt(row['worst_hp_corr_s3'])}</td>"
            "</tr>"
        )
    detail_rows = []
    for row in sorted(rows, key=lambda r: (r["image_id"], r["lpips"])):
        cls = "pass" if row["preview_pass"] else "fail"
        detail_rows.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['image_id'])}</td>"
            f"<td class='left'>{html.escape(row['candidate'])}</td>"
            f"<td>{fmt(row['lpips'])}</td>"
            f"<td>{fmt(row['ms_ssim'])}</td>"
            f"<td>{fmt(row['y_psnr'])}</td>"
            f"<td>{fmt(row['dE2000_mean'])}</td>"
            f"<td>{fmt(row['hp_corr_s1.5'])}</td>"
            f"<td>{fmt(row['hp_corr_s3'])}</td>"
            f"<td>{fmt(row['hp_corr_s6'])}</td>"
            f"<td>{fmt(row['grad_orient_coherence'])}</td>"
            f"<td class='{cls}'>{'PASS' if row['preview_pass'] else 'FAIL'}</td>"
            "</tr>"
        )
    missing_html = ""
    if missing:
        missing_html = "<p><b>Missing donor PNGs:</b><br>" + "<br>".join(html.escape(m) for m in missing) + "</p>"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>PREVIEW texture recoverability</title><style>{css}</style></head><body>"
        "<h1>PREVIEW Texture Recoverability</h1>"
        "<p>Lab a/b chroma is fixed from the active Lab/SIPS baseline. Rows vary "
        "only Lab L/detail and report gate metrics plus signal-alignment stats.</p>"
        f"<div class='note'>{html.escape(conclusion(summary))}</div>"
        f"{missing_html}"
        "<h2>Global candidates</h2><table><thead><tr>"
        "<th class='left'>candidate</th><th>all pass</th><th class='left'>worst image</th>"
        "<th>worst LPIPS</th><th>worst MS-SSIM</th><th>worst Y-PSNR</th><th>worst dE</th>"
        "<th>mean HP corr s3</th><th>worst HP corr s3</th></tr></thead><tbody>"
        f"{''.join(summary_rows)}</tbody></table>"
        "<h2>Per-image detail signal</h2><table><thead><tr>"
        "<th class='left'>image</th><th class='left'>candidate</th>"
        "<th>LPIPS</th><th>MS-SSIM</th><th>Y-PSNR</th><th>dE</th>"
        "<th>HP corr s1.5</th><th>HP corr s3</th><th>HP corr s6</th>"
        "<th>grad orient</th><th>PREVIEW</th></tr></thead><tbody>"
        f"{''.join(detail_rows)}</tbody></table></body></html>"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chroma-run", default="5e7d52579ffb2d3e")
    ap.add_argument("--ref-run", default="5e7d52579ffb2d3e")
    ap.add_argument("--donor", action="append", default=list(DEFAULT_DONORS))
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument("--target-width", type=int, default=3840)
    ap.add_argument("--signal-width", type=int, default=1920)
    ap.add_argument("--output-json", type=Path, default=DASH / "preview_texture_recoverability.json")
    ap.add_argument("--output-html", type=Path, default=DASH / "preview_texture_recoverability.html")
    args = ap.parse_args()

    rows, missing = collect(args)
    summary = aggregate(rows)
    payload = {
        "preview_thresholds": PREVIEW,
        "target_width": args.target_width,
        "signal_width": args.signal_width,
        "conclusion": conclusion(summary),
        "summary": summary,
        "rows": rows,
        "missing": missing,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(rows, summary, missing, args.output_html)

    print("\n=== summary ===")
    for row in summary:
        print(
            f"{'PASS' if row['all_pass'] else 'FAIL':4} {row['candidate']:<20} "
            f"worst={row['worst_image']} LPIPS={row['worst_lpips']:.4f} "
            f"MSmin={row['worst_ms_ssim']:.4f} HPcorrMean={row['mean_hp_corr_s3']:.3f}"
        )
    print(conclusion(summary))
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
