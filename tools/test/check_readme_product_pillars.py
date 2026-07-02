#!/usr/bin/env python3
"""Validate the README's four-pillar product framing.

The README is the public product surface. This guard keeps the high-level
story aligned with the current production scorecard so future edits do not
drop the raw-stills, raw-video, premium still/SR, or raw-video reconstruction
goals.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
SCORECARD = ROOT / "docs/PRODUCT_PILLAR_SCORECARD.md"
SCORECARD_BUILDER = ROOT / "tools/build_product_pillar_scorecard.py"
MANIFEST = ROOT / "docs/release_evidence_manifest.json"

MAX_README_LINES = 520

REQUIRED_SECTIONS = (
    "## Open Raw Video For Action Cameras",
    "## Product Status In One Screen",
    "## The Four Product Bets",
    "## What Is Locked",
    "## Evidence Map",
    "## Visual Proof",
    "## Current Evidence Snapshot",
    "## Stills Performance And CNN Latitude",
    "## Mission 1 Numbered List",
    "## Media And Dashboards",
    "## Raw Output Ladder",
    "## Final Camera Closure",
)

REQUIRED_README_TOKENS = (
    "8-bit JPEG size. 16-bit RAW quality.",
    "![GPR raw-video showcase: 4K Bayer .gvid, live preview, native 12MP crops, and 8K SR review](docs/img/readme_showcase.webp)",
    "![GPR four-pillar production readiness](docs/img/readme_status_matrix.svg)",
    "## What Ships From The Same Raw Stream",
    "| **Compact RAW stills** | 50 MP and 100 MP-class Bayer photos stay editable while landing near JPEG-sized file budgets. |",
    "| **Camera RAW video** | 4096 x 3072 Bayer frames become `.gvid` streams that are small enough for the accepted Pi 5 / Mission 1 stand-in write path. |",
    "| **Camera-back preview** | The same `.gvid` stream decodes to a full-frame 1024 x 768 preview instead of maintaining a separate preview-only codec. |",
    "| **Desktop reconstruction** | 4K cleanup and 8K SR run offline, where extra compute can buy detail without slowing capture. |",
    "| **Review media** | ProRes and dashboard outputs exist for inspection, but the editable Bayer `.gvid` / DNG / GPR artifacts remain the product source. |",
    "Current four-pillar completion is **",
    "production-readiness",
    "not an image-quality score",
    "not a regression signal for locked",
    "capture editable Bayer",
    "preview from the same raw stream",
    "spend desktop compute only",
    "| **Best RAW stills** | **92%** |",
    "| **GoPro RAW video MVP** | **80%** |",
    "| **Premium still/SR** | **60%** |",
    "| **RAW video reconstruction improvement** | **100%** |",
    "50 MP tiers at **9.80 MB**, **15.05 MB**, and **27.17 MB**",
    "X2D 100 MP roundtrip",
    "real RGGB/GBRG/GRBG/BGGR coverage",
    "Mission 1 and iPhone strict-provenance darkframe sidecars",
    "True 4096 x 3072 Bayer frames recompress into `.gvid`",
    "accepted **20+ fps** Pi 5 stand-in floor",
    "same stream previews full-frame at 1024 x 768",
    "Real Mission 1 sensor/DMA or camera-ring-buffer source",
    "118-receipt experiment scoreboard",
    "X2D/Z8 source-evidence audits",
    "route-specialist readiness audit",
    "Route-specialist full-frame metrics are positive",
    "exact-sidecar-only noise policy",
    "Approved offline/post 4K cleanup and 8K SR",
    "standalone no-CNN/CNN ProRes review movies",
    "PSF/blur modeling is parked as optional replacement research",
    "GPR is not one codec demo",
    "four product outcomes",
    "locked proof surfaces",
    "**1. Better RAW stills**",
    "**2. GoPro RAW video MVP**",
    "**3. Premium still improvement**",
    "**4. RAW video reconstruction**",
    "Ship as a Labs-ready handoff package from Pi 5 stand-in evidence",
    "Do not promote current CNNs",
    "Reopen only if its locked gate/receipt/hash/manual review fails",
    "same `.gvid`, editable raw, ProRes, dashboard, timing, memory, and hash evidence",
    "**50 MP RAW still tiers**",
    "**4K `.gvid` capture prototype**",
    "**1024 camera-back preview**",
    "**Offline 4K cleanup and 8K SR**",
    "The SR shipping rule is narrow by design",
    "ship/no-ship decision",
    "SR model-promotion lane is premium",
    "SR iteration is research",
    "Premium still-SR promotion is intentionally stricter than",
    "`runtime_inputs` with `candidate_raw`",
    "exclude REF/source/JPEG content at render time",
    "50 MP and 100 MP gate row",
    "positive median MAE reduction with nonnegative worst-row MAE",
    "seconds/frame and peak RSS",
    "**118** runtime-safe",
    "**0** promotable rows",
    "**4.03%**",
    "**3.75%**",
    "**15% / 15%**",
    "**4.82%**",
    "**11.52%**",
    "**0.65%**",
    "**21.90%**",
    "**+0.0088%**",
    "**-0.0736%**",
    "**-4.85%**",
    "**-8.81%**",
    "**-67.44%**",
    "**-0.0777%**",
    "**-0.9817%**",
    "route-specialist/raw-CFA promotion",
    "positive full-frame metric floors",
    "docs/PRODUCT_PILLAR_SCORECARD.md",
    "docs/GOAL_CLOSURE_MATRIX.md",
    "docs/PRODUCT_LOCK_LEDGER.md",
    "docs/WORKSPACE_AND_ARTIFACT_MAP.md",
    "docs/PRODUCTION_ARTIFACTS.md",
    "docs/release_evidence_manifest.json",
    "docs/BIG_EFFORTS_STATUS.md",
    "docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md",
    "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md",
    "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json",
    "docs/SHIP_DECISION.md",
    "docs/CAMERA_NOISE_CALIBRATION.md",
    "docs/RAW_STILLS_NOISE_FIRST_HOUR.md",
    "docs/VIDEO_STATUS.md",
    "docs/GOPRO_MISSION1_QUICK_VALIDATION.md",
    "docs/GOPRO_LABS_FIRST_HOUR.md",
    "docs/PREMIUM_STILL_SR.md",
    "docs/PREMIUM_STILL_SR_FIRST_HOUR.md",
    "docs/BAYER_RESIZE_PSF.md",
    "raw_video_psf_next_experiment_contract_20260701",
    "premium_still_sr_experiment_scoreboard_gated_residual_20260702",
    "Small preview assets stay in git",
    "full dashboards, review movies, checkpoints",
    "z8_continuous_8k_no_cnn_vs_cnn_20260630",
    "mission1_8k_true_no_cnn_vs_cnn_20260630",
    "mission1_8k_scene_GP017497_508_no_cnn_vs_cnn_20260630",
    "mission1_native12_4k_gvid",
    "20.50 fps wall / 21.52 fps median",
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
    # The public page should stay product-led. These older headings repeated
    # the same status in several places and made the README read like a logbook.
    "## At A Glance",
    "## What It Enables",
    "## Status At A Glance",
    "## Mission 1 Reality Check",
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

SVG_PILLAR_LABELS = {
    "raw_stills": "RAW stills",
    "raw_video_mvp": "GoPro RAW video MVP",
    "premium_still_sr": "Premium still/SR",
    "raw_video_reconstruction": "Video reconstruction",
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
    "118 runtime-safe experiment receipts",
    "0 are promotable",
    "Frequency-pyramid is blocked before long training",
    "X2D worst-row MAE is -4.85%",
    "Z8 median/worst-row MAE are -8.81% / -67.44%",
    "Gated no-op residual reduces Z8 damage",
    "nearly reach interpolation parity",
    "positive held-out recovery with nonnegative worst-row behavior",
    "zero promotable rows",
    "4.03",
    "3.75",
    "15 percent / 15 percent",
)


def require_tokens(text: str, tokens: tuple[str, ...], label: str, failures: list[str]) -> None:
    for token in tokens:
        if token not in text:
            failures.append(f"{label} missing {token!r}")


def extract_done_percent(readme: str, pillar: str) -> int | None:
    pattern = re.compile(rf"\|\s*(?:\*\*)?{re.escape(pillar)}(?:\*\*)?\s*\|\s*\*\*(\d+)%\*\*")
    match = pattern.search(readme)
    if not match:
        return None
    return int(match.group(1))


def extract_svg_percent(svg: str, pillar: str) -> int | None:
    label = re.escape(pillar)
    pattern = re.compile(
        rf"<text[^>]*>\s*{label}\s*</text>.*?<text[^>]*>\s*(\d+)%\s*</text>",
        re.DOTALL,
    )
    match = pattern.search(svg)
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


def expected_product_state_from_scorecard() -> tuple[int, dict[str, int], dict[str, int]]:
    builder = load_scorecard_builder()
    data = builder.build_scorecard(builder.DEFAULT_EXTERNAL_ROOT)
    overall = int(data["four_pillar_completion_percent"])
    readme_by_label: dict[str, int] = {}
    svg_by_label: dict[str, int] = {}
    for pillar in data.get("pillars", []):
        pillar_id = pillar.get("id")
        readiness = int(pillar["readiness_percent"])
        readme_label = README_PILLAR_LABELS.get(str(pillar_id))
        if readme_label is not None:
            readme_by_label[readme_label] = readiness
        svg_label = SVG_PILLAR_LABELS.get(str(pillar_id))
        if svg_label is not None:
            svg_by_label[svg_label] = readiness
    return overall, readme_by_label, svg_by_label


def product_state_from_manifest() -> dict[str, dict[str, Any]]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pillars = data.get("product_pillars")
    if not isinstance(pillars, list):
        raise ValueError("release evidence manifest missing product_pillars list")
    result: dict[str, dict[str, Any]] = {}
    for pillar in pillars:
        if not isinstance(pillar, dict):
            raise ValueError("release evidence manifest product_pillars entries must be objects")
        pillar_id = str(pillar.get("id") or "")
        if not pillar_id:
            raise ValueError("release evidence manifest product_pillars entry missing id")
        result[pillar_id] = {
            "readiness_percent": int(pillar["readiness_percent"]),
            "production_ready": bool(pillar["production_ready"]),
            "release_label": str(pillar.get("release_label") or ""),
            "status": str(pillar.get("status") or ""),
        }
    return result


def validate(readme_path: Path = README, scorecard_path: Path = SCORECARD) -> list[str]:
    failures: list[str] = []
    if not readme_path.exists():
        return [f"{readme_path} is missing"]
    readme = readme_path.read_text(encoding="utf-8")


    line_count = len(readme.splitlines())
    if line_count > MAX_README_LINES:
        failures.append(
            f"README.md is too long for the public product page: "
            f"{line_count} lines > {MAX_README_LINES}"
        )

    require_tokens(readme, REQUIRED_SECTIONS, readme_path.name, failures)
    require_tokens(readme, REQUIRED_README_TOKENS, readme_path.name, failures)
    evidence_questions = re.findall(r"^\| What [^|]+\|", readme, flags=re.MULTILINE)
    duplicate_evidence_questions = sorted(
        question for question in set(evidence_questions) if evidence_questions.count(question) > 1
    )
    if duplicate_evidence_questions:
        failures.append(
            "README.md Evidence Map repeats question rows: "
            + ", ".join(duplicate_evidence_questions)
        )
    for token in FORBIDDEN_README_TOKENS:
        if token in readme:
            failures.append(f"{readme_path.name} must not reference rejected or superseded artifact {token!r}")

    try:
        expected_overall, expected_percentages, expected_svg_percentages = expected_product_state_from_scorecard()
    except Exception as exc:
        failures.append(f"could not build product scorecard for README percentage check: {exc}")
        expected_overall, expected_percentages, expected_svg_percentages = 0, {}, {}

    try:
        builder = load_scorecard_builder()
        scorecard_data = builder.build_scorecard(builder.DEFAULT_EXTERNAL_ROOT)
        manifest_pillars = product_state_from_manifest()
        for pillar in scorecard_data.get("pillars", []):
            if not isinstance(pillar, dict):
                failures.append("product scorecard builder returned a non-object pillar")
                continue
            pillar_id = str(pillar.get("id") or "")
            if pillar_id not in manifest_pillars:
                failures.append(f"release evidence manifest missing product pillar {pillar_id!r}")
                continue
            manifest_pillar = manifest_pillars[pillar_id]
            readiness = int(pillar.get("readiness_percent"))
            manifest_readiness = int(manifest_pillar["readiness_percent"])
            if readiness != manifest_readiness:
                failures.append(
                    f"pillar {pillar_id!r} readiness drift: scorecard {readiness}% "
                    f"!= manifest {manifest_readiness}%"
                )
            production_ready = bool(pillar.get("production_ready"))
            manifest_ready = bool(manifest_pillar["production_ready"])
            if production_ready != manifest_ready:
                failures.append(
                    f"pillar {pillar_id!r} production_ready drift: scorecard "
                    f"{production_ready} != manifest {manifest_ready}"
                )
        missing_from_scorecard = sorted(
            set(manifest_pillars)
            - {
                str(pillar.get("id") or "")
                for pillar in scorecard_data.get("pillars", [])
                if isinstance(pillar, dict)
            }
        )
        if missing_from_scorecard:
            failures.append(f"product scorecard missing manifest pillars: {missing_from_scorecard}")
    except Exception as exc:
        failures.append(f"could not cross-check product scorecard against release manifest: {exc}")

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
        missing_svg_pillars = sorted(set(SVG_PILLAR_LABELS.values()) - set(expected_svg_percentages))
        if missing_svg_pillars:
            failures.append(f"product scorecard missing SVG pillar labels: {missing_svg_pillars}")
        for pillar, expected in expected_svg_percentages.items():
            actual = extract_svg_percent(status, pillar)
            if actual is None:
                failures.append(f"{status_matrix.name} missing percentage text for {pillar!r}")
            elif actual != expected:
                failures.append(
                    f"{status_matrix.name} percentage for {pillar!r} is {actual}%, expected {expected}%"
                )
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
