#!/usr/bin/env python3
"""Regression test for the Gate 12 Premium still-SR preflight builder."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate12_candidate_preflight.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def load_module():
    spec = importlib.util.spec_from_file_location("gate12_preflight", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="gpr_gate12_", dir=temp_root()) as td:
        base = Path(td)
        source_audit = base / "measured_degradation_teacher_source_audit.json"
        pairs = base / "pairs.npz"
        pairs.write_bytes(b"fixture")
        write_json(
            source_audit,
            {
                "schema": "gpr.premium_still_sr_measured_degradation_teacher_source_audit.v1",
                "gate12_candidate_intake_allowed": True,
                "selected_family": "synthetic_known_degradation_teacher_x2d_plus_z8_noop",
                "long_run_allowed": False,
                "inputs": {
                    "x2d_source_evidence": {"path": "/x2d/source_evidence.json"},
                    "z8_source_evidence": {"path": "/z8/source_evidence.json"},
                    "x2d_teacher_smoke": {"path": "/x2d/teacher_smoke.json"},
                    "z8_teacher_smoke": {"path": "/z8/teacher_smoke.json"},
                    "clean_source_pair_meta": {"path": "/pairs/pairs.npz.json"},
                },
                "route_policy": {
                    "x2d": {
                        "policy": "train_synthetic_known_degradation_teacher_route",
                        "positive_training_allowed": True,
                        "source_evidence_present": True,
                        "teacher_smoke_median_mae_recovery_pct": 0.0088,
                    },
                    "z8": {
                        "policy": "exact_noop_or_new_source_required",
                        "positive_training_allowed": False,
                        "row_count": 36,
                        "noise_floor_rows": 28,
                        "source_evidence_present": False,
                    },
                },
                "forbidden_gate12_sources": [
                    "source_minus_candidate_raw_hf_residual target",
                    "Gate 11 route-isolated residual teacher/router rerun",
                ],
            },
        )

        out = base / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--source-audit",
                str(source_audit),
                "--pairs",
                str(pairs),
                "--python",
                "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
                "--output-dir",
                str(out),
                "--smoke-output-root",
                str(base / "gate12_smoke"),
                "--steps",
                "2",
                "--require-launchable",
            ],
            cwd=ROOT,
            env={**os.environ, "GPR_EXTERNAL_ROOT": str(base)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        manifest = json.loads((out / "candidate_preflight.json").read_text(encoding="utf-8"))
        audit = json.loads((out / "preflight_audit.json").read_text(encoding="utf-8"))
        assert manifest["schema"] == module.SCHEMA
        assert manifest["candidate_id"] == "gate12_synthetic_x2d_teacher_z8_exact_noop_v1"
        assert manifest["production_ready"] is False
        assert manifest["launchable_for_production_attempt"] is True
        assert manifest["route_policy"]["selected_family"] == "synthetic_known_degradation_teacher_x2d_plus_z8_noop"
        assert manifest["route_policy"]["x2d"]["positive_training_allowed"] is True
        assert manifest["route_policy"]["z8"]["positive_training_allowed"] is False
        assert len(manifest["smoke_gate_commands"]) == 2
        assert any("train_premium_still_sr_clean_source_pairs.py" in cmd and "--holdout-image x2d_2025_austin_07" in cmd for cmd in manifest["smoke_gate_commands"])
        assert any("build_premium_still_sr_exact_noop_receipt.py" in cmd and "--holdout z8" in cmd for cmd in manifest["smoke_gate_commands"])
        assert manifest["smoke_gate_acceptance"]["route_acceptance"]["z8"]["requires_exact_noop"] is True
        assert audit["launchable_for_production_attempt"] is True
        assert audit["verdict"] == "launchable_preflight_passed"
        assert proc.stdout.strip() == str(out / "index.html")
        assert "Premium Still-SR Gate 12 Candidate Preflight" in (out / "index.html").read_text(encoding="utf-8")

    print("test_build_premium_still_sr_gate12_candidate_preflight: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
