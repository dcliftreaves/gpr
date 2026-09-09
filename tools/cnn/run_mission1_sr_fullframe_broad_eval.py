#!/usr/bin/env python3
"""Run/reduce a broad Mission 1 full-frame 12MP->8K SR evaluation.

This orchestrates the existing single-frame SR benchmark and full-frame
comparator across a directory of decoded 12MP current-codec raws. Generated
8K raws are deleted after comparison; the preserved artifacts are JSON receipts,
contact sheets, an aggregate summary, and an HTML dashboard.
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) * 0.5)


def stats(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row[key]) for row in rows]
    return {
        "min": min(values) if values else 0.0,
        "median": median(values),
        "max": max(values) if values else 0.0,
        "mean": sum(values) / len(values) if values else 0.0,
    }


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def paths_for_image(out_root: Path, stem: str, checkpoint_stem: str, tile: int, overlap: int) -> dict[str, Path]:
    out_dir = out_root / stem
    overlap_suffix = f"_ov{overlap}" if overlap else ""
    return {
        "out_dir": out_dir,
        "sr_raw": out_dir / f"{stem}_sr.raw",
        "bench_json": out_dir / f"{stem}_{checkpoint_stem}_sr8k_{tile}{overlap_suffix}_bench.json",
        "compare_json": out_dir / f"{stem}_fullframe_compare.json",
        "contact_sheet": out_dir / f"{stem}_fullframe_contact.jpg",
    }


def row_from_receipts(stem: str, paths: dict[str, Path]) -> dict[str, Any]:
    bench = load_json(paths["bench_json"])
    comp = load_json(paths["compare_json"])
    timing = bench["timing"]
    return {
        "image": stem,
        "bench_json": str(paths["bench_json"]),
        "compare_json": str(paths["compare_json"]),
        "contact_sheet": str(paths["contact_sheet"]),
        "fps_with_write": timing["fps_with_write"],
        "total_with_write_s": timing["total_with_write_s"],
        "inference_plus_copy_s": timing["inference_plus_copy_s"],
        "write_output_s": timing["write_output_s"],
        "rmse_improvement_pct": comp["improvement_pct"]["rmse"],
        "mae_improvement_pct": comp["improvement_pct"]["mae"],
        "gradient_mae_improvement_pct": comp["improvement_pct"]["gradient_mae"],
        "same_cell_detail_mae_improvement_pct": comp["improvement_pct"].get("same_cell_detail_mae", 0.0),
        "same_cell_fine_detail_mae_improvement_pct": comp["improvement_pct"].get("same_cell_fine_detail_mae", 0.0),
        "cfa_plane_detail_mae_improvement_pct": comp["improvement_pct"].get("cfa_plane_detail_mae", 0.0),
        "baseline_same_cell_detail_mae": comp.get("baseline_same_cell_detail", {}).get("same_cell_detail_mae_counts", 0.0),
        "model_same_cell_detail_mae": comp.get("model_same_cell_detail", {}).get("same_cell_detail_mae_counts", 0.0),
        "baseline_psnr14_db": comp["baseline_bilinear"]["psnr14_db"],
        "model_psnr14_db": comp["model"]["psnr14_db"],
        "baseline_rmse": comp["baseline_bilinear"]["rmse_counts"],
        "model_rmse": comp["model"]["rmse_counts"],
    }


def build_summary(out_root: Path, checkpoint: Path, rows: list[dict[str, Any]], elapsed_s: float) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "checkpoint": str(checkpoint),
        "images": rows,
        "image_count": len(rows),
        "elapsed_s": elapsed_s,
    }
    for key in [
        "fps_with_write",
        "total_with_write_s",
        "rmse_improvement_pct",
        "mae_improvement_pct",
        "gradient_mae_improvement_pct",
        "same_cell_detail_mae_improvement_pct",
        "same_cell_fine_detail_mae_improvement_pct",
        "cfa_plane_detail_mae_improvement_pct",
        "model_psnr14_db",
    ]:
        summary[key] = stats(rows, key)
    if rows:
        summary["worst_by_rmse_improvement"] = min(rows, key=lambda r: r["rmse_improvement_pct"])
        summary["worst_by_mae_improvement"] = min(rows, key=lambda r: r["mae_improvement_pct"])
        summary["worst_by_gradient_improvement"] = min(rows, key=lambda r: r["gradient_mae_improvement_pct"])
        summary["worst_by_same_cell_detail_improvement"] = min(
            rows, key=lambda r: r["same_cell_detail_mae_improvement_pct"]
        )
    summary["dashboard"] = str(out_root / "index.html")
    return summary


def rel(path: str | Path, base: Path) -> str:
    try:
        return Path(path).resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def write_dashboard(out_root: Path, summary: dict[str, Any]) -> None:
    rows = sorted(summary["images"], key=lambda r: r["rmse_improvement_pct"])
    cards = []
    for row in rows:
        cards.append(
            f"""
            <article class="card">
              <div class="meta">
                <h2>{html.escape(row['image'])}</h2>
                <dl>
                  <div><dt>RMSE lift</dt><dd>{row['rmse_improvement_pct']:.1f}%</dd></div>
                  <div><dt>MAE lift</dt><dd>{row['mae_improvement_pct']:.1f}%</dd></div>
                  <div><dt>Gradient lift</dt><dd>{row['gradient_mae_improvement_pct']:.1f}%</dd></div>
                  <div><dt>Same-cell detail</dt><dd>{row['same_cell_detail_mae_improvement_pct']:.1f}%</dd></div>
                  <div><dt>PSNR14</dt><dd>{row['model_psnr14_db']:.2f} dB</dd></div>
                  <div><dt>Time</dt><dd>{row['total_with_write_s']:.3f}s</dd></div>
                  <div><dt>FPS</dt><dd>{row['fps_with_write']:.2f}</dd></div>
                </dl>
              </div>
              <a href="{html.escape(rel(row['contact_sheet'], out_root))}">
                <img src="{html.escape(rel(row['contact_sheet'], out_root))}" alt="{html.escape(row['image'])} full-frame SR contact sheet">
              </a>
            </article>
            """
        )
    rmse = summary["rmse_improvement_pct"]
    mae = summary["mae_improvement_pct"]
    grad = summary["gradient_mae_improvement_pct"]
    detail = summary["same_cell_detail_mae_improvement_pct"]
    fps = summary["fps_with_write"]
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mission 1 8K SR Full-Frame Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101214;
      color: #f2f4f2;
    }}
    body {{ margin: 0; }}
    header {{
      padding: 32px clamp(20px, 5vw, 64px) 24px;
      border-bottom: 1px solid #2d3531;
      background: #151917;
    }}
    h1 {{ margin: 0 0 12px; font-size: clamp(28px, 4vw, 52px); letter-spacing: 0; }}
    .sub {{ color: #bdc7bf; max-width: 980px; line-height: 1.45; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 24px;
    }}
    .metric {{ border: 1px solid #334139; padding: 14px 16px; border-radius: 8px; background: #1b211e; }}
    .metric span {{ display: block; color: #aeb9b0; font-size: 13px; }}
    .metric strong {{ display: block; margin-top: 6px; font-size: 24px; }}
    main {{ padding: 28px clamp(20px, 5vw, 64px) 56px; }}
    .card {{
      display: grid;
      grid-template-columns: minmax(220px, 340px) minmax(0, 1fr);
      gap: 18px;
      align-items: start;
      border-top: 1px solid #2d3531;
      padding: 20px 0;
    }}
    .card h2 {{ margin: 0 0 14px; font-size: 22px; }}
    dl {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 0; }}
    dt {{ color: #aeb9b0; font-size: 12px; }}
    dd {{ margin: 2px 0 0; font-size: 18px; font-weight: 700; }}
    img {{ width: 100%; height: auto; display: block; border: 1px solid #26302a; }}
    a {{ color: inherit; }}
    @media (max-width: 820px) {{
      .card {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Mission 1 12MP to 8K SR</h1>
    <p class="sub">Full-frame current-codec evaluation against original 50MP Mission 1 Bayer targets. The CNN output is compared with bilinear Bayer-plane upscaling, and the generated 8K raw intermediates are deleted after metrics/contact-sheet generation.</p>
    <section class="metrics">
      <div class="metric"><span>Images</span><strong>{summary['image_count']}</strong></div>
      <div class="metric"><span>RMSE lift median</span><strong>{rmse['median']:.1f}%</strong></div>
      <div class="metric"><span>RMSE lift worst</span><strong>{rmse['min']:.1f}%</strong></div>
      <div class="metric"><span>MAE lift median</span><strong>{mae['median']:.1f}%</strong></div>
      <div class="metric"><span>Gradient lift median</span><strong>{grad['median']:.1f}%</strong></div>
      <div class="metric"><span>Same-cell detail median</span><strong>{detail['median']:.1f}%</strong></div>
      <div class="metric"><span>MPS throughput</span><strong>{fps['median']:.2f} fps</strong></div>
    </section>
  </header>
  <main>
    {''.join(cards)}
  </main>
</body>
</html>
"""
    (out_root / "index.html").write_text(body, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--low-dir", type=Path, required=True)
    ap.add_argument("--target-dir", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--out-root", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--python", type=Path, default=Path(sys.executable))
    ap.add_argument("--low-width", type=int, default=4096)
    ap.add_argument("--low-height", type=int, default=3072)
    ap.add_argument("--high-width", type=int, help="defaults to 2x --low-width")
    ap.add_argument("--high-height", type=int, help="defaults to 2x --low-height")
    ap.add_argument("--tile", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    ap.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    ap.add_argument("--stem", action="append", help="limit to one input stem; repeatable")
    ap.add_argument("--force", action="store_true", help="rerun even when per-image receipts already exist")
    ap.add_argument(
        "--keep-generated-raw",
        action="store_true",
        help="preserve generated 8K SR raw frames for follow-up diagnostics such as hard-tile mining",
    )
    args = ap.parse_args()

    args.out_root.mkdir(parents=True, exist_ok=True)
    high_width = args.high_width or args.low_width * 2
    high_height = args.high_height or args.low_height * 2
    checkpoint_stem = args.checkpoint.name.replace(".pt", "")
    rows: list[dict[str, Any]] = []
    started = time.time()
    requested_stems = set(args.stem or [])
    for low in sorted(args.low_dir.glob("*.raw")):
        stem = low.stem
        if requested_stems and stem not in requested_stems:
            continue
        target = args.target_dir / low.name
        if not target.exists():
            raise FileNotFoundError(target)
        paths = paths_for_image(args.out_root, stem, checkpoint_stem, args.tile, args.overlap)
        paths["out_dir"].mkdir(parents=True, exist_ok=True)
        if args.force or not (paths["bench_json"].exists() and paths["compare_json"].exists()):
            print(f"== {stem}: bench ==", flush=True)
            run(
                [
                    str(args.python),
                    "tools/cnn/bench_mission1_sr_8k.py",
                    "--raw",
                    str(low),
                    "--checkpoint",
                    str(args.checkpoint),
                    "--out-dir",
                    str(paths["out_dir"]),
                    "--low-width",
                    str(args.low_width),
                    "--low-height",
                    str(args.low_height),
                    "--high-width",
                    str(high_width),
                    "--high-height",
                    str(high_height),
                    "--tile",
                    str(args.tile),
                    "--overlap",
                    str(args.overlap),
                    "--device",
                    args.device,
                    "--write-output",
                    "--output-raw",
                    str(paths["sr_raw"]),
                ],
                args.repo,
            )
            print(f"== {stem}: compare ==", flush=True)
            run(
                [
                    str(args.python),
                    "tools/cnn/compare_mission1_sr_fullframe.py",
                    "--low-raw",
                    str(low),
                    "--sr-raw",
                    str(paths["sr_raw"]),
                    "--target-raw",
                    str(target),
                    "--low-width",
                    str(args.low_width),
                    "--low-height",
                    str(args.low_height),
                    "--high-width",
                    str(high_width),
                    "--high-height",
                    str(high_height),
                    "--out-json",
                    str(paths["compare_json"]),
                    "--contact-sheet",
                    str(paths["contact_sheet"]),
                ],
                args.repo,
            )
        if not args.keep_generated_raw:
            paths["sr_raw"].unlink(missing_ok=True)
        rows.append(row_from_receipts(stem, paths))

    summary = build_summary(args.out_root, args.checkpoint, rows, time.time() - started)
    (args.out_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_dashboard(args.out_root, summary)
    print(json.dumps({"summary": str(args.out_root / "summary.json"), "dashboard": summary["dashboard"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
