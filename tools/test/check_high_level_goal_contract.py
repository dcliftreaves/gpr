#!/usr/bin/env python3
"""Validate the high-level four-pillar production goal docs."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
BIG_EFFORTS = ROOT / "docs/BIG_EFFORTS_STATUS.md"
PLAN = ROOT / "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md"


DOC_TOKENS = {
    "README.md": (
        "Open Raw Video For Action Cameras",
        "8-bit JPEG size. 16-bit RAW quality.",
        "The denominator is the full four-pillar production suite",
        "**1. Best RAW stills**",
        "**2. GoPro RAW video MVP**",
        "**3. Premium still/SR**",
        "**4. PSF-aware video/SR**",
    ),
    "docs/BIG_EFFORTS_STATUS.md": (
        "Raw stills for 50 MP / 100 MP cameras",
        "Raw video MVP for GoPro / Mission 1",
        "Raw stills improvement / expensive SR",
        "Raw video improvement / PSF-aware Bayer resize",
        "normal unpacked 2x2 Bayer",
        "camera-noise coverage audit",
        "real sensor/DMA",
        "no-REF",
        "PSF-conditioned",
        "controlled high/low pairs",
    ),
    "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md": (
        "Raw stills pass committed gates",
        "50 MP / 100 MP camera",
        "Raw video has a GoPro/Mission 1 MVP path",
        "Offline premium still improvement has a dedicated still-SR gate",
        "Raw video improvement has PSF/blur-aware 4K cleanup",
        "8K reconstruction",
        "Execution Split",
        "Can advance locally without new captures",
        "Requires new hardware or new samples before it can close",
        "The next local work should therefore default to premium still-SR and",
        "camera access",
        "noise calibration uncertainty",
        "PSF mismatch",
        "throughput, memory, or storage",
    ),
}


def path_for(label: str) -> Path:
    if label == "README.md":
        return README
    if label == "docs/BIG_EFFORTS_STATUS.md":
        return BIG_EFFORTS
    if label == "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md":
        return PLAN
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
