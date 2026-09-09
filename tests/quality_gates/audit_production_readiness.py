#!/usr/bin/env python3
"""Production readiness audit for user-visible output families.

This is not a quality gate replacement. It is a checklist runner that verifies
the production surface has receipts or runnable scripts for each output family:
stills, video freeze quality, preview/chroma, UPRESABLE, containers, and the
Pi 5 / Mission 1 target path.

Default mode prints the matrix and exits 0 so it can be used while burning the
list down. Use --strict to make any FAIL row exit non-zero. Use
--require-mission1-strict24 when auditing the final Mission 1 production target;
that mode treats the current 20+ fps Pi proxy as insufficient until a
quality-preserving 12MP receipt proves the 24 fps target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO / "tests/quality_gates/runs"
REG = json.loads((REPO / "pipelines/registry.json").read_text())


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root()))
ARTIFACT_ROOT = Path(os.environ.get("GPR_ARTIFACT_ROOT", EXTERNAL_ROOT / "artifacts"))


@dataclass
class Check:
    area: str
    name: str
    status: str
    detail: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
    lpips = worst.get("lpips")
    lpips_s = f"{lpips:.4f}" if isinstance(lpips, (int, float)) else "n/a"
    return f"run={run.get('run_hash')} gates={run.get('gates_sha')} worst={worst.get('id')} lpips={lpips_s}"


def to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    if run:
        return Check(area, name, "PASS", run_summary(run))
    latest = latest_run_for_pipeline(pipeline)
    if latest:
        return Check(area, name, "FAIL", f"latest committed verdict={latest.get('verdict')} {run_summary(latest)}")
    return Check(area, name, "FAIL", "no committed PASS run")


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
    """Accept the detail item only when the current blocker is evidenced."""
    doc = REPO / "docs/RAW_SIGNAL_CNN_CANDIDATE_2026-06-05.md"
    if not doc.exists():
        return Check("preview_detail", "raw-signal detail blocker evidence", "FAIL", f"missing {doc.relative_to(REPO)}")
    if not git_tracked(doc):
        return Check("preview_detail", "raw-signal detail blocker evidence", "FAIL", f"untracked {doc.relative_to(REPO)}")

    required = {
        "source_sigma_analysis": ("1bd6fcf9583a44fa", True),
        "runtime_sigma_retrain": ("042cc4bdcf4dfe35", False),
        "iso_only_retrain": ("4f8231e47309d668", False),
    }
    missing = []
    bad = []
    deployable_worst_lpips: list[float] = []
    for label, (run_hash, allow_preview_pass) in required.items():
        run = tracked_run_by_hash(run_hash)
        if not run:
            missing.append(f"{label}:{run_hash}")
            continue
        if run.get("verdict") != "PASS" or run.get("ship_class") != "UPRESABLE":
            bad.append(f"{label}:{run_hash} verdict={run.get('verdict')} class={run.get('ship_class')}")
            continue
        z6693 = (run.get("images") or {}).get("Z8Z_6693")
        if not z6693:
            bad.append(f"{label}:{run_hash} missing Z8Z_6693 metrics")
            continue
        lpips = float(z6693.get("lpips", 999.0))
        ms = float(z6693.get("ms_ssim", 0.0))
        if not allow_preview_pass:
            deployable_worst_lpips.append(lpips)
            if lpips <= 0.15 and ms >= 0.95:
                bad.append(f"{label}:{run_hash} unexpectedly clears PREVIEW detail metrics")
    if missing:
        return Check("preview_detail", "raw-signal detail blocker evidence", "FAIL", "missing tracked runs " + ", ".join(missing))
    if bad:
        return Check("preview_detail", "raw-signal detail blocker evidence", "FAIL", "; ".join(bad))

    text = doc.read_text(errors="ignore")
    doc_needles = [
        "conditioning mismatch",
        "rendered quality remains unusable",
        "removing sigma channels does not solve the blocker",
        "larger/full-context",
        "teacher-distilled objective",
        "not production-ready",
    ]
    missing_doc = [s for s in doc_needles if s not in text]
    if missing_doc:
        return Check("preview_detail", "raw-signal detail blocker evidence", "FAIL", f"doc missing {missing_doc}")

    return Check(
        "preview_detail",
        "raw-signal detail blocker evidence",
        "PASS",
        "no deployable full PREVIEW pass; source-sigma analysis passes but is not runtime-valid, "
        f"runtime-valid retries fail rendered detail with max Z8Z_6693 LPIPS={max(deployable_worst_lpips):.4f}",
    )


def check_preview_detail(area: str, name: str, pipeline: str) -> Check:
    run = latest_pass_for_pipeline(pipeline)
    if run:
        return Check(area, name, "PASS", run_summary(run))
    return check_preview_detail_blocker_evidence()


def check_preview_variant_oracle_evidence() -> Check:
    tool = REPO / "tools/cnn/compare_preview_fullframe_variants.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "fullframe_variant_oracle_holdout28_v1"
        / "preview_fullframe_variant_oracle.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "full-frame variant oracle evidence", "FAIL", "missing tracked variant oracle tool")
    if not receipt.exists():
        return Check("preview_detail", "full-frame variant oracle evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = payload.get("oracle_summary") or {}
        complete_rows = int(payload.get("complete_row_count", 0))
        pass_count = int(summary.get("pass_count", 0))
        row_count = int(summary.get("count", 0))
        unsolved = int(payload.get("unsolved_count", 0))
        ok = (
            payload.get("schema") == "preview_fullframe_variant_oracle.v1"
            and complete_rows == 84
            and row_count == 84
            and pass_count == 63
            and unsolved == 21
        )
        return Check(
            "preview_detail",
            "full-frame variant oracle evidence",
            "PASS" if ok else "FAIL",
            f"oracle={pass_count}/{row_count} unsolved={unsolved} receipt={receipt}",
        )
    except Exception as exc:
        return Check("preview_detail", "full-frame variant oracle evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_exact_teacher_oracle_evidence() -> Check:
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "fullframe_exact_teacher_oracle_hard8_v1"
        / "preview_exact_teacher_oracle.json"
    )
    if not receipt.exists():
        return Check("preview_detail", "exact-crop teacher oracle evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = payload.get("oracle_summary") or {}
        pass_count = int(summary.get("pass_count", 0))
        row_count = int(summary.get("count", 0))
        unsolved = int(payload.get("unsolved_count", 0))
        ok = (
            payload.get("schema") == "preview_fullframe_variant_oracle.v1"
            and row_count == 24
            and pass_count == 16
            and unsolved == 8
        )
        return Check(
            "preview_detail",
            "exact-crop teacher oracle evidence",
            "PASS" if ok else "FAIL",
            f"oracle={pass_count}/{row_count} unsolved={unsolved} receipt={receipt}",
        )
    except Exception as exc:
        return Check("preview_detail", "exact-crop teacher oracle evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_post_refiner_negative_evidence() -> Check:
    root = ARTIFACT_ROOT / "preview_runtime_policy_20260606"
    baseline = root / "stitched_post_refiner_hard8_intersect_ov256_lf_v1" / "baseline_source_metrics.json"
    unconstrained = root / "stitched_post_refiner_hard8_intersect_ov256_lf_v1" / "preview_runtime_refiner.json"
    fullframe = root / "fullframe_tiled_v32_hard8_post_lf_v1" / "preview_scene_routed_fullframe.json"
    source_guarded = root / "stitched_post_refiner_hard8_intersect_ov256_direct_srcguard_v1" / "preview_runtime_refiner.json"
    missing = [str(path) for path in (baseline, unconstrained, fullframe, source_guarded) if not path.exists()]
    if missing:
        return Check("preview_detail", "stitched post-refiner negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        base_summary = json.loads(baseline.read_text()).get("summary") or {}
        uncon_summary = (json.loads(unconstrained.read_text()).get("summary") or {}).get("preview_runtime_policy") or {}
        full_summary = (json.loads(fullframe.read_text()).get("summary") or {}).get("preview_runtime_policy") or {}
        guarded_summary = (json.loads(source_guarded.read_text()).get("summary") or {}).get("preview_runtime_policy") or {}
        base_count = int(base_summary.get("count", 0))
        base_pass = int(base_summary.get("pass_count", 0))
        uncon_pass = int(uncon_summary.get("pass_count", 0))
        full_pass = int(full_summary.get("pass_count", 0))
        guarded_pass = int(guarded_summary.get("pass_count", 0))
        ok = (
            base_count == 394
            and base_pass == 13
            and uncon_pass == 33
            and int(uncon_summary.get("count", 0)) == 394
            and full_pass == 3
            and int(full_summary.get("count", 0)) == 24
            and guarded_pass == 15
            and int(guarded_summary.get("count", 0)) == 394
        )
        return Check(
            "preview_detail",
            "stitched post-refiner negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"dense baseline={base_pass}/{base_count}, unconstrained={uncon_pass}/394, "
                f"fullframe={full_pass}/24, source_guarded={guarded_pass}/394"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "stitched post-refiner negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_coord_field_negative_evidence() -> Check:
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "scene_expert_hard8_coord_field_globalstats_v1"
        / "preview_runtime_refiner.json"
    )
    if not receipt.exists():
        return Check("preview_detail", "coordinate-field negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = (payload.get("summary") or {}).get("preview_runtime_policy") or {}
        checkpoint = payload.get("training") or {}
        count = int(summary.get("count", 0))
        pass_count = int(summary.get("pass_count", -1))
        worst_lpips = float(summary.get("worst_lpips", 0.0))
        ok = (
            count == 96
            and pass_count == 0
            and worst_lpips > 0.60
            and checkpoint.get("checkpoint_sha256")
        )
        return Check(
            "preview_detail",
            "coordinate-field negative evidence",
            "PASS" if ok else "FAIL",
            f"coord_field={pass_count}/{count} worst_lpips={worst_lpips:.4f} receipt={receipt}",
        )
    except Exception as exc:
        return Check("preview_detail", "coordinate-field negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_fullimage_lf_negative_evidence() -> Check:
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "fullimage_lf_refiner_hard8_capacity_v2"
        / "preview_fullimage_lf_refiner.json"
    )
    if not receipt.exists():
        return Check("preview_detail", "full-image LF negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summaries = {str(row.get("variant")): row for row in payload.get("summary") or []}
        refined = summaries.get("fullimage_lf_refined") or {}
        oracle = summaries.get("ref_lowfield_oracle") or {}
        checkpoint = (payload.get("model") or {}).get("checkpoint_sha256")
        contract = payload.get("render_contract") or {}
        ok = (
            payload.get("schema") == "preview_fullimage_lf_refiner_receipt.v1"
            and int(refined.get("count", 0)) == 24
            and int(refined.get("pass_count", -1)) == 0
            and int(oracle.get("count", 0)) == 24
            and int(oracle.get("pass_count", -1)) == 0
            and float(oracle.get("worst_lpips", 0.0)) > 0.60
            and checkpoint
            and "ref_lowfield_oracle" in contract.get("oracle_variants_not_allowed_for_production", [])
        )
        return Check(
            "preview_detail",
            "full-image LF negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"refined={int(refined.get('pass_count', -1))}/{int(refined.get('count', 0))}, "
                f"oracle={int(oracle.get('pass_count', -1))}/{int(oracle.get('count', 0))}, "
                f"oracle_worst_lpips={float(oracle.get('worst_lpips', 0.0)):.4f} receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "full-image LF negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_frequency_oracle_evidence() -> Check:
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "fullimage_frequency_oracle_hard8_v1"
        / "preview_fullimage_frequency_oracle.json"
    )
    if not receipt.exists():
        return Check("preview_detail", "full-image frequency oracle evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summaries = {str(row.get("variant")): row for row in payload.get("summary") or []}
        exact = summaries.get("ref_exact_oracle") or {}
        best_band = summaries.get("ref_low_source_high_s1") or {}
        ref_high = summaries.get("source_low_ref_high_s4") or {}
        ok = (
            payload.get("schema") == "preview_fullimage_frequency_oracle.v1"
            and int(exact.get("pass_count", -1)) == 24
            and int(best_band.get("pass_count", -1)) == 14
            and int(best_band.get("count", 0)) == 24
            and int(ref_high.get("pass_count", -1)) == 5
            and "ref_exact_oracle" in payload.get("oracle_variants_not_allowed_for_production", [])
        )
        return Check(
            "preview_detail",
            "full-image frequency oracle evidence",
            "PASS" if ok else "FAIL",
            (
                f"exact={int(exact.get('pass_count', -1))}/24, "
                f"ref_low_source_high_s1={int(best_band.get('pass_count', -1))}/24, "
                f"source_low_ref_high_s4={int(ref_high.get('pass_count', -1))}/24 receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "full-image frequency oracle evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_context_generator_negative_evidence() -> Check:
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "context768_center512_generator_hard8_fit_v1"
        / "preview_runtime_refiner.json"
    )
    if not receipt.exists():
        return Check("preview_detail", "context generator negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = (payload.get("summary") or {}).get("preview_runtime_policy") or {}
        training = payload.get("training") or {}
        contract = payload.get("runtime_contract") or {}
        ok = (
            payload.get("schema") == "preview_runtime_refiner_train_receipt.v1"
            and int(summary.get("count", 0)) == 24
            and int(summary.get("pass_count", -1)) == 0
            and float(summary.get("worst_lpips", 0.0)) > 0.60
            and training.get("checkpoint_sha256")
            and contract.get("render_inputs")
            and "REF image content" in contract.get("forbidden_inputs", [])
        )
        return Check(
            "preview_detail",
            "context generator negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"generator={int(summary.get('pass_count', -1))}/{int(summary.get('count', 0))}, "
                f"worst_lpips={float(summary.get('worst_lpips', 0.0)):.4f}, "
                f"median_lpips={float(summary.get('median_lpips', 0.0)):.4f} receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "context generator negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_multi_origin_tile_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/evaluate_preview_scene_routed_fullframe.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260612"
        / "fullframe_multi_offset_v32_z8z6680_t512_o256_v1"
        / "preview_scene_routed_fullframe.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "multi-origin tile negative evidence", "FAIL", "missing tracked full-frame evaluator")
    tool_text = tool.read_text(errors="ignore")
    if "--tile-offset" not in tool_text or "tile_offsets" not in tool_text:
        return Check("preview_detail", "multi-origin tile negative evidence", "FAIL", "full-frame evaluator missing tile offset support")
    if not receipt.exists():
        return Check("preview_detail", "multi-origin tile negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = (payload.get("summary") or {}).get("preview_runtime_policy") or {}
        contract = payload.get("runtime_contract") or {}
        rows = payload.get("rows") or []
        timing = payload.get("timing_summary") or {}
        offsets = contract.get("tile_offsets") or []
        ok = (
            payload.get("schema") == "preview_scene_routed_fullframe_receipt.v1"
            and len(offsets) == 4
            and int(summary.get("count", 0)) == 3
            and int(summary.get("pass_count", -1)) == 0
            and 0.20 < float(summary.get("worst_lpips", 0.0)) < 0.30
            and 5.0 < float(summary.get("worst_dE2000_mean", 0.0)) < 6.0
            and rows
            and float(timing.get("runtime_no_ref_wall_ms_avg", 0.0)) > 0.0
            and "REF image content" in set(contract.get("forbidden_inputs") or [])
        )
        return Check(
            "preview_detail",
            "multi-origin tile negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"multi_origin={int(summary.get('pass_count', -1))}/{int(summary.get('count', 0))}, "
                f"worst_lpips={float(summary.get('worst_lpips', 0.0)):.4f}, "
                f"worst_dE={float(summary.get('worst_dE2000_mean', 0.0)):.2f}, "
                f"runtime={float(timing.get('runtime_no_ref_wall_ms_avg', 0.0)) / 1000.0:.2f}s "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "multi-origin tile negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_source_frequency_negative_evidence() -> Check:
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260612"
        / "source_frequency_post_hard8_w40_v1"
        / "preview_runtime_refiner.json"
    )
    if not receipt.exists():
        return Check("preview_detail", "source-frequency post negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = (payload.get("summary") or {}).get("preview_runtime_policy") or {}
        contract = payload.get("runtime_contract") or {}
        training = payload.get("training") or {}
        ok = (
            payload.get("schema") == "preview_runtime_refiner_train_receipt.v1"
            and int(summary.get("count", 0)) == 24
            and int(summary.get("pass_count", -1)) == 3
            and float(summary.get("worst_lpips", 0.0)) > 0.50
            and float(summary.get("worst_dE2000_mean", 0.0)) > 8.0
            and contract.get("source_frequency_planes") == "low_high"
            and int(contract.get("input_channels", 0)) == 15
            and training.get("checkpoint_sha256")
        )
        return Check(
            "preview_detail",
            "source-frequency post negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"source_freq={int(summary.get('pass_count', -1))}/{int(summary.get('count', 0))}, "
                f"worst_lpips={float(summary.get('worst_lpips', 0.0)):.4f}, "
                f"worst_dE={float(summary.get('worst_dE2000_mean', 0.0)):.2f}, "
                f"input_channels={int(contract.get('input_channels', 0))} receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "source-frequency post negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_fullimage_band_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_fullimage_band_refiner.py"
    hard8_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260612"
        / "fullimage_band_refiner_hard8_from_v32_capacity_v1"
        / "preview_fullimage_band_refiner.json"
    )
    smoke_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260612"
        / "fullimage_band_refiner_z8z6680_from_multioffset_smoke_v1"
        / "preview_fullimage_band_refiner.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "full-image band negative evidence", "FAIL", "missing tracked full-image band refiner")
    tool_text = tool.read_text(errors="ignore")
    if "--source-fullframe-receipt" not in tool_text or "ref_lowfield_residual" not in tool_text:
        return Check("preview_detail", "full-image band negative evidence", "FAIL", "tool missing receipt-source or lowfield oracle support")
    missing = [str(path) for path in (hard8_receipt, smoke_receipt) if not path.exists()]
    if missing:
        return Check("preview_detail", "full-image band negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        hard8 = json.loads(hard8_receipt.read_text())
        smoke = json.loads(smoke_receipt.read_text())
        hard8_summary = {row["variant"]: row for row in hard8.get("summary", [])}
        smoke_summary = {row["variant"]: row for row in smoke.get("summary", [])}
        hard8_source = hard8_summary.get("source_baseline") or {}
        hard8_ref_low = hard8_summary.get("ref_lowfield_residual") or {}
        hard8_generated = hard8_summary.get("generated_lowfield_residual") or {}
        smoke_source = smoke_summary.get("source_baseline") or {}
        smoke_ref_low = smoke_summary.get("ref_lowfield_residual") or {}
        ok = (
            hard8.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and smoke.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and hard8.get("source_fullframe_receipt")
            and smoke.get("source_fullframe_receipt")
            and int(hard8_source.get("count", 0)) == 24
            and int(hard8_source.get("pass_count", -1)) == 4
            and int(hard8_ref_low.get("pass_count", -1)) == 4
            and int(hard8_generated.get("pass_count", -1)) == 0
            and float(hard8_generated.get("worst_dE2000_mean", 0.0)) > 20.0
            and int(smoke_source.get("count", 0)) == 3
            and int(smoke_source.get("pass_count", -1)) == 0
            and int(smoke_ref_low.get("pass_count", -1)) == 0
            and float(smoke_ref_low.get("worst_lpips", 0.0)) > 0.25
        )
        return Check(
            "preview_detail",
            "full-image band negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"hard8_source={int(hard8_source.get('pass_count', -1))}/24, "
                f"hard8_ref_low={int(hard8_ref_low.get('pass_count', -1))}/24, "
                f"hard8_generated={int(hard8_generated.get('pass_count', -1))}/24, "
                f"smoke_ref_low={int(smoke_ref_low.get('pass_count', -1))}/3 "
                f"receipt={hard8_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "full-image band negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_highres_fullimage_band_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_fullimage_band_refiner.py"
    w2048_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_refiner_hard8_w2048_capacity_v1"
        / "preview_fullimage_band_refiner.json"
    )
    w4096_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_refiner_hard8_w4096_narrow_v1"
        / "preview_fullimage_band_refiner.json"
    )
    stats_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_refiner_hard8_w4096_globalstats_v1"
        / "preview_fullimage_band_refiner.json"
    )
    crop_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_refiner_hard8_w4096_croploss_best_v2"
        / "preview_fullimage_band_refiner.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "high-res full-image band negative evidence", "FAIL", "missing tracked full-image band refiner")
    tool_text = tool.read_text(errors="ignore")
    if "xy_global_color_stats" not in tool_text or "source_rgb_global_mean_std" not in tool_text:
        return Check("preview_detail", "high-res full-image band negative evidence", "FAIL", "tool missing source-global-stat conditioning contract")
    if "crop_loss_weight" not in tool_text or "best_step" not in tool_text:
        return Check("preview_detail", "high-res full-image band negative evidence", "FAIL", "tool missing crop-loss/best-step receipt contract")
    missing = [str(path) for path in (w2048_receipt, w4096_receipt, stats_receipt, crop_receipt) if not path.exists()]
    if missing:
        return Check("preview_detail", "high-res full-image band negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        w2048 = json.loads(w2048_receipt.read_text())
        w4096 = json.loads(w4096_receipt.read_text())
        stats = json.loads(stats_receipt.read_text())
        crop = json.loads(crop_receipt.read_text())

        def summary(payload: dict[str, Any], variant: str) -> dict[str, Any]:
            return {row.get("variant"): row for row in payload.get("summary", [])}.get(variant) or {}

        w2048_ref = summary(w2048, "ref_lowfield_residual")
        w2048_generated = summary(w2048, "generated_lowfield_residual")
        w4096_ref = summary(w4096, "ref_low_plus_source_high_s1")
        w4096_generated = summary(w4096, "generated_low_plus_source_high_s1")
        stats_generated = summary(stats, "generated_low_plus_source_high_s1")
        crop_generated = summary(crop, "generated_low_plus_source_high_s4")
        stats_contract = stats.get("render_contract") or {}
        stats_model = stats.get("model") or {}
        crop_training = crop.get("training") or {}
        crop_timing = crop.get("timing") or {}
        ok = (
            w2048.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and w4096.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and stats.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and crop.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and int(w2048_ref.get("pass_count", -1)) == 7
            and int(w2048_generated.get("pass_count", -1)) == 0
            and int(w4096_ref.get("pass_count", -1)) == 18
            and int(w4096_generated.get("pass_count", -1)) == 0
            and int(stats_generated.get("pass_count", -1)) == 0
            and float(stats_generated.get("worst_dE2000_mean", 0.0)) > 20.0
            and int(crop_generated.get("count", 0)) == 24
            and int(crop_generated.get("pass_count", -1)) == 0
            and float(crop_generated.get("worst_dE2000_mean", 0.0)) > 20.0
            and float(crop_training.get("crop_loss_weight", 0.0)) >= 20.0
            and float(crop_timing.get("best_step", 0.0)) > 0.0
            and stats_contract.get("conditioning") == "xy_global_color_stats"
            and "source_rgb_global_mean_std" in (stats_contract.get("render_time_inputs") or [])
            and int(stats_model.get("in_channels", 0)) == 11
        )
        return Check(
            "preview_detail",
            "high-res full-image band negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"w2048_ref={int(w2048_ref.get('pass_count', -1))}/24, "
                f"w2048_generated={int(w2048_generated.get('pass_count', -1))}/24, "
                f"w4096_ref={int(w4096_ref.get('pass_count', -1))}/24, "
                f"w4096_generated={int(w4096_generated.get('pass_count', -1))}/24, "
                f"globalstats_generated={int(stats_generated.get('pass_count', -1))}/24, "
                f"crop_loss_generated={int(crop_generated.get('pass_count', -1))}/24 "
                f"receipt={crop_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "high-res full-image band negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_residual_fullimage_band_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_fullimage_band_refiner.py"
    w1536_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_residual_smoke_0026_6680_w1536_v1"
        / "preview_fullimage_band_refiner.json"
    )
    w4096_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_residual_smoke_0026_6680_w4096_v1"
        / "preview_fullimage_band_refiner.json"
    )
    unet1536_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_residual_unet_smoke_0026_6680_w1536_v1"
        / "preview_fullimage_band_refiner.json"
    )
    unet2048_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_band_residual_unet_smoke_0026_6680_w2048_v1"
        / "preview_fullimage_band_refiner.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "residual full-image band negative evidence", "FAIL", "missing tracked full-image band refiner")
    tool_text = tool.read_text(errors="ignore")
    if "ResidualFullImageBandGenerator" not in tool_text or "ResidualUNetFullImageBandGenerator" not in tool_text or "--architecture" not in tool_text:
        return Check("preview_detail", "residual full-image band negative evidence", "FAIL", "tool missing residual architecture contract")
    missing = [str(path) for path in (w1536_receipt, w4096_receipt, unet1536_receipt, unet2048_receipt) if not path.exists()]
    if missing:
        return Check("preview_detail", "residual full-image band negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        w1536 = json.loads(w1536_receipt.read_text())
        w4096 = json.loads(w4096_receipt.read_text())
        unet1536 = json.loads(unet1536_receipt.read_text())
        unet2048 = json.loads(unet2048_receipt.read_text())

        def summary(payload, variant: str):
            return {row.get("variant"): row for row in payload.get("summary", [])}.get(variant) or {}

        w1536_generated = summary(w1536, "generated_low_plus_source_high_s4")
        w1536_source = summary(w1536, "source_baseline")
        w4096_source = summary(w4096, "source_baseline")
        w4096_generated = summary(w4096, "generated_low_plus_source_high_s1")
        w4096_ref = summary(w4096, "ref_low_plus_source_high_s1")
        unet1536_generated = summary(unet1536, "generated_low_plus_source_high_s4")
        unet2048_generated = summary(unet2048, "generated_low_plus_source_high_s4")
        w1536_model = w1536.get("model") or {}
        w4096_model = w4096.get("model") or {}
        unet1536_model = unet1536.get("model") or {}
        unet2048_model = unet2048.get("model") or {}
        w4096_contract = w4096.get("render_contract") or {}
        ok = (
            w1536.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and w4096.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and unet1536.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and unet2048.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and w1536_model.get("architecture") == "residual"
            and w4096_model.get("architecture") == "residual"
            and unet1536_model.get("architecture") == "residual_unet"
            and unet2048_model.get("architecture") == "residual_unet"
            and int(w1536_model.get("model_width", 0)) == 1536
            and int(w4096_model.get("model_width", 0)) == 4096
            and int(unet1536_model.get("model_width", 0)) == 1536
            and int(unet2048_model.get("model_width", 0)) == 2048
            and int(w4096_model.get("in_channels", 0)) == 11
            and w1536_model.get("checkpoint_sha256")
            and w4096_model.get("checkpoint_sha256")
            and unet1536_model.get("checkpoint_sha256")
            and unet2048_model.get("checkpoint_sha256")
            and "source_rgb_global_mean_std" in (w4096_contract.get("render_time_inputs") or [])
            and "ref_rgb" in (w4096_contract.get("forbidden_render_time_inputs") or [])
            and int(w1536_source.get("count", 0)) == 6
            and int(w1536_source.get("pass_count", -1)) == 0
            and int(w1536_generated.get("pass_count", -1)) == 0
            and float(w1536_generated.get("worst_lpips", 0.0)) > 0.64
            and int(unet1536_generated.get("pass_count", -1)) == 0
            and float(unet1536_generated.get("worst_lpips", 0.0)) > 0.64
            and int(unet2048_generated.get("pass_count", -1)) == 0
            and float(unet2048_generated.get("worst_lpips", 0.0)) > 0.64
            and int(w4096_source.get("count", 0)) == 6
            and int(w4096_source.get("pass_count", -1)) == 0
            and int(w4096_generated.get("pass_count", -1)) == 0
            and int(w4096_ref.get("pass_count", -1)) == 0
            and float(w4096_ref.get("worst_lpips", 1.0)) < float(w4096_generated.get("worst_lpips", 0.0))
            and float(w4096_generated.get("worst_lpips", 0.0)) > float(w4096_source.get("worst_lpips", 0.0))
        )
        return Check(
            "preview_detail",
            "residual full-image band negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"w1536_generated={int(w1536_generated.get('pass_count', -1))}/6 "
                f"lpips={float(w1536_generated.get('worst_lpips', 999.0)):.4f}; "
                f"w4096_source={int(w4096_source.get('pass_count', -1))}/6 "
                f"lpips={float(w4096_source.get('worst_lpips', 999.0)):.4f}; "
                f"w4096_generated={int(w4096_generated.get('pass_count', -1))}/6 "
                f"lpips={float(w4096_generated.get('worst_lpips', 999.0)):.4f}; "
                f"w4096_ref={int(w4096_ref.get('pass_count', -1))}/6 "
                f"lpips={float(w4096_ref.get('worst_lpips', 999.0)):.4f}; "
                f"unet2048={int(unet2048_generated.get('pass_count', -1))}/6 "
                f"lpips={float(unet2048_generated.get('worst_lpips', 999.0)):.4f} "
                f"receipt={unet2048_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "residual full-image band negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_fullimage_affine_oracle_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/probe_preview_fullimage_affine_oracle.py"
    local_tool = REPO / "tools/cnn/probe_preview_fullimage_local_affine_oracle.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_affine_oracle_hard8_v1"
        / "preview_fullimage_affine_oracle.json"
    )
    local_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullimage_local_affine_oracle_hard8_v1"
        / "preview_fullimage_local_affine_oracle.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "full-image affine oracle negative evidence", "FAIL", "missing tracked affine oracle tool")
    if not local_tool.exists() or not git_tracked(local_tool):
        return Check("preview_detail", "full-image affine oracle negative evidence", "FAIL", "missing tracked local affine oracle tool")
    tool_text = tool.read_text(errors="ignore")
    if "oracle_uses_ref_to_fit_affine" not in tool_text or "production_allowed" not in tool_text:
        return Check("preview_detail", "full-image affine oracle negative evidence", "FAIL", "tool missing diagnostic-only contract")
    local_tool_text = local_tool.read_text(errors="ignore")
    if "oracle_uses_ref_to_fit_local_affine" not in local_tool_text or "production_allowed" not in local_tool_text:
        return Check("preview_detail", "full-image affine oracle negative evidence", "FAIL", "local tool missing diagnostic-only contract")
    if not receipt.exists():
        return Check("preview_detail", "full-image affine oracle negative evidence", "FAIL", f"missing {receipt}")
    if not local_receipt.exists():
        return Check("preview_detail", "full-image affine oracle negative evidence", "FAIL", f"missing {local_receipt}")
    try:
        payload = json.loads(receipt.read_text())
        local_payload = json.loads(local_receipt.read_text())
        variants = {row.get("variant"): row for row in payload.get("summary", [])}
        affine_4096 = variants.get("affine_field_oracle_w4096") or {}
        affine_6144 = variants.get("affine_field_oracle_w6144") or {}
        source_high = variants.get("affine_field_source_high_s1_w4096") or {}
        contract = payload.get("render_contract") or {}
        local_variants = {row.get("variant"): row for row in local_payload.get("summary", [])}
        local_6144 = local_variants.get("local_affine_grid8_w6144") or {}
        local_4096 = local_variants.get("local_affine_grid8_w4096") or {}
        local_contract = local_payload.get("render_contract") or {}
        ok = (
            payload.get("schema") == "preview_fullimage_affine_oracle.v1"
            and local_payload.get("schema") == "preview_fullimage_local_affine_oracle.v1"
            and contract.get("oracle_uses_ref_to_fit_affine") is True
            and local_contract.get("oracle_uses_ref_to_fit_local_affine") is True
            and contract.get("production_allowed") is False
            and local_contract.get("production_allowed") is False
            and int(affine_4096.get("count", 0)) == 24
            and int(affine_4096.get("pass_count", -1)) == 0
            and int(affine_6144.get("count", 0)) == 24
            and int(affine_6144.get("pass_count", -1)) == 0
            and int(source_high.get("count", 0)) == 24
            and int(source_high.get("pass_count", -1)) == 0
            and int(local_4096.get("count", 0)) == 24
            and int(local_4096.get("pass_count", -1)) == 0
            and int(local_6144.get("count", 0)) == 24
            and int(local_6144.get("pass_count", -1)) == 0
            and float(affine_6144.get("worst_lpips", 0.0)) > 0.6
            and float(affine_6144.get("worst_dE2000_mean", 0.0)) > 10.0
            and float(local_6144.get("worst_lpips", 0.0)) > 0.55
            and float(local_6144.get("worst_dE2000_mean", 0.0)) > 9.0
        )
        return Check(
            "preview_detail",
            "full-image affine oracle negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"affine4096={int(affine_4096.get('pass_count', -1))}/24, "
                f"affine6144={int(affine_6144.get('pass_count', -1))}/24, "
                f"affine_source_high={int(source_high.get('pass_count', -1))}/24, "
                f"local6144={int(local_6144.get('pass_count', -1))}/24 "
                f"receipt={local_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "full-image affine oracle negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_source_representation_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/probe_preview_source_representation.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "source_representation_hard8_v1"
        / "preview_source_representation_probe.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "source representation negative evidence", "FAIL", "missing tracked source representation probe")
    tool_text = tool.read_text(errors="ignore")
    if "uses_ref_at_render_time" not in tool_text or "clean_bundle_frame_tiff" not in tool_text:
        return Check("preview_detail", "source representation negative evidence", "FAIL", "tool missing runtime-source contract or frame variant")
    if not receipt.exists():
        return Check("preview_detail", "source representation negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        variants = {row.get("variant"): row for row in payload.get("summary", [])}
        sips = variants.get("editable_dng_sips_w6144") or {}
        frame = variants.get("clean_bundle_frame_tiff_fullres") or {}
        rawpy = variants.get("editable_dng_rawpy_camera_auto_w6144") or {}
        contract = payload.get("render_contract") or {}
        ok = (
            payload.get("schema") == "preview_source_representation_probe.v1"
            and contract.get("uses_ref_at_render_time") is False
            and contract.get("ref_usage") == "scoring only"
            and int(sips.get("count", 0)) == 24
            and int(sips.get("pass_count", -1)) == 0
            and int(frame.get("count", 0)) == 24
            and int(frame.get("pass_count", -1)) == 0
            and int(rawpy.get("count", 0)) == 24
            and int(rawpy.get("pass_count", -1)) == 0
            and float(sips.get("worst_lpips", 0.0)) > 0.6
            and float(frame.get("worst_lpips", 0.0)) > float(sips.get("worst_lpips", 1.0))
            and float(rawpy.get("worst_lpips", 0.0)) > float(sips.get("worst_lpips", 1.0))
        )
        return Check(
            "preview_detail",
            "source representation negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"sips6144={int(sips.get('pass_count', -1))}/24, "
                f"frame={int(frame.get('pass_count', -1))}/24, "
                f"rawpy_auto6144={int(rawpy.get('pass_count', -1))}/24 "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "source representation negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_residual_feature_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/probe_preview_fullimage_residual_features.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "residual_features_hard8_w4096_v1"
        / "preview_fullimage_residual_features.json"
    )
    knn_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "residual_features_knn_hard8_w2048_v1"
        / "preview_fullimage_residual_features.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "source-feature residual negative evidence", "FAIL", "missing tracked residual feature probe")
    tool_text = tool.read_text(errors="ignore")
    if "oracle_uses_ref_to_fit_residual" not in tool_text or "runtime_apply_features_are_source_only" not in tool_text:
        return Check("preview_detail", "source-feature residual negative evidence", "FAIL", "tool missing oracle/runtime-source contract")
    missing = [str(path) for path in (receipt, knn_receipt) if not path.exists()]
    if missing:
        return Check("preview_detail", "source-feature residual negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        payload = json.loads(receipt.read_text())
        knn_payload = json.loads(knn_receipt.read_text())
        variants = {row.get("variant"): row for row in payload.get("summary", [])}
        baseline = variants.get("source_baseline_w4096") or {}
        residual = variants.get("source_feature_residual_ridge_w4096") or {}
        contract = payload.get("render_contract") or {}
        knn_variants = {row.get("variant"): row for row in knn_payload.get("summary", [])}
        knn_baseline = knn_variants.get("source_baseline_w2048") or {}
        knn_residual = knn_variants.get("source_feature_residual_knn_k8_w2048") or {}
        knn_contract = knn_payload.get("render_contract") or {}
        ok = (
            payload.get("schema") == "preview_fullimage_residual_features.v1"
            and knn_payload.get("schema") == "preview_fullimage_residual_features.v1"
            and contract.get("oracle_uses_ref_to_fit_residual") is True
            and knn_contract.get("oracle_uses_ref_to_fit_residual") is True
            and contract.get("production_allowed") is False
            and knn_contract.get("production_allowed") is False
            and contract.get("runtime_apply_features_are_source_only") is True
            and knn_contract.get("runtime_apply_features_are_source_only") is True
            and int(baseline.get("count", 0)) == 24
            and int(baseline.get("pass_count", -1)) == 0
            and int(residual.get("count", 0)) == 24
            and int(residual.get("pass_count", -1)) == 0
            and int(knn_baseline.get("count", 0)) == 24
            and int(knn_baseline.get("pass_count", -1)) == 0
            and int(knn_residual.get("count", 0)) == 24
            and int(knn_residual.get("pass_count", -1)) == 0
            and float(residual.get("worst_dE2000_mean", 0.0)) < float(baseline.get("worst_dE2000_mean", 999.0))
            and float(residual.get("worst_lpips", 0.0)) > float(baseline.get("worst_lpips", 0.0))
            and float(residual.get("worst_lpips", 0.0)) > 0.70
            and float(knn_residual.get("worst_dE2000_mean", 0.0)) < float(knn_baseline.get("worst_dE2000_mean", 999.0))
            and float(knn_residual.get("worst_lpips", 0.0)) > 0.75
        )
        return Check(
            "preview_detail",
            "source-feature residual negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"baseline={int(baseline.get('pass_count', -1))}/24 "
                f"lpips={float(baseline.get('worst_lpips', 999.0)):.4f} "
                f"dE={float(baseline.get('worst_dE2000_mean', 999.0)):.2f}; "
                f"residual={int(residual.get('pass_count', -1))}/24 "
                f"lpips={float(residual.get('worst_lpips', 999.0)):.4f} "
                f"dE={float(residual.get('worst_dE2000_mean', 999.0)):.2f}; "
                f"knn={int(knn_residual.get('pass_count', -1))}/24 "
                f"lpips={float(knn_residual.get('worst_lpips', 999.0)):.4f} "
                f"dE={float(knn_residual.get('worst_dE2000_mean', 999.0)):.2f} "
                f"receipt={knn_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "source-feature residual negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_dense_warp_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/probe_preview_fullimage_dense_warp_oracle.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "dense_warp_hard8_w1024_v1"
        / "preview_fullimage_dense_warp_oracle.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "dense-warp oracle negative evidence", "FAIL", "missing tracked dense-warp oracle")
    tool_text = tool.read_text(errors="ignore")
    if "uses_ref_to_estimate_dense_flow" not in tool_text or "production_allowed" not in tool_text:
        return Check("preview_detail", "dense-warp oracle negative evidence", "FAIL", "tool missing diagnostic-only contract")
    if not receipt.exists():
        return Check("preview_detail", "dense-warp oracle negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        variants = {row.get("variant"): row for row in payload.get("summary", [])}
        baseline = variants.get("source_baseline_w1024") or {}
        tvl1_plus = variants.get("dense_warp_tvl1_plus_w1024") or {}
        ilk_plus = variants.get("dense_warp_ilk_plus_w1024") or {}
        contract = payload.get("render_contract") or {}
        ok = (
            payload.get("schema") == "preview_fullimage_dense_warp_oracle.v1"
            and contract.get("uses_ref_to_estimate_dense_flow") is True
            and contract.get("production_allowed") is False
            and int(baseline.get("count", 0)) == 24
            and int(baseline.get("pass_count", -1)) == 0
            and int(tvl1_plus.get("count", 0)) == 24
            and int(tvl1_plus.get("pass_count", -1)) == 0
            and int(ilk_plus.get("count", 0)) == 24
            and int(ilk_plus.get("pass_count", -1)) == 0
            and float(tvl1_plus.get("worst_ms_ssim", 0.0)) > float(baseline.get("worst_ms_ssim", 999.0))
            and float(tvl1_plus.get("worst_y_psnr", 0.0)) > float(baseline.get("worst_y_psnr", 999.0))
            and float(tvl1_plus.get("worst_lpips", 0.0)) > 0.90
        )
        return Check(
            "preview_detail",
            "dense-warp oracle negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"baseline={int(baseline.get('pass_count', -1))}/24 "
                f"lpips={float(baseline.get('worst_lpips', 999.0)):.4f}; "
                f"tvl1={int(tvl1_plus.get('pass_count', -1))}/24 "
                f"lpips={float(tvl1_plus.get('worst_lpips', 999.0)):.4f} "
                f"MS={float(tvl1_plus.get('worst_ms_ssim', 999.0)):.4f}; "
                f"ilk={int(ilk_plus.get('pass_count', -1))}/24 "
                f"lpips={float(ilk_plus.get('worst_lpips', 999.0)):.4f} "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "dense-warp oracle negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_alignment_oracle_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/probe_preview_fullframe_alignment_oracle.py"
    hard8_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "alignment_oracle_hard8_v32_coarse_v1"
        / "preview_fullframe_alignment_oracle.json"
    )
    smoke_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "alignment_oracle_z8z6680_multioffset_v1"
        / "preview_fullframe_alignment_oracle.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "alignment oracle negative evidence", "FAIL", "missing tracked alignment oracle")
    tool_text = tool.read_text(errors="ignore")
    if "uses_ref_to_select_alignment" not in tool_text or "production_allowed" not in tool_text:
        return Check("preview_detail", "alignment oracle negative evidence", "FAIL", "tool missing diagnostic-only contract")
    missing = [str(path) for path in (hard8_receipt, smoke_receipt) if not path.exists()]
    if missing:
        return Check("preview_detail", "alignment oracle negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        hard8 = json.loads(hard8_receipt.read_text())
        smoke = json.loads(smoke_receipt.read_text())
        hard8_summary = hard8.get("summary") or {}
        smoke_summary = smoke.get("summary") or {}
        hard8_contract = hard8.get("render_contract") or {}
        smoke_contract = smoke.get("render_contract") or {}
        ok = (
            hard8.get("schema") == "preview_fullframe_alignment_oracle.v1"
            and smoke.get("schema") == "preview_fullframe_alignment_oracle.v1"
            and hard8_contract.get("uses_ref_to_select_alignment") is True
            and hard8_contract.get("production_allowed") is False
            and smoke_contract.get("uses_ref_to_select_alignment") is True
            and smoke_contract.get("production_allowed") is False
            and int(hard8_summary.get("base_count", 0)) == 24
            and int(hard8_summary.get("base_pass_count", -1)) == 4
            and int(hard8_summary.get("oracle_pass_count", -1)) == 4
            and int(hard8_summary.get("rows_improved_pass", -1)) == 0
            and float(hard8_summary.get("oracle_worst_dE2000_mean", 0.0)) > 9.0
            and int(smoke_summary.get("base_count", 0)) == 3
            and int(smoke_summary.get("base_pass_count", -1)) == 0
            and int(smoke_summary.get("oracle_pass_count", -1)) == 0
            and int(smoke_summary.get("rows_improved_pass", -1)) == 0
            and float(smoke_summary.get("oracle_worst_lpips", 0.0)) > 0.25
        )
        return Check(
            "preview_detail",
            "alignment oracle negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"hard8_base={int(hard8_summary.get('base_pass_count', -1))}/24, "
                f"hard8_oracle={int(hard8_summary.get('oracle_pass_count', -1))}/24, "
                f"hard8_improved={int(hard8_summary.get('rows_improved_pass', -1))}, "
                f"smoke_oracle={int(smoke_summary.get('oracle_pass_count', -1))}/3 "
                f"receipt={hard8_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "alignment oracle negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_fullframe_failure_mode_audit() -> Check:
    tool = REPO / "tools/cnn/audit_preview_fullframe_failure_modes.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "fullframe_failure_mode_audit_v4"
        / "preview_fullframe_failure_mode_audit.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "full-frame failure-mode audit", "FAIL", "missing tracked audit tool")
    if not receipt.exists():
        return Check("preview_detail", "full-frame failure-mode audit", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = payload.get("summary") or {}
        variants = {row.get("variant"): row for row in payload.get("variant_summary", [])}
        crop = variants.get("crop_holdout_v32") or {}
        fullframe = variants.get("fullframe_scene_gated_84") or {}
        contract = variants.get("hard8_contract:arbitrary_tiled") or {}
        exact = variants.get("hard8_contract:exact_manifest_crop") or {}
        teacher_distill = variants.get("hard8_exact_teacher_distill:output_vs_ref") or {}
        context_unet = variants.get("hard8_stitched_context_unet") or {}
        ref_field_3072 = variants.get("hard8_resolution_oracle_lowmid:ref_field_oracle_w3072") or {}
        ref_field_4096 = variants.get("hard8_resolution_oracle_high:ref_field_oracle_w4096") or {}
        ref_field_6144 = variants.get("hard8_resolution_oracle_high:ref_field_oracle_w6144") or {}
        ref_field_full = variants.get("hard8_resolution_oracle_high:ref_field_oracle_w8280") or {}
        residual_band = variants.get("hard8_band_residual_w4096:generated_low_plus_source_high_s1") or {}
        residual_unet = variants.get("hard8_band_residual_unet_w2048:generated_low_plus_source_high_s4") or {}
        ok = (
            payload.get("schema") == "preview_fullframe_failure_mode_audit.v1"
            and int(summary.get("normalized_row_count", 0)) >= 2043
            and int(summary.get("variant_count", 0)) >= 121
            and int(summary.get("unique_row_count", 0)) == 84
            and int(summary.get("exact_pass_tiled_fail_count", 0)) == 13
            and int(summary.get("exact_pass_tiled_fail_mixed_role_count", 0)) == 11
            and int(summary.get("exact_pass_tiled_fail_coherent_role_count", 0)) == 2
            and int(crop.get("pass_count", -1)) == 84
            and int(fullframe.get("pass_count", -1)) == 63
            and int(exact.get("pass_count", -1)) == 16
            and int(contract.get("pass_count", -1)) == 3
            and int(teacher_distill.get("pass_count", -1)) == 2
            and int(context_unet.get("pass_count", -1)) == 2
            and int(ref_field_3072.get("pass_count", -1)) == 14
            and int(ref_field_4096.get("pass_count", -1)) == 19
            and int(ref_field_6144.get("pass_count", -1)) == 23
            and int(ref_field_full.get("pass_count", -1)) == 24
            and int(residual_band.get("pass_count", -1)) == 0
            and int(residual_band.get("count", 0)) == 6
            and int(residual_unet.get("pass_count", -1)) == 0
            and int(residual_unet.get("count", 0)) == 6
        )
        return Check(
            "preview_detail",
            "full-frame failure-mode audit",
            "PASS" if ok else "FAIL",
            (
                f"rows={int(summary.get('normalized_row_count', -1))}, "
                f"unique={int(summary.get('unique_row_count', -1))}, "
                f"exact_pass_tiled_fail={int(summary.get('exact_pass_tiled_fail_count', -1))}, "
                f"mixed={int(summary.get('exact_pass_tiled_fail_mixed_role_count', -1))}, "
                f"coherent={int(summary.get('exact_pass_tiled_fail_coherent_role_count', -1))}, "
                f"fullframe={int(fullframe.get('pass_count', -1))}/84, "
                f"teacher_distill={int(teacher_distill.get('pass_count', -1))}/24, "
                f"context_unet={int(context_unet.get('pass_count', -1))}/24, "
                f"residual_band={int(residual_band.get('pass_count', -1))}/6, "
                f"residual_unet={int(residual_unet.get('pass_count', -1))}/6, "
                "ref_field_oracle="
                f"3072:{int(ref_field_3072.get('pass_count', -1))}/24 "
                f"4096:{int(ref_field_4096.get('pass_count', -1))}/24 "
                f"6144:{int(ref_field_6144.get('pass_count', -1))}/24 "
                f"full:{int(ref_field_full.get('pass_count', -1))}/24 "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "full-frame failure-mode audit", "FAIL", f"bad JSON: {exc}")


def check_preview_candidate_evidence_rank() -> Check:
    tool = REPO / "tools/cnn/rank_preview_candidate_evidence.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "preview_candidate_evidence_rank_v5"
        / "preview_candidate_evidence_rank.json"
    )
    union_tool = REPO / "tools/cnn/score_preview_policy_union.py"
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "candidate evidence rank dashboard", "FAIL", "missing tracked evidence-rank tool")
    if not union_tool.exists() or not git_tracked(union_tool):
        return Check("preview_detail", "candidate evidence rank dashboard", "FAIL", "missing tracked policy-union tool")
    if not receipt.exists():
        return Check("preview_detail", "candidate evidence rank dashboard", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = payload.get("summary") or {}
        rows = payload.get("rows") or []
        by_variant = {str(row.get("variant")): row for row in rows}
        crop = by_variant.get("crop_holdout_v32") or {}
        fullframe = by_variant.get("fullframe_scene_gated_84") or {}
        stitched = next(
            (
                row
                for row in rows
                if row.get("receipt") == "stitched_context_post"
                and row.get("variant") == "preview_runtime_policy"
            ),
            {},
        )
        ref_full = next(
            (
                row
                for row in rows
                if row.get("receipt") == "resolution_oracle_highres"
                and row.get("variant") == "ref_field_oracle_w8280"
            ),
            {},
        )
        codec_teacher_hard = next(
            (
                row
                for row in rows
                if row.get("receipt") == "codec_teacher_sources_hard8"
                and row.get("variant") == "codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools"
            ),
            {},
        )
        codec_teacher_broad = next(
            (
                row
                for row in rows
                if row.get("receipt") == "codec_teacher_q8_holdout28"
                and row.get("variant") == "codec=gpr_tools_q8+cnn=none+demosaic=sips_via_gpr_tools"
            ),
            {},
        )
        policy_union = next(
            (
                row
                for row in rows
                if row.get("receipt") == "policy_union_scene_vs_q8"
                and row.get("variant") == "oracle_union"
            ),
            {},
        )
        findings_text = "\n".join(str(item) for item in payload.get("findings") or [])
        ok = (
            payload.get("schema") == "preview_candidate_evidence_rank.v1"
            and int(summary.get("variant_count", 0)) >= 215
            and int(summary.get("production_eligible_count", 0)) >= 70
            and int(crop.get("pass_count", -1)) == 84
            and int(crop.get("count", 0)) == 84
            and crop.get("class") == "no_ref_crop_only"
            and crop.get("production_eligible") is False
            and int(fullframe.get("pass_count", -1)) == 63
            and int(fullframe.get("count", 0)) == 84
            and fullframe.get("class") == "no_ref_fullframe"
            and fullframe.get("production_eligible") is True
            and int(stitched.get("pass_count", -1)) == 2
            and int(stitched.get("count", 0)) == 24
            and stitched.get("production_eligible") is True
            and int(codec_teacher_hard.get("pass_count", -1)) == 12
            and int(codec_teacher_hard.get("count", 0)) == 24
            and codec_teacher_hard.get("production_eligible") is True
            and int(codec_teacher_broad.get("pass_count", -1)) == 32
            and int(codec_teacher_broad.get("count", 0)) == 84
            and codec_teacher_broad.get("production_eligible") is True
            and int(policy_union.get("pass_count", -1)) == 74
            and int(policy_union.get("count", 0)) == 84
            and policy_union.get("production_eligible") is False
            and int(ref_full.get("pass_count", -1)) == 24
            and int(ref_full.get("count", 0)) == 24
            and ref_full.get("production_eligible") is False
            and "Crop-shaped no-REF evidence reaches 84/84" in findings_text
            and "Best broad production-shaped full-frame row is 63/84" in findings_text
            and "Best hard-row no-REF model candidate is 2/24" in findings_text
            and "Archival q8 no-REF teacher/source reaches 32/84" in findings_text
            and "broad true-REF holdout and 12/24 on the hard-eight rows" in findings_text
            and "earlier broad q8 score compared some editable-DNG rows against their source path" in findings_text
            and "Metric-selected scene-gated/q8 oracle union reaches only 74/84" in findings_text
        )
        return Check(
            "preview_detail",
            "candidate evidence rank dashboard",
            "PASS" if ok else "FAIL",
            (
                f"variants={int(summary.get('variant_count', -1))}, "
                f"eligible={int(summary.get('production_eligible_count', -1))}, "
                f"crop={int(crop.get('pass_count', -1))}/{int(crop.get('count', 0))}, "
                f"fullframe={int(fullframe.get('pass_count', -1))}/{int(fullframe.get('count', 0))}, "
                f"best_model={int(stitched.get('pass_count', -1))}/{int(stitched.get('count', 0))}, "
                f"codec_teacher_broad={int(codec_teacher_broad.get('pass_count', -1))}/{int(codec_teacher_broad.get('count', 0))}, "
                f"codec_teacher_hard={int(codec_teacher_hard.get('pass_count', -1))}/{int(codec_teacher_hard.get('count', 0))}, "
                f"selector_union={int(policy_union.get('pass_count', -1))}/{int(policy_union.get('count', 0))}, "
                f"ref_full={int(ref_full.get('pass_count', -1))}/{int(ref_full.get('count', 0))} "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "candidate evidence rank dashboard", "FAIL", f"bad JSON: {exc}")


def check_preview_source_ref_policy_audit() -> Check:
    tool = REPO / "tools/cnn/audit_preview_source_ref_policy.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "source_ref_policy_audit_v1"
        / "preview_source_ref_policy_audit.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "source/REF policy audit", "FAIL", "missing tracked source/REF audit tool")
    if not receipt.exists():
        return Check("preview_detail", "source/REF policy audit", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = payload.get("summary") or {}
        by_source_root = {str(row.get("label")): row for row in payload.get("by_source_root") or []}
        by_ref_root = {str(row.get("label")): row for row in payload.get("by_ref_root") or []}
        clean_source = by_source_root.get("artifacts/upresable_holdout_clean_20260607/editable_dng") or {}
        diverse_ref = by_ref_root.get("cnn/diverse_dngs") or {}
        barnsky_ref = by_ref_root.get("barnsky_full_dngs") or {}
        ok = (
            payload.get("schema") == "preview_source_ref_policy_audit.v1"
            and int(summary.get("pass_count", -1)) == 20
            and int(summary.get("count", 0)) == 84
            and int(clean_source.get("pass_count", -1)) == 20
            and int(clean_source.get("count", 0)) == 84
            and int(diverse_ref.get("pass_count", -1)) == 0
            and int(diverse_ref.get("count", 0)) == 24
            and int(barnsky_ref.get("pass_count", -1)) == 20
            and int(barnsky_ref.get("count", 0)) == 60
        )
        return Check(
            "preview_detail",
            "source/REF policy audit",
            "PASS" if ok else "FAIL",
            (
                f"source_baseline={int(summary.get('pass_count', -1))}/{int(summary.get('count', 0))}, "
                f"clean_source={int(clean_source.get('pass_count', -1))}/{int(clean_source.get('count', 0))}, "
                f"diverse_ref={int(diverse_ref.get('pass_count', -1))}/{int(diverse_ref.get('count', 0))}, "
                f"barnsky_ref={int(barnsky_ref.get('pass_count', -1))}/{int(barnsky_ref.get('count', 0))}, "
                f"worst_lpips={float(summary.get('worst_lpips', float('nan'))):.4f}, "
                f"worst_ms={float(summary.get('worst_ms_ssim', float('nan'))):.4f}, "
                f"worst_y={float(summary.get('worst_y_psnr', float('nan'))):.2f}, "
                f"worst_dE={float(summary.get('worst_dE2000_mean', float('nan'))):.2f} "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "source/REF policy audit", "FAIL", f"bad JSON: {exc}")


def check_preview_source_policy_generalization_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_fullimage_band_refiner.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "upresable_source_lowfield_barnskyfit_diverseholdout_w1024_v1"
        / "preview_fullimage_band_refiner.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "source-policy generalization negative evidence", "FAIL", "missing tracked full-image band tool")
    if not receipt.exists():
        return Check("preview_detail", "source-policy generalization negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = {str(row.get("variant")): row for row in payload.get("summary") or []}
        rows = payload.get("rows") or []

        def role_count(variant: str, role: str) -> tuple[int, int]:
            selected = [row for row in rows if row.get("variant") == variant and row.get("fit_role") == role]
            return sum(1 for row in selected if row.get("preview_pass")), len(selected)

        source = summary.get("source_baseline") or {}
        generated = summary.get("generated_lowfield_residual") or {}
        ref_low = summary.get("ref_lowfield_residual") or {}
        generated_fit = role_count("generated_lowfield_residual", "fit")
        generated_holdout = role_count("generated_lowfield_residual", "holdout")
        ref_low_holdout = role_count("ref_lowfield_residual", "holdout")
        ok = (
            payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and int(source.get("pass_count", -1)) == 20
            and int(source.get("count", 0)) == 84
            and int(generated.get("pass_count", -1)) == 52
            and int(generated.get("count", 0)) == 84
            and int(ref_low.get("pass_count", -1)) == 60
            and int(ref_low.get("count", 0)) == 84
            and generated_fit == (52, 60)
            and generated_holdout == (0, 24)
            and ref_low_holdout == (0, 24)
        )
        return Check(
            "preview_detail",
            "source-policy generalization negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"source={int(source.get('pass_count', -1))}/{int(source.get('count', 0))}, "
                f"generated={int(generated.get('pass_count', -1))}/{int(generated.get('count', 0))}, "
                f"generated_fit={generated_fit[0]}/{generated_fit[1]}, "
                f"generated_holdout={generated_holdout[0]}/{generated_holdout[1]}, "
                f"ref_low={int(ref_low.get('pass_count', -1))}/{int(ref_low.get('count', 0))}, "
                f"ref_low_holdout={ref_low_holdout[0]}/{ref_low_holdout[1]}, "
                f"model_ms_median={float((payload.get('timing') or {}).get('model_ms_median', float('nan'))):.2f}, "
                f"rss={float((payload.get('timing') or {}).get('max_rss_mb', float('nan'))):.1f} MB "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "source-policy generalization negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_q8_lowfield_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_fullimage_band_refiner.py"
    base = ARTIFACT_ROOT / "preview_runtime_policy_20260613"
    receipts = {
        "barnskyfit": base / "q8_source_lowfield_barnskyfit_diverseholdout_w1024_v1/preview_fullimage_band_refiner.json",
        "allfit": base / "q8_source_lowfield_allfit_w1024_v1/preview_fullimage_band_refiner.json",
        "diversefit": base / "q8_source_lowfield_diversefit_barnskyholdout_w1024_v1/preview_fullimage_band_refiner.json",
        "unet_smoke": base / "q8_source_lowfield_residual_unet_allfit_w512_smoke_v1/preview_fullimage_band_refiner.json",
    }
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "q8 source low-field negative evidence", "FAIL", "missing tracked full-image band tool")
    missing = [str(path) for path in receipts.values() if not path.exists()]
    if missing:
        return Check("preview_detail", "q8 source low-field negative evidence", "FAIL", f"missing {missing[0]}")

    def load_summary(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
        payload = json.loads(path.read_text())
        return payload, {str(row.get("variant")): row for row in payload.get("summary") or []}, payload.get("rows") or []

    def pass_count(summary: dict[str, dict[str, Any]], variant: str) -> int:
        return int((summary.get(variant) or {}).get("pass_count", -1))

    def role_count(rows: list[dict[str, Any]], variant: str, role: str) -> tuple[int, int]:
        selected = [row for row in rows if row.get("variant") == variant and row.get("fit_role") == role]
        return sum(1 for row in selected if row.get("preview_pass")), len(selected)

    try:
        barnsky_payload, barnsky, barnsky_rows = load_summary(receipts["barnskyfit"])
        allfit_payload, allfit, allfit_rows = load_summary(receipts["allfit"])
        diverse_payload, diverse, diverse_rows = load_summary(receipts["diversefit"])
        unet_payload, unet, unet_rows = load_summary(receipts["unet_smoke"])
        ok = (
            barnsky_payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and allfit_payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and diverse_payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and unet_payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and pass_count(barnsky, "source_baseline") == 32
            and pass_count(barnsky, "generated_lowfield_residual") == 50
            and pass_count(barnsky, "generated_low_plus_source_high_s4") == 51
            and pass_count(barnsky, "ref_lowfield_residual") == 78
            and role_count(barnsky_rows, "generated_lowfield_residual", "fit") == (50, 60)
            and role_count(barnsky_rows, "generated_lowfield_residual", "holdout") == (0, 24)
            and role_count(barnsky_rows, "ref_lowfield_residual", "holdout") == (18, 24)
            and pass_count(allfit, "generated_lowfield_residual") == 60
            and pass_count(allfit, "generated_low_plus_source_high_s4") == 60
            and pass_count(allfit, "ref_lowfield_residual") == 78
            and role_count(allfit_rows, "generated_lowfield_residual", "fit") == (60, 84)
            and pass_count(diverse, "generated_lowfield_residual") == 0
            and pass_count(diverse, "generated_low_plus_source_high_s4") == 0
            and pass_count(diverse, "ref_lowfield_residual") == 78
            and role_count(diverse_rows, "generated_lowfield_residual", "fit") == (0, 24)
            and role_count(diverse_rows, "generated_lowfield_residual", "holdout") == (0, 60)
            and pass_count(unet, "source_baseline") == 32
            and pass_count(unet, "generated_lowfield_residual") == 56
            and pass_count(unet, "generated_low_plus_source_high_s4") == 53
            and pass_count(unet, "ref_lowfield_residual") == 78
            and role_count(unet_rows, "generated_lowfield_residual", "fit") == (56, 84)
            and (unet_payload.get("model") or {}).get("architecture") == "residual_unet"
        )
        return Check(
            "preview_detail",
            "q8 source low-field negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"barnskyfit generated={pass_count(barnsky, 'generated_lowfield_residual')}/84 "
                f"fit={role_count(barnsky_rows, 'generated_lowfield_residual', 'fit')[0]}/60 "
                f"holdout={role_count(barnsky_rows, 'generated_lowfield_residual', 'holdout')[0]}/24; "
                f"allfit generated={pass_count(allfit, 'generated_lowfield_residual')}/84; "
                f"diversefit generated={pass_count(diverse, 'generated_lowfield_residual')}/84; "
                f"unet_smoke generated={pass_count(unet, 'generated_lowfield_residual')}/84; "
                f"ref_low_oracle={pass_count(allfit, 'ref_lowfield_residual')}/84; "
                f"receipts={receipts['barnskyfit']}, {receipts['allfit']}, {receipts['diversefit']}, {receipts['unet_smoke']}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "q8 source low-field negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_q8_multiband_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_fullimage_band_refiner.py"
    base = ARTIFACT_ROOT / "preview_runtime_policy_20260613"
    receipts = {
        "allfit": base / "q8_source_multiband_residual_unet_allfit_w512_smoke_v1/preview_fullimage_band_refiner.json",
        "hard_holdout": base / "q8_source_multiband_residual_unet_hard8holdout_w512_smoke_v1/preview_fullimage_band_refiner.json",
        "diverse_holdout": base / "q8_source_multiband_residual_unet_diverseholdout_w512_smoke_v1/preview_fullimage_band_refiner.json",
    }
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "q8 source multiband negative evidence", "FAIL", "missing tracked full-image band tool")
    tool_text = tool.read_text()
    if "xy_multiband_global_color_stats" not in tool_text or "source_multiband_tensor" not in tool_text:
        return Check("preview_detail", "q8 source multiband negative evidence", "FAIL", "tool missing multiband conditioning contract")
    missing = [str(path) for path in receipts.values() if not path.exists()]
    if missing:
        return Check("preview_detail", "q8 source multiband negative evidence", "FAIL", f"missing {missing[0]}")

    def load_summary(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
        payload = json.loads(path.read_text())
        return payload, {str(row.get("variant")): row for row in payload.get("summary") or []}, payload.get("rows") or []

    def pass_count(summary: dict[str, dict[str, Any]], variant: str) -> int:
        return int((summary.get(variant) or {}).get("pass_count", -1))

    def role_count(rows: list[dict[str, Any]], variant: str, role: str) -> tuple[int, int]:
        selected = [row for row in rows if row.get("variant") == variant and row.get("fit_role") == role]
        return sum(1 for row in selected if row.get("preview_pass")), len(selected)

    try:
        allfit_payload, allfit, allfit_rows = load_summary(receipts["allfit"])
        hard_payload, hard, hard_rows = load_summary(receipts["hard_holdout"])
        diverse_payload, diverse, diverse_rows = load_summary(receipts["diverse_holdout"])
        ok = (
            allfit_payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and hard_payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and diverse_payload.get("schema") == "preview_fullimage_band_refiner_receipt.v1"
            and (allfit_payload.get("model") or {}).get("architecture") == "residual_unet"
            and (allfit_payload.get("model") or {}).get("conditioning") == "xy_multiband_global_color_stats"
            and int((allfit_payload.get("model") or {}).get("in_channels", 0)) == 34
            and pass_count(allfit, "source_baseline") == 32
            and pass_count(allfit, "generated_lowfield_residual") == 72
            and pass_count(allfit, "ref_lowfield_residual") == 78
            and role_count(allfit_rows, "generated_lowfield_residual", "fit") == (72, 84)
            and pass_count(hard, "generated_lowfield_residual") == 59
            and role_count(hard_rows, "generated_lowfield_residual", "fit") == (59, 60)
            and role_count(hard_rows, "generated_lowfield_residual", "holdout") == (0, 24)
            and role_count(hard_rows, "source_baseline", "holdout") == (12, 24)
            and pass_count(diverse, "generated_lowfield_residual") == 18
            and role_count(diverse_rows, "generated_lowfield_residual", "fit") == (18, 24)
            and role_count(diverse_rows, "generated_lowfield_residual", "holdout") == (0, 60)
            and role_count(diverse_rows, "source_baseline", "holdout") == (20, 60)
            and float((allfit_payload.get("timing") or {}).get("model_ms_median", 0.0)) > 0.0
            and float((allfit_payload.get("timing") or {}).get("max_rss_mb", 0.0)) > 1000.0
        )
        return Check(
            "preview_detail",
            "q8 source multiband negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"allfit generated={pass_count(allfit, 'generated_lowfield_residual')}/84; "
                f"hard_holdout generated={pass_count(hard, 'generated_lowfield_residual')}/84 "
                f"fit={role_count(hard_rows, 'generated_lowfield_residual', 'fit')[0]}/60 "
                f"holdout={role_count(hard_rows, 'generated_lowfield_residual', 'holdout')[0]}/24; "
                f"diverse_holdout generated={pass_count(diverse, 'generated_lowfield_residual')}/84 "
                f"fit={role_count(diverse_rows, 'generated_lowfield_residual', 'fit')[0]}/24 "
                f"holdout={role_count(diverse_rows, 'generated_lowfield_residual', 'holdout')[0]}/60; "
                f"receipts={receipts['allfit']}, {receipts['hard_holdout']}, {receipts['diverse_holdout']}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "q8 source multiband negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_q8_crop_specialist_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_q8_crop_refiner.py"
    fullframe_tool = REPO / "tools/cnn/evaluate_preview_q8_crop_fullframe.py"
    base = ARTIFACT_ROOT / "preview_runtime_policy_20260613"
    receipts = {
        "hardfit": base / "q8_crop_refiner_hardfit_diverseholdout_w40_s300_v1/preview_q8_crop_refiner.json",
        "hard_split": base / "q8_crop_refiner_hard_split_holdout7480_7955_w40_s300_v1/preview_q8_crop_refiner.json",
        "allfit": base / "q8_crop_refiner_allfit_w40_s300_v1/preview_q8_crop_refiner.json",
        "fullframe_hardfit_z7955": base / "q8_crop_fullframe_hardfit_z7955_t512_smoke_v1/preview_q8_crop_fullframe.json",
        "fullframe_hardfit_z7480": base / "q8_crop_fullframe_hardfit_z7480_t512_smoke_v1/preview_q8_crop_fullframe.json",
        "fullframe_hardsplit": base / "q8_crop_fullframe_hardsplit_z7480_z7955_t512_smoke_v1/preview_q8_crop_fullframe.json",
        "fullframe_hard8": base / "q8_crop_fullframe_hardfit_hard8_t512_v1/preview_q8_crop_fullframe.json",
    }
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "q8 crop specialist evidence", "FAIL", "missing tracked q8 crop refiner tool")
    if not fullframe_tool.exists() or not git_tracked(fullframe_tool):
        return Check("preview_detail", "q8 crop specialist evidence", "FAIL", "missing tracked q8 crop full-frame evaluator")
    tool_text = tool.read_text()
    if "crop_identity_key_planes" not in tool_text or "q8_source_rgb_crop" not in tool_text:
        return Check("preview_detail", "q8 crop specialist evidence", "FAIL", "tool missing no-key-plane runtime contract")
    fullframe_tool_text = fullframe_tool.read_text()
    if "q8_source_rgb_fullframe_tiles" not in fullframe_tool_text or "uses_ref_at_render_time" not in fullframe_tool_text:
        return Check("preview_detail", "q8 crop specialist evidence", "FAIL", "full-frame evaluator missing runtime contract")
    missing = [str(path) for path in receipts.values() if not path.exists()]
    if missing:
        return Check("preview_detail", "q8 crop specialist evidence", "FAIL", f"missing {missing[0]}")

    try:
        hardfit = json.loads(receipts["hardfit"].read_text())
        hard_split = json.loads(receipts["hard_split"].read_text())
        allfit = json.loads(receipts["allfit"].read_text())
        fullframe_z7955 = json.loads(receipts["fullframe_hardfit_z7955"].read_text())
        fullframe_z7480 = json.loads(receipts["fullframe_hardfit_z7480"].read_text())
        fullframe_split = json.loads(receipts["fullframe_hardsplit"].read_text())
        fullframe_hard8 = json.loads(receipts["fullframe_hard8"].read_text())

        def summary(payload: dict[str, Any], role: str) -> dict[str, Any]:
            return (payload.get("summary") or {}).get(role) or {}

        def pass_count(payload: dict[str, Any], role: str) -> tuple[int, int]:
            row = summary(payload, role)
            return int(row.get("pass_count", -1)), int(row.get("count", 0))

        hard_split_holdout_rows = [
            row for row in hard_split.get("rows") or []
            if row.get("fit_role") == "holdout"
        ]
        z7480_holdout = [
            row for row in hard_split_holdout_rows
            if row.get("image_id") == "Z8Z_7480"
        ]
        z7955_holdout = [
            row for row in hard_split_holdout_rows
            if row.get("image_id") == "Z8Z_7955"
        ]

        def ff_summary(payload: dict[str, Any]) -> dict[str, Any]:
            return (payload.get("summary") or {}).get("preview_q8_crop_fullframe") or {}

        def ff_pass_count(payload: dict[str, Any]) -> tuple[int, int]:
            row = ff_summary(payload)
            return int(row.get("pass_count", -1)), int(row.get("count", 0))

        def ff_image_pass_count(payload: dict[str, Any], image_id: str) -> tuple[int, int]:
            rows = [row for row in payload.get("rows") or [] if row.get("image_id") == image_id]
            return sum(1 for row in rows if row.get("preview_pass")), len(rows)

        ff_split_contract = fullframe_split.get("render_contract") or {}
        ff_split_timing = fullframe_split.get("timing") or {}
        ok = (
            hardfit.get("schema") == "preview_q8_crop_refiner_receipt.v1"
            and hard_split.get("schema") == "preview_q8_crop_refiner_receipt.v1"
            and allfit.get("schema") == "preview_q8_crop_refiner_receipt.v1"
            and fullframe_z7955.get("schema") == "preview_q8_crop_fullframe_receipt.v1"
            and fullframe_z7480.get("schema") == "preview_q8_crop_fullframe_receipt.v1"
            and fullframe_split.get("schema") == "preview_q8_crop_fullframe_receipt.v1"
            and fullframe_hard8.get("schema") == "preview_q8_crop_fullframe_receipt.v1"
            and (hardfit.get("render_contract") or {}).get("source_policy") == "q8_source_crop_plus_source_derived_features_only"
            and (hardfit.get("model") or {}).get("architecture") == "direct"
            and int((hardfit.get("model") or {}).get("in_channels", 0)) == 34
            and pass_count(hardfit, "fit") == (24, 24)
            and pass_count(hardfit, "holdout") == (0, 60)
            and pass_count(hardfit, "all") == (24, 84)
            and pass_count(hard_split, "fit") == (18, 18)
            and pass_count(hard_split, "holdout") == (3, 6)
            and sum(1 for row in z7480_holdout if row.get("preview_pass")) == 0
            and len(z7480_holdout) == 3
            and sum(1 for row in z7955_holdout if row.get("preview_pass")) == 3
            and len(z7955_holdout) == 3
            and pass_count(allfit, "all") == (46, 84)
            and float((hardfit.get("timing") or {}).get("model_ms_median", 0.0)) > 0.0
            and float((hardfit.get("timing") or {}).get("max_rss_mb", 0.0)) > 1000.0
            and (fullframe_z7955.get("checkpoint_sha256") == (hardfit.get("model") or {}).get("checkpoint_sha256"))
            and (fullframe_z7480.get("checkpoint_sha256") == (hardfit.get("model") or {}).get("checkpoint_sha256"))
            and ff_pass_count(fullframe_z7955) == (3, 3)
            and ff_pass_count(fullframe_z7480) == (3, 3)
            and ff_pass_count(fullframe_hard8) == (24, 24)
            and ff_pass_count(fullframe_split) == (3, 6)
            and ff_image_pass_count(fullframe_split, "Z8Z_7480") == (0, 3)
            and ff_image_pass_count(fullframe_split, "Z8Z_7955") == (3, 3)
            and ff_split_contract.get("uses_ref_at_render_time") is False
            and ff_split_contract.get("source_policy") == "q8_source_fullframe_tiled_plus_source_derived_features_only"
            and int((fullframe_hard8.get("timing") or {}).get("tile_count_total", 0)) == 1496
            and float((fullframe_hard8.get("timing") or {}).get("model_ms_total", 0.0)) > 20000.0
            and int(ff_split_timing.get("tile_count_total", 0)) == 374
            and float(ff_split_timing.get("model_ms_total", 0.0)) > 5000.0
            and float(ff_split_timing.get("max_rss_mb", 0.0)) > 1000.0
        )
        return Check(
            "preview_detail",
            "q8 crop specialist evidence",
            "PASS" if ok else "FAIL",
            (
                f"hardfit fit={pass_count(hardfit, 'fit')[0]}/24 holdout={pass_count(hardfit, 'holdout')[0]}/60; "
                f"hard_split fit={pass_count(hard_split, 'fit')[0]}/18 "
                f"holdout={pass_count(hard_split, 'holdout')[0]}/6 "
                f"z7480={sum(1 for row in z7480_holdout if row.get('preview_pass'))}/3 "
                f"z7955={sum(1 for row in z7955_holdout if row.get('preview_pass'))}/3; "
                f"allfit={pass_count(allfit, 'all')[0]}/84; "
                f"fullframe_hardfit={ff_pass_count(fullframe_hard8)[0]}/24 "
                f"fullframe_split={ff_pass_count(fullframe_split)[0]}/6 "
                f"ff_z7480={ff_image_pass_count(fullframe_split, 'Z8Z_7480')[0]}/3 "
                f"ff_z7955={ff_image_pass_count(fullframe_split, 'Z8Z_7955')[0]}/3; "
                f"receipts={receipts['hardfit']}, {receipts['hard_split']}, {receipts['allfit']}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "q8 crop specialist evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_q8_hard_router_union_evidence() -> Check:
    tool = REPO / "tools/cnn/score_preview_q8_hard_router_union.py"
    base = ARTIFACT_ROOT / "preview_runtime_policy_20260613"
    loo_receipt = base / "q8_hard_router_union_loo_v1/preview_q8_hard_router_union.json"
    final_receipt = base / "q8_hard_router_union_finalsidecar_v1/preview_q8_hard_router_union.json"
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "q8 hard router union evidence", "FAIL", "missing tracked q8 hard router union scorer")
    tool_text = tool.read_text(errors="ignore")
    if "fixed_manifest_crop_rgb_windows" not in tool_text or "forbidden_router_inputs" not in tool_text:
        return Check("preview_detail", "q8 hard router union evidence", "FAIL", "tool missing router runtime contract")
    missing = [str(path) for path in (loo_receipt, final_receipt) if not path.exists()]
    if missing:
        return Check("preview_detail", "q8 hard router union evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        loo = json.loads(loo_receipt.read_text())
        final = json.loads(final_receipt.read_text())

        def union_summary(payload: dict[str, Any]) -> dict[str, Any]:
            return (payload.get("summary") or {}).get("routed_preview_union") or {}

        def route_summary(payload: dict[str, Any], key: str) -> dict[str, Any]:
            return (payload.get("route_summary") or {}).get(key) or {}

        loo_union = union_summary(loo)
        final_union = union_summary(final)
        loo_route = route_summary(loo, "leave_one_out")
        final_route = route_summary(final, "final_sidecar")
        failures = [row for row in final.get("rows") or [] if not row.get("preview_pass")]
        failure_ids = sorted({str(row.get("image_id")) for row in failures})
        contract = final.get("render_contract") or {}
        sidecar = final.get("sidecar") or {}
        ok = (
            loo.get("schema") == "preview_q8_hard_router_union.v1"
            and final.get("schema") == "preview_q8_hard_router_union.v1"
            and loo.get("route_mode") == "leave_one_out"
            and final.get("route_mode") == "final_sidecar"
            and int(loo_union.get("pass_count", -1)) == 78
            and int(loo_union.get("count", 0)) == 84
            and int(final_union.get("pass_count", -1)) == 78
            and int(final_union.get("count", 0)) == 84
            and int(loo_route.get("correct", -1)) == 28
            and int(loo_route.get("hard_recall", -1)) == 8
            and int(loo_route.get("fallback_specificity", -1)) == 20
            and int(final_route.get("correct", -1)) == 28
            and int(final_route.get("hard_recall", -1)) == 8
            and int(final_route.get("fallback_specificity", -1)) == 20
            and failure_ids == ["Z8Z_0680", "Z8Z_0694", "Z8Z_0718"]
            and contract.get("uses_ref_at_route_time") is False
            and contract.get("uses_ref_at_render_time") is False
            and "ref_rgb" in set(contract.get("forbidden_router_inputs") or [])
            and sidecar.get("schema") == "preview_q8_hard_router_sidecar.v1"
            and (sidecar.get("training_counts") or {}).get("hard") == 8
            and (sidecar.get("training_counts") or {}).get("fallback") == 20
        )
        return Check(
            "preview_detail",
            "q8 hard router union evidence",
            "PASS" if ok else "FAIL",
            (
                f"loo={int(loo_union.get('pass_count', -1))}/84 "
                f"route={int(loo_route.get('correct', -1))}/28 "
                f"hard={int(loo_route.get('hard_recall', -1))}/8 "
                f"fallback={int(loo_route.get('fallback_specificity', -1))}/20; "
                f"final={int(final_union.get('pass_count', -1))}/84 "
                f"failures={','.join(failure_ids)} receipt={loo_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "q8 hard router union evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_q8_threeway_router_union_evidence() -> Check:
    tool = REPO / "tools/cnn/score_preview_q8_threeway_router_union.py"
    base = ARTIFACT_ROOT / "preview_runtime_policy_20260613"
    crop_receipt = base / "q8_crop_refiner_fallback3_allfit_w40_s300_v1/preview_q8_crop_refiner.json"
    fullframe_receipt = base / "q8_crop_fullframe_fallback3_allfit_t512_v1/preview_q8_crop_fullframe.json"
    false_positive_receipt = base / "q8_crop_fullframe_fallback3_falsepositive_z0640_t512_v1/preview_q8_crop_fullframe.json"
    loo_receipt = base / "q8_threeway_router_union_loo_v1/preview_q8_threeway_router_union.json"
    final_receipt = base / "q8_threeway_router_union_finalsidecar_v1/preview_q8_threeway_router_union.json"
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "q8 three-way router union evidence", "FAIL", "missing tracked q8 three-way router scorer")
    tool_text = tool.read_text(errors="ignore")
    if "fallback3_max_distance" not in tool_text or "q8_fallback3_fullframe" not in tool_text:
        return Check("preview_detail", "q8 three-way router union evidence", "FAIL", "tool missing guarded three-way route contract")
    missing = [
        str(path)
        for path in (crop_receipt, fullframe_receipt, false_positive_receipt, loo_receipt, final_receipt)
        if not path.exists()
    ]
    if missing:
        return Check("preview_detail", "q8 three-way router union evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        crop = json.loads(crop_receipt.read_text())
        fullframe = json.loads(fullframe_receipt.read_text())
        false_positive = json.loads(false_positive_receipt.read_text())
        loo = json.loads(loo_receipt.read_text())
        final = json.loads(final_receipt.read_text())

        def q8_crop_count(payload: dict[str, Any]) -> tuple[int, int]:
            row = ((payload.get("summary") or {}).get("all") or {})
            return int(row.get("pass_count", -1)), int(row.get("count", 0))

        def q8_fullframe_count(payload: dict[str, Any]) -> tuple[int, int]:
            row = ((payload.get("summary") or {}).get("preview_q8_crop_fullframe") or {})
            return int(row.get("pass_count", -1)), int(row.get("count", 0))

        def union_summary(payload: dict[str, Any]) -> dict[str, Any]:
            return (payload.get("summary") or {}).get("routed_preview_union") or {}

        def route_summary(payload: dict[str, Any], key: str) -> dict[str, Any]:
            return (payload.get("route_summary") or {}).get(key) or {}

        loo_union = union_summary(loo)
        final_union = union_summary(final)
        loo_route = route_summary(loo, "leave_one_out")
        final_route = route_summary(final, "final_sidecar")
        sidecar = final.get("sidecar") or {}
        contract = final.get("render_contract") or {}
        ok = (
            crop.get("schema") == "preview_q8_crop_refiner_receipt.v1"
            and fullframe.get("schema") == "preview_q8_crop_fullframe_receipt.v1"
            and false_positive.get("schema") == "preview_q8_crop_fullframe_receipt.v1"
            and loo.get("schema") == "preview_q8_threeway_router_union.v1"
            and final.get("schema") == "preview_q8_threeway_router_union.v1"
            and q8_crop_count(crop) == (9, 9)
            and q8_fullframe_count(fullframe) == (9, 9)
            and q8_fullframe_count(false_positive) == (1, 3)
            and int(loo_union.get("pass_count", -1)) == 84
            and int(loo_union.get("count", 0)) == 84
            and int(final_union.get("pass_count", -1)) == 84
            and int(final_union.get("count", 0)) == 84
            and float(final_union.get("worst_dE2000_mean", 999.0)) < 3.0
            and int(loo_route.get("correct", -1)) == 28
            and int(loo_route.get("hard_correct", -1)) == 8
            and int(loo_route.get("fallback3_correct", -1)) == 3
            and int(loo_route.get("fallback_correct", -1)) == 17
            and int(final_route.get("correct", -1)) == 28
            and int(final_route.get("hard_correct", -1)) == 8
            and int(final_route.get("fallback3_correct", -1)) == 3
            and int(final_route.get("fallback_correct", -1)) == 17
            and sidecar.get("schema") == "preview_q8_threeway_router_sidecar.v1"
            and float(sidecar.get("fallback3_max_distance", 0.0)) == 3.0
            and contract.get("uses_ref_at_route_time") is False
            and contract.get("uses_ref_at_render_time") is False
            and "gate_metrics" in set(contract.get("forbidden_router_inputs") or [])
        )
        return Check(
            "preview_detail",
            "q8 three-way router union evidence",
            "PASS" if ok else "FAIL",
            (
                f"fallback3_crop={q8_crop_count(crop)[0]}/9 "
                f"fallback3_fullframe={q8_fullframe_count(fullframe)[0]}/9 "
                f"false_positive={q8_fullframe_count(false_positive)[0]}/3; "
                f"loo={int(loo_union.get('pass_count', -1))}/84 route={int(loo_route.get('correct', -1))}/28; "
                f"final={int(final_union.get('pass_count', -1))}/84 "
                f"worst_dE={float(final_union.get('worst_dE2000_mean', 0.0)):.2f} receipt={loo_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "q8 three-way router union evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_q8_threeway_runtime_fullframe_evidence() -> Check:
    tool = REPO / "tools/cnn/evaluate_preview_q8_threeway_runtime_fullframe.py"
    entrypoint = REPO / "tools/cnn/render_preview_q8_threeway_runtime.py"
    readme = REPO / "README.md"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "q8_threeway_runtime_full_holdout_v1"
        / "preview_q8_threeway_runtime_fullframe.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "q8 three-way runtime full-frame evidence", "FAIL", "missing tracked integrated runtime evaluator")
    if not entrypoint.exists() or not git_tracked(entrypoint):
        return Check("preview_detail", "q8 three-way runtime full-frame evidence", "FAIL", "missing tracked runtime entrypoint")
    tool_text = tool.read_text(errors="ignore")
    if "evaluate_preview_q8_crop_fullframe.py" not in tool_text or "evaluate_preview_scene_routed_fullframe.py" not in tool_text:
        return Check("preview_detail", "q8 three-way runtime full-frame evidence", "FAIL", "tool does not invoke real full-frame child renderers")
    entrypoint_text = entrypoint.read_text(errors="ignore")
    if "evaluate_preview_q8_threeway_runtime_fullframe.py" not in entrypoint_text or "GPR_EXTERNAL_ROOT" not in entrypoint_text:
        return Check("preview_detail", "q8 three-way runtime full-frame evidence", "FAIL", "runtime entrypoint does not delegate through the integrated render path")
    if not receipt.exists():
        return Check("preview_detail", "q8 three-way runtime full-frame evidence", "FAIL", f"missing {receipt}")
    pipeline_key = "codec=ml2_q3_dec2+cnn=preview_q8_threeway_runtime_fullframe_v1+demosaic=sips_via_gpr_tools"
    pipeline = ((REG.get("pipelines") or {}).get(pipeline_key, {}) or {})
    pipeline_doc = str(pipeline.get("$doc", ""))
    pipeline_role = str(pipeline.get("$role", ""))
    pipeline_use_for = str(pipeline.get("use_for", ""))
    cnn_doc = ((REG.get("cnns") or {}).get("preview_q8_threeway_runtime_fullframe_v1", {}) or {}).get("$doc", "")
    cnn_entrypoint = ((REG.get("cnns") or {}).get("preview_q8_threeway_runtime_fullframe_v1", {}) or {}).get("runtime_entrypoint", "")
    readme_text = readme.read_text(errors="ignore") if readme.exists() else ""
    pipeline_doc_l = pipeline_doc.lower()
    cnn_doc_l = cnn_doc.lower()
    readme_text_l = readme_text.lower()
    documentation_ok = (
        "offline/review" in pipeline_doc_l
        and "not live/camera-back preview" in pipeline_doc_l
        and "production path" in pipeline_doc_l
        and pipeline_role == "ship-preview-offline-q8-threeway-runtime-fullframe"
        and pipeline_use_for == "PREVIEW_OFFLINE_REVIEW_Q8_THREEWAY"
        and "offline/review" in cnn_doc_l
        and "not live/camera-back preview" in cnn_doc_l
        and "production path" in cnn_doc_l
        and cnn_entrypoint == "tools/cnn/render_preview_q8_threeway_runtime.py"
        and "offline/review" in readme_text_l
        and "not a live/camera-back preview path" in readme_text_l
    )
    try:
        payload = json.loads(receipt.read_text())
        summary = (payload.get("summary") or {}).get("preview_q8_threeway_runtime_fullframe") or {}
        route = (payload.get("route_summary") or {}).get("final_sidecar") or {}
        selected = payload.get("selected_images_by_family") or {}
        contract = payload.get("render_contract") or {}
        timing = payload.get("timing_summary") or {}
        memory = payload.get("memory") or {}
        child_timing = payload.get("child_timing") or {}
        ok = (
            payload.get("schema") == "preview_q8_threeway_runtime_fullframe_receipt.v1"
            and int(summary.get("pass_count", -1)) == 84
            and int(summary.get("count", 0)) == 84
            and float(summary.get("worst_lpips", 999.0)) <= 0.15
            and float(summary.get("worst_ms_ssim", 0.0)) >= 0.95
            and float(summary.get("worst_y_psnr", 0.0)) >= 28.0
            and float(summary.get("worst_dE2000_mean", 999.0)) <= 3.0
            and int(route.get("correct", -1)) == 28
            and len(selected.get("hard") or []) == 8
            and len(selected.get("fallback3") or []) == 3
            and len(selected.get("fallback") or []) == 17
            and contract.get("uses_ref_at_route_time") is False
            and contract.get("uses_ref_at_render_time") is False
            and "gate_metrics" in set(contract.get("forbidden_inputs") or [])
            and int(timing.get("image_count", 0)) == 28
            and float(timing.get("runtime_no_ref_wall_ms_avg", 0.0)) > 0.0
            and float(timing.get("runtime_no_ref_fps_avg", 0.0)) > 0.0
            and float(timing.get("runtime_no_ref_fps_avg", 0.0)) < 1.0
            and float(memory.get("max_rss_mb", 0.0)) > 0.0
            and {"hard", "fallback3", "fallback"}.issubset(set(child_timing))
            and documentation_ok
        )
        return Check(
            "preview_detail",
            "q8 three-way runtime full-frame evidence",
            "PASS" if ok else "FAIL",
            (
                f"integrated={int(summary.get('pass_count', -1))}/84 "
                f"route={int(route.get('correct', -1))}/28 "
                f"runtime={float(timing.get('runtime_no_ref_wall_ms_avg', 0.0)) / 1000.0:.2f}s "
                f"fps={float(timing.get('runtime_no_ref_fps_avg', 0.0)):.3f} "
                f"rss={float(memory.get('max_rss_mb', 0.0)):.1f}MB "
                f"offline_live_doc={'yes' if documentation_ok else 'no'} "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "q8 three-way runtime full-frame evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_rolemap_post_distill_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/probe_preview_rolemap_post_distill.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "rolemap_post_distill_exactpass_tiledfail_v1"
        / "preview_rolemap_post_distill.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "role-map post-distill negative evidence", "FAIL", "missing tracked role-map probe")
    if not receipt.exists():
        return Check("preview_detail", "role-map post-distill negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = payload.get("summary") or {}
        tiled = summary.get("tiled_ref") or {}
        exact = summary.get("exact_ref") or {}
        output_ref = summary.get("output_ref") or {}
        output_teacher = summary.get("output_teacher") or {}
        contract = payload.get("runtime_contract") or {}
        ok = (
            payload.get("schema") == "preview_rolemap_post_distill.v1"
            and contract.get("training_target") == "exact no-REF crop output"
            and contract.get("ref_usage") == "scoring_only"
            and int(tiled.get("count", 0)) == 13
            and int(tiled.get("pass_count", -1)) == 0
            and int(exact.get("pass_count", -1)) == 13
            and int(output_ref.get("pass_count", -1)) == 1
            and int(output_teacher.get("pass_count", -1)) == 4
            and float(output_ref.get("worst_lpips", 0.0)) > 0.40
            and float(output_ref.get("worst_dE2000_mean", 0.0)) > 5.0
        )
        return Check(
            "preview_detail",
            "role-map post-distill negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"tiled={int(tiled.get('pass_count', -1))}/13, "
                f"exact_teacher={int(exact.get('pass_count', -1))}/13, "
                f"output_ref={int(output_ref.get('pass_count', -1))}/13, "
                f"output_teacher={int(output_teacher.get('pass_count', -1))}/13 "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "role-map post-distill negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_route_smoothing_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/evaluate_preview_scene_routed_fullframe.py"
    root = ARTIFACT_ROOT / "preview_runtime_policy_20260613"
    r512 = root / "fullframe_route_smoothing_smoke_0026_6680_r512_v1" / "preview_scene_routed_fullframe.json"
    r1024 = root / "fullframe_route_smoothing_smoke_0026_6680_r1024_v1" / "preview_scene_routed_fullframe.json"
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "route-smoothing negative evidence", "FAIL", "missing tracked full-frame evaluator")
    tool_text = tool.read_text(errors="ignore")
    if "--route-smoothing-radius" not in tool_text or "route_smoothing_changed" not in tool_text:
        return Check("preview_detail", "route-smoothing negative evidence", "FAIL", "evaluator missing route smoothing receipt fields")
    missing = [str(path) for path in (r512, r1024) if not path.exists()]
    if missing:
        return Check("preview_detail", "route-smoothing negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        p512 = json.loads(r512.read_text())
        p1024 = json.loads(r1024.read_text())
        s512 = (p512.get("summary") or {}).get("preview_runtime_policy") or {}
        s1024 = (p1024.get("summary") or {}).get("preview_runtime_policy") or {}
        c512 = p512.get("runtime_contract") or {}
        c1024 = p1024.get("runtime_contract") or {}
        changed512 = sum(int((image.get("route_smoothing") or {}).get("changed_tile_count", 0)) for image in p512.get("images") or [])
        changed1024 = sum(int((image.get("route_smoothing") or {}).get("changed_tile_count", 0)) for image in p1024.get("images") or [])
        ok = (
            p512.get("schema") == "preview_scene_routed_fullframe_receipt.v1"
            and p1024.get("schema") == "preview_scene_routed_fullframe_receipt.v1"
            and float(c512.get("route_smoothing_radius", 0.0)) == 512.0
            and float(c1024.get("route_smoothing_radius", 0.0)) == 1024.0
            and int(s512.get("count", 0)) == 6
            and int(s1024.get("count", 0)) == 6
            and int(s512.get("pass_count", -1)) == 0
            and int(s1024.get("pass_count", -1)) == 0
            and changed512 >= 30
            and changed1024 >= 30
            and float(s512.get("worst_lpips", 0.0)) > 0.43
            and float(s1024.get("worst_lpips", 0.0)) > 0.44
            and float(s512.get("worst_dE2000_mean", 0.0)) > 8.8
            and float(s1024.get("worst_dE2000_mean", 0.0)) > 8.7
        )
        return Check(
            "preview_detail",
            "route-smoothing negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"r512={int(s512.get('pass_count', -1))}/{int(s512.get('count', 0))} "
                f"changed={changed512} worst_lpips={float(s512.get('worst_lpips', 0.0)):.4f}; "
                f"r1024={int(s1024.get('pass_count', -1))}/{int(s1024.get('count', 0))} "
                f"changed={changed1024} worst_lpips={float(s1024.get('worst_lpips', 0.0)):.4f} "
                f"receipt={r512}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "route-smoothing negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_stitched_context_unet_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/train_preview_runtime_refiner.py"
    receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260613"
        / "stitched_post_hard8_context_unet_capacity_v1"
        / "preview_runtime_refiner.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "stitched context-U-Net negative evidence", "FAIL", "missing tracked runtime refiner trainer")
    tool_text = tool.read_text(errors="ignore")
    if "context_unet" not in tool_text or "--sample-receipt" not in tool_text:
        return Check("preview_detail", "stitched context-U-Net negative evidence", "FAIL", "trainer missing expected stitched/context support")
    if not receipt.exists():
        return Check("preview_detail", "stitched context-U-Net negative evidence", "FAIL", f"missing {receipt}")
    try:
        payload = json.loads(receipt.read_text())
        summary = (payload.get("summary") or {}).get("preview_runtime_policy") or {}
        contract = payload.get("runtime_contract") or {}
        training = payload.get("training") or {}
        checkpoint = Path(str(training.get("checkpoint", "")))
        ok = (
            payload.get("schema") == "preview_runtime_refiner_train_receipt.v1"
            and int(summary.get("count", 0)) == 24
            and int(summary.get("pass_count", -1)) == 2
            and float(summary.get("worst_lpips", 0.0)) > 0.55
            and float(summary.get("worst_ms_ssim", 1.0)) < 0.70
            and float(summary.get("worst_dE2000_mean", 0.0)) > 8.0
            and contract.get("conditioning") == "global_color_stats"
            and contract.get("coordinate_mode") == "global_tile"
            and int(contract.get("input_channels", 0)) == 9
            and "REF image content" in set(contract.get("forbidden_inputs") or [])
            and bool(training.get("checkpoint_sha256"))
            and checkpoint.exists()
        )
        return Check(
            "preview_detail",
            "stitched context-U-Net negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"context_unet={int(summary.get('pass_count', -1))}/{int(summary.get('count', 0))}, "
                f"worst_lpips={float(summary.get('worst_lpips', 0.0)):.4f}, "
                f"worst_ms={float(summary.get('worst_ms_ssim', 0.0)):.4f}, "
                f"worst_dE={float(summary.get('worst_dE2000_mean', 0.0)):.2f} "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "stitched context-U-Net negative evidence", "FAIL", f"bad JSON: {exc}")


def check_preview_exact_teacher_distill_negative_evidence() -> Check:
    tool = REPO / "tools/cnn/build_preview_exact_teacher_receipt.py"
    scorer = REPO / "tools/cnn/score_preview_exact_teacher_distill.py"
    direct_score_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "exact_teacher_post_distill_hard8_w96_v2"
        / "exact_teacher_distill_score.json"
    )
    unet_score_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "exact_teacher_post_distill_hard8_unetgen_v3"
        / "exact_teacher_distill_score.json"
    )
    global_context_score_receipt = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260612"
        / "exact_teacher_post_distill_hard8_global_context_w96_v1"
        / "exact_teacher_distill_score.json"
    )
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_detail", "exact-teacher distill negative evidence", "FAIL", "missing tracked exact-teacher receipt tool")
    if not scorer.exists() or not git_tracked(scorer):
        return Check("preview_detail", "exact-teacher distill negative evidence", "FAIL", "missing tracked exact-teacher scorer")
    missing = [
        str(path)
        for path in (direct_score_receipt, unet_score_receipt, global_context_score_receipt)
        if not path.exists()
    ]
    if missing:
        return Check("preview_detail", "exact-teacher distill negative evidence", "FAIL", "missing " + ", ".join(missing))
    try:
        payload = json.loads(direct_score_receipt.read_text())
        unet_payload = json.loads(unet_score_receipt.read_text())
        global_context_payload = json.loads(global_context_score_receipt.read_text())
        summary = payload.get("summary") or {}
        unet_summary = unet_payload.get("summary") or {}
        global_context_summary = global_context_payload.get("summary") or {}
        source_ref = summary.get("source_vs_ref") or {}
        teacher_ref = summary.get("teacher_vs_ref") or {}
        output_ref = summary.get("output_vs_ref") or {}
        output_teacher = summary.get("output_vs_teacher") or {}
        unet_ref = unet_summary.get("output_vs_ref") or {}
        unet_teacher = unet_summary.get("output_vs_teacher") or {}
        global_context_ref = global_context_summary.get("output_vs_ref") or {}
        global_context_teacher = global_context_summary.get("output_vs_teacher") or {}
        ok = (
            payload.get("schema") == "preview_exact_teacher_distill_score.v1"
            and unet_payload.get("schema") == "preview_exact_teacher_distill_score.v1"
            and global_context_payload.get("schema") == "preview_exact_teacher_distill_score.v1"
            and int(source_ref.get("count", 0)) == 24
            and int(source_ref.get("pass_count", -1)) == 3
            and int(teacher_ref.get("pass_count", -1)) == 16
            and int(output_teacher.get("pass_count", -1)) == 6
            and int(output_ref.get("pass_count", -1)) == 3
            and float(output_ref.get("worst_lpips", 0.0)) > 0.45
            and int(unet_teacher.get("pass_count", -1)) == 0
            and int(unet_ref.get("pass_count", -1)) == 0
            and float(unet_ref.get("worst_dE2000_mean", 0.0)) > 15.0
            and int(global_context_teacher.get("pass_count", -1)) == 5
            and int(global_context_ref.get("pass_count", -1)) == 2
            and float(global_context_ref.get("worst_lpips", 0.0)) > 0.50
        )
        return Check(
            "preview_detail",
            "exact-teacher distill negative evidence",
            "PASS" if ok else "FAIL",
            (
                f"source_ref={int(source_ref.get('pass_count', -1))}/24, "
                f"teacher_ref={int(teacher_ref.get('pass_count', -1))}/24, "
                f"output_teacher={int(output_teacher.get('pass_count', -1))}/24, "
                f"output_ref={int(output_ref.get('pass_count', -1))}/24, "
                f"unet_teacher={int(unet_teacher.get('pass_count', -1))}/24, "
                f"unet_ref={int(unet_ref.get('pass_count', -1))}/24, "
                f"global_context_teacher={int(global_context_teacher.get('pass_count', -1))}/24, "
                f"global_context_ref={int(global_context_ref.get('pass_count', -1))}/24 "
                f"receipt={direct_score_receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "exact-teacher distill negative evidence", "FAIL", f"bad JSON: {exc}")


def check_nonref_preview_candidate() -> list[Check]:
    artifact_dir = ARTIFACT_ROOT / "display_rgb_direct_lpips_nonref_20260606"
    dashboard = artifact_dir / "rgb_direct_lpips_nonref_dashboard.json"
    checkpoint = artifact_dir / "display_rgb_direct_lpips_nonref.pt"
    tool = REPO / "tools/cnn/train_display_rgb_direct_nonref.py"
    runtime_tool = REPO / "tools/cnn/evaluate_preview_runtime_policy.py"
    runtime_dashboard = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "scene_routed_holdout_v32_k16_k40_namespaced_84"
        / "preview_scene_routed_holdout.json"
    )
    expected_sha = "da1cb051daa696e4dafcb34395704081686e67f101bb5d86f0fb97fd163d4591"
    checks = [
        check_file("preview_nonref", "direct RGB non-REF tool", "tools/cnn/train_display_rgb_direct_nonref.py"),
        check_file("preview_nonref", "runtime PREVIEW policy evaluator", "tools/cnn/evaluate_preview_runtime_policy.py"),
        check_file("preview_nonref", "runtime-shaped PREVIEW trainer", "tools/cnn/train_preview_runtime_refiner.py"),
        check_file("preview_nonref", "scene router audit tool", "tools/cnn/build_preview_scene_router_audit.py"),
        check_file("preview_nonref", "full-image holdout source builder", "tools/cnn/build_preview_holdout_runtime_receipt.py"),
        check_file("preview_nonref", "scene routed evaluator", "tools/cnn/evaluate_preview_scene_routed.py"),
        check_file("preview_nonref", "full-frame tiled evaluator", "tools/cnn/evaluate_preview_scene_routed_fullframe.py"),
    ]

    if not dashboard.exists():
        checks.append(Check("preview_nonref", "direct RGB dashboard receipt", "FAIL", f"missing {dashboard}"))
        return checks
    if not checkpoint.exists():
        checks.append(Check("preview_nonref", "direct RGB checkpoint receipt", "FAIL", f"missing {checkpoint}"))
        return checks

    try:
        data = json.loads(dashboard.read_text())
    except Exception as exc:
        checks.append(Check("preview_nonref", "direct RGB dashboard receipt", "FAIL", f"bad JSON: {exc}"))
        return checks

    summary = (data.get("summary") or {}).get("rgb_direct_lpips_nonref") or {}
    rows = data.get("rows") or []
    training = data.get("training") or {}
    pass_rate = float(summary.get("pass_rate", 0.0))
    pass_count = int(summary.get("pass_count", 0))
    count = int(summary.get("count", len(rows)))
    bad_color = [
        f"{r.get('image_id')}:{r.get('crop')} dE={r.get('dE2000_mean')}"
        for r in rows
        if float(r.get("dE2000_mean", 999.0)) > 3.0
    ]
    bad_ref_variants = [
        str(r.get("variant"))
        for r in rows
        if re.search(r"\bREF\b|\[REF\]", str(r.get("variant", "")))
    ]
    sha_ok = training.get("checkpoint_sha256") == expected_sha
    render_note = str(training.get("note", ""))
    note_ok = "render uses non-REF source crop + checkpoint only" in render_note
    tool_text = tool.read_text(errors="ignore") if tool.exists() else ""
    tool_contract_ok = "REF is used only as the training target" in tool_text

    detail = (
        f"{pass_count}/{count} pass ({pass_rate * 100:.1f}%), "
        f"worst_lpips={float(summary.get('worst_lpips', 999.0)):.4f}, "
        f"worst_dE={float(summary.get('worst_dE2000_mean', 999.0)):.2f}, "
        f"dashboard={dashboard}"
    )
    checks.append(Check(
        "preview_nonref",
        "dashboard-shaped no-REF >70 diagnostic",
        "PASS" if pass_rate > 0.70 and count >= 16 and pass_count >= 12 else "FAIL",
        detail + " (diagnostic only; runtime policy checked separately)",
    ))
    checks.append(Check(
        "preview_nonref",
        "color guardrail on no-REF candidate",
        "PASS" if rows and not bad_color else "FAIL",
        "dE2000<=3.0 all dashboard rows" if not bad_color else "; ".join(bad_color[:4]),
    ))
    checks.append(Check(
        "preview_nonref",
        "no REF source labels in render rows",
        "PASS" if rows and not bad_ref_variants else "FAIL",
        "all variants are non-REF render sources" if not bad_ref_variants else "; ".join(bad_ref_variants[:4]),
    ))
    checks.append(Check(
        "preview_nonref",
        "checkpoint hash receipt",
        "PASS" if sha_ok else "FAIL",
        f"sha256={training.get('checkpoint_sha256')} expected={expected_sha}",
    ))
    checks.append(Check(
        "preview_nonref",
        "dashboard diagnostic contract documented",
        "PASS" if note_ok and tool_contract_ok else "FAIL",
        "dashboard note and tool docstring restrict REF to training/scoring, but not runtime source/key selection"
        if note_ok and tool_contract_ok
        else f"note_ok={note_ok} tool_contract_ok={tool_contract_ok}",
    ))

    if not runtime_dashboard.exists():
        checks.append(Check(
            "preview_nonref",
            "deterministic runtime policy receipt",
            "FAIL",
            f"missing {runtime_dashboard}",
        ))
        return checks

    try:
        runtime = json.loads(runtime_dashboard.read_text())
    except Exception as exc:
        checks.append(Check("preview_nonref", "deterministic runtime policy receipt", "FAIL", f"bad JSON: {exc}"))
        return checks

    contract = runtime.get("runtime_contract") or {}
    runtime_summary = (runtime.get("summary") or {}).get("preview_runtime_policy") or {}
    timing = runtime.get("timing") or {}
    memory = runtime.get("memory") or {}
    runtime_rows = runtime.get("rows") or []
    runtime_pass_rate = float(runtime_summary.get("pass_rate", 0.0))
    runtime_pass_count = int(runtime_summary.get("pass_count", 0))
    runtime_count = int(runtime_summary.get("count", len(runtime_rows)))
    forbidden = set(contract.get("forbidden_inputs") or [])
    forbidden_ok = {
        "REF image content",
        "REF HF/LF fields",
        "winner JSON",
        "sample index",
        "crop identity key planes",
    }.issubset(forbidden)
    deterministic_ok = (
        contract.get("source_policy") in {"runtime_priority_v1", "scene_router_kmeans_runtime_features"}
        and contract.get("conditioning") == "zero"
        and contract.get("router_assignment") == "frozen_sidecar_nearest_center"
        and bool(contract.get("router_sidecar"))
    )
    sidecar_path = Path(str(contract.get("router_sidecar") or ""))
    sidecar_expected_sha = str(runtime.get("router_sidecar_sha256") or "")
    sidecar_actual_sha = hashlib.sha256(sidecar_path.read_bytes()).hexdigest() if sidecar_path.exists() else ""
    sidecar_ok = bool(sidecar_expected_sha) and sidecar_expected_sha == sidecar_actual_sha
    override_sidecar_value = contract.get("override_router_sidecar") or []
    if isinstance(override_sidecar_value, str):
        override_sidecar_paths = [Path(override_sidecar_value)] if override_sidecar_value else []
    else:
        override_sidecar_paths = [Path(str(path)) for path in override_sidecar_value]
    override_expected_value = runtime.get("override_router_sidecar_sha256") or []
    if isinstance(override_expected_value, str):
        override_expected_shas = [override_expected_value] if override_expected_value else []
    else:
        override_expected_shas = [str(sha) for sha in override_expected_value]
    override_actual_shas = [
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in override_sidecar_paths
        if path.exists()
    ]
    override_sidecar_ok = (
        len(override_sidecar_paths) == len(override_expected_shas) == len(override_actual_shas)
        and override_expected_shas == override_actual_shas
    )
    route_ok = bool(runtime_rows) and all(r.get("route_source") == "frozen_sidecar_nearest_center" for r in runtime_rows)
    override_route_ok = (
        True
        if not override_sidecar_paths
        else bool(runtime_rows)
        and all(r.get("override_route_source") == "frozen_sidecar_nearest_center" for r in runtime_rows)
    )
    timing_ok = float(timing.get("model_ms_per_crop_median", 0.0)) > 0.0 and float(timing.get("model_ms_per_crop_p95", 0.0)) > 0.0
    memory_ok = float(memory.get("max_rss_mb", 0.0)) > 0.0
    runtime_detail = (
        f"{runtime_pass_count}/{runtime_count} pass ({runtime_pass_rate * 100:.1f}%), "
        f"worst_lpips={float(runtime_summary.get('worst_lpips', 999.0)):.4f}, "
        f"model_ms_median={float(timing.get('model_ms_per_crop_median', 0.0)):.2f}, "
        f"rss={float(memory.get('max_rss_mb', 0.0)):.1f} MB, dashboard={runtime_dashboard}"
    )
    checks.append(Check(
        "preview_nonref",
        "deterministic runtime policy full holdout",
        "PASS" if runtime_count >= 84 and runtime_pass_count == runtime_count else "FAIL",
        runtime_detail,
    ))
    checks.append(Check(
        "preview_nonref",
        "runtime policy forbids dashboard inputs",
        "PASS" if deterministic_ok and forbidden_ok and sidecar_ok and override_sidecar_ok and route_ok and override_route_ok else "FAIL",
        f"source_policy={contract.get('source_policy')} conditioning={contract.get('conditioning')} "
        f"assignment={contract.get('router_assignment')} forbidden_ok={forbidden_ok} "
        f"sidecar_ok={sidecar_ok} override_sidecar_ok={override_sidecar_ok} "
        f"route_ok={route_ok} override_route_ok={override_route_ok}",
    ))
    checks.append(Check(
        "preview_nonref",
        "runtime timing and memory receipt",
        "PASS" if timing_ok and memory_ok else "FAIL",
        f"timing_ok={timing_ok} memory_ok={memory_ok} receipt={runtime_dashboard}",
    ))
    runtime_tool_text = runtime_tool.read_text(errors="ignore") if runtime_tool.exists() else ""
    holdout_tool = REPO / "tools/cnn/build_preview_holdout_runtime_receipt.py"
    holdout_tool_text = holdout_tool.read_text(errors="ignore") if holdout_tool.exists() else ""
    checks.append(Check(
        "preview_nonref",
        "full-image capable runtime entrypoint",
        "PASS" if "Build PREVIEW holdout RGB crop pairs for runtime routed evaluation" in holdout_tool_text else "FAIL",
        "holdout source builder renders full images before cropping for metric rows",
    ))
    fullframe_tool = REPO / "tools/cnn/evaluate_preview_scene_routed_fullframe.py"
    fullframe_dashboard = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "fullframe_tiled_v32_smoke_z8z6680_t512"
        / "preview_scene_routed_fullframe.json"
    )
    fullframe_timing_dashboard = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "fullframe_quality_cached_route_smoke_z8z0026_v1"
        / "preview_scene_routed_fullframe.json"
    )
    fullframe_production_timing_dashboard = (
        ARTIFACT_ROOT
        / "preview_runtime_policy_20260606"
        / "fullframe_production_timing_tiffraw_route512_fastfeature_smoke_z8z0026_v1"
        / "preview_scene_routed_fullframe.json"
    )
    if not fullframe_tool.exists():
        checks.append(Check("preview_nonref", "full-frame tiled PREVIEW evaluator", "FAIL", "missing full-frame tiled evaluator"))
    elif not fullframe_dashboard.exists():
        checks.append(Check("preview_nonref", "full-frame tiled blocker receipt", "FAIL", f"missing {fullframe_dashboard}"))
    else:
        try:
            fullframe = json.loads(fullframe_dashboard.read_text())
            fullframe_summary = (fullframe.get("summary") or {}).get("preview_runtime_policy") or {}
            fullframe_pass = int(fullframe_summary.get("pass_count", 0))
            fullframe_count = int(fullframe_summary.get("count", 0))
            checks.append(Check(
                "preview_nonref",
                "full-frame tiled blocker receipt",
                "PASS" if fullframe_count >= 3 and fullframe_pass < fullframe_count else "FAIL",
                f"{fullframe_pass}/{fullframe_count} pass; "
                f"worst_lpips={float(fullframe_summary.get('worst_lpips', 999.0)):.4f}, "
                f"worst_dE={float(fullframe_summary.get('worst_dE2000_mean', 999.0)):.2f}, "
                f"receipt={fullframe_dashboard}",
            ))
        except Exception as exc:
            checks.append(Check("preview_nonref", "full-frame tiled blocker receipt", "FAIL", f"bad JSON: {exc}"))
    if not fullframe_timing_dashboard.exists():
        checks.append(Check("preview_nonref", "full-frame wall timing receipt", "FAIL", f"missing {fullframe_timing_dashboard}"))
    else:
        try:
            fullframe_timing = json.loads(fullframe_timing_dashboard.read_text())
            timing_summary = fullframe_timing.get("timing_summary") or {}
            first_timing = ((fullframe_timing.get("images") or [{}])[0].get("timing") or {})
            memory = fullframe_timing.get("memory") or {}
            runtime_ms = float(timing_summary.get("runtime_no_ref_wall_ms_avg", 0.0))
            model_ms = float(timing_summary.get("model_ms_total_avg", 0.0))
            fps = float(timing_summary.get("runtime_no_ref_fps_avg", 0.0))
            timing_ok = (
                runtime_ms > 0.0
                and model_ms > 0.0
                and fps > 0.0
                and float(first_timing.get("runtime_no_ref_wall_ms", 0.0)) > 0.0
                and float(first_timing.get("scoring_wall_ms", 0.0)) > 0.0
                and float(memory.get("max_rss_mb", 0.0)) > 0.0
            )
            checks.append(Check(
                "preview_nonref",
                "full-frame wall timing receipt",
                "PASS" if timing_ok else "FAIL",
                f"runtime={runtime_ms / 1000.0:.2f}s fps={fps:.4f} "
                f"model={model_ms / 1000.0:.2f}s rss={float(memory.get('max_rss_mb', 0.0)):.1f} MB "
                f"receipt={fullframe_timing_dashboard}",
            ))
        except Exception as exc:
            checks.append(Check("preview_nonref", "full-frame wall timing receipt", "FAIL", f"bad JSON: {exc}"))
    if not fullframe_production_timing_dashboard.exists():
        checks.append(Check("preview_nonref", "full-frame production timing receipt", "FAIL", f"missing {fullframe_production_timing_dashboard}"))
    else:
        try:
            fullframe_timing = json.loads(fullframe_production_timing_dashboard.read_text())
            timing_summary = fullframe_timing.get("timing_summary") or {}
            first_timing = ((fullframe_timing.get("images") or [{}])[0].get("timing") or {})
            first_image = (fullframe_timing.get("images") or [{}])[0]
            memory = fullframe_timing.get("memory") or {}
            runtime_contract = fullframe_timing.get("runtime_contract") or {}
            runtime_ms = float(timing_summary.get("runtime_no_ref_wall_ms_avg", 0.0))
            model_ms = float(timing_summary.get("model_ms_total_avg", 0.0))
            fps = float(timing_summary.get("runtime_no_ref_fps_avg", 0.0))
            scoring_ms = float(first_timing.get("scoring_wall_ms", 999.0))
            output_format = str(runtime_contract.get("stitched_output_format", ""))
            route_feature_max_side = int(runtime_contract.get("route_feature_max_side", 0))
            route_feature_total_ms = float(first_timing.get("scene_route_feature_ms_total", 0.0))
            route_select_total_ms = float(first_timing.get("scene_route_select_ms_total", 0.0))
            timing_ok = (
                runtime_contract.get("quality_scoring") == "skipped"
                and output_format == "tiff_raw"
                and route_feature_max_side == 512
                and runtime_ms > 0.0
                and model_ms > 0.0
                and fps > 0.0
                and float(first_timing.get("runtime_no_ref_wall_ms", 0.0)) > 0.0
                and 0.0 < float(first_timing.get("stitch_save_ms", 0.0)) < 500.0
                and route_feature_total_ms > route_select_total_ms > 0.0
                and route_feature_total_ms < 1300.0
                and scoring_ms < 1.0
                and int(first_image.get("stitched_output_bytes", 0)) > 0
                and float(memory.get("max_rss_mb", 0.0)) > 0.0
            )
            checks.append(Check(
                "preview_nonref",
                "full-frame production timing receipt",
                "PASS" if timing_ok else "FAIL",
                f"runtime={runtime_ms / 1000.0:.2f}s fps={fps:.4f} "
                f"model={model_ms / 1000.0:.2f}s output={output_format} "
                f"route_max_side={route_feature_max_side} "
                f"route_features={route_feature_total_ms / 1000.0:.2f}s "
                f"route_select={route_select_total_ms / 1000.0:.3f}s "
                f"save={float(first_timing.get('stitch_save_ms', 0.0)):.1f}ms scoring={scoring_ms:.3f}ms "
                f"rss={float(memory.get('max_rss_mb', 0.0)):.1f} MB "
                f"receipt={fullframe_production_timing_dashboard}",
            ))
        except Exception as exc:
            checks.append(Check("preview_nonref", "full-frame production timing receipt", "FAIL", f"bad JSON: {exc}"))
    return checks


def check_file(area: str, name: str, rel_path: str, require_tracked: bool = True) -> Check:
    path = REPO / rel_path
    if not path.exists():
        return Check(area, name, "FAIL", f"missing {rel_path}")
    if require_tracked and not git_tracked(path):
        return Check(area, name, "FAIL", f"exists but is not tracked: {rel_path}")
    return Check(area, name, "PASS", rel_path)


def check_external_file(area: str, name: str, path: Path, *, min_bytes: int = 1) -> Check:
    if not path.exists():
        return Check(area, name, "FAIL", f"missing {path}")
    size = path.stat().st_size
    return Check(
        area,
        name,
        "PASS" if size >= min_bytes else "FAIL",
        f"{path} size={size}",
    )


def ffprobe_video(path: Path) -> dict | None:
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_name,profile,width,height,avg_frame_rate,nb_frames",
                "-of",
                "json",
                str(path),
            ],
            text=True,
            stderr=subprocess.STDOUT,
        )
        data = json.loads(out)
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    streams = data.get("streams") or []
    return streams[0] if streams else None


def check_prores_receipt(area: str, name: str, path: Path, *, min_frames: int = 1) -> Check:
    base = check_external_file(area, name, path, min_bytes=1_000_000)
    if base.status != "PASS":
        return base
    stream = ffprobe_video(path)
    if stream is None:
        return Check(area, name, "PASS", f"{path} exists; ffprobe unavailable")
    codec = stream.get("codec_name")
    frames = int(stream.get("nb_frames") or 0)
    ok = codec == "prores" and frames >= min_frames
    return Check(
        area,
        name,
        "PASS" if ok else "FAIL",
        f"{path} codec={codec} frames={frames} dims={stream.get('width')}x{stream.get('height')}",
    )


def check_gvid_receipt(area: str, name: str, path: Path, *, min_frames: int = 1) -> Check:
    base = check_external_file(area, name, path, min_bytes=1_000_000)
    if base.status != "PASS":
        return base
    try:
        data = path.read_bytes()
        header = struct.unpack("<IBBHHHIIIII", data[:32])
    except Exception as exc:
        return Check(area, name, "FAIL", f"bad .gvid header: {exc}")
    magic, version, _flags, pixel_format, quality, _reserved, width, height, fps_x1000, _target_kbps, frame_count = header
    ok = (
        magic == 0x44495647
        and version == 1
        and width > 0
        and height > 0
        and fps_x1000 >= 24_000
        and frame_count >= min_frames
    )
    return Check(
        area,
        name,
        "PASS" if ok else "FAIL",
        f"{path} frames={frame_count} {width}x{height}@{fps_x1000 / 1000:.2f} "
        f"pixel_format={pixel_format} q={quality}",
    )


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


def check_capability_memory_receipt() -> Check:
    path = REPO / "docs/CAPABILITIES.md"
    if not path.exists():
        return Check("platform_perf", "capability memory receipt", "FAIL", "missing docs/CAPABILITIES.md")
    text = path.read_text(errors="ignore")
    required = ["| Capability | Encode | Decode | Peak RSS |", "- **Peak RSS**"]
    missing = [s for s in required if s not in text]
    if missing:
        return Check("platform_perf", "capability memory receipt", "FAIL", f"missing {missing}")
    return Check(
        "platform_perf",
        "capability memory receipt",
        "PASS",
        "Peak RSS measured with explicit criteria in docs/CAPABILITIES.md",
    )


def check_pi5_capture_receipt(require_strict24: bool = False) -> Check:
    manifest_path = REPO / "docs/release_evidence_manifest.json"
    if not manifest_path.exists():
        return Check("platform_perf", "Pi 5 half-res capture fps receipt", "FAIL", "missing release evidence manifest")
    manifest = json.loads(manifest_path.read_text())
    entry = next(
        (
            item for item in manifest.get("platform_performance", [])
            if item.get("id") == "pi5_mission1_halfres_capture"
        ),
        None,
    )
    if not isinstance(entry, dict):
        return Check("platform_perf", "Pi 5 half-res capture fps receipt", "FAIL", "missing pi5_mission1_halfres_capture manifest entry")
    metrics = entry.get("metrics", {})
    try:
        fps = float(metrics.get("fps_median"))
        target_fps = float(metrics.get("target_fps"))
    except (TypeError, ValueError):
        return Check("platform_perf", "Pi 5 half-res capture fps receipt", "FAIL", "missing numeric fps_median/target_fps")
    status = str(entry.get("status"))
    detail = f"status={status} fps_median={fps:.2f} target>={target_fps:.2f} reason={entry.get('reason', '')}"
    pass_status = status == "meets-target" and fps >= target_fps
    hardened = entry.get("hardened_wall_fps_probe")
    strict24_ok = pass_status
    if isinstance(hardened, dict):
        metrics = hardened.get("metrics")
        if isinstance(metrics, dict):
            try:
                hardened_fps = float(metrics.get("fps_median"))
                wall_fps = float(metrics.get("actual_wall_fps"))
                hardened_target = float(metrics.get("target_fps"))
                detail += (
                    f" hardened_native12=fps_median={hardened_fps:.2f} "
                    f"wall_fps={wall_fps:.2f} target>={hardened_target:.2f}"
                )
                proxy_fps = float((entry.get("metrics") or {}).get("pi_proxy_fps", 20.0))
                proxy_ok = hardened_fps >= proxy_fps and wall_fps >= proxy_fps
                receipt_rel = hardened.get("receipt")
                if isinstance(receipt_rel, str):
                    receipt, _ = read_json_receipt(EXTERNAL_ROOT / receipt_rel)
                    receipt = receipt or {}
                    verdict = receipt.get("verdict") or {}
                    storage_target = ((receipt.get("storage") or {}).get("target") or {})
                    phase_ms = ((receipt.get("bench_phase_timing") or {}).get("phase_ms") or {})
                    encode_median = (phase_ms.get("encode") or {}).get("median_ms")
                    write_median = (phase_ms.get("write") or {}).get("median_ms")
                    proxy_ok = proxy_ok and (
                        verdict.get("gvid_valid") is True
                        and verdict.get("no_drops") is True
                        and verdict.get("interruption_recovery_proven") is True
                        and verdict.get("storage_target_met") is True
                        and storage_target.get("fits_target") is True
                    )
                    if encode_median is not None and write_median is not None:
                        encode_median_f = float(encode_median)
                        write_median_f = float(write_median)
                        detail += f" phase=encode:{encode_median_f:.2f}ms/write:{write_median_f:.2f}ms"
                        proxy_ok = proxy_ok and encode_median_f > (write_median_f * 5.0)
                strict24_ok = hardened_fps >= hardened_target and wall_fps >= hardened_target
                if status == "blocked" and proxy_ok:
                    pass_status = True
            except (TypeError, ValueError):
                detail += " hardened_native12=metrics-unreadable"
    if require_strict24 and not strict24_ok:
        return Check(
            "platform_perf",
            "Pi 5 half-res capture fps receipt",
            "FAIL",
            detail + " strict24_required=yes strict24_proven=no",
        )
    return Check(
        "platform_perf",
        "Pi 5 half-res capture fps receipt",
        "PASS" if pass_status else "FAIL",
        detail,
    )


def check_mission1_strict24_production_candidate() -> Check:
    summary_path = ARTIFACT_ROOT / "mission1_native12_frontier_summary_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        return Check("mission1_native12", "strict-24 production candidate", "FAIL", err)
    frontier = [
        row for row in (summary or {}).get("frontier", [])
        if isinstance(row, dict)
    ]
    passing: list[str] = []
    near: list[str] = []
    for row in frontier:
        config = str(row.get("config"))
        quality = row.get("quality") or {}
        perf = row.get("performance") or {}
        quality_ok = (
            quality.get("quality_floor_pass") is True
            and quality.get("storage_24fps_pass") is True
        )
        fps_ok = (
            perf.get("fps_target_met") is True
            and perf.get("fps_median_target_met") is True
            and perf.get("fps_wall_target_met") is True
        )
        if quality_ok and fps_ok:
            passing.append(config)
        elif quality_ok:
            fps = to_float(perf.get("fps_median"))
            near.append(f"{config}:{fps:.2f}fps" if fps is not None else f"{config}:fps-missing")
    if passing:
        return Check(
            "mission1_native12",
            "strict-24 production candidate",
            "PASS",
            f"quality+storage+fps candidate(s)={','.join(passing)} receipt={summary_path}",
        )
    return Check(
        "mission1_native12",
        "strict-24 production candidate",
        "FAIL",
        (
            "no quality-preserving candidate proves median+wall 24 fps; "
            f"quality-preserving near misses={','.join(near) if near else 'none'} "
            f"receipt={summary_path}"
        ),
    )


def check_video_status_doc() -> Check:
    path = REPO / "docs/VIDEO_STATUS.md"
    if not path.exists():
        return Check("platform_perf", "video status doc current split", "FAIL", "missing docs/VIDEO_STATUS.md")
    text = path.read_text(errors="ignore")
    required = [
        "24.93 fps median",
        "preview_q8_threeway_runtime_fullframe_v1",
        "84-row holdout",
        "13.65 s/image",
        "0.073 fps",
        "not live/camera-back preview",
        "Latest strict 10 minute Labs receipt",
        "Treat the current commit/path as blocked",
    ]
    missing = [s for s in required if s not in text]
    return Check(
        "platform_perf",
        "video status doc current split",
        "PASS" if not missing else "FAIL",
        f"{path.relative_to(REPO)}" if not missing else f"missing {missing}",
    )


def check_live_preview_fast_path() -> Check:
    pipeline = "codec=ml2_q3_dec2+cnn=none+demosaic=sips_via_gpr_tools"
    pipe = (REG.get("pipelines") or {}).get(pipeline) or {}
    playback = REPO / "tools/test/test_sustained_playback.sh"
    if not pipe:
        return Check("platform_perf", "live PREVIEW fast path", "FAIL", f"missing registry pipeline {pipeline}")
    if not playback.exists() or not git_tracked(playback):
        return Check("platform_perf", "live PREVIEW fast path", "FAIL", "missing tracked sustained playback test")
    doc = str(pipe.get("$doc", ""))
    playback_text = playback.read_text(errors="ignore")
    ok = (
        pipe.get("ship_class") == "PREVIEW"
        and pipe.get("use_for") == "PREVIEW_LIVE_CODEC_ONLY"
        and pipe.get("cnn") == "none"
        and "Live/camera-back PREVIEW fast path" in doc
        and "not the highest-quality offline/review PREVIEW route" in doc
        and 'FPS_WITH_CNN_MIN="${FPS_WITH_CNN_MIN:-24}"' in playback_text
        and 'FPS_NO_CNN_MIN="${FPS_NO_CNN_MIN:-24}"' in playback_text
    )
    return Check(
        "platform_perf",
        "live PREVIEW fast path",
        "PASS" if ok else "FAIL",
        f"{pipeline}; sustained playback thresholds default to 24 fps UHD",
    )


def read_json_receipt(path: Path) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, f"missing {path}"
    try:
        return json.loads(path.read_text()), None
    except Exception as exc:
        return None, f"bad JSON {path}: {exc}"


def summary_target(payload: dict, target: str) -> dict:
    summary = payload.get("summary") or {}
    value = summary.get(target)
    return value if isinstance(value, dict) else {}


def target_timing(payload: dict, target: str) -> dict:
    target_summary = summary_target(payload, target)
    timing = target_summary.get("timing")
    return timing if isinstance(timing, dict) else {}


def target_metric_summary(payload: dict, target: str, key: str) -> dict:
    target_summary = summary_target(payload, target)
    value = target_summary.get(key)
    return value if isinstance(value, dict) else {}


def stats(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0, "mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def pi_receipt_metadata_ok(payload: dict, target: str, policy: str) -> bool:
    memory = payload.get("memory") or {}
    return (
        payload.get("target_2k") == target
        and payload.get("target_2k_policy") == policy
        and bool(payload.get("git_commit"))
        and bool(payload.get("cli_sha256"))
        and int(memory.get("children_maxrss_kb", 0)) > 0
    )


def expected_2k_child_policy(target: str) -> dict:
    if target == "2k_raw_0p5x_fast":
        return {
            "source": "fused_decode_cli named target",
            "halfres_stream": True,
            "halfres_drop_l2_hp": True,
            "halfres_l2_mask": None,
            "stream_strips": 2,
        }
    if target == "2k_raw_0p5x_l2hh":
        return {
            "source": "fused_decode_cli named target",
            "halfres_stream": True,
            "halfres_drop_l2_hp": False,
            "halfres_l2_mask": 4,
            "stream_strips": 2,
        }
    return {
        "source": "environment",
        "halfres_stream": True,
        "halfres_drop_l2_hp": None,
        "halfres_l2_mask": None,
    }


def pi_child_policy_ok(payload: dict, target: str) -> bool:
    """Check the child decode policy when the newer receipt schema records it.

    Older Pi receipts only captured the parent benchmark environment. Named 2K
    target policy is set inside fused_decode_cli, so the old parent field is
    useful for debugging but not sufficient proof of the child decode mode.
    """
    observed = payload.get("target_2k_child_decode_policy")
    if observed is None:
        return True
    expected = expected_2k_child_policy(target)
    return all(observed.get(key) == value for key, value in expected.items())


def pi_policy_detail(payload: dict, target: str) -> str:
    child_policy = payload.get("target_2k_child_decode_policy")
    if child_policy is None:
        child_policy = expected_2k_child_policy(target)
        source = "expected_child_policy"
    else:
        source = "child_policy"
    parent_env = payload.get("parent_decode_env") or payload.get("decode_mode") or {}
    return f"{source}={child_policy} parent_env={parent_env}"


def artifact_receipt_path(ref: str) -> Path:
    prefix = "artifacts/"
    if not ref.startswith(prefix):
        return Path(ref)
    return ARTIFACT_ROOT / ref[len(prefix):]


def registry_artifact_path(ref: str | None) -> Path | None:
    if not ref:
        return None
    return artifact_receipt_path(str(ref))


def check_registry_artifact_hash(area: str, name: str, ref: str | None, expected_sha: str | None, *, min_bytes: int = 1) -> Check:
    path = registry_artifact_path(ref)
    if path is None:
        return Check(area, name, "FAIL", "missing registry path")
    if not path.exists():
        return Check(area, name, "FAIL", f"missing {path}")
    size = path.stat().st_size
    if size < min_bytes:
        return Check(area, name, "FAIL", f"{path} size={size} below {min_bytes}")
    actual = sha256_file(path)
    ok = bool(expected_sha) and actual == expected_sha
    return Check(
        area,
        name,
        "PASS" if ok else "FAIL",
        f"sha256={actual} expected={expected_sha} path={path}",
    )


def check_native12_8k_sr_training_pairs(cnn: dict) -> Check:
    area = "native12_sr8k"
    pairs_path = registry_artifact_path(cnn.get("training_pairs_path"))
    if pairs_path is None:
        return Check(area, "8K SR training pair provenance", "FAIL", "missing training_pairs_path")

    sidecar = Path(str(pairs_path) + ".json")
    meta, err = read_json_receipt(sidecar)
    if err:
        return Check(area, "8K SR training pair provenance", "FAIL", err)

    bad: list[str] = []
    source_datasets = meta.get("source_datasets")
    if meta.get("schema") != "mission1_sr_pairs_merged.v1":
        bad.append("sidecar schema must be mission1_sr_pairs_merged.v1")
    if not isinstance(source_datasets, list) or len(source_datasets) < 2:
        bad.append("merged pair sidecar must include Mission 1 and Z8 source datasets")
        source_datasets = []

    image_rows = meta.get("images")
    if not isinstance(image_rows, list):
        bad.append("merged pair sidecar must include image rows")
        image_rows = []
    image_ids = {str(row.get("image_id", "")) for row in image_rows if isinstance(row, dict)}
    mission_ids = {image_id for image_id in image_ids if image_id.startswith("GP")}
    z8_ids = {image_id for image_id in image_ids if image_id.startswith("Z8Z_")}
    if len(mission_ids) < 8:
        bad.append(f"expected at least 8 Mission 1 50MP source images, got {len(mission_ids)}")
    if len(z8_ids) < 24:
        bad.append(f"expected at least 24 Z8 50MP source images, got {len(z8_ids)}")

    total_tiles = 0
    expected_profile = "mission1_native12_fll2_t233_avg7555_fast_pinp2_20fps_v1"
    for index, source in enumerate(source_datasets):
        if not isinstance(source, dict):
            bad.append(f"source dataset {index} must be an object")
            continue
        try:
            total_tiles += int(source.get("tile_count", 0))
        except (TypeError, ValueError):
            bad.append(f"source dataset {index} has non-numeric tile_count")
        source_meta = source.get("meta")
        if not isinstance(source_meta, dict):
            bad.append(f"source dataset {index} missing embedded meta")
            continue
        if source_meta.get("schema") != "mission1_sr_pairs.v1":
            bad.append(f"source dataset {index} schema must be mission1_sr_pairs.v1")
        if source_meta.get("downsample") != "gaussian_area":
            bad.append(f"source dataset {index} must use gaussian_area downsample")
        if source_meta.get("allow_diagnostic_downsample") is True:
            bad.append(f"source dataset {index} must not opt into diagnostic downsample")
        if source_meta.get("production_downsample") is False:
            bad.append(f"source dataset {index} explicitly marks non-production downsample")
        policy = source_meta.get("downsample_policy")
        if policy not in {None, "cfa_same_color_gaussian_area_2x"}:
            bad.append(f"source dataset {index} has unexpected downsample_policy={policy!r}")
        if source_meta.get("cfa_preserving") is False:
            bad.append(f"source dataset {index} explicitly marks non-CFA-preserving downsample")
        if source_meta.get("codec") != "current_t233":
            bad.append(f"source dataset {index} codec must be current_t233")
        if source_meta.get("codec_profile_id") != expected_profile:
            bad.append(f"source dataset {index} codec_profile_id must be {expected_profile}")
        source_images = source_meta.get("images")
        if not isinstance(source_images, list) or not source_images:
            bad.append(f"source dataset {index} missing image provenance rows")

    if int(meta.get("low_tile", 0)) != 96 or int(meta.get("high_tile", 0)) != 192:
        bad.append("merged pair tiles must be 96->192 Bayer-plane crops")
    if total_tiles < 3000:
        bad.append(f"expected at least 3000 merged SR tiles, got {total_tiles}")

    return Check(
        area,
        "8K SR training pair provenance",
        "PASS" if not bad else "FAIL",
        (
            f"datasets={len(source_datasets)} mission_images={len(mission_ids)} z8_images={len(z8_ids)} "
            f"tiles={total_tiles} downsample=gaussian_area sidecar={sidecar}"
            if not bad
            else "; ".join(bad) + f" sidecar={sidecar}"
        ),
    )


def check_native12_8k_sr_candidate() -> list[Check]:
    area = "native12_sr8k"
    pipeline_id = "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_all24_holdout5_v1+demosaic=sips_via_gpr_tools"
    cnn_id = "mission1_native12_8k_sr_all24_holdout5_v1"
    pipeline = (REG.get("pipelines") or {}).get(pipeline_id) or {}
    cnn = (REG.get("cnns") or {}).get(cnn_id) or {}
    checks: list[Check] = []

    pipe_ok = (
        pipeline.get("codec") == "mission1_native12_t233"
        and pipeline.get("cnn") == cnn_id
        and pipeline.get("ship_class") == "UPRESABLE"
        and pipeline.get("use_for") == "UPRESABLE_NATIVE12_8K_OFFLINE_CANDIDATE"
        and pipeline.get("production_scope") == "offline_review_only"
        and "not a live-camera path" in str(pipeline.get("$doc", ""))
    )
    checks.append(Check(
        area,
        "registered offline pipeline contract",
        "PASS" if pipe_ok else "FAIL",
        f"{pipeline_id} ship_class={pipeline.get('ship_class')} use_for={pipeline.get('use_for')}",
    ))

    checks.append(check_registry_artifact_hash(
        area,
        "checkpoint hash",
        cnn.get("ckpt_path"),
        cnn.get("ckpt_sha256"),
        min_bytes=100_000,
    ))
    checks.append(check_registry_artifact_hash(
        area,
        "8K SR training pair hash",
        cnn.get("training_pairs_path"),
        cnn.get("training_pairs_sha256"),
        min_bytes=1_000,
    ))
    checks.append(check_native12_8k_sr_training_pairs(cnn))

    z8_summary_path = registry_artifact_path(cnn.get("holdout_receipt"))
    z8_summary, err = read_json_receipt(z8_summary_path) if z8_summary_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "Z8 strict holdout dashboard", "FAIL", err))
    else:
        z8_rmse = ((z8_summary or {}).get("rmse_improvement_pct") or {}).get("min", 0.0)
        z8_mae = ((z8_summary or {}).get("mae_improvement_pct") or {}).get("min", 0.0)
        z8_grad = ((z8_summary or {}).get("gradient_mae_improvement_pct") or {}).get("min", 0.0)
        z8_psnr = ((z8_summary or {}).get("model_psnr14_db") or {}).get("min", 0.0)
        z8_ok = (
            (z8_summary or {}).get("schema") == "mission1_sr_fullframe_broad_eval.v1"
            and int((z8_summary or {}).get("image_count", 0)) >= 5
            and float(z8_rmse) >= 40.0
            and float(z8_mae) >= 7.0
            and float(z8_grad) >= 2.0
            and float(z8_psnr) >= 54.0
        )
        checks.append(Check(
            area,
            "Z8 strict holdout dashboard",
            "PASS" if z8_ok else "FAIL",
            f"images={(z8_summary or {}).get('image_count')} rmse_min={float(z8_rmse):.2f}% "
            f"mae_min={float(z8_mae):.2f}% grad_min={float(z8_grad):.2f}% psnr_min={float(z8_psnr):.2f} "
            f"receipt={z8_summary_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "Z8 holdout receipt hash",
        cnn.get("holdout_receipt"),
        cnn.get("holdout_receipt_sha256"),
        min_bytes=1_000,
    ))

    mission_summary_path = registry_artifact_path(cnn.get("mission_holdout_receipt"))
    mission_summary, err = read_json_receipt(mission_summary_path) if mission_summary_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "Mission 1 holdout dashboard", "FAIL", err))
    else:
        m_rmse = ((mission_summary or {}).get("rmse_improvement_pct") or {}).get("min", 0.0)
        m_mae = ((mission_summary or {}).get("mae_improvement_pct") or {}).get("min", 0.0)
        m_grad = ((mission_summary or {}).get("gradient_mae_improvement_pct") or {}).get("min", 0.0)
        m_psnr = ((mission_summary or {}).get("model_psnr14_db") or {}).get("min", 0.0)
        mission_ok = (
            (mission_summary or {}).get("schema") == "mission1_sr_fullframe_broad_eval.v1"
            and int((mission_summary or {}).get("image_count", 0)) >= 1
            and float(m_rmse) >= 45.0
            and float(m_mae) >= 35.0
            and float(m_grad) >= 15.0
            and float(m_psnr) >= 47.0
        )
        checks.append(Check(
            area,
            "Mission 1 holdout dashboard",
            "PASS" if mission_ok else "FAIL",
            f"images={(mission_summary or {}).get('image_count')} rmse_min={float(m_rmse):.2f}% "
            f"mae_min={float(m_mae):.2f}% grad_min={float(m_grad):.2f}% psnr_min={float(m_psnr):.2f} "
            f"receipt={mission_summary_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "Mission 1 holdout receipt hash",
        cnn.get("mission_holdout_receipt"),
        cnn.get("mission_holdout_receipt_sha256"),
        min_bytes=1_000,
    ))

    mission_broad_path = registry_artifact_path(cnn.get("mission_broad_holdout_receipt"))
    mission_broad, err = read_json_receipt(mission_broad_path) if mission_broad_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "Mission 1 broad holdout dashboard", "FAIL", err))
    else:
        b_rmse = ((mission_broad or {}).get("rmse_improvement_pct") or {}).get("min", 0.0)
        b_mae = ((mission_broad or {}).get("mae_improvement_pct") or {}).get("min", 0.0)
        b_grad = ((mission_broad or {}).get("gradient_mae_improvement_pct") or {}).get("min", 0.0)
        b_psnr = ((mission_broad or {}).get("model_psnr14_db") or {}).get("min", 0.0)
        b_fps = ((mission_broad or {}).get("fps_with_write") or {}).get("median", 0.0)
        broad_ok = (
            (mission_broad or {}).get("schema") == "mission1_sr_fullframe_broad_eval.v1"
            and int((mission_broad or {}).get("image_count", 0)) >= 8
            and float(b_rmse) >= 30.0
            and float(b_mae) >= 20.0
            and float(b_grad) >= 8.0
            and float(b_psnr) >= 47.0
            and float(b_fps) >= 2.0
        )
        checks.append(Check(
            area,
            "Mission 1 broad holdout dashboard",
            "PASS" if broad_ok else "FAIL",
            f"images={(mission_broad or {}).get('image_count')} rmse_min={float(b_rmse):.2f}% "
            f"mae_min={float(b_mae):.2f}% grad_min={float(b_grad):.2f}% psnr_min={float(b_psnr):.2f} "
            f"fps_median={float(b_fps):.2f} receipt={mission_broad_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "Mission 1 broad holdout receipt hash",
        cnn.get("mission_broad_holdout_receipt"),
        cnn.get("mission_broad_holdout_receipt_sha256"),
        min_bytes=1_000,
    ))

    refresh_path = registry_artifact_path(cnn.get("gvid_decode_sr_refresh_receipt"))
    refresh, err = read_json_receipt(refresh_path) if refresh_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, ".gvid decode to 8K SR receipt", "FAIL", err))
    else:
        summary = (refresh or {}).get("summary") or {}
        total = summary.get("decode_plus_sr_total_s") or {}
        fps = float(summary.get("fps_median_decode_plus_sr", 0.0))
        refresh_ok = (
            (refresh or {}).get("schema") == "mission1_native12_gvid_to_8k_sr_multiframe.v1"
            and int((refresh or {}).get("frames_rendered", 0)) >= 3
            and ((refresh or {}).get("output_bayer") or {}).get("width") == 8192
            and ((refresh or {}).get("output_bayer") or {}).get("height") == 6144
            and (refresh or {}).get("write_sr_raw") is True
            and (refresh or {}).get("keep_sr_raw") is False
            and fps >= 2.0
            and float((refresh or {}).get("max_rss_mb", 0.0)) > 0.0
            and float(total.get("median", 0.0)) > 0.0
        )
        checks.append(Check(
            area,
            ".gvid decode to 8K SR receipt",
            "PASS" if refresh_ok else "FAIL",
            f"frames={(refresh or {}).get('frames_rendered')} fps={fps:.2f} "
            f"median_s={float(total.get('median', 0.0)):.3f} rss={float((refresh or {}).get('max_rss_mb', 0.0)):.1f} "
            f"receipt={refresh_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        ".gvid decode to 8K SR receipt hash",
        cnn.get("gvid_decode_sr_refresh_receipt"),
        cnn.get("gvid_decode_sr_refresh_receipt_sha256"),
        min_bytes=1_000,
    ))

    bench_path = registry_artifact_path(cnn.get("sr8k_fresh_bench_receipt"))
    bench, err = read_json_receipt(bench_path) if bench_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "fresh 8K SR timing receipt", "FAIL", err))
    else:
        timing = (bench or {}).get("timing") or {}
        output = (bench or {}).get("output_bayer") or {}
        cost = (bench or {}).get("architecture_cost") or {}
        bench_ok = (
            (bench or {}).get("schema") == "mission1_sr_8k_bench.v1"
            and output.get("width") == 8192
            and output.get("height") == 6144
            and output.get("written") is True
            and int(timing.get("tile_count", 0)) == 20
            and float(timing.get("fps_with_write", 0.0)) >= 2.0
            and float(cost.get("actual_macs_per_frame", 0.0)) > 0.0
        )
        checks.append(Check(
            area,
            "fresh 8K SR timing receipt",
            "PASS" if bench_ok else "FAIL",
            f"fps={float(timing.get('fps_with_write', 0.0)):.2f} tiles={timing.get('tile_count')} "
            f"macs={cost.get('actual_macs_per_frame')} receipt={bench_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "fresh 8K SR timing receipt hash",
        cnn.get("sr8k_fresh_bench_receipt"),
        cnn.get("sr8k_fresh_bench_receipt_sha256"),
        min_bytes=1_000,
    ))

    compare_path = registry_artifact_path(cnn.get("sr8k_fresh_compare_receipt"))
    compare, err = read_json_receipt(compare_path) if compare_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "fresh 8K SR compare receipt", "FAIL", err))
    else:
        imp = (compare or {}).get("improvement_pct") or {}
        model = (compare or {}).get("model") or {}
        compare_ok = (
            (compare or {}).get("schema") == "mission1_sr_fullframe_compare.v1"
            and int((compare or {}).get("high_width", 0)) == 8192
            and int((compare or {}).get("high_height", 0)) == 6144
            and float(imp.get("rmse", 0.0)) >= 45.0
            and float(imp.get("mae", 0.0)) >= 35.0
            and float(imp.get("gradient_mae", 0.0)) >= 15.0
            and float(model.get("psnr14_db", 0.0)) >= 47.0
        )
        checks.append(Check(
            area,
            "fresh 8K SR compare receipt",
            "PASS" if compare_ok else "FAIL",
            f"rmse={float(imp.get('rmse', 0.0)):.2f}% mae={float(imp.get('mae', 0.0)):.2f}% "
            f"grad={float(imp.get('gradient_mae', 0.0)):.2f}% psnr={float(model.get('psnr14_db', 0.0)):.2f} "
            f"receipt={compare_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "fresh 8K SR compare receipt hash",
        cnn.get("sr8k_fresh_compare_receipt"),
        cnn.get("sr8k_fresh_compare_receipt_sha256"),
        min_bytes=1_000,
    ))

    packaging_path = registry_artifact_path(cnn.get("gvid_decode_sr_packaging_receipt"))
    packaging, err = read_json_receipt(packaging_path) if packaging_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "8K SR packaging receipt", "FAIL", err))
    else:
        sr_raw = (packaging or {}).get("sr_raw") or {}
        dng = (packaging or {}).get("editable_dng") or {}
        gpr = (packaging or {}).get("editable_gpr") or {}
        prores = (packaging or {}).get("prores_review") or {}
        prores_streams = ((prores.get("ffprobe") or {}).get("streams") or [])
        prores_stream = prores_streams[0] if prores_streams else {}
        gpr_metrics = gpr.get("readback_metrics") or {}
        packaging_ok = (
            (packaging or {}).get("schema") == "mission1_native12_gvid_to_8k_sr_packaging.v2"
            and sr_raw.get("width") == 8192
            and sr_raw.get("height") == 6144
            and int(sr_raw.get("bytes", 0)) == 100663296
            and tuple(dng.get("rawpy_open_shape") or []) == (6144, 8192)
            and bool(dng.get("raw_roundtrip_byte_identical"))
            and float(gpr_metrics.get("psnr14_db", 0.0)) >= 50.0
            and tuple(gpr.get("gpr_to_dng_rawpy_open_shape") or []) == (6144, 8192)
            and str(prores_stream.get("codec_name")) == "prores"
        )
        checks.append(Check(
            area,
            "8K SR packaging receipt",
            "PASS" if packaging_ok else "FAIL",
            f"raw={sr_raw.get('width')}x{sr_raw.get('height')} dng_roundtrip={dng.get('raw_roundtrip_byte_identical')} "
            f"gpr_psnr={float(gpr_metrics.get('psnr14_db', 0.0)):.2f} prores={prores_stream.get('codec_name')} "
            f"receipt={packaging_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "8K SR packaging receipt hash",
        cnn.get("gvid_decode_sr_packaging_receipt"),
        cnn.get("gvid_decode_sr_packaging_receipt_sha256"),
        min_bytes=1_000,
    ))

    prores_path = registry_artifact_path(cnn.get("gvid_decode_sr_prores_fps_receipt"))
    prores, err = read_json_receipt(prores_path) if prores_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "ProRes fps receipt", "FAIL", err))
    else:
        result = (prores or {}).get("result") or {}
        one = (prores or {}).get("one_frame_probe") or {}
        two = (prores or {}).get("two_frame_probe") or {}
        prores_ok = (
            (prores or {}).get("schema") == "gpr.prores_fps_fix_receipt.v1"
            and result.get("pass") is True
            and one.get("time_base") == "1/24"
            and int(one.get("duration_ts", 0)) == 1
            and str(two.get("avg_frame_rate")) == "24/1"
            and str(two.get("r_frame_rate")) == "24/1"
        )
        checks.append(Check(
            area,
            "ProRes fps receipt",
            "PASS" if prores_ok else "FAIL",
            f"pass={result.get('pass')} one_time_base={one.get('time_base')} two_avg={two.get('avg_frame_rate')} "
            f"receipt={prores_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "ProRes fps receipt hash",
        cnn.get("gvid_decode_sr_prores_fps_receipt"),
        cnn.get("gvid_decode_sr_prores_fps_receipt_sha256"),
        min_bytes=1_000,
    ))

    metadata_path = registry_artifact_path(cnn.get("mission1_metadata_repack_receipt"))
    metadata, err = read_json_receipt(metadata_path) if metadata_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "Mission 1 metadata repack receipt", "FAIL", err))
    else:
        candidates = (metadata or {}).get("candidates") or []
        missing_required = [
            f"{Path(str(row.get('source', 'candidate'))).name}:{row.get('missing_required')}"
            for row in candidates
            if row.get("missing_required")
        ]
        unreadable = [
            Path(str(row.get("source", "candidate"))).name
            for row in candidates
            if not row.get("readable_by_exiftool")
        ]
        metadata_ok = len(candidates) >= 2 and not missing_required and not unreadable
        checks.append(Check(
            area,
            "Mission 1 metadata repack receipt",
            "PASS" if metadata_ok else "FAIL",
            f"candidates={len(candidates)} missing_required={missing_required} unreadable={unreadable} receipt={metadata_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "Mission 1 metadata repack receipt hash",
        cnn.get("mission1_metadata_repack_receipt"),
        cnn.get("mission1_metadata_repack_receipt_sha256"),
        min_bytes=1_000,
    ))

    focus_cnn_id = "mission1_native12_8k_sr_focus_hardrows_2500_v1"
    focus_pipeline_id = (
        "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_focus_hardrows_2500_v1+"
        "demosaic=sips_via_gpr_tools"
    )
    focus_cnn = (REG.get("cnns") or {}).get(focus_cnn_id) or {}
    focus_pipeline = (REG.get("pipelines") or {}).get(focus_pipeline_id) or {}
    focus_contract_ok = (
        focus_pipeline.get("codec") == "mission1_native12_t233"
        and focus_pipeline.get("cnn") == focus_cnn_id
        and focus_pipeline.get("ship_class") == "UPRESABLE"
        and focus_pipeline.get("use_for") == "UPRESABLE_NATIVE12_8K_OFFLINE_REGISTRY_REVIEW"
        and focus_pipeline.get("production_scope") == "offline_review_only"
        and "not the production default" in str(focus_pipeline.get("$doc", ""))
    )
    checks.append(Check(
        area,
        "focused 8K SR registry-review contract",
        "PASS" if focus_contract_ok else "FAIL",
        f"{focus_pipeline_id} use_for={focus_pipeline.get('use_for')}",
    ))
    checks.append(check_registry_artifact_hash(
        area,
        "focused 8K SR checkpoint hash",
        focus_cnn.get("ckpt_path"),
        focus_cnn.get("ckpt_sha256"),
        min_bytes=100_000,
    ))
    checks.append(check_registry_artifact_hash(
        area,
        "focused 8K SR training receipt hash",
        focus_cnn.get("training_receipt"),
        focus_cnn.get("training_receipt_sha256"),
        min_bytes=100,
    ))

    focus_mission_path = registry_artifact_path(focus_cnn.get("mission_broad_holdout_receipt"))
    focus_mission, err = read_json_receipt(focus_mission_path) if focus_mission_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "focused 8K SR Mission broad holdout", "FAIL", err))
    else:
        f_rmse = ((focus_mission or {}).get("rmse_improvement_pct") or {}).get("min", 0.0)
        f_mae = ((focus_mission or {}).get("mae_improvement_pct") or {}).get("min", 0.0)
        f_grad = ((focus_mission or {}).get("gradient_mae_improvement_pct") or {}).get("min", 0.0)
        f_psnr = ((focus_mission or {}).get("model_psnr14_db") or {}).get("min", 0.0)
        f_fps = ((focus_mission or {}).get("fps_with_write") or {}).get("median", 0.0)
        focus_mission_ok = (
            (focus_mission or {}).get("schema") == "mission1_sr_fullframe_broad_eval.v1"
            and int((focus_mission or {}).get("image_count", 0)) >= 8
            and float(f_rmse) >= 37.0
            and float(f_mae) >= 24.0
            and float(f_grad) >= 9.0
            and float(f_psnr) >= 47.0
            and float(f_fps) >= 2.0
        )
        checks.append(Check(
            area,
            "focused 8K SR Mission broad holdout",
            "PASS" if focus_mission_ok else "FAIL",
            f"images={(focus_mission or {}).get('image_count')} rmse_min={float(f_rmse):.2f}% "
            f"mae_min={float(f_mae):.2f}% grad_min={float(f_grad):.2f}% psnr_min={float(f_psnr):.2f} "
            f"fps_median={float(f_fps):.2f} receipt={focus_mission_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "focused 8K SR Mission broad receipt hash",
        focus_cnn.get("mission_broad_holdout_receipt"),
        focus_cnn.get("mission_broad_holdout_receipt_sha256"),
        min_bytes=1_000,
    ))

    focus_z8_path = registry_artifact_path(focus_cnn.get("z8_regenerated_holdout_receipt"))
    focus_z8, err = read_json_receipt(focus_z8_path) if focus_z8_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "focused 8K SR regenerated Z8 holdout", "FAIL", err))
    else:
        z_rmse = ((focus_z8 or {}).get("rmse_improvement_pct") or {}).get("min", 0.0)
        z_mae = ((focus_z8 or {}).get("mae_improvement_pct") or {}).get("min", 0.0)
        z_grad = ((focus_z8 or {}).get("gradient_mae_improvement_pct") or {}).get("min", 0.0)
        z_psnr = ((focus_z8 or {}).get("model_psnr14_db") or {}).get("min", 0.0)
        focus_z8_ok = (
            (focus_z8 or {}).get("schema") == "mission1_sr_fullframe_broad_eval.v1"
            and int((focus_z8 or {}).get("image_count", 0)) >= 5
            and float(z_rmse) >= 24.0
            and float(z_mae) >= 5.0
            and float(z_grad) >= 1.5
            and float(z_psnr) >= 51.0
        )
        checks.append(Check(
            area,
            "focused 8K SR regenerated Z8 holdout",
            "PASS" if focus_z8_ok else "FAIL",
            f"images={(focus_z8 or {}).get('image_count')} rmse_min={float(z_rmse):.2f}% "
            f"mae_min={float(z_mae):.2f}% grad_min={float(z_grad):.2f}% psnr_min={float(z_psnr):.2f} "
            f"receipt={focus_z8_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "focused 8K SR regenerated Z8 receipt hash",
        focus_cnn.get("z8_regenerated_holdout_receipt"),
        focus_cnn.get("z8_regenerated_holdout_receipt_sha256"),
        min_bytes=1_000,
    ))

    focus_multi_path = registry_artifact_path(focus_cnn.get("gvid_decode_sr_multiframe_receipt"))
    focus_multi, err = read_json_receipt(focus_multi_path) if focus_multi_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "focused .gvid decode to 8K SR receipt", "FAIL", err))
    else:
        summary = (focus_multi or {}).get("summary") or {}
        total = summary.get("decode_plus_sr_total_s") or {}
        fps = float(summary.get("fps_median_decode_plus_sr", 0.0))
        focus_multi_ok = (
            (focus_multi or {}).get("schema") == "mission1_native12_gvid_to_8k_sr_multiframe.v1"
            and int((focus_multi or {}).get("frames_rendered", 0)) >= 3
            and ((focus_multi or {}).get("output_bayer") or {}).get("width") == 8192
            and ((focus_multi or {}).get("output_bayer") or {}).get("height") == 6144
            and (focus_multi or {}).get("write_sr_raw") is True
            and (focus_multi or {}).get("keep_sr_raw") is False
            and fps >= 2.5
            and float((focus_multi or {}).get("max_rss_mb", 0.0)) > 0.0
            and float(total.get("median", 0.0)) > 0.0
        )
        checks.append(Check(
            area,
            "focused .gvid decode to 8K SR receipt",
            "PASS" if focus_multi_ok else "FAIL",
            f"frames={(focus_multi or {}).get('frames_rendered')} fps={fps:.2f} "
            f"median_s={float(total.get('median', 0.0)):.3f} rss={float((focus_multi or {}).get('max_rss_mb', 0.0)):.1f} "
            f"receipt={focus_multi_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "focused .gvid decode to 8K SR receipt hash",
        focus_cnn.get("gvid_decode_sr_multiframe_receipt"),
        focus_cnn.get("gvid_decode_sr_multiframe_receipt_sha256"),
        min_bytes=1_000,
    ))

    focus_pack_path = registry_artifact_path(focus_cnn.get("gvid_decode_sr_packaging_receipt"))
    focus_packaging, err = read_json_receipt(focus_pack_path) if focus_pack_path else (None, "missing registry path")
    if err:
        checks.append(Check(area, "focused 8K SR packaging receipt", "FAIL", err))
    else:
        sr_raw = (focus_packaging or {}).get("sr_raw") or {}
        dng = (focus_packaging or {}).get("editable_dng") or {}
        gpr = (focus_packaging or {}).get("editable_gpr") or {}
        prores = (focus_packaging or {}).get("prores_review") or {}
        prores_fps = (focus_packaging or {}).get("prores_fps_review") or {}
        prores_streams = ((prores.get("ffprobe") or {}).get("streams") or [])
        prores_fps_streams = ((prores_fps.get("ffprobe") or {}).get("streams") or [])
        prores_stream = prores_streams[0] if prores_streams else {}
        prores_fps_stream = prores_fps_streams[0] if prores_fps_streams else {}
        gpr_metrics = gpr.get("readback_metrics") or {}
        focus_packaging_ok = (
            (focus_packaging or {}).get("schema") == "mission1_native12_gvid_to_8k_sr_packaging.v2"
            and sr_raw.get("width") == 8192
            and sr_raw.get("height") == 6144
            and int(sr_raw.get("bytes", 0)) == 100663296
            and tuple(dng.get("rawpy_open_shape") or []) == (6144, 8192)
            and bool(dng.get("raw_roundtrip_byte_identical"))
            and float(gpr_metrics.get("psnr14_db", 0.0)) >= 50.0
            and tuple(gpr.get("gpr_to_dng_rawpy_open_shape") or []) == (6144, 8192)
            and str(prores_stream.get("codec_name")) == "prores"
            and str(prores_fps_stream.get("avg_frame_rate")) == "24/1"
            and str(prores_fps_stream.get("time_base")) == "1/24"
            and int(prores_fps_stream.get("duration_ts", 0)) == 2
        )
        checks.append(Check(
            area,
            "focused 8K SR packaging receipt",
            "PASS" if focus_packaging_ok else "FAIL",
            f"raw={sr_raw.get('width')}x{sr_raw.get('height')} dng_roundtrip={dng.get('raw_roundtrip_byte_identical')} "
            f"gpr_psnr={float(gpr_metrics.get('psnr14_db', 0.0)):.2f} prores={prores_stream.get('codec_name')} "
            f"two_avg={prores_fps_stream.get('avg_frame_rate')} receipt={focus_pack_path}",
        ))
    checks.append(check_registry_artifact_hash(
        area,
        "focused 8K SR packaging receipt hash",
        focus_cnn.get("gvid_decode_sr_packaging_receipt"),
        focus_cnn.get("gvid_decode_sr_packaging_receipt_sha256"),
        min_bytes=1_000,
    ))

    return checks


def check_native12_sr_registry_boundaries() -> list[Check]:
    area = "native12_sr8k"
    allowed_codec = "mission1_native12_t233"
    allowed_use_for = {
        "UPRESABLE_NATIVE12_8K_OFFLINE_CANDIDATE",
        "UPRESABLE_NATIVE12_8K_OFFLINE_REGISTRY_REVIEW",
    }
    bad: list[str] = []
    for pipeline_id, pipeline in (REG.get("pipelines") or {}).items():
        if not isinstance(pipeline, dict):
            continue
        use_for = pipeline.get("use_for")
        if use_for not in allowed_use_for:
            continue
        codec = pipeline.get("codec")
        if codec != allowed_codec:
            bad.append(f"{pipeline_id}: codec={codec} use_for={use_for}")
        if pipeline.get("production_scope") not in {"offline_review_only", "offline_production"}:
            bad.append(f"{pipeline_id}: production_scope={pipeline.get('production_scope')}")
        doc = str(pipeline.get("$doc", ""))
        if "not a live-camera path" not in doc and "not the production default" not in doc:
            bad.append(f"{pipeline_id}: missing offline/live-boundary doc")

    return [Check(
        area,
        "native12 SR registry codec boundary",
        "PASS" if not bad else "FAIL",
        "all native12 8K SR pipelines are offline T233 pipelines"
        if not bad else "; ".join(bad),
    )]


def check_native12_sr_frontier_summary() -> list[Check]:
    area = "native12_sr8k"
    checks: list[Check] = [
        check_file(area, "native12 SR frontier summary tool", "tools/mission1_native12_sr_frontier_summary.py"),
        check_file(area, "native12 SR frontier regression", "tools/test/test_mission1_native12_sr_frontier_summary.py"),
        check_file(area, "native12 SR promotion decision tool", "tools/cnn/decide_mission1_sr_promotion.py"),
        check_file(area, "native12 SR promotion decision regression", "tools/test/test_decide_mission1_sr_promotion.py"),
        check_file(area, "native12 SR guarded experiment runner", "tools/cnn/run_mission1_sr_guarded_experiment.py"),
        check_file(area, "native12 SR guarded experiment regression", "tools/test/test_run_mission1_sr_guarded_experiment.py"),
    ]
    summary_path = ARTIFACT_ROOT / "mission1_native12_sr_frontier_summary_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        checks.append(Check(area, "native12 SR frontier evidence summary", "FAIL", err))
        return checks

    profiles = {
        row.get("profile"): row
        for row in (summary or {}).get("profiles", [])
        if isinstance(row, dict)
    }
    registered = profiles.get("t233_registered") or {}
    t233_focus = profiles.get("t233_focus_hardrows_2500") or {}
    t233_guardrail = profiles.get("t233_guardrail_focus_1500") or {}
    t233_light = profiles.get("t233_guardrail_light_w15_800") or {}
    t236 = profiles.get("t236_ch2lh3") or {}
    t236_gw08 = profiles.get("t236_ch2lh3_gw08") or {}
    t356 = profiles.get("t356_ch2lh3") or {}

    bad: list[str] = []
    if (summary or {}).get("schema") != "mission1_native12_sr_frontier_summary.v1":
        bad.append("bad schema")
    if (summary or {}).get("decision") not in {
        "keep_registered_t233",
        "candidate_ready_for_registry_review",
        "promoted_registered_offline_candidate",
    }:
        bad.append(f"decision={(summary or {}).get('decision')}")
    if registered.get("status") != "registered_offline_candidate" or registered.get("gate_pass") is not True:
        bad.append("registered T233 is not the offline candidate pass")
    if t233_focus:
        if t233_focus.get("status") != "hold_boundary_not_promoted" or t233_focus.get("gate_pass") is not True:
            bad.append(f"t233_focus_hardrows_2500 unexpected status: {t233_focus.get('status')}")
        if t233_focus.get("requires_z8_guardrail") is not True:
            bad.append("t233_focus_hardrows_2500 should require regenerated Z8 guardrail")
        if "regenerated Z8 guardrail" not in str(t233_focus.get("decision_reason", "")):
            bad.append("t233_focus_hardrows_2500 should document regenerated Z8 guardrail reason")
        if t233_focus.get("registered") is True:
            bad.append("t233_focus_hardrows_2500 unexpectedly registered")
    if t233_guardrail:
        if t233_guardrail.get("status") != "hold_boundary_not_promoted" or t233_guardrail.get("gate_pass") is not True:
            bad.append(f"t233_guardrail_focus_1500 unexpected status: {t233_guardrail.get('status')}")
        if "psnr14_min" not in str(t233_guardrail.get("decision_reason", "")):
            bad.append("t233_guardrail_focus_1500 should document PSNR boundary reason")
        if t233_guardrail.get("registered") is True:
            bad.append("t233_guardrail_focus_1500 unexpectedly registered")
    if not t233_light:
        bad.append("missing t233_guardrail_light_w15_800 frontier row")
    else:
        light_pipeline_id = (
            "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_guardrail_light_w15_800_v1+"
            "demosaic=sips_via_gpr_tools"
        )
        light_pipeline = (REG.get("pipelines") or {}).get(light_pipeline_id) or {}
        if t233_light.get("status") != "registered_offline_candidate" or t233_light.get("gate_pass") is not True:
            bad.append(f"t233_guardrail_light_w15_800 unexpected status: {t233_light.get('status')}")
        if t233_light.get("registered") is not True:
            bad.append("t233_guardrail_light_w15_800 should be registered as offline candidate")
        if light_pipeline.get("use_for") != "UPRESABLE_NATIVE12_8K_OFFLINE_CANDIDATE":
            bad.append(f"t233_guardrail_light_w15_800 pipeline use_for={light_pipeline.get('use_for')}")
        if "direct retained-artifact fallback" not in str(light_pipeline.get("$doc", "")):
            bad.append("t233_guardrail_light_w15_800 pipeline should document direct retained-artifact fallback")
        if t233_light.get("requires_packaging") is not True:
            bad.append("t233_guardrail_light_w15_800 should require packaging receipts")
        if t233_light.get("requires_z8_guardrail") is not True:
            bad.append("t233_guardrail_light_w15_800 should require regenerated Z8 guardrail")
        if float(t233_light.get("z8_rmse_improvement_min", 0.0)) <= float(registered.get("z8_rmse_improvement_min", 0.0)):
            bad.append("t233_guardrail_light_w15_800 does not improve regenerated Z8 RMSE floor")
        if float(t233_light.get("packaging_gpr_psnr14_db", 0.0)) < 50.0:
            bad.append("t233_guardrail_light_w15_800 packaging PSNR floor too low")
        if t233_light.get("packaging_raw_to_gpr_mode") != "direct_fallback_after_scratch_failure":
            bad.append("t233_guardrail_light_w15_800 packaging fallback mode not recorded")
        if float(t233_light.get("multiframe_fps_median", 0.0)) < 2.5:
            bad.append("t233_guardrail_light_w15_800 runtime receipt too slow")
    for name, row in (
        ("t236_ch2lh3", t236),
        ("t236_ch2lh3_gw08", t236_gw08),
        ("t356_ch2lh3", t356),
    ):
        if row.get("status") not in {"rejected_worst_row_regression", "hold_boundary_not_promoted"}:
            bad.append(f"{name} unexpectedly promoted: {row.get('status')}")
        if row.get("registered") is True:
            bad.append(f"{name} unexpectedly registered")
    if float(registered.get("gradient_improvement_min", 0.0)) < 8.0:
        bad.append("registered gradient floor too low")
    if float((t236_gw08 or {}).get("rmse_improvement_median", 0.0)) <= float(registered.get("rmse_improvement_median", 0.0)):
        bad.append("t236_gw08 no longer demonstrates median RMSE lift")
    if float((t236_gw08 or {}).get("rmse_improvement_min", 999.0)) >= float(registered.get("rmse_improvement_min", 0.0)):
        bad.append("t236_gw08 no longer demonstrates worst-row regression")

    checks.append(Check(
        area,
        "native12 SR frontier evidence summary",
        "PASS" if not bad else "FAIL",
        (
            f"decision={(summary or {}).get('decision')} "
            f"registered={registered.get('status')} "
            f"t233_focus={t233_focus.get('status')} "
            f"t233_guardrail={t233_guardrail.get('status')} "
            f"t233_light={t233_light.get('status')} "
            f"t236_gw08={t236_gw08.get('status')} "
            f"median_rmse={float(t236_gw08.get('rmse_improvement_median', 0.0)):.2f}% "
            f"worst_rmse={float(t236_gw08.get('rmse_improvement_min', 0.0)):.2f}% "
            f"receipt={summary_path}"
            if not bad
            else "; ".join(bad)
        ),
    ))

    guarded_path = ARTIFACT_ROOT / "current_goal_sr_t233_guarded_focus_w8_600_decision_20260618" / "decision.json"
    guarded, guarded_err = read_json_receipt(guarded_path)
    guarded_bad: list[str] = []
    if guarded_err:
        guarded_bad.append(guarded_err)
    else:
        deltas = (guarded or {}).get("deltas_vs_guardrail_light") or {}
        candidate = (guarded or {}).get("candidate") or {}
        try:
            mission_rmse_min_delta = float(deltas.get("mission_rmse_min"))
            mission_rmse_median_delta = float(deltas.get("mission_rmse_median"))
            z8_rmse_delta = float(deltas.get("z8_rmse_min"))
            z8_psnr_delta = float(deltas.get("z8_psnr14_min"))
        except (TypeError, ValueError):
            mission_rmse_min_delta = mission_rmse_median_delta = z8_rmse_delta = z8_psnr_delta = 1.0
            guarded_bad.append("missing numeric guarded-focus deltas")
        if (guarded or {}).get("schema") != "mission1_sr_guarded_focus_retrain_decision.v1":
            guarded_bad.append(f"schema={(guarded or {}).get('schema')}")
        if (guarded or {}).get("decision") != "reject_do_not_register":
            guarded_bad.append(f"decision={(guarded or {}).get('decision')}")
        if "guardrail-light" not in str((guarded or {}).get("reason", "")):
            guarded_bad.append("reason should document guardrail-light comparison")
        if not str(candidate.get("checkpoint", "")).endswith(
            "mission1_sr_t233_guarded_focus_w8_from_registered_w48_d6_rs03_600.pt"
        ):
            guarded_bad.append("unexpected guarded-focus checkpoint")
        if not (
            mission_rmse_min_delta < 0.0
            and mission_rmse_median_delta < 0.0
            and z8_rmse_delta < 0.0
            and z8_psnr_delta < 0.0
        ):
            guarded_bad.append("guarded-focus candidate no longer records a clear guardrail-light regression")
        if "not focus-only continuation" not in str((guarded or {}).get("next_experiment", "")):
            guarded_bad.append("next experiment should reject focus-only continuation")

    checks.append(Check(
        area,
        "guarded-focus SR retrain rejection",
        "PASS" if not guarded_bad else "FAIL",
        (
            f"decision={(guarded or {}).get('decision')} "
            f"mission_delta={float(((guarded or {}).get('deltas_vs_guardrail_light') or {}).get('mission_rmse_min', 0.0)):.2f}% "
            f"z8_delta={float(((guarded or {}).get('deltas_vs_guardrail_light') or {}).get('z8_rmse_min', 0.0)):.2f}% "
            f"receipt={guarded_path}"
            if not guarded_bad
            else "; ".join(guarded_bad) + f" receipt={guarded_path}"
        ),
    ))

    mixed_path = ARTIFACT_ROOT / "current_goal_sr_guarded_mixed_probe_20260618" / "guarded_experiment_summary.json"
    mixed, mixed_err = read_json_receipt(mixed_path)
    mixed_bad: list[str] = []
    if mixed_err:
        mixed_bad.append(mixed_err)
    else:
        candidates = [
            row for row in (mixed or {}).get("candidates", [])
            if isinstance(row, dict)
        ]
        if (mixed or {}).get("schema") != "mission1_sr_guarded_experiment.v1":
            mixed_bad.append(f"schema={(mixed or {}).get('schema')}")
        if (mixed or {}).get("decision") != "no_candidate_promoted":
            mixed_bad.append(f"decision={(mixed or {}).get('decision')}")
        if int((mixed or {}).get("candidate_count", 0)) < 3:
            mixed_bad.append(f"candidate_count={(mixed or {}).get('candidate_count')}")
        if any(row.get("decision") != "reject_do_not_register" for row in candidates):
            mixed_bad.append("all mixed guarded candidates should be rejected")

        saw_mission_worst_lift = False
        saw_z8_guarded_near_miss = False
        saw_incomplete_coverage_rejection = False
        for row in candidates:
            deltas = row.get("deltas") or {}
            scope = row.get("comparison_scope") or {}
            mission_scope = scope.get("mission") if isinstance(scope.get("mission"), dict) else {}
            z8_scope = scope.get("z8") if isinstance(scope.get("z8"), dict) else {}
            if mission_scope.get("missing_baseline_images") or z8_scope.get("missing_baseline_images"):
                saw_incomplete_coverage_rejection = True
            try:
                mission_min = float(deltas.get("mission_rmse_min"))
                mission_median = float(deltas.get("mission_rmse_median"))
                z8_min = float(deltas.get("z8_rmse_min"))
                z8_psnr = float(deltas.get("z8_psnr14_min"))
            except (TypeError, ValueError):
                continue
            if mission_min > 0.0 and (z8_min < 0.0 or z8_psnr < 0.0):
                saw_mission_worst_lift = True
            if z8_min > 0.0 and mission_min < 0.0:
                saw_z8_guarded_near_miss = True
        if not saw_mission_worst_lift:
            mixed_bad.append("mixed probe should capture Mission worst-row lift with Z8 regression")
        if not saw_z8_guarded_near_miss:
            mixed_bad.append("mixed probe should capture Z8-preserving near miss with Mission regression")
        if not saw_incomplete_coverage_rejection:
            mixed_bad.append("mixed probe should record incomplete baseline coverage rejection")

    checks.append(Check(
        area,
        "mixed Mission+Z8 guarded SR probe",
        "PASS" if not mixed_bad else "FAIL",
        (
            f"decision={(mixed or {}).get('decision')} "
            f"candidates={(mixed or {}).get('candidate_count')} "
            f"receipt={mixed_path}"
            if not mixed_bad
            else "; ".join(mixed_bad) + f" receipt={mixed_path}"
        ),
    ))

    full_mixed_path = (
        ARTIFACT_ROOT
        / "current_goal_sr_guarded_mixed_probe_20260618"
        / "guarded_experiment_fullcoverage_summary.json"
    )
    full_mixed, full_mixed_err = read_json_receipt(full_mixed_path)
    full_bad: list[str] = []
    if full_mixed_err:
        full_bad.append(full_mixed_err)
    else:
        candidates = [
            row for row in (full_mixed or {}).get("candidates", [])
            if isinstance(row, dict)
        ]
        if (full_mixed or {}).get("schema") != "mission1_sr_guarded_experiment.v1":
            full_bad.append(f"schema={(full_mixed or {}).get('schema')}")
        if (full_mixed or {}).get("decision") != "no_candidate_promoted":
            full_bad.append(f"decision={(full_mixed or {}).get('decision')}")
        if (full_mixed or {}).get("coverage") != "full_baseline_holdout":
            full_bad.append(f"coverage={(full_mixed or {}).get('coverage')}")
        if int((full_mixed or {}).get("mission_image_count", 0)) != 8:
            full_bad.append(f"mission_image_count={(full_mixed or {}).get('mission_image_count')}")
        if int((full_mixed or {}).get("z8_image_count", 0)) != 5:
            full_bad.append(f"z8_image_count={(full_mixed or {}).get('z8_image_count')}")
        if int((full_mixed or {}).get("candidate_count", 0)) < 3:
            full_bad.append(f"candidate_count={(full_mixed or {}).get('candidate_count')}")
        if any(row.get("decision") != "reject_do_not_register" for row in candidates):
            full_bad.append("all full-coverage mixed candidates should be rejected")

        saw_mission_worst_lift = False
        saw_z8_preserving_miss = False
        for row in candidates:
            scope = row.get("comparison_scope") or {}
            mission_scope = scope.get("mission") if isinstance(scope.get("mission"), dict) else {}
            z8_scope = scope.get("z8") if isinstance(scope.get("z8"), dict) else {}
            if mission_scope.get("missing_baseline_images") or z8_scope.get("missing_baseline_images"):
                full_bad.append("full-coverage mixed probe should have no missing baseline images")
                break
            deltas = row.get("deltas") or {}
            try:
                mission_min = float(deltas.get("mission_rmse_min"))
                mission_median = float(deltas.get("mission_rmse_median"))
                z8_min = float(deltas.get("z8_rmse_min"))
                z8_psnr = float(deltas.get("z8_psnr14_min"))
            except (TypeError, ValueError):
                continue
            if mission_min > 0.0 and mission_median < 0.0 and (z8_min < 0.0 or z8_psnr < 0.0):
                saw_mission_worst_lift = True
            if z8_min > 0.0 and mission_min < 0.0:
                saw_z8_preserving_miss = True
        if not saw_mission_worst_lift:
            full_bad.append("full-coverage probe should capture Mission worst-row lift with median/Z8 regression")
        if not saw_z8_preserving_miss:
            full_bad.append("full-coverage probe should capture Z8-preserving Mission miss")

    checks.append(Check(
        area,
        "full-coverage mixed Mission+Z8 guarded SR probe",
        "PASS" if not full_bad else "FAIL",
        (
            f"decision={(full_mixed or {}).get('decision')} "
            f"coverage={(full_mixed or {}).get('coverage')} "
            f"candidates={(full_mixed or {}).get('candidate_count')} "
            f"receipt={full_mixed_path}"
            if not full_bad
            else "; ".join(full_bad) + f" receipt={full_mixed_path}"
        ),
    ))

    resblock_path = (
        ARTIFACT_ROOT
        / "current_goal_sr_resblock_zeroinit_w48_800_probe_20260618"
        / "guarded_experiment_summary.json"
    )
    resblock, resblock_err = read_json_receipt(resblock_path)
    resblock_bad: list[str] = []
    if resblock_err:
        resblock_bad.append(resblock_err)
    else:
        candidates = [
            row for row in (resblock or {}).get("candidates", [])
            if isinstance(row, dict)
        ]
        if (resblock or {}).get("schema") != "mission1_sr_guarded_experiment.v1":
            resblock_bad.append(f"schema={(resblock or {}).get('schema')}")
        if (resblock or {}).get("decision") != "no_candidate_promoted":
            resblock_bad.append(f"decision={(resblock or {}).get('decision')}")
        if int((resblock or {}).get("candidate_count", 0)) != 4:
            resblock_bad.append(f"candidate_count={(resblock or {}).get('candidate_count')}")
        if (resblock or {}).get("selected") is not None:
            resblock_bad.append("production-sized resblock should not select a candidate")
        if any(row.get("decision") != "reject_do_not_register" for row in candidates):
            resblock_bad.append("all production-sized resblock candidates should be rejected")
        final = candidates[-1] if candidates else {}
        deltas = final.get("deltas") if isinstance(final.get("deltas"), dict) else {}
        try:
            mission_min = float(deltas.get("mission_rmse_min"))
            mission_median = float(deltas.get("mission_rmse_median"))
            z8_min = float(deltas.get("z8_rmse_min"))
            z8_psnr = float(deltas.get("z8_psnr14_min"))
        except (TypeError, ValueError):
            mission_min = mission_median = z8_min = z8_psnr = 0.0
            resblock_bad.append("missing numeric production-sized resblock deltas")
        if mission_min > -30.0 or mission_median > -40.0 or z8_min > -20.0 or z8_psnr > -2.0:
            resblock_bad.append("production-sized resblock rejection no longer proves a clear guardrail-light miss")
        if "guardrail-light" not in str(final.get("reason", "")):
            resblock_bad.append("production-sized resblock reason should document guardrail-light comparison")

    checks.append(Check(
        area,
        "production-sized zero-init resblock SR rejection",
        "PASS" if not resblock_bad else "FAIL",
        (
            f"decision={(resblock or {}).get('decision')} "
            f"candidates={(resblock or {}).get('candidate_count')} "
            f"mission_delta={float((((resblock or {}).get('candidates') or [{}])[-1].get('deltas') or {}).get('mission_rmse_median', 0.0)):.2f}% "
            f"z8_delta={float((((resblock or {}).get('candidates') or [{}])[-1].get('deltas') or {}).get('z8_rmse_min', 0.0)):.2f}% "
            f"receipt={resblock_path}"
            if not resblock_bad
            else "; ".join(resblock_bad) + f" receipt={resblock_path}"
        ),
    ))

    interp_path = (
        ARTIFACT_ROOT
        / "current_goal_sr_interp_light_focus_probe_20260618"
        / "summary.json"
    )
    interp, interp_err = read_json_receipt(interp_path)
    interp_bad: list[str] = []
    if interp_err:
        interp_bad.append(interp_err)
    else:
        candidates = [
            row for row in (interp or {}).get("candidates", [])
            if isinstance(row, dict)
        ]
        if (interp or {}).get("schema") != "mission1_sr_light_focus_interpolation_probe.v1":
            interp_bad.append(f"schema={(interp or {}).get('schema')}")
        if (interp or {}).get("decision") != "no_candidate_promoted":
            interp_bad.append(f"decision={(interp or {}).get('decision')}")
        if (interp or {}).get("selected") is not None:
            interp_bad.append("interpolation probe should not select a candidate")
        alphas = sorted(float(row.get("alpha", -1.0)) for row in candidates)
        if alphas != [0.25, 0.5, 0.75]:
            interp_bad.append(f"alphas={alphas}")
        if any(row.get("decision") != "reject_do_not_register" for row in candidates):
            interp_bad.append("all interpolation candidates should be rejected")
        saw_mission_floor_lift = False
        saw_guardrail_regression = False
        for row in candidates:
            deltas = row.get("deltas_vs_guardrail_light") or {}
            try:
                mission_min = float(deltas.get("mission_rmse_min"))
                mission_median = float(deltas.get("mission_rmse_median"))
                z8_min = float(deltas.get("z8_rmse_min"))
                z8_psnr = float(deltas.get("z8_psnr14_min"))
            except (TypeError, ValueError):
                interp_bad.append("missing numeric interpolation deltas")
                continue
            if mission_min > 0.0:
                saw_mission_floor_lift = True
            if mission_median < 0.0 and (z8_min < 0.0 or z8_psnr < 0.0):
                saw_guardrail_regression = True
            if "guardrail-light" not in str(row.get("reason", "")):
                interp_bad.append("interpolation rejection should document guardrail-light comparison")
        if not saw_mission_floor_lift:
            interp_bad.append("interpolation should capture the small Mission worst-row lift")
        if not saw_guardrail_regression:
            interp_bad.append("interpolation should capture Mission median/Z8 guardrail regression")

    checks.append(Check(
        area,
        "light-focus SR checkpoint interpolation rejection",
        "PASS" if not interp_bad else "FAIL",
        (
            f"decision={(interp or {}).get('decision')} "
            f"candidates={len((interp or {}).get('candidates', []))} "
            f"best_mission_floor_delta={max(float((row.get('deltas_vs_guardrail_light') or {}).get('mission_rmse_min', 0.0)) for row in ((interp or {}).get('candidates') or [{}])):.3f}% "
            f"receipt={interp_path}"
            if not interp_bad
            else "; ".join(interp_bad) + f" receipt={interp_path}"
        ),
    ))
    return checks


def check_native12_bayer_resample_contract() -> list[Check]:
    area = "mission1_native12"
    checks: list[Check] = []
    checks.extend([
        check_file(area, "CFA-preserving Bayer resample helper", "tools/bayer_resample.py"),
        check_file(area, "CFA resample regression test", "tools/test/test_bayer_resample.py"),
    ])

    matrix_path = REPO / "tools/mission1_true_bayer_recompression_matrix.py"
    if matrix_path.exists():
        text = matrix_path.read_text(errors="ignore")
        required = ["from bayer_resample import cfa_downsample_2x", 'cfa_downsample_2x(arr, mode="gaussian_area")']
        missing = [needle for needle in required if needle not in text]
        checks.append(Check(
            area,
            "50MP-to-12MP matrix uses shared CFA resample",
            "PASS" if not missing else "FAIL",
            "tools/mission1_true_bayer_recompression_matrix.py" if not missing else f"missing {missing}",
        ))
    else:
        checks.append(Check(
            area,
            "50MP-to-12MP matrix uses shared CFA resample",
            "FAIL",
            "missing tools/mission1_true_bayer_recompression_matrix.py",
        ))

    sr_pair_path = REPO / "tools/cnn/build_mission1_sr_pairs.py"
    if sr_pair_path.exists():
        text = sr_pair_path.read_text(errors="ignore")
        required = [
            "from bayer_resample import cfa_downsample_2x",
            "return cfa_downsample_2x(bayer50, mode=mode)",
            '"downsample_implementation": downsample_impl',
            '"downsample_policy": downsample_policy',
            '"production_downsample": production_downsample',
            "--allow-diagnostic-downsample",
            '"cfa_preserving": True',
        ]
        missing = [needle for needle in required if needle not in text]
        checks.append(Check(
            area,
            "SR pair builder records shared CFA resample provenance",
            "PASS" if not missing else "FAIL",
            "tools/cnn/build_mission1_sr_pairs.py" if not missing else f"missing {missing}",
        ))
    else:
        checks.append(Check(
            area,
            "SR pair builder records shared CFA resample provenance",
            "FAIL",
            "missing tools/cnn/build_mission1_sr_pairs.py",
        ))

    sr_pair_test = REPO / "tools/test/test_mission1_sr_pair_codec_profiles.py"
    if sr_pair_test.exists():
        text = sr_pair_test.read_text(errors="ignore")
        required = [
            "synthesize_12mp_from_50mp",
            "cfa_downsample_2x",
            "SR pair builder diverged from shared CFA downsampler",
            "diagnostic downsample should require explicit opt-in",
            "production_downsample=true",
        ]
        missing = [needle for needle in required if needle not in text]
        checks.append(Check(
            area,
            "SR pair builder shared-resample regression",
            "PASS" if not missing else "FAIL",
            "tools/test/test_mission1_sr_pair_codec_profiles.py" if not missing else f"missing {missing}",
        ))
    else:
        checks.append(Check(
            area,
            "SR pair builder shared-resample regression",
            "FAIL",
            "missing tools/test/test_mission1_sr_pair_codec_profiles.py",
        ))

    test_path = REPO / "tools/test/test_bayer_resample.py"
    if test_path.exists():
        text = test_path.read_text(errors="ignore")
        required = [
            "expected_same_plane_average",
            "top-row CFA phase was not preserved",
            "bottom-row CFA phase was not preserved",
            "gaussian_area mixed CFA planes",
            "gaussian_area did not preserve constant same-plane values",
            "gaussian_area anti-aliasing did not attenuate same-plane impulse",
            "gaussian_area anti-aliasing did not spread same-plane impulse",
            "gaussian_area anti-aliasing touched other CFA planes",
            "expected non-divisible-by-4 height to fail",
            "CLI output mismatch",
        ]
        missing = [needle for needle in required if needle not in text]
        checks.append(Check(
            area,
            "CFA resample test coverage",
            "PASS" if not missing else "FAIL",
            "phase, G1/G2, gaussian_area anti-aliasing, geometry, and CLI covered" if not missing else f"missing {missing}",
        ))
    else:
        checks.append(Check(area, "CFA resample test coverage", "FAIL", "missing tools/test/test_bayer_resample.py"))
    return checks


def check_native12_frontier_summary() -> list[Check]:
    area = "mission1_native12"
    checks: list[Check] = []
    checks.extend([
        check_file(area, "native12 frontier summary tool", "tools/mission1_native12_frontier_summary.py"),
        check_file(area, "native12 frontier summary regression", "tools/test/test_mission1_native12_frontier_summary.py"),
    ])

    summary_path = ARTIFACT_ROOT / "mission1_native12_frontier_summary_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        checks.append(Check(area, "native12 frontier evidence summary", "FAIL", err))
        return checks

    if (summary or {}).get("schema") != "mission1_native12_frontier_summary.v2":
        checks.append(Check(
            area,
            "native12 frontier evidence summary",
            "FAIL",
            f"unexpected schema {(summary or {}).get('schema')} receipt={summary_path}",
        ))
        return checks

    frontier = {
        str(row.get("config")): row
        for row in (summary or {}).get("frontier", [])
        if isinstance(row, dict)
    }
    expected_status = {
        "t236_ch2lh3": "fps_fail",
        "t238_ch2lh3": "fps_fail",
        "t244_lh2_hl4_hh4": "quality_fail",
        "t356_ch2lh3": "quality_fail",
        "t468_ch2lh4": "quality_fail",
    }
    bad = []
    for config, expected in expected_status.items():
        actual = (frontier.get(config) or {}).get("production_status")
        if actual != expected:
            bad.append(f"{config}={actual}, expected {expected}")

    t236 = frontier.get("t236_ch2lh3") or {}
    t236_quality = t236.get("quality") or {}
    t236_perf = t236.get("performance") or {}
    if t236_quality.get("quality_floor_pass") is not True or t236_quality.get("storage_24fps_pass") is not True:
        bad.append("t236_ch2lh3 does not preserve quality/storage boundary")
    if (t236.get("cnn_recovery_policy") or {}).get("cnn_recovery_allowed") is not True:
        bad.append("t236_ch2lh3 must remain allowed as a valid decoded-Bayer SR input")
    try:
        if float(t236_perf.get("fps_median")) >= 24.0:
            bad.append("t236_ch2lh3 unexpectedly reports strict-24 median fps")
    except (TypeError, ValueError):
        bad.append("t236_ch2lh3 missing numeric fps_median")

    t238 = frontier.get("t238_ch2lh3") or {}
    t238_quality = t238.get("quality") or {}
    t238_perf = t238.get("performance") or {}
    if t238_quality.get("quality_floor_pass") is not True or t238_quality.get("storage_24fps_pass") is not True:
        bad.append("t238_ch2lh3 does not preserve quality/storage boundary")
    if (t238.get("cnn_recovery_policy") or {}).get("cnn_recovery_allowed") is not True:
        bad.append("t238_ch2lh3 must remain allowed as a valid decoded-Bayer SR input")
    try:
        if float(t238_perf.get("fps_median")) >= 24.0:
            bad.append("t238_ch2lh3 unexpectedly reports strict-24 median fps")
    except (TypeError, ValueError):
        bad.append("t238_ch2lh3 missing numeric fps_median")

    t244 = frontier.get("t244_lh2_hl4_hh4") or {}
    t244_quality = t244.get("quality") or {}
    t244_perf = t244.get("performance") or {}
    if t244_quality.get("quality_floor_pass") is not False or t244_quality.get("storage_24fps_pass") is not True:
        bad.append("t244_lh2_hl4_hh4 must remain classified as speed/storage-only quality fail")
    t244_policy = t244.get("cnn_recovery_policy") or {}
    if t244_policy.get("cnn_recovery_allowed") is not False or t244_policy.get("decoded_bayer_status") != "codec_quality_failure":
        bad.append("t244_lh2_hl4_hh4 must be blocked from CNN recovery until codec quality passes")
    try:
        if float(t244_quality.get("min_psnr14")) >= 75.0:
            bad.append("t244_lh2_hl4_hh4 unexpectedly clears quality floor")
    except (TypeError, ValueError):
        bad.append("t244_lh2_hl4_hh4 missing min_psnr14")
    if t244_perf.get("fps_target_met") is not True:
        bad.append("t244_lh2_hl4_hh4 missing strict-24 speed receipt")
    for config in ("t356_ch2lh3", "t468_ch2lh4"):
        policy = (frontier.get(config) or {}).get("cnn_recovery_policy") or {}
        if policy.get("cnn_recovery_allowed") is not False or policy.get("decoded_bayer_status") != "codec_quality_failure":
            bad.append(f"{config} must be blocked from CNN recovery until codec quality passes")

    legacy = (summary or {}).get("legacy_fast_q0_l1") or []
    legacy_statuses = {
        row.get("production_status")
        for row in legacy
        if isinstance(row, dict)
    }
    if len(legacy) != 3 or legacy_statuses != {"invalid_legacy_no_quality_boundary_or_current_provenance"}:
        bad.append("legacy q0/l1 receipts are not all marked invalid for production")

    entropy = (summary or {}).get("entropy_safety") or {}
    current = entropy.get("current_profile") or {}
    sweep = entropy.get("stripe_sweep") or {}
    safe_stripe = entropy.get("safe_stripe") or {}
    safe_quality = safe_stripe.get("quality") or {}
    safe_timing = safe_stripe.get("timing") or {}
    freq_sat = entropy.get("frequency_saturation_candidate") or {}
    freq_sat_local = freq_sat.get("local_ab") or {}
    freq_sat_decoded_delta = freq_sat_local.get("decoded_delta_saturating_vs_wrap") or {}
    freq_sat_local_delta = freq_sat_local.get("delta") or {}
    freq_sat_pi = freq_sat.get("pi_metrics") or {}
    largest_safe = sweep.get("largest_no_overflow") or {}
    first_overflow = sweep.get("first_overflow_above_safe") or {}
    if entropy.get("schema") != "mission1_native12_entropy_safety.v1":
        bad.append("missing entropy safety v1 summary")
    if entropy.get("production_status") != "raw_count_over_uint16_diagnostic":
        bad.append(f"unexpected entropy production_status={entropy.get('production_status')}")
    if entropy.get("practical_blocker") is not False:
        bad.append("raw count diagnostic is incorrectly marked as a practical blocker")
    if current.get("stripe_rows") != 384 or current.get("entropy_counter_safe") is not False:
        bad.append("current 384-row profile is not marked entropy-unsafe")
    try:
        if float(current.get("max_symbol_freq")) <= 65535.0:
            bad.append("current profile max_symbol_freq does not prove uint16 overflow risk")
    except (TypeError, ValueError):
        bad.append("current profile missing max_symbol_freq")
    try:
        if float(current.get("overflow_symbols_max")) <= 0.0:
            bad.append("current profile missing overflow symbol evidence")
    except (TypeError, ValueError):
        bad.append("current profile missing overflow_symbols_max")
    if largest_safe.get("rows") != 264 or largest_safe.get("entropy_counter_safe") is not True:
        bad.append("largest no-overflow stripe is not 264")
    if first_overflow.get("rows") != 268 or first_overflow.get("entropy_counter_safe") is not False:
        bad.append("first overflow stripe above safe boundary is not 268")
    if safe_stripe.get("rows") != 264 or safe_stripe.get("quality_profile_env_matches") is not True:
        bad.append("safe stripe profile env does not record FUSED_STRIPE_ROWS=264")
    if safe_quality.get("all_pass") is not True:
        bad.append("safe 264-row quality receipt does not pass")
    if safe_timing.get("all_storage_target_met") is not True or safe_timing.get("all_fps_target_met") is not False:
        bad.append("safe 264-row timing must pass storage and fail strict fps")
    if freq_sat.get("schema") != "mission1_jans_freq_saturate_probe.v1":
        bad.append("missing frequency saturation candidate probe")
    if freq_sat.get("decision") != "rejected_for_current_strict24_path":
        bad.append(f"unexpected frequency saturation decision={freq_sat.get('decision')}")
    if freq_sat.get("source_change_reverted") is not True:
        bad.append("frequency saturation source change must remain reverted")
    if freq_sat.get("quality_impact") != "none_detected_decoded_bayer_byte_identical":
        bad.append("frequency saturation candidate must prove byte-identical decoded Bayer")
    if freq_sat_decoded_delta.get("byte_identical") is not True:
        bad.append("frequency saturation decoded output is not byte-identical")
    try:
        if float(freq_sat_local_delta.get("bytes")) >= 0.0:
            bad.append("frequency saturation candidate did not reduce payload")
    except (TypeError, ValueError):
        bad.append("frequency saturation candidate missing payload delta")
    if freq_sat_pi.get("fps_target_met") is not False:
        bad.append("frequency saturation candidate unexpectedly passes strict fps")
    if freq_sat_pi.get("gvid_valid") is not True or freq_sat_pi.get("storage_target_met") is not True:
        bad.append("frequency saturation candidate must preserve valid media/storage")

    checks.append(Check(
        area,
        "native12 frontier evidence summary",
        "PASS" if not bad else "FAIL",
        (
            "t236/t238=fps_fail quality/storage boundary; t244/t356/t468=quality_fail; "
            "CNN recovery blocked for quality-failing speed tiers; legacy q0/l1 invalid; "
            "entropy raw-count diagnostic is non-blocking; frequency saturation speed probe rejected for strict-24 timing"
            if not bad
            else "; ".join(bad)
        ) + f" receipt={summary_path}",
    ))
    return checks


def check_native12_tokenizer_microbench_summary() -> list[Check]:
    area = "mission1_native12"
    checks: list[Check] = [
        check_file(area, "native12 tokenizer microbench", "source/app/jans_coeff_bench.c"),
    ]
    baseline_path = ARTIFACT_ROOT / "mission1_prod_jans_coeff_stats_splitdump_20260617" / "jans_coeff_bench_highpass_summary.json"
    mag4_path = ARTIFACT_ROOT / "mission1_prod_jans_mag4fast_splitdump_20260617" / "jans_coeff_bench_highpass_summary.json"
    packed_path = ARTIFACT_ROOT / "mission1_prod_jans_packedlut_splitdump_20260617" / "jans_coeff_bench_highpass_summary.json"
    packed_full_path = ARTIFACT_ROOT / "mission1_prod_jans_packedlut_GP017602_120f_24fps_20260617" / "labs_target_bench.json"
    zero_path = ARTIFACT_ROOT / "mission1_jans_zero_scan_probe_20260618" / "summary.json"
    prefetch_path = ARTIFACT_ROOT / "current_goal_jans_prefetch_probe_20260618" / "summary.json"

    baseline, err = read_json_receipt(baseline_path)
    if err:
        checks.append(Check(area, "native12 tokenizer microbench evidence", "FAIL", err))
        return checks
    mag4, err = read_json_receipt(mag4_path)
    if err:
        checks.append(Check(area, "native12 tokenizer microbench evidence", "FAIL", err))
        return checks
    packed, err = read_json_receipt(packed_path)
    if err:
        checks.append(Check(area, "native12 tokenizer microbench evidence", "FAIL", err))
        return checks
    packed_full, err = read_json_receipt(packed_full_path)
    if err:
        checks.append(Check(area, "native12 tokenizer microbench evidence", "FAIL", err))
        return checks
    zero, err = read_json_receipt(zero_path)
    if err:
        checks.append(Check(area, "native12 tokenizer microbench evidence", "FAIL", err))
        return checks
    prefetch, err = read_json_receipt(prefetch_path)
    if err:
        checks.append(Check(area, "native12 tokenizer microbench evidence", "FAIL", err))
        return checks

    hot_bands = [
        "ch0_s2_w1024_h768.s32",
        "ch0_s1_w1024_h768.s32",
        "ch3_s1_w1024_h768.s32",
        "ch3_s2_w1024_h768.s32",
        "ch1_s2_w1024_h768.s32",
    ]

    def rows_by_band(payload: dict) -> dict[str, dict]:
        return {
            str(row.get("band")): row
            for row in payload.get("rows", [])
            if isinstance(row, dict) and row.get("band") is not None
        }

    base_rows = rows_by_band(baseline or {})
    mag4_rows = rows_by_band(mag4 or {})
    packed_rows = rows_by_band(packed or {})
    bad: list[str] = []
    for label, payload in (("baseline", baseline), ("mag4", mag4), ("packed_lut", packed)):
        if (payload or {}).get("schema") != "gpr_jans_coeff_bench_summary.v1":
            bad.append(f"{label} schema={(payload or {}).get('schema')}")
        if (payload or {}).get("stripe_rows") != 384 or (payload or {}).get("defer_rans") != 1:
            bad.append(f"{label} not measured at stripe_rows=384/defer_rans=1")
        if (payload or {}).get("missing_timing") not in ([], None):
            bad.append(f"{label} missing_timing={(payload or {}).get('missing_timing')}")

    if (mag4 or {}).get("candidate") != "jans_inline_run0_mag4_fastpath":
        bad.append("mag4 candidate label drifted")
    if (packed or {}).get("candidate") != "jans_inline_packed_run_mag_lut":
        bad.append("packed LUT candidate label drifted")

    row_wins = 0
    packed_total_wins = 0
    for band in hot_bands:
        base = base_rows.get(band)
        mag = mag4_rows.get(band)
        pack = packed_rows.get(band)
        if base is None or mag is None or pack is None:
            bad.append(f"missing hot band {band}")
            continue
        try:
            base_row = float(base.get("rows_median_ms"))
            base_fin = float(base.get("finalize_median_ms"))
            base_total = float(base.get("total_median_ms"))
            base_nonzero = float(base.get("nonzero_pct"))
            mag_row = float(mag.get("rows_median_ms"))
            packed_row = float(pack.get("rows_median_ms"))
            packed_total = float(pack.get("total_median_ms"))
        except (TypeError, ValueError):
            bad.append(f"non-numeric timing/stat for {band}")
            continue
        if base_row <= base_fin:
            bad.append(f"{band} baseline is not row-tokenizer dominated")
        if base_nonzero < 50.0:
            bad.append(f"{band} is not representative high-nonzero tokenizer load")
        if int(base.get("mag_ge2048", -1)) != 0:
            bad.append(f"{band} unexpectedly has mag_ge2048={base.get('mag_ge2048')}")
        if mag_row <= base_row:
            bad.append(f"{band} mag4 fast-path no longer regresses row timing")
        if packed_row < base_row:
            row_wins += 1
        if packed_total < base_total:
            packed_total_wins += 1

    packed_verdict = (packed_full or {}).get("verdict") or {}
    packed_timing = (packed_full or {}).get("timing") or {}
    packed_phase = ((packed_full or {}).get("bench_phase_timing") or {}).get("phase_ms") or {}
    packed_encode = packed_phase.get("encode") or {}
    packed_write = packed_phase.get("write") or {}
    try:
        packed_full_total = float(packed_timing.get("median_ms"))
        packed_full_fps = float(packed_timing.get("fps_median"))
        packed_full_encode = float(packed_encode.get("median_ms"))
        packed_full_write = float(packed_write.get("median_ms"))
    except (TypeError, ValueError):
        packed_full_total = packed_full_fps = packed_full_encode = packed_full_write = -1.0
        bad.append("packed full-target receipt missing timing")
    if row_wins < len(hot_bands) or packed_total_wins < len(hot_bands):
        bad.append(f"packed LUT microbench wins only row={row_wins}/{len(hot_bands)} total={packed_total_wins}/{len(hot_bands)}")
    if packed_verdict.get("fps_target_met") is not False:
        bad.append("packed LUT full target must remain strict-24 rejected")
    if packed_verdict.get("gvid_valid") is not True or packed_verdict.get("storage_target_met") is not True:
        bad.append("packed LUT full target must preserve valid media/storage")
    if packed_full_total <= (1000.0 / 24.0) or packed_full_fps >= 24.0:
        bad.append("packed LUT full target unexpectedly clears strict 24 fps")
    if packed_full_encode <= packed_full_write * 5.0:
        bad.append("packed LUT full target is no longer encode-dominant")

    zero_agg = (zero or {}).get("aggregate") or {}
    try:
        zero_total_delta = float(zero_agg.get("median_total_delta_pct"))
    except (TypeError, ValueError):
        zero_total_delta = -999.0
        bad.append("zero-scan summary missing aggregate median_total_delta_pct")
    if (zero or {}).get("schema") != "mission1_jans_zero_scan_probe.v1":
        bad.append(f"zero-scan schema={(zero or {}).get('schema')}")
    if (zero or {}).get("decision") != "rejected_regressed_microbench":
        bad.append(f"zero-scan decision={(zero or {}).get('decision')}")
    if zero_agg.get("all_byte_counts_same") is not True:
        bad.append("zero-scan did not prove byte-count identity")
    if zero_total_delta <= 0.0:
        bad.append("zero-scan no longer shows aggregate total regression")

    prefetch_local = (prefetch or {}).get("local_microbench") or {}
    prefetch_delta = prefetch_local.get("delta_candidate_minus_baseline_ms") or {}
    prefetch_ab = (prefetch or {}).get("local_ab") or {}
    prefetch_pi = (prefetch or {}).get("pi_metrics") or {}
    try:
        prefetch_local_delta = float(prefetch_delta.get("total_median_ms"))
        prefetch_pi_total = float(prefetch_pi.get("total_median_ms"))
        prefetch_pi_fps = float(prefetch_pi.get("fps_median"))
    except (TypeError, ValueError):
        prefetch_local_delta = 999.0
        prefetch_pi_total = -1.0
        prefetch_pi_fps = 999.0
        bad.append("prefetch summary missing numeric local/Pi timing")
    if (prefetch or {}).get("schema") != "mission1_jans_prefetch64_probe.v1":
        bad.append(f"prefetch schema={(prefetch or {}).get('schema')}")
    if (prefetch or {}).get("decision") != "rejected_target_total_regression":
        bad.append(f"prefetch decision={(prefetch or {}).get('decision')}")
    if (prefetch or {}).get("source_change_reverted") is not True:
        bad.append("prefetch source change must remain reverted")
    if prefetch_ab.get("byte_identical") is not True:
        bad.append("prefetch did not prove local byte identity")
    if prefetch_local_delta >= 0.0:
        bad.append("prefetch no longer records local microbench win")
    if prefetch_pi.get("gvid_valid") is not True or prefetch_pi.get("storage_target_met") is not True:
        bad.append("prefetch target receipt must preserve valid media/storage")
    if prefetch_pi.get("fps_target_met") is not False or prefetch_pi_total <= (1000.0 / 24.0) or prefetch_pi_fps >= 24.0:
        bad.append("prefetch target receipt no longer proves strict-24 rejection")

    checks.append(Check(
        area,
        "native12 tokenizer microbench evidence",
        "PASS" if not bad else "FAIL",
        (
            f"baseline hot bands row-dominated; mag4 rejected; packed LUT wins {row_wins}/{len(hot_bands)} "
            f"hot rows but full target rejects at {packed_full_total:.3f}ms/{packed_full_fps:.3f}fps "
            f"encode={packed_full_encode:.3f}ms write={packed_full_write:.3f}ms; "
            f"zero-scan rejected delta={zero_total_delta:.3f}%; "
            f"prefetch rejected despite local delta={prefetch_local_delta:.3f}ms "
            f"at target {prefetch_pi_total:.3f}ms/{prefetch_pi_fps:.3f}fps"
            if not bad
            else "; ".join(bad)
        ) + f" receipts={baseline_path},{mag4_path},{packed_path},{packed_full_path},{zero_path},{prefetch_path}",
    ))
    return checks


def check_native12_unpack_frontier_summary() -> list[Check]:
    area = "mission1_native12"
    timing_path = ARTIFACT_ROOT / "mission1_unpack_asm_pass_20260617" / "timing_detail_GP017602_30f" / "labs_target_bench.json"
    chroma_path = ARTIFACT_ROOT / "mission1_chroma_specialized_t234_GP017602_120f_24fps_20260618" / "labs_target_bench.json"
    persistent_path = ARTIFACT_ROOT / "mission1_persistent_scratch_lh3_k6656_GP017602_120f_24fps_20260618" / "labs_target_bench.json"
    xscratch_path = ARTIFACT_ROOT / "mission1_unpack_xscratch_lh3_k6656_GP017602_60f_24fps_20260618" / "labs_target_bench.json"

    timing, err = read_json_receipt(timing_path)
    if err:
        return [Check(area, "native12 unpack frontier evidence", "FAIL", err)]
    chroma, err = read_json_receipt(chroma_path)
    if err:
        return [Check(area, "native12 unpack frontier evidence", "FAIL", err)]
    persistent, err = read_json_receipt(persistent_path)
    if err:
        return [Check(area, "native12 unpack frontier evidence", "FAIL", err)]
    xscratch, err = read_json_receipt(xscratch_path)
    if err:
        return [Check(area, "native12 unpack frontier evidence", "FAIL", err)]

    bad: list[str] = []
    timing_fused = (timing or {}).get("fused_timing") or {}
    timing_phase = ((timing or {}).get("bench_phase_timing") or {}).get("phase_ms") or {}
    timing_verdict = (timing or {}).get("verdict") or {}
    timing_channels = timing_fused.get("channel_component_by_channel_ms") or {}
    timing_capture = (timing or {}).get("capture") or {}
    if (timing or {}).get("schema") != "gpr_labs_target_bench.v1":
        bad.append(f"timing-detail schema={(timing or {}).get('schema')}")
    if timing_fused.get("available") is not True:
        bad.append("timing-detail receipt lacks fused_timing")
    if timing_capture.get("capture_width") != 4096 or timing_capture.get("capture_height") != 3072:
        bad.append("timing-detail receipt is not native 12MP")
    try:
        total_ms = float(((timing_phase.get("total") or {}).get("median_ms")))
        encode_ms = float(((timing_phase.get("encode") or {}).get("median_ms")))
        write_ms = float(((timing_phase.get("write") or {}).get("median_ms")))
        ch0_unpack = float((((timing_channels.get("0") or {}).get("unpack") or {}).get("median_ms")))
        ch1_unpack = float((((timing_channels.get("1") or {}).get("unpack") or {}).get("median_ms")))
        ch2_unpack = float((((timing_channels.get("2") or {}).get("unpack") or {}).get("median_ms")))
        ch3_unpack = float((((timing_channels.get("3") or {}).get("unpack") or {}).get("median_ms")))
        ch0_tokenize = float((((timing_channels.get("0") or {}).get("tokenize") or {}).get("median_ms")))
        ch3_tokenize = float((((timing_channels.get("3") or {}).get("tokenize") or {}).get("median_ms")))
    except (TypeError, ValueError):
        total_ms = encode_ms = write_ms = -1.0
        ch0_unpack = ch1_unpack = ch2_unpack = ch3_unpack = -1.0
        ch0_tokenize = ch3_tokenize = -1.0
        bad.append("timing-detail receipt missing numeric phase/channel medians")
    if timing_verdict.get("gvid_valid") is not True or timing_verdict.get("storage_target_met") is not True:
        bad.append("timing-detail receipt does not preserve valid media/storage")
    if total_ms <= (1000.0 / 24.0):
        bad.append("timing-detail receipt unexpectedly clears total strict-24")
    if encode_ms <= write_ms * 10.0:
        bad.append("timing-detail receipt is no longer encode-dominant")
    if ch2_unpack <= max(ch0_unpack, ch1_unpack, ch3_unpack):
        bad.append("ch2 unpack is no longer the measured unpack frontier")
    if ch0_tokenize <= ch0_unpack or ch3_tokenize <= ch3_unpack:
        bad.append("dense luma/GD tokenization no longer dominates unpack")

    def receipt_rejected(payload: dict, label: str, *, min_total_ms: float) -> tuple[bool, str]:
        verdict = payload.get("verdict") or {}
        phase = ((payload.get("bench_phase_timing") or {}).get("phase_ms") or {})
        timing_payload = payload.get("timing") or {}
        try:
            candidate_total = float(timing_payload.get("median_ms"))
            candidate_fps = float(timing_payload.get("fps_median"))
            candidate_encode = float((phase.get("encode") or {}).get("median_ms"))
            candidate_write = float((phase.get("write") or {}).get("median_ms"))
        except (TypeError, ValueError):
            return False, f"{label} missing timing"
        ok = (
            payload.get("schema") == "gpr_labs_target_bench.v1"
            and verdict.get("gvid_valid") is True
            and verdict.get("no_drops") is True
            and verdict.get("storage_target_met") is True
            and verdict.get("fps_target_met") is False
            and candidate_total >= min_total_ms
            and candidate_fps < 24.0
        )
        return ok, (
            f"{label}={candidate_total:.3f}ms/{candidate_fps:.3f}fps "
            f"encode={candidate_encode:.3f}ms write={candidate_write:.3f}ms"
        )

    chroma_ok, chroma_detail = receipt_rejected(chroma or {}, "chroma_split", min_total_ms=43.0)
    persistent_ok, persistent_detail = receipt_rejected(persistent or {}, "persistent_scratch", min_total_ms=44.0)
    xscratch_ok, xscratch_detail = receipt_rejected(xscratch or {}, "active_chroma_scratch", min_total_ms=47.0)
    if not chroma_ok:
        bad.append(f"chroma split rejection not proven: {chroma_detail}")
    if not persistent_ok:
        bad.append(f"persistent scratch rejection not proven: {persistent_detail}")
    if not xscratch_ok:
        bad.append(f"active chroma scratch rejection not proven: {xscratch_detail}")

    return [Check(
        area,
        "native12 unpack frontier evidence",
        "PASS" if not bad else "FAIL",
        (
            f"timing_detail total={total_ms:.3f}ms encode={encode_ms:.3f}ms write={write_ms:.3f}ms; "
            f"unpack ch0={ch0_unpack:.1f} ch1={ch1_unpack:.1f} ch2={ch2_unpack:.1f} ch3={ch3_unpack:.1f}ms; "
            f"{chroma_detail}; {persistent_detail}; {xscratch_detail}"
            if not bad
            else "; ".join(bad)
        ) + f" receipts={timing_path},{chroma_path},{persistent_path},{xscratch_path}",
    )]


def check_native12_current_repo_source_target_receipt() -> list[Check]:
    area = "mission1_native12"
    receipt_path = ARTIFACT_ROOT / "current_goal_repo_source_t236_GP017602_60f_20260618" / "labs_target_bench.json"
    receipt, err = read_json_receipt(receipt_path)
    if err:
        return [Check(area, "native12 current repo-source target receipt", "FAIL", err)]

    verdict = (receipt or {}).get("verdict") or {}
    phase = ((receipt or {}).get("bench_phase_timing") or {}).get("phase_ms") or {}
    timing = (receipt or {}).get("timing") or {}
    capture = (receipt or {}).get("capture") or {}
    storage_target = (((receipt or {}).get("storage") or {}).get("target") or {})
    bad: list[str] = []
    try:
        total_ms = float(timing.get("median_ms"))
        fps = float(timing.get("fps_median"))
        encode_ms = float((phase.get("encode") or {}).get("median_ms"))
        write_ms = float((phase.get("write") or {}).get("median_ms"))
        payload_kib = float((phase.get("payload_kib") or {}).get("median"))
    except (TypeError, ValueError):
        total_ms = fps = encode_ms = write_ms = payload_kib = -1.0
        bad.append("missing numeric timing/payload")
    if (receipt or {}).get("schema") != "gpr_labs_target_bench.v1":
        bad.append(f"schema={(receipt or {}).get('schema')}")
    if capture.get("capture_width") != 4096 or capture.get("capture_height") != 3072:
        bad.append("receipt is not native 12MP")
    if verdict.get("gvid_valid") is not True or verdict.get("no_drops") is not True:
        bad.append("current repo-source receipt does not validate media/no-drops")
    if verdict.get("interruption_recovery_proven") is not True:
        bad.append("current repo-source receipt lacks recovery proof")
    if verdict.get("storage_target_met") is not True or storage_target.get("fits_target") is not True:
        bad.append("current repo-source receipt does not pass guarded storage")
    if verdict.get("fps_target_met") is not False or total_ms <= (1000.0 / 24.0) or fps >= 24.0:
        bad.append("current repo-source receipt no longer records strict-24 miss")
    if payload_kib < 5480.0:
        bad.append("current repo-source payload is unexpectedly below the repo-source boundary")
    if encode_ms <= write_ms * 8.0:
        bad.append("current repo-source receipt is no longer encode-dominant")

    return [Check(
        area,
        "native12 current repo-source target receipt",
        "PASS" if not bad else "FAIL",
        (
            f"total={total_ms:.3f}ms fps={fps:.3f} encode={encode_ms:.3f}ms "
            f"write={write_ms:.3f}ms payload={payload_kib:.3f}KiB strict24=no "
            f"receipt={receipt_path}"
            if not bad
            else "; ".join(bad) + f" receipt={receipt_path}"
        ),
    )]


def check_native12_current_frequency_saturation_retest() -> list[Check]:
    area = "mission1_native12"
    summary_path = ARTIFACT_ROOT / "current_goal_inline_freq_saturate_t236_GP017602_summary_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        return [Check(area, "native12 accepted frequency-saturation fix", "FAIL", err)]

    baseline = (summary or {}).get("baseline_context") or {}
    sustained = (summary or {}).get("sustained_240f") or {}
    bad: list[str] = []
    try:
        baseline_payload = float(baseline.get("previous_explicit_gap_payload_kib"))
        payload = float(sustained.get("payload_kib"))
        total_ms = float(sustained.get("loop_median_ms"))
        wall_fps = float(sustained.get("wall_fps"))
        wall_gap = float(sustained.get("wall_gap_ms"))
    except (TypeError, ValueError):
        baseline_payload = payload = total_ms = wall_fps = wall_gap = -999.0
        bad.append("missing numeric accepted frequency-saturation metrics")
    if (summary or {}).get("schema") != "gpr.inline_freq_saturate_summary.v1":
        bad.append(f"schema={(summary or {}).get('schema')}")
    if (summary or {}).get("decision") != "accept_correctness_and_payload_fix_not_strict24_fix":
        bad.append(f"decision={(summary or {}).get('decision')}")
    if sustained.get("valid_gvid") is not True or sustained.get("storage_target_met") is not True:
        bad.append("accepted fix must preserve valid media/storage")
    if sustained.get("fps_target_met") is not False:
        bad.append("accepted fix unexpectedly passes strict 24fps")
    if payload >= baseline_payload:
        bad.append("accepted fix no longer records smaller payload")
    if total_ms <= 0.0 or wall_fps <= 0.0 or wall_gap <= 0.0:
        bad.append("accepted fix must still record the strict-24 timing miss")

    return [Check(
        area,
        "native12 accepted frequency-saturation fix",
        "PASS" if not bad else "FAIL",
        (
            f"payload={payload:.3f}KiB vs prior={baseline_payload:.3f}KiB; "
            f"median={total_ms:.3f}ms wall_fps={wall_fps:.3f}; strict24 still open receipt={summary_path}"
            if not bad
            else "; ".join(bad) + f" receipt={summary_path}"
        ),
    )]


def check_native12_post_saturation_stripe_sweep() -> list[Check]:
    area = "mission1_native12"
    summary_path = ARTIFACT_ROOT / "current_goal_inline_freq_saturate_stripe_sweep_GP017602_120f_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        return [Check(area, "native12 post-saturation stripe sweep", "FAIL", err)]

    rows = (summary or {}).get("rows") or []
    by_rows = {int(row.get("stripe_rows", -1)): row for row in rows if isinstance(row, dict)}
    best_loop = (summary or {}).get("best_by_loop_median_ms") or {}
    best_wall = (summary or {}).get("best_by_wall_fps") or {}
    bad: list[str] = []
    if (summary or {}).get("schema") != "gpr.current_goal.stripe_sweep_summary.v1":
        bad.append(f"schema={(summary or {}).get('schema')}")
    if (summary or {}).get("decision") != "reject_as_strict24_closure; stripe264 is the fastest observed here but remains CPU/encode-bound and below 24fps":
        bad.append(f"decision={(summary or {}).get('decision')}")
    if set(by_rows) != {256, 264, 320, 384}:
        bad.append(f"stripe rows={sorted(by_rows)}")
    if int(best_loop.get("stripe_rows", -1)) != 264 or int(best_wall.get("stripe_rows", -1)) != 264:
        bad.append("stripe264 is no longer the best row in the retained sweep")
    try:
        best_median_ms = float(best_loop.get("median_ms"))
        best_wall_fps = float(best_wall.get("wall_fps"))
        best_wall_gap = float(best_wall.get("wall_target_gap_ms"))
    except (TypeError, ValueError):
        best_median_ms = best_wall_fps = best_wall_gap = -999.0
        bad.append("missing numeric best stripe timing")
    for stripe, row in by_rows.items():
        if row.get("fps_target_met") is not False:
            bad.append(f"stripe{stripe} unexpectedly passes strict 24")
        if row.get("storage_target_met") is not True or row.get("gvid_valid") is not True or row.get("no_drops") is not True:
            bad.append(f"stripe{stripe} missing media/storage/drop proof")
    if best_median_ms <= 0.0 or best_wall_fps >= 24.0 or best_wall_gap <= 0.0:
        bad.append("best retained stripe sweep no longer records the strict-24 miss")

    return [Check(
        area,
        "native12 post-saturation stripe sweep",
        "PASS" if not bad else "FAIL",
        (
            f"best=stripe{int(best_wall.get('stripe_rows', -1))} "
            f"median={best_median_ms:.3f}ms wall_fps={best_wall_fps:.3f} "
            f"wall_gap={best_wall_gap:.3f}ms strict24=no receipt={summary_path}"
            if not bad
            else "; ".join(bad) + f" receipt={summary_path}"
        ),
    )]


def check_native12_ll_bitwriter32_probe() -> list[Check]:
    area = "mission1_native12"
    summary_path = ARTIFACT_ROOT / "current_goal_ll_bitwriter32_probe_GP017602_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        return [Check(area, "native12 accepted LL bitwriter32 timing fix", "FAIL", err)]

    byte_identity = (summary or {}).get("byte_identity") or {}
    baseline = (summary or {}).get("baseline_240f") or {}
    sustained = (summary or {}).get("sustained_240f") or {}
    delta = (summary or {}).get("sustained_delta_vs_baseline_240f") or {}
    bad: list[str] = []
    try:
        baseline_ms = float(baseline.get("median_ms"))
        sustained_ms = float(sustained.get("median_ms"))
        sustained_wall_fps = float(sustained.get("wall_fps"))
        median_delta = float(delta.get("median_ms_delta"))
        wall_gap = float(sustained.get("wall_gap_ms"))
    except (TypeError, ValueError):
        baseline_ms = sustained_ms = sustained_wall_fps = median_delta = wall_gap = -999.0
        bad.append("missing numeric LL bitwriter32 metrics")
    if (summary or {}).get("schema") != "gpr.current_goal.ll_bitwriter32_probe.v2":
        bad.append(f"schema={(summary or {}).get('schema')}")
    if (summary or {}).get("decision") != "accept_timing_improvement_not_strict24_closure":
        bad.append(f"decision={(summary or {}).get('decision')}")
    if byte_identity.get("same") is not True:
        bad.append("short gvid byte identity was not preserved")
    if (summary or {}).get("candidate_binary_sha256") != "dd6214c666d62b1b62c864b59ef8e387c76c61e2e4d2ba2461e8bbc74e4e3c26":
        bad.append("candidate binary hash changed")
    if baseline.get("gvid_valid") is not True or sustained.get("gvid_valid") is not True:
        bad.append("baseline/candidate media validity missing")
    if baseline.get("storage_target_met") is not True or sustained.get("storage_target_met") is not True:
        bad.append("baseline/candidate storage proof missing")
    if sustained.get("fps_target_met") is not False:
        bad.append("LL bitwriter32 unexpectedly closes strict 24")
    if not (median_delta < 0.0 and sustained_ms < baseline_ms and sustained_wall_fps > 23.0 and wall_gap > 0.0):
        bad.append("LL bitwriter32 no longer records the accepted near-miss timing improvement")

    return [Check(
        area,
        "native12 accepted LL bitwriter32 timing fix",
        "PASS" if not bad else "FAIL",
        (
            f"baseline={baseline_ms:.3f}ms candidate={sustained_ms:.3f}ms "
            f"delta={median_delta:.3f}ms wall_fps={sustained_wall_fps:.3f} "
            f"wall_gap={wall_gap:.3f}ms strict24=no receipt={summary_path}"
            if not bad
            else "; ".join(bad) + f" receipt={summary_path}"
        ),
    )]


def check_native12_inline_tail_flush_fix() -> list[Check]:
    area = "mission1_native12"
    checks: list[Check] = [
        check_file(area, "native12 inline jANS tail flush regression", "source/app/test_jans_inline_tail_flush.c"),
    ]
    summary_path = ARTIFACT_ROOT / "current_goal_inline_tail_flush_sanity_GP017602_30f_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        checks.append(Check(area, "native12 inline jANS tail flush sanity", "FAIL", err))
        return checks

    bad: list[str] = []
    try:
        median_ms = float(summary.get("median_ms"))
        wall_fps = float(summary.get("wall_fps"))
        payload_delta = float(summary.get("payload_kib_delta_vs_prior_timing_detail"))
    except (TypeError, ValueError):
        median_ms = wall_fps = payload_delta = 0.0
        bad.append("missing numeric tail-flush sanity metrics")

    if summary.get("schema") != "gpr.current_goal.inline_tail_flush_sanity.v1":
        bad.append(f"schema={summary.get('schema')}")
    if summary.get("decision") != "accept_correctness_fix_not_strict24_timing_closure":
        bad.append(f"decision={summary.get('decision')}")
    if summary.get("gvid_valid") is not True or summary.get("no_drops") is not True:
        bad.append("media validity/drop proof missing")
    if summary.get("storage_target_met") is not True:
        bad.append("storage proof missing")
    if summary.get("fps_target_met") is not False:
        bad.append("tail-flush sanity unexpectedly closes strict 24")
    if not (0.0 < payload_delta < 0.1 and median_ms > 41.666 and wall_fps < 24.0):
        bad.append("tail-flush sanity no longer records the expected tiny payload delta and strict-24 miss")

    checks.append(Check(
        area,
        "native12 inline jANS tail flush sanity",
        "PASS" if not bad else "FAIL",
        (
            f"median={median_ms:.3f}ms wall_fps={wall_fps:.3f} "
            f"payload_delta={payload_delta:.3f}KiB strict24=no receipt={summary_path}"
            if not bad
            else "; ".join(bad) + f" receipt={summary_path}"
        ),
    ))
    return checks


def check_native12_pgo_ofast_probe() -> list[Check]:
    area = "mission1_native12"
    summary_path = ARTIFACT_ROOT / "current_goal_pgo_ofast_probe_GP017602_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        return [Check(area, "native12 rejected PGO/code-layout probe", "FAIL", err)]

    baseline = (summary or {}).get("baseline") or {}
    pgo = (summary or {}).get("pgo") or {}
    delta = (summary or {}).get("delta") or {}
    bad: list[str] = []
    try:
        baseline_ms = float(baseline.get("median_ms"))
        pgo_ms = float(pgo.get("median_ms"))
        baseline_wall_fps = float(baseline.get("wall_fps"))
        pgo_wall_fps = float(pgo.get("wall_fps"))
        median_delta = float(delta.get("median_ms"))
        wall_fps_delta = float(delta.get("wall_fps"))
        encode_delta = float(delta.get("encode_median_ms"))
    except (TypeError, ValueError):
        baseline_ms = pgo_ms = baseline_wall_fps = pgo_wall_fps = median_delta = wall_fps_delta = encode_delta = 0.0
        bad.append("missing numeric PGO metrics")

    if (summary or {}).get("schema") != "gpr.current_goal.pgo_ofast_probe.v1":
        bad.append(f"schema={(summary or {}).get('schema')}")
    if (summary or {}).get("decision") != "reject_no_clear_timing_win":
        bad.append(f"decision={(summary or {}).get('decision')}")
    if (summary or {}).get("byte_identity") is not True:
        bad.append("PGO probe did not preserve byte-identical .gvid output")
    if baseline.get("gvid_sha256") != pgo.get("gvid_sha256"):
        bad.append("baseline and PGO .gvid hashes differ")
    if str(baseline.get("binary_sha256")) != "dd6214c666d62b1b62c864b59ef8e387c76c61e2e4d2ba2461e8bbc74e4e3c26":
        bad.append("baseline binary hash changed")
    if not (median_delta > 0.0 and encode_delta > 0.0 and wall_fps_delta < 0.0 and pgo_ms > baseline_ms):
        bad.append("PGO summary no longer proves a timing regression")

    return [Check(
        area,
        "native12 rejected PGO/code-layout probe",
        "PASS" if not bad else "FAIL",
        (
            f"baseline={baseline_ms:.3f}ms/{baseline_wall_fps:.3f}fps "
            f"pgo={pgo_ms:.3f}ms/{pgo_wall_fps:.3f}fps "
            f"delta={median_delta:.3f}ms wall_delta={wall_fps_delta:.3f}fps "
            f"receipt={summary_path}"
            if not bad
            else "; ".join(bad) + f" receipt={summary_path}"
        ),
    )]


def check_native12_write_contention_summary() -> list[Check]:
    area = "mission1_native12"
    checks: list[Check] = [
        check_file(area, "native12 write-contention summary tool", "tools/mission1_write_contention_summary.py"),
        check_file(area, "native12 write-contention regression", "tools/test/test_mission1_write_contention_summary.py"),
    ]
    summary_path = ARTIFACT_ROOT / "mission1_write_contention_summary_20260618" / "summary.json"
    summary, err = read_json_receipt(summary_path)
    if err:
        checks.append(Check(area, "native12 write-contention evidence summary", "FAIL", err))
        return checks

    best = (summary or {}).get("best_no_block_case") or {}
    real = (summary or {}).get("real_block_write_case") or {}
    latest = (summary or {}).get("latest_t236_boundary") or {}
    clean = (summary or {}).get("fresh_t236_clean_pi_probe") or {}
    followups = (summary or {}).get("recent_t236_followup_probes") or {}
    latest_encode = latest.get("encode_only_best_case") or {}
    latest_write = latest.get("real_write_best_case") or {}
    clean_no_write = clean.get("ofast_no_write") or {}
    clean_write = clean.get("ofast_real_write") or {}
    clean_pingpong = clean.get("pingpong") or {}
    sustained = followups.get("current_source_t236_sustained_240f") or {}
    sustained_metrics = sustained.get("metrics") or {}
    writer_handoff = followups.get("writer_handoff_t236") or {}
    writer_handoff_writer = writer_handoff.get("writer_handoff") or {}
    prealloc = followups.get("prealloc") or {}
    prealloc_baseline = prealloc.get("baseline") or {}
    prealloc_candidate = prealloc.get("candidate") or {}
    sdwrite = followups.get("sdwrite") or {}
    sdwrite_metrics = sdwrite.get("metrics") or {}
    lto = followups.get("lto") or {}
    lto_no_write = lto.get("no_write") or {}
    lto_real_write = lto.get("real_write") or {}
    exact_pgo = followups.get("exact_encode_pgo") or {}
    exact_pgo_baseline_encode = exact_pgo.get("baseline_encode_only") or {}
    exact_pgo_use_encode = exact_pgo.get("pgo_encode_only") or {}
    exact_pgo_use_write = exact_pgo.get("pgo_real_write") or {}
    layout_alignment = followups.get("layout_alignment") or {}
    layout_candidate = layout_alignment.get("candidate") or {}
    layout_baseline = layout_alignment.get("baseline") or {}
    ionice = followups.get("ionice") or {}
    ionice_idle = ionice.get("ionice_idle") or {}
    ionice_best_effort_low = ionice.get("ionice_best_effort_low") or {}
    sync_range = followups.get("sync_range") or {}
    sync_baseline = sync_range.get("baseline") or {}
    sync_candidate = sync_range.get("candidate") or {}
    neon_zero = followups.get("neon_zero_scan") or {}
    neon_zero_candidate = neon_zero.get("candidate") or {}
    pwritev = followups.get("pwritev") or {}
    pwritev_candidate = pwritev.get("candidate") or {}
    coalesced_header = followups.get("coalesced_header") or {}
    coalesced_initial = coalesced_header.get("initial") or {}
    coalesced_initial_candidate = coalesced_initial.get("candidate") or {}
    coalesced_native = coalesced_header.get("native_repeat") or {}
    coalesced_native_baseline = coalesced_native.get("baseline") or {}
    coalesced_native_candidate = coalesced_native.get("candidate") or {}
    dontneed = followups.get("dontneed") or {}
    dontneed_candidate = dontneed.get("candidate") or {}
    timing_detail = followups.get("timing_detail_current_t236") or {}
    timing_detail_metrics = timing_detail.get("metrics") or {}
    pinning = followups.get("pinning") or {}
    pinning_pinned = pinning.get("pinned") or {}
    scatter_async = followups.get("scatter_async_copy") or {}
    scatter_async_candidate = scatter_async.get("async_copy") or {}
    llrice = followups.get("llrice_k6556") or {}
    llrice_short_best = llrice.get("short_best") or {}
    llrice_candidate = llrice.get("candidate") or {}
    writev_index = followups.get("writev_index") or {}
    writev_index_baseline = writev_index.get("baseline") or {}
    writev_index_candidate = writev_index.get("candidate") or {}
    coalesce_index = followups.get("coalesce_index") or {}
    coalesce_index_baseline = coalesce_index.get("baseline") or {}
    coalesce_index_candidate = coalesce_index.get("candidate") or {}
    partition_abab = followups.get("partition_abab") or {}
    prealloc_baseline_total = prealloc_baseline.get("total_median_ms")
    prealloc_candidate_total = prealloc_candidate.get("total_median_ms")
    writer_handoff_gap = writer_handoff.get("strict_24_gap_ms")
    writer_handoff_encode = writer_handoff.get("encode_median_ms")
    writer_handoff_write = writer_handoff.get("write_median_ms")
    sustained_gap = sustained.get("strict_24_gap_ms")
    sustained_wall_fps = sustained.get("actual_wall_fps")
    sustained_source_sha = sustained.get("source_provenance_sha256")
    sustained_source_file_count = sustained.get("source_provenance_file_count")
    penalty = (summary or {}).get("block_write_penalty_ms")
    latest_gap = latest.get("strict_24_total_gap_ms")
    clean_gap = clean.get("ofast_real_write_gap_ms")
    sdwrite_gap = sdwrite.get("strict_24_gap_ms")
    lto_gap = lto.get("real_write_gap_ms")
    exact_pgo_encode_delta = exact_pgo.get("encode_only_delta_ms")
    exact_pgo_total_delta = exact_pgo.get("real_write_total_delta_ms")
    layout_total_delta = layout_alignment.get("total_delta_ms")
    layout_write_delta = layout_alignment.get("write_delta_ms")
    layout_fps_delta = layout_alignment.get("fps_delta")
    ionice_idle_delta = ionice.get("ionice_idle_total_delta_ms")
    ionice_best_effort_low_delta = ionice.get("ionice_best_effort_low_total_delta_ms")
    sync_delta = sync_range.get("total_delta_ms")
    neon_zero_encode_delta = neon_zero.get("encode_delta_ms")
    neon_zero_total_delta = neon_zero.get("total_delta_ms")
    pwritev_total_delta = pwritev.get("total_delta_ms")
    pwritev_write_delta = pwritev.get("write_delta_ms")
    coalesced_initial_delta = coalesced_initial.get("total_delta_ms")
    coalesced_native_delta = coalesced_native.get("total_delta_ms")
    dontneed_total_delta = dontneed.get("total_delta_ms")
    dontneed_write_delta = dontneed.get("write_delta_ms")
    timing_detail_wall_delta = timing_detail.get("wall_minus_fused_total_ms")
    pinning_total_delta = pinning.get("total_delta_ms")
    scatter_async_total_delta = scatter_async.get("total_delta_ms")
    scatter_async_encode_delta = scatter_async.get("encode_delta_ms")
    scatter_async_write_delta = scatter_async.get("write_delta_ms")
    scatter_async_wall_fps_delta = scatter_async.get("wall_fps_delta")
    llrice_short_delta = llrice_short_best.get("delta_total_vs_k6656_ms")
    llrice_total_delta = llrice.get("total_delta_ms")
    llrice_encode_delta = llrice.get("encode_delta_ms")
    llrice_payload_delta = llrice.get("payload_delta_kib")
    llrice_fps_delta = llrice.get("fps_delta")
    writev_index_total_delta = writev_index.get("total_delta_ms")
    writev_index_write_delta = writev_index.get("write_delta_ms")
    coalesce_index_total_delta = coalesce_index.get("total_delta_ms")
    coalesce_index_secondary_total_delta = coalesce_index.get("secondary_total_delta_ms")
    partition_abab_loop_gap = partition_abab.get("direct_loop_gap_ms")
    partition_abab_write_delta = partition_abab.get("direct_minus_encode_total_ms")
    try:
        penalty_f = float(penalty)
    except (TypeError, ValueError):
        penalty_f = -1.0
    try:
        latest_gap_f = float(latest_gap)
    except (TypeError, ValueError):
        latest_gap_f = -1.0
    try:
        clean_gap_f = float(clean_gap)
    except (TypeError, ValueError):
        clean_gap_f = -1.0
    try:
        sdwrite_gap_f = float(sdwrite_gap)
    except (TypeError, ValueError):
        sdwrite_gap_f = -1.0
    try:
        lto_gap_f = float(lto_gap)
    except (TypeError, ValueError):
        lto_gap_f = -1.0
    try:
        exact_pgo_encode_delta_f = float(exact_pgo_encode_delta)
        exact_pgo_total_delta_f = float(exact_pgo_total_delta)
    except (TypeError, ValueError):
        exact_pgo_encode_delta_f = -1.0
        exact_pgo_total_delta_f = -1.0
    try:
        layout_total_delta_f = float(layout_total_delta)
        layout_write_delta_f = float(layout_write_delta)
        layout_fps_delta_f = float(layout_fps_delta)
    except (TypeError, ValueError):
        layout_total_delta_f = -1.0
        layout_write_delta_f = -1.0
        layout_fps_delta_f = 1.0
    try:
        ionice_idle_delta_f = float(ionice_idle_delta)
        ionice_best_effort_low_delta_f = float(ionice_best_effort_low_delta)
    except (TypeError, ValueError):
        ionice_idle_delta_f = -1.0
        ionice_best_effort_low_delta_f = -1.0
    try:
        sync_delta_f = float(sync_delta)
    except (TypeError, ValueError):
        sync_delta_f = -1.0
    try:
        neon_zero_encode_delta_f = float(neon_zero_encode_delta)
        neon_zero_total_delta_f = float(neon_zero_total_delta)
    except (TypeError, ValueError):
        neon_zero_encode_delta_f = -1.0
        neon_zero_total_delta_f = -1.0
    try:
        pwritev_total_delta_f = float(pwritev_total_delta)
        pwritev_write_delta_f = float(pwritev_write_delta)
    except (TypeError, ValueError):
        pwritev_total_delta_f = -1.0
        pwritev_write_delta_f = -1.0
    try:
        coalesced_initial_delta_f = float(coalesced_initial_delta)
        coalesced_native_delta_f = float(coalesced_native_delta)
    except (TypeError, ValueError):
        coalesced_initial_delta_f = 1.0
        coalesced_native_delta_f = -1.0
    try:
        dontneed_total_delta_f = float(dontneed_total_delta)
        dontneed_write_delta_f = float(dontneed_write_delta)
    except (TypeError, ValueError):
        dontneed_total_delta_f = -1.0
        dontneed_write_delta_f = -1.0
    try:
        timing_detail_wall_delta_f = float(timing_detail_wall_delta)
    except (TypeError, ValueError):
        timing_detail_wall_delta_f = -1.0
    try:
        pinning_total_delta_f = float(pinning_total_delta)
    except (TypeError, ValueError):
        pinning_total_delta_f = -1.0
    try:
        scatter_async_total_delta_f = float(scatter_async_total_delta)
        scatter_async_encode_delta_f = float(scatter_async_encode_delta)
        scatter_async_write_delta_f = float(scatter_async_write_delta)
        scatter_async_wall_fps_delta_f = float(scatter_async_wall_fps_delta)
    except (TypeError, ValueError):
        scatter_async_total_delta_f = -1.0
        scatter_async_encode_delta_f = -1.0
        scatter_async_write_delta_f = 1.0
        scatter_async_wall_fps_delta_f = 1.0
    try:
        llrice_short_delta_f = float(llrice_short_delta)
        llrice_total_delta_f = float(llrice_total_delta)
        llrice_encode_delta_f = float(llrice_encode_delta)
        llrice_payload_delta_f = float(llrice_payload_delta)
        llrice_fps_delta_f = float(llrice_fps_delta)
    except (TypeError, ValueError):
        llrice_short_delta_f = 1.0
        llrice_total_delta_f = -1.0
        llrice_encode_delta_f = -1.0
        llrice_payload_delta_f = 1.0
        llrice_fps_delta_f = 1.0
    try:
        writev_index_total_delta_f = float(writev_index_total_delta)
        writev_index_write_delta_f = float(writev_index_write_delta)
    except (TypeError, ValueError):
        writev_index_total_delta_f = 1.0
        writev_index_write_delta_f = 1.0
    try:
        coalesce_index_total_delta_f = float(coalesce_index_total_delta)
        coalesce_index_secondary_total_delta_f = float(coalesce_index_secondary_total_delta)
    except (TypeError, ValueError):
        coalesce_index_total_delta_f = 1.0
        coalesce_index_secondary_total_delta_f = 1.0
    try:
        partition_abab_loop_gap_f = float(partition_abab_loop_gap)
        partition_abab_write_delta_f = float(partition_abab_write_delta)
    except (TypeError, ValueError):
        partition_abab_loop_gap_f = -1.0
        partition_abab_write_delta_f = -1.0
    try:
        prealloc_baseline_total_f = float(prealloc_baseline_total)
        prealloc_candidate_total_f = float(prealloc_candidate_total)
    except (TypeError, ValueError):
        prealloc_baseline_total_f = -1.0
        prealloc_candidate_total_f = -1.0
    try:
        writer_handoff_gap_f = float(writer_handoff_gap)
        writer_handoff_encode_f = float(writer_handoff_encode)
        writer_handoff_write_f = float(writer_handoff_write)
    except (TypeError, ValueError):
        writer_handoff_gap_f = -1.0
        writer_handoff_encode_f = -1.0
        writer_handoff_write_f = -1.0
    try:
        sustained_gap_f = float(sustained_gap)
        sustained_wall_fps_f = float(sustained_wall_fps)
    except (TypeError, ValueError):
        sustained_gap_f = -1.0
        sustained_wall_fps_f = -1.0
    ok = (
        (summary or {}).get("schema") == "mission1_write_contention_summary.v1"
        and (summary or {}).get("blocker_class") == "block_write_cache_contention"
        and best.get("strict_24_pass") is True
        and real.get("strict_24_pass") is False
        and penalty_f >= 3.0
        and latest.get("blocker_class") == "visual_neutral_write_handoff_margin"
        and latest.get("visual_quality_impact") == "none_detected_quality_storage_boundary"
        and latest_encode.get("strict_24_pass") is True
        and latest_write.get("strict_24_pass") is False
        and 0.0 < latest_gap_f < 2.0
        and clean.get("classification") == "visual_neutral_target_handoff_near_miss"
        and clean.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and clean_no_write.get("strict_24_pass") is True
        and clean_write.get("strict_24_pass") is False
        and 0.0 < clean_gap_f < 2.0
        and clean_pingpong.get("rejected") is True
        and sustained.get("classification") == "visual_neutral_sustained_current_source_strict24_miss"
        and sustained.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and sustained.get("frames") == 240
        and isinstance(sustained_source_sha, str)
        and len(sustained_source_sha) == 64
        and sustained_source_file_count == 565
        and sustained_metrics.get("strict_24_pass") is False
        and sustained_metrics.get("gvid_valid") is True
        and sustained_metrics.get("storage_target_met") is True
        and sustained.get("storage_fits_target") is True
        and sustained_gap_f > writer_handoff_gap_f
        and 1.7 < sustained_gap_f < 2.0
        and 22.3 < sustained_wall_fps_f < 22.7
        and writer_handoff.get("classification") == "visual_neutral_writer_handoff_not_deferred_drain"
        and writer_handoff.get("fps_target_met") is False
        and writer_handoff.get("storage_fits_target") is True
        and writer_handoff.get("deferred_writer_work_present") is False
        and writer_handoff_writer.get("deferred_writer_drain_ms") == 0.0
        and writer_handoff_encode_f > writer_handoff_write_f * 10.0
        and 1.0 < writer_handoff_gap_f < 1.2
        and prealloc.get("classification") == "rejected_visual_neutral_storage_preallocation"
        and prealloc.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and prealloc.get("rejected") is True
        and prealloc_candidate.get("strict_24_pass") is False
        and prealloc_candidate_total_f > prealloc_baseline_total_f > 0.0
        and sdwrite.get("classification") == "visual_neutral_sd_write_near_miss"
        and sdwrite.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and sdwrite_metrics.get("strict_24_pass") is False
        and 0.0 < sdwrite_gap_f < 2.0
        and lto.get("classification") == "rejected_visual_neutral_lto_build_variant"
        and lto.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and lto.get("rejected") is True
        and lto_no_write.get("strict_24_pass") is True
        and lto_real_write.get("strict_24_pass") is False
        and 0.0 < lto_gap_f < 2.0
        and exact_pgo.get("classification") == "rejected_visual_neutral_gcc_pgo_code_layout"
        and exact_pgo.get("quality_impact") == "none_byte_identical_gvid"
        and exact_pgo.get("rejected") is True
        and exact_pgo.get("byte_identical_gvid") is True
        and exact_pgo.get("compiler") == "gcc"
        and int(exact_pgo.get("profile_gcda_count", 0)) > 0
        and exact_pgo_baseline_encode.get("strict_24_pass") is False
        and exact_pgo_use_encode.get("strict_24_pass") is False
        and exact_pgo_use_write.get("strict_24_pass") is False
        and exact_pgo_encode_delta_f > 0.0
        and exact_pgo_total_delta_f > 0.0
        and layout_alignment.get("classification") == "rejected_visual_neutral_gcc_layout_alignment_flags"
        and layout_alignment.get("quality_impact") == "none_detected_codec_parameters_unchanged"
        and layout_alignment.get("rejected") is True
        and layout_candidate.get("strict_24_pass") is False
        and (layout_candidate.get("verdict") or {}).get("gvid_valid") is True
        and layout_candidate.get("payload_kib_median") == layout_baseline.get("payload_kib_median")
        and layout_total_delta_f > 0.0
        and layout_write_delta_f > 0.0
        and layout_fps_delta_f < 0.0
        and ionice.get("classification") == "rejected_visual_neutral_process_io_priority"
        and ionice.get("quality_impact") == "none_byte_identical_gvid"
        and ionice.get("rejected") is True
        and ionice.get("byte_identical_gvid") is True
        and ionice_idle.get("strict_24_pass") is False
        and ionice_best_effort_low.get("strict_24_pass") is False
        and ionice_idle_delta_f > 0.0
        and ionice_best_effort_low_delta_f > 0.0
        and sync_range.get("classification") == "rejected_visual_neutral_linux_writeback_hint"
        and sync_range.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and sync_range.get("rejected") is True
        and sync_candidate.get("gvid_valid") is True
        and sync_candidate.get("storage_target_met") is True
        and sync_candidate.get("strict_24_pass") is False
        and sync_delta_f > 0.0
        and neon_zero.get("classification") == "rejected_visual_neutral_neon_zero_scan"
        and neon_zero.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and neon_zero.get("rejected") is True
        and neon_zero_candidate.get("gvid_valid") is True
        and neon_zero_candidate.get("storage_target_met") is True
        and neon_zero_candidate.get("strict_24_pass") is False
        and neon_zero_encode_delta_f > 0.0
        and neon_zero_total_delta_f > 0.0
        and pwritev.get("classification") == "rejected_visual_neutral_explicit_offset_pwritev"
        and pwritev.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and pwritev.get("rejected") is True
        and pwritev_candidate.get("gvid_valid") is True
        and pwritev_candidate.get("storage_target_met") is True
        and pwritev_candidate.get("strict_24_pass") is False
        and pwritev_total_delta_f > 0.0
        and pwritev_write_delta_f > 0.0
        and coalesced_header.get("classification") == "rejected_visual_neutral_coalesced_header"
        and coalesced_header.get("quality_impact") == "none_byte_layout_only"
        and coalesced_header.get("rejected") is True
        and coalesced_header.get("initial_decision") == "promote_for_target_probe"
        and coalesced_header.get("native_repeat_decision") == "reject_no_timing_win"
        and coalesced_initial_candidate.get("strict_24_pass") is False
        and coalesced_initial_delta_f < 0.0
        and coalesced_native_candidate.get("strict_24_pass") is False
        and coalesced_native_delta_f > 0.0
        and coalesced_native_candidate.get("payload_kib_median") == coalesced_native_baseline.get("payload_kib_median")
        and dontneed.get("classification") == "rejected_visual_neutral_posix_fadvise_dontneed"
        and dontneed.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and dontneed.get("rejected") is True
        and dontneed.get("source_change_reverted") is True
        and dontneed_candidate.get("gvid_valid") is True
        and dontneed_candidate.get("storage_target_met") is True
        and dontneed_candidate.get("fps_target_met") is False
        and dontneed_total_delta_f > 0.0
        and dontneed_write_delta_f > 0.0
        and timing_detail.get("classification") == "stage_split_current_t236"
        and timing_detail.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and timing_detail.get("fused_total_strict_24_pass") is True
        and timing_detail_metrics.get("strict_24_pass") is False
        and float(timing_detail.get("write_median_ms", 0.0)) > 3.0
        and timing_detail_wall_delta_f > 3.0
        and pinning.get("classification") == "rejected_visual_neutral_scheduler_pinning"
        and pinning.get("quality_impact") == "codec parameters unchanged; no quality impact expected"
        and pinning.get("rejected") is True
        and pinning_pinned.get("strict_24_pass") is False
        and pinning_total_delta_f > 0.0
        and scatter_async.get("classification") == "rejected_visual_neutral_scatter_async_copy_writer"
        and scatter_async.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and scatter_async.get("rejected") is True
        and scatter_async_candidate.get("strict_24_pass") is False
        and scatter_async_total_delta_f > 0.0
        and scatter_async_encode_delta_f > 0.0
        and scatter_async_write_delta_f < 0.0
        and scatter_async_wall_fps_delta_f < 0.0
        and llrice.get("classification") == "rejected_visual_neutral_exact_ll_rice_ks"
        and llrice.get("quality_impact") == "none_exact_ll_entropy_parameter_only"
        and llrice.get("short_sweep_decision") == "no_short_strict24_pass"
        and llrice_short_best.get("ks") == "6,5,5,6"
        and llrice_short_delta_f < 0.0
        and llrice.get("rejected") is True
        and llrice_candidate.get("ks") == "6,5,5,6"
        and llrice_candidate.get("strict_24_pass") is False
        and llrice_candidate.get("gvid_valid") is True
        and llrice_payload_delta_f < 0.0
        and llrice_total_delta_f > 0.0
        and llrice_encode_delta_f > 0.0
        and llrice_fps_delta_f < 0.0
        and writev_index.get("classification") == "visual_neutral_near_miss_not_strict24"
        and writev_index.get("quality_impact") == "none_detected_payload_and_codec_settings_unchanged"
        and writev_index.get("near_miss") is True
        and writev_index_candidate.get("strict_24_pass") is False
        and writev_index_candidate.get("gvid_valid") is True
        and writev_index_candidate.get("payload_kib_median") == writev_index_baseline.get("payload_kib_median")
        and writev_index_total_delta_f < 0.0
        and writev_index_write_delta_f < 0.0
        and coalesce_index.get("classification") == "visual_neutral_near_miss_not_strict24"
        and coalesce_index.get("quality_impact") == "none_detected_payload_and_codec_settings_unchanged"
        and coalesce_index.get("near_miss") is True
        and coalesce_index.get("payload_unchanged") is True
        and coalesce_index.get("all_gvid_valid") is True
        and coalesce_index_candidate.get("strict_24_pass") is False
        and coalesce_index_candidate.get("gvid_valid") is True
        and coalesce_index_candidate.get("payload_kib_median") == coalesce_index_baseline.get("payload_kib_median")
        and coalesce_index_total_delta_f < 0.0
        and coalesce_index_secondary_total_delta_f < 0.0
        and partition_abab.get("classification") == "diagnostic_visual_neutral_encode_write_partition"
        and partition_abab.get("quality_impact") == "none_detected_no_codec_parameter_change"
        and partition_abab.get("diagnostic_only") is True
        and partition_abab.get("production_receipt") is False
        and partition_abab.get("strict_24_pass") is False
        and 1.0 < partition_abab_loop_gap_f < 2.5
        and 0.0 < partition_abab_write_delta_f < 2.0
    )
    checks.append(Check(
        area,
        "native12 write-contention evidence summary",
        "PASS" if ok else "FAIL",
        f"blocker={(summary or {}).get('blocker_class')} "
        f"best_no_block={best.get('name')}:{best.get('total_median_ms')}ms "
        f"real_write={real.get('name')}:{real.get('total_median_ms')}ms "
        f"penalty={penalty_f:.3f}ms "
        f"latest_t236={latest_write.get('name')}:{latest_write.get('total_median_ms')}ms "
        f"gap={latest_gap_f:.3f}ms "
        f"clean_gap={clean_gap_f:.3f}ms "
        f"sustained240_gap={sustained_gap_f:.3f}ms "
        f"sustained240_wall_fps={sustained_wall_fps_f:.3f} "
        f"writer_handoff_gap={writer_handoff_gap_f:.3f}ms "
        f"writer_deferred={writer_handoff.get('deferred_writer_work_present')} "
        f"pingpong_rejected={clean_pingpong.get('rejected')} "
        f"prealloc_rejected={prealloc.get('rejected')} "
        f"sd_gap={sdwrite_gap_f:.3f}ms "
        f"lto_gap={lto_gap_f:.3f}ms "
        f"exact_pgo_delta={exact_pgo_total_delta_f:.3f}ms "
        f"layout_align_delta={layout_total_delta_f:.3f}ms "
        f"ionice_delta={ionice_best_effort_low_delta_f:.3f}ms "
        f"sync_delta={sync_delta_f:.3f}ms "
        f"sync_base={sync_baseline.get('total_median_ms')}ms "
        f"sync_candidate={sync_candidate.get('total_median_ms')}ms "
        f"neon_zero_delta={neon_zero_total_delta_f:.3f}ms "
        f"pwritev_delta={pwritev_total_delta_f:.3f}ms "
        f"coalesce_native_delta={coalesced_native_delta_f:.3f}ms "
        f"dontneed_delta={dontneed_total_delta_f:.3f}ms "
        f"timing_wall_minus_fused={timing_detail_wall_delta_f:.3f}ms "
        f"pinning_delta={pinning_total_delta_f:.3f}ms "
        f"scatter_async_total_delta={scatter_async_total_delta_f:.3f}ms "
        f"scatter_async_encode_delta={scatter_async_encode_delta_f:.3f}ms "
        f"scatter_async_write_delta={scatter_async_write_delta_f:.3f}ms "
        f"scatter_async_wall_fps_delta={scatter_async_wall_fps_delta_f:.3f}fps "
        f"llrice_short_delta={llrice_short_delta_f:.3f}ms "
        f"llrice_total_delta={llrice_total_delta_f:.3f}ms "
        f"llrice_payload_delta={llrice_payload_delta_f:.3f}KiB "
        f"writev_index_delta={writev_index_total_delta_f:.3f}ms "
        f"writev_index_write_delta={writev_index_write_delta_f:.3f}ms "
        f"coalesce_index_delta={coalesce_index_total_delta_f:.3f}ms "
        f"coalesce_index_secondary_delta={coalesce_index_secondary_total_delta_f:.3f}ms "
        f"partition_abab_loop_gap={partition_abab_loop_gap_f:.3f}ms "
        f"partition_abab_write_delta={partition_abab_write_delta_f:.3f}ms "
        f"receipt={summary_path}",
    ))
    return checks


def check_native12_detail_residual_sidecar_boundary() -> list[Check]:
    area = "mission1_native12"
    checks = [
        check_file(area, "native detail-residual sidecar tool", "source/app/bayer_detail_residual_sidecar.c"),
        check_file(area, "native detail-residual sidecar regression", "tools/test/test_bayer_detail_residual_sidecar_native.sh"),
        check_file(area, "native detail-residual benchmark tool", "tools/cnn/bench_bayer_detail_residual_sidecar_native.py"),
        check_file(area, "native detail-residual benchmark regression", "tools/test/test_bench_bayer_detail_residual_sidecar_native.py"),
        check_file(area, "native12 SR production gap report tool", "tools/mission1_sr_production_gap_report.py"),
        check_file(area, "native12 SR production gap report regression", "tools/test/test_mission1_sr_production_gap_report.py"),
    ]

    summary_path = ARTIFACT_ROOT / "current_goal_sr_detail_residual_native_sidecar_threads_20260619" / "summary.json"
    if not summary_path.exists():
        checks.append(Check(area, "native detail-residual sidecar timing boundary", "FAIL", f"missing {summary_path}"))
        return checks
    try:
        summary = json.loads(summary_path.read_text())
    except Exception as exc:
        checks.append(Check(area, "native detail-residual sidecar timing boundary", "FAIL", f"bad JSON: {exc}"))
        return checks

    rows = {int(row.get("threads", 0)): row for row in summary.get("summary_rows") or []}
    t4 = rows.get(4) or {}
    t8 = rows.get(8) or {}
    t4_ms = to_float(t4.get("mean_encode_ms"))
    t8_ms = to_float(t8.get("mean_encode_ms"))
    t4_match = t4.get("all_match_baseline_sidecar") is True
    t8_match = t8.get("all_match_baseline_sidecar") is True
    keep_sidecars = summary.get("keep_sidecars")
    keep_decoded = summary.get("keep_decoded")
    sidecars = list(summary_path.parent.glob("threads_*/sidecar/*.bdrs"))
    raws = list(summary_path.parent.glob("threads_*/*.raw")) + list(summary_path.parent.glob("threads_*/decoded/*.raw"))
    live_budget_ms = 1000.0 / 24.0
    ok = (
        summary.get("schema") == "gpr.native_bayer_detail_residual_sidecar_thread_sweep.v1"
        and set(rows) >= {1, 2, 4, 8}
        and t4_ms is not None
        and t8_ms is not None
        and t4_ms > live_budget_ms
        and t8_ms > live_budget_ms
        and t4_match
        and t8_match
        and keep_sidecars is False
        and keep_decoded is False
        and not sidecars
        and not raws
    )
    checks.append(Check(
        area,
        "native detail-residual sidecar timing boundary",
        "PASS" if ok else "FAIL",
        f"schema={summary.get('schema')} "
        f"t4={t4_ms:.2f}ms t8={t8_ms:.2f}ms budget24={live_budget_ms:.2f}ms "
        f"byte_stable_4={t4_match} byte_stable_8={t8_match} "
        f"keep_sidecars={keep_sidecars} keep_decoded={keep_decoded} "
        f"payload_left={len(sidecars)} raw_left={len(raws)} "
        f"classification=offline_or_future_bitstream_not_live_capture receipt={summary_path}",
    ))

    compact_path = ARTIFACT_ROOT / "current_goal_sr_detail_residual_native_sidecar_compact_direct_20260619" / "summary.json"
    if not compact_path.exists():
        checks.append(Check(area, "native detail-residual compact sidecar boundary", "FAIL", f"missing {compact_path}"))
    else:
        try:
            compact = json.loads(compact_path.read_text())
        except Exception as exc:
            checks.append(Check(area, "native detail-residual compact sidecar boundary", "FAIL", f"bad JSON: {exc}"))
        else:
            compact_rows = {int(row.get("threads", 0)): row for row in compact.get("summary_rows") or []}
            c4 = compact_rows.get(4) or {}
            c4_ms = to_float(c4.get("mean_encode_ms"))
            c4_mib = to_float(c4.get("mean_sidecar_mib"))
            u4_mib = to_float(t4.get("mean_sidecar_mib"))
            c4_match = c4.get("all_match_baseline_sidecar") is True
            formats = set(c4.get("sidecar_formats") or [])
            compact_sidecars = list(compact_path.parent.glob("threads_*/sidecar/*.bdrs"))
            compact_raws = (
                list(compact_path.parent.glob("threads_*/*.raw")) +
                list(compact_path.parent.glob("threads_*/decoded/*.raw"))
            )
            compact_ok = (
                compact.get("schema") == "gpr.native_bayer_detail_residual_sidecar_thread_sweep.v1"
                and (compact.get("params") or {}).get("compact") is True
                and set(compact_rows) >= {1, 4}
                and c4_ms is not None
                and c4_mib is not None
                and u4_mib is not None
                and c4_mib < u4_mib
                and c4_match
                and formats == {"compact_varint_qstep"}
                and compact.get("keep_sidecars") is False
                and compact.get("keep_decoded") is False
                and not compact_sidecars
                and not compact_raws
            )
            c4_ms_s = f"{c4_ms:.2f}" if c4_ms is not None else "None"
            c4_mib_s = f"{c4_mib:.2f}" if c4_mib is not None else "None"
            u4_mib_s = f"{u4_mib:.2f}" if u4_mib is not None else "None"
            checks.append(Check(
                area,
                "native detail-residual compact sidecar boundary",
                "PASS" if compact_ok else "FAIL",
                f"compact={((compact.get('params') or {}).get('compact'))} "
                f"c4={c4_ms_s}ms compact_mib={c4_mib_s} uncompressed_mib={u4_mib_s} "
                f"formats={sorted(formats)} byte_stable_4={c4_match} "
                f"payload_left={len(compact_sidecars)} raw_left={len(compact_raws)} "
                f"receipt={compact_path}",
            ))

    q4_path = ARTIFACT_ROOT / "current_goal_sr_detail_residual_native_sidecar_q4t2_direct_20260619" / "summary.json"
    if not q4_path.exists():
        checks.append(Check(area, "native detail-residual q4/t2 direct compact timing", "FAIL", f"missing {q4_path}"))
    else:
        try:
            q4 = json.loads(q4_path.read_text())
        except Exception as exc:
            checks.append(Check(area, "native detail-residual q4/t2 direct compact timing", "FAIL", f"bad JSON: {exc}"))
        else:
            q4_rows = {int(row.get("threads", 0)): row for row in q4.get("summary_rows") or []}
            q4_t4 = q4_rows.get(4) or {}
            q4_params = q4.get("params") or {}
            q4_mean_ms = to_float(q4_t4.get("mean_encode_ms"))
            q4_median_ms = to_float(q4_t4.get("median_encode_ms"))
            q4_max_ms = to_float(q4_t4.get("max_encode_ms"))
            q4_decode_ms = to_float(q4_t4.get("mean_decode_ms"))
            q4_sidecar_mib = to_float(q4_t4.get("mean_sidecar_mib"))
            q4_match = q4_t4.get("all_match_baseline_sidecar") is True
            q4_formats = set(q4_t4.get("sidecar_formats") or [])
            q4_payloads = list(q4_path.parent.glob("threads_*/*.bdrs")) + list(q4_path.parent.glob("threads_*/sidecar/*.bdrs"))
            q4_raws = list(q4_path.parent.glob("threads_*/*.raw")) + list(q4_path.parent.glob("threads_*/decoded/*.raw"))
            q4_ok = (
                q4.get("schema") == "gpr.native_bayer_detail_residual_sidecar_thread_sweep.v1"
                and q4_params.get("compact") is True
                and q4_params.get("quant_step") == 4
                and q4_params.get("residual_threshold") == 2
                and q4_params.get("significant_detail_threshold") == 2
                and q4_params.get("plane_mask") == 15
                and q4_mean_ms is not None
                and q4_mean_ms < 42.0
                and q4_median_ms is not None
                and q4_median_ms < live_budget_ms
                and q4_max_ms is not None
                and q4_max_ms > live_budget_ms
                and q4_decode_ms is not None
                and q4_decode_ms < 24.0
                and q4_sidecar_mib is not None
                and q4_sidecar_mib < 4.6
                and q4_match
                and q4_formats == {"compact_varint_qstep"}
                and q4.get("keep_sidecars") is False
                and q4.get("keep_decoded") is False
                and not q4_payloads
                and not q4_raws
            )
            checks.append(Check(
                area,
                "native detail-residual q4/t2 direct compact timing",
                "PASS" if q4_ok else "FAIL",
                f"mean={q4_mean_ms}ms median={q4_median_ms}ms max={q4_max_ms}ms "
                f"decode={q4_decode_ms}ms sidecar_mib={q4_sidecar_mib} "
                f"byte_stable_4={q4_match} formats={sorted(q4_formats)} "
                f"payload_left={len(q4_payloads)} raw_left={len(q4_raws)} "
                f"classification=near_24fps_component_not_end_to_end receipt={q4_path}",
            ))

    broad_path = ARTIFACT_ROOT / "current_goal_sr_detail_residual_q4t2_broad_gate_20260619" / "summary.json"
    if not broad_path.exists():
        checks.append(Check(area, "native detail-residual q4/t2 broad SR gate", "FAIL", f"missing {broad_path}"))
    else:
        try:
            broad = json.loads(broad_path.read_text())
        except Exception as exc:
            checks.append(Check(area, "native detail-residual q4/t2 broad SR gate", "FAIL", f"bad JSON: {exc}"))
        else:
            mission = broad.get("mission42") or {}
            z8 = broad.get("z8_all24") or {}
            interpretation = broad.get("interpretation") or {}
            mission_rmse = to_float(mission.get("rmse_improvement_pct_mean"))
            mission_grad = to_float(mission.get("gradient_mae_improvement_pct_min"))
            z8_rmse = to_float(z8.get("rmse_improvement_pct_mean"))
            z8_grad = to_float(z8.get("gradient_mae_improvement_pct_mean"))
            z8_grad_min = to_float(z8.get("gradient_mae_improvement_pct_min"))
            high_manifest = Path(str(broad.get("z8_high_target_manifest") or ""))
            expected_high_manifest_sha = str(broad.get("z8_high_target_manifest_sha256") or "")
            actual_high_manifest_sha = sha256_file(high_manifest) if high_manifest.exists() else ""
            broad_ok = (
                broad.get("schema") == "current_goal_sr_detail_residual_q4t2_broad_gate.v1"
                and broad.get("candidate") == "q4_t2_all_detail_residual_sidecar_plus_preclean_step0200_sr"
                and broad.get("quant_step") == 4
                and broad.get("residual_threshold") == 2
                and broad.get("significant_detail_threshold") == 2
                and broad.get("sidecar_planes") == "all"
                and int(mission.get("image_count", 0)) == 42
                and int(z8.get("image_count", 0)) == 24
                and mission_rmse is not None
                and mission_rmse > 50.0
                and mission_grad is not None
                and mission_grad > 8.0
                and z8_rmse is not None
                and z8_rmse > 40.0
                and z8_grad is not None
                and 2.0 < z8_grad < 4.0
                and z8_grad_min is not None
                and z8_grad_min > 2.0
                and interpretation.get("production_status") == "candidate_evidence_not_final_production"
                and "not a complete texture-placement solution" in str(interpretation.get("z8_all24") or "")
                and expected_high_manifest_sha
                and actual_high_manifest_sha == expected_high_manifest_sha
            )
            checks.append(Check(
                area,
                "native detail-residual q4/t2 broad SR gate",
                "PASS" if broad_ok else "FAIL",
                f"mission={int(mission.get('image_count', 0))} "
                f"mission_rmse_mean={mission_rmse} mission_grad_min={mission_grad} "
                f"z8={int(z8.get('image_count', 0))} z8_rmse_mean={z8_rmse} "
                f"z8_grad_mean={z8_grad} z8_grad_min={z8_grad_min} "
                f"status={interpretation.get('production_status')} "
                f"high_manifest_ok={actual_high_manifest_sha == expected_high_manifest_sha} "
                f"receipt={broad_path}",
            ))

    aware_root = ARTIFACT_ROOT / "current_goal_sr_q4t2_sidecar_aware_train_20260619"
    aware_summary_path = aware_root / "sidecar_aware_preclean_step0200_continue_s400" / "guarded_experiment_summary.json"
    aware_decision_path = aware_root / "sidecar_aware_preclean_step0200_continue_s400" / "q4t2_sidecar_aware_preclean_continue_s400_decision.json"
    aware_checkpoint_path = aware_root / "sidecar_aware_preclean_step0200_continue_s400" / "q4t2_sidecar_aware_preclean_continue_s400.pt"
    aware_pairs_path = aware_root / "mission42_z8_all24_q4t2_inputs_w96.npz"
    aware_multi_path = ARTIFACT_ROOT / "mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_multiframe_20260619" / "receipt.json"
    aware_retained_path = ARTIFACT_ROOT / "mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_packaging_20260619" / "receipt.json"
    aware_packaging_path = ARTIFACT_ROOT / "mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_packaging_q3_20260619" / "packaging_receipt.json"
    aware_interp_path = ARTIFACT_ROOT / "current_goal_sr_q4t2_sidecar_aware_interp_probe_20260619" / "interpolation_decision_summary.json"
    if not aware_summary_path.exists() or not aware_decision_path.exists():
        checks.append(Check(
            area,
            "q4/t2 sidecar-aware SR registry-review candidate",
            "FAIL",
            f"missing {aware_summary_path} or {aware_decision_path}",
        ))
    else:
        try:
            aware_summary = json.loads(aware_summary_path.read_text())
            aware_decision = json.loads(aware_decision_path.read_text())
            aware_multi = json.loads(aware_multi_path.read_text()) if aware_multi_path.exists() else {}
            aware_retained = json.loads(aware_retained_path.read_text()) if aware_retained_path.exists() else {}
            aware_packaging = json.loads(aware_packaging_path.read_text()) if aware_packaging_path.exists() else {}
            aware_interp = json.loads(aware_interp_path.read_text()) if aware_interp_path.exists() else {}
        except Exception as exc:
            checks.append(Check(
                area,
                "q4/t2 sidecar-aware SR registry-review candidate",
                "FAIL",
                f"bad JSON: {exc}",
            ))
        else:
            candidate = aware_decision.get("candidate") or {}
            mission_holdout = candidate.get("mission_holdout") or {}
            z8_holdout = candidate.get("z8_regenerated_holdout") or {}
            deltas = aware_decision.get("deltas_vs_q4t2_preclean_step0200") or {}
            scope = aware_decision.get("comparison_scope") or {}
            mission_scope = scope.get("mission") or {}
            z8_scope = scope.get("z8") or {}
            mission_rmse_delta = (mission_scope.get("per_image_rmse_delta") or {}).get("GP017346")
            mission_psnr_delta = (mission_scope.get("per_image_psnr14_delta") or {}).get("GP017346")
            checkpoint_sha = sha256_file(aware_checkpoint_path) if aware_checkpoint_path.exists() else ""
            pairs_sha = sha256_file(aware_pairs_path) if aware_pairs_path.exists() else ""
            summary_sha = sha256_file(aware_summary_path)
            decision_sha = sha256_file(aware_decision_path)
            multi_sha = sha256_file(aware_multi_path) if aware_multi_path.exists() else ""
            retained_sha = sha256_file(aware_retained_path) if aware_retained_path.exists() else ""
            packaging_sha = sha256_file(aware_packaging_path) if aware_packaging_path.exists() else ""
            interp_sha = sha256_file(aware_interp_path) if aware_interp_path.exists() else ""
            multi_summary = aware_multi.get("summary") or {}
            multi_fps = to_float(multi_summary.get("fps_median_decode_plus_sr"))
            multi_total = to_float((multi_summary.get("decode_plus_sr_total_s") or {}).get("median"))
            multi_rows = aware_multi.get("frames") or []
            retained_rows = aware_retained.get("frames") or []
            retained_sr = retained_rows[0].get("sr_raw_sha256") if retained_rows else None
            packaging_gpr = aware_packaging.get("editable_gpr") or {}
            packaging_gpr_metrics = packaging_gpr.get("readback_metrics") or {}
            packaging_gpr_psnr = to_float(packaging_gpr_metrics.get("psnr14_db"))
            prores = aware_packaging.get("prores_review") or {}
            prores_streams = ((prores.get("ffprobe") or {}).get("streams") or [])
            prores_codec = prores_streams[0].get("codec_name") if prores_streams else None
            interp_alphas = aware_interp.get("interpolations") or {}
            interp_a025 = (interp_alphas.get("a025") or {}).get("mission_hard4") or {}
            interp_a075 = (interp_alphas.get("a075") or {}).get("mission_hard4") or {}
            interp_z8_a075 = (interp_alphas.get("a075") or {}).get("z8_all24") or {}
            aware_ok = (
                aware_summary.get("schema") == "mission1_sr_guarded_experiment.v1"
                and aware_summary.get("decision") == "promotion_candidate_found"
                and int(aware_summary.get("candidate_count", 0)) == 4
                and aware_decision.get("decision") == "promote_for_registry_review"
                and candidate.get("checkpoint_sha256") == "a16579f2aacd6edbadc3931ab112a3ff52566bd4f8a6245c95b246b16af98bb5"
                and checkpoint_sha == candidate.get("checkpoint_sha256")
                and pairs_sha == "d6976cbf92729b78eeff7bf0c6b0f79e550c7d895bd64a7db21a61a0e9526d62"
                and summary_sha == "2635796d17f7559ca79a0c1fe39d7eeff3f019aa0b05e38e91b71215de52b5ce"
                and decision_sha == "660f22cf85c392b9e43d7ce5f525fa5f4450f51905f3629934ee48a18f1d850b"
                and int(mission_holdout.get("image_count", 0)) == 42
                and int(z8_holdout.get("image_count", 0)) == 24
                and mission_scope.get("coverage_ok") is True
                and z8_scope.get("coverage_ok") is True
                and to_float(deltas.get("mission_rmse_median")) is not None
                and to_float(deltas.get("mission_rmse_median")) > 2.9
                and to_float(deltas.get("mission_rmse_min")) is not None
                and to_float(deltas.get("mission_rmse_min")) > 1.3
                and to_float(deltas.get("z8_rmse_min")) is not None
                and to_float(deltas.get("z8_rmse_min")) > 1.7
                and to_float(deltas.get("z8_psnr14_min")) is not None
                and to_float(deltas.get("z8_psnr14_min")) > 0.26
                and to_float(mission_rmse_delta) is not None
                and to_float(mission_rmse_delta) < 0.0
                and to_float(mission_psnr_delta) is not None
                and to_float(mission_psnr_delta) < 0.0
                and multi_sha == "b79cac5b1ad12bdeeddac0bb4b53bc806b45c5822fb6ac6fe1267f5d4a6501d1"
                and retained_sha == "9bd45a49a13b344498907f7c0532a120fff2944382a9659bd1db9870f39d2e57"
                and packaging_sha == "eab82ddaa985e2ce6f1667ee5ad025f60a87fc8ee4d4e83504a3121e5975c8f8"
                and aware_multi.get("schema") == "mission1_native12_gvid_to_8k_sr_multiframe.v1"
                and int(aware_multi.get("frames_requested", 0)) == 3
                and all(int(row.get("payload_size", 0)) == 8765001 for row in multi_rows)
                and multi_fps is not None
                and 1.0 < multi_fps < 1.3
                and multi_total is not None
                and 0.8 < multi_total < 0.95
                and aware_retained.get("schema") == "mission1_native12_gvid_to_8k_sr_multiframe.v1"
                and retained_sr == "396eb8f342f3ab0b75cb4f7909f15bdbd8f7d2c525c99ad4324a6ac139c647f2"
                and aware_packaging.get("schema") == "mission1_native12_gvid_to_8k_sr_packaging.v2"
                and packaging_gpr.get("quality") == 3
                and packaging_gpr_psnr is not None
                and packaging_gpr_psnr > 52.0
                and packaging_gpr.get("gpr_to_dng_rawpy_open_shape") == [6144, 8192]
                and prores_codec == "prores"
                and interp_sha == "8b6972e2cb4dfecb05c0c89229e029c1647a06276c7937da3f9fae497c01b8da"
                and aware_interp.get("schema") == "mission1_sr_q4t2_interpolation_decision.v1"
                and aware_interp.get("decision") == "reject_interpolations_keep_step400_as_review_candidate"
                and aware_interp.get("production_status") == "not_production_offline_registry_review_only"
                and int(interp_a025.get("image_count", 0)) == 4
                and int(interp_z8_a075.get("image_count", 0)) == 24
                and to_float(interp_a075.get("rmse_lift_min")) is not None
                and to_float(interp_a075.get("rmse_lift_min")) > to_float(interp_a025.get("rmse_lift_min"))
                and to_float(interp_a075.get("gradient_lift_min")) is not None
                and to_float(interp_a075.get("gradient_lift_min")) < to_float(interp_a025.get("gradient_lift_min"))
            )
            checks.append(Check(
                area,
                "q4/t2 sidecar-aware SR registry-review candidate",
                "PASS" if aware_ok else "FAIL",
                f"decision={aware_decision.get('decision')} "
                f"mission={int(mission_holdout.get('image_count', 0))} "
                f"z8={int(z8_holdout.get('image_count', 0))} "
                f"mission_rmse_median_delta={deltas.get('mission_rmse_median')} "
                f"z8_rmse_min_delta={deltas.get('z8_rmse_min')} "
                f"gp017346_rmse_delta={mission_rmse_delta} "
                f"gvid_fps={multi_fps} packaging_psnr={packaging_gpr_psnr} "
                f"interp_decision={aware_interp.get('decision')} "
                f"classification=registry_review_candidate_not_production "
                f"receipt={aware_summary_path}",
            ))

    gap_report_path = ARTIFACT_ROOT / "current_goal_sr_production_gap_report_20260619" / "summary.json"
    if not gap_report_path.exists():
        checks.append(Check(area, "native12 8K SR production gap report", "FAIL", f"missing {gap_report_path}"))
    else:
        try:
            gap_report = json.loads(gap_report_path.read_text())
        except Exception as exc:
            checks.append(Check(area, "native12 8K SR production gap report", "FAIL", f"bad JSON: {exc}"))
        else:
            gap_quality = gap_report.get("quality") if isinstance(gap_report.get("quality"), dict) else {}
            gap_runtime = gap_report.get("runtime") if isinstance(gap_report.get("runtime"), dict) else {}
            gap_packaging = gap_report.get("packaging") if isinstance(gap_report.get("packaging"), dict) else {}
            gap_capture = (
                gap_report.get("native12_capture_dependency")
                if isinstance(gap_report.get("native12_capture_dependency"), dict)
                else {}
            )
            blockers = {
                str(row.get("name"))
                for row in (gap_report.get("blockers") or [])
                if isinstance(row, dict)
            }
            required_blockers = {
                "offline_scope",
                "live_timing",
                "mission_paired_regression",
                "mission_metadata_refresh",
                "native12_capture_strict24",
                "checkpoint_interpolation_rejected",
            }
            rmse_regressions = gap_quality.get("mission_paired_rmse_regressions") or {}
            psnr_regressions = gap_quality.get("mission_paired_psnr14_regressions") or {}
            gap_fps = to_float(gap_runtime.get("decode_plus_sr_fps_median"))
            gap_psnr = to_float(gap_packaging.get("editable_gpr_psnr14_db"))
            gap_ok = (
                gap_report.get("schema") == "mission1_sr_production_gap_report.v1"
                and gap_report.get("production_ready") is False
                and gap_report.get("production_status") == "offline_registry_review_not_production"
                and gap_report.get("pipeline_id") == (
                    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_q4t2_sidecar_aware_s400_v1+"
                    "demosaic=sips_via_gpr_tools"
                )
                and gap_quality.get("quality_evidence_ok_for_registry_review") is True
                and gap_packaging.get("packaging_ok") is True
                and gap_runtime.get("live_timing_ok") is False
                and gap_capture.get("strict24_capture_ok") is False
                and gap_capture.get("decision") == "strict24_open_wall_throughput_gap"
                and required_blockers.issubset(blockers)
                and rmse_regressions.get("GP017346") is not None
                and to_float(rmse_regressions.get("GP017346")) < 0.0
                and psnr_regressions.get("GP017346") is not None
                and to_float(psnr_regressions.get("GP017346")) < 0.0
                and gap_fps is not None
                and 1.0 < gap_fps < 1.3
                and gap_psnr is not None
                and gap_psnr > 52.0
            )
            checks.append(Check(
                area,
                "native12 8K SR production gap report",
                "PASS" if gap_ok else "FAIL",
                f"status={gap_report.get('production_status')} blockers={sorted(blockers)} "
                f"fps={gap_fps} gp017346_rmse_delta={rmse_regressions.get('GP017346')} "
                f"packaging_psnr={gap_psnr} capture={gap_capture.get('decision')} "
                f"receipt={gap_report_path}",
            ))

    status_doc = REPO / "docs/MISSION1_SR_PRODUCTION_STATUS_2026-06-18.md"
    if not status_doc.exists():
        checks.append(Check(area, "native detail-residual sidecar status doc", "FAIL", f"missing {status_doc.relative_to(REPO)}"))
        return checks
    text = status_doc.read_text(errors="ignore")
    doc_needles = [
        "Native sidecar thread sweep",
        "BDRS_ENCODE_THREADS",
        "BDRS_COMPACT",
        "compact_varint_qstep",
        "direct threaded compact",
        "byte-identical",
        "not be folded into the live",
        "without further algorithmic compression",
    ]
    missing = [needle for needle in doc_needles if needle not in text]
    checks.append(Check(
        area,
        "native detail-residual sidecar status doc",
        "PASS" if not missing else "FAIL",
        "documents offline/live boundary" if not missing else f"missing {missing}",
    ))
    return checks


def check_native12_strict24_gap_report() -> list[Check]:
    area = "mission1_native12"
    checks = [
        check_file(area, "native12 strict-24 gap report tool", "tools/mission1_strict24_gap_report.py"),
        check_file(area, "native12 strict-24 gap report regression", "tools/test/test_mission1_strict24_gap_report.py"),
        check_file(area, "native12 strict-24 probe summary tool", "tools/mission1_strict24_probe_matrix_summary.py"),
        check_file(area, "native12 strict-24 probe summary regression", "tools/test/test_mission1_strict24_probe_matrix_summary.py"),
    ]
    summary_path = ARTIFACT_ROOT / "current_goal_mission1_strict24_gap_report_20260619" / "summary.json"
    if not summary_path.exists():
        checks.append(Check(area, "native12 strict-24 gap report evidence", "FAIL", f"missing {summary_path}"))
        return checks
    try:
        summary = json.loads(summary_path.read_text())
    except Exception as exc:
        checks.append(Check(area, "native12 strict-24 gap report evidence", "FAIL", f"bad JSON: {exc}"))
        return checks
    loop = to_float(summary.get("required_loop_reduction_ms"))
    wall = to_float(summary.get("required_wall_reduction_ms"))
    best_loop = summary.get("best_loop_candidate") if isinstance(summary.get("best_loop_candidate"), dict) else {}
    best_wall = summary.get("best_wall_candidate") if isinstance(summary.get("best_wall_candidate"), dict) else {}
    plan = summary.get("optimization_plan") if isinstance(summary.get("optimization_plan"), dict) else {}
    rejected = plan.get("already_rejected") if isinstance(plan.get("already_rejected"), list) else []
    do_not_repeat = plan.get("do_not_repeat") if isinstance(plan.get("do_not_repeat"), list) else []
    near_misses = plan.get("near_miss_candidates") if isinstance(plan.get("near_miss_candidates"), list) else []
    acceptance = plan.get("acceptance_criteria") if isinstance(plan.get("acceptance_criteria"), list) else []
    probe_matrix = plan.get("next_probe_matrix") if isinstance(plan.get("next_probe_matrix"), list) else []
    probe_ids = [row.get("probe_id") for row in probe_matrix if isinstance(row, dict)]
    probes_by_id = {row.get("probe_id"): row for row in probe_matrix if isinstance(row, dict)}
    expected_probe_ids = [
        "current_source_sustained_repeat_240f",
        "encoder_hotrow_profile_30f",
        "camera_like_handoff_floor_240f",
        "indexed_writev_plus_clean_source_ab_240f",
        "target_hardware_or_20fps_decision_receipt",
    ]
    hotrow_probe = probes_by_id.get("encoder_hotrow_profile_30f") if isinstance(probes_by_id.get("encoder_hotrow_profile_30f"), dict) else {}
    handoff_probe = probes_by_id.get("camera_like_handoff_floor_240f") if isinstance(probes_by_id.get("camera_like_handoff_floor_240f"), dict) else {}
    writev_probe = probes_by_id.get("indexed_writev_plus_clean_source_ab_240f") if isinstance(probes_by_id.get("indexed_writev_plus_clean_source_ab_240f"), dict) else {}
    handoff_acceptance = handoff_probe.get("acceptance") if isinstance(handoff_probe.get("acceptance"), dict) else {}
    writev_acceptance = writev_probe.get("acceptance") if isinstance(writev_probe.get("acceptance"), dict) else {}
    ok = (
        summary.get("schema") == "mission1_strict24_gap_report.v1"
        and summary.get("decision") == "strict24_open_wall_throughput_gap"
        and summary.get("quality_storage_boundary_ok") is True
        and int(summary.get("strict24_pass_count", -1)) == 0
        and loop is not None
        and wall is not None
        and 0.5 < loop < 1.5
        and wall > loop
        and wall > 2.0
        and best_loop.get("name") == "t236_quality_storage_boundary_real_write"
        and best_wall.get("name") == "explicit_gap_t236_240f"
        and "wall time" in str(summary.get("next_optimization_target", ""))
        and plan.get("status") == "visual_quality_and_storage_are_not_the_current_blocker"
        and plan.get("dominant_gap") == "wall"
        and len(rejected) >= 10
        and len(near_misses) >= 3
        and "prealloc" in do_not_repeat
        and "exact_encode_pgo" in do_not_repeat
        and "coalesce_scout" in do_not_repeat
        and any("whole-run wall throughput" in str(item) for item in acceptance)
        and probe_ids == expected_probe_ids
        and ((hotrow_probe.get("env") or {}).get("JANS_INLINE_PROFILE") == "1")
        and ((hotrow_probe.get("env") or {}).get("GPR_INLINE_DENOISE_HARD") == "1")
        and ((hotrow_probe.get("env") or {}).get("GPR_INLINE_DENOISE_T_CH2_LH") == "3")
        and to_float(handoff_acceptance.get("wall_save_ms_needed")) is not None
        and writev_acceptance.get("both_orders_win") is True
    )
    checks.append(Check(
        area,
        "native12 strict-24 gap report evidence",
        "PASS" if ok else "FAIL",
        f"decision={summary.get('decision')} loop_gap={loop:.3f}ms wall_gap={wall:.3f}ms "
        f"best_loop={best_loop.get('name')} best_wall={best_wall.get('name')} "
        f"target={summary.get('next_optimization_target')} rejected_paths={len(rejected)} "
        f"near_misses={len(near_misses)} probes={len(probe_ids)} receipt={summary_path}",
    ))
    probe_summary_path = ARTIFACT_ROOT / "current_goal_strict24_probe_matrix_20260619" / "summary.json"
    if not probe_summary_path.exists():
        checks.append(Check(area, "native12 strict-24 probe summary evidence", "FAIL", f"missing {probe_summary_path}"))
        return checks
    try:
        probe_summary = json.loads(probe_summary_path.read_text())
    except Exception as exc:
        checks.append(Check(area, "native12 strict-24 probe summary evidence", "FAIL", f"bad JSON: {exc}"))
        return checks
    repeat = probe_summary.get("current_source_repeat") if isinstance(probe_summary.get("current_source_repeat"), dict) else {}
    repeat_delta = probe_summary.get("current_vs_previous") if isinstance(probe_summary.get("current_vs_previous"), dict) else {}
    production = probe_summary.get("production_profile_summary") if isinstance(probe_summary.get("production_profile_summary"), dict) else {}
    production_repeats = probe_summary.get("production_profile_repeats") if isinstance(probe_summary.get("production_profile_repeats"), list) else []
    production_best = production.get("best") if isinstance(production.get("best"), dict) else {}
    production_latest = production.get("latest") if isinstance(production.get("latest"), dict) else {}
    production_best_delta = (
        probe_summary.get("production_profile_best_vs_current")
        if isinstance(probe_summary.get("production_profile_best_vs_current"), dict)
        else {}
    )
    production_latest_delta = (
        probe_summary.get("production_profile_latest_vs_current")
        if isinstance(probe_summary.get("production_profile_latest_vs_current"), dict)
        else {}
    )
    hotrow = probe_summary.get("hotrow_diagnostics") if isinstance(probe_summary.get("hotrow_diagnostics"), dict) else {}
    production_hotrow = (
        probe_summary.get("production_profile_labeled_hotrow")
        if isinstance(probe_summary.get("production_profile_labeled_hotrow"), dict)
        else {}
    )
    production_hotrow_diag = (
        probe_summary.get("production_profile_labeled_hotrow_diagnostics")
        if isinstance(probe_summary.get("production_profile_labeled_hotrow_diagnostics"), dict)
        else {}
    )
    rank = hotrow.get("channel_rank_by_tokenize") if isinstance(hotrow.get("channel_rank_by_tokenize"), list) else []
    top_channels = [str(row.get("channel")) for row in rank[:2] if isinstance(row, dict)]
    label_rank = (
        production_hotrow_diag.get("jans_label_rank_by_overflow")
        if isinstance(production_hotrow_diag.get("jans_label_rank_by_overflow"), list)
        else []
    )
    top_labels = [str(row.get("label")) for row in label_rank[:4] if isinstance(row, dict)]
    total_ms = to_float(repeat.get("total_median_ms"))
    fps = to_float(repeat.get("fps_median"))
    wall_fps = to_float(repeat.get("wall_fps"))
    payload_kib = to_float(repeat.get("payload_kib_median"))
    total_delta = to_float(repeat_delta.get("total_median_ms_delta"))
    encode_delta = to_float(repeat_delta.get("encode_median_ms_delta"))
    payload_delta = to_float(repeat_delta.get("payload_kib_median_delta"))
    overflow_max = to_float(hotrow.get("overflow_symbols_max"))
    max_symbol_freq = to_float(hotrow.get("max_symbol_freq_max"))
    production_count = int(production.get("count", -1))
    production_best_total_ms = to_float(production_best.get("total_median_ms"))
    production_best_fps = to_float(production_best.get("fps_median"))
    production_best_wall_fps = to_float(production_best.get("wall_fps"))
    production_best_payload_kib = to_float(production_best.get("payload_kib_median"))
    production_best_total_delta = to_float(production_best_delta.get("total_median_ms_delta"))
    production_best_payload_delta = to_float(production_best_delta.get("payload_kib_median_delta"))
    production_latest_total_ms = to_float(production_latest.get("total_median_ms"))
    production_latest_wall_fps = to_float(production_latest.get("wall_fps"))
    production_latest_total_delta = to_float(production_latest_delta.get("total_median_ms_delta"))
    production_latest_gap = to_float(production.get("latest_total_gap_ms"))
    production_latest_wall_gap = to_float(production.get("latest_wall_gap_ms"))
    production_hotrow_total_ms = to_float(production_hotrow.get("total_median_ms"))
    production_hotrow_wall_fps = to_float(production_hotrow.get("wall_fps"))
    production_hotrow_profile_lines = int(production_hotrow_diag.get("jans_profile_lines", 0))
    production_hotrow_overflow = to_float(production_hotrow_diag.get("overflow_symbols_max"))
    production_hotrow_max_symbol = to_float(production_hotrow_diag.get("max_symbol_freq_max"))
    probe_ok = (
        probe_summary.get("schema") == "mission1_strict24_probe_matrix_summary.v1"
        and probe_summary.get("decision") == "strict24_still_open_current_source_regressed"
        and probe_summary.get("strict24_closed") is False
        and repeat.get("storage_target_met") is True
        and repeat.get("gvid_valid") is True
        and repeat.get("no_drops") is True
        and repeat.get("interruption_recovery_proven") is True
        and total_ms is not None
        and 44.0 < total_ms < 44.5
        and fps is not None
        and 22.4 < fps < 22.8
        and wall_fps is not None
        and 22.0 < wall_fps < 22.4
        and payload_kib is not None
        and 5300.0 < payload_kib < 5450.0
        and total_delta is not None
        and total_delta > 0.0
        and encode_delta is not None
        and encode_delta > 0.0
        and payload_delta is not None
        and payload_delta < 0.0
        and production_count >= 3
        and len(production_repeats) >= 3
        and production.get("strict24_any_closed") is False
        and production_best.get("storage_target_met") is True
        and production_best.get("gvid_valid") is True
        and production_best.get("no_drops") is True
        and production_best.get("interruption_recovery_proven") is True
        and production_best.get("fps_target_met") is False
        and production_best_total_ms is not None
        and 42.5 < production_best_total_ms < 43.1
        and production_best_fps is not None
        and 23.2 < production_best_fps < 23.6
        and production_best_wall_fps is not None
        and 22.7 < production_best_wall_fps < 23.1
        and production_best_payload_kib is not None
        and 5300.0 < production_best_payload_kib < 5400.0
        and production_best_total_delta is not None
        and production_best_total_delta < -1.0
        and production_best_payload_delta is not None
        and production_best_payload_delta < 0.0
        and production_latest.get("storage_target_met") is True
        and production_latest.get("gvid_valid") is True
        and production_latest.get("no_drops") is True
        and production_latest.get("interruption_recovery_proven") is True
        and production_latest.get("fps_target_met") is False
        and production_latest_total_ms is not None
        and 43.2 < production_latest_total_ms < 43.7
        and production_latest_wall_fps is not None
        and 22.5 < production_latest_wall_fps < 22.9
        and production_latest_total_delta is not None
        and production_latest_total_delta < 0.0
        and production_latest_gap is not None
        and 1.4 < production_latest_gap < 2.1
        and production_latest_wall_gap is not None
        and 1.8 < production_latest_wall_gap < 3.0
        and hotrow.get("instrumented") is True
        and int(hotrow.get("fused_timing_lines", 0)) >= 200
        and int(hotrow.get("jans_profile_lines", 0)) >= 300
        and top_channels == ["3", "0"]
        and overflow_max is not None
        and overflow_max >= 1.0
        and max_symbol_freq is not None
        and max_symbol_freq > 65535.0
        and production_hotrow.get("storage_target_met") is True
        and production_hotrow.get("gvid_valid") is True
        and production_hotrow.get("no_drops") is True
        and production_hotrow.get("interruption_recovery_proven") is True
        and production_hotrow_total_ms is not None
        and 49.0 < production_hotrow_total_ms < 50.0
        and production_hotrow_wall_fps is not None
        and 18.0 < production_hotrow_wall_fps < 19.5
        and production_hotrow_diag.get("instrumented") is True
        and production_hotrow_profile_lines >= 300
        and production_hotrow_overflow is not None
        and production_hotrow_overflow >= 2.0
        and production_hotrow_max_symbol is not None
        and production_hotrow_max_symbol > 90000.0
        and top_labels[:4] == ["ch0_b1", "ch3_b1", "ch0_b2", "ch3_b2"]
        and "production T233 profile" in str(probe_summary.get("next_target", ""))
        and "tokenization hot path" in str(probe_summary.get("next_target", ""))
    )
    def fmt_ms(value: float | None) -> str:
        return f"{value:.3f}" if value is not None else "n/a"

    checks.append(Check(
        area,
        "native12 strict-24 probe summary evidence",
        "PASS" if probe_ok else "FAIL",
        f"decision={probe_summary.get('decision')} median={fmt_ms(total_ms)}ms fps={fmt_ms(fps)} "
        f"wall_fps={fmt_ms(wall_fps)} payload={fmt_ms(payload_kib)}KiB "
        f"delta={fmt_ms(total_delta)}ms production_best={fmt_ms(production_best_total_ms)}ms "
        f"production_latest={fmt_ms(production_latest_total_ms)}ms "
        f"latest_wall={fmt_ms(production_latest_wall_fps)} "
        f"latest_gap={fmt_ms(production_latest_gap)}ms top_channels={top_channels} "
        f"top_labels={top_labels[:4]} production_hotrow={fmt_ms(production_hotrow_total_ms)}ms "
        f"overflow_max={overflow_max} receipt={probe_summary_path}",
    ))
    return checks


def check_live_preview_edge_safe_policy() -> Check:
    tool = REPO / "tools/live_preview_policy.py"
    if not tool.exists() or not git_tracked(tool):
        return Check("preview_live", "Mission 1 1024 runtime policy", "FAIL", "missing tracked tools/live_preview_policy.py")

    sys.path.insert(0, str(REPO / "tools"))
    try:
        from live_preview_policy import DEFAULT_POLICY_ID, materialize_policy  # type: ignore

        policy = materialize_policy(DEFAULT_POLICY_ID)
    except Exception as exc:
        return Check("preview_live", "Mission 1 1024 runtime policy", "FAIL", f"policy import/materialize failed: {exc}")

    expected_viewport = {"x": 0, "y": 0, "width": 1024, "height": 768}
    if policy.get("production_path_id") != "preview_live_mission1_1024":
        return Check("preview_live", "Mission 1 1024 runtime policy", "FAIL", "unexpected production_path_id")
    if policy.get("raw_target") != "mission1_preview_1024":
        return Check("preview_live", "Mission 1 1024 runtime policy", "FAIL", "unexpected raw_target")
    if policy.get("display_viewport") != expected_viewport:
        return Check("preview_live", "Mission 1 1024 runtime policy", "FAIL", f"viewport={policy.get('display_viewport')}")
    if policy.get("forbids_ref_content") is not True:
        return Check("preview_live", "Mission 1 1024 runtime policy", "FAIL", "policy must forbid REF content")

    return Check(
        "preview_live",
        "Mission 1 1024 runtime policy",
        "PASS",
        f"policy={policy.get('id')} viewport=1024x768 target_fps={policy.get('target_fps')}",
    )


def check_raw_resolution_receipts() -> list[Check]:
    base13 = ARTIFACT_ROOT / "raw_resolution_targets_20260613"
    base14 = ARTIFACT_ROOT / "raw_resolution_targets_20260614"
    base14_alias = ARTIFACT_ROOT / "raw_resolution_targets_20260614_alias_v4"
    checks: list[Check] = []

    fast_pi_path = base14_alias / "pi5_2k_fast_alias_120f" / "raw_resolution_targets_pi5_120f.json"
    mask4_pi_path = base14_alias / "pi5_2k_l2hh_alias_120f" / "raw_resolution_targets_pi5_120f.json"
    fast_visual_path = base13 / "visual_fast_2k_28f" / "raw_resolution_targets_visual_dashboard.json"
    fast_quality_path = base13 / "quality_2k_runtime_fast_l2drop_100f" / "raw_resolution_targets_quality.json"
    visual2k_path = base14 / "visual_2k_l2hh_28f_explicit" / "raw_resolution_targets_visual_dashboard.json"
    visual2k_edge_path = (
        ARTIFACT_ROOT
        / "raw_resolution_targets_20260614_analysis"
        / "visual_2k_l2hh_edgeinset16_28f"
        / "raw_resolution_targets_visual_dashboard.json"
    )
    visual4k_path = base14 / "visual_4k_28f" / "raw_resolution_targets_visual_dashboard.json"
    quality2k_l2hh_path = (
        ARTIFACT_ROOT
        / "raw_resolution_targets_20260614_analysis"
        / "quality_2k_l2hh_100f"
        / "raw_resolution_targets_quality.json"
    )
    quality100_path = base13 / "quality_2k4k_100f" / "raw_resolution_targets_quality.json"
    quality_path = base13 / "quality_2k4k8k_3f" / "raw_resolution_targets_quality.json"
    bench8k_path = base13 / "smoke_2k4k8k_3f" / "raw_resolution_targets_bench.json"
    raw_probe4k_path = (
        ARTIFACT_ROOT
        / "raw_resolution_targets_20260614_analysis"
        / "visual_4k_28f_current"
        / "raw_domain_lower_right_probe.json"
    )

    fast_pi, err = read_json_receipt(fast_pi_path)
    if err:
        checks.append(Check("raw_targets", "2K fast Pi timing receipt", "FAIL", err))
    else:
        target = "2k_raw_0p5x_fast"
        timing = target_timing(fast_pi or {}, target)
        fps = float(timing.get("fps_median", 0.0))
        ms = float(timing.get("median_ms", 999.0))
        p95 = float(timing.get("p95_ms", 999.0))
        mode = (fast_pi or {}).get("decode_mode") or {}
        ok = (
            fps >= 24.0
            and ms < 41.7
            and p95 < 41.7
            and bool(mode.get("halfres_stream"))
            and pi_child_policy_ok(fast_pi or {}, target)
            and pi_receipt_metadata_ok(fast_pi or {}, target, "named target: drop L2 highpass")
        )
        checks.append(Check(
            "raw_targets",
            "2K fast Pi timing receipt",
            "PASS" if ok else "FAIL",
            f"fps_median={fps:.2f} median_ms={ms:.1f} p95_ms={p95:.1f} "
            f"{pi_policy_detail(fast_pi or {}, target)} commit={(fast_pi or {}).get('git_commit', '')[:8]} "
            f"receipt={fast_pi_path}",
        ))

    fast_visual, err = read_json_receipt(fast_visual_path)
    if err:
        checks.append(Check("raw_targets", "2K fast visual proxy receipt", "FAIL", err))
    else:
        summary = (fast_visual or {}).get("summary") or {}
        pass_count = int(summary.get("pass_count", -1))
        count = int(summary.get("count", 0))
        worst_lpips = float(summary.get("worst_lpips", 999.0))
        worst_ms = float(summary.get("worst_ms_ssim", 0.0))
        worst_y = float(summary.get("worst_y_psnr", 0.0))
        worst_de = float(summary.get("worst_dE2000_mean", 999.0))
        ok = (
            (fast_visual or {}).get("target") == "2k_raw_0p5x"
            and count == 84
            and pass_count == 56
            and 0.15 < worst_lpips < 0.17
            and worst_ms >= 0.95
            and worst_y >= 28.0
            and worst_de <= 3.0
        )
        checks.append(Check(
            "raw_targets",
            "2K fast visual proxy receipt",
            "PASS" if ok else "FAIL",
            f"{pass_count}/{count} worst_lpips={worst_lpips:.4f} worst_ms={worst_ms:.4f} "
            f"worst_y={worst_y:.2f} worst_dE={worst_de:.2f} receipt={fast_visual_path}",
        ))

    fast_quality, err = read_json_receipt(fast_quality_path)
    if err:
        checks.append(Check("raw_targets", "2K fast raw quality receipt", "FAIL", err))
    else:
        summary = ((fast_quality or {}).get("summary") or {}).get("2k_raw_0p5x") or {}
        psnr = summary.get("psnr_db") or {}
        mae = summary.get("mae_lsb") or {}
        p99 = summary.get("p99_abs_lsb") or {}
        ok = (
            int(summary.get("count", 0)) == 100
            and float(psnr.get("mean", 0.0)) >= 55.0
            and float(psnr.get("median", 0.0)) >= 54.0
            and float(mae.get("mean", 999.0)) <= 7.0
            and float(p99.get("median", 999.0)) <= 45.0
        )
        checks.append(Check(
            "raw_targets",
            "2K fast raw quality receipt",
            "PASS" if ok else "FAIL",
            f"n={int(summary.get('count', 0))} psnr_mean={float(psnr.get('mean', 0.0)):.2f} "
            f"psnr_median={float(psnr.get('median', 0.0)):.2f} mae_mean={float(mae.get('mean', 0.0)):.2f} "
            f"p99_median={float(p99.get('median', 0.0)):.1f} receipt={fast_quality_path}",
        ))

    mask4_pi, err = read_json_receipt(mask4_pi_path)
    if err:
        checks.append(Check("raw_targets", "2K L2 HH Pi p95-live timing receipt", "FAIL", err))
    else:
        target = "2k_raw_0p5x_l2hh"
        timing = target_timing(mask4_pi or {}, target)
        fps = float(timing.get("fps_median", 0.0))
        ms = float(timing.get("median_ms", 999.0))
        p95 = float(timing.get("p95_ms", 999.0))
        mode = (mask4_pi or {}).get("decode_mode") or {}
        ok = (
            fps >= 24.0
            and ms < 41.7
            and p95 < 41.7
            and bool(mode.get("halfres_stream"))
            and pi_child_policy_ok(mask4_pi or {}, target)
            and pi_receipt_metadata_ok(mask4_pi or {}, target, "named target: restore selective L2 HH")
        )
        checks.append(Check(
            "raw_targets",
            "2K L2 HH Pi p95-live timing receipt",
            "PASS" if ok else "FAIL",
            f"fps_median={fps:.2f} median_ms={ms:.1f} p95_ms={p95:.1f} "
            f"p95_live={'yes' if p95 < 41.7 else 'no'} {pi_policy_detail(mask4_pi or {}, target)} "
            f"commit={(mask4_pi or {}).get('git_commit', '')[:8]} receipt={mask4_pi_path}",
        ))

    visual2k, err = read_json_receipt(visual2k_path)
    if err:
        checks.append(Check("raw_targets", "2K L2 HH visual proxy receipt", "FAIL", err))
    else:
        summary = (visual2k or {}).get("summary") or {}
        pass_count = int(summary.get("pass_count", -1))
        count = int(summary.get("count", 0))
        worst_lpips = float(summary.get("worst_lpips", 999.0))
        ok = (
            (visual2k or {}).get("target") == "2k_raw_0p5x_l2hh"
            and count == 84
            and pass_count == 80
            and worst_lpips < 0.16
        )
        checks.append(Check(
            "raw_targets",
            "2K L2 HH visual proxy receipt",
            "PASS" if ok else "FAIL",
            f"{pass_count}/{count} worst_lpips={worst_lpips:.4f} receipt={visual2k_path}",
        ))

    visual2k_edge, err = read_json_receipt(visual2k_edge_path)
    if err:
        checks.append(Check("raw_targets", "2K L2 HH edge-safe visual proxy receipt", "FAIL", err))
    else:
        summary = (visual2k_edge or {}).get("summary") or {}
        pass_count = int(summary.get("pass_count", -1))
        count = int(summary.get("count", 0))
        worst_lpips = float(summary.get("worst_lpips", 999.0))
        worst_ms = float(summary.get("worst_ms_ssim", 0.0))
        worst_y = float(summary.get("worst_y_psnr", 0.0))
        worst_de = float(summary.get("worst_dE2000_mean", 999.0))
        edge_inset = int((visual2k_edge or {}).get("edge_inset_px", -1))
        ok = (
            (visual2k_edge or {}).get("target") == "2k_raw_0p5x_l2hh"
            and edge_inset == 16
            and count == 84
            and pass_count == 84
            and worst_lpips <= 0.15
            and worst_ms >= 0.95
            and worst_y >= 28.0
            and worst_de <= 3.0
        )
        checks.append(Check(
            "raw_targets",
            "2K L2 HH edge-safe visual proxy receipt",
            "PASS" if ok else "FAIL",
            f"{pass_count}/{count} edge_inset={edge_inset}px worst_lpips={worst_lpips:.4f} "
            f"worst_ms={worst_ms:.4f} worst_y={worst_y:.2f} worst_dE={worst_de:.2f} "
            f"receipt={visual2k_edge_path}",
        ))

    quality2k_l2hh, err = read_json_receipt(quality2k_l2hh_path)
    if err:
        checks.append(Check("raw_targets", "2K L2 HH main-corpus raw quality receipt", "FAIL", err))
    else:
        rows = [
            row
            for row in (quality2k_l2hh or {}).get("rows", [])
            if "/barnsky_full_dngs/" in str(row.get("source_dng", ""))
            and "2k_raw_0p5x_l2hh" in (row.get("targets") or {})
        ]
        psnr = stats([float(row["targets"]["2k_raw_0p5x_l2hh"].get("psnr_db", 0.0)) for row in rows])
        mae = stats([float(row["targets"]["2k_raw_0p5x_l2hh"].get("mae_lsb", 999.0)) for row in rows])
        p99 = stats([float(row["targets"]["2k_raw_0p5x_l2hh"].get("p99_abs_lsb", 999.0)) for row in rows])
        ok = (
            psnr["n"] >= 99
            and psnr["min"] >= 53.0
            and psnr["mean"] >= 55.0
            and mae["max"] <= 7.0
            and p99["max"] <= 45.0
        )
        checks.append(Check(
            "raw_targets",
            "2K L2 HH main-corpus raw quality receipt",
            "PASS" if ok else "FAIL",
            f"n={psnr['n']} psnr_min={psnr['min']:.2f} psnr_mean={psnr['mean']:.2f} "
            f"mae_max={mae['max']:.2f} p99_max={p99['max']:.1f} receipt={quality2k_l2hh_path}",
        ))

    visual4k, err = read_json_receipt(visual4k_path)
    if err:
        checks.append(Check("raw_targets", "4K rendered proxy diagnostic receipt", "FAIL", err))
    else:
        summary = (visual4k or {}).get("summary") or {}
        pass_count = int(summary.get("pass_count", -1))
        count = int(summary.get("count", 0))
        worst_lpips = float(summary.get("worst_lpips", 0.0))
        worst_y = float(summary.get("worst_y_psnr", 0.0))
        worst_de = float(summary.get("worst_dE2000_mean", 999.0))
        ok = (
            (visual4k or {}).get("target") == "4k_raw_1x"
            and count == 84
            and pass_count == 55
            and worst_lpips > 0.30
            and worst_y >= 28.0
            and worst_de <= 3.0
        )
        checks.append(Check(
            "raw_targets",
            "4K rendered proxy diagnostic receipt",
            "PASS" if ok else "FAIL",
            f"{pass_count}/{count} worst_lpips={worst_lpips:.4f} worst_y={worst_y:.2f} "
            f"worst_dE={worst_de:.2f} receipt={visual4k_path}",
        ))

    quality100, err = read_json_receipt(quality100_path)
    if err:
        checks.append(Check("raw_targets", "4K main-corpus raw quality receipt", "FAIL", err))
    else:
        rows = [
            row
            for row in (quality100 or {}).get("rows", [])
            if "/barnsky_full_dngs/" in str(row.get("source_dng", ""))
            and "4k_raw_1x" in (row.get("targets") or {})
        ]
        psnr = stats([float(row["targets"]["4k_raw_1x"].get("psnr_db", 0.0)) for row in rows])
        mae = stats([float(row["targets"]["4k_raw_1x"].get("mae_lsb", 999.0)) for row in rows])
        p99 = stats([float(row["targets"]["4k_raw_1x"].get("p99_abs_lsb", 999.0)) for row in rows])
        ok = (
            psnr["n"] >= 99
            and psnr["min"] >= 48.0
            and psnr["mean"] >= 50.0
            and mae["max"] <= 11.0
            and p99["max"] <= 80.0
        )
        checks.append(Check(
            "raw_targets",
            "4K main-corpus raw quality receipt",
            "PASS" if ok else "FAIL",
            f"n={psnr['n']} psnr_min={psnr['min']:.2f} psnr_mean={psnr['mean']:.2f} "
            f"mae_max={mae['max']:.2f} p99_max={p99['max']:.1f} receipt={quality100_path}",
        ))

    raw_probe4k, err = read_json_receipt(raw_probe4k_path)
    if err:
        checks.append(Check("raw_targets", "4K raw/proxy calibration receipt", "FAIL", err))
    else:
        margin0 = []
        for row in (raw_probe4k or {}).get("rows", []):
            for margin in row.get("margins", []):
                if int(margin.get("margin_px", -1)) == 0:
                    margin0.append(margin.get("raw_metrics") or {})
        psnr = stats([float(row.get("psnr_db", 0.0)) for row in margin0])
        mae = stats([float(row.get("mae_lsb", 999.0)) for row in margin0])
        ok = (
            (raw_probe4k or {}).get("schema") == "raw_resolution_raw_domain_failure_probe.v1"
            and (raw_probe4k or {}).get("target") == "4k_raw_1x"
            and psnr["n"] >= 20
            and psnr["mean"] >= 65.0
            and mae["mean"] <= 4.0
        )
        checks.append(Check(
            "raw_targets",
            "4K raw/proxy calibration receipt",
            "PASS" if ok else "FAIL",
            f"lower_right_fail_rows={psnr['n']} raw_psnr_mean={psnr['mean']:.2f} "
            f"raw_mae_mean={mae['mean']:.2f} receipt={raw_probe4k_path}",
        ))

    quality, err = read_json_receipt(quality_path)
    if err:
        checks.append(Check("raw_targets", "8K raw quality smoke receipt", "FAIL", err))
    else:
        psnr = target_metric_summary(quality or {}, "8k_raw_2x", "psnr_db")
        mean_psnr = float(psnr.get("mean", 0.0))
        count = int(summary_target(quality or {}, "8k_raw_2x").get("count", 0))
        ok = count >= 3 and mean_psnr >= 45.0
        checks.append(Check(
            "raw_targets",
            "8K raw quality smoke receipt",
            "PASS" if ok else "FAIL",
            f"count={count} mean_psnr={mean_psnr:.2f} receipt={quality_path}",
        ))

    bench8k, err = read_json_receipt(bench8k_path)
    if err:
        checks.append(Check("raw_targets", "8K offline timing smoke receipt", "FAIL", err))
    else:
        timing = target_timing(bench8k or {}, "8k_raw_2x")
        fps = float(timing.get("fps_median", 0.0))
        ms = float(timing.get("median_ms", 0.0))
        ok = 0.0 < fps < 24.0 and ms > 40.0
        checks.append(Check(
            "raw_targets",
            "8K offline timing smoke receipt",
            "PASS" if ok else "FAIL",
            f"fps_median={fps:.2f} median_ms={ms:.1f} classification=offline-only receipt={bench8k_path}",
        ))

    return checks


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
        target = f" target>={min_fps:.2f}" if min_fps > 0 else " measured-stage"
        checks.append(Check("platform_perf", name, status, f"fps={fps:.2f}{target}"))
    return checks


def check_x2d_noise_receipts() -> list[Check]:
    base = Path("/Volumes/OWC_8TB/gpr_work/artifacts/x2d_focus_20260605")
    selection = base / "x2d_iso_stratified_21_fff_selection.json"
    manifest = base / "x2d_iso_stratified_21_test_set.json"
    targets = base / "raw_clean_targets_iso_stratified_21_min800/raw_clean_ref_targets.json"
    audit = base / "raw_noise_signal_audit_iso_stratified_21_min800/raw_noise_signal_audit.json"
    missing = [p for p in (selection, manifest, targets, audit) if not p.exists()]
    if missing:
        return [Check("noise_signal", "X2D ISO-stratified receipts", "FAIL", "missing " + ", ".join(str(p) for p in missing))]

    try:
        manifest_data = json.loads(manifest.read_text())
        target_data = json.loads(targets.read_text())
        audit_data = json.loads(audit.read_text())
    except Exception as exc:
        return [Check("noise_signal", "X2D ISO-stratified receipts", "FAIL", f"bad JSON: {exc}")]

    images = manifest_data.get("images") or []
    target_rows = target_data.get("rows") or []
    audit_rows = audit_data.get("rows") or []
    checks = [
        Check(
            "noise_signal",
            "X2D ISO-stratified corpus",
            "PASS" if len(images) >= 21 and len(target_rows) >= 63 else "FAIL",
            f"images={len(images)} target_crops={len(target_rows)} manifest={manifest}",
        )
    ]

    low_iso = [r for r in target_rows if int(r.get("iso", 0)) < 800]
    low_nonzero = [
        r for r in low_iso
        if not r.get("force_noop") or float(r.get("exact_residual_rms_counts", 0.0)) > 1e-6
    ]
    checks.append(Check(
        "noise_signal",
        "low-ISO no-op controls",
        "PASS" if low_iso and not low_nonzero else "FAIL",
        f"low_iso_crops={len(low_iso)} nonzero_or_unforced={len(low_nonzero)}",
    ))

    fail_count = int(audit_data.get("fail_count", -1))
    pass_count = int(audit_data.get("pass_count", 0))
    no_op_count = int(audit_data.get("no_op_count", 0))
    checks.append(Check(
        "noise_signal",
        "strict noise/signal audit",
        "PASS" if fail_count == 0 and pass_count == len(audit_rows) else "FAIL",
        f"pass={pass_count} fail={fail_count} no_op={no_op_count} audit={audit}",
    ))
    return checks


def check_upresable_media_receipts() -> list[Check]:
    base = ARTIFACT_ROOT / "upresable_missing_hard_20260606"
    summary = base / "summary.json"
    checks = [
        check_external_file("media_receipts", "hard-tail UPRESABLE summary", summary, min_bytes=128),
        check_gvid_receipt("media_receipts", "hard-tail .gvid deliverable", base / "upresable_timelapse.gvid", min_frames=6),
        check_external_file("media_receipts", "GPR1 MOV compatibility wrapper", base / "upresable_timelapse.gpr1.mov", min_bytes=1_000_000),
        check_prores_receipt("media_receipts", "hard-tail ProRes review MOV", base / "upresable_timelapse.mov", min_frames=6),
    ]
    dngs = sorted((base / "editable_dng").glob("*.dng"))
    gprs = sorted((base / "editable_gpr").glob("*.gpr"))
    checks.append(Check(
        "media_receipts",
        "editable DNG exports",
        "PASS" if len(dngs) >= 6 and all(p.stat().st_size > 10_000_000 for p in dngs) else "FAIL",
        f"count={len(dngs)} dir={base / 'editable_dng'}",
    ))
    checks.append(Check(
        "media_receipts",
        "editable GPR exports",
        "PASS" if len(gprs) >= 6 and all(p.stat().st_size > 1_000_000 for p in gprs) else "FAIL",
        f"count={len(gprs)} dir={base / 'editable_gpr'}",
    ))
    if summary.exists():
        try:
            data = json.loads(summary.read_text())
            stats = data.get("timelapse_stats") or {}
            ok = (
                stats.get("deliverable") == "gvid+prores"
                and bool(stats.get("mov_compatibility"))
                and bool(stats.get("dng_exported"))
                and int(stats.get("n_frames", 0)) >= 6
            )
            checks.append(Check(
                "media_receipts",
                "hard-tail media summary contract",
                "PASS" if ok else "FAIL",
                f"deliverable={stats.get('deliverable')} mov={stats.get('mov_compatibility')} "
                f"dng={stats.get('dng_exported')} frames={stats.get('n_frames')}",
            ))
        except Exception as exc:
            checks.append(Check("media_receipts", "hard-tail media summary contract", "FAIL", f"bad JSON: {exc}"))
    return checks


def check_preview_review_media_receipts() -> list[Check]:
    base = ARTIFACT_ROOT / "preview_review_20260604"
    expected = [
        ("codec-only ProRes review", "barnsky_codec_only_120f_4k_prores_hq.mov", 120),
        ("SOTA-v2 ProRes review", "barnsky_sota_v2_120f_4k_prores_hq.mov", 120),
        ("codec-vs-SOTA ProRes review", "barnsky_codec_vs_sota_v2_120f_3840x1080_prores_hq.mov", 120),
        ("UPRESABLE ProRes review", "upresable_720f_4k_prores_hq.mov", 720),
    ]
    checks = [
        check_external_file("media_receipts", "preview review dashboard", base / "preview_review_dashboard.html", min_bytes=1_000),
    ]
    for name, filename, frames in expected:
        checks.append(check_prores_receipt("media_receipts", name, base / filename, min_frames=frames))
    return checks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="exit non-zero when any check fails")
    ap.add_argument(
        "--require-mission1-strict24",
        action="store_true",
        help="fail unless Mission 1 native 12MP has quality-preserving strict-24 fps evidence",
    )
    args = ap.parse_args()

    checks: list[Check] = []
    checks.extend(check_ship_group("stills", "ship-still"))
    checks.extend(check_ship_group("video_quality", "ship-video-freeze"))
    checks.extend(check_nonref_preview_candidate())
    lab_sips_pipeline = "codec=ml2_q3_dec2+cnn=lab_chroma_corrector_w12_sips_residual_ab8_sub10+demosaic=sips_via_gpr_tools"
    checks.append(check_preview_detail(
        "preview_detail",
        "Lab Chroma SIPS full PREVIEW gate",
        lab_sips_pipeline,
    ))
    checks.append(check_preview_variant_oracle_evidence())
    checks.append(check_preview_exact_teacher_oracle_evidence())
    checks.append(check_preview_post_refiner_negative_evidence())
    checks.append(check_preview_coord_field_negative_evidence())
    checks.append(check_preview_fullimage_lf_negative_evidence())
    checks.append(check_preview_frequency_oracle_evidence())
    checks.append(check_preview_context_generator_negative_evidence())
    checks.append(check_preview_multi_origin_tile_negative_evidence())
    checks.append(check_preview_source_frequency_negative_evidence())
    checks.append(check_preview_fullimage_band_negative_evidence())
    checks.append(check_preview_highres_fullimage_band_negative_evidence())
    checks.append(check_preview_residual_fullimage_band_negative_evidence())
    checks.append(check_preview_fullimage_affine_oracle_negative_evidence())
    checks.append(check_preview_residual_feature_negative_evidence())
    checks.append(check_preview_dense_warp_negative_evidence())
    checks.append(check_preview_source_representation_negative_evidence())
    checks.append(check_preview_alignment_oracle_negative_evidence())
    checks.append(check_preview_fullframe_failure_mode_audit())
    checks.append(check_preview_candidate_evidence_rank())
    checks.append(check_preview_source_ref_policy_audit())
    checks.append(check_preview_source_policy_generalization_negative_evidence())
    checks.append(check_preview_q8_lowfield_negative_evidence())
    checks.append(check_preview_q8_multiband_negative_evidence())
    checks.append(check_preview_q8_crop_specialist_evidence())
    checks.append(check_preview_q8_hard_router_union_evidence())
    checks.append(check_preview_q8_threeway_router_union_evidence())
    checks.append(check_preview_q8_threeway_runtime_fullframe_evidence())
    checks.append(check_preview_rolemap_post_distill_negative_evidence())
    checks.append(check_preview_route_smoothing_negative_evidence())
    checks.append(check_preview_stitched_context_unet_negative_evidence())
    checks.append(check_preview_exact_teacher_distill_negative_evidence())
    checks.extend([
        check_file("preview_holdout", "28-image holdout manifest", "tests/quality_gates/preview_holdout_set.json"),
        check_file("preview_holdout", "holdout summary dashboard tool", "tests/quality_gates/summarize_preview_holdout.py"),
    ])
    checks.extend(check_x2d_noise_receipts())
    checks.append(check_pipeline(
        "upresable",
        "production UPRESABLE",
        "codec=ml2_q3_dec2+cnn=bibo2x_ane_ml2_q3_dec2_diverse+demosaic=sips_via_gpr_tools",
    ))
    checks.extend(check_native12_8k_sr_candidate())
    checks.extend(check_native12_sr_registry_boundaries())
    checks.extend(check_native12_sr_frontier_summary())
    checks.extend(check_native12_bayer_resample_contract())
    checks.extend(check_native12_frontier_summary())
    checks.extend(check_native12_tokenizer_microbench_summary())
    checks.extend(check_native12_unpack_frontier_summary())
    checks.extend(check_native12_current_repo_source_target_receipt())
    checks.extend(check_native12_current_frequency_saturation_retest())
    checks.extend(check_native12_post_saturation_stripe_sweep())
    checks.extend(check_native12_ll_bitwriter32_probe())
    checks.extend(check_native12_inline_tail_flush_fix())
    checks.extend(check_native12_pgo_ofast_probe())
    checks.extend(check_native12_write_contention_summary())
    checks.extend(check_native12_strict24_gap_report())
    checks.extend(check_native12_detail_residual_sidecar_boundary())
    checks.extend(check_upresable_media_receipts())
    checks.extend(check_preview_review_media_receipts())

    checks.extend([
        check_file("container_gvid", "wire format header", "source/lib/vc5_encoder/gpr_video_format.h"),
        check_file("container_gvid", "wire format implementation", "source/lib/vc5_encoder/gpr_video_format.c"),
        check_file("container_gvid", "CI format smoke", "source/app/test_video_format.c"),
        check_file("container_gvid", "GVID pack tool", "tools/gvid_pack.py"),
        check_file("container_gvid", "GVID pack smoke", "tools/test/test_gvid_pack.sh"),
        check_file("container_mov", "MOV compatibility pack tool source", "tools/gpr2prores/gpr_mov_tool.m"),
        check_script_contains(
            "container_mov",
            "MOV compatibility build recipe",
            "tools/gpr2prores/Makefile",
            ["gpr_mov_tool:", "install -m 0755 gpr_mov_tool"],
        ),
        check_file("container_mov", "MOV compatibility fixture recipe", "tools/test/make_gpraw_fixture.sh"),
        check_file("pi5_mission1", "Pi encoder benchmark", "tools/test/test_pi_encoder.sh"),
        check_file("pi5_mission1", "Pi-to-Mac UPRESABLE bench", "tools/test/bench_pi_to_mac_upresable.sh"),
        check_file("pi5_mission1", "Pi SD first-boot config", "tools/test/configure_pi_sd.sh"),
    ])

    checks.extend([
        check_capabilities_doc(),
        check_capability_memory_receipt(),
        check_pi5_capture_receipt(require_strict24=args.require_mission1_strict24),
        check_video_status_doc(),
        check_live_preview_fast_path(),
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
    if args.require_mission1_strict24:
        checks.append(check_mission1_strict24_production_candidate())
    checks.append(check_live_preview_edge_safe_policy())
    checks.extend(check_raw_resolution_receipts())
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
