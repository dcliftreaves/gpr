#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
except ModuleNotFoundError as exc:  # pragma: no cover - CI supplies numpy
    print("test_build_premium_still_sr_gate17_replacement_targets: SKIP missing numpy")
    raise SystemExit(0) from exc


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate17_replacement_targets.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate17_targets_", dir=temp_root()) as td:
        base = Path(td)
        rows = []
        for i in range(3):
            rows.append(
                {
                    "class": "100mp",
                    "domain": "x2d",
                    "camera": "Hasselblad X2D 100C",
                    "scene_id": f"x2d_{i}",
                    "gate14_output_index": i,
                    "raw_same_color_hf_residual_abs_mean": 0.01 + i * 0.01,
                    "candidate_raw_same_color_hf_abs_mean": 0.004 + i * 0.001,
                    "source_raw_same_color_hf_abs_mean": 0.02 + i * 0.001,
                }
            )
        for i in range(4):
            rows.append(
                {
                    "class": "50mp",
                    "domain": "z8",
                    "camera": "Nikon Z8",
                    "scene_id": f"z8_{i}",
                    "gate14_output_index": i + 3,
                    "raw_same_color_hf_residual_abs_mean": 0.001 + i * 0.001,
                    "candidate_raw_same_color_hf_abs_mean": 0.0004 + i * 0.0001,
                    "source_raw_same_color_hf_abs_mean": 0.002 + i * 0.0001,
                }
            )
        shape = (len(rows), 4, 4, 4)
        targets = base / "gate14_targets.npz"
        np.savez_compressed(
            targets,
            candidate_raw_cfa4=np.ones(shape, dtype=np.float16),
            candidate_raw_hf_cfa4=np.ones(shape, dtype=np.float16) * 2,
            raw_hf_residual_cfa4=np.ones(shape, dtype=np.float16) * 3,
            source_raw_hf_cfa4=np.ones(shape, dtype=np.float16) * 4,
            render_hf_residual_y=np.ones((len(rows), 4, 4), dtype=np.float16),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        gate16 = base / "gate16_audit.json"
        write_json(
            gate16,
            {
                "schema": "gpr.premium_still_sr_gate16_target_row_audit.v1",
                "candidate_id": "gate16_rejected",
                "production_promotable_from_this_audit": False,
            },
        )
        out = base / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--gate14-target-npz",
                str(targets),
                "--gate16-audit",
                str(gate16),
                "--output-dir",
                str(out),
                "--candidate-id",
                "gate17_test",
                "--python-bin",
                sys.executable,
                "--rows-per-class",
                "2",
                "--minimum-rows-per-class",
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
        receipt = json.loads((out / "gate17_replacement_targets.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_gate17_replacement_targets.v1"
        assert receipt["candidate_id"] == "gate17_test"
        assert receipt["paired_smoke_ready"] is True
        assert receipt["long_run_allowed"] is False
        assert receipt["coverage"]["selected_class_counts"] == {"100mp": 2, "50mp": 2}
        assert receipt["runtime_policy"]["forbidden_runtime_inputs_absent"] is True
        assert receipt["runtime_policy"]["uses_ref_or_source_content_at_render_time"] is False
        assert all(row["gate17_exact_noop"] is False for row in receipt["sample_rows"])
        manifest = json.loads((out / "candidate_preflight.json").read_text(encoding="utf-8"))
        assert manifest["schema"] == "gpr.premium_still_sr_candidate_preflight.v1"
        assert manifest["candidate_id"] == "gate17_test"
        assert manifest["forbidden_runtime_inputs_absent"] is True
        assert len(manifest["smoke_gate_commands"]) == 2
        with np.load(out / "gate17_replacement_targets.npz", allow_pickle=False) as z:
            assert z["candidate_raw_cfa4"].shape[0] == 4
            out_rows = json.loads(str(z["meta"]))
        assert {row["gate17_target_class"] for row in out_rows} == {"50mp", "100mp"}
        assert "Gate17 Premium Still-SR Replacement Targets" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_gate17_replacement_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
