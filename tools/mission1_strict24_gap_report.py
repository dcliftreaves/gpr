#!/usr/bin/env python3
"""Create a compact Mission 1 native12 strict-24 gap report."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "mission1_strict24_gap_report.v1"
TARGET_FPS = 24.0
TARGET_FRAME_MS = 1000.0 / TARGET_FPS
ROOT = Path(__file__).resolve().parents[1]
WRITE_SUMMARY_TOOL = ROOT / "tools" / "mission1_write_contention_summary.py"


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_write_summary(external_root: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("mission1_write_contention_summary", WRITE_SUMMARY_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {WRITE_SUMMARY_TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module.build_summary(external_root)  # type: ignore[attr-defined]
    if not isinstance(payload, dict):
        raise TypeError("write-contention summary must be a JSON object")
    return payload


def gap_ms(total_ms: float | None) -> float | None:
    return total_ms - TARGET_FRAME_MS if total_ms is not None else None


def wall_ms_from_fps(wall_fps: float | None) -> float | None:
    if wall_fps is None or wall_fps <= 0.0:
        return None
    return 1000.0 / wall_fps


def candidate(
    name: str,
    source: dict[str, Any],
    *,
    metrics: dict[str, Any] | None = None,
    source_receipt: str | None = None,
    classification: str | None = None,
    quality_impact: str | None = None,
) -> dict[str, Any]:
    m = metrics if metrics is not None else source
    total = safe_float(m.get("total_median_ms"))
    encode = safe_float(m.get("encode_median_ms"))
    write = safe_float(m.get("write_median_ms"))
    fps = safe_float(m.get("fps_median"))
    wall_fps = safe_float(source.get("actual_wall_fps") or m.get("wall_fps"))
    wall_ms = wall_ms_from_fps(wall_fps)
    loop_gap = gap_ms(total)
    wall_gap = gap_ms(wall_ms)
    payload = safe_float(m.get("payload_kib_median"))
    return {
        "name": name,
        "classification": classification or source.get("classification"),
        "quality_impact": quality_impact or source.get("quality_impact"),
        "source_receipt": source_receipt or source.get("source_receipt"),
        "total_median_ms": total,
        "loop_gap_ms": loop_gap,
        "fps_median": fps,
        "actual_wall_fps": wall_fps,
        "wall_ms_per_frame": wall_ms,
        "wall_gap_ms": wall_gap,
        "encode_median_ms": encode,
        "write_median_ms": write,
        "payload_kib_median": payload,
        "storage_target_met": m.get("storage_target_met") if "storage_target_met" in m else source.get("storage_fits_target"),
        "gvid_valid": m.get("gvid_valid"),
        "strict_24_pass": bool(total is not None and total <= TARGET_FRAME_MS and (wall_ms is None or wall_ms <= TARGET_FRAME_MS)),
        "has_wall_evidence": wall_ms is not None,
    }


def collect_candidates(summary: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    boundary = summary.get("latest_t236_boundary")
    if isinstance(boundary, dict):
        real = boundary.get("real_write_best_case")
        if isinstance(real, dict):
            out.append(candidate(
                "t236_quality_storage_boundary_real_write",
                boundary,
                metrics=real,
                classification=boundary.get("blocker_class"),
                quality_impact=boundary.get("visual_quality_impact"),
                source_receipt=(boundary.get("source_receipts") or {}).get("real_write"),
            ))

    clean = summary.get("fresh_t236_clean_pi_probe")
    if isinstance(clean, dict) and isinstance(clean.get("ofast_real_write"), dict):
        out.append(candidate("t236_clean_real_write", clean, metrics=clean["ofast_real_write"]))

    recent = summary.get("recent_t236_followup_probes")
    if not isinstance(recent, dict):
        return out

    for key in ("current_source_t236_sustained_240f", "writer_handoff_t236", "explicit_gap_t236_240f"):
        row = recent.get(key)
        if isinstance(row, dict):
            out.append(candidate(key, row, metrics=row.get("metrics") if isinstance(row.get("metrics"), dict) else None))

    for key in ("writev_index", "coalesce_index"):
        row = recent.get(key)
        if isinstance(row, dict) and isinstance(row.get("candidate"), dict):
            out.append(candidate(f"{key}_candidate", row, metrics=row["candidate"]))

    writer_core = recent.get("writer_core_pinning")
    if isinstance(writer_core, dict) and isinstance(writer_core.get("best"), dict):
        out.append(candidate("writer_core_best", writer_core, metrics=writer_core["best"]))

    return out


def best_by(candidates: list[dict[str, Any]], key: str, *, require_wall: bool = False) -> dict[str, Any] | None:
    filtered = [
        row for row in candidates
        if safe_float(row.get(key)) is not None and (not require_wall or row.get("has_wall_evidence") is True)
    ]
    if not filtered:
        return None
    return min(filtered, key=lambda row: float(row[key]))


def collect_rejected_paths(summary: dict[str, Any]) -> list[dict[str, Any]]:
    recent = summary.get("recent_t236_followup_probes")
    if not isinstance(recent, dict):
        return []
    rejected: list[dict[str, Any]] = []
    for name, row in recent.items():
        if not isinstance(name, str) or not isinstance(row, dict):
            continue
        classification = str(row.get("classification") or "")
        if row.get("rejected") is not True and not classification.startswith("rejected_"):
            continue
        rejected.append({
            "name": name,
            "classification": classification or None,
            "quality_impact": row.get("quality_impact"),
            "reason": row.get("decision") or row.get("reason") or row.get("sustained_decision"),
            "total_delta_ms": safe_float(row.get("total_delta_ms") or row.get("real_write_total_delta_ms")),
            "write_delta_ms": safe_float(row.get("write_delta_ms")),
            "source_receipt": row.get("source_receipt") or row.get("source_receipts"),
        })
    return sorted(rejected, key=lambda row: str(row.get("name")))


def collect_near_misses(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    near: list[dict[str, Any]] = []
    for row in candidates:
        loop_gap = safe_float(row.get("loop_gap_ms"))
        wall_gap = safe_float(row.get("wall_gap_ms"))
        if loop_gap is None:
            continue
        if loop_gap <= 2.5 or (wall_gap is not None and wall_gap <= 3.0):
            near.append({
                "name": row.get("name"),
                "classification": row.get("classification"),
                "loop_gap_ms": loop_gap,
                "wall_gap_ms": wall_gap,
                "encode_median_ms": row.get("encode_median_ms"),
                "write_median_ms": row.get("write_median_ms"),
                "source_receipt": row.get("source_receipt"),
            })
    return sorted(near, key=lambda row: (
        float(row["wall_gap_ms"]) if row.get("wall_gap_ms") is not None else 1e9,
        float(row["loop_gap_ms"]),
        str(row.get("name")),
    ))


def build_next_probe_matrix(
    required_loop_reduction: float,
    required_wall_reduction: float,
    quality_storage_boundary_ok: bool,
) -> list[dict[str, Any]]:
    base_env = {
        "GPR_INCLUDE_LL": "1",
        "FUSED_MULTI_LEVEL": "0",
        "FUSED_WAVELET_LEVELS": "1",
        "FUSED_QUALITY": "8",
        "FUSED_RAW_LL": "1",
        "FUSED_LL_PREDICT": "1",
        "FUSED_LL_PREDICTOR": "avg",
        "FUSED_LL_RICE_FAST": "1",
        "FUSED_LL_RICE_KS": "6,6,5,6",
        "FUSED_REFERENCE_HORIZONTAL": "1",
        "FUSED_INLINE_TOKENIZE": "1",
        "FUSED_DEFER_RANS": "1",
        "FUSED_STRIPE_ROWS": "384",
        "GPR_INLINE_DENOISE_HARD": "1",
        "GPR_INLINE_DENOISE_T_LH": "2",
        "GPR_INLINE_DENOISE_T_HL": "3",
        "GPR_INLINE_DENOISE_T_HH": "6",
        "GPR_INLINE_DENOISE_T_CH2_LH": "3",
        "GPR_BENCH_PIXEL_FORMAT": "1",
        "GPR_BENCH_GVID_SCATTER": "1",
        "GPR_BENCH_GVID_FPS": "24.000000",
    }
    target_command = (
        "python3 tools/run_labs_target_bench.py "
        "--bench <pi>/bench_fused --raw <pi>/GP017602_native12.raw "
        "--output-dir <external_artifacts>/<probe_id> --frames <frames> "
        "--target-fps 24 --source-width 4096 --source-height 3072 "
        "--capture-width 4096 --capture-height 3072 --quality 8 "
        "--wavelet-levels 1 --no-decimate --pixel-format 1 "
        "--direct-gvid --target-evidence "
        "--source-provenance-root <repo>"
    )
    return [
        {
            "probe_id": "current_source_sustained_repeat_240f",
            "priority": 1,
            "purpose": "refresh the current-source T236 direct .gvid baseline after any source edit",
            "frames": 240,
            "env": base_env,
            "command_template": target_command.replace("<probe_id>", "current_source_sustained_repeat_240f").replace("<frames>", "240"),
            "new_information": "separates real source changes from Pi run-to-run variance before chasing sub-millisecond wins",
            "acceptance": {
                "quality_storage_boundary_ok": quality_storage_boundary_ok,
                "loop_ms_max": TARGET_FRAME_MS,
                "wall_fps_min": TARGET_FPS,
            },
        },
        {
            "probe_id": "encoder_hotrow_profile_30f",
            "priority": 2,
            "purpose": "identify which encoder rows/bands own the remaining encode-side budget",
            "frames": 30,
            "env": {**base_env, "JANS_INLINE_PROFILE": "1"},
            "command_template": target_command.replace("<probe_id>", "encoder_hotrow_profile_30f").replace("<frames>", "30"),
            "new_information": "targets worker hot rows instead of repeating rejected storage and scheduler probes",
            "acceptance": {
                "dominant_stage_named": True,
                "candidate_save_ms_needed": round(max(required_loop_reduction, 0.0), 3),
            },
        },
        {
            "probe_id": "camera_like_handoff_floor_240f",
            "priority": 3,
            "purpose": "measure the minimum possible Pi handoff cost with direct container write and no per-frame wrapper work",
            "frames": 240,
            "env": base_env,
            "command_template": target_command.replace("<probe_id>", "camera_like_handoff_floor_240f").replace("<frames>", "240"),
            "new_information": "tests whether the 2.437 ms wall gap is Pi harness handoff overhead or unavoidable target cost",
            "acceptance": {
                "wall_gap_ms_max": 0.0,
                "wall_save_ms_needed": round(max(required_wall_reduction, 0.0), 3),
            },
        },
        {
            "probe_id": "indexed_writev_plus_clean_source_ab_240f",
            "priority": 4,
            "purpose": "rerun the best visual-neutral write-indexing near miss on the current cleaned source in both A/B orders",
            "frames": 240,
            "env": {**base_env, "GPR_BENCH_GVID_WRITEV": "1"},
            "command_template": target_command.replace("<probe_id>", "indexed_writev_plus_clean_source_ab_240f").replace("<frames>", "240"),
            "new_information": "only worth keeping if it beats the current-source baseline in both orderings and closes wall throughput",
            "acceptance": {
                "both_orders_win": True,
                "loop_ms_max": TARGET_FRAME_MS,
                "wall_fps_min": TARGET_FPS,
            },
        },
        {
            "probe_id": "target_hardware_or_20fps_decision_receipt",
            "priority": 5,
            "purpose": "close the product decision if Pi remains a conservative stand-in rather than the final camera path",
            "frames": 14400,
            "env": base_env,
            "command_template": target_command.replace("<probe_id>", "target_hardware_or_20fps_decision_receipt").replace("<frames>", "14400"),
            "new_information": "promotes either real Mission 1 strict-24 evidence or an explicit 20 fps Pi proxy product boundary",
            "acceptance": {
                "mission1_strict24_receipt": True,
                "or_explicit_20fps_proxy_policy": True,
            },
        },
    ]


def build_optimization_plan(
    summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    decision: str,
    required_loop_reduction: float,
    required_wall_reduction: float,
    quality_storage_boundary_ok: bool,
) -> dict[str, Any]:
    rejected = collect_rejected_paths(summary)
    near_misses = collect_near_misses(candidates)
    dominant_gap = "wall" if required_wall_reduction > required_loop_reduction else "loop"
    do_not_repeat = [
        str(row["name"])
        for row in rejected
        if isinstance(row.get("name"), str)
    ]
    return {
        "status": (
            "visual_quality_and_storage_are_not_the_current_blocker"
            if quality_storage_boundary_ok
            else "quality_or_storage_boundary_needs_recheck"
        ),
        "dominant_gap": dominant_gap,
        "required_reduction_ms": {
            "loop": required_loop_reduction,
            "wall": required_wall_reduction,
        },
        "near_miss_candidates": near_misses,
        "already_rejected": rejected,
        "do_not_repeat": do_not_repeat,
        "next_steps": [
            "measure a camera-like sensor/DMA-to-encoder handoff path that removes Pi userland file-read overhead",
            "try a single-owner frame buffer path that avoids ping-pong writer cache contention and avoids extra scatter async copies",
            "profile encoder hot rows inside the accepted T236/T238 quality boundary before changing codec thresholds",
            "accept the 20+ fps Pi proxy only as a product decision; keep strict 24 fps blocked until target hardware or a new receipt proves it",
        ],
        "next_probe_matrix": build_next_probe_matrix(
            required_loop_reduction,
            required_wall_reduction,
            quality_storage_boundary_ok,
        ),
        "acceptance_criteria": [
            "same codec quality profile and payload class remain visually neutral against the current Mission 1 dashboard",
            "gvid_valid, storage_target_met, no drops, and interruption recovery stay true",
            "median encode+write loop time is <= 41.6667 ms",
            "whole-run wall throughput is >= 24.0 fps when wall evidence is present",
        ],
        "decision_context": decision,
    }


def build_report(summary: dict[str, Any]) -> dict[str, Any]:
    candidates = collect_candidates(summary)
    loop_best = best_by(candidates, "loop_gap_ms")
    wall_best = best_by(candidates, "wall_gap_ms", require_wall=True)
    storage_ok = all(row.get("storage_target_met") is not False for row in candidates)
    quality_ok = all(str(row.get("quality_impact") or "").startswith("none") for row in candidates if row.get("quality_impact"))
    strict_passes = [row for row in candidates if row.get("strict_24_pass") is True]
    loop_gap = safe_float((loop_best or {}).get("loop_gap_ms"))
    wall_gap = safe_float((wall_best or {}).get("wall_gap_ms"))
    required_loop_reduction = max(loop_gap or 0.0, 0.0)
    required_wall_reduction = max(wall_gap or 0.0, 0.0)
    if strict_passes:
        decision = "strict24_candidate_present"
    elif wall_best is not None and required_wall_reduction > required_loop_reduction:
        decision = "strict24_open_wall_throughput_gap"
    else:
        decision = "strict24_open_loop_timing_gap"
    quality_storage_boundary_ok = bool(storage_ok and quality_ok)
    return {
        "schema": SCHEMA,
        "target_fps": TARGET_FPS,
        "target_frame_ms": TARGET_FRAME_MS,
        "decision": decision,
        "quality_storage_boundary_ok": quality_storage_boundary_ok,
        "strict24_pass_count": len(strict_passes),
        "required_loop_reduction_ms": required_loop_reduction,
        "required_wall_reduction_ms": required_wall_reduction,
        "best_loop_candidate": loop_best,
        "best_wall_candidate": wall_best,
        "candidate_count": len(candidates),
        "candidates": sorted(
            candidates,
            key=lambda row: (
                float(row["loop_gap_ms"]) if row.get("loop_gap_ms") is not None else 1e9,
                row["name"],
            ),
        ),
        "next_optimization_target": (
            "reduce sustained wall time and encode/write handoff overhead"
            if decision == "strict24_open_wall_throughput_gap"
            else "reduce median encode+write loop time"
        ),
        "optimization_plan": build_optimization_plan(
            summary,
            candidates,
            decision,
            required_loop_reduction,
            required_wall_reduction,
            quality_storage_boundary_ok,
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=default_external_root())
    ap.add_argument("--write-summary", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    if args.write_summary:
        write_summary = json.loads(args.write_summary.read_text(encoding="utf-8"))
    else:
        write_summary = load_write_summary(args.external_root)
    report = build_report(write_summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "decision": report["decision"],
        "required_loop_reduction_ms": report["required_loop_reduction_ms"],
        "required_wall_reduction_ms": report["required_wall_reduction_ms"],
        "best_loop": (report.get("best_loop_candidate") or {}).get("name"),
        "best_wall": (report.get("best_wall_candidate") or {}).get("name"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
