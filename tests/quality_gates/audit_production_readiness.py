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
import hashlib
import json
import os
import re
import struct
import subprocess
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
        "codec-only PREVIEW route is the fast live/camera-back",
        "Live/camera-back quality beyond codec-only remains a separate future",
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


def check_raw_resolution_receipts() -> list[Check]:
    base13 = ARTIFACT_ROOT / "raw_resolution_targets_20260613"
    base14 = ARTIFACT_ROOT / "raw_resolution_targets_20260614"
    checks: list[Check] = []

    fast_pi_path = base14 / "pi5_l2drop_stream_v2_120f" / "raw_resolution_targets_pi5_120f.json"
    mask4_pi_path = base14 / "pi5_l2mask4_stream_v3_120f" / "raw_resolution_targets_pi5_120f.json"
    visual2k_path = base14 / "visual_2k_l2mask4_28f" / "raw_resolution_targets_visual_dashboard.json"
    visual4k_path = base14 / "visual_4k_28f" / "raw_resolution_targets_visual_dashboard.json"
    quality_path = base13 / "quality_2k4k8k_3f" / "raw_resolution_targets_quality.json"
    bench8k_path = base13 / "smoke_2k4k8k_3f" / "raw_resolution_targets_bench.json"

    fast_pi, err = read_json_receipt(fast_pi_path)
    if err:
        checks.append(Check("raw_targets", "2K fast Pi timing receipt", "FAIL", err))
    else:
        timing = target_timing(fast_pi or {}, "2k_raw_0p5x")
        fps = float(timing.get("fps_median", 0.0))
        ms = float(timing.get("median_ms", 999.0))
        mode = (fast_pi or {}).get("decode_mode") or {}
        ok = (
            fps >= 24.0
            and ms < 41.7
            and bool(mode.get("halfres_drop_l2_hp"))
            and bool(mode.get("halfres_stream"))
        )
        checks.append(Check(
            "raw_targets",
            "2K fast Pi timing receipt",
            "PASS" if ok else "FAIL",
            f"fps_median={fps:.2f} median_ms={ms:.1f} mode={mode} receipt={fast_pi_path}",
        ))

    mask4_pi, err = read_json_receipt(mask4_pi_path)
    if err:
        checks.append(Check("raw_targets", "2K L2 HH Pi timing receipt", "FAIL", err))
    else:
        timing = target_timing(mask4_pi or {}, "2k_raw_0p5x")
        fps = float(timing.get("fps_median", 0.0))
        ms = float(timing.get("median_ms", 999.0))
        mode = (mask4_pi or {}).get("decode_mode") or {}
        ok = (
            fps >= 24.0
            and ms < 41.7
            and mode.get("halfres_l2_mask") == "4"
            and bool(mode.get("halfres_stream"))
        )
        checks.append(Check(
            "raw_targets",
            "2K L2 HH Pi timing receipt",
            "PASS" if ok else "FAIL",
            f"fps_median={fps:.2f} median_ms={ms:.1f} mode={mode} receipt={mask4_pi_path}",
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
            (visual2k or {}).get("target") == "2k_raw_0p5x"
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

    visual4k, err = read_json_receipt(visual4k_path)
    if err:
        checks.append(Check("raw_targets", "4K rendered proxy blocker receipt", "FAIL", err))
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
            "4K rendered proxy blocker receipt",
            "PASS" if ok else "FAIL",
            f"{pass_count}/{count} worst_lpips={worst_lpips:.4f} worst_y={worst_y:.2f} "
            f"worst_dE={worst_de:.2f} receipt={visual4k_path}",
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
        target = f" target>={min_fps:.2f}" if min_fps > 0 else " receipt-only"
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
        check_pi5_capture_receipt(),
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
