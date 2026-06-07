#!/usr/bin/env python3
"""PREVIEW crop-level Lab channel oracle for routed candidates.

This diagnostic is for blocker triage only. It compares existing no-REF
candidate crops against REF, then scores controlled Lab channel swaps and
small fixed Lab a/b offsets. REF is used only to prove which channel would
need a better runtime source or teacher; oracle rows are not deployable.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import color

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_gate import compute_visual_metrics  # noqa: E402


Image.MAX_IMAGE_PIXELS = None

ARTIFACT_ROOT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/preview_runtime_policy_20260606")
DEFAULT_SOURCE_DIR = ARTIFACT_ROOT / "holdout_runtime_crops_v8_clean_upresable_28img"
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


def from_lab(lab: np.ndarray) -> np.ndarray:
    return np.clip(color.lab2rgb(lab) * 255.0, 0, 255).astype(np.uint8)


def passes(metrics: dict) -> bool:
    return (
        metrics["lpips"] <= PREVIEW["lpips"]
        and metrics["ms_ssim"] >= PREVIEW["ms_ssim"]
        and metrics["y_psnr"] >= PREVIEW["y_psnr"]
        and metrics["dE2000_mean"] <= PREVIEW["dE2000_mean"]
    )


def score(ref: np.ndarray, pred: np.ndarray) -> dict:
    h = min(ref.shape[0], pred.shape[0])
    w = min(ref.shape[1], pred.shape[1])
    out = compute_visual_metrics(ref[:h, :w], pred[:h, :w])
    return {k: float(v) for k, v in out.items()}


def candidate_path(candidate_dir: Path, image_id: str, crop: str, kind: str) -> Path:
    if kind == "scene_routed":
        return candidate_dir / f"{image_id}_{crop}_scene_routed.png"
    if kind == "runtime_refiner":
        return candidate_dir / f"{image_id}_{crop}_runtime_priority_v1_content_stats_runtime_refiner.png"
    raise ValueError(f"unknown candidate kind: {kind}")


def parse_sample(item: str) -> tuple[str, str]:
    if ":" not in item:
        raise ValueError(f"sample must be IMAGE_ID:CROP, got {item!r}")
    image_id, crop = item.split(":", 1)
    return image_id, crop


def parse_candidate(item: str) -> tuple[str, Path, str]:
    parts = item.split("=", 2)
    if len(parts) != 3:
        raise ValueError("candidate must be LABEL=KIND=DIR")
    label, kind, path = parts
    return label, Path(path), kind


def channel_oracle_rows(args: argparse.Namespace) -> list[dict]:
    candidates = [parse_candidate(c) for c in args.candidate]
    samples = [parse_sample(s) for s in args.sample]
    rows: list[dict] = []
    for image_id, crop in samples:
        ref = load_rgb(args.source_dir / f"{image_id}_{crop}_REF.png")
        source = load_rgb(args.source_dir / f"{image_id}_{crop}_upresable_preview.png")
        source_lab = to_lab(source)
        ref_lab = to_lab(ref)
        for label, cand_dir, kind in candidates:
            cand = load_rgb(candidate_path(cand_dir, image_id, crop, kind))
            cand_lab = to_lab(cand)
            variants: list[tuple[str, np.ndarray, bool]] = [
                (label, cand, False),
            ]

            ref_l = cand_lab.copy()
            ref_l[..., 0] = ref_lab[..., 0]
            variants.append((f"{label}:REF_L_oracle", from_lab(ref_l), True))

            ref_ab = cand_lab.copy()
            ref_ab[..., 1:3] = ref_lab[..., 1:3]
            variants.append((f"{label}:REF_ab_oracle", from_lab(ref_ab), True))

            source_l = cand_lab.copy()
            source_l[..., 0] = source_lab[..., 0]
            variants.append((f"{label}:source_L", from_lab(source_l), False))

            for da, db in args.offset:
                shifted = cand_lab.copy()
                shifted[..., 1] += da
                shifted[..., 2] += db
                variants.append((f"{label}:Lab_offset_da={da:+.2f}_db={db:+.2f}", from_lab(shifted), False))

            for variant, pred, uses_ref_channel in variants:
                metrics = score(ref, pred)
                rows.append({
                    "image_id": image_id,
                    "crop": crop,
                    "candidate": variant,
                    "uses_ref_channel": uses_ref_channel,
                    **metrics,
                    "preview_pass": passes(metrics),
                })
    return rows


def write_html(rows: list[dict], out: Path) -> None:
    def fmt(v: float) -> str:
        return f"{v:.4f}" if abs(v) < 10 else f"{v:.2f}"

    trs = []
    for row in rows:
        verdict = "PASS" if row["preview_pass"] else "FAIL"
        cls = "pass" if row["preview_pass"] else "fail"
        oracle = "yes" if row["uses_ref_channel"] else "no"
        trs.append(
            "<tr>"
            f"<td class='left'>{html.escape(row['image_id'])}</td>"
            f"<td class='left'>{html.escape(row['crop'])}</td>"
            f"<td class='left'>{html.escape(row['candidate'])}</td>"
            f"<td>{oracle}</td>"
            f"<td>{fmt(row['lpips'])}</td>"
            f"<td>{fmt(row['ms_ssim'])}</td>"
            f"<td>{fmt(row['y_psnr'])}</td>"
            f"<td>{fmt(row['dE2000_mean'])}</td>"
            f"<td class='{cls}'>{verdict}</td>"
            "</tr>"
        )
    css = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; margin: 24px; background: #f6f7f8; color: #202124; }
h1 { font-size: 24px; margin: 0 0 8px; }
p { color: #555; max-width: 1100px; line-height: 1.45; }
table { border-collapse: collapse; width: 100%; background: #fff; font-size: 12px; }
th, td { border: 1px solid #d9dee5; padding: 6px 8px; text-align: right; }
th.left, td.left { text-align: left; }
th { background: #edf1f5; }
.pass { color: #0b6d2b; font-weight: 650; }
.fail { color: #a31621; font-weight: 650; }
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>PREVIEW channel oracle</title><style>{css}</style></head><body>"
        "<h1>PREVIEW Channel Oracle</h1>"
        "<p>Crop-level diagnostic. REF channel rows are oracle evidence only; "
        "non-oracle Lab offsets are deterministic candidate probes.</p>"
        "<table><thead><tr><th class='left'>image</th><th class='left'>crop</th>"
        "<th class='left'>candidate</th><th>uses REF channel</th><th>LPIPS</th>"
        "<th>MS-SSIM</th><th>Y-PSNR</th><th>dE mean</th><th>PREVIEW</th>"
        "</tr></thead><tbody>"
        f"{''.join(trs)}</tbody></table></body></html>"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    ap.add_argument("--sample", action="append", default=[
        "Z8Z_0026:B_center",
        "Z8Z_0026:C_lowerleft",
        "Z8Z_6680:C_lowerleft",
    ])
    ap.add_argument("--candidate", action="append", required=True,
                    help="LABEL=KIND=DIR where KIND is scene_routed or runtime_refiner")
    ap.add_argument("--offset", nargs=2, type=float, action="append", default=[],
                    metavar=("DA", "DB"), help="non-oracle fixed Lab a/b offset to test")
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    args = ap.parse_args()

    rows = channel_oracle_rows(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps({"schema": "preview_channel_oracle.v1", "rows": rows}, indent=2))
    write_html(rows, args.output_html)

    for row in rows:
        print(
            f"{row['image_id']} {row['crop']} {row['candidate']} "
            f"oracle={row['uses_ref_channel']} pass={row['preview_pass']} "
            f"lp={row['lpips']:.4f} ms={row['ms_ssim']:.4f} "
            f"y={row['y_psnr']:.2f} dE={row['dE2000_mean']:.2f}",
            flush=True,
        )
    print(args.output_json)
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
