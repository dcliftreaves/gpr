#!/usr/bin/env python3
"""Validate the README's four-pillar product framing.

The README is the public product surface. This guard keeps the high-level
story aligned with the current production scorecard so future edits do not
drop the raw-stills, raw-video, premium still/SR, or PSF-aware video goals.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SCORECARD = ROOT / "docs/PRODUCT_PILLAR_SCORECARD.md"

REQUIRED_SECTIONS = (
    "## Open Raw Video For Action Cameras",
    "## What This Branch Proves",
    "## Four Product Tracks",
    "## Product Snapshot",
    "## Product Pillars",
    "## Evidence Map",
    "## Stills Performance And CNN Latitude",
    "## Mission 1 Numbered List",
)

REQUIRED_README_TOKENS = (
    "8-bit JPEG size. 16-bit RAW quality.",
    "Current four-pillar completion is **69%**",
    "production-readiness burn-down",
    "not an image-quality score",
    "not a regression signal for locked artifacts",
    "GPR is not one codec demo",
    "The repo is organized around four product outcomes, not one benchmark",
    "outcome has a locked proof surface",
    "**Best RAW stills**",
    "**GoPro RAW video MVP**",
    "**Premium still improvement**",
    "**PSF-aware video improvement**",
    "Actual Mission 1 sensor/DMA, SD writer, and rear-display receipts",
    "A no-REF candidate that clears the 50 MP / 100 MP still/editor-latitude gate",
    "Controlled high/low Mission 1 pairs",
    "capture better raw, keep raw editable, preview it",
    "**1. RAW stills**",
    "**2. RAW video MVP**",
    "**3. Premium still improvement**",
    "**4. PSF-aware video improvement**",
    "The denominator is the full four-pillar production suite",
    "use the lock ledger for artifact stability and the scorecard for remaining production evidence",
    "For the Mission 1 raw-video loop",
    "The full",
    "four-pillar suite still has the fixture/noise, premium still-SR, and PSF gates",
    "**50 MP RAW still tiers**",
    "**4K `.gvid` capture prototype**",
    "**1024 camera-back preview**",
    "**Offline 4K cleanup and 8K SR**",
    "See [`docs/PRODUCT_LOCK_LEDGER.md`](docs/PRODUCT_LOCK_LEDGER.md)",
    "**1. Best RAW stills**",
    "**2. GoPro RAW video MVP**",
    "**3. Premium still/SR**",
    "**4. PSF-aware video/SR**",
    "50 MP and 100 MP-class cameras",
    "normal CFA support",
    "camera-noise-aware compression",
    "4096 x 3072 Bayer",
    ".gvid",
    "20+ fps",
    "1024 x 768",
    "Mission 1 sensor/DMA",
    "raw-CFA targets",
    "13-scene / 351-row",
    "PSF-conditioned model",
    "Controlled high/low pairs",
    "decoded Bayer hashes",
    "docs/PRODUCT_PILLAR_SCORECARD.md",
    "docs/PRODUCT_LOCK_LEDGER.md",
    "docs/WORKSPACE_AND_ARTIFACT_MAP.md",
    "docs/BIG_EFFORTS_STATUS.md",
    "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md",
    "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md",
    "docs/SHIP_DECISION.md",
    "docs/CAMERA_NOISE_CALIBRATION.md",
    "docs/VIDEO_STATUS.md",
    "docs/GOPRO_MISSION1_QUICK_VALIDATION.md",
    "docs/PREMIUM_STILL_SR.md",
    "docs/BAYER_RESIZE_PSF.md",
    "premium_still_sr_next_experiment_contract_20260630",
    "z8_continuous_8k_no_cnn_vs_cnn_20260630",
    "Open the separate standalone ProRes movies, not a dashboard",
    "z8_24f_true_no_cnn_4k_raw_lanczos_to_8k_20p_prores.mov",
    "z8_24f_with_4k_cleanup_and_8k_sr_cnn_20p_prores.mov",
    "both movies are 8280 x 5520 ProRes, 24 matched frames at 20 fps",
    "Mission 1 broad sequence",
    "mission1_8k_true_no_cnn_vs_cnn_20260630",
    "mission42_true_no_cnn_4k_raw_lanczos_to_8k_42f_20p_prores.mov",
    "mission42_with_4k_cleanup_and_8k_sr_cnn_42f_20p_prores.mov",
    "both movies are 8192 x 6144 ProRes, 42 frames at 20 fps",
    "Mission 1 strict sequential scene",
    "mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630",
    "GP017497_508_true_no_cnn_8k_12f_20p_prores.mov",
    "GP017497_508_with_4k_cleanup_8k_sr_cnn_12f_20p_prores.mov",
    "12 sequential frames at 20 fps",
    "Production capture requirements",
    "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json",
    "real fixtures, darkframes, camera receipts, PSF pairs, and model-promotion receipts",
)

FORBIDDEN_README_TOKENS = (
    # This folder contains a dashboard/contact-sheet movie, not the requested
    # continuous scene-video comparison. Keep it out of the public evidence map.
    "mission1_8k_sr_with_without_cnn_review_20260630",
    "mission1_8k_sr_with_without_cnn_contact_review_42f_prores.mov",
    # This older artifact isolates only the 8K SR stage from an already-cleaned
    # 4K CNN input, so it is not the top-level no-CNN comparison reviewers ask
    # for in the public README.
    "mission1_8k_continuous_cnn_ab_20260630",
)

EXPECTED_PERCENTAGES = {
    "Best RAW stills": 90,
    "GoPro RAW video MVP": 80,
    "Premium still/SR": 60,
    "RAW video PSF/SR improvement": 44,
}

REQUIRED_SCORECARD_TOKENS = (
    "| Best RAW stills | 90% |",
    "| GoPro RAW video MVP | 80% |",
    "| Premium still/SR | 60% |",
    "| PSF-aware RAW video improvement | 44% |",
    "The percentages are production-readiness burn-down estimates.",
    "not regression signals for locked artifacts",
    "candidate-only patch-dictionary retrieval pass regresses the hard X2D holdout",
    "Current candidate-only local/full-crop/global-context statistics are not enough for simple CNN or nearest-neighbor transfer",
    "deeper gated pyramid U-Net",
    "premium_still_sr_patch_dictionary_x2dholdout_20260630/patch_dictionary_probe.json",
)


def require_tokens(text: str, tokens: tuple[str, ...], label: str, failures: list[str]) -> None:
    for token in tokens:
        if token not in text:
            failures.append(f"{label} missing {token!r}")


def extract_done_percent(readme: str, pillar: str) -> int | None:
    pattern = re.compile(rf"\|\s*{re.escape(pillar)}\s*\|\s*\*\*(\d+)%\*\*")
    match = pattern.search(readme)
    if not match:
        return None
    return int(match.group(1))


def validate(readme_path: Path = README, scorecard_path: Path = SCORECARD) -> list[str]:
    failures: list[str] = []
    if not readme_path.exists():
        return [f"{readme_path} is missing"]
    readme = readme_path.read_text(encoding="utf-8")

    require_tokens(readme, REQUIRED_SECTIONS, readme_path.name, failures)
    require_tokens(readme, REQUIRED_README_TOKENS, readme_path.name, failures)
    for token in FORBIDDEN_README_TOKENS:
        if token in readme:
            failures.append(f"{readme_path.name} must not reference rejected or superseded artifact {token!r}")

    for pillar, expected in EXPECTED_PERCENTAGES.items():
        actual = extract_done_percent(readme, pillar)
        if actual is None:
            failures.append(f"README.md missing percentage row for {pillar!r}")
        elif actual != expected:
            failures.append(
                f"README.md percentage for {pillar!r} is {actual}%, expected {expected}%"
            )

    if scorecard_path.exists():
        scorecard = scorecard_path.read_text(encoding="utf-8")
        require_tokens(scorecard, REQUIRED_SCORECARD_TOKENS, scorecard_path.name, failures)
    else:
        failures.append(f"{scorecard_path} is missing")

    lock_ledger = readme_path.parent / "docs" / "PRODUCT_LOCK_LEDGER.md"
    if lock_ledger.exists():
        ledger = lock_ledger.read_text(encoding="utf-8")
        require_tokens(
            ledger,
            (
                "a locked path regresses only when its own committed gate",
                "## Locked Paths",
                "## Open Production Gates",
                "Mission 1 4K cleanup",
                "Mission 1 8K SR",
                "Mission 1 Pi stand-in raw-video encode",
                "Real Mission 1 camera-role raw-video closure",
                "Premium still-SR promotion",
                "PSF-aware raw-video replacement",
            ),
            lock_ledger.name,
            failures,
        )
    else:
        failures.append(f"{lock_ledger} is missing")

    return failures


def main() -> int:
    failures = validate()
    if failures:
        print("README product-pillar check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("OK - README product-pillar check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
