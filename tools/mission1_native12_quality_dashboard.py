#!/usr/bin/env python3
"""Build a Mission 1 native-12MP raw quality dashboard.

The dashboard is visual evidence for the exact Mission 1 profile: source
Bayer, decoded Bayer, raw-domain absolute difference, and 100% crop sheets.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mission1_native12_fll2_t2_profile import PROFILE_ID, QUALITY_THRESHOLDS, profile_env

try:
    import rawpy
except ImportError:  # pragma: no cover - fallback is exercised without rawpy
    rawpy = None


WIDTH = 4096
HEIGHT = 3072
BITS = 14
MAX_VALUE = (1 << BITS) - 1
ENCODE_BYTES_RE = re.compile(r"ENCODE:\s+(?P<bytes>\d+)\s+bytes")
CROPS = {
    "upper_left": (384, 384, 512, 512),
    "center": ((WIDTH - 512) // 2, (HEIGHT - 512) // 2, 512, 512),
    "lower_detail": (WIDTH - 896, HEIGHT - 896, 512, 512),
}


def run(cmd: list[str], *, env: dict[str, str], cwd: Path, stdout: Path, stderr: Path) -> None:
    stdout.parent.mkdir(parents=True, exist_ok=True)
    with stdout.open("wb") as out, stderr.open("wb") as err:
        subprocess.run(cmd, cwd=cwd, env=env, stdout=out, stderr=err, check=True)


def load_raw(path: Path, width: int = WIDTH, height: int = HEIGHT) -> np.ndarray:
    arr = np.fromfile(path, dtype=np.uint16)
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} pixels, expected {expected}")
    return arr.reshape((height, width))


def render_bayer_preview(raw: np.ndarray) -> Image.Image:
    """Fast, deterministic RGGB preview suitable for inspection dashboards."""
    rgb = np.zeros((raw.shape[0] // 2, raw.shape[1] // 2, 3), dtype=np.float32)
    rgb[..., 0] = raw[0::2, 0::2]
    rgb[..., 1] = (raw[0::2, 1::2].astype(np.float32) + raw[1::2, 0::2].astype(np.float32)) * 0.5
    rgb[..., 2] = raw[1::2, 1::2]

    lo = float(np.percentile(rgb, 0.1))
    hi = float(np.percentile(rgb, 99.8))
    if hi <= lo:
        hi = lo + 1.0
    rgb = np.clip((rgb - lo) / (hi - lo), 0.0, 1.0)
    rgb = np.power(rgb, 1.0 / 2.2)
    return Image.fromarray((rgb * 255.0 + 0.5).astype(np.uint8), "RGB")


def render_normal_raw(raw: np.ndarray, dng_template: Path, *, auto_bright: bool) -> Image.Image:
    """Render Bayer through the template DNG's WB/color matrix/demosaic path."""
    if rawpy is None:
        raise RuntimeError("rawpy is not available")
    dng = rawpy.imread(str(dng_template))
    try:
        raw_image = dng.raw_image
        if raw_image.shape != raw.shape:
            raise ValueError(f"{dng_template} raw shape {raw_image.shape} != {raw.shape}")
        raw_image[:] = raw
        rgb = dng.postprocess(
            use_camera_wb=True,
            no_auto_bright=not auto_bright,
            output_bps=8,
            gamma=(2.222, 4.5),
            output_color=rawpy.ColorSpace.sRGB,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
        )
        return Image.fromarray(rgb, "RGB")
    finally:
        dng.close()


def render_for_dashboard(
    raw: np.ndarray,
    dng_template: Path | None,
    *,
    auto_bright: bool,
) -> tuple[Image.Image, str]:
    if dng_template is not None:
        try:
            img = render_normal_raw(raw, dng_template, auto_bright=auto_bright)
            mode = "normal_raw_autobright" if auto_bright else "normal_raw"
            return img, mode
        except Exception as exc:
            print(f"warning: normal raw render failed for {dng_template}: {exc}")
    return render_bayer_preview(raw), "bayer_quicklook"


def render_abs_diff(diff: np.ndarray) -> Image.Image:
    absdiff = np.abs(diff).astype(np.float32)
    p99 = max(float(np.percentile(absdiff, 99.0)), 1.0)
    vis = np.clip(absdiff / p99, 0.0, 1.0)
    return Image.fromarray((vis * 255.0 + 0.5).astype(np.uint8), "L")


def raw_crop_to_rgb(raw: np.ndarray, box: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = box
    x &= ~1
    y &= ~1
    w &= ~1
    h &= ~1
    return render_bayer_preview(raw[y : y + h, x : x + w]).resize((w, h), Image.Resampling.NEAREST)


def image_crop_to_rgb(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = box
    x &= ~1
    y &= ~1
    w &= ~1
    h &= ~1
    return image.crop((x, y, x + w, y + h))


def diff_crop_to_rgb(diff: np.ndarray, box: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = box
    x &= ~1
    y &= ~1
    w &= ~1
    h &= ~1
    crop = np.abs(diff[y : y + h, x : x + w]).astype(np.float32)
    vis = np.clip(crop / 16.0, 0.0, 1.0)
    img = Image.fromarray((vis * 255.0 + 0.5).astype(np.uint8), "L").convert("RGB")
    return img


def label_image(img: Image.Image, label: str) -> Image.Image:
    pad = 28
    out = Image.new("RGB", (img.width, img.height + pad), "white")
    out.paste(img.convert("RGB"), (0, pad))
    draw = ImageDraw.Draw(out)
    draw.text((8, 7), label, fill=(20, 24, 30), font=ImageFont.load_default())
    return out


def crop_sheet(
    source_img: Image.Image,
    decoded_img: Image.Image,
    diff: np.ndarray,
    box: tuple[int, int, int, int],
    label: str,
    out_path: Path,
) -> None:
    panels = [
        label_image(image_crop_to_rgb(source_img, box), f"{label}: source"),
        label_image(image_crop_to_rgb(decoded_img, box), "decoded"),
        label_image(diff_crop_to_rgb(diff, box), "abs diff, 16 DN = white"),
    ]
    gutter = 12
    sheet = Image.new(
        "RGB",
        (sum(p.width for p in panels) + gutter * (len(panels) - 1), max(p.height for p in panels)),
        (245, 247, 250),
    )
    x = 0
    for panel in panels:
        sheet.paste(panel, (x, 0))
        x += panel.width + gutter
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=94)


def metrics(source: np.ndarray, decoded: np.ndarray) -> dict[str, float | int]:
    diff = decoded.astype(np.int32) - source.astype(np.int32)
    absdiff = np.abs(diff)
    mse = float(np.mean(diff.astype(np.float64) ** 2))
    rmse = math.sqrt(mse)
    psnr = 99.0 if mse == 0.0 else 20.0 * math.log10(MAX_VALUE / rmse)
    return {
        "psnr14": round(psnr, 4),
        "rmse": round(rmse, 4),
        "mae": round(float(np.mean(absdiff)), 4),
        "p99_abs": float(np.percentile(absdiff, 99.0)),
        "p999_abs": float(np.percentile(absdiff, 99.9)),
        "max_abs": int(absdiff.max()),
        "min_err": int(diff.min()),
        "max_err": int(diff.max()),
    }


def write_html(payload: dict, out_path: Path) -> None:
    css = """
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#f5f7fa;color:#111820}
header{padding:28px 36px;background:#101820;color:white}
main{padding:24px 36px;display:grid;gap:24px}
.card{background:white;border:1px solid #d8dee8;border-radius:8px;padding:18px}
h1,h2{margin:0 0 12px}.metrics{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.metrics span{background:#eef3f8;border:1px solid #d5dde8;border-radius:999px;padding:5px 9px;font-size:13px}
.renders{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-bottom:16px}
.crops{display:grid;grid-template-columns:1fr;gap:14px}figure{margin:0}
img{width:100%;height:auto;display:block;border:1px solid #d9e0ea;background:#fff}
figcaption{font-size:12px;color:#4c5968;margin-top:4px}@media(max-width:1100px){.renders{grid-template-columns:1fr}main{padding:16px}header{padding:20px}}
"""
    lines = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Mission 1 Native12 T233 Quality Dashboard</title>",
        f"<style>{css}</style></head><body>",
        "<header><h1>Mission 1 Native12 T233 Quality</h1>",
        "<p>Exact current profile: source render, decoded render, abs-diff view, and 100% crop sheets.</p></header><main>",
    ]
    for row in payload["rows"]:
        m = row["metrics"]
        lines.append("<section class='card'>")
        lines.append(f"<h2>{html.escape(row['stem'])}</h2>")
        lines.append(
            "<div class='metrics'>"
            f"<span>PSNR14 {m['psnr14']:.2f} dB</span>"
            f"<span>RMSE {m['rmse']:.3f}</span>"
            f"<span>MAE {m['mae']:.3f}</span>"
            f"<span>p99 abs {m['p99_abs']:.1f}</span>"
            f"<span>p99.9 abs {m['p999_abs']:.1f}</span>"
            f"<span>max abs {m['max_abs']}</span>"
            f"<span>{row['encoded_MiB']:.3f} MiB</span>"
            f"<span>{row['required_MBps_at_20fps']:.3f} MB/s at 20 fps</span>"
            f"<span>{html.escape(row['render_mode'])}</span>"
            f"<span>{'PASS' if row['pass'] else 'FAIL'}</span>"
            "</div>"
        )
        lines.append("<div class='renders'>")
        for key, caption in [
            ("source_render", "source normal raw render"),
            ("decoded_render", "decoded normal raw render"),
            ("diff_render", "absolute difference view"),
        ]:
            lines.append(
                f"<figure><img src='{html.escape(row[key])}'>"
                f"<figcaption>{html.escape(caption)}</figcaption></figure>"
            )
        lines.append("</div><div class='crops'>")
        for crop in row["crops"]:
            lines.append(
                f"<figure><img src='{html.escape(crop['sheet'])}'>"
                f"<figcaption>{html.escape(crop['name'])} 100% crop</figcaption></figure>"
            )
        lines.append("</div></section>")
    lines.append("</main></body></html>")
    out_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roundtrip", type=Path, default=Path("build-local/bin/test_fused_roundtrip"))
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--tmpdir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--dng-dir", type=Path, help="directory containing matching Mission 1 DNG templates")
    parser.add_argument(
        "--auto-bright",
        action="store_true",
        help="apply rawpy auto-bright for GoPro-JPEG-like dashboard viewing",
    )
    parser.add_argument("--images", nargs="+", default=["GP017601", "GP017602", "GP017603"])
    parser.add_argument("--keep-decoded", action="store_true")
    parser.add_argument("--profile-id", default=PROFILE_ID, help="profile id to write into the dashboard receipt")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override/add an encoder environment variable for this dashboard run",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    args.tmpdir.mkdir(parents=True, exist_ok=True)
    env = profile_env()
    env_overrides = {}
    for item in args.env:
        if "=" not in item:
            raise ValueError(f"--env must be KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError(f"--env key cannot be empty in {item!r}")
        env[key] = value
        env_overrides[key] = value
    env["TMPDIR"] = str(args.tmpdir)

    rows = []
    for stem in args.images:
        raw_path = args.raw_dir / f"{stem}.raw"
        work = out_dir / stem
        render_dir = work / "render"
        render_dir.mkdir(parents=True, exist_ok=True)
        decoded = args.tmpdir / f"{stem}_t233_decoded.raw"
        run(
            [str(args.roundtrip), str(raw_path), str(WIDTH), str(HEIGHT), str(decoded)],
            env=env,
            cwd=args.repo_root,
            stdout=work / "roundtrip.stdout.txt",
            stderr=work / "roundtrip.stderr.txt",
        )
        source_raw = load_raw(raw_path)
        decoded_raw = load_raw(decoded)
        diff = decoded_raw.astype(np.int32) - source_raw.astype(np.int32)
        row_metrics = metrics(source_raw, decoded_raw)
        dng_template = args.dng_dir / f"{stem}.dng" if args.dng_dir else None
        if dng_template is not None and not dng_template.exists():
            print(f"warning: missing DNG template for {stem}: {dng_template}")
            dng_template = None

        source_png = render_dir / f"{stem}_source.png"
        decoded_png = render_dir / f"{stem}_t233_decoded.png"
        diff_png = render_dir / f"{stem}_absdiff.png"
        source_img, source_mode = render_for_dashboard(source_raw, dng_template, auto_bright=args.auto_bright)
        decoded_img, decoded_mode = render_for_dashboard(decoded_raw, dng_template, auto_bright=args.auto_bright)
        render_mode = source_mode if source_mode == decoded_mode else f"{source_mode}/{decoded_mode}"
        source_img.save(source_png)
        decoded_img.save(decoded_png)
        render_abs_diff(diff).save(diff_png)

        crops = []
        for name, box in CROPS.items():
            sheet = render_dir / f"{stem}_{name}_100pct_sheet.jpg"
            crop_sheet(source_img, decoded_img, diff, box, name, sheet)
            crops.append({"name": name, "sheet": str(sheet.relative_to(out_dir))})

        stdout_text = (work / "roundtrip.stdout.txt").read_text() + (work / "roundtrip.stderr.txt").read_text()
        match = ENCODE_BYTES_RE.search(stdout_text)
        if not match:
            raise ValueError(f"roundtrip output did not include encoded byte count for {stem}")
        encoded_bytes = int(match.group("bytes"))
        required_MBps_at_20fps = encoded_bytes * 20.0 / 1_000_000.0
        row_pass = (
            row_metrics["psnr14"] >= QUALITY_THRESHOLDS["min_psnr14_db"]
            and required_MBps_at_20fps <= QUALITY_THRESHOLDS["max_required_write_mbps_at_20fps"]
        )
        rows.append(
            {
                "stem": stem,
                "profile_id": args.profile_id,
                "encoded_bytes": encoded_bytes,
                "encoded_MiB": encoded_bytes / (1024 * 1024),
                "required_MBps_at_20fps": required_MBps_at_20fps,
                "pass": bool(row_pass),
                "render_mode": render_mode,
                "metrics": row_metrics,
                "source_render": str(source_png.relative_to(out_dir)),
                "decoded_render": str(decoded_png.relative_to(out_dir)),
                "diff_render": str(diff_png.relative_to(out_dir)),
                "crops": crops,
            }
        )
        if not args.keep_decoded:
            decoded.unlink(missing_ok=True)

    payload = {
        "schema": "mission1_native12_quality_dashboard.v1",
        "profile_id": args.profile_id,
        "env_overrides": env_overrides,
        "quality_thresholds": QUALITY_THRESHOLDS,
        "all_pass": all(bool(row["pass"]) for row in rows),
        "rows": rows,
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2))
    write_html(payload, out_dir / "index.html")
    print(out_dir / "index.html")
    print(out_dir / "summary.json")


if __name__ == "__main__":
    main()
