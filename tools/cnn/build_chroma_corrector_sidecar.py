#!/usr/bin/env python3
"""Build sidecar inputs for the Lab chroma-corrector trainer.

The source NPZ is the gate-aligned DMSR tile set:

  codec_R/G1/G2/B: (N, H, W) uint16 codec planes
  tgt_rgb:         (N, 4H, 4W, 3) uint8 target render
  src/src_lookup_names

This writes a compact sidecar NPZ with:

  y_half:          (N, H, W) uint8, VA-Y prediction area-pooled from 4H/4W
  a_naive_half:    (N, H, W) float16, Lab a baseline at codec plane res
  b_naive_half:    (N, H, W) float16, Lab b baseline at codec plane res
  tile_sat_score:  (N,) float32, target 95th-percentile Lab chroma

The default baseline is codec-only Lab so historical checkpoints remain
reproducible. Use ``--baseline-mode demosaic_sips`` to build the production
candidate baseline: full decoded codec raws are wrapped with source DNG
metadata, rendered through sips, bicubic-upscaled to source dimensions, then
sampled on the tile grid and area-downsampled to codec plane resolution.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F
from skimage import color

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from model import build as build_variant  # noqa: E402


RAW_NORM = 16383.0
SOURCE_BAYER_H = 5520
SOURCE_BAYER_W = 8280
CODEC_BAYER_H = 2760
CODEC_BAYER_W = 4140
TILE_CODEC = 128
TILE_TGT_RGB = 512
STRIDE_CODEC = 256
SCALE_TO_BAYER = 4


def _names_from_lookup(lookup) -> list[str]:
    return [s.decode() if isinstance(s, bytes) else str(s) for s in lookup.tolist()]


def _codec_batch(npz, indices: np.ndarray, raw_norm: float) -> torch.Tensor:
    planes = [
        np.asarray(npz[k][indices], dtype=np.float32) / raw_norm
        for k in ("codec_R", "codec_G1", "codec_G2", "codec_B")
    ]
    return torch.from_numpy(np.stack(planes, axis=1))


def _load_y_model(ckpt_path: Path, device: torch.device):
    ck = torch.load(str(ckpt_path), map_location=device, weights_only=False)
    variant = ck.get("variant", "F_ane_no_sr_w16_y")
    model = build_variant(variant)
    model.load_state_dict(ck["backbone_state"])
    model.to(device).eval()
    return model


def _codec_planes_to_naive_lab_half(r, g1, g2, b, raw_norm: float) -> tuple[np.ndarray, np.ndarray]:
    """Cheap codec-only chroma hint at plane resolution.

    The codec planes are already deinterleaved RGGB samples. Average the two
    greens, normalize to display-ish RGB, convert to Lab, and keep a/b. This
    avoids target leakage and gives the corrector a local chroma prior.

    Accepts either a single tile (H, W) or a batch (N, H, W).
    """
    rgb = np.stack([
        r.astype(np.float32),
        0.5 * (g1.astype(np.float32) + g2.astype(np.float32)),
        b.astype(np.float32),
    ], axis=-1)
    rgb = np.clip(rgb / raw_norm, 0.0, 1.0)
    lab = color.rgb2lab(rgb)
    return lab[..., 1].astype(np.float16), lab[..., 2].astype(np.float16)


def _tile_sat_score(tgt_rgb: np.ndarray) -> np.ndarray:
    """Return per-tile 95th percentile Lab chroma for RGB batch."""
    lab = color.rgb2lab(tgt_rgb.astype(np.float32) / 255.0)
    chroma = np.sqrt(lab[..., 1] * lab[..., 1] + lab[..., 2] * lab[..., 2])
    if chroma.ndim == 2:
        return np.asarray([float(np.percentile(chroma, 95))], dtype=np.float32)
    flat = chroma.reshape(chroma.shape[0], -1)
    return np.percentile(flat, 95, axis=1).astype(np.float32)


def _source_paths(source_dirs: list[str]) -> dict[str, Path]:
    out = {}
    for d in source_dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in p.iterdir():
            if f.suffix.lower() == ".dng":
                out[f.stem] = f
    return out


def _codec_paths(pairs_dirs: list[str]) -> dict[str, Path]:
    out = {}
    for d in pairs_dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in p.iterdir():
            if f.name.endswith("_codec.raw"):
                out[f.name[:-len("_codec.raw")]] = f
    return out


def _base_name(src_name: str) -> str:
    return src_name[4:] if src_name.startswith("div_") else src_name


def _render_demosaic_sips_baseline(
    src_name: str,
    source_dng: Path,
    codec_raw: Path,
    gpr_tools: Path,
    cache_dir: Path,
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_png = cache_dir / f"{src_name}_ml2_q3_dec2_none_upscaled.png"
    if out_png.exists() and out_png.stat().st_size > 1000:
        return out_png

    workdir = Path(tempfile.mkdtemp(prefix=f"chroma_sidecar_{src_name}_"))
    try:
        params_dump = subprocess.run(
            [str(gpr_tools), "-i", str(source_dng), "-d", "1"],
            capture_output=True, text=True, check=True,
        )
        lines = [line for line in params_dump.stdout.splitlines() if not line.startswith("[")]
        params = json.loads("\n".join(lines))
        params["input_width"] = CODEC_BAYER_W
        params["input_height"] = CODEC_BAYER_H
        params["input_pitch"] = CODEC_BAYER_W * 2
        params_path = workdir / "params.json"
        params_path.write_text(json.dumps(params))

        dng_out = workdir / "codec_baseline.dng"
        subprocess.run(
            [
                str(gpr_tools), "-i", str(codec_raw), "-w", str(CODEC_BAYER_W),
                "-h", str(CODEC_BAYER_H), "-x", "rggb14", "-a", str(params_path),
                "-o", str(dng_out),
            ],
            capture_output=True, text=True, check=True,
        )
        half_png = workdir / "codec_baseline.png"
        subprocess.run(
            ["sips", "-s", "format", "png", str(dng_out), "--out", str(half_png)],
            capture_output=True, text=True, check=True,
        )
        img = Image.open(half_png).convert("RGB")
        if img.size != (SOURCE_BAYER_W, SOURCE_BAYER_H):
            img = img.resize((SOURCE_BAYER_W, SOURCE_BAYER_H), Image.BICUBIC)
        img.save(out_png)
        return out_png
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _fill_demosaic_sips_ab(
    npz,
    a_mm,
    b_mm,
    names: list[str],
    args,
) -> None:
    sources = _source_paths([p for p in args.source_dirs.split(":") if p])
    codecs = _codec_paths([p for p in args.pairs_dirs.split(":") if p])
    src = np.asarray(npz["src"])
    cache_dir = Path(args.render_cache)
    gpr_tools = Path(args.gpr_tools)
    if not gpr_tools.exists():
        raise FileNotFoundError(gpr_tools)

    missing = []
    for src_name in names:
        base = _base_name(src_name)
        source_dng = sources.get(base)
        codec_raw = codecs.get(src_name) or codecs.get(base)
        if source_dng is None or codec_raw is None:
            missing.append(f"{src_name}: source_dng={source_dng} codec_raw={codec_raw}")
    if missing:
        preview = "\n  ".join(missing[:20])
        extra = "" if len(missing) <= 20 else f"\n  ... {len(missing) - 20} more"
        raise RuntimeError(f"missing demosaic_sips inputs:\n  {preview}{extra}")

    t0 = time.time()
    for sid, src_name in enumerate(names):
        base = _base_name(src_name)
        source_dng = sources.get(base)
        codec_raw = codecs.get(src_name) or codecs.get(base)
        png = _render_demosaic_sips_baseline(src_name, source_dng, codec_raw, gpr_tools, cache_dir)
        lab = color.rgb2lab(np.asarray(Image.open(png).convert("RGB"), dtype=np.float32) / 255.0)
        tile_indices = np.where(src == sid)[0]
        i = 0
        for yc in range(0, 1380 - TILE_CODEC + 1, STRIDE_CODEC):
            for xc in range(0, 2070 - TILE_CODEC + 1, STRIDE_CODEC):
                if i >= len(tile_indices):
                    break
                y = yc * SCALE_TO_BAYER
                x = xc * SCALE_TO_BAYER
                patch = lab[y:y + TILE_TGT_RGB, x:x + TILE_TGT_RGB, 1:3]
                if patch.shape[:2] != (TILE_TGT_RGB, TILE_TGT_RGB):
                    i += 1
                    continue
                ab = torch.from_numpy(np.transpose(patch.astype(np.float32), (2, 0, 1))[None])
                ab_half = F.interpolate(ab, size=(TILE_CODEC, TILE_CODEC), mode="area").squeeze(0).numpy()
                idx = tile_indices[i]
                a_mm[idx] = ab_half[0].astype(np.float16)
                b_mm[idx] = ab_half[1].astype(np.float16)
                i += 1
        if sid == 0 or sid + 1 == len(names) or sid % 10 == 0:
            print(f"  chroma baseline {sid+1}/{len(names)} {src_name} tiles={i} t={time.time()-t0:.1f}s", flush=True)


def _write_zip_stored(out_npz: Path, staging: Path) -> None:
    with zipfile.ZipFile(out_npz, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for fn in sorted(os.listdir(staging)):
            zf.write(staging / fn, arcname=fn)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-npz", required=True)
    ap.add_argument("--y-ckpt", required=True)
    ap.add_argument("--out-npz", required=True)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--raw-norm", type=float, default=RAW_NORM)
    ap.add_argument("--device", default=None, choices=[None, "cpu", "mps", "cuda"])
    ap.add_argument("--baseline-mode", choices=["codec_lab", "demosaic_sips"], default="codec_lab")
    ap.add_argument(
        "--pairs-dirs",
        default=os.environ.get(
            "PAIRS_DIRS",
            "/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3_dec2:"
            "/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3_dec2_diverse:"
            "/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3_dec2_ood",
        ),
    )
    ap.add_argument(
        "--source-dirs",
        default=os.environ.get(
            "SOURCE_DIRS",
            "/Volumes/OWC_8TB/barnsky_full_dngs:/Volumes/OWC_8TB/gpr_cnn/diverse_dngs",
        ),
    )
    ap.add_argument("--gpr-tools", default=str(Path.cwd() / "build-local/source/app/gpr_tools/gpr_tools"))
    ap.add_argument("--render-cache", default="/Volumes/OWC_8TB/gpr_cnn/render_cache_chroma_baseline")
    ap.add_argument("--resume", action="store_true", help="Reuse existing staging .npy files when shapes match.")
    args = ap.parse_args()

    in_npz = Path(args.in_npz)
    out_npz = Path(args.out_npz)
    y_ckpt = Path(args.y_ckpt)
    if not in_npz.exists():
        raise FileNotFoundError(in_npz)
    if not y_ckpt.exists():
        raise FileNotFoundError(y_ckpt)

    if args.device is None:
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    print(f"loading {in_npz}", flush=True)
    npz = np.load(in_npz, mmap_mode="r", allow_pickle=True)
    for k in ("codec_R", "codec_G1", "codec_G2", "codec_B", "tgt_rgb", "src", "src_lookup_names"):
        if k not in npz.files:
            raise RuntimeError(f"{in_npz} missing required field {k!r}")

    n, h, w = npz["codec_R"].shape
    names = _names_from_lookup(np.asarray(npz["src_lookup_names"]))
    print(f"tiles: {n}  codec plane: {h}x{w}  device={device}", flush=True)

    staging = out_npz.with_suffix(out_npz.suffix + ".staging")
    if staging.exists() and not args.resume:
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    def _open_or_create(name: str, dtype, shape):
        p = staging / name
        if args.resume and p.exists():
            arr = np.load(p, mmap_mode="r+")
            if arr.shape == shape and arr.dtype == np.dtype(dtype):
                return arr, True
        return np.lib.format.open_memmap(p, mode="w+", dtype=dtype, shape=shape), False

    y_mm, y_resumed = _open_or_create("y_half.npy", np.uint8, (n, h, w))
    a_mm, a_resumed = _open_or_create("a_naive_half.npy", np.float16, (n, h, w))
    b_mm, b_resumed = _open_or_create("b_naive_half.npy", np.float16, (n, h, w))
    sat, sat_resumed = _open_or_create("tile_sat_score.npy", np.float32, (n,))

    y_model = _load_y_model(y_ckpt, device)
    t0 = time.time()
    skip_tile_phase = args.resume and y_resumed and sat_resumed and (
        args.baseline_mode == "demosaic_sips" or (a_resumed and b_resumed)
    )
    if skip_tile_phase:
        print("  resuming from existing tile sidecar arrays", flush=True)
    else:
        for start in range(0, n, args.batch):
            end = min(n, start + args.batch)
            idx = np.arange(start, end)
            x = _codec_batch(npz, idx, args.raw_norm).to(device)
            with torch.no_grad():
                y_full = y_model(x).clamp(0, 1)
                y_half = F.avg_pool2d(y_full, kernel_size=4, stride=4)
            y_mm[start:end] = np.clip(
                y_half.squeeze(1).cpu().numpy() * 255.0 + 0.5, 0, 255
            ).astype(np.uint8)

            if args.baseline_mode == "codec_lab":
                a, b = _codec_planes_to_naive_lab_half(
                    np.asarray(npz["codec_R"][start:end]),
                    np.asarray(npz["codec_G1"][start:end]),
                    np.asarray(npz["codec_G2"][start:end]),
                    np.asarray(npz["codec_B"][start:end]),
                    args.raw_norm,
                )
                a_mm[start:end] = a
                b_mm[start:end] = b
            sat[start:end] = _tile_sat_score(np.asarray(npz["tgt_rgb"][start:end]))

            if start == 0 or end == n or (start // args.batch) % 25 == 0:
                print(f"  {end}/{n} tiles  t={time.time() - t0:.1f}s", flush=True)

    if args.baseline_mode == "demosaic_sips":
        print("building demosaic_sips display-space chroma baseline", flush=True)
        _fill_demosaic_sips_ab(npz, a_mm, b_mm, names, args)

    np.save(staging / "src.npy", np.asarray(npz["src"]))
    np.save(staging / "src_lookup_names.npy", np.asarray(npz["src_lookup_names"]), allow_pickle=True)
    (staging / "README.txt").write_text(
        "Sidecar for train_chroma_corrector.py. "
        f"a_naive_half/b_naive_half baseline_mode={args.baseline_mode}, not target-derived.\n"
    )
    (staging / "baseline_mode.txt").write_text(args.baseline_mode + "\n")
    print(f"writing {out_npz}", flush=True)
    _write_zip_stored(out_npz, staging)
    shutil.rmtree(staging)
    print(f"DONE {out_npz} size={out_npz.stat().st_size / (1024 ** 2):.1f} MiB", flush=True)


if __name__ == "__main__":
    main()
