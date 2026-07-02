#!/usr/bin/env python3
"""Validate the compact release evidence manifest.

This check keeps high-level production claims tied to concrete registry entries,
committed quality-gate runs, external receipt references, and tracked docs/tools.
It intentionally does not require heavyweight external artifacts in CI.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/release_evidence_manifest.json"
REGISTRY = ROOT / "pipelines/registry.json"
README = ROOT / "README.md"
DOCS_README = ROOT / "docs/README.md"
RELEASE_READINESS = ROOT / "docs/RELEASE_READINESS.md"
PRODUCTION_ARTIFACTS = ROOT / "docs/PRODUCTION_ARTIFACTS.md"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
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
    "camera-mvp-stand-in",
    "preview-capable",
    "offline-only",
    "offline-production",
}
REQUIRED_OUTPUT_IDS = {
    "still_smallest",
    "still_primary",
    "still_archival",
    "video_freeze_primary",
    "video_freeze_smallest",
    "video_freeze_smallest_conservative",
    "video_freeze_alternate_tighter_lpips",
    "upresable_editable_raw",
    "preview_offline_review_q8_threeway",
    "preview_live_codec_only",
    "preview_live_mission1_1024",
    "gvid_container",
    "mov_wrapper",
    "prores_review_outputs",
    "editable_dng_gpr_outputs",
}
REQUIRED_RAW_IDS = {
    "2k_raw_0p5x_fast",
    "2k_raw_0p5x_l2hh",
    "mission1_native12_4k_gvid",
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
    "mission1_numbered_list_closure_plan",
}
REQUIRED_PRODUCT_PILLARS = {
    "raw_stills": {
        "label": "RAW stills",
        "status": "locked_with_sample_gaps",
        "refs": {
            "production_paths": {"still_smallest", "still_primary", "still_archival"},
            "dashboards": {
                "realphoto_bayer_phase_sample_20260630",
                "targeted_raw_fixture_scan_20260630",
                "source_root_raw_fixture_scan_20260630",
                "camera_noise_runtime_policy_20260630",
            },
        },
        "tokens": ("50 MP", "100 MP", "noise"),
    },
    "raw_video_mvp": {
        "label": "RAW video MVP",
        "status": "pi_stand_in_pass_camera_handoff_open",
        "refs": {
            "production_paths": {
                "preview_live_mission1_1024",
                "gvid_container",
                "mov_wrapper",
                "prores_review_outputs",
                "editable_dng_gpr_outputs",
            },
            "raw_targets": {"mission1_native12_4k_gvid"},
            "platform_performance": {
                "pi5_mission1_halfres_capture",
                "pi5_mission1_bench_fused_dma_like_stream_source",
            },
        },
        "tokens": ("4096 x 3072", "Mission 1", "camera-role"),
    },
    "premium_still_sr": {
        "label": "Premium still/SR",
        "status": "research_loop_working_candidate_not_promoted",
        "refs": {
            "dashboards": {
                "premium_still_sr_raw_cfa_residual_gap_20260701",
                "premium_still_sr_self_supervised_raw_sr_contract_20260702",
                "premium_still_sr_self_supervised_raw_sr_pair_audit_smoke_20260702",
                "premium_still_sr_clean_source_pair_model_smoke_20260702",
                "premium_still_sr_self_supervised_raw_sr_pair_audit_routed_t16_20260702",
                "premium_still_sr_clean_source_pair_model_routed_x2dholdout_w48_1500_20260702",
                "premium_still_sr_clean_source_pair_model_routed_z8holdout_w48_1500_20260702",
                "premium_still_sr_clean_source_pair_model_routed_x2dholdout_naf_grad_w48_500_20260702",
                "premium_still_sr_clean_source_pair_model_routed_z8holdout_naf_grad_w48_500_20260702",
                "premium_still_sr_noise_policy_gate_20260702",
                "cnn_product_scorecard_20260629",
            },
        },
        "tokens": ("Candidate-only", "50 MP", "100 MP"),
    },
    "raw_video_reconstruction": {
        "label": "RAW video reconstruction",
        "status": "approved_offline_reconstruction_psf_research_optional",
        "refs": {
            "raw_targets": {"8k_raw_2x"},
            "dashboards": {
                "cnn_product_scorecard_20260629",
                "z8_continuous_8k_no_cnn_vs_cnn_20260630",
                "mission1_8k_true_no_cnn_vs_cnn_20260630",
                "mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630",
                "mission1_8k_sr_step0075_visual_signoff_20260701",
                "mission1_8k_sr_step0075_signed_audit_20260701",
            },
            "platform_performance": {"local_8k_raw_offline"},
        },
        "tokens": ("continuous", "PSF", "baselines", "optional"),
    },
}
OPTIONAL_RESEARCH_REFS = {
    "raw_video_psf_replacement": {
        "dashboards": {
            "mission1_native_psf_corpus_audit_20260630",
            "mission1_native_psf_kernel_stability_audit_20260630",
            "raw_video_psf_capture_request_20260630",
            "bayer_resize_psf_known_kernel_validation_20260701",
            "raw_video_sr_candidate_scoreboard_20260701",
            "raw_video_psf_next_experiment_contract_20260701",
        },
        "scope_tokens": (
            "Optional next-generation research only",
            "must not be counted as release blockers",
        ),
    }
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

README_REQUIRED_SECTIONS = (
    "## Open Raw Video For Action Cameras",
    "## What It Enables",
    "## Status At A Glance",
    "## Mission 1 Numbered List",
    "## Quality Model",
    "## Media And Dashboards",
    "## Raw Output Ladder",
    "## Mission 1 Reality Check",
    "## Quick Start",
    "## Documentation",
)

README_REQUIRED_TOKENS = (
    "8-bit JPEG size. 16-bit RAW quality. Editable Bayer video.",
    "open raw Bayer media suite",
    "actual Mission 1 sensor/DMA",
    "docs/img/readme_showcase.webp",
    "docs/img/readme_z8_timelapse_1024.webp",
    "docs/img/readme_pipeline_flow.svg",
    "docs/img/readme_status_matrix.svg",
    "docs/img/still_three_tiers.png",
    ".gvid",
    "MOV / ProRes",
    "PREVIEW offline/review",
    "PREVIEW live/camera-back",
    "mission1_preview_1024",
    "mission1_native12_4k_gvid",
    "camera MVP stand-in",
    "20.50 fps wall / 21.52 fps median",
    "4k_raw_1x",
    "8k_raw_2x",
    "Mission 1 Numbered List",
    "docs/MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md",
    "gpr_labs_encoder",
    "test_labs_encoder_api",
    "target_preflight_receipt.json",
    "mission1_camera_closure_run.json",
    "Real Mission 1 sensor/DMA/storage handoff receipt",
    "Real Mission 1 UI/display receipt",
    "4K cleanup production signoff",
    "/Volumes/OWC_8TB/gpr_work/artifacts",
    "docs/RELEASE_READINESS.md",
)

RELEASE_READINESS_REQUIRED_SECTIONS = (
    "## Production Goal",
    "## Production Definition Of Done",
    "## Readiness Snapshot",
    "## Current Ship Matrix",
    "## Release Evidence",
    "## Focused Checks",
)

RELEASE_READINESS_REQUIRED_TOKENS = (
    "Productionize GPR as a release-quality raw media suite",
    "Every registered production path is passing its committed gate or explicitly",
    "PREVIEW/live decode has a no-REF runtime path",
    "A path is production only when the repo can prove all of these",
    "Runtime inputs",
    "PREVIEW render paths must not use REF content",
    "Output contract",
    "Performance",
    "Reproducibility",
    "Repo hygiene",
    "/Volumes/OWC_8TB/gpr_work",
    "2K raw target",
    "4K raw target",
    "8K raw target",
    "offline-only",
    "4K raw-video target",
    "PASS on the Pi 5 stand-in for the accepted 20+ fps floor",
    "Strict 24 fps is stretch performance research unless the product bar is raised again",
    "Mission 1 and iPhone noise sidecars",
    "Premium still-SR promotion",
    "Optional stretch work, not release blockers",
    "This check is intentionally not part of the current release blocker list",
    "preview_live_mission1_1024",
    "CI-safe release checks",
    "tools/verify_production_artifacts.py",
    "tests/quality_gates/audit_production_readiness.py --strict",
)

RELEASE_READINESS_FORBIDDEN_TOKENS = (
    "| Native 12MP strict 24 fps |",
    "| T233 threshold speed probes |",
    "| Repo merge readiness |",
    "large dirty surface across source, tools, docs, and tests",
    "ready to claim strict 24 fps production",
)

REQUIRED_RELEASE_CHECKS = (
    "python3 tools/test/check_sensitive_content.py",
    "python3 tools/test/check_sensitive_content.py --history",
    "python3 tools/test/check_repo_artifact_hygiene.py",
    "python3 tools/test/check_readme_media.py",
    "python3 tools/test/test_check_readme_media.py",
    "python3 tools/test/check_release_evidence_manifest.py",
    "python3 tools/test/check_labs_readiness.py",
    "python3 tools/test/test_mission1_numbered_list_readiness.py",
    "python3 tools/test/test_mission1_numbered_list_closure_plan.py",
    "python3 tools/test/test_mission1_8k_sr_production_promotion.py",
    "python3 tools/test/test_build_mission1_8k_sr_visual_review.py",
    "python3 tools/test/test_build_cnn_product_scorecard.py",
    "python3 tools/test/test_mission1_camera_dispatch_inputs.py",
    "python3 tools/test/test_mission1_camera_closure_package.py",
    "python3 tools/test/test_mission1_camera_hardware_audit.py",
    "python3 tools/test/test_mission1_camera_source_probe.py",
    "python3 tools/test/test_mission1_camera_target_preflight.py",
    "python3 tools/test/test_collect_mission1_target_closure.py",
    "python3 tools/test/test_run_mission1_target_closure_package.py",
    "python3 tools/test/test_run_mission1_remote_closure_package.py",
    "python3 tools/test/test_run_mission1_camera_closure.py",
    "python3 tools/test/test_mission1_camera_closure_run.py",
    "python3 tools/test/check_labs_target_receipts.py",
    "python3 tools/verify_production_artifacts.py",
    "python3 tools/test/test_verify_production_artifacts.py",
    "python3 tools/verify_production_artifacts.py --strict",
    "python3 tools/verify_release_manifest_artifacts.py --summary",
    "python3 tools/test/test_verify_release_manifest_artifacts.py",
    "python3 tools/verify_release_manifest_artifacts.py --strict --summary",
    "python3 tools/live_preview_policy.py",
    "python3 tools/test/test_raw_resolution_targets.py",
    "python3 tools/test/test_bayer_resample.py",
    "bash tools/test/test_gvid_pack.sh",
    "bash tools/test/test_gvid_metadata.sh",
    "bash tools/test/test_labs_bundle_verify.sh",
    "bash tools/test/test_labs_target_bench_smoke.sh",
    "bash tools/test/test_labs_encoder_bench_cli.sh",
    "bash tools/test/test_labs_camera_handoff_receipt.sh",
    "bash tools/test/test_labs_preview_ui_receipt.sh",
    "bash tools/test/test_build_labs_preview_ui_receipt.sh",
    "bash tools/test/test_mission1_4k_cleanup_signoff_receipt.sh",
    "bash tools/test/test_build_mission1_4k_cleanup_signoff_receipt.sh",
    "python3 tools/test/test_native12_sr8k_readiness_audit.py",
    "python3 tools/test/test_mission1_sr_production_gap_report.py",
    "python3 tools/test/test_decide_mission1_sr_promotion.py",
    "python3 tools/test/test_run_mission1_sr_guarded_experiment.py",
    "python3 tools/test/test_mission1_native12_sr_frontier_summary.py",
    "python3 tools/test/test_mission1_native12_frontier_summary.py",
    "python3 tools/test/test_mission1_write_contention_summary.py",
    "python3 tools/test/test_mission1_strict24_probe_matrix_summary.py",
    "python3 tools/test/test_mission1_sr_pair_codec_profiles.py",
    "python3 tests/quality_gates/check_registry_consistency.py",
    "python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts",
    "python3 tests/quality_gates/audit_ship_pipelines.py --strict",
    "python3 tests/quality_gates/audit_production_readiness.py --strict",
)

REQUIRED_CI_CHECKS = (
    "python3 tools/test/check_sensitive_content.py",
    "python3 tools/test/check_sensitive_content.py --history",
    "python3 tools/test/check_repo_artifact_hygiene.py",
    "python3 tools/test/check_readme_media.py",
    "python3 tools/test/test_check_readme_media.py",
    "python3 tools/test/check_release_evidence_manifest.py",
    "python3 tools/test/check_labs_readiness.py",
    "python3 tools/test/test_mission1_numbered_list_readiness.py",
    "python3 tools/test/test_mission1_numbered_list_closure_plan.py",
    "python3 tools/test/test_mission1_8k_sr_production_promotion.py",
    "python3 tools/test/test_build_mission1_8k_sr_visual_review.py",
    "python3 tools/test/test_build_cnn_product_scorecard.py",
    "python3 tools/test/test_mission1_camera_dispatch_inputs.py",
    "python3 tools/test/test_mission1_camera_closure_package.py",
    "python3 tools/test/test_mission1_camera_hardware_audit.py",
    "python3 tools/test/test_mission1_camera_target_preflight.py",
    "python3 tools/test/test_collect_mission1_target_closure.py",
    "python3 tools/test/test_run_mission1_target_closure_package.py",
    "python3 tools/test/test_run_mission1_remote_closure_package.py",
    "python3 tools/test/test_run_mission1_camera_closure.py",
    "python3 tools/test/test_mission1_camera_closure_run.py",
    "python3 tools/test/check_labs_target_receipts.py",
    "python3 tools/verify_production_artifacts.py",
    "python3 tools/test/test_verify_production_artifacts.py",
    "python3 tools/verify_release_manifest_artifacts.py --summary",
    "python3 tools/test/test_verify_release_manifest_artifacts.py",
    "python3 tools/live_preview_policy.py",
    "python3 tools/test/test_raw_resolution_targets.py",
    "python3 tools/test/test_bayer_resample.py",
    "bash tools/test/test_gvid_pack.sh",
    "bash tools/test/test_gvid_metadata.sh",
    "bash tools/test/test_labs_bundle_verify.sh",
    "bash tools/test/test_labs_target_bench_smoke.sh",
    "bash tools/test/test_labs_encoder_bench_cli.sh",
    "bash tools/test/test_labs_camera_handoff_receipt.sh",
    "bash tools/test/test_labs_preview_ui_receipt.sh",
    "bash tools/test/test_build_labs_preview_ui_receipt.sh",
    "bash tools/test/test_mission1_4k_cleanup_signoff_receipt.sh",
    "bash tools/test/test_build_mission1_4k_cleanup_signoff_receipt.sh",
    "python3 tools/test/test_native12_sr8k_readiness_audit.py",
    "python3 tools/test/test_mission1_sr_production_gap_report.py",
    "python3 tools/test/test_decide_mission1_sr_promotion.py",
    "python3 tools/test/test_run_mission1_sr_guarded_experiment.py",
    "python3 tools/test/test_mission1_native12_sr_frontier_summary.py",
    "python3 tools/test/test_mission1_native12_frontier_summary.py",
    "python3 tools/test/test_mission1_write_contention_summary.py",
    "python3 tools/test/test_mission1_strict24_probe_matrix_summary.py",
    "python3 tools/test/test_mission1_sr_pair_codec_profiles.py",
    "python3 tests/quality_gates/check_registry_consistency.py",
    "python3 tests/quality_gates/audit_ship_pipelines.py --strict",
)

REQUIRED_BLOCKED_RELEASE_CHECKS = (
    "python3 tests/quality_gates/audit_production_readiness.py --strict --require-mission1-strict24",
    "python3 tools/mission1_numbered_list_readiness.py --external-root /Volumes/OWC_8TB/gpr_work --require-production",
)

EXTERNAL_RELEASE_ONLY_CHECKS = (
    "python3 tools/verify_production_artifacts.py --strict",
    "python3 tools/verify_release_manifest_artifacts.py --strict --summary",
    "python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts",
    "python3 tests/quality_gates/audit_production_readiness.py --strict",
)

PRODUCTION_ARTIFACT_REQUIRED_TOKENS = (
    "Required Registry Artifacts",
    "Release mode verifies every checkpoint and registered training-pair field",
    "python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts",
)

DATE_RE = re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)|(?<!\d)(20\d{6})(?!\d)")


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


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def parse_date_token(match: re.Match[str]) -> dt.date:
    if match.group(1):
        return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    compact = match.group(4)
    assert compact is not None
    return dt.date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))


def require_manifest_freshness(manifest: dict[str, Any], failures: list[str]) -> None:
    updated_raw = manifest.get("updated")
    if not isinstance(updated_raw, str):
        failures.append("manifest updated must be an ISO date string")
        return
    try:
        updated = dt.date.fromisoformat(updated_raw)
    except ValueError:
        failures.append(f"manifest updated is not an ISO date: {updated_raw!r}")
        return

    referenced_dates: list[dt.date] = []
    for text in iter_strings(manifest):
        for match in DATE_RE.finditer(text):
            try:
                referenced_dates.append(parse_date_token(match))
            except ValueError:
                failures.append(f"manifest contains invalid embedded date in {text!r}")
    if not referenced_dates:
        failures.append("manifest must reference at least one dated evidence artifact")
        return

    newest = max(referenced_dates)
    if updated < newest:
        failures.append(
            f"manifest updated date {updated.isoformat()} is older than newest referenced evidence "
            f"{newest.isoformat()}"
        )


def require_readme_contract(tracked: set[str], failures: list[str]) -> None:
    if "README.md" not in tracked:
        failures.append("README.md must be tracked")
        return
    if not README.exists():
        failures.append("README.md is missing")
        return

    readme = README.read_text(encoding="utf-8")
    for section in README_REQUIRED_SECTIONS:
        if section not in readme:
            failures.append(f"README.md missing section {section!r}")
    for token in README_REQUIRED_TOKENS:
        if token not in readme:
            failures.append(f"README.md missing production contract token {token!r}")

    if "docs/RELEASE_READINESS.md" not in tracked:
        failures.append("docs/RELEASE_READINESS.md must be tracked")
    elif not RELEASE_READINESS.exists():
        failures.append("docs/RELEASE_READINESS.md is missing")
    else:
        release_readiness = RELEASE_READINESS.read_text(encoding="utf-8")
        for section in RELEASE_READINESS_REQUIRED_SECTIONS:
            if section not in release_readiness:
                failures.append(f"docs/RELEASE_READINESS.md missing section {section!r}")
        for token in RELEASE_READINESS_REQUIRED_TOKENS:
            if token not in release_readiness:
                failures.append(f"docs/RELEASE_READINESS.md missing production contract token {token!r}")
        for token in RELEASE_READINESS_FORBIDDEN_TOKENS:
            if token in release_readiness:
                failures.append(f"docs/RELEASE_READINESS.md contains stale release-readiness token {token!r}")

    if "docs/README.md" not in tracked:
        failures.append("docs/README.md must be tracked")
    else:
        docs_readme = DOCS_README.read_text(encoding="utf-8")
        for token in (
            "Release readiness and production proof",
            "MISSION1_NUMBERED_LIST_BURNDOWN_2026-06-25.md",
            "test_mission1_numbered_list_readiness.py",
            "test_mission1_numbered_list_closure_plan.py",
            "test_mission1_8k_sr_production_promotion.py",
            "test_build_mission1_8k_sr_visual_review.py",
            "test_mission1_camera_dispatch_inputs.py",
            "test_mission1_camera_closure_package.py",
            "check_mission1_camera_closure_package.py",
            "test_mission1_camera_target_preflight.py",
            "test_verify_release_manifest_artifacts.py",
            "test_labs_encoder_api",
            "labs_encoder_bench_cli",
            "test_labs_encoder_bench_cli.sh",
            "test_labs_camera_handoff_receipt.sh",
        ):
            if token not in docs_readme:
                failures.append(f"docs/README.md must link {token}")


def checkpoint_specs(cnn: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    specs: list[tuple[str, str, str | None]] = []
    if "ckpt_path" in cnn:
        specs.append(("ckpt_path", str(cnn["ckpt_path"]), cnn.get("ckpt_sha256")))
    if "training_pairs_path" in cnn:
        specs.append(("training_pairs_path", str(cnn["training_pairs_path"]), cnn.get("training_pairs_sha256")))
    for suffix in ("y", "cb", "cr", "chroma", "detail", "rgb_detail"):
        path_key = f"ckpt_{suffix}"
        if path_key in cnn:
            specs.append((path_key, str(cnn[path_key]), cnn.get(f"{path_key}_sha256")))
    if "luma_detail_refiner" in cnn:
        specs.append((
            "luma_detail_refiner",
            str(cnn["luma_detail_refiner"]),
            cnn.get("luma_detail_refiner_sha256"),
        ))
    return specs


def require_production_artifacts_contract(
    registry: dict[str, Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    if "docs/PRODUCTION_ARTIFACTS.md" not in tracked:
        failures.append("docs/PRODUCTION_ARTIFACTS.md must be tracked")
        return
    if not PRODUCTION_ARTIFACTS.exists():
        failures.append("docs/PRODUCTION_ARTIFACTS.md is missing")
        return

    text = PRODUCTION_ARTIFACTS.read_text(encoding="utf-8")
    for token in PRODUCTION_ARTIFACT_REQUIRED_TOKENS:
        if token not in text:
            failures.append(f"docs/PRODUCTION_ARTIFACTS.md missing artifact contract token {token!r}")
    for cnn_name, cnn in registry.get("cnns", {}).items():
        if str(cnn_name).startswith("$") or cnn_name == "none" or not isinstance(cnn, dict):
            continue
        for path_field, path_value, expected_sha in checkpoint_specs(cnn):
            for token in (str(cnn_name), path_field, path_value, str(expected_sha)):
                if token not in text:
                    failures.append(
                        "docs/PRODUCTION_ARTIFACTS.md missing registry artifact "
                        f"token {token!r} for {cnn_name}"
                    )


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


def require_check_command_paths(
    label: str,
    checks: list[Any],
    tracked: set[str],
    failures: list[str],
) -> None:
    """Ensure release-check command strings cannot reference missing repo files."""
    path_prefixes = ("tools/", "tests/", "docs/", ".github/", "source/")
    for check in checks:
        if not isinstance(check, str):
            failures.append(f"{label} entries must be strings")
            continue
        try:
            tokens = shlex.split(check)
        except ValueError as exc:
            failures.append(f"{label} command is not shell-parseable: {check!r}: {exc}")
            continue
        for token in tokens:
            if not token.startswith(path_prefixes):
                continue
            path = ROOT / token
            if not path.exists():
                failures.append(f"{label} command references missing repo path: {check!r} -> {token}")
            elif token not in tracked:
                failures.append(f"{label} command references untracked repo path: {check!r} -> {token}")


def require_artifact_ref(entry_id: str, key: str, ref: str, failures: list[str]) -> None:
    if not ref.startswith("artifacts/"):
        failures.append(f"{entry_id}: {key} must be under artifacts/: {ref}")
        return
    path = Path(ref)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        failures.append(f"{entry_id}: malformed {key} artifact path: {ref}")
    if len(path.parts) < 2:
        failures.append(f"{entry_id}: {key} artifact path must name a receipt: {ref}")


def ids_by_section(manifest: dict[str, Any], section: str, failures: list[str]) -> set[str]:
    rows = manifest.get(section)
    if not isinstance(rows, list):
        failures.append(f"{section} must be a list before product_pillars can reference it")
        return set()
    ids: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            ids.add(row["id"])
    return ids


def require_product_pillars_contract(manifest: dict[str, Any], failures: list[str]) -> None:
    pillars = manifest.get("product_pillars")
    if not isinstance(pillars, list):
        failures.append("manifest product_pillars must be a list")
        return
    by_id = {str(row.get("id")): row for row in pillars if isinstance(row, dict)}
    missing = set(REQUIRED_PRODUCT_PILLARS) - set(by_id)
    extra = set(by_id) - set(REQUIRED_PRODUCT_PILLARS)
    if missing:
        failures.append("manifest product_pillars missing ids: " + ", ".join(sorted(missing)))
    if extra:
        failures.append("manifest product_pillars has unexpected ids: " + ", ".join(sorted(extra)))

    section_ids = {
        section: ids_by_section(manifest, section, failures)
        for section in ("production_paths", "raw_targets", "platform_performance", "dashboards")
    }
    for pillar_id, spec in REQUIRED_PRODUCT_PILLARS.items():
        row = by_id.get(pillar_id)
        if not isinstance(row, dict):
            continue
        if row.get("release_label") != spec["label"]:
            failures.append(f"product_pillars.{pillar_id}: release_label must be {spec['label']!r}")
        if row.get("status") != spec["status"]:
            failures.append(f"product_pillars.{pillar_id}: status must be {spec['status']!r}")
        summary = str(row.get("summary", ""))
        open_gate = str(row.get("open_gate", ""))
        for token in spec["tokens"]:
            if token not in summary and token not in open_gate:
                failures.append(f"product_pillars.{pillar_id}: missing required token {token!r}")
        refs = row.get("manifest_refs")
        if not isinstance(refs, dict):
            failures.append(f"product_pillars.{pillar_id}: manifest_refs must be an object")
            continue
        for section, required_ids in spec["refs"].items():
            values = refs.get(section)
            if not isinstance(values, list):
                failures.append(f"product_pillars.{pillar_id}: manifest_refs.{section} must be a list")
                continue
            value_set = {str(value) for value in values}
            missing_refs = set(required_ids) - value_set
            if missing_refs:
                failures.append(
                    f"product_pillars.{pillar_id}: manifest_refs.{section} missing "
                    + ", ".join(sorted(missing_refs))
                )
            unknown_refs = value_set - section_ids.get(section, set())
            if unknown_refs:
                failures.append(
                    f"product_pillars.{pillar_id}: manifest_refs.{section} references unknown ids "
                    + ", ".join(sorted(unknown_refs))
                )
        if pillar_id == "raw_video_reconstruction":
            dashboards = refs.get("dashboards", [])
            dash_by_id = {
                str(row.get("id")): row
                for row in manifest.get("dashboards", [])
                if isinstance(row, dict)
            }
            for dashboard_id in dashboards if isinstance(dashboards, list) else []:
                dash = dash_by_id.get(str(dashboard_id))
                if isinstance(dash, dict) and dash.get("family") == "raw_video_psf":
                    failures.append(
                        "raw_video_reconstruction production refs must not point "
                        f"at raw_video_psf research dashboard {dashboard_id!r}"
                    )


def require_optional_research_refs(manifest: dict[str, Any], failures: list[str]) -> None:
    refs = manifest.get("optional_research_refs")
    if not isinstance(refs, dict):
        failures.append("manifest optional_research_refs must be an object")
        return
    dashboard_ids = ids_by_section(manifest, "dashboards", failures)
    for group_id, spec in OPTIONAL_RESEARCH_REFS.items():
        group = refs.get(group_id)
        if not isinstance(group, dict):
            failures.append(f"optional_research_refs missing group {group_id!r}")
            continue
        scope = str(group.get("scope", ""))
        for token in spec["scope_tokens"]:
            if token not in scope:
                failures.append(f"optional_research_refs.{group_id}.scope missing token {token!r}")
        dashboards = group.get("dashboards")
        if not isinstance(dashboards, list):
            failures.append(f"optional_research_refs.{group_id}.dashboards must be a list")
            continue
        dashboard_set = {str(item) for item in dashboards}
        missing = spec["dashboards"] - dashboard_set
        if missing:
            failures.append(
                f"optional_research_refs.{group_id}.dashboards missing "
                + ", ".join(sorted(missing))
            )
        unknown = dashboard_set - dashboard_ids
        if unknown:
            failures.append(
                f"optional_research_refs.{group_id}.dashboards references unknown ids "
                + ", ".join(sorted(unknown))
            )


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

    if entry_id == "premium_still_sr_experiment_scoreboard_20260701":
        if entry.get("status") != "diagnostic":
            failures.append(f"{entry_id}: premium still-SR scoreboard must remain diagnostic until promoted")
        metrics = entry.get("metrics")
        if not isinstance(metrics, dict):
            failures.append(f"{entry_id}: premium still-SR scoreboard needs metrics")
        else:
            expected_metrics = {
                "receipt_count": 82,
                "runtime_safe_candidate_count": 82,
                "promotable_candidate_count": 0,
                "promotion_threshold_pct": 15.0,
                "production_ready": 0,
            }
            for key, expected in expected_metrics.items():
                if metrics.get(key) != expected:
                    failures.append(f"{entry_id}: metric {key} must stay {expected!r}")
            try:
                mae = float(metrics.get("best_runtime_safe_holdout_mae_recovery_pct"))
                rmse = float(metrics.get("best_runtime_safe_holdout_rmse_recovery_pct"))
            except (TypeError, ValueError):
                failures.append(f"{entry_id}: best runtime-safe MAE/RMSE metrics must be numeric")
            else:
                if abs(mae - 4.031355420019811) > 1e-9:
                    failures.append(f"{entry_id}: best runtime-safe MAE recovery drifted")
                if abs(rmse - 3.753504206299621) > 1e-9:
                    failures.append(f"{entry_id}: best runtime-safe RMSE recovery drifted")
            try:
                latest_mae = float(metrics.get("latest_full_window_attention_holdout_mae_recovery_pct"))
                latest_rmse = float(metrics.get("latest_full_window_attention_holdout_rmse_recovery_pct"))
                latest_seconds = float(metrics.get("latest_full_window_attention_train_seconds"))
            except (TypeError, ValueError):
                failures.append(f"{entry_id}: latest full-window-attention metrics must be numeric")
            else:
                if abs(latest_mae - (-0.029526052219816575)) > 1e-9:
                    failures.append(f"{entry_id}: latest full-window-attention MAE recovery drifted")
                if abs(latest_rmse - (-0.09789250498606653)) > 1e-9:
                    failures.append(f"{entry_id}: latest full-window-attention RMSE recovery drifted")
                if abs(latest_seconds - 31155.659887040965) > 1e-6:
                    failures.append(f"{entry_id}: latest full-window-attention train seconds drifted")
        hashes = entry.get("hashes")
        if not isinstance(hashes, dict):
            failures.append(f"{entry_id}: premium still-SR scoreboard needs hashes")
        else:
            expected_hashes = {
                "scoreboard_json_sha256": "24388bc1b7b162535fb3e2010c0b1b05b189793cb314baf9e2ecd8a55a7ecac3",
                "dashboard_sha256": "03118e71867c43efa7f84df9fd485f20df8fcd7789d73999027efd9abf762313",
            }
            for key, expected in expected_hashes.items():
                if hashes.get(key) != expected:
                    failures.append(f"{entry_id}: hash {key} must stay {expected}")
        readme_text = README.read_text(encoding="utf-8")
        readme_plain = re.sub(r"[*_`]", "", readme_text)
        for token in ("82-receipt experiment scoreboard", "82 runtime-safe"):
            if token not in readme_plain:
                failures.append(f"{entry_id}: README missing current premium still-SR token {token!r}")

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
            target_fps = float(target.get("target_fps"))
            p95_target_ms = float(target.get("p95_target_ms"))
            fps = float(target.get("pi5_fps_median"))
            p95_ms = float(target.get("pi5_p95_ms"))
        except (TypeError, ValueError):
            failures.append(
                f"{target_id}: live-capable raw targets need target_fps, p95_target_ms, "
                "pi5_fps_median, and pi5_p95_ms"
            )
        else:
            if fps < target_fps or p95_ms >= p95_target_ms:
                failures.append(
                    f"{target_id}: live-capable raw target must clear {target_fps:g} fps / "
                    f"{p95_target_ms:g} ms p95 on Pi 5"
                )

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

    if classification == "camera-mvp-stand-in":
        detail = str(target.get("classification_detail", "")).lower()
        for required in ("pi 5 stand-in", "not actual mission 1 camera"):
            if required not in detail:
                failures.append(f"{target_id}: camera MVP stand-in detail must say {required}")
        try:
            target_fps = float(target.get("target_fps"))
            wall_fps = float(target.get("pi5_wall_fps"))
            median_fps = float(target.get("pi5_fps_median"))
            frames = int(target.get("frame_count"))
        except (TypeError, ValueError):
            failures.append(
                f"{target_id}: camera MVP stand-in targets need target_fps, "
                "pi5_wall_fps, pi5_fps_median, and frame_count"
            )
        else:
            if target_fps < 20.0:
                failures.append(f"{target_id}: camera MVP stand-in target_fps must be at least 20")
            if wall_fps < target_fps or median_fps < target_fps:
                failures.append(f"{target_id}: camera MVP stand-in must clear target_fps by wall and median fps")
            if frames < 1000:
                failures.append(f"{target_id}: camera MVP stand-in receipt must cover at least 1000 frames")
        if target.get("valid_gvid") is not True:
            failures.append(f"{target_id}: camera MVP stand-in must validate .gvid output")
        if target.get("zero_drops") is not True:
            failures.append(f"{target_id}: camera MVP stand-in must record zero drops")
        if target.get("lexar_silver_plus_budget_pass") is not True:
            failures.append(f"{target_id}: camera MVP stand-in must fit the Lexar SILVER PLUS budget")
        if target.get("camera_role_production_evidence") is not False:
            failures.append(f"{target_id}: camera MVP stand-in must not claim actual camera-role evidence")

    if classification == "preview-capable":
        try:
            passing = int(target.get("proxy_rows_passing"))
            total = int(target.get("proxy_rows_total"))
        except (TypeError, ValueError):
            failures.append(f"{target_id}: preview-capable raw targets need proxy_rows_passing/proxy_rows_total")
        else:
            if total <= 0 or passing < total:
                failures.append(f"{target_id}: preview-capable raw target must pass every proxy row")

    if classification == "offline-production":
        detail = str(target.get("classification_detail", "")).lower()
        if "not a live-camera path" not in detail:
            failures.append(f"{target_id}: offline-production raw target must say it is not a live-camera path")

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
    if entry_id != "preview_live_mission1_1024":
        return

    if entry.get("status") != "production-pass-external-receipt":
        failures.append(f"{entry_id}: bounded live PREVIEW must use external receipt status")
    if entry.get("family") != "preview" or entry.get("ship_class") != "PREVIEW":
        failures.append(f"{entry_id}: bounded live PREVIEW must stay in PREVIEW family/class")
    if entry.get("raw_target") != "mission1_preview_1024":
        failures.append(f"{entry_id}: live PREVIEW must use mission1_preview_1024")
    if entry.get("policy") != "preview_live_mission1_1024_v1":
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
                "raw_target": "mission1_preview_1024",
                "source_codec": "mission1_native12_gvid",
                "display_mode": "full_frame_downsample",
                "edge_inset_px": 0,
                "forbids_ref_content": True,
            }
            for key, expected in expected_policy.items():
                if policy.get(key) != expected:
                    failures.append(f"{entry_id}: policy {key} {policy.get(key)!r} != {expected!r}")
            viewport = policy.get("display_viewport")
            if viewport != {"x": 0, "y": 0, "width": 1024, "height": 768}:
                failures.append(f"{entry_id}: policy viewport mismatch: {viewport!r}")

    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        failures.append(f"{entry_id}: bounded live PREVIEW needs metrics")
        return
    try:
        source_width = int(metrics.get("source_width"))
        source_height = int(metrics.get("source_height"))
        preview_width = int(metrics.get("preview_width"))
        preview_height = int(metrics.get("preview_height"))
        frames = int(metrics.get("frames"))
        whole_run_fps = float(metrics.get("whole_run_fps"))
        decode_fps = float(metrics.get("decode_plus_target_fps_median"))
        target_fps = float(metrics.get("target_fps"))
    except (TypeError, ValueError):
        failures.append(f"{entry_id}: bounded live PREVIEW metrics must be numeric")
        return
    if (source_width, source_height, preview_width, preview_height) != (4096, 3072, 1024, 768):
        failures.append(f"{entry_id}: Mission preview dimensions drifted")
    if frames < 1000:
        failures.append(f"{entry_id}: Mission preview receipt must cover a sustained run")
    if whole_run_fps < target_fps or decode_fps < target_fps:
        failures.append(f"{entry_id}: Mission preview must clear its target fps")

    constraints = "\n".join(str(item).lower() for item in entry.get("constraints", []))
    for required in ("no ref", "1024 x 768", "ui/display handoff"):
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


def require_gvid_container_contract(entry: dict[str, Any], tracked: set[str], failures: list[str]) -> None:
    entry_id = str(entry.get("id", ""))
    if entry_id != "gvid_container":
        return

    if entry.get("status") != "production-supported":
        failures.append(f"{entry_id}: .gvid container must remain production-supported or be explicitly downgraded")
    if entry.get("family") != "container":
        failures.append(f"{entry_id}: .gvid container must stay in container family")

    docs = entry.get("docs") if isinstance(entry.get("docs"), list) else []
    tools = entry.get("tools") if isinstance(entry.get("tools"), list) else []
    for required_doc in (
        "docs/GVID_METADATA_DISPATCH_2026-06-04.md",
        "docs/GVID_RENDER_INPUT_2026-06-04.md",
    ):
        if required_doc not in docs:
            failures.append(f"{entry_id}: docs must include {required_doc}")
    for required_tool in (
        "tools/gvid_pack.py",
        "tools/gvid_metadata.py",
        "tools/test/test_gvid_pack.sh",
        "tools/test/test_gvid_metadata.sh",
        "tools/test/test_gpr2prores_gvid_input.sh",
    ):
        if required_tool not in tools:
            failures.append(f"{entry_id}: tools must include {required_tool}")

    render_doc = ROOT / "docs/GVID_RENDER_INPUT_2026-06-04.md"
    if "docs/GVID_RENDER_INPUT_2026-06-04.md" in tracked and render_doc.exists():
        text = render_doc.read_text(encoding="utf-8", errors="ignore")
        for token in (
            "accepted as an input format",
            "honored explicitly",
            "--gvid-dispatch <plan.json>",
            "Scripted local smoke",
            "tools/test/test_gpr2prores_gvid_input.sh",
        ):
            if token not in text:
                failures.append(f"{entry_id}: render-input doc missing {token!r}")

    receipts = "\n".join(str(item) for item in entry.get("external_receipts", []))
    for token in (
        ".gvid",
        "summary.json",
        "gvid_runtime_dispatch",
    ):
        if token not in receipts:
            failures.append(f"{entry_id}: external receipts missing {token!r}")


def require_still_metrics_contract(entry: dict[str, Any], run: dict[str, Any], failures: list[str]) -> None:
    entry_id = str(entry.get("id", ""))
    if entry.get("family") != "stills":
        return
    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        failures.append(f"{entry_id}: still production entries need compact metrics")
        return
    images = run.get("images")
    if not isinstance(images, dict) or not images:
        failures.append(f"{entry_id}: still run must contain image metrics")
        return
    enc_bytes = []
    lpips = []
    ms_ssim = []
    y_psnr = []
    de2000 = []
    for image_id, image in images.items():
        if not isinstance(image, dict):
            failures.append(f"{entry_id}: still image row {image_id!r} must be an object")
            continue
        try:
            enc_bytes.append(float(image["enc_bytes"]))
            lpips.append(float(image["lpips"]))
            ms_ssim.append(float(image["ms_ssim"]))
            y_psnr.append(float(image["y_psnr"]))
            de2000.append(float(image["dE2000_mean"]))
        except (KeyError, TypeError, ValueError):
            failures.append(f"{entry_id}: still image row {image_id!r} missing numeric size/quality metrics")
    if not enc_bytes or not lpips or not ms_ssim or not y_psnr or not de2000:
        return

    actual = {
        "image_count": float(len(images)),
        "mean_mb": sum(enc_bytes) / len(enc_bytes) / 1e6,
        "min_mb": min(enc_bytes) / 1e6,
        "max_mb": max(enc_bytes) / 1e6,
        "worst_lpips": max(lpips),
        "min_ms_ssim": min(ms_ssim),
        "min_y_psnr": min(y_psnr),
        "max_dE2000": max(de2000),
    }
    tolerances = {
        "image_count": 0.0,
        "mean_mb": 0.002,
        "min_mb": 0.002,
        "max_mb": 0.002,
        "worst_lpips": 0.0002,
        "min_ms_ssim": 0.0002,
        "min_y_psnr": 0.02,
        "max_dE2000": 0.02,
    }
    for key, expected in metrics.items():
        if key not in actual:
            failures.append(f"{entry_id}: unknown still metric {key!r}")
            continue
        try:
            expected_f = float(expected)
        except (TypeError, ValueError):
            failures.append(f"{entry_id}: still metric {key} must be numeric")
            continue
        if abs(expected_f - actual[key]) > tolerances[key]:
            failures.append(
                f"{entry_id}: still metric {key} drifted "
                f"manifest={expected_f:.4f} run={actual[key]:.4f}"
            )

    if actual["image_count"] < 4:
        failures.append(f"{entry_id}: still gate must cover at least 4 images")
    if actual["worst_lpips"] > 0.05:
        failures.append(f"{entry_id}: still worst_lpips exceeds STILL gate")
    if actual["min_ms_ssim"] < 0.99:
        failures.append(f"{entry_id}: still min_ms_ssim below production floor")
    if actual["min_y_psnr"] < 40.0:
        failures.append(f"{entry_id}: still min_y_psnr below production floor")
    if actual["max_dE2000"] > 3.0:
        failures.append(f"{entry_id}: still max_dE2000 exceeds color guardrail")


def require_registry_ship_pipeline_coverage(
    production_paths: list[dict[str, Any]],
    pipelines: dict[str, Any],
    failures: list[str],
) -> None:
    manifest_by_pipeline = {
        entry.get("pipeline"): entry
        for entry in production_paths
        if isinstance(entry.get("pipeline"), str)
    }
    for pipeline_name, pipeline in pipelines.items():
        if not isinstance(pipeline, dict):
            continue
        role = str(pipeline.get("$role", ""))
        if not role.startswith("ship-"):
            continue
        entry = manifest_by_pipeline.get(pipeline_name)
        if not entry:
            failures.append(f"registry ship pipeline missing from release manifest: {role} ({pipeline_name})")
            continue
        entry_id = str(entry.get("id", ""))
        status = entry.get("status")
        if status not in PRODUCTION_STATUSES:
            failures.append(f"{entry_id}: registry ship pipeline must have production status, got {status!r}")
        if entry.get("ship_class") != pipeline.get("ship_class"):
            failures.append(
                f"{entry_id}: manifest ship_class {entry.get('ship_class')!r} "
                f"!= registry ship_class {pipeline.get('ship_class')!r}"
            )
        if not entry.get("committed_run_hash") and not entry.get("external_receipt"):
            failures.append(f"{entry_id}: registry ship pipeline needs committed_run_hash or external_receipt")


def main() -> int:
    failures: list[str] = []
    manifest = load_json(MANIFEST)
    registry = load_json(REGISTRY)
    pipelines = registry.get("pipelines") or {}
    tracked = tracked_paths()
    require_readme_contract(tracked, failures)
    require_production_artifacts_contract(registry, tracked, failures)

    if manifest.get("schema") != EXPECTED_SCHEMA:
        failures.append(f"schema must be {EXPECTED_SCHEMA}")
    require_manifest_freshness(manifest, failures)
    require_product_pillars_contract(manifest, failures)
    require_optional_research_refs(manifest, failures)

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
                require_still_metrics_contract(entry, run, failures)

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
        require_gvid_container_contract(entry, tracked, failures)
        require_tracked_refs(entry_id, entry, tracked, failures)

    missing_output_ids = REQUIRED_OUTPUT_IDS - seen_output_ids
    if missing_output_ids:
        failures.append("manifest missing output ids: " + ", ".join(sorted(missing_output_ids)))
    require_registry_ship_pipeline_coverage(production_paths, pipelines, failures)

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

    release_checks_obj = manifest.get("release_checks")
    if not isinstance(release_checks_obj, list):
        failures.append("release_checks must be a list")
        release_checks = []
    else:
        release_checks = release_checks_obj
    release_check_text = "\n".join(str(item) for item in release_checks)
    for required in REQUIRED_RELEASE_CHECKS:
        if required not in release_check_text:
            failures.append(f"release_checks missing {required}")
    require_check_command_paths("release_checks", release_checks, tracked, failures)

    ci_checks_obj = manifest.get("ci_checks")
    if not isinstance(ci_checks_obj, list):
        failures.append("ci_checks must be a list")
        ci_checks = []
    else:
        ci_checks = ci_checks_obj
    ci_check_text = "\n".join(str(item) for item in ci_checks)
    for required in REQUIRED_CI_CHECKS:
        if required not in ci_check_text:
            failures.append(f"ci_checks missing {required}")
    require_check_command_paths("ci_checks", ci_checks, tracked, failures)
    release_check_set = {item for item in release_checks if isinstance(item, str)}
    for check in ci_checks:
        if not isinstance(check, str):
            failures.append("ci_checks entries must be strings")
            continue
        if check not in release_check_set:
            failures.append(f"ci_checks entry is not also a release_check: {check!r}")
    for check in EXTERNAL_RELEASE_ONLY_CHECKS:
        if check in ci_check_text:
            failures.append(f"external-artifact release check must not be listed as CI-safe: {check}")

    blocked_checks_obj = manifest.get("blocked_release_checks")
    if not isinstance(blocked_checks_obj, list):
        failures.append("blocked_release_checks must be a list")
        blocked_checks = []
    else:
        blocked_checks = blocked_checks_obj
    blocked_check_text = "\n".join(str(item) for item in blocked_checks)
    for required in REQUIRED_BLOCKED_RELEASE_CHECKS:
        if required not in blocked_check_text:
            failures.append(f"blocked_release_checks missing {required}")
    require_check_command_paths("blocked_release_checks", blocked_checks, tracked, failures)
    for check in blocked_checks:
        if not isinstance(check, str):
            failures.append("blocked_release_checks entries must be strings")
            continue
        if check in release_check_text:
            failures.append(f"blocked release check must not be listed as passing release_check: {check}")
        if check in ci_check_text:
            failures.append(f"blocked release check must not be listed as CI-safe: {check}")

    if CI_WORKFLOW.exists():
        workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
        for check in ci_checks:
            if isinstance(check, str) and check not in workflow_text:
                failures.append(f"CI workflow missing ci_checks command {check!r}")
    else:
        failures.append(".github/workflows/ci.yml is missing")

    if RELEASE_READINESS.exists():
        release_text = RELEASE_READINESS.read_text(encoding="utf-8")
        for check in release_checks:
            if not isinstance(check, str):
                failures.append("release_checks entries must be strings")
                continue
            if check not in release_text:
                failures.append(f"docs/RELEASE_READINESS.md quick checks missing release check {check!r}")
        for check in blocked_checks:
            if isinstance(check, str) and check not in release_text:
                failures.append(
                    f"docs/RELEASE_READINESS.md quick checks missing blocked release check {check!r}"
                )
    else:
        failures.append("docs/RELEASE_READINESS.md is missing")

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
