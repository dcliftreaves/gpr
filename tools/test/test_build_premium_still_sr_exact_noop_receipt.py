#!/usr/bin/env python3
"""Regression test for exact-noop Premium still-SR smoke receipts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_exact_noop_receipt.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_exact_noop_", dir=temp_root()) as td:
        out = Path(td) / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--output-dir",
                str(out),
                "--holdout",
                "z8",
                "--mode",
                "exact-noop",
                "--row-count",
                "36",
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
        receipt = json.loads((out / "train_receipt.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_exact_noop_smoke.v1"
        assert receipt["mode"] == "exact-noop"
        assert receipt["holdout"] == "z8"
        assert receipt["eval"]["holdout"]["mae_improvement_pct"]["median"] == 0.0
        assert receipt["eval"]["holdout"]["mae_improvement_pct"]["min"] == 0.0
        assert receipt["promotion"]["baseline_beaten_on_holdout"] is True
        assert receipt["checkpoint_sha256"]
        assert receipt["training_config_sha256"]
        assert "Exact No-op" in (out / "index.html").read_text(encoding="utf-8")
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_build_premium_still_sr_exact_noop_receipt: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
