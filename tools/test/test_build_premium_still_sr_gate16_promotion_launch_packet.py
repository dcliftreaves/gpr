#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate16_promotion_launch_packet.py"


def write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        checkpoint = root / "gate16.pt"
        checkpoint.write_bytes(b"checkpoint\n")

        preflight = write_json(
            root / "candidate_preflight.json",
            {
                "candidate_id": "premium_still_sr_gate16_tail_safe_x2d_positive_z8_noop_v1",
                "launchable_for_production_attempt": True,
                "uses_ref_or_source_content_at_render_time": False,
                "forbidden_runtime_inputs_absent": True,
            },
        )
        audit = write_json(root / "preflight_audit.json", {"verdict": "launchable_preflight_passed"})
        acceptance = write_json(
            root / "smoke_gate_acceptance.json",
            {
                "smoke_gate_passed": True,
                "long_run_allowed": True,
                "rows": [
                    {
                        "holdout": "x2d",
                        "median_mae_improvement_pct": 17.0,
                        "worst_row_mae_improvement_pct": 0.0,
                        "checkpoint_sha256": "abc",
                    },
                    {
                        "holdout": "z8",
                        "median_mae_improvement_pct": 0.0,
                        "worst_row_mae_improvement_pct": 0.0,
                        "checkpoint_sha256": "def",
                    },
                ],
            },
        )
        x2d = write_json(
            root / "x2d_train_receipt.json",
            {
                "checkpoint": checkpoint.as_posix(),
                "checkpoint_sha256": __import__("hashlib").sha256(checkpoint.read_bytes()).hexdigest(),
            },
        )
        z8 = write_json(root / "z8_noop.json", {"checkpoint_sha256": "def"})
        route = write_json(
            root / "route_readiness.json",
            {
                "route_coverage_ready": True,
                "fullframe_metric_floor_ready": True,
                "rendered_proxy_review_ready": True,
                "required_routes": ["z8:50mp:dng", "x2d:100mp:dng"],
                "routes": [
                    {
                        "route_key": "z8:50mp:dng",
                        "positive_fullframe_metrics": True,
                        "median_mae_improvement_pct": 7.0,
                        "median_rmse_improvement_pct": 40.0,
                    },
                    {
                        "route_key": "x2d:100mp:dng",
                        "positive_fullframe_metrics": True,
                        "median_mae_improvement_pct": 1.0,
                        "median_rmse_improvement_pct": 1.0,
                    },
                ],
            },
        )
        editor = write_json(
            root / "coverage.json",
            {
                "production_ready": True,
                "openability_route_coverage_ready": True,
                "latitude_route_coverage_ready": True,
            },
        )
        noise = write_json(
            root / "noise.json",
            {
                "clean_signal": {
                    "policy_pass": True,
                    "row_count": 10,
                    "rows_with_noise_sidecars": 10,
                }
            },
        )
        rollup = write_json(
            root / "rollup.json",
            {
                "first_open_step": "model_promotion_floor",
                "done_step_count": 5,
                "total_step_count": 9,
            },
        )
        out = root / "out"
        cmd = [
            sys.executable,
            str(TOOL),
            "--preflight",
            str(preflight),
            "--preflight-audit",
            str(audit),
            "--smoke-acceptance",
            str(acceptance),
            "--x2d-train-receipt",
            str(x2d),
            "--z8-noop-receipt",
            str(z8),
            "--route-readiness",
            str(route),
            "--editor-coverage",
            str(editor),
            "--noise-policy-gate",
            str(noise),
            "--promotion-rollup",
            str(rollup),
            "--output-dir",
            str(out),
            "--require-ready-to-launch",
        ]
        subprocess.run(cmd, cwd=ROOT, check=True)
        payload = json.loads((out / "gate16_promotion_launch_packet.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.premium_still_sr_gate16_promotion_launch_packet.v1"
        assert payload["ready_to_launch_full_gate"] is True
        assert payload["production_ready"] is False
        assert payload["first_open_step"] == "gate16_full_frame_metric_generation"
        assert payload["blocked_by_existing_route_metrics"] is True
        assert payload["promotion_thresholds"]["median_mae_reduction_pct_100mp"] == 15.0
        assert len(payload["missing_evidence_before_100_percent"]) >= 8
    print("test_build_premium_still_sr_gate16_promotion_launch_packet: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
