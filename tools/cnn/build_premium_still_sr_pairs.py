#!/usr/bin/env python3
"""Build premium still-SR Bayer tile pairs from the fixture manifest.

The output NPZ uses the same `inputs`, `targets`, and JSON `meta` layout as
the Mission 1 SR trainer. Inputs are same-color 2x downsampled Bayer planes;
targets are the original high-resolution Bayer planes. Mixed camera bit depth
is normalized to the existing 14-bit CNN training scale while retaining source
black/white levels in metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import random
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_pairs.v1"
RAW_SCALE = 16383.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def default_gpr_tools(repo: Path) -> Path:
    for rel in ("build-local/source/app/gpr_tools/gpr_tools", "build/source/app/gpr_tools/gpr_tools"):
        path = repo / rel
        if path.is_file() and path.stat().st_mode & 0o111:
            return path
    return repo / "build-local/source/app/gpr_tools/gpr_tools"


def json_from_gpr_tools_dump(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise ValueError("gpr_tools dump did not contain a JSON object")
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    def number(name: str, default: float | None = None) -> float:
        match = re.search(rf'"{re.escape(name)}"\s*:\s*(-?[0-9]+(?:\.[0-9]+)?)', text)
        if not match:
            if default is None:
                raise ValueError(f"gpr_tools dump missing {name}")
            return default
        return float(match.group(1))

    return {
        "input_width": int(number("input_width")),
        "input_height": int(number("input_height")),
        "tuning_info": {
            "static_black_level": {
                "r_black": number("r_black", 0.0),
                "g_r_black": number("g_r_black", 0.0),
                "g_b_black": number("g_b_black", 0.0),
                "b_black": number("b_black", 0.0),
            },
            "dgain_saturation_level": {
                "level_red": number("level_red", 16383.0),
                "level_green_even": number("level_green_even", 16383.0),
                "level_green_odd": number("level_green_odd", 16383.0),
                "level_blue": number("level_blue", 16383.0),
            },
        },
        "parse_mode": "field_regex_fallback",
    }


def run_gpr_tools_dump(gpr_tools: Path, source: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(gpr_tools), "-i", str(source), "-d", "1"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return json_from_gpr_tools_dump(proc.stdout)


def extract_raw(gpr_tools: Path, source: Path, out_raw: Path) -> None:
    out_raw.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(gpr_tools), "-i", str(source), "-o", str(out_raw)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def mean_level(obj: dict[str, Any], names: list[str], default: float) -> float:
    values = [float(obj[name]) for name in names if name in obj and isinstance(obj[name], (int, float))]
    return float(sum(values) / len(values)) if values else default


def levels_from_dump(dump: dict[str, Any]) -> tuple[float, float]:
    tuning = dump.get("tuning_info") if isinstance(dump.get("tuning_info"), dict) else {}
    black = tuning.get("static_black_level") if isinstance(tuning.get("static_black_level"), dict) else {}
    sat = tuning.get("dgain_saturation_level") if isinstance(tuning.get("dgain_saturation_level"), dict) else {}
    black_mean = mean_level(black, ["r_black", "g_r_black", "g_b_black", "b_black"], 0.0)
    white_mean = mean_level(sat, ["level_red", "level_green_even", "level_green_odd", "level_blue"], 16383.0)
    if white_mean <= black_mean:
        white_mean = black_mean + 16383.0
    return black_mean, white_mean


def read_raw(path: Path, width: int, height: int) -> np.ndarray:
    arr = np.fromfile(path, dtype="<u2")
    expected = width * height
    if arr.size != expected:
        raise ValueError(f"{path} has {arr.size} pixels, expected {expected} for {width}x{height}")
    return arr.reshape((height, width))


def normalize_to_14bit(raw: np.ndarray, black: float, white: float) -> np.ndarray:
    scaled = (raw.astype(np.float32) - float(black)) * (RAW_SCALE / max(1.0, float(white) - float(black)))
    return np.clip(scaled + 0.5, 0, int(RAW_SCALE)).astype(np.uint16)


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


def downsample_planes_2x(planes: np.ndarray) -> np.ndarray:
    a = planes[:, 0::2, 0::2].astype(np.uint32)
    b = planes[:, 0::2, 1::2].astype(np.uint32)
    c = planes[:, 1::2, 0::2].astype(np.uint32)
    d = planes[:, 1::2, 1::2].astype(np.uint32)
    return ((a + b + c + d + 2) // 4).astype(np.uint16)


def fixture_raw(
    *,
    repo: Path,
    gpr_tools: Path,
    work_dir: Path,
    fixture: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    source = Path(str(fixture["source"]["path"]))
    ext = str(fixture.get("extension") or source.suffix.lstrip(".")).lower()
    if ext == "raw":
        width = int(fixture["source"].get("width") or fixture.get("width"))
        height = int(fixture["source"].get("height") or fixture.get("height"))
        black = float(fixture.get("black_level", 0.0))
        white = float(fixture.get("white_level", 16383.0))
        raw_path = source
        dump: dict[str, Any] = {"input_width": width, "input_height": height, "source_kind": "raw_fixture"}
    elif ext in {"dng", "gpr"}:
        dump = run_gpr_tools_dump(gpr_tools, source)
        width = int(dump["input_width"])
        height = int(dump["input_height"])
        black, white = levels_from_dump(dump)
        raw_path = work_dir / "raw_extract" / f"{fixture['label']}.raw"
        extract_raw(gpr_tools, source, raw_path)
    else:
        raise ValueError(f"unsupported fixture extension for {fixture['label']}: {ext}")
    raw = read_raw(raw_path, width, height)
    return normalize_to_14bit(raw, black, white), {
        "raw_extract": str(raw_path),
        "source_width": width,
        "source_height": height,
        "normalization_black_level": black,
        "normalization_white_level": white,
        "gpr_tools_dump": dump,
        "gpr_tools": str(gpr_tools if ext in {"dng", "gpr"} else ""),
    }


def sample_fixture_tiles(
    *,
    fixture: dict[str, Any],
    raw14: np.ndarray,
    low_plane_tile: int,
    tiles_per_fixture: int,
    rng: random.Random,
) -> tuple[list[np.ndarray], list[np.ndarray], list[dict[str, Any]]]:
    high_raw_tile = low_plane_tile * 4
    height, width = raw14.shape
    if width < high_raw_tile or height < high_raw_tile:
        raise ValueError(f"{fixture['label']} is too small for high_raw_tile={high_raw_tile}: {width}x{height}")
    max_x_units = (width - high_raw_tile) // 4
    max_y_units = (height - high_raw_tile) // 4
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    rows: list[dict[str, Any]] = []
    for idx in range(tiles_per_fixture):
        x = rng.randrange(0, max_x_units + 1) * 4
        y = rng.randrange(0, max_y_units + 1) * 4
        high_tile = raw14[y : y + high_raw_tile, x : x + high_raw_tile]
        target = deinterleave(high_tile)
        low = downsample_planes_2x(target)
        xs.append(low)
        ys.append(target)
        rows.append(
            {
                "image_id": fixture["label"],
                "low_x": x // 4,
                "low_y": y // 4,
                "low_tile": low_plane_tile,
                "high_x": x,
                "high_y": y,
                "high_raw_tile": high_raw_tile,
                "sample_source": "random_same_color_2x_downsample",
            }
        )
    return xs, ys, rows


def eligible_fixtures(manifest: dict[str, Any], include_gpr: bool) -> list[dict[str, Any]]:
    fixtures = []
    for item in manifest.get("fixtures", []):
        if not isinstance(item, dict) or item.get("premium_still_sr_eligible") is not True:
            continue
        if item.get("source", {}).get("exists") is not True:
            continue
        ext = str(item.get("extension", "")).lower()
        if ext == "gpr" and not include_gpr:
            continue
        if ext in {"dng", "gpr", "raw"}:
            fixtures.append(item)
    if not fixtures:
        raise ValueError("manifest contains no usable premium still-SR fixtures")
    return fixtures


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture-manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--gpr-tools", type=Path, default=default_gpr_tools(repo))
    ap.add_argument("--tiles-per-fixture", type=int, default=16)
    ap.add_argument("--low-plane-tile", type=int, default=96)
    ap.add_argument("--include-gpr", action="store_true", help="include source .gpr fixtures in addition to DNG/raw fixtures")
    ap.add_argument("--dataset-label", default="premium_still_sr_pairs")
    ap.add_argument("--seed", type=int, default=20260629)
    args = ap.parse_args()

    manifest = json.loads(args.fixture_manifest.read_text(encoding="utf-8"))
    fixtures = eligible_fixtures(manifest, args.include_gpr)
    rng = random.Random(args.seed)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    inputs: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    tiles: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []

    for fixture in fixtures:
        raw14, info = fixture_raw(repo=repo, gpr_tools=args.gpr_tools, work_dir=args.work_dir, fixture=fixture)
        x, y, rows = sample_fixture_tiles(
            fixture=fixture,
            raw14=raw14,
            low_plane_tile=args.low_plane_tile,
            tiles_per_fixture=args.tiles_per_fixture,
            rng=rng,
        )
        inputs.extend(x)
        targets.extend(y)
        tiles.extend(rows)
        images.append(
            {
                "image_id": fixture["label"],
                "camera": fixture.get("camera"),
                "camera_key": fixture.get("camera_key"),
                "class": fixture.get("class"),
                "source": fixture.get("source"),
                "source_sha256": fixture.get("source", {}).get("sha256") or sha256_file(Path(str(fixture["source"]["path"]))),
                "noise_sidecars": fixture.get("noise_sidecars", []),
                "low_width": info["source_width"] // 2,
                "low_height": info["source_height"] // 2,
                "high_width": info["source_width"],
                "high_height": info["source_height"],
                **info,
            }
        )

    input_arr = np.stack(inputs).astype(np.uint16)
    target_arr = np.stack(targets).astype(np.uint16)
    max_low_width = max(int(row["low_width"]) for row in images)
    max_low_height = max(int(row["low_height"]) for row in images)
    meta = {
        "schema": SCHEMA,
        "dataset_label": args.dataset_label,
        "fixture_manifest": str(args.fixture_manifest),
        "fixture_manifest_sha256": sha256_file(args.fixture_manifest),
        "created_from": "real premium still-SR fixture manifest",
        "normalization": "source black/saturation mapped to 0..16383 per fixture",
        "downsample": "same-color 2x2 average within each Bayer plane",
        "low_tile": args.low_plane_tile,
        "high_tile": args.low_plane_tile * 2,
        "width12": max_low_width,
        "height12": max_low_height,
        "tiles_per_fixture": args.tiles_per_fixture,
        "seed": args.seed,
        "include_gpr": bool(args.include_gpr),
        "images": images,
        "tiles": tiles,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.out, inputs=input_arr, targets=target_arr, meta=json.dumps(meta, sort_keys=True))
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "inputs": list(input_arr.shape), "targets": list(target_arr.shape)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
