#!/usr/bin/env python3
"""Run the true Mission 1 12MP Bayer recompression matrix.

This script deliberately starts from Bayer pixels. It does not wrap existing
camera-compressed GPR payloads. It compares:

- native 4096x3072 Mission 1 Bayer -> legacy gpr_tools -> decoded Bayer
- native 4096x3072 Mission 1 Bayer -> fused encoder -> decoded Bayer
- 8192x6144 Mission 1 Bayer -> CFA-aware 4096x3072 Bayer -> fused encoder

Artifacts stay under /Volumes/OWC_8TB/gpr_work by default.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageOps

from bayer_resample import cfa_downsample_2x


ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(os.environ.get("PYTHON_BIN", sys.executable))
GTOOLS = ROOT / "build-local/source/app/gpr_tools/gpr_tools"
BENCH_FUSED = ROOT / "build-local/source/app/bench_fused/bench_fused"
if not BENCH_FUSED.exists():
    BENCH_FUSED = ROOT / "build-local/bin/bench_fused"
FUSED_DECODE = ROOT / "build-local/bin/fused_decode_cli"
RENDER_COMPARE = ROOT / "tools/render_compare.py"

SOURCE_SCAN = Path("/Volumes/OWC_8TB/gpr_work/artifacts/mission1p_source_scan_20260616")
SOURCE_PHOTOS = Path("/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P/RawPics")
DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/mission1_true_bayer_recompression_matrix_20260616")

W12, H12 = 4096, 3072
W50, H50 = 8192, 6144
PEAK14 = 16383.0


@dataclass
class InputItem:
    dataset: str
    stem: str
    raw: Path
    dng: Path | None
    width: int = W12
    height: int = H12


def run(cmd: list[str | Path], *, env: dict[str, str] | None = None, cwd: Path = ROOT,
        stdout: Path | None = None, stderr: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd_s = [str(c) for c in cmd]
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd_s,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    elapsed = time.perf_counter() - t0
    if stdout:
        stdout.write_text(proc.stdout)
    if stderr:
        stderr.write_text(proc.stderr)
    proc.elapsed_s = elapsed  # type: ignore[attr-defined]
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed rc={proc.returncode}: {' '.join(cmd_s)}\n"
            f"stdout:\n{proc.stdout[-2000:]}\n\nstderr:\n{proc.stderr[-4000:]}"
        )
    return proc


def ensure_tools() -> None:
    for path in [GTOOLS, BENCH_FUSED, FUSED_DECODE, RENDER_COMPARE, PYTHON]:
        if not path.exists():
            raise FileNotFoundError(path)


def prepare_inputs(out: Path, max_50mp: int) -> list[InputItem]:
    inputs_dir = out / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    items: list[InputItem] = []

    for stem in ["GP017601", "GP017602", "GP017603"]:
        src = SOURCE_SCAN / "raw12_decode" / f"{stem}.raw"
        dst = inputs_dir / f"native12_{stem}.raw"
        if not dst.exists():
            shutil.copy2(src, dst)
        dng = SOURCE_PHOTOS / "DNG" / f"{stem}.dng"
        items.append(InputItem("native12_camera_bayer", stem, dst, dng))

    raw50_dir = SOURCE_SCAN / "raw50_decode"
    stems50 = [p.stem for p in sorted(raw50_dir.glob("*.raw")) if p.stem not in {"GP017601", "GP017602", "GP017603"}]
    for stem in stems50[:max_50mp]:
        src = raw50_dir / f"{stem}.raw"
        dst = inputs_dir / f"resample50to12_{stem}.raw"
        if not dst.exists():
            arr = np.fromfile(src, dtype="<u2").reshape(H50, W50)
            cfa_downsample_2x(arr, mode="gaussian_area").tofile(dst)
        items.append(InputItem("50mp_to_12mp_cfa_resample_bayer", stem, dst, None))
    return items


def source_dng_for_item(item: InputItem, work: Path) -> Path:
    dng = work / f"{item.dataset}_{item.stem}_source.dng"
    if not dng.exists():
        run([
            GTOOLS, "-i", item.raw, "-w", str(item.width), "-h", str(item.height),
            "-x", "rggb14", "-o", dng,
        ], stdout=work / "raw_to_dng.stdout.txt", stderr=work / "raw_to_dng.stderr.txt")
    return dng


def raw_metrics(src_raw: Path, dec_raw: Path, width: int = W12, height: int = H12) -> dict[str, Any]:
    a = np.fromfile(src_raw, dtype="<u2")
    b = np.fromfile(dec_raw, dtype="<u2")
    if a.size != width * height or b.size != width * height:
        raise ValueError(f"bad raw sizes src={a.size} dec={b.size} expected={width*height}")
    ai = a.astype(np.int32)
    bi = b.astype(np.int32)
    d = bi - ai
    mse = float(np.mean(d.astype(np.float64) ** 2))
    rmse = math.sqrt(mse)
    mae = float(np.mean(np.abs(d)))
    psnr = 20.0 * math.log10(PEAK14 / rmse) if rmse > 0 else float("inf")
    return {
        "rmse": rmse,
        "mae": mae,
        "psnr14": psnr,
        "min_err": int(d.min()),
        "max_err": int(d.max()),
        "src_min": int(ai.min()),
        "src_max": int(ai.max()),
        "dec_min": int(bi.min()),
        "dec_max": int(bi.max()),
    }


def render_pair(source_dng: Path, dec_raw: Path, render_dir: Path, label: str) -> tuple[Path, Path]:
    render_dir.mkdir(parents=True, exist_ok=True)
    src_png = render_dir / f"{label}_source.png"
    dec_png = render_dir / f"{label}_decoded.png"
    run([
        PYTHON, RENDER_COMPARE,
        "--dng", source_dng,
        "--codec-raw", dec_raw,
        "--codec-w", str(W12),
        "--codec-h", str(H12),
        "--out-source", src_png,
        "--out-codec", dec_png,
    ], stdout=render_dir / f"{label}_render.stdout.txt", stderr=render_dir / f"{label}_render.stderr.txt")
    return src_png, dec_png


def crop_box(name: str) -> tuple[int, int, int, int]:
    boxes = {
        "upper_left": (256, 256, 768, 768),
        "center": (W12 // 2 - 256, H12 // 2 - 256, W12 // 2 + 256, H12 // 2 + 256),
        "lower_detail": (W12 // 2 - 256, H12 - 900, W12 // 2 + 256, H12 - 388),
    }
    return boxes[name]


def make_crop_sheet(src_png: Path, dec_png: Path, out: Path) -> list[dict[str, str]]:
    src = Image.open(src_png).convert("RGB")
    dec = Image.open(dec_png).convert("RGB")
    crops = []
    for name in ["upper_left", "center", "lower_detail"]:
        box = crop_box(name)
        s = src.crop(box)
        d = dec.crop(box)
        diff = ImageChops.difference(s, d)
        diff = ImageEnhance.Contrast(diff).enhance(4.0)
        sheet = Image.new("RGB", (s.width * 3, s.height + 28), "white")
        sheet.paste(s, (0, 0))
        sheet.paste(d, (s.width, 0))
        sheet.paste(diff, (s.width * 2, 0))
        path = out / f"{src_png.stem}_{name}_sheet.jpg"
        sheet.save(path, quality=92)
        crops.append({"name": name, "sheet": path.name})
    return crops


def legacy_encode_decode(item: InputItem, q: int, out: Path) -> dict[str, Any]:
    work = out / item.dataset / item.stem / f"legacy_q{q}"
    work.mkdir(parents=True, exist_ok=True)
    src_dng = source_dng_for_item(item, work)
    enc = work / "encoded.gpr"
    dec = work / "decoded.raw"
    t0 = time.perf_counter()
    run([GTOOLS, "-i", src_dng, "-o", enc, "-q", str(q)],
        stdout=work / "encode.stdout.txt", stderr=work / "encode.stderr.txt")
    enc_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    run([GTOOLS, "-i", enc, "-o", dec],
        stdout=work / "decode.stdout.txt", stderr=work / "decode.stderr.txt")
    dec_s = time.perf_counter() - t1
    src_png, dec_png = render_pair(src_dng, dec, work / "render", f"{item.dataset}_{item.stem}_legacy_q{q}")
    crops = make_crop_sheet(src_png, dec_png, work / "render")
    return {
        "dataset": item.dataset,
        "stem": item.stem,
        "candidate": f"legacy_q{q}",
        "encoder_kind": "legacy_gpr_tools",
        "q": q,
        "encoded_bytes": enc.stat().st_size,
        "encode_ms": enc_s * 1000.0,
        "decode_ms": dec_s * 1000.0,
        "metrics": raw_metrics(item.raw, dec),
        "source_render": str(src_png.relative_to(out)),
        "decoded_render": str(dec_png.relative_to(out)),
        "crops": crops,
        "work_dir": str(work),
    }


def fused_env(candidate: str, q: int) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "GPR_BENCH_PIXEL_FORMAT": "1",
        "FUSED_QUALITY": str(q),
        "GPR_INCLUDE_LL": "1",
    })
    if candidate == "fused_3level":
        env.update({"FUSED_MULTI_LEVEL": "1", "FUSED_WAVELET_LEVELS": "3"})
    elif candidate == "fused_3level_allq1":
        env.update({
            "FUSED_MULTI_LEVEL": "1",
            "FUSED_WAVELET_LEVELS": "3",
            "GPR_QUANT_OVERRIDE": ",".join(f"{i}:1" for i in range(10)),
        })
    elif candidate == "fused_single_ll":
        env.update({"FUSED_MULTI_LEVEL": "0"})
        env.pop("FUSED_WAVELET_LEVELS", None)
    else:
        raise ValueError(candidate)
    return env


def parse_bench_stderr(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    m = re.search(r"# n=(\d+)\s+mean=([0-9.]+).*?median=([0-9.]+)", text)
    if m:
        out["bench_n"] = int(m.group(1))
        out["bench_mean_ms"] = float(m.group(2))
        out["bench_median_ms"] = float(m.group(3))
    m = re.search(r"# fps_mean=([0-9.]+)\s+fps_median=([0-9.]+)", text)
    if m:
        out["bench_fps_mean"] = float(m.group(1))
        out["bench_fps_median"] = float(m.group(2))
    return out


def fused_encode_decode(item: InputItem, candidate: str, q: int, out: Path, n_iters: int) -> dict[str, Any]:
    work = out / item.dataset / item.stem / f"{candidate}_q{q}"
    work.mkdir(parents=True, exist_ok=True)
    enc = work / "encoded.gpr"
    dec = work / "decoded.raw"
    env = fused_env(candidate, q)
    env["GPR_BENCH_DUMP"] = str(enc)
    proc = run([BENCH_FUSED, item.raw, str(item.width), str(item.height), str(n_iters)],
               env=env, stdout=work / "bench.stdout.txt", stderr=work / "bench.stderr.txt")
    run([FUSED_DECODE, enc, str(item.width), str(item.height), dec], env=env,
        stdout=work / "decode.stdout.txt", stderr=work / "decode.stderr.txt")
    src_dng = source_dng_for_item(item, work)
    src_png, dec_png = render_pair(src_dng, dec, work / "render", f"{item.dataset}_{item.stem}_{candidate}_q{q}")
    crops = make_crop_sheet(src_png, dec_png, work / "render")
    row = {
        "dataset": item.dataset,
        "stem": item.stem,
        "candidate": f"{candidate}_q{q}",
        "encoder_kind": "fused",
        "q": q,
        "encoded_bytes": enc.stat().st_size,
        "decode_raw": str(dec),
        "metrics": raw_metrics(item.raw, dec),
        "source_render": str(src_png.relative_to(out)),
        "decoded_render": str(dec_png.relative_to(out)),
        "crops": crops,
        "work_dir": str(work),
    }
    row.update(parse_bench_stderr(proc.stderr))
    return row


def error_row(
    item: InputItem,
    *,
    candidate: str,
    encoder_kind: str,
    q: int,
    out: Path,
    work: Path,
    exc: Exception,
) -> dict[str, Any]:
    logs = []
    if work.exists():
        logs = [str(p.relative_to(out)) for p in sorted(work.rglob("*.txt"))]
    return {
        "dataset": item.dataset,
        "stem": item.stem,
        "candidate": candidate,
        "encoder_kind": encoder_kind,
        "q": q,
        "status": "error",
        "encoded_bytes": 0,
        "metrics": None,
        "crops": [],
        "work_dir": str(work),
        "logs": logs,
        "error": str(exc),
    }


def safe_legacy_encode_decode(item: InputItem, q: int, out: Path) -> dict[str, Any]:
    work = out / item.dataset / item.stem / f"legacy_q{q}"
    try:
        row = legacy_encode_decode(item, q, out)
        row["status"] = "ok"
        return row
    except Exception as exc:
        return error_row(
            item,
            candidate=f"legacy_q{q}",
            encoder_kind="legacy_gpr_tools",
            q=q,
            out=out,
            work=work,
            exc=exc,
        )


def safe_fused_encode_decode(
    item: InputItem,
    candidate: str,
    q: int,
    out: Path,
    n_iters: int,
) -> dict[str, Any]:
    work = out / item.dataset / item.stem / f"{candidate}_q{q}"
    try:
        row = fused_encode_decode(item, candidate, q, out, n_iters)
        row["status"] = "ok"
        return row
    except Exception as exc:
        return error_row(
            item,
            candidate=f"{candidate}_q{q}",
            encoder_kind="fused",
            q=q,
            out=out,
            work=work,
            exc=exc,
        )


def verdict(row: dict[str, Any]) -> str:
    m = row.get("metrics")
    if not m:
        return "error"
    if m["psnr14"] >= 55.0 and m["rmse"] <= 30.0:
        return "metric-pass-needs-visual"
    return "fail"


def write_dashboard(out: Path, rows: list[dict[str, Any]]) -> None:
    row_cards = []
    for row in rows:
        m = row.get("metrics")
        fps = row.get("bench_fps_median")
        timing = f"{fps:.2f} fps local median" if isinstance(fps, float) else f"{row.get('encode_ms', 0):.1f} ms local encode"
        status = row.get("status", "ok")
        crop_imgs = ""
        if row.get("crops"):
            crop_imgs = "".join(
                f"<figure><img src='{row['work_dir'].replace(str(out) + '/', '')}/render/{c['sheet']}'><figcaption>{html.escape(c['name'])}</figcaption></figure>"
                for c in row["crops"]
            )
        metric_spans = "<span>no metrics</span>"
        if m:
            metric_spans = (
                f"<span>PSNR14 {m['psnr14']:.2f} dB</span>"
                f"<span>RMSE {m['rmse']:.2f}</span>"
            )
        render_html = ""
        if row.get("source_render") and row.get("decoded_render"):
            render_html = f"""
          <div class="renders">
            <figure><img src="{html.escape(row['source_render'])}"><figcaption>source render</figcaption></figure>
            <figure><img src="{html.escape(row['decoded_render'])}"><figcaption>decoded render</figcaption></figure>
          </div>"""
        error_html = ""
        if status != "ok":
            logs = "".join(
                f"<li><a href='{html.escape(log)}'>{html.escape(log)}</a></li>"
                for log in row.get("logs", [])
            )
            error_html = f"""
          <pre class="error-text">{html.escape(row.get('error', 'unknown error'))}</pre>
          <ul class="logs">{logs}</ul>"""
        row_cards.append(f"""
        <section class="row">
          <h2>{html.escape(row['dataset'])} / {html.escape(row['stem'])} / {html.escape(row['candidate'])}</h2>
          <div class="metrics">
            <span>{html.escape(row['encoder_kind'])}</span>
            <span class="{html.escape(status)}">{html.escape(status)}</span>
            <span>{row.get('encoded_bytes', 0) / 1024 / 1024:.2f} MiB</span>
            <span>{timing}</span>
            {metric_spans}
            <span class="{verdict(row)}">{verdict(row)}</span>
          </div>
          {error_html}
          {render_html}
          <div class="crops">{crop_imgs}</div>
        </section>
        """)
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mission 1 True Bayer Recompression Matrix</title>
<style>
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#111820;background:#fff}}
header{{padding:28px 36px;background:#f4f6f8;border-bottom:1px solid #d9dfe7}}
h1{{margin:0;font-size:30px;letter-spacing:0}} p{{color:#586471;max-width:1100px}}
main{{padding:24px 36px}} .row{{border-top:1px solid #d9dfe7;padding:24px 0}}
h2{{font-size:20px;margin:0 0 10px}} .metrics{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}}
.metrics span{{border:1px solid #d9dfe7;border-radius:999px;padding:6px 9px;font-size:13px;background:#fff}}
.metrics .fail,.metrics .error{{color:#9b1c1c;border-color:#e4b4b4;background:#fff7f7;font-weight:700}}
.metrics .metric-pass-needs-visual{{color:#0b6840;border-color:#aad6c1;background:#f2fbf6;font-weight:700}}
.error-text{{white-space:pre-wrap;background:#fff7f7;border:1px solid #e4b4b4;color:#5f1515;padding:12px;border-radius:8px;max-height:260px;overflow:auto}}
.logs{{margin:8px 0 14px;color:#586471}}
.renders{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:12px}}
.crops{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}
figure{{margin:0;border:1px solid #d9dfe7;border-radius:8px;overflow:hidden;background:#fff}}
img{{display:block;width:100%;height:auto}} figcaption{{padding:8px 10px;color:#586471;border-top:1px solid #d9dfe7;font-size:13px}}
@media(max-width:900px){{header,main{{padding-left:18px;padding-right:18px}}.renders,.crops{{grid-template-columns:1fr}}}}
</style></head>
<body><header><h1>Mission 1 true Bayer recompression matrix</h1>
<p>Every candidate starts from Bayer pixels and freshly compresses them. Native camera payload wrapping is intentionally excluded.</p></header>
<main>{''.join(row_cards)}</main></body></html>"""
    (out / "index.html").write_text(html_doc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-50mp", type=int, default=3)
    ap.add_argument("--native-only", action="store_true")
    ap.add_argument("--fused-iters", type=int, default=5)
    args = ap.parse_args()

    ensure_tools()
    args.out.mkdir(parents=True, exist_ok=True)
    items = prepare_inputs(args.out, 0 if args.native_only else args.max_50mp)

    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(safe_legacy_encode_decode(item, 3, args.out))
        rows.append(safe_legacy_encode_decode(item, 8, args.out))
        rows.append(safe_fused_encode_decode(item, "fused_3level", 3, args.out, args.fused_iters))
        rows.append(safe_fused_encode_decode(item, "fused_3level_allq1", 1, args.out, args.fused_iters))
        rows.append(safe_fused_encode_decode(item, "fused_single_ll", 3, args.out, args.fused_iters))
        (args.out / "matrix_partial.json").write_text(json.dumps({"rows": rows}, indent=2) + "\n")
        write_dashboard(args.out, rows)

    summary = {
        "schema": "mission1_true_bayer_recompression_matrix.v1",
        "out": str(args.out),
        "row_count": len(rows),
        "rows": rows,
    }
    (args.out / "matrix_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    write_dashboard(args.out, rows)
    print(args.out / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
