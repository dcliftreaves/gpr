#!/usr/bin/env python3
"""Regression test for premium still-SR noise-clean target sweep."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_noise_clean_sweep.py"


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_noise_clean_sweep: SKIP missing {exc.name}")
        return 0

    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_noise_clean_sweep_", dir=tmp_parent) as td:
        root = Path(td)
        sidecar = root / "noise.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.camera_noise_calibration.v1",
                    "camera": {"black_level": 0.0, "white_level": 1000.0},
                    "calibrations": [
                        {
                            "usable_for_training_targets": True,
                            "iso": 1600,
                            "sample_count": 4,
                            "per_plane": {
                                "r": {"sigma_black": 1.0},
                                "g1": {"sigma_black": 1.0},
                                "g2": {"sigma_black": 1.0},
                                "b": {"sigma_black": 1.0},
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        residual = np.full((2, 8, 8, 3), 0.00075, dtype=np.float16)
        source_hf = residual.copy()
        source_hf[1] = 0.1
        residual[1] = 0.00075
        rows = [
            {"scene_id": "synthetic", "crop": "low_texture", "ev": 0.0},
            {"scene_id": "synthetic", "crop": "high_texture", "ev": 0.0},
        ]
        npz = root / "targets.npz"
        np.savez_compressed(
            npz,
            inputs=np.zeros((2, 8, 8, 3), dtype=np.float16),
            hf_residuals=residual,
            source_hf_targets=source_hf,
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        receipt = root / "hf_residual_targets.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_hf_residual_targets.v1",
                    "arrays": {"npz": str(npz)},
                    "noise_sidecars": [{"path": str(sidecar)}],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        out = root / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--target-receipt",
                str(receipt),
                "--output-dir",
                str(out),
                "--render-gain",
                "1",
                "--render-gain",
                "4",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        payload = json.loads((out / "noise_clean_sweep.json").read_text(encoding="utf-8"))
        html = (out / "index.html").read_text(encoding="utf-8")
        assert payload["schema"] == "gpr.premium_still_sr_noise_clean_sweep.v1"
        assert len(payload["gains"]) == 2
        assert payload["gains"][0]["render_gain"] == 1.0
        assert payload["gains"][1]["render_gain"] == 4.0
        assert payload["gains"][0]["changed_fraction"]["median"] > 0.0
        assert payload["gains"][1]["changed_fraction"]["median"] >= payload["gains"][0]["changed_fraction"]["median"]
        assert "Premium Still-SR Noise-Clean Sweep" in html
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_audit_premium_still_sr_noise_clean_sweep: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
