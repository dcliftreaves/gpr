#!/usr/bin/env python3
"""Build ml2_q3_dec2 codec-input to raw-clean-target training pairs."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests/quality_gates"))
import run_gate  # noqa: E402

from train_raw_clean_ref_cnn import deinterleave


DEFAULT_TARGETS = Path("/Volumes/OWC_8TB/gpr_work/artifacts/raw_clean_ref_targets_noise_only_20260605/raw_clean_ref_targets.json")
DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_signal_pairs_20260605/ml2_q3_dec2_raw_signal_pairs.npz")


def load_registry_codec(name: str) -> dict[str, Any]:
    registry = json.loads((REPO / "pipelines/registry.json").read_text())
    return registry["codecs"][name]


def decoded_crop_for_target(decoded: np.ndarray, crop_xywh: np.ndarray, decimation: int) -> np.ndarray:
    x, y, w, h = [int(v) for v in crop_xywh]
    if any(v % decimation for v in (x, y, w, h)):
        raise RuntimeError(
            f"source crop {(x, y, w, h)} is not divisible by decimation {decimation}"
        )
    xd = x // decimation
    yd = y // decimation
    wd = w // decimation
    hd = h // decimation
    if any(v % 2 for v in (xd, yd, wd, hd)):
        raise RuntimeError(
            f"decoded crop {(xd, yd, wd, hd)} is not 2x2 CFA aligned"
        )
    crop = decoded[yd:yd + hd, xd:xd + wd]
    if crop.shape != (hd, wd):
        raise RuntimeError(f"decoded crop shape {crop.shape} != expected {(hd, wd)}")
    return crop.astype(np.float32)


def build(args: argparse.Namespace) -> dict[str, Any]:
    data = json.loads(args.targets.read_text())
    codec = load_registry_codec(args.codec)
    rows_by_image: dict[str, list[dict[str, Any]]] = {}
    for row in data["rows"]:
        rows_by_image.setdefault(row["image_id"], []).append(row)

    codec_planes: list[np.ndarray] = []
    target_clean_planes: list[np.ndarray] = []
    target_raw_planes: list[np.ndarray] = []
    exact_residual_planes: list[np.ndarray] = []
    sigma_planes: list[np.ndarray] = []
    names: list[str] = []
    crops: list[str] = []
    accepted: list[bool] = []
    iso: list[int] = []
    source_xywh: list[np.ndarray] = []
    encoded_bytes: dict[str, int] = {}
    encoded_ms: dict[str, float] = {}

    scratch = args.work_dir
    scratch.mkdir(parents=True, exist_ok=True)
    for image_id, rows in rows_by_image.items():
        source_path = Path(rows[0]["path"])
        print(f"{image_id}: encode/decode {source_path}", flush=True)
        bayer, w, h = run_gate.read_source_bayer(str(source_path))
        workdir = Path(tempfile.mkdtemp(prefix=f"codec_raw_clean_{image_id}_", dir=str(scratch)))
        try:
            decoded, enc_bytes, enc_ms = run_gate.encode_decode(
                codec,
                bayer,
                w,
                h,
                workdir,
                src_dng=str(source_path),
            )
            encoded_bytes[image_id] = int(enc_bytes)
            encoded_ms[image_id] = float(enc_ms)
            print(f"  decoded {decoded.shape[1]}x{decoded.shape[0]} bytes={enc_bytes} enc_ms={enc_ms:.2f}", flush=True)
            for row in rows:
                z = np.load(row["npz"])
                crop_xywh = z["crop_xywh"].astype(np.int32)
                codec_crop = decoded_crop_for_target(decoded, crop_xywh, args.decimation)
                codec_planes.append(deinterleave(codec_crop))
                target_clean_planes.append(deinterleave(z["clean"].astype(np.float32)))
                target_raw_planes.append(deinterleave(z["raw"].astype(np.float32)))
                exact_residual_planes.append(deinterleave(z["exact_residual"].astype(np.float32)))
                sigma_planes.append(deinterleave(z["sigma"].astype(np.float32)))
                names.append(row["image_id"])
                crops.append(row["crop"])
                accepted.append(bool(row.get("accepted", True)))
                iso.append(int(row["iso"]))
                source_xywh.append(crop_xywh)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        codec_planes=np.stack(codec_planes).astype(np.float32),
        target_clean_planes=np.stack(target_clean_planes).astype(np.float32),
        target_raw_planes=np.stack(target_raw_planes).astype(np.float32),
        exact_residual_planes=np.stack(exact_residual_planes).astype(np.float32),
        sigma_planes=np.stack(sigma_planes).astype(np.float32),
        image_id=np.asarray(names),
        crop=np.asarray(crops),
        accepted=np.asarray(accepted, dtype=np.bool_),
        iso=np.asarray(iso, dtype=np.int32),
        source_xywh=np.stack(source_xywh).astype(np.int32),
    )
    receipt = {
        "out": str(args.out),
        "targets": str(args.targets),
        "codec": args.codec,
        "decimation": args.decimation,
        "target_semantics": (
            "target_raw_planes are the source Bayer signal/detail target; "
            "target_clean_planes are retained for clean-target experiments; "
            "exact_residual_planes are an evaluation/addback sidecar, not a training objective by default"
        ),
        "count": len(names),
        "codec_shape": list(codec_planes[0].shape),
        "target_shape": list(target_clean_planes[0].shape),
        "encoded_bytes": encoded_bytes,
        "encoded_ms": encoded_ms,
    }
    args.out.with_suffix(args.out.suffix + ".json").write_text(json.dumps(receipt, indent=2))
    return receipt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--codec", default="ml2_q3_dec2")
    ap.add_argument("--decimation", type=int, default=2)
    ap.add_argument("--work-dir", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work/tmp/codec_raw_clean_pairs"))
    args = ap.parse_args()
    receipt = build(args)
    print(args.out)
    print(args.out.with_suffix(args.out.suffix + ".json"))
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
