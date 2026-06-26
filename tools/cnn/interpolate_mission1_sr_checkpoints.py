#!/usr/bin/env python3
"""Interpolate two Mission 1 SR checkpoints with provenance sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import torch


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_checkpoint(path: Path) -> dict[str, Any]:
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(ckpt, dict) or not isinstance(ckpt.get("model"), dict):
        raise ValueError(f"{path} is not a Mission 1 SR checkpoint with a model state dict")
    return ckpt


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True, help="base checkpoint, alpha=0")
    ap.add_argument("--target", type=Path, required=True, help="target checkpoint, alpha=1")
    ap.add_argument("--alpha", type=float, required=True, help="target interpolation weight")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--description", required=True)
    args = ap.parse_args()

    if not 0.0 <= args.alpha <= 1.0:
        raise ValueError("--alpha must be in [0, 1]")

    base = load_checkpoint(args.base)
    target = load_checkpoint(args.target)
    if base.get("config") != target.get("config"):
        raise ValueError("checkpoint configs differ")

    base_model = base["model"]
    target_model = target["model"]
    if set(base_model) != set(target_model):
        missing = sorted(set(base_model) ^ set(target_model))
        raise ValueError(f"checkpoint state keys differ: {missing[:8]}")

    mixed = {}
    for key, base_value in base_model.items():
        target_value = target_model[key]
        if getattr(base_value, "shape", None) != getattr(target_value, "shape", None):
            raise ValueError(f"shape mismatch for {key}: {base_value.shape} vs {target_value.shape}")
        if torch.is_floating_point(base_value):
            mixed[key] = base_value * (1.0 - args.alpha) + target_value * args.alpha
        else:
            mixed[key] = base_value.clone()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": mixed,
        "config": base["config"],
    }
    torch.save(payload, args.out)

    sidecar = {
        "schema": "mission1_sr_checkpoint_interpolation.v1",
        "description": args.description,
        "base": str(args.base),
        "base_sha256": sha256(args.base),
        "target": str(args.target),
        "target_sha256": sha256(args.target),
        "alpha": args.alpha,
        "out": str(args.out),
        "out_sha256": sha256(args.out),
        "config": base["config"],
        "parameter_tensors": len(mixed),
    }
    args.out.with_suffix(args.out.suffix + ".json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(sidecar, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
