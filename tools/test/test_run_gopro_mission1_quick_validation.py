#!/usr/bin/env python3
"""Tests for the GoPro Mission 1 quick validation wrapper."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/run_gopro_mission1_quick_validation.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "quick"
        compact = Path(tmp) / "compact"
        proc = run_tool(
            "--output-dir",
            str(out),
            "--collection-output-dir",
            str(compact),
            "--dry-run",
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["schema"] == "gpr.gopro_mission1_quick_validation.v1"
        assert payload["dry_run"] is True
        assert payload["target"]["role"] == "camera"
        assert payload["target"]["raw_source_kind"] == "sensor_dma_capture"
        assert payload["verdict"]["command_ready"] is True
        assert payload["verdict"]["production_ready"] is False
        assert [step["name"] for step in payload["steps"]] == [
            "source_probe",
            "check_source_probe",
            "target_closure_package",
            "check_camera_handoff",
            "check_preview_ui",
            "check_closure_run",
        ]
        assert "mission1_camera_source_probe.py" in " ".join(payload["steps"][0]["cmd"])
        assert "check_mission1_camera_source_probe.py" in " ".join(payload["steps"][1]["cmd"])
        assert "run_mission1_target_closure_package.py" in " ".join(payload["steps"][2]["cmd"])
        assert "--camera-frame-source-ready" in payload["steps"][2]["cmd"]
        assert "--sensor-dma-executed" in payload["steps"][2]["cmd"]
        assert "--ui-path-executed" in payload["steps"][2]["cmd"]
        assert not out.exists()
        assert not compact.exists()
    print("test_run_gopro_mission1_quick_validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
