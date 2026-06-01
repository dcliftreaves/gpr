#!/usr/bin/env python3
"""Build a small gate-space BIDO training NPZ for hard PREVIEW images.

This intentionally uses the same codec and REF render path as
tests/quality_gates/run_gate.py:
  source DNG -> ml2_q3_dec2 encode/decode -> half-res Bayer planes
  source Bayer -> gpr_tools wrap -> sips REF RGB

The output schema matches tiles_ml2_q3_dec2_dmsr_gate.npz:
codec_R/G1/G2/B, tgt_rgb, src, src_lookup_names.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests/quality_gates"))
import run_gate  # noqa: E402

DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_dmsr_gate_hardtail.npz")
DEFAULT_RENDER_CACHE = Path("/Volumes/OWC_8TB/gpr_cnn/render_cache_gate_hardtail")
DEFAULT_IMAGE_IDS = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")

TILE_CODEC = 128
TILE_RGB = 512
STRIDE = 256
SCALE_TO_SOURCE = 4


def _load_gate_images(ids: list[str]) -> list[dict]:
    test_set = json.loads((REPO / "tests/quality_gates/test_set.json").read_text())
    by_id = {im["id"]: im for im in test_set["images"]}
    missing = [image_id for image_id in ids if image_id not in by_id]
    if missing:
        raise SystemExit(f"image ids not in gate test_set.json: {missing}")
    return [by_id[image_id] for image_id in ids]


def _render_ref_cached(image_id: str, bayer: np.ndarray, dms: dict, src_dng: Path,
                       cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{image_id}_REF.png"
    if out.exists() and out.stat().st_size > 1000:
        return out
    workdir = Path(tempfile.mkdtemp(prefix=f"hardtail_ref_{image_id}_"))
    try:
        run_gate.demosaic_to_png(bayer, dms, src_dng, workdir, out)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return out


def _codec_planes(decoded_bayer: np.ndarray) -> np.ndarray:
    h, w = decoded_bayer.shape
    h -= h & 1
    w -= w & 1
    b = decoded_bayer[:h, :w]
    return np.stack(
        [b[0::2, 0::2], b[0::2, 1::2], b[1::2, 0::2], b[1::2, 1::2]],
        axis=0,
    )


def _tile_image(planes: np.ndarray, ref_rgb: np.ndarray,
                src_id: int) -> tuple[list[np.ndarray], list[np.ndarray], list[int], list[tuple[int, int]]]:
    _, hp, wp = planes.shape
    codec_tiles: list[np.ndarray] = []
    rgb_tiles: list[np.ndarray] = []
    src_ids: list[int] = []
    coords: list[tuple[int, int]] = []
    for yc in range(0, hp - TILE_CODEC + 1, STRIDE):
        for xc in range(0, wp - TILE_CODEC + 1, STRIDE):
            y = yc * SCALE_TO_SOURCE
            x = xc * SCALE_TO_SOURCE
            if y + TILE_RGB > ref_rgb.shape[0] or x + TILE_RGB > ref_rgb.shape[1]:
                continue
            codec_tiles.append(planes[:, yc:yc + TILE_CODEC, xc:xc + TILE_CODEC])
            rgb_tiles.append(ref_rgb[y:y + TILE_RGB, x:x + TILE_RGB, :])
            src_ids.append(src_id)
            coords.append((yc, xc))
    return codec_tiles, rgb_tiles, src_ids, coords


def build(args: argparse.Namespace) -> None:
    registry = json.loads((REPO / "pipelines/registry.json").read_text())
    codec = registry["codecs"][args.codec]
    dms = registry["demosaicers"][args.demosaic]
    images = _load_gate_images(args.images)

    codec_tiles: list[np.ndarray] = []
    rgb_tiles: list[np.ndarray] = []
    src: list[int] = []
    tile_yx: list[tuple[int, int]] = []
    names: list[str] = []
    t0 = time.time()
    for src_id, im in enumerate(images):
        image_id = im["id"]
        names.append(image_id)
        src_dng = Path(im["path"])
        if not src_dng.exists():
            raise SystemExit(f"missing source DNG for {image_id}: {src_dng}")
        print(f"[{src_id + 1}/{len(images)}] {image_id}", flush=True)
        bayer, w, h = run_gate.read_source_bayer(str(src_dng))
        workdir = Path(tempfile.mkdtemp(prefix=f"hardtail_codec_{image_id}_"))
        try:
            dec, enc_bytes, enc_ms = run_gate.encode_decode(
                codec, bayer, w, h, workdir, src_dng=str(src_dng)
            )
            print(
                f"  codec decoded {dec.shape[1]}x{dec.shape[0]} "
                f"{enc_bytes} bytes {enc_ms:.1f} ms",
                flush=True,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        planes = _codec_planes(dec)
        ref_png = _render_ref_cached(image_id, bayer, dms, src_dng, args.render_cache)
        ref_rgb = np.asarray(Image.open(ref_png).convert("RGB"))
        c_tiles, r_tiles, s_ids, coords = _tile_image(planes, ref_rgb, src_id)
        codec_tiles.extend(c_tiles)
        rgb_tiles.extend(r_tiles)
        src.extend(s_ids)
        tile_yx.extend(coords)
        print(f"  tiles: {len(c_tiles)}", flush=True)

    if not codec_tiles:
        raise SystemExit("no tiles produced")

    codec_arr = np.stack(codec_tiles, axis=0).astype(np.uint16)
    tgt_rgb = np.stack(rgb_tiles, axis=0).astype(np.uint8)
    src_arr = np.asarray(src, dtype=np.int32)
    tile_yx_arr = np.asarray(tile_yx, dtype=np.int32)
    names_arr = np.asarray(names, dtype=object)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        args.out,
        codec_R=codec_arr[:, 0],
        codec_G1=codec_arr[:, 1],
        codec_G2=codec_arr[:, 2],
        codec_B=codec_arr[:, 3],
        tgt_rgb=tgt_rgb,
        src=src_arr,
        src_lookup_names=names_arr,
        tile_yx=tile_yx_arr,
    )
    print(
        f"DONE {args.out}  tiles={len(src_arr)}  "
        f"size={args.out.stat().st_size / (1024 ** 2):.1f} MiB  "
        f"t={time.time() - t0:.1f}s",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--render-cache", type=Path, default=DEFAULT_RENDER_CACHE)
    ap.add_argument("--codec", default="ml2_q3_dec2")
    ap.add_argument("--demosaic", default="sips_via_gpr_tools")
    ap.add_argument("--images", nargs="+", default=list(DEFAULT_IMAGE_IDS))
    build(ap.parse_args())


if __name__ == "__main__":
    main()
