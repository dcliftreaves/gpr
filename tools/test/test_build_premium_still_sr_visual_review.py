#!/usr/bin/env python3
"""Regression test for the premium still-SR visual review builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_visual_review.py"
CNN_DIR = ROOT / "tools/cnn"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_fixture(np, torch, pairs: Path, checkpoint: Path, receipt: Path) -> None:
    sys.path.insert(0, str(CNN_DIR))
    from train_mission1_sr import make_model

    inputs = []
    targets = []
    tiles = []
    for idx in range(6):
        target = (np.arange(4 * 16 * 16, dtype=np.float32).reshape(4, 16, 16) + idx * 37.0) % 1024.0
        low = (
            target[:, 0::2, 0::2]
            + target[:, 0::2, 1::2]
            + target[:, 1::2, 0::2]
            + target[:, 1::2, 1::2]
        ) * 0.25
        inputs.append(np.clip(low * 16.0, 0, 16383).astype(np.uint16))
        targets.append(np.clip(target * 16.0, 0, 16383).astype(np.uint16))
        tiles.append({"image_id": "holdout" if idx < 4 else "train", "low_x": idx, "low_y": idx, "sample_source": "synthetic"})
    meta = {
        "schema": "gpr.premium_still_sr_pairs.v1",
        "low_tile": 8,
        "width12": 32,
        "height12": 32,
        "tiles": tiles,
        "images": [
            {"image_id": "holdout", "camera": "Synthetic", "cfa_phase": "RGGB"},
            {"image_id": "train", "camera": "Synthetic", "cfa_phase": "RGGB"},
        ],
    }
    np.savez_compressed(pairs, inputs=np.stack(inputs), targets=np.stack(targets), meta=json.dumps(meta))

    config = {"architecture": "lowres_pixelshuffle", "width": 4, "depth": 2, "residual_scale": 0.1}
    model = make_model(**config)
    torch.save({"model": model.state_dict(), "config": config}, checkpoint)
    receipt.write_text(
        json.dumps(
            {
                "schema": "mission1_sr_train_receipt.v1",
                "pairs": pairs.as_posix(),
                "checkpoint": checkpoint.as_posix(),
                "holdout_image": "holdout",
                **config,
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    try:
        import numpy as np
        import torch
        import PIL  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_visual_review: SKIP missing {exc.name}")
        return 0

    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_visual_", dir=temp_root()) as tmp:
        tmp_path = Path(tmp)
        pairs = tmp_path / "pairs.npz"
        checkpoint = tmp_path / "checkpoint.pt"
        receipt = tmp_path / "checkpoint.pt.json"
        out_dir = tmp_path / "out"
        write_fixture(np, torch, pairs, checkpoint, receipt)
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--receipt",
                str(receipt),
                "--output-dir",
                str(out_dir),
                "--max-tiles",
                "4",
                "--review-rows",
                "2",
            ],
            check=True,
        )
        summary_path = out_dir / "visual_review.json"
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_visual_review.v1"
        assert data["evaluated_tiles"] == 4
        assert len(data["review_rows"]) == 2
        assert (out_dir / "index.html").is_file()
        for row in data["review_rows"]:
            assert (out_dir / row["contact_sheet"]).is_file()

    print("test_build_premium_still_sr_visual_review: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
