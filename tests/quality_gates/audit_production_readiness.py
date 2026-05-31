#!/usr/bin/env python3
"""Production readiness audit for user-visible output families.

This is not a quality gate replacement. It is a checklist runner that verifies
the production surface has receipts or runnable scripts for each output family:
stills, video freeze quality, preview/chroma, UPRESABLE, containers, and the
Pi 5 / Mission 1 target path.

Default mode prints the matrix and exits 0 so it can be used while burning the
list down. Use --strict to make any FAIL row exit non-zero.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "tests/quality_gates/runs"
REG = json.loads((REPO / "pipelines/registry.json").read_text())


@dataclass
class Check:
    area: str
    name: str
    status: str
    detail: str


def git_tracked(path: Path) -> bool:
    rel = str(path.relative_to(REPO))
    try:
        subprocess.check_output(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=REPO,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def tracked_run_jsons() -> list[Path]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "tests/quality_gates/runs/*/run.json"],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    return [REPO / line.strip() for line in out.splitlines() if line.strip()]


def latest_pass_for_pipeline(pipeline: str) -> dict | None:
    matches = []
    for path in tracked_run_jsons():
        try:
            run = json.loads(path.read_text())
        except Exception:
            continue
        if run.get("pipeline") == pipeline and run.get("verdict") == "PASS":
            matches.append((run.get("finished_at") or "", path.parent.name, run))
    if not matches:
        return None
    return sorted(matches)[-1][2]


def ship_pipelines(prefix: str) -> list[tuple[str, dict]]:
    out = []
    for name, pipe in REG.get("pipelines", {}).items():
        if not isinstance(pipe, dict):
            continue
        if str(pipe.get("$role", "")).startswith(prefix):
            out.append((name, pipe))
    return out


def run_summary(run: dict | None) -> str:
    if not run:
        return "no committed PASS run"
    worst = run.get("worst_image") or {}
    return f"run={run.get('run_hash')} gates={run.get('gates_sha')} worst={worst.get('id')} lpips={worst.get('lpips'):.4f}"


def check_ship_group(area: str, prefix: str) -> list[Check]:
    checks = []
    for pipeline, pipe in ship_pipelines(prefix):
        run = latest_pass_for_pipeline(pipeline)
        role = pipe.get("$role", "?")
        status = "PASS" if run else "FAIL"
        checks.append(Check(area, role, status, run_summary(run)))
    if not checks:
        checks.append(Check(area, prefix, "FAIL", "no registry roles found"))
    return checks


def check_pipeline(area: str, name: str, pipeline: str) -> Check:
    run = latest_pass_for_pipeline(pipeline)
    return Check(area, name, "PASS" if run else "FAIL", run_summary(run))


def check_file(area: str, name: str, rel_path: str, require_tracked: bool = True) -> Check:
    path = REPO / rel_path
    if not path.exists():
        return Check(area, name, "FAIL", f"missing {rel_path}")
    if require_tracked and not git_tracked(path):
        return Check(area, name, "FAIL", f"exists but is not tracked: {rel_path}")
    return Check(area, name, "PASS", rel_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="exit non-zero when any check fails")
    args = ap.parse_args()

    checks: list[Check] = []
    checks.extend(check_ship_group("stills", "ship-still"))
    checks.extend(check_ship_group("video_quality", "ship-video-freeze"))
    checks.append(check_pipeline(
        "preview",
        "baseline PREVIEW",
        "codec=sl_q3+cnn=none+demosaic=sips_via_gpr_tools",
    ))
    checks.append(check_pipeline(
        "preview_chroma",
        "YCbCr decomp chroma candidate",
        "codec=ml2_q3_dec2+cnn=ycbcr_decomp_y_w16_cb_w8_cr_w8+demosaic=sips_via_gpr_tools",
    ))
    checks.append(check_pipeline(
        "upresable",
        "production UPRESABLE",
        "codec=ml2_q3_dec2+cnn=bibo2x_ane_ml2_q3_dec2_diverse+demosaic=sips_via_gpr_tools",
    ))

    checks.extend([
        check_file("container_gvid", "wire format header", "source/lib/vc5_encoder/gpr_video_format.h"),
        check_file("container_gvid", "wire format implementation", "source/lib/vc5_encoder/gpr_video_format.c"),
        check_file("container_gvid", "CI format smoke", "source/app/test_video_format.c"),
        check_file("container_gpraw", "GPRaw pack tool", "tools/gpr2prores/gpr_mov_tool", require_tracked=False),
        check_file("container_gpraw", "GPRaw fixture recipe", "tools/test/make_gpraw_fixture.sh"),
        check_file("pi5_mission1", "Pi encoder benchmark", "tools/test/test_pi_encoder.sh"),
        check_file("pi5_mission1", "Pi-to-Mac UPRESABLE bench", "tools/test/bench_pi_to_mac_upresable.sh"),
        check_file("pi5_mission1", "Pi SD first-boot config", "tools/test/configure_pi_sd.sh"),
    ])

    print("=== production readiness audit ===")
    fail_count = 0
    for c in checks:
        if c.status != "PASS":
            fail_count += 1
        print(f"{c.status:4}  {c.area:16}  {c.name:42}  {c.detail}")
    print()
    if fail_count:
        print(f"{fail_count} readiness check(s) failing")
    else:
        print("OK - all readiness checks pass")
    return 1 if args.strict and fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
