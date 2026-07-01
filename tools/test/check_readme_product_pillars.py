#!/usr/bin/env python3
"""Validate the README's four-pillar product framing.

The README is the public product surface. This guard keeps the high-level
story aligned with the current production scorecard so future edits do not
drop the raw-stills, raw-video, premium still/SR, or raw-video reconstruction
goals.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SCORECARD = ROOT / "docs/PRODUCT_PILLAR_SCORECARD.md"
SCORECARD_BUILDER = ROOT / "tools/build_product_pillar_scorecard.py"

REQUIRED_SECTIONS = (
    "## Open Raw Video For Action Cameras",
    "## The Four Product Bets",
    "## Release Board",
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
    "![GPR four-pillar production readiness](docs/img/readme_status_matrix.svg)",
    "Current four-pillar completion is **",
    "production-readiness burn-down",
    "not an image-quality score",
    "not a regression signal for locked artifacts",
    "GPR is not one codec demo",
    "The repo is organized around four product outcomes, not one benchmark",
    "outcome has a locked proof surface",
    "**1. Better RAW stills**",
    "**2. GoPro RAW video MVP**",
    "**3. Premium still improvement**",
    "**4. RAW video reconstruction**",
    "Closed for the current offline/post release",
    "| **RAW stills** | Ship the current 50 MP still tiers and normal-Bayer support.",
    "X2D/Z8 calibrated noise addback is enabled by sidecars.",
    "Mission 1 and iPhone darkframe sidecars with strict source provenance.",
    "| **GoPro RAW video MVP** | Ship as a Labs-ready handoff package from the Pi 5 stand-in evidence.",
    "Real Mission 1 camera-role receipts for sensor/DMA input, SD write, rear display, zero drops",
    "| **Premium still/SR** | Do not ship as a promoted quality claim yet.",
    "Current CNNs are diagnostic.",
    "A no-REF 50 MP / 100 MP raw-CFA still candidate that beats the existing still baseline",
    "| **RAW video reconstruction** | Ship the approved offline/post 4K cleanup and 8K SR path now.",
    "Reopen only if a locked receipt/gate/hash/manual review fails",
    "same `.gvid`, editable raw, ProRes, dashboard, timing, memory, and hash evidence",
    "**Best RAW stills**",
    "**GoPro RAW video MVP**",
    "**Premium still improvement**",
    "**Raw video reconstruction**",
    "Actual Mission 1 sensor/DMA, SD writer, and rear-display receipts",
    "A no-REF candidate that clears the 50 MP / 100 MP still/editor-latitude gate",
    "PSF-aware video/SR is now tracked as optional next-gen research",
    "capture better raw, keep raw editable, preview it",
    "**1. RAW stills**",
    "**2. RAW video MVP**",
    "**3. Premium still improvement**",
    "**4. Raw video reconstruction improvement**",
    "The denominator is the shippable production suite",
    "Research Parking Lot",
    "outside production action counts and readiness percentages",
    "research cannot quietly become a ship blocker",
    "use the lock ledger for artifact stability and the scorecard for remaining production evidence",
    "For the Mission 1 raw-video loop",
    "The full",
    "PSF-conditioned replacement work is optional research",
    "Premium still-SR promotion is intentionally stricter than",
    "`runtime_inputs` with `candidate_raw`",
    "exclude REF/source/JPEG content at render time",
    "50 MP and 100 MP gate row counts",
    "positive median MAE reduction with nonnegative worst-row MAE",
    "seconds/frame and peak RSS",
    "exact-sidecar-only noise",
    "**50 MP RAW still tiers**",
    "**4K `.gvid` capture prototype**",
    "**1024 camera-back preview**",
    "**Offline 4K cleanup and 8K SR**",
    "See [`docs/PRODUCT_LOCK_LEDGER.md`](docs/PRODUCT_LOCK_LEDGER.md)",
    "**1. Best RAW stills**",
    "**2. GoPro RAW video MVP**",
    "**3. Premium still/SR**",
    "**4. Raw video reconstruction improvement**",
    "50 MP and 100 MP-class cameras",
    "normal CFA support",
    "camera-noise-aware compression",
    "mission1_native12_4k_gvid",
    "4096 x 3072 Bayer",
    "camera MVP stand-in",
    "20.50 fps wall / 21.52 fps median",
    ".gvid",
    "20+ fps",
    "1024 x 768",
    "Mission 1 sensor/DMA",
    "raw-CFA targets",
    "13-scene / 351-row",
    "PSF-conditioned replacement",
    "Controlled high/low PSF pairs remain optional research",
    "The SR shipping rule is deliberately narrow",
    "That is the anti-infinite-iteration rule for this branch",
    "ship/no-ship decision",
    "The only open",
    "SR model-promotion lane is premium still-SR",
    "SR iteration is research, not a",
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
    "raw_video_psf_next_experiment_contract_20260701",
    "premium_still_sr_next_experiment_contract_transformer_teacher_20260701",
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
    "Production capture requirements",
    "full-manifest Mission/iPhone audit parses **1,997 / 2,000** rows",
    "finds **59** dark-like frames",
    "Mission ISO232 RGGB has **2** dark-like candidates",
    "iPhone ISO1250 RGGB has **27** dark-like candidates",
)

REQUIRED_STATUS_MATRIX_TOKENS = (
    "GPR four-pillar production readiness",
    "RAW stills",
    "92%",
    "GoPro RAW video MVP",
    "80%",
    "Premium still/SR",
    "60%",
    "Video reconstruction",
    "100%",
    "PSF / blur modeling is parked, not blocking the release.",
    "Controlled high/low Mission 1 pairs",
    "same .gvid, editable raw, ProRes, dashboard, timing, memory, and hash receipts",
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
    # Superseded by the broad Mission/iPhone darkframe candidate audit. iPhone
    # now has dark-like CFA candidates, but no production sidecar until
    # no-scene-signal provenance is proven.
    "iPhone has no CFA darkframe source",
    # PSF/blur modeling is optional research for a future replacement, not a
    # current-release blocker for the approved raw-video SR path.
    "PSF gates",
    "PSF pairs, and model-promotion receipts still needed",
)

README_PILLAR_LABELS = {
    "raw_stills": "Best RAW stills",
    "raw_video_mvp": "GoPro RAW video MVP",
    "premium_still_sr": "Premium still/SR",
    "raw_video_reconstruction": "RAW video reconstruction improvement",
}

REQUIRED_SCORECARD_TOKENS = (
    "| Best RAW stills | 92% |",
    "| GoPro RAW video MVP | 80% |",
    "| Premium still/SR | 60% |",
    "| RAW video reconstruction improvement | 100% |",
    "psf_gradient_focus_from_detail_s400_fw6_gw12_s300",
    "mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1",
    "PSF-conditioned replacement training are preserved as optional research evidence",
    "separate Research Parking Lot for PSF/SR follow-ups",
    "excluded from production action counts and readiness percentages",
    "The percentages are production-readiness burn-down estimates.",
    "not regression signals for locked artifacts",
    "deduplicated raw-supervision NPZ collapses it to 117 unique scene/crop raw-domain rows with zero raw conflicts",
    "same-scene candidate-signal and frequency-filter probes regress",
    "candidate-only local/full-crop/global-context/masked-context",
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


def load_scorecard_builder() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_product_pillar_scorecard_under_readme_check",
        SCORECARD_BUILDER,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCORECARD_BUILDER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def expected_percentages_from_scorecard() -> tuple[int, dict[str, int]]:
    builder = load_scorecard_builder()
    data = builder.build_scorecard(builder.DEFAULT_EXTERNAL_ROOT)
    overall = int(data["four_pillar_completion_percent"])
    by_label: dict[str, int] = {}
    for pillar in data.get("pillars", []):
        pillar_id = pillar.get("id")
        label = README_PILLAR_LABELS.get(str(pillar_id))
        if label is not None:
            by_label[label] = int(pillar["readiness_percent"])
    return overall, by_label


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

    try:
        expected_overall, expected_percentages = expected_percentages_from_scorecard()
    except Exception as exc:
        failures.append(f"could not build product scorecard for README percentage check: {exc}")
        expected_overall, expected_percentages = 0, {}

    overall_token = f"Current four-pillar completion is **{expected_overall}%**"
    if expected_overall and overall_token not in readme:
        failures.append(f"README.md missing generated overall completion token {overall_token!r}")

    missing_pillars = sorted(set(README_PILLAR_LABELS.values()) - set(expected_percentages))
    if missing_pillars:
        failures.append(f"product scorecard missing README pillar labels: {missing_pillars}")
    for pillar, expected in expected_percentages.items():
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

    status_matrix = readme_path.parent / "docs" / "img" / "readme_status_matrix.svg"
    if status_matrix.exists():
        status = status_matrix.read_text(encoding="utf-8")
        require_tokens(status, REQUIRED_STATUS_MATRIX_TOKENS, status_matrix.name, failures)
    else:
        failures.append(f"{status_matrix} is missing")

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
