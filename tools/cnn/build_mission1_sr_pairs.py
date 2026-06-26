#!/usr/bin/env python3
"""Build Mission 1 native-12MP to 50MP Bayer super-resolution pairs.

The 12MP capture path is native camera output and does not need capture-side
downsampling. This tool uses 50MP Mission 1 raws only to synthesize training
pairs for the optional desktop upres path:

    50MP Bayer -> same-color Bayer low-pass/downsample -> 12MP Bayer
              -> optional q0/1-level codec degradation -> 50MP target

The downsample happens per Bayer color plane, preserving RGGB phase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - required only for image/pair generation
    np = None

try:
    import cv2
except ImportError:  # pragma: no cover - only needed by high-quality resize modes
    cv2 = None

try:
    import rawpy
except ImportError:  # pragma: no cover - only needed for --input-kind dng
    rawpy = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mission1_native12_fll2_t2_profile import PROFILE_ID as CURRENT_PROFILE_ID  # noqa: E402
from mission1_native12_fll2_t2_profile import effective_profile_env  # noqa: E402
from mission1_native12_fll2_t2_profile import profile_env  # noqa: E402


RAW_SCALE = 16383.0
DEFAULT_HI_W = 8192
DEFAULT_HI_H = 6144


def file_sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require_numpy() -> Any:
    if np is None:
        raise RuntimeError("Mission 1 SR pair generation requires numpy")
    return np


MISSION1_CODEC_PROFILES: dict[str, dict[str, Any]] = {
    "current_t233": {
        "profile_id": CURRENT_PROFILE_ID,
        "description": "registered 20+ fps quality profile, LH/HL/HH=2/3/3",
        "quality": 8,
        "levels": 1,
        "env": {},
    },
    "t236_ch2lh3": {
        "profile_id": "mission1_native12_t236_ch2lh3_q8_avg6656_quality_boundary",
        "description": "quality/storage boundary, still below strict-24 timing on Pi",
        "quality": 8,
        "levels": 1,
        "env": {
            "FUSED_LL_RICE_KS": "6,6,5,6",
            "GPR_INLINE_DENOISE_T_HH": "6",
            "GPR_INLINE_DENOISE_T_CH2_LH": "3",
        },
    },
    "t356_ch2lh3": {
        "profile_id": "mission1_native12_t356_ch2lh3_q8_avg6656_near24_speed_tier",
        "description": "near-24 speed tier, quality-failing without SR compensation",
        "quality": 8,
        "levels": 1,
        "env": {
            "FUSED_LL_RICE_KS": "6,6,5,6",
            "GPR_INLINE_DENOISE_T_LH": "3",
            "GPR_INLINE_DENOISE_T_HL": "5",
            "GPR_INLINE_DENOISE_T_HH": "6",
            "GPR_INLINE_DENOISE_T_CH2_LH": "3",
        },
    },
    "t468_ch2lh4": {
        "profile_id": "mission1_native12_t468_ch2lh4_q8_avg6656_speed_tier",
        "description": "comfortable 24 fps speed tier, quality-failing without SR compensation",
        "quality": 8,
        "levels": 1,
        "env": {
            "FUSED_LL_RICE_KS": "6,6,5,6",
            "GPR_INLINE_DENOISE_T_LH": "4",
            "GPR_INLINE_DENOISE_T_HL": "6",
            "GPR_INLINE_DENOISE_T_HH": "8",
            "GPR_INLINE_DENOISE_T_CH2_LH": "4",
        },
    },
}


def mission1_codec_profile(codec: str) -> dict[str, Any] | None:
    return MISSION1_CODEC_PROFILES.get(codec)


def mission1_codec_env(codec: str) -> dict[str, str]:
    profile = mission1_codec_profile(codec)
    if profile is None:
        raise ValueError(f"{codec} is not a Mission 1 FLL2 codec profile")
    env = profile_env()
    env.update({str(key): str(value) for key, value in (profile.get("env") or {}).items()})
    env["FUSED_QUALITY"] = str(profile.get("quality", 8))
    env["FUSED_WAVELET_LEVELS"] = str(profile.get("levels", 1))
    env["FUSED_MULTI_LEVEL"] = "0"
    return env


def read_u16_raw(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} pixels, expected {expected}")
    return arr.reshape((height, width))


def read_dng_raw(path: Path, width: int, height: int) -> np.ndarray:
    if rawpy is None:
        raise RuntimeError("--input-kind dng requires rawpy")
    dng = rawpy.imread(str(path))
    try:
        raw = dng.raw_image.copy()
    finally:
        dng.close()
    if raw.shape != (height, width):
        raise ValueError(f"{path} has raw shape {raw.shape}, expected {(height, width)}")
    return raw.astype(np.uint16, copy=False)


def read_high_bayer(path: Path, width: int, height: int, input_kind: str) -> np.ndarray:
    if input_kind == "raw":
        return read_u16_raw(path, width, height)
    if input_kind == "dng":
        return read_dng_raw(path, width, height)
    raise ValueError(f"unknown input kind: {input_kind}")


def write_u16_raw(path: Path, arr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arr.astype("<u2", copy=False).tofile(path)


def deinterleave(bayer: np.ndarray) -> np.ndarray:
    return np.stack(
        [
            bayer[0::2, 0::2],
            bayer[0::2, 1::2],
            bayer[1::2, 0::2],
            bayer[1::2, 1::2],
        ],
        axis=0,
    )


def reinterleave(planes: np.ndarray) -> np.ndarray:
    _, h, w = planes.shape
    out = np.empty((h * 2, w * 2), dtype=np.uint16)
    out[0::2, 0::2] = planes[0]
    out[0::2, 1::2] = planes[1]
    out[1::2, 0::2] = planes[2]
    out[1::2, 1::2] = planes[3]
    return out


def resize_plane_cv2(plane: np.ndarray, mode: str) -> np.ndarray:
    if cv2 is None:
        raise RuntimeError(f"downsample mode {mode} requires cv2")
    src = plane.astype(np.float32)
    if mode == "gaussian_area":
        src = cv2.GaussianBlur(src, (0, 0), sigmaX=0.85, sigmaY=0.85, borderType=cv2.BORDER_REPLICATE)
        interpolation = cv2.INTER_AREA
    elif mode == "area":
        interpolation = cv2.INTER_AREA
    elif mode == "lanczos4":
        interpolation = cv2.INTER_LANCZOS4
    else:
        raise ValueError(f"unknown cv2 downsample mode: {mode}")
    out = cv2.resize(src, (plane.shape[1] // 2, plane.shape[0] // 2), interpolation=interpolation)
    return np.clip(out + 0.5, 0, 65535).astype(np.uint16)


def downsample_plane_2x(plane: np.ndarray, mode: str) -> np.ndarray:
    """Downsample one Bayer color plane by 2x.

    The high-quality modes resize only within the same Bayer color plane, so
    RGGB phase is preserved while the synthetic 12MP source is antialiased.
    """
    if mode == "sample":
        return plane[0::2, 0::2].copy()
    if mode == "avg2":
        a = plane[0::2, 0::2].astype(np.uint32)
        b = plane[0::2, 1::2].astype(np.uint32)
        c = plane[1::2, 0::2].astype(np.uint32)
        d = plane[1::2, 1::2].astype(np.uint32)
        return ((a + b + c + d + 2) // 4).astype(np.uint16)
    if mode == "avg3x3_same":
        p = np.pad(plane.astype(np.uint32), ((1, 1), (1, 1)), mode="edge")
        s = (
            p[0:-2, 0:-2]
            + p[0:-2, 1:-1]
            + p[0:-2, 2:]
            + p[1:-1, 0:-2]
            + p[1:-1, 1:-1]
            + p[1:-1, 2:]
            + p[2:, 0:-2]
            + p[2:, 1:-1]
            + p[2:, 2:]
        )
        filt = ((s + 4) // 9).astype(np.uint16)
        return filt[0::2, 0::2].copy()
    if mode in {"area", "gaussian_area", "lanczos4"}:
        return resize_plane_cv2(plane, mode)
    raise ValueError(f"unknown downsample mode: {mode}")


def synthesize_12mp_from_50mp(bayer50: np.ndarray, mode: str) -> np.ndarray:
    if mode in {"gaussian_area", "area", "sample"}:
        from bayer_resample import cfa_downsample_2x

        return cfa_downsample_2x(bayer50, mode=mode)
    hi = deinterleave(bayer50)
    low = np.stack([downsample_plane_2x(ch, mode) for ch in hi], axis=0)
    return reinterleave(low)


def run_codec(
    coeff_tool: Path,
    raw_in: Path,
    raw_out: Path,
    gpr_out: Path,
    quality: int,
    levels: int,
    codec: str,
    width: int,
    height: int,
) -> None:
    profile = mission1_codec_profile(codec)
    if profile is not None:
        env = mission1_codec_env(codec)
    else:
        env = os.environ.copy()
        env.update(
            {
                "GPR_INCLUDE_LL": "1",
                "FUSED_MULTI_LEVEL": "1",
                "FUSED_WAVELET_LEVELS": str(levels),
                "FUSED_QUALITY": str(quality),
            }
        )
    env["GPR_SAVE_TO"] = str(gpr_out)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    gpr_out.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        [str(coeff_tool), str(raw_in), str(width), str(height), str(raw_out)],
        env=env,
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"codec failed for {raw_in}: {cp.stderr[-1000:]}")


def list_50mp_inputs(input_dir: Path, input_kind: str, stems: list[str] | None) -> list[Path]:
    suffix = ".dng" if input_kind == "dng" else ".raw"
    paths = sorted(input_dir.glob(f"*{suffix}"))
    if stems:
        keep = set(stems)
        paths = [p for p in paths if p.stem in keep]
    if not paths:
        raise ValueError(f"no {input_kind} files found in {input_dir}")
    return paths


def load_tile_manifest(path: Path | None, low_tile: int, repeat: int) -> dict[str, list[dict[str, Any]]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text())
    tiles = payload.get("tiles")
    if not isinstance(tiles, list):
        raise ValueError(f"{path} does not contain a tiles list")
    by_image: dict[str, list[dict[str, Any]]] = {}
    for tile in tiles:
        image_id = str(tile.get("image_id", ""))
        if not image_id:
            raise ValueError(f"{path} contains a tile without image_id")
        tile_low = int(tile.get("low_tile", low_tile))
        if tile_low != low_tile:
            raise ValueError(f"{path} tile for {image_id} has low_tile={tile_low}, expected {low_tile}")
        x = int(tile["low_x"])
        y = int(tile["low_y"])
        row = {
            "image_id": image_id,
            "low_x": x,
            "low_y": y,
            "low_tile": low_tile,
            "sample_source": "tile_manifest",
            "tile_manifest": str(path),
        }
        for key in ("score", "rank", "score_mode", "source_compare"):
            if key in tile:
                row[key] = tile[key]
        by_image.setdefault(image_id, []).extend([dict(row) for _ in range(max(1, repeat))])
    return by_image


def sample_tiles(
    low_planes: np.ndarray,
    high_planes: np.ndarray,
    image_id: str,
    tiles_per_image: int,
    low_tile: int,
    rng: random.Random,
    prescribed_tiles: list[dict[str, Any]] | None = None,
    manifest_only: bool = False,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    _, low_h, low_w = low_planes.shape
    high_tile = low_tile * 2
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    for tile in prescribed_tiles or []:
        x = int(tile["low_x"])
        y = int(tile["low_y"])
        if x < 0 or y < 0 or x + low_tile > low_w or y + low_tile > low_h:
            raise ValueError(f"manifest tile for {image_id} is out of bounds: x={x} y={y} low_tile={low_tile}")
        xs.append(low_planes[:, y : y + low_tile, x : x + low_tile])
        ys.append(high_planes[:, y * 2 : y * 2 + high_tile, x * 2 : x * 2 + high_tile])
        row = dict(tile)
        row.update({"image_id": image_id, "low_x": x, "low_y": y, "low_tile": low_tile})
        rows.append(row)
    random_tiles = 0 if manifest_only else tiles_per_image
    for _ in range(random_tiles):
        y = rng.randrange(0, low_h - low_tile + 1)
        x = rng.randrange(0, low_w - low_tile + 1)
        xs.append(low_planes[:, y : y + low_tile, x : x + low_tile])
        ys.append(high_planes[:, y * 2 : y * 2 + high_tile, x * 2 : x * 2 + high_tile])
        rows.append({"image_id": image_id, "low_x": x, "low_y": y, "low_tile": low_tile, "sample_source": "random"})
    if not xs:
        raise ValueError(f"no tiles selected for {image_id}")
    return np.stack(xs).astype(np.uint16), np.stack(ys).astype(np.uint16), rows


def main() -> int:
    require_numpy()

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw50-dir", type=Path, required=True)
    ap.add_argument("--input-kind", choices=("raw", "dng"), default="raw")
    ap.add_argument("--high-width", type=int, default=DEFAULT_HI_W)
    ap.add_argument("--high-height", type=int, default=DEFAULT_HI_H)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument(
        "--write-high-raw-dir",
        type=Path,
        help="optional directory for full-frame high-resolution raw targets used by full-frame SR eval",
    )
    ap.add_argument("--coeff-tool", type=Path, default=Path("build-local/bin/coeff_io_tool"))
    ap.add_argument("--stem", action="append", help="limit to specific 50MP stem; repeatable")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tiles-per-image", type=int, default=128)
    ap.add_argument("--low-tile", type=int, default=128)
    ap.add_argument(
        "--tile-manifest",
        type=Path,
        help="optional hard-tile manifest from mine_mission1_sr_hard_tiles.py",
    )
    ap.add_argument(
        "--manifest-only",
        action="store_true",
        help="use only manifest tiles instead of appending random tiles",
    )
    ap.add_argument(
        "--manifest-repeat",
        type=int,
        default=1,
        help="repeat each manifest tile this many times in the pair corpus",
    )
    ap.add_argument(
        "--downsample",
        choices=("gaussian_area", "area", "lanczos4", "avg3x3_same", "avg2", "sample"),
        default="gaussian_area",
    )
    ap.add_argument(
        "--allow-diagnostic-downsample",
        action="store_true",
        help="allow non-production downsample modes for explicit diagnostics",
    )
    ap.add_argument(
        "--codec",
        choices=("none", "q0_l1", *MISSION1_CODEC_PROFILES.keys()),
        default="current_t233",
    )
    ap.add_argument("--seed", type=int, default=20260616)
    args = ap.parse_args()

    if args.high_width % 4 != 0 or args.high_height % 4 != 0:
        raise ValueError("high dimensions must be divisible by 4 for same-color Bayer 2x downsample")
    lo_w = args.high_width // 2
    lo_h = args.high_height // 2
    production_downsample = args.downsample == "gaussian_area"
    if not production_downsample and not args.allow_diagnostic_downsample:
        raise ValueError(
            f"downsample={args.downsample!r} is diagnostic-only; use gaussian_area for production "
            "50MP-to-12MP SR pairs or pass --allow-diagnostic-downsample"
        )
    rng = random.Random(args.seed)
    paths = list_50mp_inputs(args.raw50_dir, args.input_kind, args.stem)
    if args.limit:
        paths = paths[: args.limit]
    manifest_tiles = load_tile_manifest(args.tile_manifest, args.low_tile, args.manifest_repeat)
    downsample_impl = (
        "tools/bayer_resample.py:cfa_downsample_2x"
        if args.downsample in {"gaussian_area", "area", "sample"}
        else "tools/cnn/build_mission1_sr_pairs.py:diagnostic_same_plane_downsample"
    )
    downsample_impl_path = (
        Path(__file__).resolve().parents[1] / "bayer_resample.py"
        if args.downsample in {"gaussian_area", "area", "sample"}
        else Path(__file__).resolve()
    )
    downsample_policy = (
        "cfa_same_color_gaussian_area_2x"
        if production_downsample
        else f"diagnostic_cfa_same_color_{args.downsample}_2x"
    )
    codec_profile = mission1_codec_profile(args.codec)
    codec_env_contract = (
        effective_profile_env(mission1_codec_env(args.codec)) if codec_profile is not None else None
    )
    coeff_tool_sha256 = file_sha256(args.coeff_tool)
    downsample_impl_sha256 = file_sha256(downsample_impl_path)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)

    all_x: list[np.ndarray] = []
    all_y: list[np.ndarray] = []
    tile_rows: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []

    for raw50 in paths:
        image_id = raw50.stem
        print(f"build pairs: {image_id}", flush=True)
        high_bayer = read_high_bayer(raw50, args.high_width, args.high_height, args.input_kind)
        high_target_path = None
        if args.write_high_raw_dir:
            high_target_path = args.write_high_raw_dir / f"{image_id}.raw"
            write_u16_raw(high_target_path, high_bayer)
        high_planes = deinterleave(high_bayer)
        low_bayer = synthesize_12mp_from_50mp(high_bayer, args.downsample)
        low_clean_path = args.work_dir / "low12_clean" / f"{image_id}.raw"
        write_u16_raw(low_clean_path, low_bayer)

        low_source_path = low_clean_path
        codec_gpr_path = None
        if args.codec != "none":
            codec_tag = args.codec
            low_dec_path = args.work_dir / f"low12_{codec_tag}_dec" / f"{image_id}.raw"
            codec_gpr_path = args.work_dir / f"low12_{codec_tag}_gpr" / f"{image_id}.gpr"
            if not low_dec_path.exists() or low_dec_path.stat().st_size != lo_w * lo_h * 2:
                profile = mission1_codec_profile(args.codec)
                run_codec(
                    args.coeff_tool,
                    low_clean_path,
                    low_dec_path,
                    codec_gpr_path,
                    quality=int((profile or {}).get("quality", 0 if args.codec == "q0_l1" else 8)),
                    levels=int((profile or {}).get("levels", 1)),
                    codec=args.codec,
                    width=lo_w,
                    height=lo_h,
                )
            low_source_path = low_dec_path

        low_planes = deinterleave(read_u16_raw(low_source_path, lo_w, lo_h))
        x, y, rows = sample_tiles(
            low_planes,
            high_planes,
            image_id,
            args.tiles_per_image,
            args.low_tile,
            rng,
            prescribed_tiles=manifest_tiles.get(image_id),
            manifest_only=args.manifest_only,
        )
        all_x.append(x)
        all_y.append(y)
        tile_rows.extend(rows)
        image_rows.append(
            {
                "image_id": image_id,
                "high_source": str(raw50),
                "high_target_raw": str(high_target_path) if high_target_path else None,
                "input_kind": args.input_kind,
                "high_width": args.high_width,
                "high_height": args.high_height,
                "low_width": lo_w,
                "low_height": lo_h,
                "low_clean_raw": str(low_clean_path),
                "low_source_raw": str(low_source_path),
                "codec_gpr": str(codec_gpr_path) if codec_gpr_path else None,
                "downsample": args.downsample,
                "downsample_implementation": downsample_impl,
                "downsample_implementation_sha256": downsample_impl_sha256,
                "downsample_policy": downsample_policy,
                "production_downsample": production_downsample,
                "cfa_preserving": True,
                "codec_profile_id": (codec_profile or {}).get("profile_id"),
                "codec_env_contract": codec_env_contract,
                "coeff_tool_sha256": coeff_tool_sha256,
            }
        )

    inputs = np.concatenate(all_x, axis=0)
    targets = np.concatenate(all_y, axis=0)
    meta = {
        "schema": "mission1_sr_pairs.v1",
        "source": "synthetic 2x Bayer SR pairs from full-resolution Bayer sources",
        "capture_note": "Mission 1 native 12MP capture does not downsample; these pairs are for optional 12MP-to-full-res upscaling.",
        "input_kind": args.input_kind,
        "width50": args.high_width,
        "height50": args.high_height,
        "width12": lo_w,
        "height12": lo_h,
        "downsample": args.downsample,
        "downsample_implementation": downsample_impl,
        "downsample_implementation_sha256": downsample_impl_sha256,
        "downsample_policy": downsample_policy,
        "production_downsample": production_downsample,
        "allow_diagnostic_downsample": bool(args.allow_diagnostic_downsample),
        "cfa_preserving": True,
        "codec": args.codec,
        "codec_profile_id": (codec_profile or {}).get("profile_id"),
        "codec_profile": codec_profile,
        "codec_env_contract": codec_env_contract,
        "coeff_tool": str(args.coeff_tool),
        "coeff_tool_sha256": coeff_tool_sha256,
        "low_tile": args.low_tile,
        "high_tile": args.low_tile * 2,
        "tiles_per_image": args.tiles_per_image,
        "tile_manifest": str(args.tile_manifest) if args.tile_manifest else None,
        "manifest_only": bool(args.manifest_only),
        "manifest_repeat": int(args.manifest_repeat),
        "seed": args.seed,
        "images": image_rows,
        "tiles": tile_rows,
    }
    np.savez_compressed(args.out, inputs=inputs, targets=targets, meta=json.dumps(meta))
    (args.out.with_suffix(args.out.suffix + ".json")).write_text(json.dumps(meta, indent=2))
    print(f"wrote {args.out} inputs={inputs.shape} targets={targets.shape}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
