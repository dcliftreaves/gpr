#!/usr/bin/env python3
"""Regression test for the Gate 9 Premium still-SR preflight builder."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate9_candidate_preflight.py"


def temp_root() -> Path:
    return Path("/Volumes/OWC_8TB/gpr_work/tmp") if Path("/Volumes/OWC_8TB/gpr_work/tmp").exists() else Path(tempfile.gettempdir())


def load_module():
    spec = importlib.util.spec_from_file_location("gate9_preflight", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_gate9_manifest_is_launchable() -> None:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="gpr_gate9_", dir=temp_root()) as td:
        base = Path(td)
        contract = base / "replacement_contract.json"
        targets = base / "targets.npz"
        targets.write_bytes(b"fixture")
        write_json(
            contract,
            {
                "schema": "gpr.premium_still_sr_replacement_target_source_contract.v1",
                "paired_smoke_preflight_allowed": True,
                "inputs": {
                    "x2d_source_evidence": {"path": "/x2d/source_evidence.json"},
                    "z8_source_evidence": {"path": "/z8/source_evidence.json"},
                    "target_distribution": {"path": "/target/distribution.json"},
                    "target_snr": {"path": "/target/snr.json"},
                },
            },
        )
        out = base / "out"
        subprocess.run(
            [
                "python3",
                str(TOOL),
                "--contract",
                str(contract),
                "--targets",
                str(targets),
                "--python",
                "/Volumes/OWC_8TB/gpr_work/venvs/gpr_ml/bin/python",
                "--output-dir",
                str(out),
                "--smoke-output-root",
                str(base / "gate9_smoke"),
                "--steps",
                "2",
                "--require-launchable",
            ],
            cwd=ROOT,
            check=True,
        )
        manifest = json.loads((out / "candidate_preflight.json").read_text(encoding="utf-8"))
        audit = json.loads((out / "preflight_audit.json").read_text(encoding="utf-8"))

        assert manifest["schema"] == module.SCHEMA
        assert manifest["candidate_id"] == "gate9_route_conditioned_noise_weighted_rawcfa_v1"
        assert manifest["runtime_inputs"] == [
            "candidate_raw",
            "camera_metadata",
            "validated_noise_sidecar_optional",
        ]
        assert manifest["forbidden_runtime_inputs_absent"] is True
        assert manifest["production_ready"] is False
        assert len(manifest["smoke_gate_commands"]) == 2
        assert any("--train-camera x2d" in cmd for cmd in manifest["smoke_gate_commands"])
        assert any("--train-camera Z8Z" in cmd for cmd in manifest["smoke_gate_commands"])
        assert any("--snr-loss-weight-policy continuous_snr" in cmd for cmd in manifest["smoke_gate_commands"])
        assert audit["launchable_for_production_attempt"] is True
        assert audit["verdict"] == "launchable_preflight_passed"


if __name__ == "__main__":
    test_gate9_manifest_is_launchable()
    print("test_build_premium_still_sr_gate9_candidate_preflight: PASS")
