#!/usr/bin/env python3
"""Regression test for the premium still-SR launch packet builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_launch_packet.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or "/Volumes/OWC_8TB/gpr_work/tmp")
    if not root.exists():
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_premium_sr_launch_packet_", dir=temp_root()) as td:
        base = Path(td)
        good = base / "good_packet"
        proc = run([sys.executable, str(TOOL), "--output-dir", str(good), "--require-launchable"])
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        for name in (
            "candidate_preflight.json",
            "preflight_audit.json",
            "launch_packet.json",
            "launch_packet.md",
            "index.html",
        ):
            assert (good / name).exists(), name

        packet = json.loads((good / "launch_packet.json").read_text(encoding="utf-8"))
        assert packet["schema"] == "gpr.premium_still_sr_launch_packet.v1"
        assert packet["production_ready"] is False
        assert packet["promotion_claimed"] is False
        assert packet["preflight"]["launchable_for_production_attempt"] is True
        assert packet["preflight"]["verdict"] == "launchable_preflight_passed"
        commands = "\n".join(item["command"] for item in packet["next_commands"])
        for token in (
            "build_premium_still_sr_candidate_preflight_template.py",
            "check_premium_still_sr_candidate_preflight.py",
            "build_premium_still_sr_pairs.py",
            "audit_premium_still_sr_pairs.py",
            "train_premium_still_sr_clean_source_pairs.py",
            "build_premium_still_sr_experiment_scoreboard.py",
            "check_premium_still_sr_promotion_gate.py",
        ):
            assert token in commands, token
        repeats = " ".join(packet["blocked_repeats"])
        assert "residual_pixelshuffle" in repeats
        assert "local-CNN" in repeats
        assert "source-HF" in repeats
        assert any("50 MP" in item and "100 MP" in item for item in packet["promotion_stop_conditions"])

        bad = base / "bad_packet"
        proc = run(
            [
                sys.executable,
                str(TOOL),
                "--output-dir",
                str(bad),
                "--template",
                "rejected_repeat_fixture",
                "--require-launchable",
            ]
        )
        assert proc.returncode != 0
        assert (bad / "launch_packet.json").exists()
        blocked = json.loads((bad / "launch_packet.json").read_text(encoding="utf-8"))
        assert blocked["preflight"]["launchable_for_production_attempt"] is False
        assert blocked["preflight"]["verdict"] == "blocked_before_long_run"
        assert any("rejected primary path" in item for item in blocked["preflight"]["failures"])

    print("test_build_premium_still_sr_launch_packet: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
