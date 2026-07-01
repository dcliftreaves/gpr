#!/usr/bin/env python3
"""Regression test for the raw-video PSF gradient/detail blocker audit."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_raw_video_psf_gradient_detail_blocker_audit.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def summary(rows: list[dict]) -> dict:
    return {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "image_count": len(rows),
        "images": rows,
    }


def row(image: str, *, grad: float, detail: float, fine: float, rmse: float) -> dict:
    return {
        "image": image,
        "gradient_mae_improvement_pct": grad,
        "same_cell_detail_mae_improvement_pct": detail,
        "same_cell_fine_detail_mae_improvement_pct": fine,
        "rmse_improvement_pct": rmse,
        "contact_sheet": f"{image}.jpg",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_psf_gradient_detail_audit_", dir=temp_root()) as td:
        root = Path(td)
        baseline = root / "baseline.json"
        candidate = root / "candidate.json"
        out = root / "out"
        write_json(
            baseline,
            summary(
                [
                    row("good", grad=10.0, detail=5.0, fine=4.0, rmse=20.0),
                    row("bad", grad=8.0, detail=6.0, fine=5.0, rmse=30.0),
                ]
            ),
        )
        write_json(
            candidate,
            summary(
                [
                    row("good", grad=11.0, detail=6.0, fine=5.0, rmse=22.0),
                    row("bad", grad=7.0, detail=4.5, fine=3.5, rmse=31.0),
                ]
            ),
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(root),
                "--baseline-summary",
                str(baseline),
                "--candidate-summary",
                str(candidate),
                "--created-utc",
                "2026-07-01T03:30:00Z",
                "--output-dir",
                str(out),
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
        data = json.loads((out / "gradient_detail_blocker_audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.raw_video_psf_gradient_detail_blocker_audit.v1"
        assert data["created_utc"] == "2026-07-01T03:30:00Z"
        assert data["metrics"]["shared_image_count"] == 2
        assert data["metrics"]["gradient_regression_count"] == 1
        assert data["metrics"]["same_cell_detail_regression_count"] == 1
        assert data["metrics"]["combined_gradient_detail_regression_count"] == 1
        assert data["production_status"] == "blocked_by_mission_gradient_detail_regressions"
        assert data["worst_blockers"][0]["image"] == "bad"
        assert "Raw Video PSF Gradient/Detail Blocker Audit" in (out / "index.html").read_text(encoding="utf-8")
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_build_raw_video_psf_gradient_detail_blocker_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
