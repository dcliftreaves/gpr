"""CNN-aware rate-distortion calibration harness for the GPR codec.

Sweeps codec quality presets across a DNG corpus and measures:
  - Encoded bytes per frame
  - Bayer-domain roundtrip PSNR vs source (no CNN)
  - CNN-corrected PSNR vs source (BIBO_1x by default)

Output: a CSV per-(image, quality) and a summary table that lets you see
where on the rate-distortion curve the CNN is "free" — i.e. quant
presets where the codec drops a lot of bits but the CNN gets the PSNR
back. That's the empirical signal that tells you which subbands the
CNN can recover.

This is the foundation pass for task #158 (AccelIR-style per-subband
quant calibration). Once the encoder/decoder gain a per-subband quant
override env var (waiting on task #155's decoder work to land), this
script grows a `--per-subband-sweep` mode that walks individual qt[]
slots, not whole presets.

Usage:
  python3 tools/test/quant_calibration.py \\
      --corpus /Volumes/OWC_8TB/gpr_artifacts/fixtures/barn_sky_dngs \\
      --max-images 4 \\
      --qualities 0,1,2,3,4,5,6,7,8 \\
      --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration

Optional:
  --with-cnn           also measure CNN-corrected PSNR (slower)
  --cnn-ckpt PATH      Metal weights dir (default F_ane_1x_weights_metal)
  --build-dir DIR      cmake build root (default build-local)
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def find_tool(build_dir: Path, name: str) -> Path:
    candidates = [
        build_dir / "source/app/gpr_tools/gpr_tools",
        build_dir / "source/app/bench_fused/bench_fused",
        REPO / "tools/gpr2prores/gpr2prores",
        REPO / "tools/gpr2prores/gpr_mov_tool",
    ]
    for c in candidates:
        if c.name == name and c.exists() and os.access(c, os.X_OK):
            return c
    raise SystemExit(f"can't find {name} under {build_dir} or repo")


def extract_bayer(dng_path: Path, out_raw: Path) -> tuple[int, int, int]:
    """Return (width, height, peak) of the DNG bayer plane.
    peak = (1 << bit_depth) - 1 derived from rawpy's white level.
    """
    import rawpy
    import numpy as np

    r = rawpy.imread(str(dng_path))
    bayer = r.raw_image.copy().astype("<u2")
    h, w = bayer.shape
    # Best-effort bit-depth guess from white_level
    white = int(r.white_level)
    if white >= 65000:
        peak = 65535
    elif white >= 16000:
        peak = 16383
    elif white >= 4000:
        peak = 4095
    else:
        peak = white
    r.close()
    bayer.tofile(out_raw)
    return w, h, peak


def encode_at_quality(gtools: Path, dng_in: Path, gpr_out: Path, quality: int) -> float:
    """Run gpr_tools dng→gpr at the given quality. Return encode wall-clock ms."""
    t0 = time.time()
    subprocess.run(
        [str(gtools), "-i", str(dng_in), "-o", str(gpr_out), "-q", str(quality)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return (time.time() - t0) * 1000


def decode_to_dng(gtools: Path, gpr_in: Path, dng_out: Path) -> float:
    t0 = time.time()
    subprocess.run(
        [str(gtools), "-i", str(gpr_in), "-o", str(dng_out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return (time.time() - t0) * 1000


def bayer_psnr(src_dng: Path, dec_dng: Path, peak: int) -> float:
    import rawpy
    import numpy as np
    a = rawpy.imread(str(src_dng)); src = a.raw_image.copy().astype("float64"); a.close()
    b = rawpy.imread(str(dec_dng)); dec = b.raw_image.copy().astype("float64"); b.close()
    if src.shape != dec.shape:
        return float("nan")
    mse = ((src - dec) ** 2).mean()
    return float(10 * (np.log10(peak * peak / mse))) if mse > 0 else float("inf")


def cnn_render_psnr(gpr2prores: Path, gpr_in: Path, meta_dng: Path,
                    ckpt: Path, out_mov: Path) -> float | None:
    """Run gpr2prores playback on a single .gpr, extract frame 0 RGB,
    PSNR against the no-codec rawpy AHD render of the source DNG.

    Returns brightness-matched Y-PSNR on the masked middle (matches
    test_cnn_regression.py methodology). None if CNN run failed.
    """
    try:
        import cv2
        import numpy as np
        import rawpy
    except Exception as e:
        print(f"  (CNN PSNR skipped: missing dep {e})")
        return None

    # gpr2prores needs a directory of .gpr or a packed .mov. Single .gpr → tmp dir.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        frame_dst = td_path / "frame_0000.gpr"
        frame_dst.symlink_to(gpr_in)
        rc = subprocess.run([
            str(gpr2prores),
            "--meta-dng", str(meta_dng),
            "--cnn-backend", "mpsgraph",
            "--ckpt", str(ckpt),
            "--cnn-scale", "1x",
            "--demosaic", "metal-bilinear",
            "--out-resolution", "uhd",
            str(td_path), str(out_mov),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc.returncode != 0:
            return None

    # Extract frame 0 RGB16, render reference DNG at UHD, compute masked PSNR.
    rgb_test = td_path / "test.png"
    subprocess.run(["ffmpeg", "-y", "-i", str(out_mov), "-frames:v", "1",
                    "-pix_fmt", "rgb48", str(rgb_test)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if not rgb_test.exists():
        return None

    from PIL import Image
    test = np.asarray(Image.open(rgb_test)).astype(np.float64)
    raw = rawpy.imread(str(meta_dng))
    src = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=16,
                          gamma=(2.222, 4.5), output_color=rawpy.ColorSpace.sRGB,
                          demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD)
    raw.close()

    if src.shape[:2] != test.shape[:2]:
        # Downscale src to test dims (test is UHD, src is native sensor)
        src_resized = cv2.resize(src.astype(np.float32),
                                  (test.shape[1], test.shape[0]),
                                  interpolation=cv2.INTER_AREA).astype(np.float64)
        src = src_resized
    # brightness-match per channel
    test_bm = test.copy()
    for c in range(3):
        test_bm[..., c] = np.clip(test[..., c] + (src[..., c].mean() - test[..., c].mean()),
                                   0, 65535)
    # masked Y-PSNR
    rs = (src / 256.0)
    ts = (test_bm / 256.0)
    ry = 0.299 * rs[..., 0] + 0.587 * rs[..., 1] + 0.114 * rs[..., 2]
    ty = 0.299 * ts[..., 0] + 0.587 * ts[..., 1] + 0.114 * ts[..., 2]
    mask = (ry > 10) & (ry < 250)
    mse = ((ry[mask] - ty[mask]) ** 2).mean()
    if mse <= 0:
        return float("inf")
    return float(20 * np.log10(255.0 / np.sqrt(mse)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path,
                    help="directory of source DNGs to sweep")
    ap.add_argument("--max-images", type=int, default=4,
                    help="limit number of corpus images (deterministic)")
    ap.add_argument("--qualities", default="0,1,2,3,4,5,6,7,8",
                    help="comma-separated quality presets to sweep")
    ap.add_argument("--build-dir", type=Path, default=Path("build-local"))
    ap.add_argument("--out-dir", type=Path,
                    default=Path("/Volumes/OWC_8TB/gpr_artifacts/quant_calibration"))
    ap.add_argument("--with-cnn", action="store_true",
                    help="also measure CNN-corrected PSNR (much slower)")
    ap.add_argument("--cnn-ckpt", type=Path,
                    default=Path("/Volumes/OWC_8TB/gpr_artifacts/weights/F_ane_1x_weights_metal"))
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    build_dir = (args.build_dir if args.build_dir.is_absolute()
                 else REPO / args.build_dir)
    gtools = find_tool(build_dir, "gpr_tools")
    gpr2prores = find_tool(build_dir, "gpr2prores") if args.with_cnn else None

    images = sorted(args.corpus.glob("*.dng"))[: args.max_images]
    if not images:
        raise SystemExit(f"no DNGs under {args.corpus}")
    qualities = [int(q) for q in args.qualities.split(",")]

    rows = []
    print(f"== Sweeping {len(images)} images × {len(qualities)} qualities ==")
    print(f"== Corpus: {args.corpus}")
    print(f"== Output: {args.out_dir}")
    if args.with_cnn:
        print(f"== CNN ckpt: {args.cnn_ckpt}")
    print()

    for dng in images:
        # Pre-extract raw + dims once per image (cheaper than re-reading every quality)
        # Then run encode/decode/PSNR per quality.
        print(f"  {dng.name}")
        for q in qualities:
            gpr_path = args.out_dir / f"{dng.stem}_q{q}.gpr"
            dec_dng = args.out_dir / f"{dng.stem}_q{q}_dec.dng"
            try:
                enc_ms = encode_at_quality(gtools, dng, gpr_path, q)
                dec_ms = decode_to_dng(gtools, gpr_path, dec_dng)
            except subprocess.CalledProcessError as e:
                print(f"    q={q}: FAILED encode/decode ({e})")
                continue

            gpr_bytes = gpr_path.stat().st_size
            raw_bytes = dng.stat().st_size
            ratio = gpr_bytes / raw_bytes if raw_bytes else float("nan")

            # Read the DNG to get peak
            import rawpy
            r = rawpy.imread(str(dng))
            white = int(r.white_level)
            r.close()
            peak = 65535 if white >= 65000 else (16383 if white >= 16000
                                                  else (4095 if white >= 4000 else white))

            psnr_bayer = bayer_psnr(dng, dec_dng, peak)

            psnr_cnn = None
            if args.with_cnn:
                out_mov = args.out_dir / f"{dng.stem}_q{q}_cnn.mov"
                psnr_cnn = cnn_render_psnr(gpr2prores, gpr_path, dng,
                                            args.cnn_ckpt, out_mov)

            row = {
                "image": dng.name,
                "quality": q,
                "encode_ms": round(enc_ms, 2),
                "decode_ms": round(dec_ms, 2),
                "gpr_bytes": gpr_bytes,
                "ratio_vs_dng": round(ratio, 4),
                "bayer_psnr_dB": round(psnr_bayer, 2),
                "cnn_psnr_dB": round(psnr_cnn, 2) if psnr_cnn is not None else None,
            }
            rows.append(row)
            extra = f" cnn={psnr_cnn:.2f}dB" if psnr_cnn is not None else ""
            print(f"    q={q}: enc={enc_ms:6.0f}ms dec={dec_ms:6.0f}ms "
                  f"{gpr_bytes/1024:8.0f}KB bayer={psnr_bayer:5.2f}dB{extra}")

    csv_path = args.out_dir / "calibration.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            w.writeheader()
            for r in rows:
                w.writerow(r)
    print(f"\nWrote {csv_path}")

    # Aggregate: mean across images per quality
    if rows:
        by_q = {}
        for r in rows:
            by_q.setdefault(r["quality"], []).append(r)
        print("\n== Summary (mean across corpus) ==")
        print(f"{'q':>3s} {'kb/frame':>10s} {'ratio':>8s} {'bayer_dB':>10s}", end="")
        if args.with_cnn:
            print(f" {'cnn_dB':>10s}", end="")
        print()
        for q in qualities:
            if q not in by_q:
                continue
            mean_kb = sum(r["gpr_bytes"] for r in by_q[q]) / len(by_q[q]) / 1024
            mean_ratio = sum(r["ratio_vs_dng"] for r in by_q[q]) / len(by_q[q])
            mean_bayer = sum(r["bayer_psnr_dB"] for r in by_q[q]) / len(by_q[q])
            line = f"{q:>3d} {mean_kb:>10.1f} {mean_ratio:>8.4f} {mean_bayer:>10.2f}"
            if args.with_cnn:
                vals = [r["cnn_psnr_dB"] for r in by_q[q] if r["cnn_psnr_dB"] is not None]
                if vals:
                    line += f" {sum(vals)/len(vals):>10.2f}"
                else:
                    line += " " * 11 + "—"
            print(line)


if __name__ == "__main__":
    main()
