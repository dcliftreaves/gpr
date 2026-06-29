#!/usr/bin/env python3
"""Regression test for the premium still-SR fixture manifest builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_fixture_manifest.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_fixtures_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        out = Path(tmp) / "out"
        receipt = Path(tmp) / "compat.txt"
        z8 = root / "fixtures/Z8Z_1349.dng"
        x2d = root / "fixtures/2024_April_X2D_1742.dng"
        mission = root / "fixtures/GP017504.dng"
        for path in (z8, x2d, mission):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode("utf-8"))
        sidecar = root / "artifacts/camera_noise_sidecars_20260629/x2d/Hasselblad_X2D_100C_ISO800_noise_calibration.json"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text('{"schema":"gpr.camera_noise_calibration.v1"}\n', encoding="utf-8")
        receipt.write_text(
            "\n".join(
                [
                    f"RUN dng_roundtrip z8_50mp_dng src={z8}",
                    f"RUN dng_roundtrip x2d_100mp_dng src={x2d}",
                    f"RUN dng_roundtrip mission1_50mp_dng src={mission}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--compat-receipt",
                str(receipt),
                "--external-root",
                str(root),
                "--output-dir",
                str(out),
            ],
            cwd=ROOT,
            check=True,
        )
        data = json.loads((out / "fixture_manifest.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_fixture_manifest.v1"
        assert data["summary"]["eligible_fixture_count"] == 3
        assert data["summary"]["hundred_mp_or_larger_count"] == 1
        assert data["summary"]["ready_for_first_training_manifest"] is True
        assert any(f["label"] == "x2d_100mp_dng" and len(f["noise_sidecars"]) == 1 for f in data["fixtures"])
        assert "Premium Still-SR Fixtures" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_fixture_manifest: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
