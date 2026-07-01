#!/usr/bin/env python3
"""Validate the high-level four-pillar production goal docs."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
BIG_EFFORTS = ROOT / "docs/BIG_EFFORTS_STATUS.md"
PLAN = ROOT / "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md"
SHIP_DECISION = ROOT / "docs/SHIP_DECISION.md"


DOC_TOKENS = {
    "README.md": (
        "Open Raw Video For Action Cameras",
        "8-bit JPEG size. 16-bit RAW quality.",
        "The denominator is the shippable production suite",
        "**1. Best RAW stills**",
        "**2. GoPro RAW video MVP**",
        "**3. Premium still/SR**",
        "**4. Raw video reconstruction improvement**",
        "PSF-aware video/SR remains optional research",
    ),
    "docs/BIG_EFFORTS_STATUS.md": (
        "Raw stills for 50 MP / 100 MP cameras",
        "Raw video MVP for GoPro / Mission 1",
        "Raw stills improvement / expensive SR",
        "Raw video reconstruction improvement",
        "Shippable offline/post path",
        "normal unpacked 2x2 Bayer",
        "camera-noise coverage audit",
        "real sensor/DMA",
        "no-REF",
        "optional research",
    ),
    "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md": (
        "Raw stills pass committed gates",
        "50 MP / 100 MP camera",
        "Raw video has a GoPro/Mission 1 MVP path",
        "Offline premium still improvement has a dedicated still-SR gate",
        "Raw video reconstruction improvement ships the approved 4K cleanup",
        "reconstruction workflow",
        "optional research, not a release blocker",
        "No Infinite SR Rule",
        "SR work is not allowed to move the release target by itself.",
        "PSF/blur experiments are optional next-generation research.",
        "Execution Split",
        "Can advance locally without new captures",
        "Requires new hardware or new samples before it can close",
        "The next local work should therefore default to premium still-SR and",
        "camera access",
        "noise calibration uncertainty",
        "throughput, memory, or storage",
    ),
    "docs/SHIP_DECISION.md": (
        "Current release boundary",
        "Raw-video SR is frozen for shipment",
        "Do not keep iterating on SR just because a new",
        "experiment is plausible",
        "Reopen the raw-video SR decision only if the locked",
        "gate, artifact hash, receipt, CI guard, or manual review fails",
        "replacement has already beaten the locked baseline",
        "PSF/blur modeling is useful next-generation research",
        "not a release",
        "requirement for the current raw-video workflow",
        "future claim that a PSF-conditioned model replaces",
    ),
}

FORBIDDEN_TOKENS = {
    "README.md": (
        "PSF gates",
    ),
    "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md": (
        "PSF/blur-aware replacement work is required",
    ),
    "docs/SHIP_DECISION.md": (
        "PSF gates",
        "PSF/blur modeling is required",
        "PSF/blur modeling is a release requirement",
    ),
}


def path_for(label: str) -> Path:
    if label == "README.md":
        return README
    if label == "docs/BIG_EFFORTS_STATUS.md":
        return BIG_EFFORTS
    if label == "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md":
        return PLAN
    if label == "docs/SHIP_DECISION.md":
        return SHIP_DECISION
    raise KeyError(label)


def validate(paths: dict[str, Path] | None = None) -> list[str]:
    failures: list[str] = []
    actual_paths = paths or {label: path_for(label) for label in DOC_TOKENS}
    for label, tokens in DOC_TOKENS.items():
        path = actual_paths[label]
        if not path.exists():
            failures.append(f"{label} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                failures.append(f"{label} missing {token!r}")
        for token in FORBIDDEN_TOKENS.get(label, ()):
            if token in text:
                failures.append(f"{label} must not contain {token!r}")
    return failures


def main() -> int:
    failures = validate()
    if failures:
        print("high-level goal contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("OK - high-level goal contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
