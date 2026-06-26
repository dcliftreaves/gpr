#!/usr/bin/env python3
"""Summarize Mission 1 native-12MP quality/performance frontier evidence."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


QUALITY_MATRIX = "mission1_native12_threshold_quality_matrix_20260618/summary.json"
JANS_AUDIT_DIR = "mission1_jans_freq_audit_20260618"
JANS_STRIPE_SUMMARIES = (
    "mission1_jans_freq_audit_20260618/stripe_sweep/summary.json",
    "mission1_jans_freq_audit_20260618/stripe_refine/summary.json",
    "mission1_jans_freq_audit_20260618/stripe_fine/summary.json",
)
ENTROPY_SAFE_STRIPE_ROWS = 264
ENTROPY_SAFE_TIMING = "mission1_stripe264_timing_20260618/summary.json"
ENTROPY_SAFE_QUALITY = "mission1_stripe264_quality_20260618/summary.json"
FREQ_SATURATE_PROBE = "current_goal_jans_freq_saturate_probe_20260618/summary.json"
UINT16_COUNTER_LIMIT = 65535
REQUIRED_FRONTIER_CONFIGS = {
    "t236_ch2lh3": {
        "class": "quality_boundary",
        "receipt_glob": "mission1_hardened_fps_gate_lh3_k6656_GP017602_120f_24fps_20260618/labs_target_bench.json",
        "note": "Current high-quality storage-safe boundary; strict Pi 24 fps still fails.",
    },
    "t238_ch2lh3": {
        "class": "quality_boundary_probe",
        "receipt_glob": "mission1_ch2lh3_t238_GP017602_120f_24fps_20260618/labs_target_bench.json",
        "quality_glob": "mission1_t238_quality_local_20260618/summary.json",
        "note": "Quality/storage-valid near-miss, but slower than T236 on the Pi timing receipt.",
    },
    "t244_lh2_hl4_hh4": {
        "class": "speed_tier_quality_fail",
        "receipt_glob": "mission1_t244_GP017602_120f_24fps_20260618/labs_target_bench.json",
        "quality_glob": "mission1_native12_t244_quality_dashboard_20260618/summary.json",
        "note": "Strict-24 median speed/storage tier, but all Mission 1 quality rows fail the PSNR14 floor.",
    },
    "t356_ch2lh3": {
        "class": "speed_candidate_quality_fail",
        "receipt_glob": "mission1_native12_t356_ch2lh3_GP017602_120f_24fps_20260618/labs_target_bench.json",
        "note": "Near 24 fps median on GP017602, but GP017603 quality collapses.",
    },
    "t468_ch2lh4": {
        "class": "speed_tier_quality_fail",
        "receipt_glob": "mission1_native12_t468_ch2lh4_GP017602_120f_24fps_20260618/labs_target_bench.json",
        "note": "Strict-24 speed tier only; below production quality floor.",
    },
}
LEGACY_Q0_RECEIPTS = {
    "GP017601": "mission1_native12_q0_l1_labs_1440f_20260616_GP017601/labs_target_bench.json",
    "GP017602": "mission1_native12_q0_l1_labs_1440f_20260616_GP017602/labs_target_bench.json",
    "GP017603": "mission1_native12_q0_l1_labs_1440f_20260616_GP017603/labs_target_bench.json",
}


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def receipt_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload is None:
        return {"path": str(path), "present": False}
    timing = payload.get("timing") or {}
    verdict = payload.get("verdict") or {}
    storage = payload.get("storage") or {}
    return {
        "path": str(path),
        "present": True,
        "frames": timing.get("n"),
        "fps_median": safe_float(timing.get("fps_median")),
        "wall_fps": safe_float(timing.get("actual_wall_fps")),
        "median_ms": safe_float(timing.get("median_ms") or timing.get("frame_time_ms_median")),
        "p95_ms": safe_float(timing.get("p95_ms")),
        "fps_target_met": verdict.get("fps_target_met"),
        "fps_median_target_met": verdict.get("fps_median_target_met"),
        "fps_wall_target_met": verdict.get("fps_wall_target_met"),
        "no_drops": verdict.get("no_drops"),
        "gvid_valid": verdict.get("gvid_valid"),
        "interruption_recovery_proven": verdict.get("interruption_recovery_proven"),
        "storage_target_met": verdict.get("storage_target_met"),
        "target_evidence": verdict.get("target_evidence"),
        "total_frame_bytes": storage.get("total_frame_bytes"),
        "gvid_bytes": storage.get("gvid_bytes"),
        "write_MBps_wall": safe_float(storage.get("write_MBps_wall")),
    }


def metric_max(stats: dict[str, Any], metric: str) -> float | None:
    return safe_float((stats.get(metric) or {}).get("max"))


def jans_profile_stats(payload: dict[str, Any]) -> dict[str, Any] | None:
    profile = payload.get("jans_inline_profile") or {}
    labels = profile.get("by_label") or {}
    stats = labels.get("unlabeled")
    if not isinstance(stats, dict) and labels:
        first = next(iter(labels.values()))
        if isinstance(first, dict):
            stats = first
    if not isinstance(stats, dict):
        return None
    return {
        "max_symbol_freq": metric_max(stats, "max_symbol_freq"),
        "overflow_symbols_max": metric_max(stats, "overflow_symbols"),
        "stripe_rows": metric_max(stats, "stripe_rows"),
    }


def current_jans_audit_summary(artifact_root: Path) -> dict[str, Any]:
    audit_dir = artifact_root / JANS_AUDIT_DIR
    per_image: dict[str, dict[str, Any]] = {}
    max_symbol_freq = 0.0
    overflow_symbols_max = 0.0
    stripe_rows_values: set[int] = set()
    for receipt in sorted(audit_dir.glob("GP*/labs_target_bench.json")):
        payload = read_json(receipt)
        if payload is None:
            continue
        stats = jans_profile_stats(payload)
        if stats is None:
            continue
        stem = receipt.parent.name
        per_image[stem] = {"path": str(receipt), **stats}
        max_symbol_freq = max(max_symbol_freq, safe_float(stats.get("max_symbol_freq")) or 0.0)
        overflow_symbols_max = max(overflow_symbols_max, safe_float(stats.get("overflow_symbols_max")) or 0.0)
        stripe_rows = safe_int(stats.get("stripe_rows"))
        if stripe_rows is not None:
            stripe_rows_values.add(stripe_rows)

    present = bool(per_image)
    stripe_rows = sorted(stripe_rows_values)
    is_safe = present and overflow_symbols_max <= 0.0 and max_symbol_freq <= UINT16_COUNTER_LIMIT
    return {
        "path": str(audit_dir),
        "present": present,
        "stripe_rows": stripe_rows[0] if len(stripe_rows) == 1 else stripe_rows,
        "max_symbol_freq": max_symbol_freq if present else None,
        "overflow_symbols_max": overflow_symbols_max if present else None,
        "counter_limit": UINT16_COUNTER_LIMIT,
        "entropy_counter_safe": is_safe,
        "per_image": per_image,
    }


def stripe_entry_summary(path: Path, rows: int, payload: dict[str, Any]) -> dict[str, Any]:
    max_symbol_freq = safe_float(payload.get("max_symbol_freq"))
    overflow_symbols_max = safe_float(payload.get("overflow_symbols_max"))
    safe = (
        max_symbol_freq is not None
        and overflow_symbols_max is not None
        and max_symbol_freq <= UINT16_COUNTER_LIMIT
        and overflow_symbols_max <= 0.0
    )
    return {
        "rows": rows,
        "path": str(path),
        "max_symbol_freq": max_symbol_freq,
        "overflow_symbols_max": overflow_symbols_max,
        "counter_limit": UINT16_COUNTER_LIMIT,
        "entropy_counter_safe": safe,
        "per_image": payload.get("per_image") if isinstance(payload.get("per_image"), dict) else {},
    }


def stripe_sweep_summary(artifact_root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    paths = []
    for rel in JANS_STRIPE_SUMMARIES:
        path = artifact_root / rel
        paths.append(str(path))
        payload = read_json(path)
        if payload is None:
            continue
        for key, row in payload.items():
            rows = safe_int(key)
            if rows is None or not isinstance(row, dict):
                continue
            entries.append(stripe_entry_summary(path, rows, row))
    entries.sort(key=lambda row: row["rows"])
    safe_entries = [row for row in entries if row.get("entropy_counter_safe") is True]
    unsafe_entries = [row for row in entries if row.get("entropy_counter_safe") is False]
    largest_safe = max(safe_entries, key=lambda row: row["rows"]) if safe_entries else None
    first_overflow = None
    if largest_safe:
        larger_unsafe = [row for row in unsafe_entries if row["rows"] > largest_safe["rows"]]
        if larger_unsafe:
            first_overflow = min(larger_unsafe, key=lambda row: row["rows"])
    elif unsafe_entries:
        first_overflow = min(unsafe_entries, key=lambda row: row["rows"])
    return {
        "paths": paths,
        "present": bool(entries),
        "entries": entries,
        "largest_no_overflow": largest_safe,
        "first_overflow_above_safe": first_overflow,
    }


def safe_stripe_quality_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload is None:
        return {"path": str(path), "present": False}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    required = [
        safe_float(row.get("required_MBps_at_24fps"))
        for row in rows
        if isinstance(row, dict) and safe_float(row.get("required_MBps_at_24fps")) is not None
    ]
    psnr = [
        safe_float(row.get("PSNR14_dB"))
        for row in rows
        if isinstance(row, dict) and safe_float(row.get("PSNR14_dB")) is not None
    ]
    return {
        "path": str(path),
        "present": True,
        "schema": payload.get("schema"),
        "profile_id": payload.get("profile_id"),
        "profile_env": payload.get("profile_env") or {},
        "all_pass": payload.get("all_pass"),
        "passes_20fps_storage_budget_all": payload.get("passes_20fps_storage_budget_all"),
        "max_required_MBps_at_24fps": max(required) if required else None,
        "min_psnr14": min(psnr) if psnr else None,
        "rows": rows,
    }


def safe_stripe_timing_summary(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if payload is None:
        return {"path": str(path), "present": False}
    rows = {str(stem): row for stem, row in payload.items() if isinstance(row, dict)}
    fps_values = [
        safe_float(row.get("fps_median"))
        for row in rows.values()
        if safe_float(row.get("fps_median")) is not None
    ]
    wall_values = [
        safe_float(row.get("wall_fps"))
        for row in rows.values()
        if safe_float(row.get("wall_fps")) is not None
    ]
    return {
        "path": str(path),
        "present": True,
        "rows": rows,
        "min_fps_median": min(fps_values) if fps_values else None,
        "min_wall_fps": min(wall_values) if wall_values else None,
        "all_fps_target_met": all(row.get("fps_target_met") is True for row in rows.values()),
        "all_storage_target_met": all(row.get("storage_target_met") is True for row in rows.values()),
    }


def entropy_safety_summary(artifact_root: Path) -> dict[str, Any]:
    current = current_jans_audit_summary(artifact_root)
    sweep = stripe_sweep_summary(artifact_root)
    quality = safe_stripe_quality_summary(artifact_root / ENTROPY_SAFE_QUALITY)
    timing = safe_stripe_timing_summary(artifact_root / ENTROPY_SAFE_TIMING)
    freq_saturate = read_json(artifact_root / FREQ_SATURATE_PROBE)
    largest = sweep.get("largest_no_overflow") or {}
    largest_rows = safe_int(largest.get("rows"))
    stripe_env = (quality.get("profile_env") or {}).get("FUSED_STRIPE_ROWS")
    quality_matches = str(stripe_env) == str(ENTROPY_SAFE_STRIPE_ROWS)
    timing_safe_but_slow = (
        timing.get("present") is True
        and timing.get("all_storage_target_met") is True
        and timing.get("all_fps_target_met") is not True
    )
    diagnostic_only = False
    production_status = "missing_entropy_evidence"
    if current.get("present") and sweep.get("present"):
        if current.get("entropy_counter_safe") is False and largest_rows == ENTROPY_SAFE_STRIPE_ROWS:
            diagnostic_only = True
            production_status = "raw_count_over_uint16_diagnostic"
        elif largest_rows == ENTROPY_SAFE_STRIPE_ROWS and timing_safe_but_slow:
            production_status = "entropy_safe_but_fps_fail"
        elif timing.get("all_fps_target_met") is True and quality.get("all_pass") is True:
            production_status = "entropy_safe_production_candidate"
    return {
        "schema": "mission1_native12_entropy_safety.v1",
        "counter_limit": UINT16_COUNTER_LIMIT,
        "current_profile": current,
        "stripe_sweep": sweep,
        "safe_stripe": {
            "rows": ENTROPY_SAFE_STRIPE_ROWS,
            "quality": quality,
            "timing": timing,
            "quality_profile_env_matches": quality_matches,
        },
        "frequency_saturation_candidate": freq_saturate,
        "production_status": production_status,
        "practical_blocker": not diagnostic_only and production_status != "entropy_safe_production_candidate",
        "decision": (
            "The 384-row profile has raw per-symbol counts above the uint16 diagnostic limit, "
            "but this is not a visual-quality blocker by itself when the stream validates, "
            "round-trips, and the quality receipts pass. Keep the 264-row no-overflow sweep as "
            "diagnostic context; promote or block production on valid media, visual/raw quality, "
            "storage fit, and target timing receipts."
        ),
    }


def quality_rows(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in matrix.get("summary") or []:
        if not isinstance(row, dict):
            continue
        config = str(row.get("config"))
        out[config] = {
            "config": config,
            "min_psnr14": safe_float(row.get("min_psnr14")),
            "mean_psnr14": safe_float(row.get("mean_psnr14")),
            "mean_MiB": safe_float(row.get("mean_MiB")),
            "max_required_MBps_at_24fps": safe_float(row.get("max_required_MBps_at_24fps")),
            "quality_floor_pass": bool(row.get("quality_floor_pass")),
            "storage_24fps_pass": bool(row.get("storage_24fps_pass")),
            "rows": row.get("rows") or [],
        }
    return out


def quality_from_probe(path: Path) -> dict[str, Any] | None:
    payload = read_json(path)
    if payload is None:
        return None
    rows_in = payload.get("rows")
    if not isinstance(rows_in, list):
        return None
    rows = []
    psnrs: list[float] = []
    byte_values: list[int] = []
    for row in rows_in:
        if not isinstance(row, dict):
            continue
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        psnr = safe_float(row.get("psnr14"))
        if psnr is None:
            psnr = safe_float(metrics.get("psnr14"))
        encoded_bytes = row.get("bytes")
        if encoded_bytes is None:
            encoded_bytes = row.get("encoded_bytes")
        try:
            byte_count = int(encoded_bytes)
        except (TypeError, ValueError):
            byte_count = 0
        if psnr is not None:
            psnrs.append(psnr)
        if byte_count > 0:
            byte_values.append(byte_count)
        rows.append({
            "image": row.get("image") or row.get("stem"),
            "bytes": byte_count,
            "psnr": psnr,
        })
    if not psnrs or not byte_values:
        return None
    max_required = max(byte_values) * 24.0 / 1_000_000.0
    quality_pass = bool(payload.get("all_pass_75db") or payload.get("all_pass")) and min(psnrs) >= 75.0
    return {
        "config": str(payload.get("profile") or payload.get("profile_id") or path.parent.name),
        "path": str(path),
        "min_psnr14": min(psnrs),
        "mean_psnr14": sum(psnrs) / len(psnrs),
        "mean_MiB": (sum(byte_values) / len(byte_values)) / (1024.0 * 1024.0),
        "max_required_MBps_at_24fps": max_required,
        "quality_floor_pass": quality_pass,
        "storage_24fps_pass": max_required <= 135.0,
        "rows": rows,
    }


def production_status(quality: dict[str, Any] | None, receipt: dict[str, Any]) -> str:
    if not quality:
        return "missing_quality"
    if not quality.get("quality_floor_pass"):
        return "quality_fail"
    if not quality.get("storage_24fps_pass"):
        return "storage_fail"
    if not receipt.get("present"):
        return "missing_perf"
    if receipt.get("fps_target_met") is True:
        return "production_candidate"
    return "fps_fail"


def cnn_recovery_policy(quality: dict[str, Any] | None, status: str) -> dict[str, Any]:
    """Classify whether this codec output is a valid SR/CNN input.

    CNN/SR is allowed to improve or upscale a valid decoded Bayer path. It is
    not allowed to waive a codec-quality failure, because that would make
    symbol/range/phase damage look like a learned-image problem.
    """
    quality_pass = bool(quality and quality.get("quality_floor_pass") is True)
    storage_pass = bool(quality and quality.get("storage_24fps_pass") is True)
    if quality_pass and storage_pass:
        return {
            "decoded_bayer_status": "valid_quality_storage_boundary",
            "cnn_recovery_allowed": True,
            "policy": "allowed_for_sr_or_visual_recovery_after_valid_decode",
        }
    if quality and quality.get("quality_floor_pass") is False:
        return {
            "decoded_bayer_status": "codec_quality_failure",
            "cnn_recovery_allowed": False,
            "policy": "blocked_until_codec_quality_passes_do_not_hide_with_cnn",
        }
    return {
        "decoded_bayer_status": status,
        "cnn_recovery_allowed": False,
        "policy": "blocked_until_quality_evidence_exists",
    }


def build_summary(external_root: Path) -> dict[str, Any]:
    artifact_root = external_root / "artifacts"
    matrix_path = artifact_root / QUALITY_MATRIX
    matrix = read_json(matrix_path)
    if matrix is None:
        return {
            "schema": "mission1_native12_frontier_summary.v2",
            "artifact_root": str(artifact_root),
            "quality_matrix": {"path": str(matrix_path), "present": False},
            "entropy_safety": entropy_safety_summary(artifact_root),
            "frontier": [],
            "legacy_fast_q0_l1": [],
        }
    by_config = quality_rows(matrix)
    frontier = []
    for config, meta in REQUIRED_FRONTIER_CONFIGS.items():
        quality_glob = meta.get("quality_glob")
        if quality_glob:
            quality = quality_from_probe(artifact_root / quality_glob)
        else:
            quality = by_config.get(config)
        receipt = receipt_summary(artifact_root / meta["receipt_glob"])
        status = production_status(quality, receipt)
        frontier.append({
            "config": config,
            "class": meta["class"],
            "note": meta["note"],
            "quality": quality,
            "performance": receipt,
            "production_status": status,
            "cnn_recovery_policy": cnn_recovery_policy(quality, status),
        })
    frontier.sort(key=lambda row: (
        row["production_status"] != "production_candidate",
        -(row["performance"].get("fps_median") or 0.0),
        row["config"],
    ))

    legacy = []
    for stem, rel in LEGACY_Q0_RECEIPTS.items():
        receipt = receipt_summary(artifact_root / rel)
        legacy.append({
            "stem": stem,
            "performance": receipt,
            "production_status": "invalid_legacy_no_quality_boundary_or_current_provenance",
        })

    return {
        "schema": "mission1_native12_frontier_summary.v2",
        "artifact_root": str(artifact_root),
        "quality_matrix": {
            "path": str(matrix_path),
            "present": True,
            "quality_floor_psnr14": matrix.get("quality_floor_psnr14"),
            "storage_budget_MBps_at_24fps": matrix.get("storage_budget_MBps_at_24fps"),
        },
        "entropy_safety": entropy_safety_summary(artifact_root),
        "frontier": frontier,
        "legacy_fast_q0_l1": legacy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external-root",
        type=Path,
        default=Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root())),
        help="Root containing artifacts/ (default: GPR_EXTERNAL_ROOT or /Volumes/OWC_8TB/gpr_work)",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
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
