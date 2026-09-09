#!/usr/bin/env python3
"""Full-image PREVIEW Lab-L donor/blend oracle.

The remaining PREVIEW blocker is detail placement with acceptable Lab chroma.
This diagnostic keeps the chosen chroma run's Lab a/b fixed and evaluates
whether existing full-image L donors, or simple pairwise blends of those
donors, can clear the production PREVIEW gate. If the oracle cannot clear the
gate, the next work needs a better upstream detail source/teacher, not more
post-hoc donor selection.
"""
from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
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
    "s07=1f1ef2ee138c51c3",
    "upresable=8864c12ec0b6ce14",
    "sl_dec2_y=105573235badb6f2",
    "bibo_cross=73aae2672bdb19ab",
)
PREVIEW = {
    "lpips": 0.15,
    "ms_ssim": 0.95,
    "y_psnr": 28.0,
    "dE2000_mean": 3.0,
}


@dataclass(frozen=True)
class Donor:
    label: str
    run_hash: str


def parse_donor(item: str) -> Donor:
    if "=" not in item:
        raise ValueError(f"donor must be label=run_hash, got {item!r}")
    label, run_hash = item.split("=", 1)
    return Donor(label.strip(), run_hash.strip())


def load_rgb(run_hash: str, image_id: str, kind: str) -> np.ndarray:
    path = RUNS / run_hash / f"{image_id}_{kind}.png"
    if not path.exists():
        raise FileNotFoundError(path)
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def to_lab(rgb: np.ndarray) -> np.ndarray:
    return color.rgb2lab(rgb.astype(np.float32) / 255.0).astype(np.float32)


def from_lab(lab: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)


def assemble(base_lab: np.ndarray, l_chan: np.ndarray) -> np.ndarray:
    out = base_lab.copy()
    out[..., 0] = np.clip(l_chan, 0.0, 100.0)
    return from_lab(out)


def downsample_rgb(rgb: np.ndarray, target_width: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    if w <= target_width:
        return rgb
    target_height = int(round(h * (target_width / w)))
    return cv2.resize(rgb, (target_width, target_height), interpolation=cv2.INTER_LANCZOS4)


def score(render: np.ndarray, ref: np.ndarray, target_width: int) -> dict:
    ref_eval = downsample_rgb(ref, target_width)
    render_eval = downsample_rgb(render, target_width)
    h = min(ref_eval.shape[0], render_eval.shape[0])
    w = min(ref_eval.shape[1], render_eval.shape[1])
    return compute_visual_metrics(ref_eval[:h, :w], render_eval[:h, :w])


def passes(m: dict) -> bool:
    return all(
        m[k] <= v if k in ("lpips", "dE2000_mean") else m[k] >= v
        for k, v in PREVIEW.items()
    )


def candidate_l_channels(donor_l: dict[str, np.ndarray],
                         alphas: list[float]) -> list[tuple[str, np.ndarray]]:
    labels = list(donor_l)
    out: list[tuple[str, np.ndarray]] = [(label, donor_l[label]) for label in labels]
    for i, a_label in enumerate(labels):
        for b_label in labels[i + 1:]:
            a_l = donor_l[a_label]
            b_l = donor_l[b_label]
            for alpha in alphas:
                out.append((
                    f"blend:{a_label}:{b_label}:a={alpha:.2f}",
                    alpha * a_l + (1.0 - alpha) * b_l,
                ))
    return out


def collect(args: argparse.Namespace) -> tuple[list[dict], list[str]]:
    donors = [parse_donor(item) for item in args.donor]
    alphas = [float(x) for x in args.alphas.split(",") if x.strip()]
    rows: list[dict] = []
    missing: list[str] = []
    for image_id in args.images:
        print(f"[oracle] image {image_id}", flush=True)
        ref = load_rgb(args.ref_run, image_id, "REF")
        chroma = load_rgb(args.chroma_run, image_id, "PIPELINE")
        base_lab = to_lab(chroma)
        donor_l: dict[str, np.ndarray] = {}
        for donor in donors:
            try:
                donor_rgb = load_rgb(donor.run_hash, image_id, "PIPELINE")
            except FileNotFoundError as exc:
                missing.append(str(exc))
                continue
            h = min(base_lab.shape[0], donor_rgb.shape[0], ref.shape[0])
            w = min(base_lab.shape[1], donor_rgb.shape[1], ref.shape[1])
            donor_l[donor.label] = to_lab(donor_rgb[:h, :w])[..., 0]
        if not donor_l:
            continue
        h = min([base_lab.shape[0], ref.shape[0], *[v.shape[0] for v in donor_l.values()]])
        w = min([base_lab.shape[1], ref.shape[1], *[v.shape[1] for v in donor_l.values()]])
        base_crop = base_lab[:h, :w]
        ref_crop = ref[:h, :w]
        candidates = candidate_l_channels({k: v[:h, :w] for k, v in donor_l.items()}, alphas)
        for idx, (label, l_chan) in enumerate(candidates, start=1):
            if args.progress:
                print(
                    f"[oracle]   {idx:02d}/{len(candidates):02d} {label}",
                    flush=True,
                )
            render = assemble(base_crop, l_chan[:h, :w])
            m = score(render, ref_crop, args.target_width)
            rows.append({
                "image_id": image_id,
                "label": label,
                **m,
                "preview_pass": passes(m),
            })
    return rows, sorted(set(missing))


def aggregate(rows: list[dict]) -> list[dict]:
    labels = sorted({r["label"] for r in rows})
    out = []
    for label in labels:
        lr = [r for r in rows if r["label"] == label]
        if not lr:
            continue
        worst = max(lr, key=lambda r: (r["lpips"], -r["ms_ssim"]))
        out.append({
            "label": label,
            "all_pass": all(r["preview_pass"] for r in lr),
            "worst_image": worst["image_id"],
            "worst_lpips": worst["lpips"],
            "worst_ms_ssim": worst["ms_ssim"],
            "worst_y_psnr": min(r["y_psnr"] for r in lr),
            "worst_dE2000_mean": max(r["dE2000_mean"] for r in lr),
        })
    out.sort(key=lambda r: (not r["all_pass"], r["worst_lpips"], -r["worst_ms_ssim"]))
    return out


def write_html(rows: list[dict], summary: list[dict], missing: list[str], out: Path) -> None:
    def fmt(v: float) -> str:
        return f"{v:.4f}" if abs(v) < 10 else f"{v:.2f}"

    css = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; margin: 24px; background: #f6f7f8; color: #202124; }
h1 { font-size: 24px; margin: 0 0 8px; }
p { color: #555; max-width: 1120px; line-height: 1.45; }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: 12px; margin: 16px 0; }
th, td { border: 1px solid #d9dee5; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #edf1f5; }
.pass { color: #0b6d2b; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
"""
    summary_rows = []
    for row in summary:
        cls = "pass" if row["all_pass"] else "fail"
        summary_rows.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['label'])}</td>"
            f"<td class='{cls}'>{'PASS' if row['all_pass'] else 'FAIL'}</td>"
            f"<td class='left'>{html.escape(row['worst_image'])}</td>"
            f"<td>{fmt(row['worst_lpips'])}</td>"
            f"<td>{fmt(row['worst_ms_ssim'])}</td>"
            f"<td>{fmt(row['worst_y_psnr'])}</td>"
            f"<td>{fmt(row['worst_dE2000_mean'])}</td>"
            "</tr>"
        )
    detail_rows = []
    for row in sorted(rows, key=lambda r: (r["image_id"], r["lpips"], -r["ms_ssim"])):
        cls = "pass" if row["preview_pass"] else "fail"
        detail_rows.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['image_id'])}</td>"
            f"<td class='left'>{html.escape(row['label'])}</td>"
            f"<td>{fmt(row['lpips'])}</td>"
            f"<td>{fmt(row['ms_ssim'])}</td>"
            f"<td>{fmt(row['y_psnr'])}</td>"
            f"<td>{fmt(row['dE2000_mean'])}</td>"
            f"<td class='{cls}'>{'PASS' if row['preview_pass'] else 'FAIL'}</td>"
            "</tr>"
        )
    missing_html = ""
    if missing:
        missing_html = "<p><b>Skipped missing full-frame PNGs:</b><br>" + "<br>".join(
            html.escape(m) for m in missing
        ) + "</p>"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>PREVIEW L blend oracle</title><style>{css}</style></head><body>"
        "<h1>PREVIEW L Blend Oracle</h1>"
        "<p>Full-image diagnostic. Lab a/b comes from the chroma run; only Lab L "
        "is replaced by existing donors or pairwise blends. This is evidence, not "
        "a ship pipeline.</p>"
        f"{missing_html}"
        "<h2>Global candidates</h2><table><thead><tr>"
        "<th class='left'>candidate</th><th>all pass</th><th class='left'>worst image</th>"
        "<th>worst LPIPS</th><th>worst MS-SSIM</th><th>worst Y-PSNR</th><th>worst dE</th>"
        "</tr></thead><tbody>"
        f"{''.join(summary_rows)}</tbody></table>"
        "<h2>Per-image rows</h2><table><thead><tr>"
        "<th class='left'>image</th><th class='left'>candidate</th><th>LPIPS</th>"
        "<th>MS-SSIM</th><th>Y-PSNR</th><th>dE mean</th><th>verdict</th>"
        "</tr></thead><tbody>"
        f"{''.join(detail_rows)}</tbody></table></body></html>"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chroma-run", default="5e7d52579ffb2d3e")
    ap.add_argument("--ref-run", default="5e7d52579ffb2d3e")
    ap.add_argument("--donor", action="append", default=list(DEFAULT_DONORS),
                    help="L donor label=run_hash. May be repeated.")
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGES))
    ap.add_argument("--alphas", default="0.15,0.25,0.35,0.50,0.65,0.75,0.85")
    ap.add_argument("--target-width", type=int, default=3840)
    ap.add_argument("--progress", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--output-json", type=Path, default=DASH / "preview_luma_blend_oracle.json")
    ap.add_argument("--output-html", type=Path, default=DASH / "preview_luma_blend_oracle.html")
    args = ap.parse_args()

    rows, missing = collect(args)
    summary = aggregate(rows)
    payload = {
        "preview_thresholds": PREVIEW,
        "rows": rows,
        "summary": summary,
        "missing": missing,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2))
    write_html(rows, summary, missing, args.output_html)

    for row in summary[:12]:
        verdict = "PASS" if row["all_pass"] else "FAIL"
        print(
            f"{verdict:4} {row['label']:<48} worst={row['worst_image']} "
            f"LPIPS={row['worst_lpips']:.4f} MS={row['worst_ms_ssim']:.4f} "
            f"Ymin={row['worst_y_psnr']:.2f} dEmax={row['worst_dE2000_mean']:.2f}"
        )
    if missing:
        print(f"missing full-frame donors: {len(missing)}")
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
