#!/usr/bin/env python3
"""Regression test for premium still-SR expanded target executor planning."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_premium_still_sr_expanded_hf_targets_from_plan.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_expanded_plan_", dir=temp_root()) as tmp:
        root = Path(tmp)
        existing = root / "existing_target.npz"
        existing.write_bytes(b"fixture")
        merged = root / "old_merge.json"
        write_json(merged, {"sources": [{"path": str(existing), "rows": 27}]})
        plan = root / "plan.json"
        write_json(
            plan,
            {
                "sources": {"merged_target": str(merged)},
                "selected_new_targets": [
                    {
                        "scene_id": "scene_a",
                        "source_path": "/fixtures/source_a.dng",
                        "source_iso": 200,
                        "selected_noise_sidecars": [{"path": "/noise/iso200.json"}],
                    }
                ],
            },
        )
        out = root / "out"
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--plan", str(plan), "--output-dir", str(out), "--dry-run"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        receipt = json.loads((out / "expanded_target_build_receipt.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_expanded_hf_target_build.v1"
        assert receipt["dry_run"] is True
        assert receipt["scene_count"] == 1
        assert str(existing) in receipt["merge_inputs"]
        commands = "\n".join(" ".join(cmd) for cmd in receipt["scene_results"][0]["commands"])
        assert "build_premium_still_sr_degraded_candidate_raw.py" in commands
        assert "build_premium_still_sr_hf_residual_targets.py" in commands
        assert "--candidate-raw" in commands
        assert "--noise-sidecar /noise/iso200.json" in commands

    print("test_build_premium_still_sr_expanded_hf_targets_from_plan: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
