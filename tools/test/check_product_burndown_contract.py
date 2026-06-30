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
        "readiness": 90,
        "required_actions": {
            "Close real Bayer phase fixture gaps": ("GRBG", "BGGR", "still matrix"),
            "Add Mission 1 and iPhone darkframe sidecars": (
                "Mission 1 darkframes",
                "iPhone CFA darkframes",
                "gpr.camera_noise_calibration.v1",
            ),
        },
    },
    "raw_video_mvp": {
        "readiness": 80,
        "required_actions": {
            "Replace Pi stand-in receipts with Mission 1 camera-role receipts": (
                "sensor/DMA",
                "SD writer",
                "rear-display",
                ".gvid",
            ),
        },
    },
    "premium_still_sr": {
        "readiness": 60,
        "required_actions": {
            "Promote a true raw-CFA residual still-SR model": (
                "candidate-only",
                "Z8 held-out",
                "X2D held-out",
                "50 MP / 100 MP",
            ),
        },
    },
    "raw_video_psf_sr": {
        "readiness": 44,
        "required_actions": {
            "Capture or locate controlled Mission 1 high/low PSF pairs": (
                "8192 x 6144 / 4096 x 3072",
                "stable measured native PSF kernel",
                "model conditioning",
            ),
            "Gate a PSF-conditioned 4K/8K video SR candidate": (
                "PSF-conditioned",
                "Mission42 and Z8 all24",
                "4K/8K ProRes",
            ),
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
    if data.get("production_ready") is not False:
        failures.append("four-pillar burn-down must remain production_ready=false while blockers are open")
    if data.get("four_pillar_completion_percent") != 69:
        failures.append("four-pillar completion percent must stay aligned to the current 69% scorecard")

    summary = data.get("summary", {})
    if summary.get("camera_required_action_count") != 1:
        failures.append("burn-down must identify exactly one camera-required action")
    if summary.get("non_camera_action_count") != 5:
        failures.append("burn-down must identify the five non-camera actions that can continue now")
    if summary.get("lowest_readiness_pillar") != "raw_video_psf_sr":
        failures.append("raw_video_psf_sr should remain the lowest-readiness pillar until PSF work closes")

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
        for title, required_tokens in spec["required_actions"].items():
            action = actions.get(title)
            if not action:
                failures.append(f"{pillar_id} missing burn-down action {title!r}")
                continue
            if not action.get("owner"):
                failures.append(f"{title!r} must name an owner")
            evidence = action.get("evidence_required", [])
            if not isinstance(evidence, list) or len(evidence) < 3:
                failures.append(f"{title!r} must require at least three evidence items")
            if not str(action.get("completion_gate", "")).strip():
                failures.append(f"{title!r} must define a completion_gate")
            text = flatten_action(action)
            for token in required_tokens:
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
