#!/usr/bin/env python3
"""Regression test for the darkframe candidate audit builder."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_darkframe_candidate_audit.py"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_darkframe_candidate_audit_") as tmp:
        out = Path(tmp) / "out"
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--synthetic", "--output-dir", str(out)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads((out / "darkframe_candidate_audit.json").read_text(encoding="utf-8"))
        html = (out / "index.html").read_text(encoding="utf-8")
        assert audit["schema"] == "gpr.darkframe_candidate_audit.v1"
        assert audit["mode"] == "synthetic"
        assert audit["summary"]["files_seen"] == 5
        assert audit["summary"]["darkframe_like_count"] == 4
        assert audit["summary"]["production_stack_ready_group_count"] == 1
        assert audit["summary"]["production_sidecar_ready"] is True
        assert audit["policy"]["ordinary_scene_frames_are_not_noise_targets"] is True
        assert "Darkframe Candidate Audit" in html
        assert proc.stdout.strip() == str(out / "index.html")
    print("test_build_darkframe_candidate_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
