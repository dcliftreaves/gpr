#!/usr/bin/env python3
"""Regression test for the premium still-SR gate receipt skeleton."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_premium_still_sr_gate_receipt.py"
CHECKER = ROOT / "tools/check_product_pillar_receipts.py"


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
    with tempfile.TemporaryDirectory(prefix="gpr_still_sr_gate_", dir=temp_root()) as tmp:
        out_dir = Path(tmp) / "still_sr"
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(out_dir),
                "--camera-count",
                "2",
                "--fifty-mp-or-larger-count",
                "1",
                "--hundred-mp-or-larger-count",
                "1",
                "--cfa-phase",
                "RGGB",
                "--cfa-phase",
                "GBRG",
            ],
            check=True,
        )
        receipt = out_dir / "premium_still_sr_gate_receipt.json"
        subprocess.run([sys.executable, str(CHECKER), str(receipt)], check=True)

        payload = json.loads(receipt.read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.premium_still_sr_gate.v1"
        assert payload["production_ready"] is False
        assert payload["fixture_summary"]["hundred_mp_or_larger_count"] == 1
        assert payload["runtime_policy"]["runtime_inputs"] == ["candidate_raw", "camera_metadata"]
        assert payload["runtime_policy"]["no_ref_runtime"] is False
        assert payload["promotion_metrics"]["full_frame_gate_50mp_row_count"] == 0
        assert payload["performance"]["render_seconds_per_100mp_frame"] == 0.0
        assert payload["noise_policy"]["exact_sidecars_only"] is False
        assert payload["candidate"]["checkpoint_sha256"]
        for ref in payload["outputs"].values():
            assert Path(ref["path"]).exists()
            assert len(ref["sha256"]) == 64

        bad = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(Path(tmp) / "bad"),
                "--production-ready",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert bad.returncode == 2, bad

    print("test_build_premium_still_sr_gate_receipt: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
