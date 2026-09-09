#!/usr/bin/env python3
"""Regression test for the Gate 11 Premium still-SR preflight builder."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate11_candidate_preflight.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def load_module():
    spec = importlib.util.spec_from_file_location("gate11_preflight", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="gpr_gate11_", dir=temp_root()) as td:
        base = Path(td)
        audit = base / "degradation_source_audit.json"
        targets = base / "targets.npz"
        targets.write_bytes(b"fixture")
        write_json(
            audit,
            {
                "schema": "gpr.premium_still_sr_degradation_source_audit.v1",
                "gate11_candidate_intake_allowed": True,
                "selected_family": "route_isolated_teacher_then_router",
                "inputs": {
                    "gate10_decision": {"path": "/gate10/decision.json"},
                    "target_distribution": {"path": "/target/distribution.json"},
                    "target_snr": {"path": "/target/snr.json"},
                    "x2d_source_evidence": {"path": "/x2d/source_evidence.json"},
                    "z8_source_evidence": {"path": "/z8/source_evidence.json"},
                },
                "route_policy": {
                    "x2d": {
                        "policy": "train_signal_dominated_route_with_stratified_target_sampling",
                        "eligible_training_rows": 70,
                    },
                    "z8": {
                        "policy": "default_noop_for_noise_floor_rows_and_require_new_source_for_positive_route",
                        "eligible_training_rows": 8,
                    },
                },
                "forbidden_gate11_sources": [
                    "failed Gate 9 route-conditioned/noise-aware U-Net source policy",
                    "Z8 positive residual training on current noise-floor rows",
                ],
            },
        )
        out = base / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--degradation-source-audit",
                str(audit),
                "--targets",
                str(targets),
                "--python",
                "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
                "--output-dir",
                str(out),
                "--smoke-output-root",
                str(base / "gate11_smoke"),
                "--steps",
                "2",
                "--require-launchable",
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

        manifest = json.loads((out / "candidate_preflight.json").read_text(encoding="utf-8"))
        audit_out = json.loads((out / "preflight_audit.json").read_text(encoding="utf-8"))

        assert manifest["schema"] == module.SCHEMA
        assert manifest["candidate_id"] == "gate11_route_isolated_teacher_router_rawcfa_v1"
        assert manifest["production_ready"] is False
        assert manifest["launchable_for_production_attempt"] is True
        assert manifest["route_policy"]["selected_family"] == "route_isolated_teacher_then_router"
        assert manifest["route_policy"]["x2d"]["eligible_training_rows"] == 70
        assert manifest["route_policy"]["z8"]["eligible_training_rows"] == 8
        assert len(manifest["smoke_gate_commands"]) == 2
        assert any("--train-camera x2d" in cmd and "--train-snr-class signal_or_mixed" in cmd for cmd in manifest["smoke_gate_commands"])
        assert any("--train-camera Z8Z" in cmd and "--train-snr-class not_noise_floor" in cmd for cmd in manifest["smoke_gate_commands"])
        assert all("--candidate-hf-noop-threshold" in cmd for cmd in manifest["smoke_gate_commands"])
        assert any("--target-scale-policy candidate_hf_abs_mean" in cmd for cmd in manifest["smoke_gate_commands"])
        assert audit_out["launchable_for_production_attempt"] is True
        assert audit_out["verdict"] == "launchable_preflight_passed"
        assert proc.stdout.strip() == str(out / "index.html")

    print("test_build_premium_still_sr_gate11_candidate_preflight: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
