#!/usr/bin/env python3
"""Regression test for the premium still-SR router plan builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_router_plan.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_candidate(root: Path, name: str, holdout: str, rmse: float) -> Path:
    ckpt = root / f"artifacts/{name}/{name}.pt"
    pairs = root / f"artifacts/{name}/pairs.npz"
    receipt = root / f"artifacts/{name}/{name}.pt.json"
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    ckpt.write_bytes(f"{name} checkpoint".encode("utf-8"))
    pairs.write_bytes(f"{name} pairs".encode("utf-8"))
    receipt.write_text(
        json.dumps(
            {
                "schema": "mission1_sr_train_receipt.v1",
                "checkpoint": str(ckpt),
                "pairs": str(pairs),
                "architecture": "lowres_pixelshuffle",
                "width": 8,
                "depth": 3,
                "holdout_image": holdout,
                "train_tiles": 10,
                "eval_tiles_total": 4,
                "best_eval": {
                    "step": 20,
                    "rmse_improvement_pct": rmse,
                    "mae_improvement_pct": rmse * 0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_router_", dir=temp_root()) as tmp:
        root = Path(tmp) / "external"
        out = Path(tmp) / "out"
        manifest = root / "artifacts/fixtures/fixture_manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_fixture_manifest.v1",
                    "fixtures": [
                        {
                            "label": "x2d_a",
                            "camera": "Hasselblad X2D 100C",
                            "camera_key": "x2d",
                            "class": "100mp",
                            "extension": "dng",
                            "premium_still_sr_eligible": True,
                            "source": {"exists": True, "path": "/tmp/x2d.dng"},
                            "noise_sidecars": [{"path": "/tmp/noise.json"}],
                        },
                        {
                            "label": "mission_a",
                            "camera": "GoPro Mission 1",
                            "camera_key": "mission1",
                            "class": "50mp",
                            "extension": "gpr",
                            "premium_still_sr_eligible": True,
                            "source": {"exists": True, "path": "/tmp/mission.gpr"},
                            "noise_sidecars": [],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        x2d_receipt = write_candidate(root, "x2d_model", "x2d_a", 1.25)
        shared_receipt = write_candidate(root, "shared_model", "mission_a", 0.5)
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--external-root",
                str(root),
                "--fixture-manifest",
                str(manifest),
                "--receipt",
                str(x2d_receipt),
                "--receipt",
                str(shared_receipt),
                "--candidate-alias",
                "candidate_0=x2d_specialist",
                "--candidate-alias",
                "candidate_1=shared",
                "--route",
                "x2d:100mp:dng=x2d_specialist",
                "--default-candidate",
                "shared",
                "--output-dir",
                str(out),
            ],
            cwd=ROOT,
            check=True,
        )
        data = json.loads((out / "router_plan.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_router_plan.v1"
        assert data["production_ready"] is False
        assert data["fixture_summary"]["route_count"] == 2
        routes = {row["route_key"]: row for row in data["routing_policy"]["routes"]}
        assert routes["x2d:100mp:dng"]["candidate_id"] == "x2d_specialist"
        assert routes["mission1:50mp:gpr"]["candidate_id"] == "shared"
        assert routes["x2d:100mp:dng"]["candidate_found"] is True
        assert "candidate x2d_specialist is not production-ready" in data["blockers"]
        assert "Premium Still-SR Router Plan" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_router_plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
