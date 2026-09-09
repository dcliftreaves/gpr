#!/usr/bin/env python3
"""Regression test for the Mission 1 native PSF pair inventory."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_native_psf_pair_inventory.py"


def stem_row(stem: str, dims: tuple[int, int], dt: str, iso: str = "100") -> dict:
    return {
        "stem": stem,
        "types": ["DNG", "GPR", "JPEG"],
        "files": {
            "GPR": f"/fixtures/{stem}.GPR",
            "DNG": f"/fixtures/{stem}.dng",
            "JPEG": f"/fixtures/{stem}.JPG",
        },
        "dims": {"GPR": list(dims), "DNG": list(dims), "JPEG": list(dims)},
        "model": {"GPR": "MISSION 1", "DNG": "MISSION 1", "JPEG": "MISSION 1"},
        "iso": {"GPR": iso, "DNG": iso, "JPEG": iso},
        "datetime": {"GPR": dt, "DNG": dt, "JPEG": dt},
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_mission1_native_psf_pairs_") as tmp:
        root = Path(tmp)
        media = root / "media_summary.json"
        raw50 = root / "raw50"
        raw12 = root / "raw12"
        raw50.mkdir()
        raw12.mkdir()
        (raw50 / "GP_HIGH.raw").write_bytes(b"h")
        (raw12 / "GP_LOW.raw").write_bytes(b"l")
        media.write_text(
            json.dumps(
                {
                    "stems": [
                        stem_row("GP_HIGH", (8192, 6144), "2026:06:16 08:05:13", "200"),
                        stem_row("GP_LOW", (4096, 3072), "2026:06:16 08:05:30", "220"),
                        stem_row("GP_FAR", (8192, 6144), "2026:06:16 08:20:30", "100"),
                        stem_row("GP_HERO", (5568, 4176), "2026:06:16 08:05:30", "100"),
                    ]
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        out = root / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--media-summary",
                str(media),
                "--raw50-dir",
                str(raw50),
                "--raw12-dir",
                str(raw12),
                "--max-delta-s",
                "30",
                "--output-dir",
                str(out),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        data = json.loads((out / "inventory.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.mission1_native_psf_pair_inventory.v1"
        assert data["summary"]["mission1_high_count"] == 2
        assert data["summary"]["mission1_low_count"] == 1
        assert data["summary"]["candidate_pair_count"] == 1
        assert data["summary"]["decoded_candidate_pair_count"] == 1
        assert data["summary"]["native_psf_ready"] is False
        assert data["candidate_pairs"][0]["low_stem"] == "GP_LOW"
        assert data["candidate_pairs"][0]["high_stem"] == "GP_HIGH"
        assert data["candidate_pairs"][0]["production_candidate"] is True
        html = (out / "index.html").read_text(encoding="utf-8")
        assert "Mission 1 Native PSF Pair Inventory" in html
        assert "GP_LOW" in html
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_build_mission1_native_psf_pair_inventory: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
