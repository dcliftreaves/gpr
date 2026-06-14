#!/usr/bin/env python3
"""Validate the compact release evidence manifest.

This check keeps high-level production claims tied to concrete registry entries,
committed quality-gate runs, external receipt references, and tracked docs/tools.
It intentionally does not require heavyweight external artifacts in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/release_evidence_manifest.json"
REGISTRY = ROOT / "pipelines/registry.json"
RUNS_DIR = ROOT / "tests/quality_gates/runs"

EXPECTED_SCHEMA = "gpr_release_evidence_manifest.v1"
PRODUCTION_STATUSES = {
    "production-pass",
    "production-pass-external-receipt",
    "production-supported",
}
ALLOWED_STATUSES = PRODUCTION_STATUSES | {"experimental"}
ALLOWED_RAW_CLASSIFICATIONS = {
    "live-capable",
    "preview-capable",
    "offline-only",
}
REQUIRED_OUTPUT_IDS = {
    "still_smallest",
    "still_primary",
    "still_archival",
    "video_freeze_primary",
    "upresable_editable_raw",
    "preview_offline_review_q8_threeway",
    "preview_live_codec_only",
    "preview_live_2k_l2hh_edge_safe",
    "gvid_container",
    "mov_wrapper",
    "prores_review_outputs",
    "editable_dng_gpr_outputs",
}
REQUIRED_RAW_IDS = {
    "2k_raw_0p5x_fast",
    "2k_raw_0p5x_l2hh",
    "4k_raw_1x",
    "8k_raw_2x",
}
REQUIRED_EXTERNAL_RECEIPT_IDS = {
    "gvid_container",
    "mov_wrapper",
    "prores_review_outputs",
    "editable_dng_gpr_outputs",
}
REQUIRED_PLATFORM_PERFORMANCE_IDS = {
    "pi5_mission1_halfres_capture",
    "pi5_2k_fast_decode",
    "pi5_2k_l2hh_decode",
    "pi5_4k_decode_blocked",
    "mac_m5_preview_offline_render",
    "mac_m5_4k_raw_decode",
    "local_8k_raw_offline",
    "pi5_upresable_encode_loop",
    "pi5_usb_transfer",
    "mac_m5_upres_offline_stage",
    "gvid_mov_pack_stage",
    "mac_m5_upres_and_gvid_pack",
    "capability_memory_matrix",
}
REQUIRED_DASHBOARD_IDS = {
    "preview_offline_review_q8_threeway",
    "preview_candidate_evidence_rank",
    "preview_failure_mode_audit",
    "preview_source_ref_policy_audit",
    "raw_2k_fast_visual_proxy",
    "raw_2k_l2hh_visual_proxy",
    "raw_2k_l2hh_edge_safe_visual_proxy",
    "raw_4k_visual_proxy",
    "preview_review_media",
    "gvid_metadata_dispatch",
    "noise_signal_audit",
}
ALLOWED_PLATFORM_STATUSES = {
    "meets-target",
    "measured-offline",
    "measured-stage",
    "blocked",
}
ALLOWED_DASHBOARD_STATUSES = {
    "current",
    "diagnostic",
    "experimental-blocker",
}
ALLOWED_BLOCKERS = {
    "quality_gate_failure",
    "model_capacity",
    "source_target_mismatch",
    "codec_detail_aliasing",
    "memory_limit",
    "fps_throughput_limit",
    "missing_data",
    "ci_build_issue",
}


def tracked_paths() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def run_for_hash(run_hash: str) -> dict[str, Any] | None:
    path = RUNS_DIR / run_hash / "run.json"
    if not path.exists():
        return None
    try:
        return load_json(path)
    except Exception:
        return None


def require_tracked_refs(
    entry_id: str,
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    for key in ("docs", "tools"):
        refs = entry.get(key, [])
        if not isinstance(refs, list):
            failures.append(f"{entry_id}: {key} must be a list")
            continue
        for ref in refs:
            if not isinstance(ref, str):
                failures.append(f"{entry_id}: {key} entry must be a string")
                continue
            path = ROOT / ref
            if not path.exists():
                failures.append(f"{entry_id}: referenced {key[:-1]} does not exist: {ref}")
            elif ref not in tracked and not any(t.startswith(ref.rstrip('/') + '/') for t in tracked):
                failures.append(f"{entry_id}: referenced {key[:-1]} is not tracked: {ref}")


def require_artifact_ref(entry_id: str, key: str, ref: str, failures: list[str]) -> None:
    if not ref.startswith("artifacts/"):
        failures.append(f"{entry_id}: {key} must be under artifacts/: {ref}")
        return
    path = Path(ref)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        failures.append(f"{entry_id}: malformed {key} artifact path: {ref}")
    if len(path.parts) < 2:
        failures.append(f"{entry_id}: {key} artifact path must name a receipt: {ref}")


def require_external_receipts(entry_id: str, entry: dict[str, Any], failures: list[str]) -> None:
    receipts = entry.get("external_receipts")
    if not isinstance(receipts, list) or not receipts:
        failures.append(f"{entry_id}: external_receipts must be a non-empty list")
        return
    for receipt in receipts:
        if not isinstance(receipt, str):
            failures.append(f"{entry_id}: external_receipts entries must be strings")
            continue
        require_artifact_ref(entry_id, "external receipt", receipt, failures)


def require_receipt_refs(
    entry_id: str,
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    receipts = entry.get("receipts")
    if not isinstance(receipts, list) or not receipts:
        failures.append(f"{entry_id}: receipts must be a non-empty list")
        return
    for receipt in receipts:
        if not isinstance(receipt, str):
            failures.append(f"{entry_id}: receipts entries must be strings")
            continue
        if receipt.startswith("artifacts/"):
            require_artifact_ref(entry_id, "receipt", receipt, failures)
            continue
        path = ROOT / receipt
        if not path.exists():
            failures.append(f"{entry_id}: referenced receipt does not exist: {receipt}")
        elif receipt not in tracked:
            failures.append(f"{entry_id}: referenced receipt is not tracked: {receipt}")


def require_platform_performance_contract(
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    entry_id = str(entry.get("id", ""))
    status = entry.get("status")
    if status not in ALLOWED_PLATFORM_STATUSES:
        failures.append(f"{entry_id}: invalid platform performance status {status!r}")

    if not isinstance(entry.get("platform"), str) or not entry.get("platform"):
        failures.append(f"{entry_id}: platform performance entry needs platform")

    raw_target = entry.get("raw_target")
    if raw_target is not None and raw_target not in REQUIRED_RAW_IDS:
        failures.append(f"{entry_id}: unknown raw_target {raw_target!r}")

    metrics = entry.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        failures.append(f"{entry_id}: platform performance entry needs metrics")
    else:
        numeric_keys = [
            "fps_median",
            "target_fps",
            "p95_ms",
            "median_ms",
            "seconds_per_image",
            "peak_rss_gb",
            "max_rss_mb",
            "mac_upres_fps",
            "gvid_pack_fps",
            "stage_fps",
            "stage_seconds",
            "frame_count",
            "mb_per_second",
        ]
        has_numeric = False
        for key in numeric_keys:
            if key not in metrics:
                continue
            try:
                float(metrics[key])
            except (TypeError, ValueError):
                failures.append(f"{entry_id}: metric {key} must be numeric")
            else:
                has_numeric = True
        if not has_numeric:
            failures.append(f"{entry_id}: platform metrics need at least one numeric timing/memory value")
        if status == "meets-target":
            try:
                fps = float(metrics.get("fps_median"))
                target_fps = float(metrics.get("target_fps"))
            except (TypeError, ValueError):
                failures.append(f"{entry_id}: meets-target entries need fps_median and target_fps")
            else:
                if fps < target_fps:
                    failures.append(f"{entry_id}: fps_median below target_fps")

    if status == "blocked":
        blockers = entry.get("blocked_by")
        if not isinstance(blockers, list) or not blockers:
            failures.append(f"{entry_id}: blocked platform entries need blocked_by")
        else:
            for blocker in blockers:
                if blocker not in ALLOWED_BLOCKERS:
                    failures.append(f"{entry_id}: invalid platform blocker {blocker!r}")
        if not entry.get("reason"):
            failures.append(f"{entry_id}: blocked platform entries need reason")

    if status == "measured-stage":
        if not isinstance(entry.get("stage_scope"), str) or not entry.get("stage_scope"):
            failures.append(f"{entry_id}: measured-stage entries need stage_scope")
        if metrics and "stage_fps" not in metrics and "max_rss_mb" not in metrics:
            failures.append(f"{entry_id}: measured-stage metrics need stage_fps or max_rss_mb")

    require_receipt_refs(entry_id, entry, tracked, failures)


def require_dashboard_contract(
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    entry_id = str(entry.get("id", ""))
    status = entry.get("status")
    if status not in ALLOWED_DASHBOARD_STATUSES:
        failures.append(f"{entry_id}: invalid dashboard status {status!r}")

    for key in ("family", "purpose"):
        if not isinstance(entry.get(key), str) or not entry.get(key):
            failures.append(f"{entry_id}: dashboard entry needs {key}")

    dashboard = entry.get("dashboard")
    if not isinstance(dashboard, str) or not dashboard:
        failures.append(f"{entry_id}: dashboard entry needs dashboard")
    elif dashboard.startswith("artifacts/"):
        require_artifact_ref(entry_id, "dashboard", dashboard, failures)
    else:
        path = ROOT / dashboard
        if not path.exists():
            failures.append(f"{entry_id}: referenced dashboard does not exist: {dashboard}")
        elif dashboard not in tracked:
            failures.append(f"{entry_id}: referenced dashboard is not tracked: {dashboard}")

    metrics = entry.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, dict):
            failures.append(f"{entry_id}: metrics must be an object")
        else:
            for key, value in metrics.items():
                try:
                    float(value)
                except (TypeError, ValueError):
                    failures.append(f"{entry_id}: metric {key} must be numeric")

    if entry_id == "raw_2k_l2hh_visual_proxy":
        failure_rows = entry.get("failure_rows")
        if not isinstance(failure_rows, list) or len(failure_rows) != 4:
            failures.append(f"{entry_id}: must name the four current LPIPS-only failure rows")
        else:
            expected = {
                ("Z8Z_0002", "lower_right"),
                ("Z8Z_0003", "lower_right"),
                ("Z8Z_0009", "lower_right"),
                ("Z8Z_0020", "lower_right"),
            }
            seen: set[tuple[str, str]] = set()
            for row in failure_rows:
                if not isinstance(row, dict):
                    failures.append(f"{entry_id}: failure_rows entries must be objects")
                    continue
                image_id = str(row.get("image_id", ""))
                crop = str(row.get("crop", ""))
                seen.add((image_id, crop))
                if row.get("failed_metric") != "lpips":
                    failures.append(f"{entry_id}: failure row {image_id}:{crop} must be LPIPS-only")
                try:
                    lpips = float(row.get("lpips"))
                    ms = float(row.get("ms_ssim"))
                    y = float(row.get("y_psnr"))
                    de = float(row.get("dE2000_mean"))
                except (TypeError, ValueError):
                    failures.append(f"{entry_id}: failure row {image_id}:{crop} metrics must be numeric")
                    continue
                if lpips <= 0.15 or ms < 0.95 or y < 28.0 or de > 3.0:
                    failures.append(
                        f"{entry_id}: failure row {image_id}:{crop} must document LPIPS-only threshold miss"
                    )
            if seen != expected:
                failures.append(f"{entry_id}: failure_rows mismatch: {sorted(seen)}")

    if entry_id == "raw_2k_l2hh_edge_safe_visual_proxy":
        metrics = entry.get("metrics")
        if not isinstance(metrics, dict):
            failures.append(f"{entry_id}: edge-safe dashboard needs metrics")
        else:
            try:
                rows = int(metrics.get("rows"))
                passing = int(metrics.get("passing_rows"))
                edge_inset = int(metrics.get("edge_inset_px"))
                worst_lpips = float(metrics.get("worst_lpips"))
                worst_ms = float(metrics.get("worst_ms_ssim"))
                worst_y = float(metrics.get("worst_y_psnr"))
                worst_de = float(metrics.get("worst_dE2000_mean"))
            except (TypeError, ValueError):
                failures.append(f"{entry_id}: edge-safe metrics must be numeric")
            else:
                if rows != 84 or passing != rows:
                    failures.append(f"{entry_id}: edge-safe dashboard must pass all 84 rows")
                if edge_inset != 16:
                    failures.append(f"{entry_id}: edge-safe dashboard must record 16 px inset")
                if worst_lpips > 0.15 or worst_ms < 0.95 or worst_y < 28.0 or worst_de > 3.0:
                    failures.append(f"{entry_id}: edge-safe metrics must clear PREVIEW thresholds")

    require_receipt_refs(entry_id, entry, tracked, failures)


def require_raw_target_contract(target: dict[str, Any], failures: list[str]) -> None:
    target_id = str(target.get("id", ""))
    classification = target.get("classification")
    if classification not in ALLOWED_RAW_CLASSIFICATIONS:
        failures.append(f"{target_id}: invalid classification {classification!r}")
        return

    if not isinstance(target.get("dimensions"), str) or "x" not in target.get("dimensions", ""):
        failures.append(f"{target_id}: raw target needs dimensions")

    if classification == "live-capable":
        try:
            fps = float(target.get("pi5_fps_median"))
            p95_ms = float(target.get("pi5_p95_ms"))
        except (TypeError, ValueError):
            failures.append(f"{target_id}: live-capable raw targets need pi5_fps_median and pi5_p95_ms")
        else:
            if fps < 24.0 or p95_ms >= 41.7:
                failures.append(f"{target_id}: live-capable raw target must clear 24 fps / 41.7 ms p95 on Pi 5")

        try:
            passing = int(target.get("proxy_rows_passing", 0))
            total = int(target.get("proxy_rows_total", 0))
        except (TypeError, ValueError):
            passing = total = 0
        if total > 0 and passing < total:
            detail = str(target.get("classification_detail", "")).lower()
            if "preview" not in detail or not (
                "not a full preview" in detail
                or "not a rendered preview" in detail
                or "remains experimental" in detail
            ):
                failures.append(
                    f"{target_id}: live raw target with proxy misses must say it is not rendered PREVIEW-ready"
                )

    if classification == "preview-capable":
        try:
            passing = int(target.get("proxy_rows_passing"))
            total = int(target.get("proxy_rows_total"))
        except (TypeError, ValueError):
            failures.append(f"{target_id}: preview-capable raw targets need proxy_rows_passing/proxy_rows_total")
        else:
            if total <= 0 or passing < total:
                failures.append(f"{target_id}: preview-capable raw target must pass every proxy row")

    receipts = target.get("external_receipts")
    receipt_text = "\n".join(str(receipt) for receipt in receipts or [])
    tokens = target.get("receipt_tokens")
    if not isinstance(tokens, list) or not tokens:
        failures.append(f"{target_id}: raw target needs receipt_tokens")
    else:
        for token in tokens:
            if not isinstance(token, str) or not token:
                failures.append(f"{target_id}: receipt_tokens entries must be non-empty strings")
                continue
            if token not in receipt_text:
                failures.append(f"{target_id}: no external receipt path contains token {token!r}")


def require_preview_live_experimental_contract(entry: dict[str, Any], failures: list[str]) -> None:
    entry_id = str(entry.get("id", ""))
    if entry_id != "preview_live_codec_only":
        return

    if entry.get("status") != "experimental":
        failures.append(f"{entry_id}: live/camera-back PREVIEW must remain experimental until it passes quality")

    blockers = entry.get("blocked_by")
    if not isinstance(blockers, list) or not blockers:
        failures.append(f"{entry_id}: experimental live PREVIEW needs blocked_by list")
    else:
        for blocker in blockers:
            if blocker not in ALLOWED_BLOCKERS:
                failures.append(f"{entry_id}: invalid blocker {blocker!r}")
        if "quality_gate_failure" not in blockers:
            failures.append(f"{entry_id}: live PREVIEW blocker must include quality_gate_failure")

    gate = entry.get("current_gate_result")
    if not isinstance(gate, dict):
        failures.append(f"{entry_id}: experimental live PREVIEW needs current_gate_result")
    else:
        if gate.get("run_hash") != entry.get("committed_run_hash"):
            failures.append(f"{entry_id}: current_gate_result run_hash must match committed_run_hash")
        if gate.get("verdict") != "FAIL":
            failures.append(f"{entry_id}: current_gate_result must record the current FAIL")
        try:
            pass_images = int(gate.get("passing_images"))
            total_images = int(gate.get("total_images"))
            worst_lpips = float(gate.get("worst_lpips"))
            worst_ms = float(gate.get("worst_ms_ssim"))
            worst_y = float(gate.get("worst_y_psnr"))
            worst_de = float(gate.get("worst_dE2000"))
        except (TypeError, ValueError):
            failures.append(f"{entry_id}: current_gate_result metrics must be numeric")
        else:
            if pass_images >= total_images:
                failures.append(f"{entry_id}: current_gate_result must show at least one failing image")
            if not (
                worst_lpips > 0.15
                or worst_ms < 0.95
                or worst_y < 28.0
                or worst_de > 3.0
            ):
                failures.append(f"{entry_id}: current_gate_result does not show a PREVIEW threshold miss")

    speed = entry.get("speed_evidence")
    if not isinstance(speed, dict):
        failures.append(f"{entry_id}: experimental live PREVIEW needs speed_evidence")
    else:
        try:
            fps = float(speed.get("pi5_fps_median"))
            p95_ms = float(speed.get("pi5_p95_ms"))
        except (TypeError, ValueError):
            failures.append(f"{entry_id}: speed_evidence fps/p95 must be numeric")
        else:
            if fps < 24.0 or p95_ms >= 41.7:
                failures.append(f"{entry_id}: speed_evidence must show current speed path clears 24 fps timing")
        receipt = speed.get("receipt")
        if not isinstance(receipt, str):
            failures.append(f"{entry_id}: speed_evidence needs receipt")
        else:
            require_artifact_ref(entry_id, "speed_evidence receipt", receipt, failures)

    promotion = entry.get("promotion_requirements")
    if not isinstance(promotion, list) or not promotion:
        failures.append(f"{entry_id}: experimental live PREVIEW needs promotion_requirements")
    else:
        text = "\n".join(str(item).lower() for item in promotion)
        for required in ("preview", "lpips", "ms-ssim", "y-psnr", "de2000", "24 fps"):
            if required not in text:
                failures.append(f"{entry_id}: promotion_requirements missing {required}")


def require_preview_live_edge_safe_contract(
    entry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    entry_id = str(entry.get("id", ""))
    if entry_id != "preview_live_2k_l2hh_edge_safe":
        return

    if entry.get("status") != "production-pass-external-receipt":
        failures.append(f"{entry_id}: bounded live PREVIEW must use external receipt status")
    if entry.get("family") != "preview" or entry.get("ship_class") != "PREVIEW":
        failures.append(f"{entry_id}: bounded live PREVIEW must stay in PREVIEW family/class")
    if entry.get("raw_target") != "2k_raw_0p5x_l2hh":
        failures.append(f"{entry_id}: bounded live PREVIEW must use 2k_raw_0p5x_l2hh")
    if entry.get("policy") != "preview_live_2k_l2hh_edge_safe_v1":
        failures.append(f"{entry_id}: unexpected live PREVIEW policy id")

    runtime_entrypoint = entry.get("runtime_entrypoint")
    if runtime_entrypoint != "tools/live_preview_policy.py" or runtime_entrypoint not in tracked:
        failures.append(f"{entry_id}: live PREVIEW runtime policy tool must be tracked")
    else:
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            from live_preview_policy import materialize_policy  # type: ignore

            policy = materialize_policy(str(entry.get("policy")))
        except Exception as exc:
            failures.append(f"{entry_id}: live PREVIEW policy cannot be materialized: {exc}")
            policy = {}
        if policy:
            expected_policy = {
                "production_path_id": entry_id,
                "raw_target": "2k_raw_0p5x_l2hh",
                "source_codec": "ml2_q3_dec2",
                "display_mode": "edge_safe_viewport",
                "edge_inset_px": 16,
                "forbids_ref_content": True,
            }
            for key, expected in expected_policy.items():
                if policy.get(key) != expected:
                    failures.append(f"{entry_id}: policy {key} {policy.get(key)!r} != {expected!r}")
            viewport = policy.get("display_viewport")
            if viewport != {"x": 16, "y": 16, "width": 2038, "height": 1348}:
                failures.append(f"{entry_id}: policy viewport mismatch: {viewport!r}")

    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        failures.append(f"{entry_id}: bounded live PREVIEW needs metrics")
        return
    try:
        rows = int(metrics.get("holdout_rows"))
        passing = int(metrics.get("passing_rows"))
        edge_inset = int(metrics.get("edge_inset_px"))
        input_width = int(metrics.get("input_width"))
        input_height = int(metrics.get("input_height"))
        viewport_width = int(metrics.get("viewport_width"))
        viewport_height = int(metrics.get("viewport_height"))
        worst_lpips = float(metrics.get("worst_lpips"))
        worst_ms = float(metrics.get("worst_ms_ssim"))
        worst_y = float(metrics.get("worst_y_psnr"))
        worst_de = float(metrics.get("worst_dE2000"))
        fps = float(metrics.get("pi5_fps_median"))
        p95 = float(metrics.get("pi5_p95_ms"))
    except (TypeError, ValueError):
        failures.append(f"{entry_id}: bounded live PREVIEW metrics must be numeric")
        return
    if rows != 84 or passing != rows:
        failures.append(f"{entry_id}: bounded live PREVIEW must show an 84/84 holdout pass")
    if edge_inset != 16:
        failures.append(f"{entry_id}: bounded live PREVIEW must keep a 16 px inset")
    if (input_width, input_height, viewport_width, viewport_height) != (2070, 1380, 2038, 1348):
        failures.append(f"{entry_id}: bounded live PREVIEW dimensions/viewport drifted")
    if worst_lpips > 0.15 or worst_ms < 0.95 or worst_y < 28.0 or worst_de > 3.0:
        failures.append(f"{entry_id}: bounded live PREVIEW metrics must clear PREVIEW thresholds")
    if fps < 24.0 or p95 >= 41.7:
        failures.append(f"{entry_id}: bounded live PREVIEW must clear Pi 5 timing")

    constraints = "\n".join(str(item).lower() for item in entry.get("constraints", []))
    for required in ("no ref", "16 px", "exact outer-edge"):
        if required not in constraints:
            failures.append(f"{entry_id}: constraints must document {required}")


def require_preview_offline_review_contract(
    entry: dict[str, Any],
    pipelines: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    entry_id = str(entry.get("id", ""))
    if entry_id != "preview_offline_review_q8_threeway":
        return

    if entry.get("status") != "production-pass-external-receipt":
        failures.append(f"{entry_id}: offline/review PREVIEW must use external receipt status")
    if entry.get("family") != "preview" or entry.get("ship_class") != "PREVIEW":
        failures.append(f"{entry_id}: offline/review PREVIEW must stay in PREVIEW family/class")

    pipeline_key = entry.get("pipeline")
    pipeline = pipelines.get(pipeline_key) if isinstance(pipeline_key, str) else None
    if not isinstance(pipeline, dict):
        failures.append(f"{entry_id}: missing registered offline/review PREVIEW pipeline")
    else:
        pipeline_doc = str(pipeline.get("$doc", "")).lower()
        if pipeline.get("use_for") != "PREVIEW_OFFLINE_REVIEW_Q8_THREEWAY":
            failures.append(f"{entry_id}: registered pipeline use_for must be offline/review q8 three-way")
        for required in ("offline/review", "not live/camera-back preview"):
            if required not in pipeline_doc:
                failures.append(f"{entry_id}: registered pipeline doc must say {required}")

    docs = entry.get("docs")
    if not isinstance(docs, list):
        docs = []
    for required_doc in ("README.md", "docs/VIDEO_STATUS.md"):
        if required_doc not in docs:
            failures.append(f"{entry_id}: docs must include {required_doc}")
            continue
        if required_doc not in tracked:
            failures.append(f"{entry_id}: required doc is not tracked: {required_doc}")
            continue
        text = (ROOT / required_doc).read_text(errors="ignore").lower()
        if "offline/review" not in text:
            failures.append(f"{entry_id}: {required_doc} must describe offline/review PREVIEW")
        if "not a live/camera-back preview path" not in text and "not live/camera-back preview" not in text:
            failures.append(f"{entry_id}: {required_doc} must distinguish this from live/camera-back preview")

    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        failures.append(f"{entry_id}: offline/review PREVIEW needs metrics")
        return
    try:
        holdout_rows = int(metrics.get("holdout_rows"))
        passing_rows = int(metrics.get("passing_rows"))
        worst_lpips = float(metrics.get("worst_lpips"))
        worst_ms = float(metrics.get("worst_ms_ssim"))
        worst_y = float(metrics.get("worst_y_psnr"))
        worst_de = float(metrics.get("worst_dE2000"))
        fps = float(metrics.get("fps"))
        seconds_per_image = float(metrics.get("seconds_per_image"))
        peak_rss_gb = float(metrics.get("peak_rss_gb"))
    except (TypeError, ValueError):
        failures.append(f"{entry_id}: offline/review PREVIEW metrics must be numeric")
        return
    if passing_rows != holdout_rows or holdout_rows < 84:
        failures.append(f"{entry_id}: offline/review PREVIEW must show full 84-row holdout pass")
    if worst_lpips > 0.15 or worst_ms < 0.95 or worst_y < 28.0 or worst_de > 3.0:
        failures.append(f"{entry_id}: offline/review PREVIEW metrics must clear committed thresholds")
    if fps >= 1.0 or seconds_per_image <= 1.0:
        failures.append(f"{entry_id}: offline/review PREVIEW must record non-live throughput")
    if peak_rss_gb <= 0.0:
        failures.append(f"{entry_id}: offline/review PREVIEW needs memory receipt metric")


def main() -> int:
    failures: list[str] = []
    manifest = load_json(MANIFEST)
    registry = load_json(REGISTRY)
    pipelines = registry.get("pipelines") or {}
    tracked = tracked_paths()

    if manifest.get("schema") != EXPECTED_SCHEMA:
        failures.append(f"schema must be {EXPECTED_SCHEMA}")

    production_paths = manifest.get("production_paths")
    if not isinstance(production_paths, list):
        failures.append("production_paths must be a list")
        production_paths = []

    seen_output_ids: set[str] = set()
    for entry in production_paths:
        if not isinstance(entry, dict):
            failures.append("production_paths entries must be objects")
            continue
        entry_id = str(entry.get("id", ""))
        seen_output_ids.add(entry_id)
        status = entry.get("status")
        if status not in ALLOWED_STATUSES:
            failures.append(f"{entry_id}: invalid status {status!r}")

        pipeline = entry.get("pipeline")
        if pipeline:
            if pipeline not in pipelines:
                failures.append(f"{entry_id}: pipeline is not registered: {pipeline}")
            else:
                expected_class = entry.get("ship_class")
                actual_class = (pipelines[pipeline] or {}).get("ship_class")
                if expected_class and actual_class != expected_class:
                    failures.append(
                        f"{entry_id}: registry ship_class {actual_class!r} != manifest {expected_class!r}"
                    )

        run_hash = entry.get("committed_run_hash")
        if run_hash:
            run = run_for_hash(str(run_hash))
            rel = f"tests/quality_gates/runs/{run_hash}/run.json"
            if not run:
                failures.append(f"{entry_id}: missing or unreadable committed run {run_hash}")
            elif rel not in tracked:
                failures.append(f"{entry_id}: committed run is not tracked: {rel}")
            else:
                if run.get("run_hash") != run_hash:
                    failures.append(f"{entry_id}: run_hash mismatch in {rel}")
                if run.get("pipeline") != pipeline:
                    failures.append(f"{entry_id}: run pipeline does not match manifest")
                if run.get("ship_class") != entry.get("ship_class"):
                    failures.append(f"{entry_id}: run ship_class does not match manifest")
                if status in PRODUCTION_STATUSES and run.get("verdict") != "PASS":
                    failures.append(f"{entry_id}: production path references non-PASS run {run_hash}")

        if status == "production-pass-external-receipt":
            receipt = entry.get("external_receipt")
            dashboard = entry.get("dashboard")
            runtime_entrypoint = entry.get("runtime_entrypoint")
            if not isinstance(receipt, str):
                failures.append(f"{entry_id}: external receipt must be a string")
            else:
                require_artifact_ref(entry_id, "external receipt", receipt, failures)
            if not isinstance(dashboard, str):
                failures.append(f"{entry_id}: external dashboard must be a string")
            else:
                require_artifact_ref(entry_id, "external dashboard", dashboard, failures)
            if not isinstance(runtime_entrypoint, str) or runtime_entrypoint not in tracked:
                failures.append(f"{entry_id}: runtime entrypoint must be tracked")
            metrics = entry.get("metrics")
            if not isinstance(metrics, dict):
                failures.append(f"{entry_id}: external receipt path needs compact metrics")
            elif metrics.get("passing_rows") != metrics.get("holdout_rows"):
                failures.append(f"{entry_id}: external receipt metrics do not show full holdout pass")

        if status == "experimental" and not entry.get("reason"):
            failures.append(f"{entry_id}: experimental entries need a reason")

        if entry_id in REQUIRED_EXTERNAL_RECEIPT_IDS:
            require_external_receipts(entry_id, entry, failures)

        require_preview_live_experimental_contract(entry, failures)
        require_preview_live_edge_safe_contract(entry, tracked, failures)
        require_preview_offline_review_contract(entry, pipelines, tracked, failures)
        require_tracked_refs(entry_id, entry, tracked, failures)

    missing_output_ids = REQUIRED_OUTPUT_IDS - seen_output_ids
    if missing_output_ids:
        failures.append("manifest missing output ids: " + ", ".join(sorted(missing_output_ids)))

    raw_targets = manifest.get("raw_targets")
    if not isinstance(raw_targets, list):
        failures.append("raw_targets must be a list")
        raw_targets = []

    seen_raw_ids: set[str] = set()
    for target in raw_targets:
        if not isinstance(target, dict):
            failures.append("raw_targets entries must be objects")
            continue
        target_id = str(target.get("id", ""))
        seen_raw_ids.add(target_id)
        require_raw_target_contract(target, failures)
        require_external_receipts(target_id, target, failures)
        require_tracked_refs(target_id, target, tracked, failures)

    missing_raw_ids = REQUIRED_RAW_IDS - seen_raw_ids
    if missing_raw_ids:
        failures.append("manifest missing raw target ids: " + ", ".join(sorted(missing_raw_ids)))

    platform_performance = manifest.get("platform_performance")
    if not isinstance(platform_performance, list):
        failures.append("platform_performance must be a list")
        platform_performance = []

    seen_platform_ids: set[str] = set()
    for entry in platform_performance:
        if not isinstance(entry, dict):
            failures.append("platform_performance entries must be objects")
            continue
        entry_id = str(entry.get("id", ""))
        seen_platform_ids.add(entry_id)
        require_platform_performance_contract(entry, tracked, failures)
        require_tracked_refs(entry_id, entry, tracked, failures)

    missing_platform_ids = REQUIRED_PLATFORM_PERFORMANCE_IDS - seen_platform_ids
    if missing_platform_ids:
        failures.append("manifest missing platform performance ids: " + ", ".join(sorted(missing_platform_ids)))

    dashboards = manifest.get("dashboards")
    if not isinstance(dashboards, list):
        failures.append("dashboards must be a list")
        dashboards = []

    seen_dashboard_ids: set[str] = set()
    for entry in dashboards:
        if not isinstance(entry, dict):
            failures.append("dashboards entries must be objects")
            continue
        entry_id = str(entry.get("id", ""))
        seen_dashboard_ids.add(entry_id)
        require_dashboard_contract(entry, tracked, failures)
        require_tracked_refs(entry_id, entry, tracked, failures)

    missing_dashboard_ids = REQUIRED_DASHBOARD_IDS - seen_dashboard_ids
    if missing_dashboard_ids:
        failures.append("manifest missing dashboard ids: " + ", ".join(sorted(missing_dashboard_ids)))

    release_checks = manifest.get("release_checks")
    if not isinstance(release_checks, list):
        failures.append("release_checks must be a list")
        release_checks = []
    release_check_text = "\n".join(str(item) for item in release_checks)
    for required in (
        "tools/test/check_sensitive_content.py",
        "tools/test/check_repo_artifact_hygiene.py",
        "tools/test/check_release_evidence_manifest.py",
        "tools/verify_production_artifacts.py",
        "tools/live_preview_policy.py",
        "tests/quality_gates/check_registry_consistency.py",
        "tests/quality_gates/audit_production_readiness.py --strict",
    ):
        if required not in release_check_text:
            failures.append(f"release_checks missing {required}")

    for guard in manifest.get("guards", []):
        if not isinstance(guard, str) or guard not in tracked:
            failures.append(f"guard is not tracked: {guard}")

    if failures:
        print("Release evidence manifest check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("OK - release evidence manifest check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
