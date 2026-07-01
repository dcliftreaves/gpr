#!/usr/bin/env python3
"""Validate the four-pillar production burn-down contract."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from build_product_burndown import build_burndown  # noqa: E402
from build_product_pillar_scorecard import DEFAULT_EXTERNAL_ROOT  # noqa: E402


EXPECTED_PILLARS = {
    "raw_stills": {
        "readiness": 92,
        "required_actions": {
            "Add Mission 1 and iPhone darkframe sidecars": {
                "requirement_ids": ["mission1_darkframe_stack", "iphone_cfa_darkframe_stack"],
                "tokens": (
                    "Mission 1 darkframes",
                    "iPhone CFA darkframes",
                    "gpr.camera_noise_calibration.v1",
                ),
                "blocker_type": "sample_acquisition",
                "requires_mission1_camera_role": False,
                "requires_new_samples": True,
                "command_tokens": ("build_darkframe_candidate_audit.py", "build_camera_noise_calibration.py"),
            },
        },
    },
    "raw_video_mvp": {
        "readiness": 80,
        "required_actions": {
            "Replace Pi stand-in receipts with Mission 1 camera-role receipts": {
                "requirement_ids": ["mission1_camera_role_receipts"],
                "tokens": ("sensor/DMA", "SD writer", "rear-display", ".gvid"),
                "blocker_type": "hardware_integration",
                "requires_mission1_camera_role": True,
                "requires_new_samples": False,
                "command_tokens": ("run_gopro_mission1_quick_validation.py", "check_mission1_camera_closure_run.py"),
            },
        },
    },
    "premium_still_sr": {
        "readiness": 60,
        "required_actions": {
            "Promote a true raw-CFA residual still-SR model": {
                "requirement_ids": ["premium_still_sr_promotion_receipts"],
                "tokens": ("candidate-only", "Z8 held-out", "X2D held-out", "50 MP / 100 MP"),
                "blocker_type": "model_promotion",
                "requires_mission1_camera_role": False,
                "requires_new_samples": False,
                "command_tokens": ("train_premium_still_sr_raw_cfa_residual.py", "build_premium_still_sr_gate_receipt.py"),
            },
        },
    },
    "raw_video_psf_sr": {
        "readiness": 55,
        "required_actions": {
            "Capture or locate controlled Mission 1 high/low PSF pairs": {
                "requirement_ids": ["controlled_mission1_psf_pairs"],
                "tokens": (
                    "8192 x 6144 / 4096 x 3072",
                    "source hashes",
                    "decoded little-endian uint16 Bayer hashes",
                    "negative controls",
                    "stable measured native PSF kernel",
                    "model conditioning",
                ),
                "blocker_type": "sample_acquisition",
                "requires_mission1_camera_role": False,
                "requires_new_samples": True,
                "command_tokens": ("build_mission1_native_psf_pair_inventory.py", "build_mission1_native_psf_measurement.py"),
            },
            "Gate a PSF-conditioned 4K/8K video SR candidate": {
                "requirement_ids": ["controlled_mission1_psf_pairs"],
                "tokens": ("PSF-conditioned", "Mission42 and Z8 all24", "4K/8K ProRes"),
                "blocker_type": "model_promotion",
                "requires_mission1_camera_role": False,
                "requires_new_samples": False,
                "command_tokens": ("build_mission1_native_psf_measurement.py", "build_raw_video_psf_gap_plan.py"),
            },
        },
    },
}


def flatten_action(action: dict[str, Any]) -> str:
    parts: list[str] = [
        str(action.get("title", "")),
        str(action.get("owner", "")),
        str(action.get("next_command", "")),
        str(action.get("completion_gate", "")),
    ]
    parts.extend(str(item) for item in action.get("evidence_required", []))
    return "\n".join(parts)


def validate_burndown(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("schema") != "gpr.product_burndown.v1":
        failures.append(f"unexpected burn-down schema: {data.get('schema')!r}")
    if data.get("source_requirements_schema") != "gpr.production_capture_requirements.v1":
        failures.append("burn-down must source blocker IDs from PRODUCTION_CAPTURE_REQUIREMENTS.json")
    if data.get("source_requirements_path") != "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json":
        failures.append("burn-down must record docs/PRODUCTION_CAPTURE_REQUIREMENTS.json as its requirement source")
    if data.get("production_ready") is not False:
        failures.append("four-pillar burn-down must remain production_ready=false while blockers are open")
    if data.get("four_pillar_completion_percent") != 72:
        failures.append("four-pillar completion percent must stay aligned to the current 72% scorecard")

    summary = data.get("summary", {})
    if summary.get("open_requirement_count") != 5:
        failures.append("burn-down must identify the five open production capture requirements")
    if summary.get("camera_required_action_count") != 1:
        failures.append("burn-down must identify exactly one camera-required action")
    if summary.get("non_camera_action_count") != 4:
        failures.append("burn-down must identify the four non-camera actions that can continue now")
    if summary.get("mission1_camera_role_required_action_count") != 1:
        failures.append("burn-down must identify exactly one Mission 1 camera-role action")
    if summary.get("new_sample_required_action_count") != 2:
        failures.append("burn-down must identify two sample-acquisition actions")
    if summary.get("model_promotion_action_count") != 2:
        failures.append("burn-down must identify two model-promotion actions")
    expected_blockers = {
        "hardware_integration": 1,
        "model_promotion": 2,
        "sample_acquisition": 2,
    }
    if summary.get("blocker_type_counts") != expected_blockers:
        failures.append(
            f"unexpected blocker_type_counts: {summary.get('blocker_type_counts')!r}, expected {expected_blockers!r}"
        )
    if summary.get("lowest_readiness_pillar") != "raw_video_psf_sr":
        failures.append("raw_video_psf_sr should remain the lowest-readiness pillar until PSF work closes")
    expected_open_ids = [
        "mission1_darkframe_stack",
        "iphone_cfa_darkframe_stack",
        "mission1_camera_role_receipts",
        "controlled_mission1_psf_pairs",
        "premium_still_sr_promotion_receipts",
    ]
    if data.get("open_requirement_ids") != expected_open_ids:
        failures.append(f"unexpected open_requirement_ids: {data.get('open_requirement_ids')!r}")

    pillars = {str(row.get("id")): row for row in data.get("pillars", [])}
    for pillar_id, spec in EXPECTED_PILLARS.items():
        pillar = pillars.get(pillar_id)
        if not pillar:
            failures.append(f"missing pillar {pillar_id!r}")
            continue
        if pillar.get("production_ready") is not False:
            failures.append(f"{pillar_id} must not be production_ready before its blockers close")
        if pillar.get("readiness_percent") != spec["readiness"]:
            failures.append(
                f"{pillar_id} readiness is {pillar.get('readiness_percent')}, expected {spec['readiness']}"
            )
        if not str(pillar.get("current_blocker", "")).strip():
            failures.append(f"{pillar_id} must carry a current_blocker string")

        actions = {str(row.get("title")): row for row in pillar.get("burn_down_actions", [])}
        for title, action_spec in spec["required_actions"].items():
            action = actions.get(title)
            if not action:
                failures.append(f"{pillar_id} missing burn-down action {title!r}")
                continue
            if action.get("requirement_ids") != action_spec["requirement_ids"]:
                failures.append(
                    f"{title!r} requirement_ids are {action.get('requirement_ids')!r}, "
                    f"expected {action_spec['requirement_ids']!r}"
                )
            statuses = action.get("source_requirement_statuses")
            if not isinstance(statuses, dict):
                failures.append(f"{title!r} must carry source_requirement_statuses")
            else:
                for req_id in action_spec["requirement_ids"]:
                    if req_id not in statuses:
                        failures.append(f"{title!r} missing source status for {req_id!r}")
            commands = action.get("validation_commands", [])
            if not isinstance(commands, list) or not commands:
                failures.append(f"{title!r} must carry validation_commands from the committed requirement")
            command_text = "\n".join(str(command) for command in commands)
            for token in action_spec["command_tokens"]:
                if token not in command_text:
                    failures.append(f"{title!r} missing validation command token {token!r}")
            if action.get("blocker_type") != action_spec["blocker_type"]:
                failures.append(
                    f"{title!r} blocker_type is {action.get('blocker_type')!r}, expected {action_spec['blocker_type']!r}"
                )
            if action.get("requires_mission1_camera_role") is not action_spec["requires_mission1_camera_role"]:
                failures.append(
                    f"{title!r} requires_mission1_camera_role must be {action_spec['requires_mission1_camera_role']}"
                )
            if action.get("requires_new_samples") is not action_spec["requires_new_samples"]:
                failures.append(f"{title!r} requires_new_samples must be {action_spec['requires_new_samples']}")
            if not action.get("owner"):
                failures.append(f"{title!r} must name an owner")
            evidence = action.get("evidence_required", [])
            if not isinstance(evidence, list) or len(evidence) < 3:
                failures.append(f"{title!r} must require at least three evidence items")
            if not str(action.get("completion_gate", "")).strip():
                failures.append(f"{title!r} must define a completion_gate")
            text = flatten_action(action)
            for token in action_spec["tokens"]:
                if token not in text:
                    failures.append(f"{title!r} missing required blocker token {token!r}")

    raw_video_actions = pillars.get("raw_video_mvp", {}).get("burn_down_actions", [])
    if not raw_video_actions or raw_video_actions[0].get("can_do_without_camera") is not False:
        failures.append("Mission 1 camera-role closure must be explicitly marked camera-required")
    for pillar_id, pillar in pillars.items():
        if pillar_id != "raw_video_mvp":
            for action in pillar.get("burn_down_actions", []):
                if action.get("can_do_without_camera") is not True:
                    failures.append(f"{pillar_id} action {action.get('title')!r} should be non-camera work")

    return failures


def main() -> int:
    data = build_burndown(DEFAULT_EXTERNAL_ROOT)
    failures = validate_burndown(data)
    if failures:
        print("product burn-down contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("OK - product burn-down contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
