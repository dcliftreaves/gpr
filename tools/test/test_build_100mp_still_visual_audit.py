#!/usr/bin/env python3
"""Regression test for the 100MP still visual audit builder."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_100mp_still_visual_audit.py"


def main() -> int:
    try:
        import numpy  # noqa: F401
        from PIL import Image  # noqa: F401
    except ModuleNotFoundError as exc:
        print(f"test_build_100mp_still_visual_audit: SKIP missing {exc.name}")
        return 0

    with tempfile.TemporaryDirectory(prefix="gpr_100mp_visual_audit_") as td:
        out_dir = Path(td) / "audit"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--synthetic",
                "--output-dir",
                str(out_dir),
                "--crop-size",
                "64",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        data = json.loads((out_dir / "audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.100mp_still_visual_audit.v1"
        assert data["mode"] == "synthetic"
        assert data["production_claim"] is False
        assert data["summary"]["shape"] == [256, 192]
        assert data["summary"]["psnr_db"] > 80.0
        assert len(data["crops"]) == 3
        assert all((out_dir / row["contact_sheet"]).is_file() for row in data["crops"])
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "100MP Still Visual Audit" in html
        assert "Raw PSNR" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_100mp_still_visual_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
