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
GOAL_CLOSURE = ROOT / "docs/GOAL_CLOSURE_MATRIX.md"
PRODUCTION_100 = ROOT / "docs/PRODUCTION_100_PERCENT_PLAN.md"


DOC_TOKENS = {
    "README.md": (
        "Open Raw Video For Action Cameras",
        "8-bit JPEG size. 16-bit RAW quality.",
        "docs/GOAL_CLOSURE_MATRIX.md",
        "docs/PRODUCTION_100_PERCENT_PLAN.md",
        "The denominator is the shippable production suite",
        "**1. Best RAW stills**",
        "**2. GoPro RAW video MVP**",
        "**3. Premium still/SR**",
        "**4. Raw video reconstruction improvement**",
        "PSF-aware video/SR remains optional research",
        "Current action stack",
        "Do not reopen approved raw-video SR",
        "no-REF 50 MP / 100 MP promotion preflight",
    ),
    "docs/BIG_EFFORTS_STATUS.md": (
        "GOAL_CLOSURE_MATRIX.md",
        "Raw stills for 50 MP / 100 MP cameras",
        "Raw video MVP for GoPro / Mission 1",
        "Raw stills improvement / expensive SR",
        "Raw video reconstruction improvement",
        "Shippable offline/post path",
        "normal unpacked 2x2 Bayer",
        "camera-noise coverage audit",
        "real sensor/DMA",
        "no-REF",
        "124-receipt experiment scoreboard",
        "124 runtime-safe",
        "Frequency-pyramid is blocked",
        "gated no-op residual",
        "masked-detail/no-op",
        "positive held-out recovery",
        "optional research",
    ),
    "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md": (
        "GOAL_CLOSURE_MATRIX.md",
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
        "release hygiene, camera-role handoff docs, noise",
        "sidecar closure, and premium still-SR promotion outrank another video-SR",
        "Execution Split",
        "Can advance locally without new captures",
        "Requires new hardware or new samples before it can close",
        "The next local work should therefore default to premium still-SR and",
        "Current Action Stack",
        "Protect the locked release paths",
        "Mission 1 camera-role validation",
        "no-REF 50 MP / 100 MP promotion preflight",
        "same `.gvid`, editable raw",
        "ProRes, dashboard, timing, memory, and hash receipt surface",
        "darkframe_provenance_review_packet_100_percent_20260702",
        "source_provenance_manifest_templates",
        "production_sidecar_ready=false",
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
    "docs/GOAL_CLOSURE_MATRIX.md": (
        "High-Level Goal Closure Matrix",
        "PRODUCTION_100_PERCENT_PLAN.md",
        "Raw stills for 50 MP / 100 MP cameras",
        "GoPro RAW video MVP",
        "Premium still/SR",
        "Raw video reconstruction / PSF-aware improvement",
        "What Would Make The Whole Goal Complete",
        "Mission 1 and iPhone strict-provenance darkframe sidecars",
        "Actual Mission 1 camera-role receipts",
        "A no-REF 50 MP / 100 MP candidate",
        "15% / 15% floor",
        "PSF-conditioned models are optional replacement research",
        "Public docs are honest and useful",
        "Non-Claims",
    ),
    "docs/PRODUCTION_100_PERCENT_PLAN.md": (
        "Production 100 Percent Plan",
        "current 83 percent production-readiness estimate to 100 percent",
        "Best RAW stills",
        "GoPro RAW video MVP",
        "Premium still/SR",
        "RAW video reconstruction improvement",
        "100 Percent Gate Queue",
        "A: Premium still-SR promotion",
        "B: Mission/iPhone noise sidecars",
        "C: Mission 1 camera-role raw-video MVP",
        "D: Locked raw-video reconstruction",
        "exact next command",
        "receipt that moves the gate",
        "if Gate C cannot run because there is no real",
        "Mission 1 camera-role access, spend local compute on Gate A",
        "Do not run raw-video SR research",
        "Execution Order",
        "Premium still/SR promotion",
        "Mission/iPhone camera-noise sidecars",
        "Mission 1 camera-role raw-video closure",
        "Locked raw-video reconstruction",
        "Step 1: Premium Still/SR Promotion",
        "runtime inputs include `candidate_raw` and `camera_metadata`",
        "Runtime inputs exclude `REF`, `source_raw`, `source_rgb`, `source_hf`, JPEG/JPG targets, and gate metrics",
        "Step 2: Mission/iPhone Camera-Noise Sidecars",
        "unique provenance-ready raw hashes",
        "Step 3: Mission 1 Camera-Role Raw Video MVP",
        "120+ sustained frames",
        "Storage medium names the actual camera SD/internal writer",
        "Step 4: Protect Locked Raw-Video Reconstruction",
        "Do not run another raw-video SR experiment as production work",
        "Done Means",
        "`docs/PRODUCTION_CAPTURE_REQUIREMENTS.json` has no open release-blocking",
    ),
}

FORBIDDEN_TOKENS = {
    "README.md": (
        "PSF gates",
    ),
    "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md": (
        "PSF/blur-aware replacement work is required",
        "video-SR research pass unless a locked video-SR gate actually fails or a replacement is already better",
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
    if label == "docs/GOAL_CLOSURE_MATRIX.md":
        return GOAL_CLOSURE
    if label == "docs/PRODUCTION_100_PERCENT_PLAN.md":
        return PRODUCTION_100
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
