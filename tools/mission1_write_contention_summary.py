#!/usr/bin/env python3
"""Summarize Mission 1 native12 write-contention evidence."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


STRICT_24_FRAME_MS = 1000.0 / 24.0
WRITER_ISOLATION = "mission1_writer_contention_isolation_20260617/summary.json"
SINGLE_ISOLATION = "mission1_single_pingpong_isolation_20260617/summary.json"
T236_ENCODE_ONLY = "current_goal_t236_build_variant_probe_GP017602_120f_20260618/summary.json"
T236_REAL_WRITE = "current_goal_t236_write_build_probe_GP017602_240f_20260618/summary.json"
T236_CLEAN_PI_PROBE = "current_goal_t236_clean_pi_probe_GP017602_60f_20260618/summary.json"
T236_PREALLOC_PROBE = "current_goal_t236_prealloc_probe_GP017602_60f_20260618/summary.json"
T236_SDWRITE_PROBE = "current_goal_t236_sdwrite_probe_GP017602_60f_20260618/summary.json"
T236_LTO_PROBE = "current_goal_t236_lto_probe_GP017602_60f_20260618/summary.json"
T236_SYNCRANGE_BASELINE = "current_goal_t236_syncrange_probe_GP017602_120f_20260618/baseline/labs_target_bench.json"
T236_SYNCRANGE_CANDIDATE = "current_goal_t236_syncrange_probe_GP017602_120f_20260618/sync_range/labs_target_bench.json"
T236_NEON_ZERO_CANDIDATE = "current_goal_t236_neonzero_GP017602_120f_20260618/labs_target_bench.json"
T236_PWRITEV_CANDIDATE = "current_goal_t236_pwritev_probe_GP017602_120f_20260618/labs_target_bench.json"
T236_COALESCE_PROBE = "current_goal_t236_coalesce_probe_GP017602_240f_20260618/summary.json"
T236_COALESCE_NATIVE_PROBE = "current_goal_t236_coalesce_native_probe_GP017602_240f_20260618/summary.json"
T236_DONTNEED_PROBE = "current_goal_t236_dontneed_probe_GP017602_240f_20260618/summary.json"
T236_EXACT_PGO_PROBE = "current_sync_t236_exact_encode_pgo_ofast_20260618/summary.json"
T236_LAYOUT_ALIGN_PROBE = "current_goal_t236_layoutalign_probe_GP017602_120f_20260618/summary.json"
T236_IONICE_PROBE = "current_sync_t236_ionice_probe_20260618/summary.json"
T236_TIMING_DETAIL_PROBE = "current_goal_t236_timing_detail_30f_20260618/labs_target_bench.json"
T236_PIN_PROBE = "current_goal_t236_pin_probe_20260618/summary.json"
T236_SCATTER_ASYNC_PROBE = "current_goal_t236_scatter_async_probe_20260618/summary.json"
T236_LLRICE_SWEEP_PROBE = "current_goal_t236_llrice_sweep_GP017602_30f_20260618/summary.json"
T236_LLRICE_K6556_AB_PROBE = "current_goal_t236_llrice_k6556_ab_GP017602_120f_20260618/summary.json"
T236_WRITEV_INDEX_PROBE = "current_goal_writev_index_probe_GP017602_240f_ba_20260618/summary.json"
T236_COALESCE_INDEX_PROBE = "current_goal_t236_coalesce_index_probe_GP017602_240f_ab_20260618/summary.json"
T236_WRITER_HANDOFF_RECEIPT = "current_goal_writer_handoff_t236_GP017602_60f_20260618/labs_target_bench.json"
T236_EXPLICIT_GAP_RECEIPT = "current_goal_gap_receipt_t236_GP017602_240f_20260618/labs_target_bench.json"
T236_CURRENT_SOURCE_SUSTAINED_RECEIPT = "current_goal_provenance_t236_GP017602_240f_20260618/labs_target_bench.json"
T236_WRITER_CORE_PROBE = "current_goal_writer_core_probe_GP017602_60f_20260619_t236s264_recorded/summary.json"
T236_COALESCE_SCOUT_PROBE = "current_goal_t236_coalesce_scout_20260619/summary.json"
T236_PARTITION_ABAB_PROBE = "current_goal_t236_partition_abab_probe_20260619/summary.json"


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_json_optional(path: Path) -> Any | None:
    if not path.exists():
        return None
    return read_json(path)


def row_by_name(rows: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            out[row["name"]] = row
    return out


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_row(name: str, row: dict[str, Any]) -> dict[str, Any]:
    total = safe_float(row.get("total_median"))
    encode = safe_float(row.get("encode_median"))
    write = safe_float(row.get("write_median"))
    return {
        "name": name,
        "total_median_ms": total,
        "encode_median_ms": encode,
        "write_median_ms": write,
        "fps_median": (1000.0 / total) if total and total > 0 else None,
        "strict_24_pass": bool(total is not None and total <= STRICT_24_FRAME_MS),
        "payload_kib_median": safe_float(row.get("payload_kib_median")),
    }


def phase_median(case: dict[str, Any], phase: str) -> float | None:
    phases = case.get("phases")
    if not isinstance(phases, dict):
        return None
    phase_row = phases.get(phase)
    if not isinstance(phase_row, dict):
        return None
    return safe_float(phase_row.get("median_ms"))


def summarize_phase_case(name: str, case: dict[str, Any]) -> dict[str, Any]:
    total = phase_median(case, "total")
    encode = phase_median(case, "encode")
    write = phase_median(case, "write")
    payload = phase_median(case, "payload_kib")
    return {
        "name": name,
        "total_median_ms": total,
        "encode_median_ms": encode,
        "write_median_ms": write,
        "fps_median": (1000.0 / total) if total and total > 0 else None,
        "strict_24_pass": bool(total is not None and total <= STRICT_24_FRAME_MS),
        "payload_kib_median": payload,
    }


def best_phase_case(summary: Any, phase: str) -> dict[str, Any] | None:
    if not isinstance(summary, dict):
        return None
    cases = summary.get("cases")
    if not isinstance(cases, dict):
        return None
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for name, case in cases.items():
        if not isinstance(name, str) or not isinstance(case, dict):
            continue
        value = phase_median(case, phase)
        if value is not None:
            candidates.append((value, name, case))
    if not candidates:
        return None
    _, name, case = min(candidates)
    return summarize_phase_case(name, case)


def summarize_t236_boundary(artifact_root: Path) -> dict[str, Any] | None:
    encode_path = artifact_root / T236_ENCODE_ONLY
    write_path = artifact_root / T236_REAL_WRITE
    encode_summary = read_json_optional(encode_path)
    write_summary = read_json_optional(write_path)
    encode_case = best_phase_case(encode_summary, "encode")
    write_case = best_phase_case(write_summary, "total")
    if not encode_case or not write_case:
        return None

    total = write_case.get("total_median_ms")
    gap = total - STRICT_24_FRAME_MS if isinstance(total, float) else None
    return {
        "source_receipts": {
            "encode_only": str(encode_path),
            "real_write": str(write_path),
        },
        "encode_only_best_case": encode_case,
        "real_write_best_case": write_case,
        "strict_24_total_gap_ms": gap,
        "visual_quality_impact": "none_detected_quality_storage_boundary",
        "blocker_class": (
            "visual_neutral_write_handoff_margin"
            if encode_case["strict_24_pass"] and not write_case["strict_24_pass"]
            else "unknown"
        ),
    }


def summarize_t236_clean_probe(artifact_root: Path) -> dict[str, Any] | None:
    probe_path = artifact_root / T236_CLEAN_PI_PROBE
    probe = read_json_optional(probe_path)
    if not isinstance(probe, dict):
        return None
    decision = probe.get("decision")
    cases = probe.get("cases")
    if not isinstance(decision, dict) or not isinstance(cases, dict):
        return None
    ofast_no_write = ((cases.get("ofast_no_write") or {}).get("metrics") or {})
    ofast_real_write = ((cases.get("ofast_real_write") or {}).get("metrics") or {})
    ofast_pingpong = ((cases.get("ofast_pingpong") or {}).get("metrics") or {})
    return {
        "source_receipt": str(probe_path),
        "classification": decision.get("classification"),
        "quality_impact": decision.get("quality_impact"),
        "ofast_no_write": {
            "total_median_ms": safe_float(ofast_no_write.get("total_median_ms")),
            "fps_median": safe_float(ofast_no_write.get("fps_median")),
            "strict_24_pass": bool(ofast_no_write.get("strict_24_pass")),
        },
        "ofast_real_write": {
            "total_median_ms": safe_float(ofast_real_write.get("total_median_ms")),
            "encode_median_ms": safe_float(ofast_real_write.get("encode_median_ms")),
            "write_median_ms": safe_float(ofast_real_write.get("write_median_ms")),
            "fps_median": safe_float(ofast_real_write.get("fps_median")),
            "strict_24_pass": bool(ofast_real_write.get("strict_24_pass")),
        },
        "ofast_real_write_gap_ms": safe_float(decision.get("ofast_real_write_gap_ms")),
        "pingpong": {
            "total_median_ms": safe_float(ofast_pingpong.get("total_median_ms")),
            "fps_median": safe_float(ofast_pingpong.get("fps_median")),
            "strict_24_pass": bool(ofast_pingpong.get("strict_24_pass")),
            "rejected": bool(decision.get("pingpong_rejected")),
            "regression_ms": safe_float(decision.get("pingpong_regression_ms")),
        },
        "recommended_next": decision.get("recommended_next"),
    }


def metrics_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "total_median_ms": safe_float(metrics.get("total_median_ms")),
        "encode_median_ms": safe_float(metrics.get("encode_median_ms")),
        "write_median_ms": safe_float(metrics.get("write_median_ms")),
        "fps_median": safe_float(metrics.get("fps_median")),
        "strict_24_pass": bool(metrics.get("strict_24_pass")),
    }


def coalesced_case_metrics(case: dict[str, Any]) -> dict[str, Any]:
    phases = case.get("phases") if isinstance(case.get("phases"), dict) else {}
    total = safe_float(((phases.get("total") or {}).get("median_ms")))
    encode = safe_float(((phases.get("encode") or {}).get("median_ms")))
    write = safe_float(((phases.get("write") or {}).get("median_ms")))
    payload = safe_float(((phases.get("payload_kib") or {}).get("median_ms")))
    return {
        "total_median_ms": total,
        "encode_median_ms": encode,
        "write_median_ms": write,
        "fps_median": safe_float(case.get("fps_median")) or ((1000.0 / total) if total and total > 0 else None),
        "strict_24_pass": bool(case.get("strict24_total_pass")),
        "payload_kib_median": payload,
    }


def labs_receipt_metrics(receipt: dict[str, Any]) -> dict[str, Any]:
    phases = ((receipt.get("bench_phase_timing") or {}).get("phase_ms") or {})
    timing = receipt.get("timing") if isinstance(receipt.get("timing"), dict) else {}
    verdict = receipt.get("verdict") if isinstance(receipt.get("verdict"), dict) else {}
    total = safe_float(((phases.get("total") or {}).get("median_ms")))
    encode = safe_float(((phases.get("encode") or {}).get("median_ms")))
    write = safe_float(((phases.get("write") or {}).get("median_ms")))
    payload = safe_float(((phases.get("payload_kib") or {}).get("median")))
    fps = safe_float(timing.get("fps_median"))
    return {
        "total_median_ms": total,
        "encode_median_ms": encode,
        "write_median_ms": write,
        "fps_median": fps,
        "strict_24_pass": bool(verdict.get("fps_target_met")),
        "storage_target_met": verdict.get("storage_target_met"),
        "gvid_valid": verdict.get("gvid_valid"),
        "payload_kib_median": payload,
    }


def partition_case_metrics(case: dict[str, Any]) -> dict[str, Any]:
    phases = case.get("phases") if isinstance(case.get("phases"), dict) else {}
    total = safe_float(((phases.get("total") or {}).get("median")))
    encode = safe_float(((phases.get("encode") or {}).get("median")))
    write = safe_float(((phases.get("write") or {}).get("median")))
    payload = safe_float(((phases.get("payload_kib") or {}).get("median")))
    wall = case.get("wall") if isinstance(case.get("wall"), dict) else {}
    return {
        "total_median_ms": total,
        "encode_median_ms": encode,
        "write_median_ms": write,
        "fps_median": (1000.0 / total) if total and total > 0 else None,
        "wall_fps": safe_float(wall.get("wall_fps")),
        "strict_24_pass": bool(total is not None and total <= STRICT_24_FRAME_MS),
        "payload_kib_median": payload,
        "capture_size_bytes": case.get("capture_size_bytes"),
    }


def rows_by_case(rows: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("case"), str):
            out[row["case"]] = row
    return out


def summarize_writer_handoff_receipt(
    artifact_root: Path,
    receipt_rel: str = T236_WRITER_HANDOFF_RECEIPT,
    classification: str = "visual_neutral_writer_handoff_not_deferred_drain",
) -> dict[str, Any] | None:
    path = artifact_root / receipt_rel
    receipt = read_json_optional(path)
    if not isinstance(receipt, dict):
        return None
    phases = ((receipt.get("bench_phase_timing") or {}).get("phase_ms") or {})
    writer = receipt.get("writer_handoff") if isinstance(receipt.get("writer_handoff"), dict) else {}
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    verdict = receipt.get("verdict") if isinstance(receipt.get("verdict"), dict) else {}
    storage = ((receipt.get("storage") or {}).get("target") or {})
    encode = phases.get("encode") if isinstance(phases.get("encode"), dict) else {}
    write = phases.get("write") if isinstance(phases.get("write"), dict) else {}
    total = phases.get("total") if isinstance(phases.get("total"), dict) else {}
    return {
        "source_receipt": str(path),
        "classification": classification,
        "metrics": labs_receipt_metrics(receipt),
        "actual_wall_fps": safe_float(target.get("actual_wall_fps")),
        "writer_handoff": writer,
        "encode_median_ms": safe_float(encode.get("median_ms")),
        "write_median_ms": safe_float(write.get("median_ms")),
        "total_median_ms": safe_float(total.get("median_ms")),
        "payload_kib_median": safe_float(((phases.get("payload_kib") or {}).get("median"))),
        "storage_fits_target": storage.get("fits_target"),
        "fps_target_met": verdict.get("fps_target_met"),
        "strict_24_gap_ms": (
            safe_float(total.get("median_ms")) - STRICT_24_FRAME_MS
            if safe_float(total.get("median_ms")) is not None
            else None
        ),
        "loop_target_gap_ms": safe_float(writer.get("loop_target_gap_ms")),
        "wall_target_gap_ms": safe_float(writer.get("wall_target_gap_ms")),
        "bottleneck_target_gap_ms": safe_float(writer.get("bottleneck_target_gap_ms")),
        "deferred_writer_work_present": writer.get("deferred_writer_work_present"),
    }


def summarize_current_source_sustained_receipt(artifact_root: Path) -> dict[str, Any] | None:
    path = artifact_root / T236_CURRENT_SOURCE_SUSTAINED_RECEIPT
    receipt = read_json_optional(path)
    if not isinstance(receipt, dict):
        return None
    metrics = labs_receipt_metrics(receipt)
    timing = receipt.get("timing") if isinstance(receipt.get("timing"), dict) else {}
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    build = ((receipt.get("bench") or {}).get("build") or {})
    storage = ((receipt.get("storage") or {}).get("target") or {})
    source_provenance = receipt.get("source_provenance") if isinstance(receipt.get("source_provenance"), dict) else {}
    total = safe_float(metrics.get("total_median_ms"))
    return {
        "source_receipt": str(path),
        "classification": "visual_neutral_sustained_current_source_strict24_miss",
        "quality_impact": "none_detected_no_codec_parameter_change",
        "metrics": metrics,
        "frames": int(timing.get("n", 0)) if timing.get("n") is not None else None,
        "actual_wall_fps": safe_float(target.get("actual_wall_fps")),
        "strict_24_gap_ms": total - STRICT_24_FRAME_MS if total is not None else None,
        "storage_fits_target": storage.get("fits_target"),
        "binary_sha256": build.get("binary_sha256"),
        "source_provenance_sha256": source_provenance.get("sha256"),
        "source_provenance_file_count": source_provenance.get("file_count"),
        "compiler_flags": {
            "encoder_c_flags": build.get("encoder_c_flags"),
            "bench_c_flags": build.get("bench_c_flags"),
        },
    }


def pgo_case_metrics(case: dict[str, Any]) -> dict[str, Any]:
    total = safe_float(((case.get("total") or {}).get("median_ms")))
    encode = safe_float(((case.get("encode") or {}).get("median_ms")))
    write = safe_float(((case.get("write") or {}).get("median_ms")))
    payload = safe_float(((case.get("payload_kib") or {}).get("median_ms")))
    return {
        "total_median_ms": total,
        "encode_median_ms": encode,
        "write_median_ms": write,
        "fps_median": safe_float(case.get("fps_median")) or ((1000.0 / total) if total and total > 0 else None),
        "strict_24_pass": bool(total is not None and total <= STRICT_24_FRAME_MS),
        "payload_kib_median": payload,
    }


def summarize_recent_followup_probes(artifact_root: Path) -> dict[str, Any]:
    prealloc_path = artifact_root / T236_PREALLOC_PROBE
    sdwrite_path = artifact_root / T236_SDWRITE_PROBE
    lto_path = artifact_root / T236_LTO_PROBE
    syncrange_baseline_path = artifact_root / T236_SYNCRANGE_BASELINE
    syncrange_candidate_path = artifact_root / T236_SYNCRANGE_CANDIDATE
    neon_zero_candidate_path = artifact_root / T236_NEON_ZERO_CANDIDATE
    pwritev_candidate_path = artifact_root / T236_PWRITEV_CANDIDATE
    coalesce_path = artifact_root / T236_COALESCE_PROBE
    coalesce_native_path = artifact_root / T236_COALESCE_NATIVE_PROBE
    dontneed_path = artifact_root / T236_DONTNEED_PROBE
    exact_pgo_path = artifact_root / T236_EXACT_PGO_PROBE
    layout_align_path = artifact_root / T236_LAYOUT_ALIGN_PROBE
    ionice_path = artifact_root / T236_IONICE_PROBE
    timing_detail_path = artifact_root / T236_TIMING_DETAIL_PROBE
    pin_probe_path = artifact_root / T236_PIN_PROBE
    scatter_async_path = artifact_root / T236_SCATTER_ASYNC_PROBE
    llrice_sweep_path = artifact_root / T236_LLRICE_SWEEP_PROBE
    llrice_k6556_ab_path = artifact_root / T236_LLRICE_K6556_AB_PROBE
    writev_index_path = artifact_root / T236_WRITEV_INDEX_PROBE
    coalesce_index_path = artifact_root / T236_COALESCE_INDEX_PROBE
    coalesce_scout_path = artifact_root / T236_COALESCE_SCOUT_PROBE
    partition_abab_path = artifact_root / T236_PARTITION_ABAB_PROBE
    writer_core_path = artifact_root / T236_WRITER_CORE_PROBE

    out: dict[str, Any] = {}

    sustained = summarize_current_source_sustained_receipt(artifact_root)
    if sustained is not None:
        out["current_source_t236_sustained_240f"] = sustained

    writer_handoff = summarize_writer_handoff_receipt(artifact_root)
    if writer_handoff is not None:
        out["writer_handoff_t236"] = writer_handoff

    explicit_gap = summarize_writer_handoff_receipt(
        artifact_root,
        T236_EXPLICIT_GAP_RECEIPT,
        "visual_neutral_explicit_loop_wall_gap_receipt",
    )
    if explicit_gap is not None:
        out["explicit_gap_t236_240f"] = explicit_gap

    prealloc = read_json_optional(prealloc_path)
    if isinstance(prealloc, dict):
        decision = prealloc.get("decision") if isinstance(prealloc.get("decision"), dict) else {}
        cases = prealloc.get("cases") if isinstance(prealloc.get("cases"), dict) else {}
        baseline = ((cases.get("baseline") or {}).get("metrics") or {})
        candidate = ((cases.get("prealloc") or {}).get("metrics") or {})
        out["prealloc"] = {
            "source_receipt": str(prealloc_path),
            "classification": decision.get("classification"),
            "quality_impact": decision.get("quality_impact"),
            "baseline": metrics_summary(baseline),
            "candidate": metrics_summary(candidate),
            "total_regression_ms": safe_float(decision.get("total_regression_ms")),
            "write_delta_ms": safe_float(decision.get("write_delta_ms")),
            "rejected": decision.get("classification") == "rejected_visual_neutral_storage_preallocation",
        }

    sdwrite = read_json_optional(sdwrite_path)
    if isinstance(sdwrite, dict):
        decision = sdwrite.get("decision") if isinstance(sdwrite.get("decision"), dict) else {}
        metrics = sdwrite.get("metrics") if isinstance(sdwrite.get("metrics"), dict) else {}
        out["sdwrite"] = {
            "source_receipt": str(sdwrite_path),
            "classification": decision.get("classification"),
            "quality_impact": decision.get("quality_impact"),
            "storage_interpretation": decision.get("storage_interpretation"),
            "metrics": metrics_summary(metrics),
            "strict_24_gap_ms": safe_float(decision.get("strict_24_gap_ms")),
        }

    lto = read_json_optional(lto_path)
    if isinstance(lto, dict):
        decision = lto.get("decision") if isinstance(lto.get("decision"), dict) else {}
        cases = lto.get("cases") if isinstance(lto.get("cases"), dict) else {}
        no_write = ((cases.get("lto_no_write") or {}).get("metrics") or {})
        real_write = ((cases.get("lto_real_write") or {}).get("metrics") or {})
        out["lto"] = {
            "source_receipt": str(lto_path),
            "classification": decision.get("classification"),
            "quality_impact": decision.get("quality_impact"),
            "no_write": metrics_summary(no_write),
            "real_write": metrics_summary(real_write),
            "real_write_gap_ms": safe_float(decision.get("lto_real_write_gap_ms")),
            "rejected": decision.get("classification") == "rejected_visual_neutral_lto_build_variant",
        }

    exact_pgo = read_json_optional(exact_pgo_path)
    if isinstance(exact_pgo, dict):
        baseline_encode = pgo_case_metrics(exact_pgo.get("baseline_encode_only") or {})
        pgo_encode = pgo_case_metrics(exact_pgo.get("pgo_encode_only") or {})
        baseline_write = pgo_case_metrics(exact_pgo.get("baseline_real_write") or {})
        pgo_write = pgo_case_metrics(exact_pgo.get("pgo_real_write") or {})
        encode_delta = safe_float(exact_pgo.get("encode_only_delta_ms"))
        total_delta = safe_float(exact_pgo.get("real_write_total_delta_ms"))
        out["exact_encode_pgo"] = {
            "source_receipt": str(exact_pgo_path),
            "classification": "rejected_visual_neutral_gcc_pgo_code_layout",
            "quality_impact": "none_byte_identical_gvid",
            "compiler": exact_pgo.get("compiler"),
            "frames_train": exact_pgo.get("frames_train"),
            "frames_eval": exact_pgo.get("frames_eval"),
            "profile_gcda_count": exact_pgo.get("profile_gcda_count"),
            "byte_identical_gvid": bool(exact_pgo.get("byte_identical_gvid")),
            "baseline_encode_only": baseline_encode,
            "pgo_encode_only": pgo_encode,
            "baseline_real_write": baseline_write,
            "pgo_real_write": pgo_write,
            "encode_only_delta_ms": encode_delta,
            "real_write_total_delta_ms": total_delta,
            "rejected": bool(
                not exact_pgo.get("byte_identical_gvid")
                or encode_delta is None
                or total_delta is None
                or encode_delta >= 0.0
                or total_delta >= 0.0
                or not pgo_write.get("strict_24_pass")
            ),
        }

    layout_align = read_json_optional(layout_align_path)
    if isinstance(layout_align, dict):
        baseline = dict(layout_align.get("baseline") if isinstance(layout_align.get("baseline"), dict) else {})
        candidate = dict(layout_align.get("layoutalign") if isinstance(layout_align.get("layoutalign"), dict) else {})
        for row in (baseline, candidate):
            if "strict_24_pass" not in row:
                verdict = row.get("verdict") if isinstance(row.get("verdict"), dict) else {}
                row["strict_24_pass"] = bool(verdict.get("fps_target_met"))
        total_delta = safe_float(layout_align.get("total_delta_ms"))
        encode_delta = safe_float(layout_align.get("encode_delta_ms"))
        write_delta = safe_float(layout_align.get("write_delta_ms"))
        fps_delta = safe_float(layout_align.get("fps_delta"))
        out["layout_alignment"] = {
            "source_receipt": str(layout_align_path),
            "classification": "rejected_visual_neutral_gcc_layout_alignment_flags",
            "quality_impact": layout_align.get("quality_impact"),
            "flags": layout_align.get("flags"),
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": total_delta,
            "encode_delta_ms": encode_delta,
            "write_delta_ms": write_delta,
            "fps_delta": fps_delta,
            "rejected": bool(
                layout_align.get("decision") == "reject_no_strict24_or_no_sustained_win"
                and total_delta is not None
                and total_delta > 0.0
                and candidate.get("strict_24_pass") is False
                and candidate.get("verdict", {}).get("gvid_valid") is True
                and candidate.get("payload_kib_median") == baseline.get("payload_kib_median")
            ),
        }

    ionice = read_json_optional(ionice_path)
    if isinstance(ionice, dict):
        cases = ionice.get("cases") if isinstance(ionice.get("cases"), dict) else {}
        baseline = pgo_case_metrics(cases.get("baseline") or {})
        idle = pgo_case_metrics(cases.get("ionice_idle") or {})
        best_effort_low = pgo_case_metrics(cases.get("ionice_best_effort_low") or {})
        idle_raw = cases.get("ionice_idle") if isinstance(cases.get("ionice_idle"), dict) else {}
        best_raw = cases.get("ionice_best_effort_low") if isinstance(cases.get("ionice_best_effort_low"), dict) else {}
        idle_delta = safe_float(idle_raw.get("delta_total_vs_baseline_ms"))
        best_delta = safe_float(best_raw.get("delta_total_vs_baseline_ms"))
        out["ionice"] = {
            "source_receipt": str(ionice_path),
            "classification": "rejected_visual_neutral_process_io_priority",
            "quality_impact": "none_byte_identical_gvid",
            "decision": ionice.get("decision"),
            "baseline": baseline,
            "ionice_idle": idle,
            "ionice_best_effort_low": best_effort_low,
            "ionice_idle_total_delta_ms": idle_delta,
            "ionice_best_effort_low_total_delta_ms": best_delta,
            "byte_identical_gvid": bool(
                idle_raw.get("byte_identical_to_baseline")
                and best_raw.get("byte_identical_to_baseline")
            ),
            "rejected": bool(
                ionice.get("decision") == "reject_no_timing_win"
                and idle_delta is not None
                and best_delta is not None
                and idle_delta > 0.0
                and best_delta > 0.0
                and idle_raw.get("byte_identical_to_baseline")
                and best_raw.get("byte_identical_to_baseline")
            ),
        }

    syncrange_baseline = read_json_optional(syncrange_baseline_path)
    syncrange_candidate = read_json_optional(syncrange_candidate_path)
    if isinstance(syncrange_baseline, dict) and isinstance(syncrange_candidate, dict):
        baseline = labs_receipt_metrics(syncrange_baseline)
        candidate = labs_receipt_metrics(syncrange_candidate)
        total_delta = None
        if baseline.get("total_median_ms") is not None and candidate.get("total_median_ms") is not None:
            total_delta = candidate["total_median_ms"] - baseline["total_median_ms"]
        out["sync_range"] = {
            "source_receipts": {
                "baseline": str(syncrange_baseline_path),
                "candidate": str(syncrange_candidate_path),
            },
            "classification": "rejected_visual_neutral_linux_writeback_hint",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": total_delta,
            "rejected": bool(total_delta is None or total_delta >= 0.0 or not candidate.get("strict_24_pass")),
        }

    neon_zero_candidate = read_json_optional(neon_zero_candidate_path)
    if isinstance(syncrange_baseline, dict) and isinstance(neon_zero_candidate, dict):
        baseline = labs_receipt_metrics(syncrange_baseline)
        candidate = labs_receipt_metrics(neon_zero_candidate)
        total_delta = None
        encode_delta = None
        if baseline.get("total_median_ms") is not None and candidate.get("total_median_ms") is not None:
            total_delta = candidate["total_median_ms"] - baseline["total_median_ms"]
        if baseline.get("encode_median_ms") is not None and candidate.get("encode_median_ms") is not None:
            encode_delta = candidate["encode_median_ms"] - baseline["encode_median_ms"]
        out["neon_zero_scan"] = {
            "source_receipts": {
                "baseline": str(syncrange_baseline_path),
                "candidate": str(neon_zero_candidate_path),
            },
            "classification": "rejected_visual_neutral_neon_zero_scan",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": total_delta,
            "encode_delta_ms": encode_delta,
            "rejected": bool(total_delta is None or total_delta >= 0.0 or not candidate.get("strict_24_pass")),
        }

    pwritev_candidate = read_json_optional(pwritev_candidate_path)
    if isinstance(syncrange_baseline, dict) and isinstance(pwritev_candidate, dict):
        baseline = labs_receipt_metrics(syncrange_baseline)
        candidate = labs_receipt_metrics(pwritev_candidate)
        total_delta = None
        write_delta = None
        if baseline.get("total_median_ms") is not None and candidate.get("total_median_ms") is not None:
            total_delta = candidate["total_median_ms"] - baseline["total_median_ms"]
        if baseline.get("write_median_ms") is not None and candidate.get("write_median_ms") is not None:
            write_delta = candidate["write_median_ms"] - baseline["write_median_ms"]
        out["pwritev"] = {
            "source_receipts": {
                "baseline": str(syncrange_baseline_path),
                "candidate": str(pwritev_candidate_path),
            },
            "classification": "rejected_visual_neutral_explicit_offset_pwritev",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": total_delta,
            "write_delta_ms": write_delta,
            "rejected": bool(total_delta is None or total_delta >= 0.0 or not candidate.get("strict_24_pass")),
        }

    coalesce = read_json_optional(coalesce_path)
    coalesce_native = read_json_optional(coalesce_native_path)
    if isinstance(coalesce, dict) and isinstance(coalesce_native, dict):
        cases = coalesce.get("cases") if isinstance(coalesce.get("cases"), dict) else {}
        native_cases = coalesce_native.get("cases") if isinstance(coalesce_native.get("cases"), dict) else {}
        initial_baseline = coalesced_case_metrics(cases.get("baseline") or {})
        initial_candidate = coalesced_case_metrics(cases.get("coalesce") or {})
        native_baseline = coalesced_case_metrics(native_cases.get("baseline") or {})
        native_candidate = coalesced_case_metrics(native_cases.get("coalesce") or {})
        initial_delta = safe_float(coalesce.get("delta_coalesce_minus_baseline_ms"))
        native_delta = safe_float(coalesce_native.get("delta_coalesce_minus_baseline_ms"))
        out["coalesced_header"] = {
            "source_receipts": {
                "initial": str(coalesce_path),
                "native_repeat": str(coalesce_native_path),
            },
            "classification": "rejected_visual_neutral_coalesced_header",
            "quality_impact": "none_byte_layout_only",
            "initial_decision": coalesce.get("decision"),
            "native_repeat_decision": coalesce_native.get("decision"),
            "initial": {
                "baseline": initial_baseline,
                "candidate": initial_candidate,
                "total_delta_ms": initial_delta,
            },
            "native_repeat": {
                "baseline": native_baseline,
                "candidate": native_candidate,
                "total_delta_ms": native_delta,
            },
            "rejected": bool(
                coalesce_native.get("decision") == "reject_no_timing_win"
                or native_delta is None
                or native_delta >= 0.0
                or not native_candidate.get("strict_24_pass")
            ),
        }

    dontneed = read_json_optional(dontneed_path)
    if isinstance(dontneed, dict):
        baseline = dontneed.get("baseline") if isinstance(dontneed.get("baseline"), dict) else {}
        candidate = (
            dontneed.get("candidate_metrics")
            if isinstance(dontneed.get("candidate_metrics"), dict)
            else {}
        )
        deltas = (
            dontneed.get("delta_candidate_minus_baseline_ms")
            if isinstance(dontneed.get("delta_candidate_minus_baseline_ms"), dict)
            else {}
        )
        out["dontneed"] = {
            "source_receipt": str(dontneed_path),
            "classification": dontneed.get("classification"),
            "quality_impact": dontneed.get("quality_impact"),
            "decision": dontneed.get("decision"),
            "source_change_reverted": bool(dontneed.get("source_change_reverted")),
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": safe_float(deltas.get("total")),
            "encode_delta_ms": safe_float(deltas.get("encode")),
            "write_delta_ms": safe_float(deltas.get("write")),
            "rejected": dontneed.get("decision") == "rejected_no_timing_win",
        }

    timing_detail = read_json_optional(timing_detail_path)
    if isinstance(timing_detail, dict):
        metrics = labs_receipt_metrics(timing_detail)
        fused_total = (((timing_detail.get("fused_timing") or {}).get("stage_ms") or {}).get("total") or {})
        fused_median = safe_float(fused_total.get("median_ms"))
        wall_median = metrics.get("total_median_ms")
        write_median = metrics.get("write_median_ms")
        out["timing_detail_current_t236"] = {
            "source_receipt": str(timing_detail_path),
            "classification": "stage_split_current_t236",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "metrics": metrics,
            "fused_total_median_ms": fused_median,
            "fused_total_strict_24_pass": bool(fused_median is not None and fused_median <= STRICT_24_FRAME_MS),
            "wall_minus_fused_total_ms": (
                wall_median - fused_median
                if isinstance(wall_median, float) and isinstance(fused_median, float)
                else None
            ),
            "write_median_ms": write_median,
            "dominant_stage": ((timing_detail.get("fused_timing") or {}).get("dominant_stage_by_mean_ms")),
            "dominant_phase": ((timing_detail.get("bench_phase_timing") or {}).get("dominant_phase_by_mean_ms")),
        }

    pin_probe = read_json_optional(pin_probe_path)
    if isinstance(pin_probe, dict):
        out["pinning"] = {
            "source_receipt": str(pin_probe_path),
            "classification": pin_probe.get("classification"),
            "quality_impact": pin_probe.get("bytestream_policy"),
            "baseline": pin_probe.get("baseline"),
            "pinned": pin_probe.get("pinned"),
            "total_delta_ms": safe_float(pin_probe.get("total_delta_ms")),
            "encode_delta_ms": safe_float(pin_probe.get("encode_delta_ms")),
            "write_delta_ms": safe_float(pin_probe.get("write_delta_ms")),
            "rejected": pin_probe.get("decision") == "rejected_target_total_regression",
        }

    scatter_async = read_json_optional(scatter_async_path)
    if isinstance(scatter_async, dict):
        out["scatter_async_copy"] = {
            "source_receipt": str(scatter_async_path),
            "classification": scatter_async.get("classification"),
            "quality_impact": scatter_async.get("quality_impact"),
            "baseline": scatter_async.get("baseline"),
            "async_copy": scatter_async.get("async_copy"),
            "total_delta_ms": safe_float(scatter_async.get("total_delta_ms")),
            "encode_delta_ms": safe_float(scatter_async.get("encode_delta_ms")),
            "write_delta_ms": safe_float(scatter_async.get("write_delta_ms")),
            "wall_fps_delta": safe_float(scatter_async.get("wall_fps_delta")),
            "rejected": scatter_async.get("decision") == "rejected_target_total_and_wall_regression",
        }

    writer_core = read_json_optional(writer_core_path)
    if isinstance(writer_core, dict):
        rows = writer_core.get("rows") if isinstance(writer_core.get("rows"), list) else []
        row_map = {row.get("name"): row for row in rows if isinstance(row, dict) and isinstance(row.get("name"), str)}
        comparable_rows = [
            row
            for row in rows
            if isinstance(row, dict) and safe_float(row.get("total_median_ms")) is not None
        ]
        best = min(comparable_rows, key=lambda row: float(row.get("total_median_ms", 1e9)), default={})
        scatter = row_map.get("scatter_baseline") if isinstance(row_map.get("scatter_baseline"), dict) else {}
        pingpong_rows = {
            name: row
            for name, row in row_map.items()
            if isinstance(row, dict) and name.startswith("pingpong_")
        }
        out["writer_core_pinning"] = {
            "source_receipt": str(writer_core_path),
            "schema": writer_core.get("schema"),
            "classification": "rejected_visual_neutral_writer_core_pinning",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "decision": writer_core.get("decision"),
            "reason": writer_core.get("reason"),
            "best": best,
            "scatter_baseline": scatter,
            "pingpong_variants": pingpong_rows,
            "scatter_remained_best": best.get("name") == "scatter_baseline",
            "all_variants_miss_strict24": all(row.get("fps_target_met") is False for row in comparable_rows),
            "rejected": writer_core.get("decision") == "reject_writer_core_pinning_not_strict24_closure",
        }

    llrice_sweep = read_json_optional(llrice_sweep_path)
    llrice_ab = read_json_optional(llrice_k6556_ab_path)
    if isinstance(llrice_sweep, dict) and isinstance(llrice_ab, dict):
        deltas = llrice_ab.get("deltas") if isinstance(llrice_ab.get("deltas"), dict) else {}
        candidate = llrice_ab.get("candidate") if isinstance(llrice_ab.get("candidate"), dict) else {}
        baseline = llrice_ab.get("baseline") if isinstance(llrice_ab.get("baseline"), dict) else {}
        rows = llrice_sweep.get("rows") if isinstance(llrice_sweep.get("rows"), list) else []
        best_short = min(
            (row for row in rows if isinstance(row, dict) and row.get("total_median_ms") is not None),
            key=lambda row: float(row.get("total_median_ms", 1e9)),
            default={},
        )
        out["llrice_k6556"] = {
            "source_receipts": {
                "short_sweep": str(llrice_sweep_path),
                "sustained_ab": str(llrice_k6556_ab_path),
            },
            "classification": "rejected_visual_neutral_exact_ll_rice_ks",
            "quality_impact": "none_exact_ll_entropy_parameter_only",
            "short_sweep_decision": llrice_sweep.get("decision"),
            "short_best": best_short,
            "sustained_decision": llrice_ab.get("decision"),
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": safe_float(deltas.get("total_ms")),
            "encode_delta_ms": safe_float(deltas.get("encode_ms")),
            "write_delta_ms": safe_float(deltas.get("write_ms")),
            "payload_delta_kib": safe_float(deltas.get("payload_kib")),
            "fps_delta": safe_float(deltas.get("fps")),
            "rejected": llrice_ab.get("decision") == "reject_k6556_no_sustained_win",
        }

    writev_index = read_json_optional(writev_index_path)
    if isinstance(writev_index, dict):
        baseline = writev_index.get("baseline") if isinstance(writev_index.get("baseline"), dict) else {}
        candidate = writev_index.get("candidate") if isinstance(writev_index.get("candidate"), dict) else {}
        total_delta = safe_float(writev_index.get("delta_total_ms"))
        write_delta = safe_float(writev_index.get("delta_write_ms"))
        out["writev_index"] = {
            "source_receipt": str(writev_index_path),
            "classification": writev_index.get("classification"),
            "quality_impact": writev_index.get("quality_impact"),
            "frames": writev_index.get("frames"),
            "order": writev_index.get("order"),
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": total_delta,
            "encode_delta_ms": safe_float(writev_index.get("delta_encode_ms")),
            "write_delta_ms": write_delta,
            "near_miss": bool(
                writev_index.get("classification") == "visual_neutral_near_miss_not_strict24"
                and total_delta is not None
                and total_delta < 0.0
                and write_delta is not None
                and write_delta < 0.0
                and candidate.get("strict_24_pass") is False
                and candidate.get("gvid_valid") is True
                and candidate.get("payload_kib_median") == baseline.get("payload_kib_median")
            ),
        }

    coalesce_index = read_json_optional(coalesce_index_path)
    if isinstance(coalesce_index, dict):
        primary = coalesce_index.get("primary") if isinstance(coalesce_index.get("primary"), dict) else {}
        secondary = coalesce_index.get("secondary") if isinstance(coalesce_index.get("secondary"), dict) else {}
        baseline = primary.get("baseline") if isinstance(primary.get("baseline"), dict) else {}
        candidate = primary.get("candidate") if isinstance(primary.get("candidate"), dict) else {}
        total_delta = safe_float(primary.get("total_delta_ms"))
        write_delta = safe_float(primary.get("write_delta_ms"))
        secondary_total_delta = safe_float(secondary.get("total_delta_ms"))
        out["coalesce_index"] = {
            "source_receipt": str(coalesce_index_path),
            "classification": coalesce_index.get("classification"),
            "quality_impact": coalesce_index.get("quality_impact"),
            "frames": coalesce_index.get("frames"),
            "primary_order": coalesce_index.get("primary_order"),
            "secondary_order": coalesce_index.get("secondary_order"),
            "baseline": baseline,
            "candidate": candidate,
            "total_delta_ms": total_delta,
            "encode_delta_ms": safe_float(primary.get("encode_delta_ms")),
            "write_delta_ms": write_delta,
            "fps_median_delta": safe_float(primary.get("fps_median_delta")),
            "secondary_total_delta_ms": secondary_total_delta,
            "secondary_fps_median_delta": safe_float(secondary.get("fps_median_delta")),
            "payload_unchanged": coalesce_index.get("payload_unchanged"),
            "all_gvid_valid": coalesce_index.get("all_gvid_valid"),
            "near_miss": bool(
                coalesce_index.get("classification") == "visual_neutral_near_miss_not_strict24"
                and coalesce_index.get("payload_unchanged") is True
                and coalesce_index.get("all_gvid_valid") is True
                and candidate.get("strict_24_pass") is False
                and total_delta is not None
                and total_delta < 0.0
                and secondary_total_delta is not None
                and secondary_total_delta < 0.0
                and candidate.get("payload_kib_median") == baseline.get("payload_kib_median")
            ),
        }

    coalesce_scout = read_json_optional(coalesce_scout_path)
    if isinstance(coalesce_scout, dict):
        rows = rows_by_case(coalesce_scout.get("rows"))
        baseline = rows.get("baseline") or {}
        variants = {
            name: row
            for name, row in rows.items()
            if name != "baseline" and isinstance(row, dict)
        }
        valid_variants = [
            row for row in variants.values()
            if row.get("gvid_valid") is True and row.get("storage_target_met") is True
        ]
        deltas = [
            safe_float(row.get("delta_total_vs_baseline_ms"))
            for row in variants.values()
            if safe_float(row.get("delta_total_vs_baseline_ms")) is not None
        ]
        best_variant = min(
            variants.values(),
            key=lambda row: safe_float(row.get("total_median_ms")) or float("inf"),
            default={},
        )
        out["coalesce_scout"] = {
            "source_receipt": str(coalesce_scout_path),
            "classification": "rejected_visual_neutral_coalesce_writev_scout",
            "quality_impact": "none_detected_payload_and_codec_settings_unchanged",
            "frames": coalesce_scout.get("frames"),
            "baseline": baseline,
            "variants": variants,
            "best_variant": best_variant,
            "all_variants_valid": len(valid_variants) == len(variants) and bool(variants),
            "all_variants_miss_strict24": all(row.get("fps_target_met") is False for row in variants.values()),
            "all_variants_regress_total": bool(deltas) and all(delta is not None and delta > 0.0 for delta in deltas),
            "rejected": bool(
                variants
                and len(valid_variants) == len(variants)
                and all(row.get("fps_target_met") is False for row in variants.values())
                and deltas
                and all(delta is not None and delta > 0.0 for delta in deltas)
            ),
        }

    partition_abab = read_json_optional(partition_abab_path)
    if isinstance(partition_abab, dict):
        cases = partition_abab.get("cases") if isinstance(partition_abab.get("cases"), dict) else {}
        analysis = partition_abab.get("analysis") if isinstance(partition_abab.get("analysis"), dict) else {}
        encode_cases = {
            name: partition_case_metrics(row)
            for name, row in cases.items()
            if isinstance(name, str) and isinstance(row, dict) and row.get("mode") == "encode_only"
        }
        direct_cases = {
            name: partition_case_metrics(row)
            for name, row in cases.items()
            if isinstance(name, str) and isinstance(row, dict) and row.get("mode") == "direct_gvid"
        }
        direct_loop_gap = safe_float(analysis.get("direct_loop_gap_ms"))
        direct_minus_encode = safe_float(analysis.get("direct_minus_encode_total_ms"))
        out["partition_abab"] = {
            "source_receipt": str(partition_abab_path),
            "schema": partition_abab.get("schema"),
            "classification": "diagnostic_visual_neutral_encode_write_partition",
            "quality_impact": "none_detected_no_codec_parameter_change",
            "frames_per_case": partition_abab.get("frames_per_case"),
            "profile": partition_abab.get("profile"),
            "case_order": partition_abab.get("case_order"),
            "encode_only_cases": encode_cases,
            "direct_gvid_cases": direct_cases,
            "analysis": analysis,
            "direct_loop_gap_ms": direct_loop_gap,
            "direct_minus_encode_total_ms": direct_minus_encode,
            "strict_24_pass": bool(direct_loop_gap is not None and direct_loop_gap <= 0.0),
            "diagnostic_only": True,
            "production_receipt": False,
            "interpretation": (
                "Short A/B/A/B partition probe narrows the remaining gap to encode/write "
                "ownership and run-to-run wall behavior. It is not a release receipt because "
                "it bypasses the Labs wrapper validation path."
            ),
        }

    return out


def build_summary(external_root: Path) -> dict[str, Any]:
    artifact_root = external_root / "artifacts"
    writer_path = artifact_root / WRITER_ISOLATION
    single_path = artifact_root / SINGLE_ISOLATION
    t236_boundary = summarize_t236_boundary(artifact_root)
    t236_clean_probe = summarize_t236_clean_probe(artifact_root)
    recent_t236_followup_probes = summarize_recent_followup_probes(artifact_root)
    writer = row_by_name(read_json(writer_path))
    single = row_by_name(read_json(single_path))

    cases = {
        "pingpong_devnull": summarize_row("pingpong_devnull", writer.get("pingpong_devnull", {})),
        "pingpong_ssd": summarize_row("pingpong_ssd", writer.get("pingpong_ssd", {})),
        "scatter_no_dbuf": summarize_row("scatter_no_dbuf", single.get("scatter_no_dbuf", {})),
        "scatter_dbuf": summarize_row("scatter_dbuf", single.get("scatter_dbuf", {})),
        "contiguous_dbuf": summarize_row("contiguous_dbuf", single.get("contiguous_dbuf", {})),
    }

    no_block = [
        row for key, row in cases.items()
        if key in {"pingpong_devnull", "scatter_no_dbuf", "scatter_dbuf", "contiguous_dbuf"}
        and row["total_median_ms"] is not None
    ]
    real_write = cases["pingpong_ssd"]
    no_block_best = min(no_block, key=lambda row: row["total_median_ms"]) if no_block else None
    devnull = cases["pingpong_devnull"]
    penalty = None
    if devnull["total_median_ms"] is not None and real_write["total_median_ms"] is not None:
        penalty = real_write["total_median_ms"] - devnull["total_median_ms"]

    blocker_class = "unknown"
    if (
        no_block_best
        and no_block_best["strict_24_pass"]
        and real_write["total_median_ms"] is not None
        and not real_write["strict_24_pass"]
        and penalty is not None
        and penalty >= 3.0
    ):
        blocker_class = "block_write_cache_contention"

    return {
        "schema": "mission1_write_contention_summary.v1",
        "artifact_root": str(artifact_root),
        "strict_24_frame_ms": STRICT_24_FRAME_MS,
        "source_receipts": {
            "writer_contention": str(writer_path),
            "single_pingpong": str(single_path),
        },
        "cases": cases,
        "best_no_block_case": no_block_best,
        "real_block_write_case": real_write,
        "block_write_penalty_ms": penalty,
        "blocker_class": blocker_class,
        "latest_t236_boundary": t236_boundary,
        "fresh_t236_clean_pi_probe": t236_clean_probe,
        "recent_t236_followup_probes": recent_t236_followup_probes,
        "production_direction": (
            "Focus on lower-contention buffer ownership, camera/storage handoff, or target write path; "
            "do not treat more threshold tuning as the primary strict-24 fix. The latest T236 isolation "
            "shows the remaining strict-24 miss is visual-neutral encode/write handoff margin, not an "
            "image-quality blocker."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external-root",
        type=Path,
        default=Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root())),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    summary = build_summary(args.external_root)
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
