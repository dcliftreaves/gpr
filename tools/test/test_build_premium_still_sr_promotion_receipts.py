#!/usr/bin/env python3
"""Regression test for Premium still-SR promotion receipt builder."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_promotion_receipts.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("build_premium_still_sr_promotion_receipts", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def selector() -> dict:
    return {
        "schema": "gpr.premium_still_sr_gate14_selector_smoke.v1",
        "production_ready": False,
        "gate14_selector_smoke_passed": True,
        "promotion_gate_allowed": True,
        "long_run_allowed": False,
        "rule_count": 7,
        "source_count": 6,
        "assigned_row_count": 88,
        "fallback_exact_noop_count": 40,
        "source_model_failures": [],
        "selector_smoke_metrics": {
            "median": 0.25,
            "min": 0.0,
            "negative_row_count": 0,
            "by_image": {
                "x2d_a": {"median": 0.33},
                "x2d_b": {"median": 0.03},
            },
        },
    }


def route() -> dict:
    return {
        "schema": "gpr.premium_still_sr_route_readiness.v1",
        "route_coverage_ready": True,
        "fullframe_metric_floor_ready": True,
        "rendered_proxy_review_ready": True,
        "production_ready": False,
        "routes": [{}, {}, {}, {}],
        "blockers": ["production submission missing"],
    }


def editor() -> dict:
    return {
        "schema": "gpr.premium_still_sr_editor_latitude_coverage.v1",
        "production_ready": True,
        "openability_route_coverage_ready": True,
        "latitude_route_coverage_ready": True,
        "blockers": [],
    }


def noise(production_ready: bool) -> dict:
    return {
        "schema": "gpr.premium_still_sr_noise_policy_gate.v1",
        "production_ready": production_ready,
        "clean_signal": {
            "policy_pass": True,
            "row_count": 8,
            "rows_with_noise_sidecars": 8,
        },
        "model_receipts": [{"policy_pass": production_ready}],
        "blockers": [] if production_ready else ["no supplied model receipt clears the promotion policy and holdout floors"],
    }


def promotion(production_ready: bool) -> dict:
    row_count = 4 if production_ready else 0
    gain = 16.0 if production_ready else 0.0
    timing = 2.5 if production_ready else 0.0
    return {
        "schema": "gpr.premium_still_sr_promotion_gate.v1",
        "promotion_safe": True,
        "production_ready": production_ready,
        "blockers": [],
        "full_gate_receipt": {
            "promotion_metrics": {
                "full_frame_gate_50mp_row_count": row_count,
                "full_frame_gate_100mp_row_count": row_count,
                "median_mae_reduction_pct_50mp": gain,
                "median_mae_reduction_pct_100mp": gain,
            },
            "performance": {
                "render_seconds_per_50mp_frame": timing,
                "render_seconds_per_100mp_frame": timing * 2,
                "peak_rss_gb": timing,
            },
        },
    }


def requirements() -> dict:
    evidence = [
        "candidate raw",
        "camera metadata",
        "50 MP and 100 MP",
        "seconds per 50 MP frame",
        "seconds per 100 MP frame",
        "peak RSS",
        "source residual noise",
    ]
    return {
        "schema": "gpr.production_capture_requirements.v1",
        "requirements": [
            {
                "id": "premium_still_sr_promotion_receipts",
                "status": "open",
                "sample_type": "model_promotion_receipt",
                "required_evidence": evidence,
                "acceptance": evidence,
                "validation_commands": [
                    "python3 tools/check_premium_still_sr_candidate_preflight.py candidate_preflight.json",
                    "python3 tools/build_premium_still_sr_launch_packet.py --manifest candidate_preflight.json",
                ],
            }
        ],
    }


def run_case(tmp: Path, production_ready: bool) -> dict:
    tool = load_tool()
    write_json(tmp / "selector.json", selector())
    write_json(tmp / "route.json", route())
    write_json(tmp / "editor.json", editor())
    write_json(tmp / "noise.json", noise(production_ready))
    write_json(tmp / "promotion.json", promotion(production_ready))
    write_json(tmp / "requirements.json", requirements())
    args = type(
        "Args",
        (),
        {
            "selector_smoke": tmp / "selector.json",
            "route_readiness": tmp / "route.json",
            "editor_coverage": tmp / "editor.json",
            "noise_policy_gate": tmp / "noise.json",
            "promotion_gate": tmp / "promotion.json",
            "production_requirements": tmp / "requirements.json",
            "output_dir": tmp / ("ready" if production_ready else "blocked"),
            "require_production_ready": False,
        },
    )()
    return tool.build(args)


def main() -> int:
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_premium_receipts_", dir=tmp_parent) as td:
        root = Path(td)
        blocked = run_case(root / "blocked_case", False)
        assert blocked["schema"] == "gpr.premium_still_sr_promotion_receipts.v1"
        assert blocked["production_ready"] is False
        assert blocked["completion_percent"] == 50.0
        assert blocked["first_open_step"] == "model_promotion_floor"
        assert "model_promotion_floor_not_met" in blocked["blocker_classifications"]
        assert "full_50mp_100mp_gate_missing" in blocked["blocker_classifications"]
        assert (root / "blocked_case" / "blocked" / "index.html").is_file()

        ready = run_case(root / "ready_case", True)
        assert ready["production_ready"] is True
        assert ready["completion_percent"] == 100.0
        assert ready["first_open_step"] is None
        assert ready["blocker_classifications"] == []
    print("test_build_premium_still_sr_promotion_receipts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
