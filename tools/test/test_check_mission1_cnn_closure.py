#!/usr/bin/env python3
"""Regression coverage for the Mission 1 CNN closure guard."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_mission1_cnn_closure.py"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def test_ci_safe_without_external_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_tool("--external-root", tmp)
    assert result.returncode == 0, result.stdout
    assert "Mission 1 CNN closure guard OK" in result.stdout


def test_strict_artifacts_require_receipts() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = run_tool("--external-root", tmp, "--strict-artifacts")
    assert result.returncode != 0
    assert "missing external 4K cleanup production signoff receipt" in result.stdout
    assert "missing external 8K SR production promotion receipt" in result.stdout


if __name__ == "__main__":
    test_ci_safe_without_external_artifacts()
    test_strict_artifacts_require_receipts()
    print("test_check_mission1_cnn_closure: PASS")
