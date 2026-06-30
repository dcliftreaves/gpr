#!/usr/bin/env python3
"""Build a 100MP still visual audit dashboard.

Real mode uses an X2D-class DNG, optionally roundtrips it through gpr_tools,
renders source/decoded crops through rawpy, and records raw-domain metrics.
Synthetic mode is for CI and exercises the dashboard/metric path without
requiring rawpy or a 154 MB fixture.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.100mp_still_visual_audit.v1"
DEFAULT_DNG = Path("/Volumes/OWC_8TB/gpr_work/artifacts/fixtures/x2d_dngs/2024_April_X2D_1742.dng")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_ref(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def find_gpr_tools(explicit: Path | None) -> Path | None:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("GTOOLS")
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            ROOT / "build-local/source/app/gpr_tools/gpr_tools",
            ROOT / "build/source/app/gpr_tools/gpr_tools",
        ]
    )
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return None


def run_command(cmd: list[str], cwd: Path) -> dict[str, Any]:
    start = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_tail": proc.stdout[-1200:],
        "stderr_tail": proc.stderr[-1200:],
    }


def psnr(mse: float, peak: float) -> float:
    if mse <= 0:
        return float("inf")
    return 10.0 * math.log10((peak * peak) / mse)


def summarize_array(np: Any, src: Any, dec: Any, peak: float) -> dict[str, Any]:
    diff = dec.astype(np.float64) - src.astype(np.float64)
    abs_diff = np.abs(diff)
    mse = float(np.mean(diff * diff))
    return {
        "shape": [int(src.shape[1]), int(src.shape[0])],
        "peak": peak,
        "mean_abs_error": float(np.mean(abs_diff)),
        "p95_abs_error": float(np.percentile(abs_diff, 95)),
        "p99_abs_error": float(np.percentile(abs_diff, 99)),
        "max_abs_error": float(np.max(abs_diff)),
        "psnr_db": psnr(mse, peak),
    }


def crop_specs(width: int, height: int, crop: int) -> list[tuple[str, int, int, int, int]]:
    crop = min(crop, width, height)
    starts = [
        ("upper_left", 0, 0),
        ("center", max(0, (width - crop) // 2), max(0, (height - crop) // 2)),
        ("lower_right", max(0, width - crop), max(0, height - crop)),
    ]
    return [(name, x, y, crop, crop) for name, x, y in starts]


def tone_rgb(np: Any, rgb: Any, lo_pct: float = 0.5, hi_pct: float = 99.5) -> Any:
    lo = float(np.percentile(rgb, lo_pct))
    hi = float(np.percentile(rgb, hi_pct))
    scaled = (rgb.astype(np.float32) - lo) / max(1.0, hi - lo)
    return np.clip(scaled * 255.0 + 0.5, 0, 255).astype(np.uint8)


def raw_crop_to_rgb(np: Any, raw: Any, peak: float) -> Any:
    raw_f = raw.astype(np.float32)
    r = raw_f[0::2, 0::2]
    g1 = raw_f[0::2, 1::2]
    g2 = raw_f[1::2, 0::2]
    b = raw_f[1::2, 1::2]
    h = min(r.shape[0], g1.shape[0], g2.shape[0], b.shape[0])
    w = min(r.shape[1], g1.shape[1], g2.shape[1], b.shape[1])
    rgb = np.stack([r[:h, :w], (g1[:h, :w] + g2[:h, :w]) * 0.5, b[:h, :w]], axis=-1)
    return np.clip(rgb * (255.0 / peak) + 0.5, 0, 255).astype(np.uint8)


def error_rgb(np: Any, src: Any, dec: Any, scale: float) -> Any:
    err = np.abs(dec.astype(np.float32) - src.astype(np.float32))
    if err.ndim == 2:
        err = err[..., None]
    if err.shape[-1] == 1:
        err = np.repeat(err, 3, axis=-1)
    return np.clip(err * scale + 0.5, 0, 255).astype(np.uint8)


def save_contact_sheet(Image: Any, ImageDraw: Any, panels: list[tuple[str, Any]], out: Path) -> None:
    titled = []
    for title, arr in panels:
        im = Image.fromarray(arr).convert("RGB")
        panel = Image.new("RGB", (im.width, im.height + 24), "white")
        panel.paste(im, (0, 24))
        draw = ImageDraw.Draw(panel)
        draw.text((5, 5), title, fill=(20, 20, 20))
        titled.append(panel)
    sheet = Image.new("RGB", (sum(p.width for p in titled), max(p.height for p in titled)), "white")
    x = 0
    for panel in titled:
        sheet.paste(panel, (x, 0))
        x += panel.width
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92)


def render_html(data: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['crop'])}</td>"
        f"<td>{row['x']},{row['y']}</td>"
        f"<td>{row['raw_psnr_db']:.2f}</td>"
        f"<td>{row['raw_mae']:.2f}</td>"
        f"<td>{row['raw_p99_abs_error']:.2f}</td>"
        f"<td><a href=\"{html.escape(row['contact_sheet'])}\">contact sheet</a></td>"
        "</tr>"
        for row in data["crops"]
    )
    commands = "\n".join(
        f"<li><code>{html.escape(' '.join(step['cmd']))}</code> rc={step['returncode']} {step['elapsed_ms']:.1f} ms</li>"
        for step in data.get("codec_roundtrip", {}).get("steps", [])
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>100MP Still Visual Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #121820; background: #f5f7f8; }}
main {{ max-width: 1160px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; }}
.metric {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.value {{ font-size: 28px; font-weight: 750; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 9px; text-align: left; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; }}
a {{ color: #075c9f; }}
</style></head><body><main>
<h1>100MP Still Visual Audit</h1>
<p class="sub">Schema {html.escape(data['schema'])}. This dashboard verifies the real 100MP-class still path visually and in raw Bayer space; it does not promote premium still-SR.</p>
<div class="metric">
  <section class="card"><div>Mode</div><div class="value">{html.escape(data['mode'])}</div></section>
  <section class="card"><div>Dimensions</div><div class="value">{data['summary']['shape'][0]} x {data['summary']['shape'][1]}</div></section>
  <section class="card"><div>Raw PSNR</div><div class="value">{data['summary']['psnr_db']:.2f} dB</div></section>
  <section class="card"><div>Mean abs error</div><div class="value">{data['summary']['mean_abs_error']:.2f}</div></section>
</div>
<h2>100% Crops</h2>
<table><thead><tr><th>Crop</th><th>Origin</th><th>Raw PSNR</th><th>Raw MAE</th><th>Raw p99 error</th><th>Panels</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Codec Roundtrip</h2>
<ul>{commands}</ul>
</main></body></html>
"""


def build_synthetic(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import numpy as np
        from PIL import Image, ImageDraw
    except ModuleNotFoundError as exc:
        print(f"build_100mp_still_visual_audit: missing optional dependency: {exc.name}", file=sys.stderr)
        raise SystemExit(2)
    h, w = 192, 256
    yy, xx = np.indices((h, w))
    src = ((xx * 97 + yy * 53) % 65535).astype(np.uint16)
    dec = np.clip(src.astype(np.int32) + ((xx + yy) % 5) - 2, 0, 65535).astype(np.uint16)
    return build_from_arrays(args, np, Image, ImageDraw, src, dec, 65535.0, "synthetic", None, [])


def load_rawpy_arrays(args: argparse.Namespace) -> tuple[Any, Any, Any, Any, Any, float, list[dict[str, Any]], dict[str, Any]]:
    try:
        import numpy as np
        import rawpy
        from PIL import Image, ImageDraw
    except ModuleNotFoundError as exc:
        print(f"build_100mp_still_visual_audit: missing optional dependency: {exc.name}", file=sys.stderr)
        raise SystemExit(2)
    dng = args.dng
    if not dng.is_file():
        print(f"build_100mp_still_visual_audit: missing DNG {dng}", file=sys.stderr)
        raise SystemExit(2)
    roundtrip: dict[str, Any] = {"enabled": False, "steps": []}
    decoded_dng = dng
    gtools = find_gpr_tools(args.gpr_tools)
    if args.roundtrip and gtools is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        gpr = args.output_dir / "roundtrip_q3.gpr"
        decoded_dng = args.output_dir / "roundtrip_q3.dng"
        step1 = run_command([str(gtools), "-i", str(dng), "-o", str(gpr)], ROOT)
        step2 = run_command([str(gtools), "-i", str(gpr), "-o", str(decoded_dng)], ROOT) if step1["returncode"] == 0 else {
            "cmd": [str(gtools), "-i", str(gpr), "-o", str(decoded_dng)],
            "returncode": 99,
            "elapsed_ms": 0.0,
            "stdout_tail": "",
            "stderr_tail": "skipped because encode failed",
        }
        roundtrip = {
            "enabled": True,
            "gpr_tools": file_ref(gtools),
            "gpr": file_ref(gpr),
            "decoded_dng": file_ref(decoded_dng),
            "steps": [step1, step2],
        }
        if step1["returncode"] != 0 or step2["returncode"] != 0 or not decoded_dng.is_file():
            print("build_100mp_still_visual_audit: gpr_tools roundtrip failed", file=sys.stderr)
            print(step1["stderr_tail"], file=sys.stderr)
            print(step2["stderr_tail"], file=sys.stderr)
            raise SystemExit(1)
    elif args.roundtrip:
        roundtrip = {"enabled": False, "reason": "gpr_tools not found", "steps": []}

    with rawpy.imread(str(dng)) as raw:
        src = raw.raw_image.copy()
        peak = float(raw.white_level or np.iinfo(src.dtype).max)
    if decoded_dng == dng:
        dec = src.copy()
    else:
        with rawpy.imread(str(decoded_dng)) as raw:
            dec = raw.raw_image.copy()
    return np, Image, ImageDraw, src, dec, peak, [file_ref(dng), file_ref(decoded_dng)], roundtrip


def build_from_arrays(
    args: argparse.Namespace,
    np: Any,
    Image: Any,
    ImageDraw: Any,
    src: Any,
    dec: Any,
    peak: float,
    mode: str,
    source_refs: list[dict[str, Any]] | None,
    roundtrip_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_array(np, src, dec, peak)
    rows: list[dict[str, Any]] = []
    for name, x, y, cw, ch in crop_specs(src.shape[1], src.shape[0], args.crop_size):
        src_crop = src[y : y + ch, x : x + cw]
        dec_crop = dec[y : y + ch, x : x + cw]
        crop_summary = summarize_array(np, src_crop, dec_crop, peak)
        contact = args.output_dir / f"crop_{name}.jpg"
        save_contact_sheet(
            Image,
            ImageDraw,
            [
                ("source raw", raw_crop_to_rgb(np, src_crop, peak)),
                ("decoded raw", raw_crop_to_rgb(np, dec_crop, peak)),
                ("abs error", error_rgb(np, src_crop, dec_crop, args.error_scale)),
            ],
            contact,
        )
        rows.append(
            {
                "crop": name,
                "x": x,
                "y": y,
                "w": cw,
                "h": ch,
                "raw_psnr_db": crop_summary["psnr_db"],
                "raw_mae": crop_summary["mean_abs_error"],
                "raw_p99_abs_error": crop_summary["p99_abs_error"],
                "contact_sheet": contact.name,
            }
        )
    data = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "production_claim": mode == "x2d_100mp_gpr_roundtrip",
        "summary": summary,
        "source_refs": source_refs or [],
        "codec_roundtrip": {"enabled": bool(roundtrip_steps), "steps": roundtrip_steps},
        "crops": rows,
    }
    return data


def build_real(args: argparse.Namespace) -> dict[str, Any]:
    np, Image, ImageDraw, src, dec, peak, refs, roundtrip = load_rawpy_arrays(args)
    mode = "x2d_100mp_gpr_roundtrip" if roundtrip.get("enabled") else "x2d_100mp_source_only"
    data = build_from_arrays(args, np, Image, ImageDraw, src, dec, peak, mode, refs, roundtrip.get("steps", []))
    data["codec_roundtrip"] = roundtrip
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dng", type=Path, default=DEFAULT_DNG)
    ap.add_argument("--gpr-tools", type=Path, default=None)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--crop-size", type=int, default=1024)
    ap.add_argument("--error-scale", type=float, default=16.0)
    ap.add_argument("--roundtrip", action="store_true", help="Roundtrip DNG through gpr_tools before comparison")
    ap.add_argument("--synthetic", action="store_true", help="Use a tiny synthetic fixture for CI")
    args = ap.parse_args()

    data = build_synthetic(args) if args.synthetic else build_real(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "audit.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(args.output_dir / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
