#!/usr/bin/env python3
"""Regression test for the external CNN dataset inventory builder."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_cnn_dataset_inventory.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_cnn_dataset_inventory_") as td:
        out_dir = Path(td) / "inventory"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--synthetic",
                "--output-dir",
                str(out_dir),
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
        data = json.loads((out_dir / "cnn_dataset_inventory.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.cnn_dataset_inventory.v1"
        assert data["summary"]["dataset_count"] >= 7
        assert data["summary"]["canonical_current_count"] == 3
        assert data["summary"]["canonical_ready_count"] == 3
        rows = {row["id"]: row for row in data["datasets"]}
        current = rows["mission1_z8_4k_cleanup_8k_sr_current"]
        assert current["status"] == "canonical_current"
        assert current["ready_for_current_work"] is True
        assert "raw_video_improvement" in current["pillars"]
        assert current["file_counts"]["npz"] >= 1
        still = rows["premium_still_sr_raw_cfa_residual_targets"]
        assert still["ready_for_current_work"] is True
        assert "source raw is training-target only" in still["do_not_use_for"]
        legacy = rows["mission1_sr_pairs_legacy"]
        assert legacy["status"] == "legacy_reference"
        assert legacy["ready_for_current_work"] is False
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        assert "GPR CNN Dataset Inventory" in html
        assert "Mission/Z8 4K cleanup" in html
        assert proc.stdout.strip() == str(out_dir / "index.html")
    print("test_build_cnn_dataset_inventory: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
