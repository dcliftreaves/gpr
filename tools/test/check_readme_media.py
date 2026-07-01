#!/usr/bin/env python3
"""Validate local README media links and showcase claim freshness.

The top-level README is the project showcase, so broken local images or
oversized committed media should fail the CI-safe release checks. Text-based
media such as SVGs is also scanned for stale headline claims because diagrams
can drift away from the current evidence while links and file sizes still pass.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
ALLOWED_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
MAX_MEDIA_BYTES = 2 * 1024 * 1024
REQUIRED_MEDIA = {
    "docs/img/readme_showcase.webp",
    "docs/img/readme_z8_timelapse_1024.webp",
}
TEXT_MEDIA_SUFFIXES = {".svg"}
STALE_SHOWCASE_CLAIMS = {
    "12MP%20Mission%201-24.32%20fps%20stand--in": "current README badge should lead with the accepted 20+ fps Mission native12 stand-in floor",
    "24 fps capture target": "current README claim is the active 20+ fps Mission native12 stand-in floor",
    "latest strict run: 19.98 fps": "current README claim uses the selected 20.50 fps aggregate stand-in closure run",
    "Pi 5 strict run, target 24 fps": "current README claim is blocked on camera handoff/UI, not strict-24 proxy timing",
    "strict 24 fps and actual camera handoff are still open": "current README should name camera handoff as the active blocker and strict 24 fps as optional performance research",
    "while strict 24 fps remains open": "current README should name strict 24 fps as optional performance research, not an active release blocker",
    "ML-2 q3 dec2": "current README raw-video showcase should describe Mission native12 .gvid, not the older half-res path",
    "Preview capture": "current README status matrix should distinguish Mission native12 and camera handoff/UI",
    "Raw-clean model dispatch is validated": "current README status matrix should describe camera-role closure blockers",
    "model apply pending": "current README status matrix should describe the two remaining camera receipts",
}


def is_remote_or_anchor(ref: str) -> bool:
    parsed = urlparse(ref)
    return bool(parsed.scheme) or ref.startswith("#")


def normalize_local_ref(ref: str) -> str:
    path = unquote(ref.split("#", 1)[0].split("?", 1)[0])
    return path.strip()


def validate_ref(ref: str, failures: list[str]) -> None:
    if is_remote_or_anchor(ref):
        return
    rel = normalize_local_ref(ref)
    if not rel:
        failures.append(f"empty README media reference from {ref!r}")
        return
    path = ROOT / rel
    try:
        path.relative_to(ROOT)
    except ValueError:
        failures.append(f"README media reference escapes repo root: {ref!r}")
        return
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        failures.append(f"README media reference has unsupported suffix: {rel}")
    if not path.exists():
        failures.append(f"README media reference is missing: {rel}")
        return
    if not path.is_file():
        failures.append(f"README media reference is not a file: {rel}")
        return
    size = path.stat().st_size
    if size <= 0:
        failures.append(f"README media reference is empty: {rel}")
    if size > MAX_MEDIA_BYTES:
        failures.append(
            f"README media reference is too large for main: {rel} "
            f"({size} bytes > {MAX_MEDIA_BYTES} bytes)"
        )
    validate_claim_freshness(path, f"README media reference {rel}", failures)


def validate_claim_freshness(path: Path, label: str, failures: list[str]) -> None:
    if path.suffix.lower() not in TEXT_MEDIA_SUFFIXES and path != README:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    except OSError as exc:
        failures.append(f"{label} could not be read for freshness scan: {exc}")
        return
    for stale, replacement in sorted(STALE_SHOWCASE_CLAIMS.items()):
        if stale in text:
            failures.append(
                f"{label} contains stale README showcase claim {stale!r}; {replacement}"
            )


def main() -> int:
    failures: list[str] = []
    if not README.exists():
        print("README.md is missing", file=sys.stderr)
        return 1

    text = README.read_text(encoding="utf-8")
    validate_claim_freshness(README, "README.md", failures)
    refs = [match.group(1) for match in IMAGE_RE.finditer(text)]
    for required in sorted(REQUIRED_MEDIA):
        if required not in refs:
            failures.append(f"README missing required media reference: {required}")
    for ref in refs:
        validate_ref(ref, failures)

    if failures:
        print("README media check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"OK - README media check passed ({len(refs)} image reference(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
