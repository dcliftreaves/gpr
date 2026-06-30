#!/usr/bin/env python3
"""Regression test for premium still-SR rendered review builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_rendered_review.py"
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


def write_checkpoint(torch, checkpoint: Path) -> None:
    sys.path.insert(0, str(CNN_DIR))
    from train_mission1_sr import make_model

    config = {"architecture": "lowres_pixelshuffle", "width": 4, "depth": 2, "residual_scale": 0.1}
    model = make_model(**config)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": model.state_dict(), "config": config}, checkpoint)


def write_raw_pair(np, low_raw: Path, target_raw: Path) -> None:
    # 8x8 low raw, 16x16 high raw. Values stay in the 14-bit training scale.
    target = (np.arange(16 * 16, dtype=np.uint16).reshape(16, 16) * 8 + 256).astype("<u2")
    low_planes = []
    for yy, xx in ((0, 0), (0, 1), (1, 0), (1, 1)):
        plane = target[yy::2, xx::2].reshape(8, 8)
        low_planes.append(((plane[0::2, 0::2].astype(np.uint32) + plane[0::2, 1::2] + plane[1::2, 0::2] + plane[1::2, 1::2] + 2) // 4).astype(np.uint16))
    low = np.empty((8, 8), dtype="<u2")
    low[0::2, 0::2] = low_planes[0]
    low[0::2, 1::2] = low_planes[1]
    low[1::2, 0::2] = low_planes[2]
    low[1::2, 1::2] = low_planes[3]
    low_raw.parent.mkdir(parents=True, exist_ok=True)
    target_raw.parent.mkdir(parents=True, exist_ok=True)
    low.tofile(low_raw)
    target.tofile(target_raw)


def main() -> int:
    try:
        import numpy as np
        import cv2  # noqa: F401
        import torch
        import PIL  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_rendered_review: SKIP missing {exc.name}")
        return 0

    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_rendered_", dir=temp_root()) as td:
        root = Path(td)
        checkpoint = root / "checkpoint.pt"
        low_raw = root / "low.raw"
        target_raw = root / "target.raw"
        compare = root / "frame/frame_fullframe_compare.json"
        summary = root / "eval/summary.json"
        out = root / "out"
        write_checkpoint(torch, checkpoint)
        write_raw_pair(np, low_raw, target_raw)
        compare.parent.mkdir(parents=True)
        compare.write_text(
            json.dumps(
                {
                    "low_raw": str(low_raw),
                    "target_raw": str(target_raw),
                    "low_width": 8,
                    "low_height": 8,
                    "high_width": 16,
                    "high_height": 16,
                }
            ),
            encoding="utf-8",
        )
        summary.parent.mkdir(parents=True)
        summary.write_text(
            json.dumps({"checkpoint": str(checkpoint), "images": [{"image": "frame", "compare_json": str(compare)}]}),
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--summary",
                str(summary),
                "--output-dir",
                str(out),
                "--crop-size",
                "4",
                "--tile",
                "4",
                "--overlap",
                "0",
                "--device",
                "cpu",
                "--contact-rows",
                "3",
            ],
            check=True,
        )
        payload = json.loads((out / "rendered_review.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.premium_still_sr_rendered_review.v1"
        assert payload["summary"]["row_count"] == 9
        assert (out / "index.html").is_file()
        assert Path(payload["contact_sheet"]).is_file()

    print("test_build_premium_still_sr_rendered_review: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
