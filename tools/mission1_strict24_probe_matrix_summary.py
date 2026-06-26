#!/usr/bin/env python3
"""Summarize Mission 1 strict-24 probe-matrix receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "mission1_strict24_probe_matrix_summary.v1"
TARGET_FPS = 24.0
TARGET_FRAME_MS = 1000.0 / TARGET_FPS
PROBE_ROOT_REL = "current_goal_strict24_probe_matrix_20260619"
CURRENT_REPEAT_REL = f"{PROBE_ROOT_REL}/current_source_sustained_repeat_240f/labs_target_bench.json"
HOTROW_REL = f"{PROBE_ROOT_REL}/encoder_hotrow_profile_30f/labs_target_bench.json"
LEGACY_POLICY_REL = f"{PROBE_ROOT_REL}/legacy_policy_ab_240f/labs_target_bench.json"
PRODUCTION_LABELED_HOTROW_REL = f"{PROBE_ROOT_REL}/production_profile_labeled_hotrow_30f/labs_target_bench.json"
PRODUCTION_PROFILE_RELS = [
    LEGACY_POLICY_REL,
    f"{PROBE_ROOT_REL}/production_profile_240f/labs_target_bench.json",
    f"{PROBE_ROOT_REL}/production_profile_repeat2_240f/labs_target_bench.json",
]
PREVIOUS_CURRENT_REL = "current_goal_provenance_t236_GP017602_240f_20260618/labs_target_bench.json"


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def phase(receipt: dict[str, Any], name: str, field: str = "median_ms") -> float | None:
    phases = ((receipt.get("bench_phase_timing") or {}).get("phase_ms") or {})
    row = phases.get(name) if isinstance(phases, dict) else None
    if not isinstance(row, dict):
        return None
    return safe_float(row.get(field))


def metrics(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    timing = receipt.get("timing") if isinstance(receipt.get("timing"), dict) else {}
    target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
    verdict = receipt.get("verdict") if isinstance(receipt.get("verdict"), dict) else {}
    storage = ((receipt.get("storage") or {}).get("target") or {})
    writer = receipt.get("writer_handoff") if isinstance(receipt.get("writer_handoff"), dict) else {}
    build = ((receipt.get("bench") or {}).get("build") or {})
    source = receipt.get("source_provenance") if isinstance(receipt.get("source_provenance"), dict) else {}
    total = safe_float(timing.get("median_ms"))
    wall_fps = safe_float(target.get("actual_wall_fps"))
    return {
        "receipt": str(path),
        "receipt_sha256": sha256_file(path),
        "frames": timing.get("n"),
        "total_median_ms": total,
        "fps_median": safe_float(timing.get("fps_median")),
        "wall_fps": wall_fps,
        "loop_gap_ms": safe_float(writer.get("loop_target_gap_ms")) if writer else (total - TARGET_FRAME_MS if total is not None else None),
        "wall_gap_ms": safe_float(writer.get("wall_target_gap_ms")),
        "encode_median_ms": phase(receipt, "encode"),
        "write_median_ms": phase(receipt, "write"),
        "payload_kib_median": phase(receipt, "payload_kib", "median"),
        "storage_target_met": verdict.get("storage_target_met"),
        "gvid_valid": verdict.get("gvid_valid"),
        "no_drops": verdict.get("no_drops"),
        "interruption_recovery_proven": verdict.get("interruption_recovery_proven"),
        "fps_target_met": verdict.get("fps_target_met"),
        "storage_budget_bytes_per_frame": safe_float(storage.get("budget_bytes_per_frame")),
        "storage_bytes_per_frame": safe_float(storage.get("bytes_per_frame")),
        "binary_sha256": build.get("binary_sha256"),
        "source_provenance_sha256": source.get("sha256"),
    }


def delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("total_median_ms", "encode_median_ms", "write_median_ms", "payload_kib_median", "fps_median", "wall_fps"):
        c = safe_float(candidate.get(key))
        b = safe_float(baseline.get(key))
        out[f"{key}_delta"] = c - b if c is not None and b is not None else None
    return out


def passes_strict24(row: dict[str, Any]) -> bool:
    wall = safe_float(row.get("wall_fps"))
    return bool(
        row.get("fps_target_met")
        and row.get("storage_target_met")
        and row.get("gvid_valid")
        and wall is not None
        and wall >= TARGET_FPS
    )


def summarize_repeats(repeats: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in repeats if isinstance(row, dict)]
    best = min(valid, key=lambda row: safe_float(row.get("total_median_ms")) or float("inf")) if valid else None
    latest = valid[-1] if valid else None
    latest_total = safe_float(latest.get("total_median_ms")) if latest else None
    latest_wall = safe_float(latest.get("wall_fps")) if latest else None
    best_total = safe_float(best.get("total_median_ms")) if best else None
    best_wall = safe_float(best.get("wall_fps")) if best else None
    return {
        "count": len(valid),
        "best": best,
        "latest": latest,
        "strict24_any_closed": any(passes_strict24(row) for row in valid),
        "best_total_gap_ms": best_total - TARGET_FRAME_MS if best_total is not None else None,
        "latest_total_gap_ms": latest_total - TARGET_FRAME_MS if latest_total is not None else None,
        "best_wall_gap_ms": (1000.0 / best_wall) - TARGET_FRAME_MS if best_wall is not None and best_wall > 0 else None,
        "latest_wall_gap_ms": (1000.0 / latest_wall) - TARGET_FRAME_MS if latest_wall is not None and latest_wall > 0 else None,
    }


def summarize_hotrow(receipt: dict[str, Any]) -> dict[str, Any]:
    fused = receipt.get("fused_timing") if isinstance(receipt.get("fused_timing"), dict) else {}
    channels = fused.get("channel_component_by_channel_ms") if isinstance(fused.get("channel_component_by_channel_ms"), dict) else {}
    rows: list[dict[str, Any]] = []
    for channel, components in channels.items():
        if not isinstance(components, dict):
            continue
        total = components.get("total") if isinstance(components.get("total"), dict) else {}
        tokenize = components.get("tokenize") if isinstance(components.get("tokenize"), dict) else {}
        unpack = components.get("unpack") if isinstance(components.get("unpack"), dict) else {}
        rows.append({
            "channel": str(channel),
            "total_median_ms": safe_float(total.get("median_ms")),
            "tokenize_median_ms": safe_float(tokenize.get("median_ms")),
            "unpack_median_ms": safe_float(unpack.get("median_ms")),
        })
    rows.sort(key=lambda row: safe_float(row.get("tokenize_median_ms")) or -1.0, reverse=True)
    jans = receipt.get("jans_inline_profile") if isinstance(receipt.get("jans_inline_profile"), dict) else {}
    by_label = jans.get("by_label") if isinstance(jans.get("by_label"), dict) else {}
    profile_labels: list[dict[str, Any]] = []
    for label, stats in by_label.items():
        if not isinstance(stats, dict):
            continue
        overflow = stats.get("overflow_symbols") if isinstance(stats.get("overflow_symbols"), dict) else {}
        max_symbol = stats.get("max_symbol_freq") if isinstance(stats.get("max_symbol_freq"), dict) else {}
        profile_labels.append({
            "label": str(label),
            "overflow_symbols_max": safe_float(overflow.get("max")),
            "max_symbol_freq_max": safe_float(max_symbol.get("max")),
        })
    profile_labels.sort(
        key=lambda row: (
            safe_float(row.get("overflow_symbols_max")) or 0.0,
            safe_float(row.get("max_symbol_freq_max")) or 0.0,
        ),
        reverse=True,
    )
    overflow_max = max((safe_float(row.get("overflow_symbols_max")) or 0.0 for row in profile_labels), default=None)
    max_symbol_freq_max = max((safe_float(row.get("max_symbol_freq_max")) or 0.0 for row in profile_labels), default=None)
    return {
        "instrumented": bool(fused.get("available") and jans.get("available")),
        "fused_timing_lines": fused.get("timing_line_count"),
        "jans_profile_lines": jans.get("profile_line_count"),
        "dominant_component": "tokenize",
        "channel_rank_by_tokenize": rows,
        "jans_label_rank_by_overflow": profile_labels,
        "overflow_symbols_max": overflow_max,
        "max_symbol_freq_max": max_symbol_freq_max,
    }


def build_summary(external_root: Path) -> dict[str, Any]:
    artifact_root = external_root / "artifacts"
    current_path = artifact_root / CURRENT_REPEAT_REL
    hotrow_path = artifact_root / HOTROW_REL
    production_labeled_hotrow_path = artifact_root / PRODUCTION_LABELED_HOTROW_REL
    previous_path = artifact_root / PREVIOUS_CURRENT_REL
    current = read_json(current_path)
    hotrow = read_json(hotrow_path)
    production_labeled_hotrow = read_json_optional(production_labeled_hotrow_path)
    previous = read_json_optional(previous_path)
    current_metrics = metrics(current_path, current)
    hotrow_metrics = metrics(hotrow_path, hotrow)
    production_labeled_hotrow_metrics = (
        metrics(production_labeled_hotrow_path, production_labeled_hotrow)
        if isinstance(production_labeled_hotrow, dict)
        else None
    )
    production_repeats: list[dict[str, Any]] = []
    for rel in PRODUCTION_PROFILE_RELS:
        path = artifact_root / rel
        payload = read_json_optional(path)
        if isinstance(payload, dict):
            production_repeats.append(metrics(path, payload))
    production_summary = summarize_repeats(production_repeats)
    production_best = production_summary.get("best") if isinstance(production_summary.get("best"), dict) else None
    production_latest = production_summary.get("latest") if isinstance(production_summary.get("latest"), dict) else None
    previous_metrics = metrics(previous_path, previous) if isinstance(previous, dict) else None
    current_vs_previous = delta(current_metrics, previous_metrics) if previous_metrics else None
    production_best_vs_current = delta(production_best, current_metrics) if production_best else None
    production_latest_vs_current = delta(production_latest, current_metrics) if production_latest else None
    hotrow_summary = summarize_hotrow(hotrow)
    production_labeled_hotrow_summary = (
        summarize_hotrow(production_labeled_hotrow)
        if isinstance(production_labeled_hotrow, dict)
        else None
    )
    strict24_closed = bool(passes_strict24(current_metrics) or production_summary.get("strict24_any_closed"))
    latest_gap = safe_float(production_summary.get("latest_total_gap_ms"))
    latest_wall_gap = safe_float(production_summary.get("latest_wall_gap_ms"))
    gap_text = (
        f"~{latest_gap:.1f}ms median / ~{latest_wall_gap:.1f}ms wall"
        if latest_gap is not None and latest_wall_gap is not None
        else "remaining median/wall"
    )
    return {
        "schema": SCHEMA,
        "target_fps": TARGET_FPS,
        "target_frame_ms": TARGET_FRAME_MS,
        "strict24_closed": strict24_closed,
        "decision": "strict24_still_open_current_source_regressed" if not strict24_closed else "strict24_probe_closed",
        "probe_root": str(artifact_root / PROBE_ROOT_REL),
        "current_source_repeat": current_metrics,
        "previous_current_source": previous_metrics,
        "current_vs_previous": current_vs_previous,
        "production_profile_repeats": production_repeats,
        "production_profile_summary": production_summary,
        "production_profile_best_repeat": production_best,
        "production_profile_latest_repeat": production_latest,
        "production_profile_best_vs_current": production_best_vs_current,
        "production_profile_latest_vs_current": production_latest_vs_current,
        "legacy_policy_repeat": production_best,
        "legacy_policy_vs_current": production_best_vs_current,
        "hotrow_profile": hotrow_metrics,
        "hotrow_diagnostics": hotrow_summary,
        "production_profile_labeled_hotrow": production_labeled_hotrow_metrics,
        "production_profile_labeled_hotrow_diagnostics": production_labeled_hotrow_summary,
        "next_target": (
            f"production T233 profile still needs {gap_text} reduction; optimize tokenization hot path on channels 0 and 3"
            if production_latest
            else "tokenization hot path on channels 0 and 3, then rerun current-source sustained repeat"
            if hotrow_summary.get("instrumented")
            else "rebuild instrumentation with JANS_INLINE_PROFILE_RUNTIME and FUSED_TIMING_DETAIL"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=default_external_root())
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    summary = build_summary(args.external_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "decision": summary["decision"],
        "current_fps": summary["current_source_repeat"].get("fps_median"),
        "current_wall_fps": summary["current_source_repeat"].get("wall_fps"),
        "next_target": summary["next_target"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
