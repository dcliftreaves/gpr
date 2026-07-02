#!/usr/bin/env python3
"""Regression test for the Gate 14 Premium still-SR selector smoke."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTAKE_TOOL = ROOT / "tools/build_premium_still_sr_gate14_candidate_intake.py"
SMOKE_TOOL = ROOT / "tools/build_premium_still_sr_gate14_selector_smoke.py"
sys.path.insert(0, str(ROOT / "tools/test"))
from test_build_premium_still_sr_gate14_candidate_intake import source_receipt, write_json, write_npz  # noqa: E402


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def source_receipt_with_real_checkpoint_sha(pairs: Path, checkpoint: Path, values: list[float]) -> dict:
    receipt = source_receipt(pairs, checkpoint, values)
    receipt["checkpoint_sha256"] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    return receipt


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate14_selector_smoke_", dir=temp_root()) as td:
        base = Path(td)
        pairs = base / "pairs.npz"
        write_npz(pairs)
        source_a = base / "source_a" / "train_receipt.json"
        source_b = base / "source_b" / "train_receipt.json"
        write_json(source_a, source_receipt_with_real_checkpoint_sha(pairs, base / "source_a" / "model.pt", [1.0, -1.0, 0.0, -1.0]))
        write_json(source_b, source_receipt_with_real_checkpoint_sha(pairs, base / "source_b" / "model.pt", [0.0, -1.0, 1.2, -1.0]))
        write_json(
            base / "gate13.json",
            {
                "source_or_objective_revision_passed": True,
                "inputs": {
                    "anchor_source_receipt": {"path": str(source_a)},
                    "gate12_acceptance": {"path": str(base / "gate12.json")},
                },
            },
        )
        write_json(
            base / "gate12.json",
            {
                "rows": [
                    {
                        "holdout": "z8",
                        "passed": True,
                        "exact_noop": True,
                        "median_mae_improvement_pct": 0.0,
                        "worst_row_mae_improvement_pct": 0.0,
                    }
                ]
            },
        )
        intake_out = base / "intake"
        intake_proc = subprocess.run(
            [
                sys.executable,
                str(INTAKE_TOOL),
                "--gate13-revision",
                str(base / "gate13.json"),
                "--artifact-root",
                str(base),
                "--receipt-glob",
                "source_*/train_receipt.json",
                "--output-dir",
                str(intake_out),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if intake_proc.returncode:
            print(intake_proc.stdout)
            print(intake_proc.stderr, file=sys.stderr)
            return intake_proc.returncode

        smoke_out = base / "smoke"
        smoke_proc = subprocess.run(
            [
                sys.executable,
                str(SMOKE_TOOL),
                "--intake",
                str(intake_out / "candidate_preflight.json"),
                "--output-dir",
                str(smoke_out),
                "--require-pass",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if smoke_proc.returncode:
            print(smoke_proc.stdout)
            print(smoke_proc.stderr, file=sys.stderr)
            return smoke_proc.returncode
        receipt = json.loads((smoke_out / "selector_smoke.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_gate14_selector_smoke.v1"
        assert receipt["gate14_selector_smoke_passed"] is True
        assert receipt["promotion_gate_allowed"] is True
        assert receipt["selector_replay_matches_intake"] is True
        assert receipt["source_model_failures"] == []
        assert "Gate 14 Selector Smoke" in (smoke_out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_gate14_selector_smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
