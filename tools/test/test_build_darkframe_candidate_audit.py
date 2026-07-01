#!/usr/bin/env python3
"""Regression test for the darkframe candidate audit builder."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_darkframe_candidate_audit.py"


def load_tool_module():
    spec = importlib.util.spec_from_file_location("build_darkframe_candidate_audit", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
        assert audit["summary"]["source_provenance_manifest_required"] is False
        assert audit["policy"]["ordinary_scene_frames_are_not_noise_targets"] is True
        assert audit["policy"]["confirmed_darkframes_require_source_provenance_manifest"] is True
        assert "Darkframe Candidate Audit" in html
        assert proc.stdout.strip() == str(out / "index.html")

        bad = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--source-kind",
                "confirmed_darkframes",
                "--output-dir",
                str(Path(tmp) / "bad"),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert bad.returncode != 0
        assert "requires --provenance-manifest" in (bad.stderr + bad.stdout)

        module = load_tool_module()
        rows = module.synthetic_rows()
        no_provenance = module.build_audit(
            rows,
            "real",
            [Path("synthetic")],
            "confirmed_darkframes",
            None,
        )
        assert no_provenance["summary"]["source_provenance_manifest_required"] is True
        assert no_provenance["summary"]["production_stack_ready_group_count"] == 0
        assert no_provenance["stack_groups"][0]["source_provenance_failure_count"] == 4

        dark_rows = [row for row in rows if row["darkframe_like"]]
        manifest = {
            "schema": "gpr.darkframe_source_provenance_manifest.v1",
            "source_kind": "confirmed_darkframes",
            "frames": [
                {
                    "path": row["path"],
                    "sha256": "a" * 64,
                    "no_scene_signal": True,
                    "capture_setup": "lens cap on",
                }
                for row in dark_rows
            ],
        }
        confirmed = module.build_audit(
            rows,
            "real",
            [Path("synthetic")],
            "confirmed_darkframes",
            manifest,
        )
        assert confirmed["summary"]["production_stack_ready_group_count"] == 1
        assert confirmed["stack_groups"][0]["source_provenance_ready"] is True
        assert confirmed["stack_groups"][0]["production_stack_ready"] is True
    print("test_build_darkframe_candidate_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
