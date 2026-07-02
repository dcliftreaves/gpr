#!/usr/bin/env python3
"""Regression test for premium still-SR smoke-gate acceptance."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_premium_still_sr_smoke_gate_acceptance.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or "/Volumes/OWC_8TB/gpr_work/tmp")
    if not root.exists():
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipt(median: float, worst: float, *, baseline_beaten: bool = True) -> dict:
    return {
        "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
        "checkpoint_sha256": "a" * 64,
        "config": {"model_arch": "frequency_pyramid_pixelshuffle", "steps": 4},
        "eval": {
            "holdout": {
                "mae_improvement_pct": {"count": 2, "median": median, "min": worst},
                "rmse_improvement_pct": {"count": 2, "median": 0.2, "min": 0.1},
            }
        },
        "promotion": {
            "baseline": "nearest_same_color_2x",
            "baseline_beaten_on_holdout": baseline_beaten,
        },
    }


def raw_cfa_receipt(median: float, worst: float) -> dict:
    return {
        "schema": "gpr.premium_still_sr_raw_cfa_residual_model.v1",
        "checkpoint_sha256": "b" * 64,
        "config": {"model_arch": "unet", "steps": 4},
        "eval": {
            "holdout": {
                "row_count": 2,
                "raw_residual_mae_reduction_pct": {"median": median, "min": worst},
                "raw_residual_rmse_reduction_pct": {"median": 0.4, "min": 0.1},
            }
        },
    }


def exact_noop_receipt() -> dict:
    return {
        "schema": "gpr.premium_still_sr_exact_noop_smoke.v1",
        "mode": "exact-noop",
        "checkpoint_sha256": "c" * 64,
        "training_config_sha256": "d" * 64,
        "config": {"mode": "exact-noop", "holdout": "z8"},
        "eval": {
            "holdout": {
                "row_count": 36,
                "mae_improvement_pct": {"count": 36, "median": 0.0, "min": 0.0},
                "rmse_improvement_pct": {"count": 36, "median": 0.0, "min": 0.0},
            }
        },
        "promotion": {
            "baseline": "same-color Bayer interpolation",
            "baseline_beaten_on_holdout": True,
        },
    }


def manifest(root: Path) -> dict:
    return {
        "schema": "gpr.premium_still_sr_candidate_preflight.v1",
        "candidate_id": "frequency_pyramid_source_evidence_teacher_v1",
        "smoke_gate_commands": [
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--output-dir {root / 'artifacts/x2d_smoke'} "
                "--holdout-image x2d --model-arch frequency_pyramid_pixelshuffle"
            ),
            (
                "python3 tools/cnn/train_premium_still_sr_clean_source_pairs.py "
                f"--output-dir {root / 'artifacts/z8_smoke'} "
                "--holdout-image z8 --model-arch frequency_pyramid_pixelshuffle"
            ),
        ],
        "smoke_gate_acceptance": {
            "baseline": "same-color Bayer interpolation",
            "required_holdouts": ["X2D", "Z8"],
            "minimum_median_mae_reduction_pct": 0.001,
            "minimum_worst_row_mae_reduction_pct": 0.0,
            "long_run_blocked_if_smoke_fails": True,
            "receipt_fields_required": [
                "x2d_smoke_receipt",
                "z8_smoke_receipt",
                "baseline_comparison",
                "checkpoint_hash",
                "training_config_hash",
            ],
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_smoke_gate_", dir=temp_root()) as td:
        base = Path(td)
        mpath = base / "candidate_preflight.json"
        write_json(mpath, manifest(base))
        write_json(base / "artifacts/x2d_smoke/train_receipt.json", receipt(0.2, 0.0))
        write_json(base / "artifacts/z8_smoke/train_receipt.json", receipt(0.3, 0.1))
        out = base / "audit.json"
        html = base / "index.html"
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(mpath), "--json-out", str(out), "--html-out", str(html), "--require-pass"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(out.read_text(encoding="utf-8"))
        assert audit["schema"] == "gpr.premium_still_sr_smoke_gate_acceptance.v1"
        assert audit["smoke_gate_passed"] is True
        assert audit["long_run_allowed"] is True
        assert all(row["training_config_sha256"] for row in audit["rows"])
        assert "Premium Still-SR Smoke Gate Acceptance" in html.read_text(encoding="utf-8")

        write_json(base / "artifacts/z8_smoke/train_receipt.json", receipt(-1.0, -3.0, baseline_beaten=False))
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(mpath), "--json-out", str(out), "--require-pass"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.returncode != 0
        audit = json.loads(out.read_text(encoding="utf-8"))
        assert audit["smoke_gate_passed"] is False
        assert audit["verdict"] == "blocked_before_long_run"
        z8 = next(row for row in audit["rows"] if row["holdout"] == "z8")
        assert z8["passed"] is False
        assert any("median MAE" in item for item in z8["failures"])
        assert any("worst-row" in item for item in z8["failures"])

        write_json(base / "artifacts/x2d_smoke/train_receipt.json", raw_cfa_receipt(0.2, 0.0))
        write_json(base / "artifacts/z8_smoke/train_receipt.json", raw_cfa_receipt(-4.0, -5.0))
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(mpath), "--json-out", str(out), "--require-pass"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.returncode != 0
        audit = json.loads(out.read_text(encoding="utf-8"))
        x2d = next(row for row in audit["rows"] if row["holdout"] == "x2d")
        z8 = next(row for row in audit["rows"] if row["holdout"] == "z8")
        assert x2d["median_mae_improvement_pct"] == 0.2
        assert x2d["baseline"] == "same-color Bayer interpolation raw residual"
        assert x2d["baseline_beaten_on_holdout"] is True
        assert z8["median_mae_improvement_pct"] == -4.0
        assert z8["baseline_beaten_on_holdout"] is False

        m = manifest(base)
        m["smoke_gate_commands"][1] = (
            "python3 tools/build_premium_still_sr_exact_noop_receipt.py "
            f"--output-dir {base / 'artifacts/z8_smoke'} "
            "--holdout z8 --mode exact-noop"
        )
        m["smoke_gate_acceptance"]["route_acceptance"] = {
            "z8": {
                "requires_exact_noop": True,
                "minimum_median_mae_reduction_pct": 0.0,
                "minimum_worst_row_mae_reduction_pct": 0.0,
            }
        }
        write_json(mpath, m)
        write_json(base / "artifacts/x2d_smoke/train_receipt.json", receipt(0.2, 0.0))
        write_json(base / "artifacts/z8_smoke/train_receipt.json", exact_noop_receipt())
        proc = subprocess.run(
            [sys.executable, str(TOOL), str(mpath), "--json-out", str(out), "--require-pass"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.returncode == 0
        audit = json.loads(out.read_text(encoding="utf-8"))
        z8 = next(row for row in audit["rows"] if row["holdout"] == "z8")
        assert z8["passed"] is True
        assert z8["exact_noop"] is True
        assert z8["requires_exact_noop"] is True

    print("test_check_premium_still_sr_smoke_gate_acceptance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
