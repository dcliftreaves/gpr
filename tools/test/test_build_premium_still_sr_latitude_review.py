#!/usr/bin/env python3
"""Regression test for premium still-SR latitude review helpers."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_latitude_review.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("latitude_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
        from PIL import Image
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_latitude_review: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    ref = np.full((8, 8, 3), 10000, dtype=np.uint16)
    cand = ref.copy()
    cand[:, :, 1] += 100
    metrics = tool.crop_metrics(ref, cand)
    assert metrics["mae"] > 0.0
    assert metrics["psnr_db"] > 40.0
    assert len(metrics["channel_mean_delta"]) == 3
    assert tool.crop_starts(100, 80, 20)[1] == ("center", 40, 30)

    with tempfile.TemporaryDirectory(prefix="gpr_latitude_review_") as td:
        out = Path(td)
        panel = out / "panels/error.jpg"
        panel.parent.mkdir(parents=True)
        Image.new("RGB", (16, 16), (128, 128, 128)).save(panel)
        contact = out / "contact_sheet.jpg"
        Image.new("RGB", (16, 16), (128, 128, 128)).save(contact)
        data = {
            "source_dng": "source.dng",
            "candidate_dng": "candidate.dng",
            "contact_sheet": str(contact),
            "summary": {
                "row_count": 1,
                "mae": {"median": metrics["mae"], "max": metrics["mae"]},
                "y_mae": {"median": metrics["y_mae"], "max": metrics["y_mae"]},
                "lf_y_mae": {"median": metrics["lf_y_mae"] or 0.0, "max": metrics["lf_y_mae"] or 0.0},
                "psnr_db": {"median": metrics["psnr_db"], "min": metrics["psnr_db"]},
            },
            "rows": [
                {
                    "crop": "center",
                    "ev": 0.0,
                    **metrics,
                    "panels": [{"kind": "error", "path": str(panel)}],
                }
            ],
        }
        html = tool.render_html(data, out)
        assert "Premium Still SR Latitude Review" in html
        assert "center" in html

    print("test_build_premium_still_sr_latitude_review: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
