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
        / "fullframe_failure_mode_audit_v2"
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
        ok = (
            payload.get("schema") == "preview_fullframe_failure_mode_audit.v1"
            and int(summary.get("normalized_row_count", 0)) >= 1371
            and int(summary.get("variant_count", 0)) >= 50
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
                f"context_unet={int(context_unet.get('pass_count', -1))}/24 "
                f"receipt={receipt}"
            ),
        )
    except Exception as exc:
        return Check("preview_detail", "full-frame failure-mode audit", "FAIL", f"bad JSON: {exc}")


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
    checks.append(check_preview_alignment_oracle_negative_evidence())
    checks.append(check_preview_fullframe_failure_mode_audit())
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
