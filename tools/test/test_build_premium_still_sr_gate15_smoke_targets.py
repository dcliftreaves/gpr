#!/usr/bin/env python3
"""Regression test for Gate15 smoke target materializer."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError as exc:  # pragma: no cover - CI image supplies numpy
    raise SystemExit("test_build_premium_still_sr_gate15_smoke_targets.py requires numpy") from exc


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate15_smoke_targets.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate15_smoke_targets_", dir=temp_root()) as td:
        base = Path(td)
        rows = [
            {"domain": "x2d", "scene_id": "x2d_train", "gate14_output_index": 0, "tile_index": 10},
            {"domain": "x2d", "scene_id": "x2d_holdout", "gate14_output_index": 1, "tile_index": 11},
            {"domain": "x2d", "scene_id": "x2d_low", "gate14_output_index": 2, "tile_index": 12},
            {"domain": "z8", "scene_id": "z8_a", "gate14_output_index": 3, "tile_index": 13},
            {"domain": "z8", "scene_id": "z8_b", "gate14_output_index": 4, "tile_index": 14},
        ]
        shape = (len(rows), 4, 4, 4)
        targets = base / "targets.npz"
        np.savez_compressed(
            targets,
            candidate_raw_cfa4=np.ones(shape, dtype=np.float16),
            candidate_raw_hf_cfa4=np.ones(shape, dtype=np.float16) * 2,
            raw_hf_residual_cfa4=np.ones(shape, dtype=np.float16) * 3,
            source_raw_hf_cfa4=np.ones(shape, dtype=np.float16) * 4,
            render_hf_residual_y=np.ones((len(rows), 4, 4), dtype=np.float16),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        proposal = base / "proposal.json"
        write_json(
            proposal,
            {
                "schema": "gpr.premium_still_sr_gate15_target_construction_proposal.v1",
                "candidate_id": "gate15_test",
                "pretraining_signal_rows": [
                    {"domain": "x2d", "gate14_output_index": 0, "candidate_only_positive_floor": True},
                    {"domain": "x2d", "gate14_output_index": 1, "candidate_only_positive_floor": True},
                    {"domain": "x2d", "gate14_output_index": 2, "candidate_only_positive_floor": False, "exact_noop": True},
                    {"domain": "z8", "gate14_output_index": 3, "exact_noop": True},
                    {"domain": "z8", "gate14_output_index": 4, "exact_noop": True},
                ],
            },
        )
        preflight = base / "preflight.json"
        write_json(preflight, {"paired_smoke_allowed": True})
        out = base / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--gate14-target-npz",
                str(targets),
                "--proposal",
                str(proposal),
                "--preflight",
                str(preflight),
                "--output-dir",
                str(out),
                "--python-bin",
                sys.executable,
                "--minimum-x2d-positive-rows",
                "2",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        receipt = json.loads((out / "gate15_smoke_targets.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_gate15_smoke_targets.v1"
        assert receipt["paired_smoke_ready"] is True
        assert receipt["long_run_allowed"] is False
        assert receipt["coverage"]["x2d_positive_target_rows"] == 2
        assert receipt["coverage"]["z8_exact_noop_rows"] == 2
        manifest = json.loads((out / "candidate_preflight.json").read_text(encoding="utf-8"))
        assert manifest["schema"] == "gpr.premium_still_sr_candidate_preflight.v1"
        assert manifest["candidate_id"] == "gate15_test"
        assert len(manifest["smoke_gate_commands"]) == 2
        assert "train_premium_still_sr_raw_cfa_residual.py" in manifest["smoke_gate_commands"][0]
        assert "build_premium_still_sr_exact_noop_receipt.py" in manifest["smoke_gate_commands"][1]
        assert manifest["smoke_gate_acceptance"]["route_acceptance"]["z8"]["requires_exact_noop"] is True
        with np.load(out / "gate15_x2d_positive_targets.npz", allow_pickle=False) as z:
            assert z["candidate_raw_cfa4"].shape[0] == 2
            out_rows = json.loads(str(z["meta"]))
        assert all(row["gate15_candidate_only_positive_floor"] is True for row in out_rows)
        assert "Gate15 Smoke Targets" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_gate15_smoke_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
