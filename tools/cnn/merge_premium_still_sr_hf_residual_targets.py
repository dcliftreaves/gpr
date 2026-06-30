#!/usr/bin/env python3
"""Merge premium still-SR HF residual target NPZ files."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_hf_residual_targets_merged.v1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {"min": float(arr.min()), "median": float(np.median(arr)), "mean": float(arr.mean()), "max": float(arr.max())}


def load_target(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None, list[dict[str, Any]]]:
    with np.load(path, allow_pickle=False) as z:
        inputs = z["inputs"]
        residuals = z["hf_residuals"]
        source_hf = z["source_hf_targets"]
        raw_cfa = z["candidate_raw_cfa4"] if "candidate_raw_cfa4" in z.files else None
        rows = json.loads(str(z["meta"]))
    return inputs, residuals, source_hf, raw_cfa, rows


def merge(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_inputs: list[np.ndarray] = []
    all_residuals: list[np.ndarray] = []
    all_source_hf: list[np.ndarray] = []
    all_raw_cfa: list[np.ndarray] = []
    raw_cfa_source_count = 0
    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    shape: tuple[int, ...] | None = None
    for path in args.target:
        inputs, residuals, source_hf, raw_cfa, part_rows = load_target(path)
        if shape is None:
            shape = tuple(inputs.shape[1:])
        elif tuple(inputs.shape[1:]) != shape:
            raise ValueError(f"{path} has row shape {inputs.shape[1:]}, expected {shape}")
        if raw_cfa is not None:
            if raw_cfa.shape[:3] != inputs.shape[:3]:
                raise ValueError(f"{path} raw CFA shape {raw_cfa.shape} does not match inputs {inputs.shape}")
            all_raw_cfa.append(raw_cfa)
            raw_cfa_source_count += 1
        all_inputs.append(inputs)
        all_residuals.append(residuals)
        all_source_hf.append(source_hf)
        rows.extend(part_rows)
        sources.append({"path": str(path), "sha256": sha256_file(path), "rows": int(inputs.shape[0])})
    out_npz = args.output_dir / "hf_residual_targets_merged.npz"
    arrays: dict[str, Any] = {
        "inputs": np.concatenate(all_inputs, axis=0).astype(np.float16),
        "hf_residuals": np.concatenate(all_residuals, axis=0).astype(np.float16),
        "source_hf_targets": np.concatenate(all_source_hf, axis=0).astype(np.float16),
        "meta": np.asarray(json.dumps(rows, sort_keys=True)),
    }
    raw_cfa_complete = raw_cfa_source_count == len(args.target)
    if raw_cfa_complete and all_raw_cfa:
        arrays["candidate_raw_cfa4"] = np.concatenate(all_raw_cfa, axis=0).astype(np.float16)
    np.savez_compressed(out_npz, **arrays)
    scenes = sorted({str(row.get("scene_id")) for row in rows})
    receipt = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "output_npz": str(out_npz),
        "output_npz_sha256": sha256_file(out_npz),
        "sources": sources,
        "summary": {
            "row_count": len(rows),
            "scene_count": len(scenes),
            "scenes": scenes,
            "residual_abs_mean": stats([float(row.get("residual_abs_mean", 0.0)) for row in rows]),
            "hf_y_correlation": stats([float(row["hf_y_correlation"]) for row in rows if row.get("hf_y_correlation") is not None]),
            "raw_cfa_feature_sources": raw_cfa_source_count,
            "raw_cfa_feature_complete": raw_cfa_complete,
        },
        "policy": {
            "uses_source_hf": True,
            "runtime_safe": False,
            "purpose": "multi_scene_supervised_hf_residual_training_target",
        },
    }
    receipt_path = args.output_dir / "merge_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    receipt["receipt"] = str(receipt_path)
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", type=Path, action="append", required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    receipt = merge(args)
    print(
        json.dumps(
            {
                "receipt": receipt["receipt"],
                "npz": receipt["output_npz"],
                "rows": receipt["summary"]["row_count"],
                "scenes": receipt["summary"]["scene_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
