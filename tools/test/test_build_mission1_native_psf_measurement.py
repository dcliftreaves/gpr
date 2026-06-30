#!/usr/bin/env python3
"""Regression test for native Mission 1 PSF measurement builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_native_psf_measurement.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_pair(np, high_path: Path, low_path: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:64, 0:64]
    high = (700 + yy * 9 + xx * 5 + 80 * np.sin(xx / 5.0) + 60 * np.cos(yy / 7.0)).astype(np.float32)
    high[:, 32:] += 500
    high += rng.normal(0, 8, high.shape).astype(np.float32)
    high = np.clip(high, 0, 16383).astype(np.uint16)
    low = np.zeros((32, 32), dtype=np.uint16)
    for y in range(32):
        for x in range(32):
            py = y % 2
            px = x % 2
            hp = high[py::2, px::2]
            low[y, x] = int(round(float(hp[2 * (y // 2) : 2 * (y // 2) + 2, 2 * (x // 2) : 2 * (x // 2) + 2].mean())))
    high_path.write_bytes(high.tobytes())
    low_path.write_bytes(low.tobytes())


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError:
        print("test_build_mission1_native_psf_measurement: SKIP missing numpy")
        return 0

    with tempfile.TemporaryDirectory(prefix="gpr_native_psf_measure_", dir=temp_root()) as td:
        root = Path(td)
        selected = []
        for idx in range(3):
            high = root / f"high_{idx}.raw"
            low = root / f"low_{idx}.raw"
            write_pair(np, high, low, idx)
            selected.append(
                {
                    "low_stem": f"low_{idx}",
                    "high_stem": f"high_{idx}",
                    "time_delta_s": 0,
                    "low_raw_path": str(low),
                    "high_raw_path": str(high),
                }
            )
        plan = {
            "schema": "gpr.mission1_native_psf_measurement_plan.v1",
            "measurement_plan_ready": True,
            "selected_pairs": selected,
            "acceptance": {
                "minimum_accepted_after_scene_vetting": 3,
                "minimum_sharp_edge_tiles": 1,
                "minimum_texture_field_tiles": 1,
            },
        }
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        out_dir = root / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--measurement-plan",
                str(plan_path),
                "--output-dir",
                str(out_dir),
                "--high-shape",
                "64",
                "64",
                "--low-shape",
                "32",
                "32",
                "--alignment-scale",
                "2",
                "--tile-size",
                "32",
                "--tile-stride",
                "32",
                "--max-samples-per-pair",
                "8000",
                "--min-alignment-corr",
                "0.0",
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
        data = json.loads((out_dir / "native_psf_measurement.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.mission1_native_psf_measurement.v1"
        assert data["measurement_executed"] is True
        assert data["production_ready"] is False
        assert data["summary"]["selected_pair_count"] == 3
        assert data["summary"]["accepted_pair_count"] == 3
        assert data["summary"]["accepted_sharp_edge_tile_count"] >= 1
        assert data["combined_kernel"]["available"] is True
        assert len(data["combined_kernel"]["normalized_weights_mean"]) == 4
        assert (out_dir / "index.html").is_file()
        assert "Mission 1 Native PSF Measurement" in (out_dir / "index.html").read_text(encoding="utf-8")
    print("test_build_mission1_native_psf_measurement: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
