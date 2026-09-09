#!/usr/bin/env python3
"""Regression test for the premium still-SR candidate dashboard builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_candidate_dashboard.py"


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
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_dashboard_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        out = Path(tmp) / "out"
        ckpt = root / "artifacts/candidate/model.pt"
        pairs = root / "artifacts/pairs/pairs.npz"
        receipt = root / "artifacts/candidate/model.pt.json"
        ckpt.parent.mkdir(parents=True, exist_ok=True)
        pairs.parent.mkdir(parents=True, exist_ok=True)
        ckpt.write_bytes(b"checkpoint")
        pairs.write_bytes(b"pairs")
        payload = {
            "schema": "mission1_sr_train_receipt.v1",
            "pairs": str(pairs),
            "checkpoint": str(ckpt),
            "architecture": "lowres_pixelshuffle",
            "width": 8,
            "depth": 3,
            "steps": 20,
            "holdout_image": "x2d_100mp_dng",
            "train_tiles": 12,
            "eval_tiles_total": 4,
            "device": "cpu",
            "elapsed_s": 1.0,
            "best_eval": {
                "step": 10,
                "baseline_rmse_counts": 100.0,
                "model_rmse_counts": 90.0,
                "rmse_improvement_pct": 10.0,
                "mae_improvement_pct": 5.0,
            },
            "history": [
                {"step": 1, "model_rmse_counts": 105.0},
                {"step": 20, "model_rmse_counts": 95.0},
            ],
        }
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(root),
                "--output-dir",
                str(out),
                "--receipt",
                str(receipt),
            ],
            cwd=ROOT,
            check=True,
        )
        data = json.loads((out / "candidate_dashboard.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_candidate_dashboard.v1"
        assert data["production_ready"] is False
        assert len(data["rows"]) == 1
        assert data["rows"][0]["best_step"] == 10
        assert data["rows"][0]["final_regressed_from_best_rmse_counts"] == 5.0
        assert "Premium Still-SR Candidate Dashboard" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_candidate_dashboard: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
