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
import re
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


def latest_run_for_pipeline(pipeline: str, ship_gate_only: bool = False) -> dict | None:
    matches = []
    for path in tracked_run_jsons():
        try:
            run = json.loads(path.read_text())
        except Exception:
            continue
        if ship_gate_only and run.get("is_ship_gate") is False:
            continue
        if run.get("pipeline") == pipeline:
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


def check_preview_color_guard(pipeline: str) -> Check:
    run = latest_run_for_pipeline(pipeline, ship_gate_only=True)
    if not run:
        return Check("preview_color", "Lab Chroma SIPS dE guardrail", "FAIL", "no committed run")
    bad = []
    for image_id, metrics in (run.get("images") or {}).items():
        de = metrics.get("dE2000_mean")
        if de is None or de > 3.0:
            bad.append(f"{image_id} dE={de}")
    if bad:
        return Check(
            "preview_color",
            "Lab Chroma SIPS dE guardrail",
            "FAIL",
            f"run={run.get('run_hash')} " + "; ".join(bad),
        )
    worst_lpips = max(
        (float(m.get("lpips", 0.0)) for m in (run.get("images") or {}).values()),
        default=0.0,
    )
    return Check(
        "preview_color",
        "Lab Chroma SIPS dE guardrail",
        "PASS",
        f"run={run.get('run_hash')} verdict={run.get('verdict')} dE<=3 all images; worst_lpips={worst_lpips:.4f}",
    )


def tracked_run_by_hash(run_hash: str) -> dict | None:
    path = RUNS_DIR / run_hash / "run.json"
    if not path.exists() or not git_tracked(path):
        return None
    try:
        run = json.loads(path.read_text())
    except Exception:
        return None
    return run if run.get("run_hash") == run_hash else None


def check_preview_detail_blocker_evidence() -> Check:
    """Accept the PREVIEW detail item only when the blocker is evidenced.

    The project stop criteria allow this area to be green if no candidate
    passes, but only after the failure is narrowed to a specific cause with
    committed metrics and visual/diagnostic receipts. This check verifies the
    tracked receipts behind that claim instead of accepting prose alone.
    """
    doc = REPO / "docs/PREVIEW_DETAIL_MOSAIC_RESULTS_2026-06-02.md"
    texture = RUNS_DIR / "dashboard/preview_texture_recoverability.json"
    for path in (doc, texture):
        if not path.exists():
            return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", f"missing {path.relative_to(REPO)}")
        if not git_tracked(path):
            return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", f"untracked {path.relative_to(REPO)}")

    try:
        tex = json.loads(texture.read_text())
    except Exception as exc:
        return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", f"bad recoverability JSON: {exc}")
    summary = {r.get("candidate"): r for r in tex.get("summary") or []}
    low2 = summary.get("ref_L_lowpass_x2")
    low4 = summary.get("ref_L_lowpass_x4")
    if not low2 or low2.get("all_pass") is not True:
        return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", "ref_L_lowpass_x2 oracle is not a committed PASS")
    if not low4 or low4.get("all_pass") is not False:
        return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", "ref_L_lowpass_x4 contrast is missing or not failing")

    required_failed = {
        "mosaic_x2": "46bf8050492744e2",
        "mosaic_z6693_select": "ebcfdf3a6ff3ba23",
        "mosaic_width48_blocker_select": "e5107f994eb2dd0b",
        "mosaic_width48_wavelet_lhf2": "6d7ed7f5b62f7732",
        "mosaic_fullref": "4ae4d3cfb39632ab",
        "luma_residual_v1": "5d3cf75bf1b1f44b",
        "luma_residual_v1_wavelet_hf": "b3b767e5d4d2f717",
        "luma_residual_v2": "9b1d4c8e7320de40",
        "rgb_residual_v1": "ac606b54716374b2",
    }
    missing = []
    bad = []
    best_lpips = 999.0
    best_ms = 0.0
    for label, run_hash in required_failed.items():
        run = tracked_run_by_hash(run_hash)
        if not run:
            missing.append(f"{label}:{run_hash}")
            continue
        if run.get("verdict") != "FAIL":
            bad.append(f"{label}:{run_hash} verdict={run.get('verdict')}")
            continue
        z6693 = (run.get("images") or {}).get("Z8Z_6693")
        if not z6693:
            bad.append(f"{label}:{run_hash} missing Z8Z_6693 metrics")
            continue
        lpips = float(z6693.get("lpips", 999.0))
        ms = float(z6693.get("ms_ssim", 0.0))
        if lpips <= 0.15 and ms >= 0.95:
            bad.append(f"{label}:{run_hash} unexpectedly passes blocker metrics")
        best_lpips = min(best_lpips, lpips)
        best_ms = max(best_ms, ms)
    if missing:
        return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", "missing tracked runs " + ", ".join(missing))
    if bad:
        return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", "; ".join(bad))

    text = doc.read_text(errors="ignore")
    doc_needles = [
        "not chroma",
        "not codec irrecoverability",
        "not just selecting a later training epoch",
        "capacity plus tile-level hard",
        "image selection",
        "wavelet target-cleanup",
        "wavelet-HF synthesis",
        "target/model path",
    ]
    missing_doc = [s for s in doc_needles if s not in text]
    if missing_doc:
        return Check("preview_detail", "Lab Chroma SIPS detail blocker evidence", "FAIL", f"doc missing {missing_doc}")

    return Check(
        "preview_detail",
        "Lab Chroma SIPS detail blocker evidence",
        "PASS",
        "no full PREVIEW pass; narrowed by tracked x2 oracle PASS, x4 oracle FAIL, "
        f"and {len(required_failed)} failed candidate receipts; best blocker lpips={best_lpips:.4f} ms={best_ms:.4f}",
    )


def check_preview_detail(area: str, name: str, pipeline: str) -> Check:
    run = latest_pass_for_pipeline(pipeline)
    if run:
        return Check(area, name, "PASS", run_summary(run))
    return check_preview_detail_blocker_evidence()


def check_file(area: str, name: str, rel_path: str, require_tracked: bool = True) -> Check:
    path = REPO / rel_path
    if not path.exists():
        return Check(area, name, "FAIL", f"missing {rel_path}")
    if require_tracked and not git_tracked(path):
        return Check(area, name, "FAIL", f"exists but is not tracked: {rel_path}")
    return Check(area, name, "PASS", rel_path)


def check_capabilities_doc() -> Check:
    path = REPO / "docs/CAPABILITIES.md"
    if not path.exists():
        return Check("platform_perf", "capability matrix receipt", "FAIL", "missing docs/CAPABILITIES.md")
    text = path.read_text(errors="ignore")
    if "FAILED" not in text:
        return Check("platform_perf", "capability matrix receipt", "FAIL", "unparseable docs/CAPABILITIES.md")
    m = re.search(r"- \*\*(\d+)\*\* FAILED", text)
    if not m:
        return Check("platform_perf", "capability matrix receipt", "FAIL", "missing FAILED summary")
    failed = int(m.group(1))
    return Check(
        "platform_perf",
        "capability matrix receipt",
        "PASS" if failed == 0 else "FAIL",
        f"docs/CAPABILITIES.md failed={failed}",
    )


def check_pi5_capture_receipt() -> Check:
    path = REPO / "docs/pi5_bench_2026-05-26.md"
    if not path.exists():
        return Check("platform_perf", "Pi 5 half-res capture fps receipt", "FAIL", "missing docs/pi5_bench_2026-05-26.md")
    text = path.read_text(errors="ignore")
    m = re.search(r"Half-res.*?fps_median=([0-9.]+)", text, re.S)
    if not m:
        return Check("platform_perf", "Pi 5 half-res capture fps receipt", "FAIL", "missing half-res fps_median")
    fps = float(m.group(1))
    return Check(
        "platform_perf",
        "Pi 5 half-res capture fps receipt",
        "PASS" if fps >= 24.0 else "FAIL",
        f"fps_median={fps:.2f} target>=24.00",
    )


def check_script_contains(area: str, name: str, rel_path: str, patterns: list[str]) -> Check:
    base = check_file(area, name, rel_path)
    if base.status != "PASS":
        return base
    text = (REPO / rel_path).read_text(errors="ignore")
    missing = [p for p in patterns if p not in text]
    if missing:
        return Check(area, name, "FAIL", f"{rel_path} missing {missing}")
    return Check(area, name, "PASS", rel_path)


def check_upresable_bench_receipt() -> list[Check]:
    log = Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable/pi_mac_bench/run.log")
    if not log.exists():
        return [Check("platform_perf", "UPRESABLE Pi-to-Mac bench receipt", "FAIL", f"missing {log}")]
    text = log.read_text(errors="ignore")
    checks = []
    rows = {}
    for line in text.splitlines():
        m = re.match(r"^(A\.|B\.|C\.|D\.)\s+(.+?)\s+([0-9.]+)\s+([0-9.]+)(?:\s+([0-9.]+|-))?$", line.strip())
        if m:
            rows[m.group(1)] = float(m.group(4))
    stage_targets = {
        "A.": ("Pi encode loop", 0.0),
        "B.": ("USB transfer", 0.0),
        "C.": ("Mac upres offline", 0.0),
        "D.": ("GVID pack", 24.0),
    }
    for key, (name, min_fps) in stage_targets.items():
        fps = rows.get(key)
        if fps is None:
            checks.append(Check("platform_perf", name, "FAIL", "missing stage row in UPRESABLE bench log"))
            continue
        status = "PASS" if fps >= min_fps else "FAIL"
        target = f" target>={min_fps:.2f}" if min_fps > 0 else " receipt-only"
        checks.append(Check("platform_perf", name, status, f"fps={fps:.2f}{target}"))
    return checks


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
    lab_sips_pipeline = "codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_sips_residual_ab8_sub10+demosaic=sips_via_gpr_tools"
    checks.append(check_preview_color_guard(lab_sips_pipeline))
    checks.append(check_preview_detail(
        "preview_detail",
        "Lab Chroma SIPS full PREVIEW gate",
        lab_sips_pipeline,
    ))
    checks.extend([
        check_file("preview_holdout", "28-image holdout manifest", "tests/quality_gates/preview_holdout_set.json"),
        check_file("preview_holdout", "holdout summary dashboard tool", "tests/quality_gates/summarize_preview_holdout.py"),
    ])
    checks.append(check_pipeline(
        "upresable",
        "production UPRESABLE",
        "codec=ml2_q3_dec2+cnn=bibo2x_ane_ml2_q3_dec2_diverse+demosaic=sips_via_gpr_tools",
    ))

    checks.extend([
        check_file("container_gvid", "wire format header", "source/lib/vc5_encoder/gpr_video_format.h"),
        check_file("container_gvid", "wire format implementation", "source/lib/vc5_encoder/gpr_video_format.c"),
        check_file("container_gvid", "CI format smoke", "source/app/test_video_format.c"),
        check_file("container_gvid", "GVID pack tool", "tools/gvid_pack.py"),
        check_file("container_gvid", "GVID pack smoke", "tools/test/test_gvid_pack.sh"),
        check_file("container_mov", "MOV compatibility pack tool", "tools/gpr2prores/gpr_mov_tool", require_tracked=False),
        check_file("container_mov", "MOV compatibility fixture recipe", "tools/test/make_gpraw_fixture.sh"),
        check_file("pi5_mission1", "Pi encoder benchmark", "tools/test/test_pi_encoder.sh"),
        check_file("pi5_mission1", "Pi-to-Mac UPRESABLE bench", "tools/test/bench_pi_to_mac_upresable.sh"),
        check_file("pi5_mission1", "Pi SD first-boot config", "tools/test/configure_pi_sd.sh"),
    ])

    checks.extend([
        check_capabilities_doc(),
        check_pi5_capture_receipt(),
        check_script_contains(
            "platform_perf",
            "Pi encoder regression covers 50MP decimate=2",
            "tools/test/test_pi_encoder.sh",
            ["50MP_DEC2", "[50MP_DEC2]=24"],
        ),
        check_script_contains(
            "platform_perf",
            "Mac sustained playback production threshold",
            "tools/test/test_sustained_playback.sh",
            ['FPS_WITH_CNN_MIN="${FPS_WITH_CNN_MIN:-24}"', 'FPS_NO_CNN_MIN="${FPS_NO_CNN_MIN:-24}"'],
        ),
    ])
    checks.extend(check_upresable_bench_receipt())

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
