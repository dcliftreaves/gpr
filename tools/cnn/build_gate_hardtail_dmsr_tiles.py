#!/usr/bin/env python3
"""Build a small gate-space BIDO training NPZ for hard PREVIEW images.

This intentionally uses the same codec and REF render path as
tests/quality_gates/run_gate.py:
  source DNG -> ml2_q3_dec2 encode/decode -> half-res Bayer planes
  source Bayer -> gpr_tools wrap -> sips REF RGB

The output schema matches tiles_ml2_q3_dec2_dmsr_gate.npz:
codec_R/G1/G2/B, tgt_rgb, src, src_lookup_names. It also stores
codec_mosaic: the decoded half-res Bayer tile before 2x2 phase packing.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from skimage import color

try:
    import pywt
except Exception:  # pragma: no cover - optional target-filter dependency
    pywt = None

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests/quality_gates"))
import run_gate  # noqa: E402

DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_hardtail.npz")
DEFAULT_RENDER_CACHE = Path("/Volumes/OWC_8TB/gpr_work/cnn/render_cache_gate_hardtail")
DEFAULT_IMAGE_IDS = ("Z8Z_0001", "Z8Z_0067", "Z8Z_5323", "Z8Z_6693")

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


def _tile_image(
    planes: np.ndarray,
    mosaic: np.ndarray,
    ref_rgb: np.ndarray,
    stride: int,
    tile_codec: int,
    src_id: int,
) -> tuple[list[np.ndarray], list[np.ndarray], list[np.ndarray],
           list[int], list[tuple[int, int]]]:
    _, hp, wp = planes.shape
    tile_rgb = tile_codec * SCALE_TO_SOURCE
    codec_tiles: list[np.ndarray] = []
    mosaic_tiles: list[np.ndarray] = []
    rgb_tiles: list[np.ndarray] = []
    src_ids: list[int] = []
    coords: list[tuple[int, int]] = []
    for yc in range(0, hp - tile_codec + 1, stride):
        for xc in range(0, wp - tile_codec + 1, stride):
            y = yc * SCALE_TO_SOURCE
            x = xc * SCALE_TO_SOURCE
            if y + tile_rgb > ref_rgb.shape[0] or x + tile_rgb > ref_rgb.shape[1]:
                continue
            codec_tiles.append(planes[:, yc:yc + tile_codec, xc:xc + tile_codec])
            mosaic_tiles.append(mosaic[yc * 2:(yc + tile_codec) * 2,
                                       xc * 2:(xc + tile_codec) * 2])
            rgb_tiles.append(ref_rgb[y:y + tile_rgb, x:x + tile_rgb, :])
            src_ids.append(src_id)
            coords.append((yc, xc))
    return codec_tiles, mosaic_tiles, rgb_tiles, src_ids, coords


def _resize_lowpass_luma(l_chan: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return l_chan.astype(np.float32)
    h, w = l_chan.shape
    small = cv2.resize(
        l_chan,
        (max(1, w // factor), max(1, h // factor)),
        interpolation=cv2.INTER_AREA,
    )
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)


def _wavelet_lowpass_luma(
    l_chan: np.ndarray,
    wavelet: str,
    levels: int,
    remove_hf_levels: int,
) -> np.ndarray:
    if pywt is None:
        raise RuntimeError("pywt is required for --target-l-filter wavelet")
    if remove_hf_levels <= 0:
        return l_chan.astype(np.float32)
    coeffs = pywt.wavedec2(l_chan.astype(np.float32), wavelet, level=levels)
    first_removed = max(1, len(coeffs) - remove_hf_levels)
    out = [coeffs[0]]
    for idx, detail in enumerate(coeffs[1:], start=1):
        if idx >= first_removed:
            out.append(tuple(np.zeros_like(c) for c in detail))
        else:
            out.append(detail)
    rec = pywt.waverec2(out, wavelet).astype(np.float32)
    return rec[: l_chan.shape[0], : l_chan.shape[1]]


def _gaussian_lowpass_luma(l_chan: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return l_chan.astype(np.float32)
    return cv2.GaussianBlur(l_chan.astype(np.float32), (0, 0), sigma).astype(np.float32)


def _filtered_luma_target(ref_rgb: np.ndarray, args: argparse.Namespace) -> np.ndarray:
    lab = color.rgb2lab(ref_rgb.astype(np.float32) / 255.0).astype(np.float32)
    l_chan = lab[..., 0]
    target_filter = args.target_l_filter
    if target_filter == "auto":
        target_filter = "resize" if args.target_l_lowpass_factor > 1 else "none"
    if target_filter == "none":
        return ref_rgb
    if target_filter == "resize":
        l_full = _resize_lowpass_luma(l_chan, args.target_l_lowpass_factor)
    elif target_filter == "wavelet":
        l_full = _wavelet_lowpass_luma(
            l_chan,
            args.target_l_wavelet,
            args.target_l_wavelet_levels,
            args.target_l_remove_hf_levels,
        )
    elif target_filter == "gaussian":
        l_full = _gaussian_lowpass_luma(l_chan, args.target_l_gaussian_sigma)
    else:
        raise RuntimeError(f"unsupported target_l_filter {target_filter!r}")
    neutral_lab = np.zeros_like(lab)
    neutral_lab[..., 0] = np.clip(l_full, 0.0, 100.0)
    return np.clip(color.lab2rgb(neutral_lab) * 255.0, 0, 255).astype(np.uint8)


def build(args: argparse.Namespace) -> None:
    registry = json.loads((REPO / "pipelines/registry.json").read_text())
    codec = registry["codecs"][args.codec]
    dms = registry["demosaicers"][args.demosaic]
    images = _load_gate_images(args.images)

    codec_tiles: list[np.ndarray] = []
    mosaic_tiles: list[np.ndarray] = []
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
        target_rgb = _filtered_luma_target(ref_rgb, args)
        c_tiles, m_tiles, r_tiles, s_ids, coords = _tile_image(
            planes, dec, target_rgb, args.stride, args.tile_codec, src_id
        )
        codec_tiles.extend(c_tiles)
        mosaic_tiles.extend(m_tiles)
        rgb_tiles.extend(r_tiles)
        src.extend(s_ids)
        tile_yx.extend(coords)
        print(f"  tiles: {len(c_tiles)}", flush=True)

    if not codec_tiles:
        raise SystemExit("no tiles produced")

    codec_arr = np.stack(codec_tiles, axis=0).astype(np.uint16)
    mosaic_arr = np.stack(mosaic_tiles, axis=0).astype(np.uint16)
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
        codec_mosaic=mosaic_arr,
        tgt_rgb=tgt_rgb,
        src=src_arr,
        src_lookup_names=names_arr,
        tile_yx=tile_yx_arr,
        tile_stride=np.asarray([args.stride], dtype=np.int32),
        tile_codec=np.asarray([args.tile_codec], dtype=np.int32),
        tile_rgb=np.asarray([args.tile_codec * SCALE_TO_SOURCE], dtype=np.int32),
        target_l_lowpass_factor=np.asarray([args.target_l_lowpass_factor], dtype=np.int32),
        target_l_filter=np.asarray([args.target_l_filter], dtype=object),
        target_l_wavelet=np.asarray([args.target_l_wavelet], dtype=object),
        target_l_wavelet_levels=np.asarray([args.target_l_wavelet_levels], dtype=np.int32),
        target_l_remove_hf_levels=np.asarray([args.target_l_remove_hf_levels], dtype=np.int32),
        target_l_gaussian_sigma=np.asarray([args.target_l_gaussian_sigma], dtype=np.float32),
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
    ap.add_argument("--stride", type=int, default=256,
                    help="Stride in codec-plane pixels. 256 reproduces the "
                         "original sparse corpus; 128 gives denser overlap.")
    ap.add_argument("--tile-codec", type=int, default=128,
                    help="Tile size in codec-plane pixels. 128 yields 512px "
                         "RGB targets; larger values train with more context.")
    ap.add_argument("--target-l-lowpass-factor", type=int, default=0,
                    help="If >1, replace target RGB with neutral grayscale "
                         "whose Lab L is REF Lab L low-passed by this factor. "
                         "Use factor=2 for the recoverable PREVIEW detail target.")
    ap.add_argument("--target-l-filter", choices=["auto", "none", "resize", "wavelet", "gaussian"],
                    default="auto",
                    help="Lab-L target filter. 'auto' preserves the legacy "
                         "--target-l-lowpass-factor behavior.")
    ap.add_argument("--target-l-wavelet", default="sym4",
                    help="Wavelet used when --target-l-filter wavelet.")
    ap.add_argument("--target-l-wavelet-levels", type=int, default=3,
                    help="Wavelet decomposition levels for Lab-L target filtering.")
    ap.add_argument("--target-l-remove-hf-levels", type=int, default=2,
                    help="Number of finest wavelet detail levels removed from REF Lab-L.")
    ap.add_argument("--target-l-gaussian-sigma", type=float, default=1.2,
                    help="Gaussian sigma for --target-l-filter gaussian.")
    build(ap.parse_args())


if __name__ == "__main__":
    main()
