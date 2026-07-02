#!/usr/bin/env python3
"""Regression test for the premium still-SR route readiness audit."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_route_readiness.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_summary(root: Path, name: str, image_count: int, rmse: float, mae: float, grad: float) -> Path:
    ckpt = root / f"artifacts/{name}/{name}.pt"
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    ckpt.write_bytes(name.encode("utf-8"))
    return write_json(
        root / f"artifacts/{name}/summary.json",
        {
            "schema": "mission1_sr_fullframe_broad_eval.v1",
            "checkpoint": str(ckpt),
            "image_count": image_count,
            "dashboard": str(root / f"artifacts/{name}/index.html"),
            "rmse_improvement_pct": {"median": rmse},
            "mae_improvement_pct": {"median": mae},
            "gradient_mae_improvement_pct": {"median": grad},
            "fps_with_write": {"median": 2.0},
        },
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_route_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        out = Path(tmp) / "out"
        router = write_json(
            root / "artifacts/router/router_plan.json",
            {
                "schema": "gpr.premium_still_sr_router_plan.v1",
                "routing_policy": {
                    "routes": [
                        {"route_key": "mission1:50mp:dng", "candidate_id": "mission1_specialist"},
                        {"route_key": "mission1:50mp:gpr", "candidate_id": "mission1_specialist"},
                        {"route_key": "z8:50mp:dng", "candidate_id": "z8_specialist"},
                        {"route_key": "x2d:100mp:dng", "candidate_id": "x2d_specialist"},
                    ]
                },
            },
        )
        smoke = write_json(
            root / "artifacts/smoke/train_receipt.json",
            {
                "holdout_image": "z8",
                "median_mae_recovery_pct": -0.1,
                "median_rmse_recovery_pct": -0.1,
                "baseline_beaten_on_holdout": False,
                "promotion_ready": False,
            },
        )
        rendered = write_json(
            root / "artifacts/rendered/rendered_review.json",
            {
                "schema": "gpr.premium_still_sr_rendered_review.v1",
                "review_kind": "simple_demosaic_ev_stress_proxy",
                "production_ready": False,
                "contact_sheet": str(root / "artifacts/rendered/rendered_latitude_contact_sheet.jpg"),
                "limitations": ["proxy only"],
                "summary": {
                    "row_count": 9,
                    "model_better_count": 8,
                    "model_worse_count": 1,
                    "model_minus_baseline_mae": {"median": -0.01, "max": 0.001},
                },
                "rows": [
                    {"route": "mission1"},
                    {"route": "mission1"},
                    {"route": "mission1"},
                    {"route": "z8"},
                    {"route": "z8"},
                    {"route": "z8"},
                    {"route": "x2d"},
                    {"route": "x2d"},
                    {"route": "x2d"},
                ],
            },
        )
        (root / "artifacts/rendered/index.html").write_text("<h1>rendered</h1>", encoding="utf-8")
        (root / "artifacts/rendered/rendered_latitude_contact_sheet.jpg").write_bytes(b"jpg")
        args = [
            sys.executable,
            str(TOOL),
            "--external-root",
            str(root),
            "--router-plan",
            str(router),
            "--fullframe-summary",
            f"mission1:50mp:dng={write_summary(root, 'mission_dng', 2, 10.0, 9.0, 8.0)}",
            "--fullframe-summary",
            f"mission1:50mp:gpr={write_summary(root, 'mission_gpr', 2, 10.0, 9.0, 8.0)}",
            "--fullframe-summary",
            f"z8:50mp:dng={write_summary(root, 'z8', 1, 5.0, 4.0, 3.0)}",
            "--fullframe-summary",
            f"x2d:100mp:dng={write_summary(root, 'x2d', 1, 2.0, 1.0, 1.0)}",
            "--rejected-smoke",
            str(smoke),
            "--rendered-review",
            str(rendered),
            "--output-dir",
            str(out),
        ]
        subprocess.run(args, cwd=ROOT, check=True)
        data = json.loads((out / "route_readiness.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_route_readiness.v1"
        assert data["route_coverage_ready"] is True
        assert data["fullframe_metric_floor_ready"] is True
        assert data["rendered_proxy_review_ready"] is True
        assert data["production_ready"] is False
        assert "clean-source split candidate is rejected for long training because a paired smoke gate failed" in data["blockers"]
        assert "rendered EV-stress proxy review is not present for every required route" not in data["blockers"]
        assert "raw-editor latitude/openability receipt is not present for every route" in data["blockers"]
        assert data["rendered_review"]["model_better_count"] == 8
        assert "Use the routed specialist/raw-CFA path" in data["next_unambiguous_steps"][0]
        assert "Premium Still-SR Route Readiness" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_route_readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
