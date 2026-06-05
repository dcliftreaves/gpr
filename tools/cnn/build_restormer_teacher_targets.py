#!/usr/bin/env python3
"""Build RGB teacher targets for BIDO distillation from codec-degraded tiles."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_restormer_teacher import codec_tile_to_rgb, load_restormer  # noqa: E402


DEFAULT_NPZ = Path("/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr_gate_hardtail_t192_s96_fullref.npz")
DEFAULT_OUT = Path("/Volumes/OWC_8TB/gpr_work/cnn/teacher_restormer_hardtail_t192_s96_fullref.npy")
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work/external/Restormer")
DEFAULT_WEIGHTS = Path("/Volumes/OWC_8TB/gpr_work/external/restormer_real_denoising.pth")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def starts_for(length: int, tile: int, overlap: int) -> list[int]:
    if tile >= length:
        return [0]
    step = tile - overlap
    if step <= 0:
        raise ValueError("--overlap must be smaller than --tile")
    starts = list(range(0, length - tile + 1, step))
    if starts[-1] != length - tile:
        starts.append(length - tile)
    return starts


def infer_tiled(model: torch.nn.Module, chw: np.ndarray, device: torch.device,
                tile: int, overlap: int) -> np.ndarray:
    _, h, w = chw.shape
    ys = starts_for(h, tile, overlap)
    xs = starts_for(w, tile, overlap)
    acc = np.zeros((3, h, w), dtype=np.float32)
    weight = np.zeros((1, h, w), dtype=np.float32)
    with torch.no_grad():
        for y in ys:
            for x in xs:
                crop = torch.from_numpy(chw[None, :, y:y + tile, x:x + tile]).to(device)
                pred = model(crop).clamp(0, 1).cpu().numpy()[0]
                acc[:, y:y + tile, x:x + tile] += pred
                weight[:, y:y + tile, x:x + tile] += 1.0
    return acc / np.maximum(weight, 1.0)


def parse_indices(value: str | None, n: int) -> list[int]:
    if not value:
        return list(range(n))
    out: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    for i in out:
        if i < 0 or i >= n:
            raise ValueError(f"index {i} is outside 0..{n - 1}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--restormer-root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    ap.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    ap.add_argument("--tile", type=int, default=256)
    ap.add_argument("--overlap", type=int, default=32)
    ap.add_argument("--indices", type=str, default=None,
                    help="comma-separated tile indices; default is all tiles")
    ap.add_argument("--max-tiles", type=int, default=0,
                    help="limit generated tiles after --indices filtering; 0 means no limit")
    ap.add_argument("--fill-missing", choices=("target", "zero"), default="target",
                    help="value for tiles not generated in limited smoke runs")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if args.device == "auto":
        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    if args.out.exists() and not args.overwrite:
        raise SystemExit(f"{args.out} exists; pass --overwrite to replace it")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out.with_suffix(args.out.suffix + ".manifest.json")

    z = np.load(args.npz, allow_pickle=True, mmap_mode="r")
    target = z["tgt_rgb"]
    n, h, w, c = target.shape
    if c != 3:
        raise RuntimeError(f"expected RGB target shape, got {target.shape}")

    selected = parse_indices(args.indices, n)
    if args.max_tiles > 0:
        selected = selected[:args.max_tiles]

    teacher = np.lib.format.open_memmap(args.out, mode="w+", dtype=np.uint8, shape=target.shape)
    if args.fill_missing == "target":
        print(f"prefilling {n} tiles from tgt_rgb for non-generated entries", flush=True)
        for i in range(n):
            teacher[i] = target[i]
            if (i + 1) % 100 == 0:
                teacher.flush()
    else:
        teacher[:] = 0
    teacher.flush()

    model = load_restormer(args.restormer_root, args.weights, device)
    generated = np.zeros(n, dtype=bool)
    t_start = time.perf_counter()
    for pos, idx in enumerate(selected, 1):
        out_hw = tuple(int(v) for v in target[idx].shape[:2])
        degraded = codec_tile_to_rgb(z, idx, out_hw)
        pred = infer_tiled(model, degraded, device, tile=args.tile, overlap=args.overlap)
        arr = np.transpose(np.clip(pred, 0.0, 1.0), (1, 2, 0))
        teacher[idx] = (arr * 255.0 + 0.5).astype(np.uint8)
        generated[idx] = True
        if pos == 1 or pos % 10 == 0 or pos == len(selected):
            elapsed = time.perf_counter() - t_start
            rate = pos / max(elapsed, 1e-9)
            print(f"generated {pos}/{len(selected)} idx={idx} rate={rate:.3f} tiles/s", flush=True)
            teacher.flush()
    teacher.flush()

    generated_mask_path = args.out.with_suffix(args.out.suffix + ".generated_mask.npy")
    np.save(generated_mask_path, generated)
    manifest = {
        "source_npz": str(args.npz),
        "out": str(args.out),
        "generated_mask": str(generated_mask_path),
        "shape": list(target.shape),
        "dtype": "uint8",
        "teacher_target_key": "tgt_rgb_teacher",
        "generated_tiles": int(generated.sum()),
        "total_tiles": int(n),
        "fill_missing": args.fill_missing,
        "indices": selected,
        "tile": args.tile,
        "overlap": args.overlap,
        "device": str(device),
        "restormer_root": str(args.restormer_root),
        "weights": str(args.weights),
        "weights_sha256": sha256_file(args.weights),
        "elapsed_sec": time.perf_counter() - t_start,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(manifest_path)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
