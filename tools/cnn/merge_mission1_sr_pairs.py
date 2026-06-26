#!/usr/bin/env python3
"""Merge compatible Mission 1/Z8 Bayer SR tile-pair NPZ files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def load_pairs(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    z = np.load(path, allow_pickle=False)
    inputs = z["inputs"]
    targets = z["targets"]
    meta = json.loads(str(z["meta"]))
    if inputs.ndim != 4 or targets.ndim != 4:
        raise ValueError(f"{path} does not contain NCHW inputs/targets")
    if inputs.shape[1] != 4 or targets.shape[1] != 4:
        raise ValueError(f"{path} is not 4-channel Bayer-plane data")
    if targets.shape[2] != inputs.shape[2] * 2 or targets.shape[3] != inputs.shape[3] * 2:
        raise ValueError(f"{path} target tile is not 2x input tile")
    return inputs, targets, meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--uncompressed",
        action="store_true",
        help="write an uncompressed NPZ for faster local iteration at the cost of larger artifacts",
    )
    ap.add_argument("pairs", type=Path, nargs="+")
    args = ap.parse_args()

    all_inputs: list[np.ndarray] = []
    all_targets: list[np.ndarray] = []
    all_tiles: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    tile_shape: tuple[int, ...] | None = None
    target_shape: tuple[int, ...] | None = None

    for dataset_index, path in enumerate(args.pairs):
        inputs, targets, meta = load_pairs(path)
        if tile_shape is None:
            tile_shape = tuple(inputs.shape[1:])
            target_shape = tuple(targets.shape[1:])
        elif tuple(inputs.shape[1:]) != tile_shape or tuple(targets.shape[1:]) != target_shape:
            raise ValueError(
                f"{path} shape mismatch: inputs {inputs.shape[1:]} targets {targets.shape[1:]}; "
                f"expected {tile_shape} / {target_shape}"
            )
        all_inputs.append(inputs)
        all_targets.append(targets)
        dataset_tag = f"dataset_{dataset_index}"
        for row in meta.get("tiles", []):
            out_row = dict(row)
            out_row["source_dataset"] = dataset_tag
            all_tiles.append(out_row)
        for row in meta.get("images", []):
            out_row = dict(row)
            out_row["source_dataset"] = dataset_tag
            image_rows.append(out_row)
        source_rows.append(
            {
                "tag": dataset_tag,
                "path": str(path),
                "tile_count": int(inputs.shape[0]),
                "meta": meta,
            }
        )

    merged_inputs = np.concatenate(all_inputs, axis=0)
    merged_targets = np.concatenate(all_targets, axis=0)
    meta = {
        "schema": "mission1_sr_pairs_merged.v1",
        "source": "merged Bayer SR tile-pair datasets",
        "source_datasets": source_rows,
        "low_tile": int(merged_inputs.shape[2]),
        "high_tile": int(merged_targets.shape[2]),
        "tiles": all_tiles,
        "images": image_rows,
        "compressed": not args.uncompressed,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer = np.savez if args.uncompressed else np.savez_compressed
    writer(args.out, inputs=merged_inputs, targets=merged_targets, meta=json.dumps(meta))
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {args.out} inputs={merged_inputs.shape} targets={merged_targets.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
