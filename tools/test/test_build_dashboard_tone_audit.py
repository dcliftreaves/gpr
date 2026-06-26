#!/usr/bin/env python3
"""Smoke-test the RGB dashboard tone/green-bias audit builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image
except ModuleNotFoundError:
    print("test_build_dashboard_tone_audit: SKIP missing Pillow")
    raise SystemExit(0)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_dashboard_tone_audit.py"


def write_rgb(path: Path, rgb: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), rgb).save(path)


def write_triplet(crop_dir: Path, stem_crop: str, target: tuple[int, int, int]) -> None:
    write_rgb(crop_dir / f"{stem_crop}_target_rgb4_from_high.png", target)
    write_rgb(crop_dir / f"{stem_crop}_baseline_rgb4.png", tuple(min(v + 20, 255) for v in target))
    write_rgb(crop_dir / f"{stem_crop}_candidate_rgb4.png", tuple(min(v + 4, 255) for v in target))


def test_build_dashboard_tone_audit() -> None:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dashboard_tone_audit_", dir=work_parent) as td:
        root = Path(td)
        crops = root / "crops"
        out = root / "out"
        write_triplet(crops, "A_center", (48, 52, 56))
        write_triplet(crops, "B_upper_left", (86, 88, 90))

        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--crop-dir",
                str(crops),
                "--output-dir",
                str(out),
                "--limit",
                "2",
            ],
            cwd=ROOT,
            check=True,
        )

        payload = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        summary = payload["summary"]
        assert summary["row_count"] == 2
        assert summary["selected_count"] == 2
        assert summary["candidate_better_display_mae_count"] == 2
        assert summary["candidate_worse_display_mae_count"] == 0
        assert summary["candidate_display_mae"]["median"] < summary["baseline_display_mae"]["median"]
        assert (out / "index.html").exists()
        assert len(list((out / "rows").glob("*_tone_contact.jpg"))) == 2


if __name__ == "__main__":
    test_build_dashboard_tone_audit()
    print("test_build_dashboard_tone_audit: PASS")
