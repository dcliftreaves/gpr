#!/usr/bin/env python3
"""Smoke-test the Mission 1 8K SR visual-signoff receipt builder."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_8k_sr_visual_signoff.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mission1_8k_visual_signoff_") as td:
        root = Path(td)
        visual = root / "visual_review.json"
        out = root / "visual_signoff.json"
        visual.write_text(
            json.dumps(
                {
                    "schema": "gpr.mission1_8k_sr_visual_review.v1",
                    "manual_visual_review_required": True,
                    "manual_visual_review_complete": False,
                    "contact_sheet": "artifacts/contact.jpg",
                    "contact_sheet_sha256": "c" * 64,
                    "checks": [{"name": "quality", "passed": True}],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--visual-review",
                str(visual),
                "--statement",
                "approved",
                "--approved",
                "--output",
                str(out),
            ],
            check=True,
        )
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.mission1_8k_sr_visual_signoff.v1"
        assert data["visual_review"]["objective_checks_pass"] is True
        assert data["signoff"]["manual_visual_review_complete"] is True
        assert data["production_boundary"]["does_not_prove_controlled_native_psf"] is True
        assert data["production_boundary"]["controlled_native_psf_evidence_required_for_future_replacement"] is True
    print("test_build_mission1_8k_sr_visual_signoff: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
