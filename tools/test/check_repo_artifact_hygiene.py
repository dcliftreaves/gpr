#!/usr/bin/env python3
"""Prevent accidental generated artifacts from landing in the repo.

Production receipts, dashboards, renders, models, and scratch media belong
under /Volumes/OWC_8TB/gpr_work. The repo may still carry small deterministic
fixtures and README assets; those are allowlisted here.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
MAX_UNALLOWLISTED_BYTES = 1_000_000
MAX_ALLOWLISTED_BYTES = 10_000_000
REQUIRED_README_MEDIA = {
    "docs/img/readme_showcase.webp": {
        "max_bytes": 500_000,
        "width": 1600,
        "height": 1100,
    },
    "docs/img/readme_z8_timelapse_1024.webp": {
        "max_bytes": 2_000_000,
        "width": 1024,
        "height": 576,
    },
}

GENERATED_SUFFIXES = {
    ".ckpt",
    ".dng",
    ".gpr",
    ".gpraw",
    ".gvid",
    ".html",
    ".jpeg",
    ".jpg",
    ".mlmodel",
    ".mov",
    ".mp4",
    ".npy",
    ".npz",
    ".png",
    ".pt",
    ".pth",
    ".raw",
    ".tif",
    ".tiff",
}

ALLOWLIST = (
    "data/readmegfx/*.png",
    "data/samples/Fusion/*.GPR",
    "data/samples/HERO7/*.GPR",
    "data/samples/HERO9/*.GPR",
    "data/samples/Hero5/*.GPR",
    "data/samples/Hero6/*.GPR",
    "docs/compression-results.html",
    "docs/img/*.gif",
    "docs/img/*.png",
    "docs/img/*.svg",
    "docs/img/*.webp",
    "source/app/fuzz_decoder/corpus/*.gvid",
    "tests/conformance/inputs/*.raw",
)

DISALLOWED_PARTS = {
    "artifacts",
    "artifact",
    "outputs",
    "output",
    "tmp",
    "scratch",
}


IMAGE_LINK_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def is_allowlisted(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, pattern) for pattern in ALLOWLIST)


def has_disallowed_part(rel: str) -> bool:
    return bool(set(rel.split("/")) & DISALLOWED_PARTS)


def check_readme_media(failures: list[str]) -> None:
    text = README.read_text(encoding="utf-8")
    image_links = IMAGE_LINK_RE.findall(text)
    image_targets = {target.split("#", 1)[0].strip() for _, target in image_links}
    if not image_links:
        failures.append("README.md: no image links found")
        return

    for alt, target in image_links:
        if not alt.strip():
            failures.append(f"README.md: image link has empty alt text: {target}")
        if "://" in target or target.startswith("#"):
            continue
        rel = target.split("#", 1)[0].strip()
        path = ROOT / rel
        if not path.exists():
            failures.append(f"README.md: image target does not exist: {target}")
            continue
        if not rel.startswith("docs/img/"):
            failures.append(f"README.md: image target should live under docs/img/: {target}")
        if path.stat().st_size > MAX_ALLOWLISTED_BYTES:
            failures.append(f"README.md: image target is too large ({path.stat().st_size} bytes): {target}")

    for rel, policy in REQUIRED_README_MEDIA.items():
        if rel not in image_targets:
            failures.append(f"README.md: required media is not embedded: {rel}")
            continue
        path = ROOT / rel
        if not path.exists():
            failures.append(f"README.md: required media is missing: {rel}")
            continue
        size = path.stat().st_size
        if size > policy["max_bytes"]:
            failures.append(f"README.md: required media is too large ({size} bytes): {rel}")
        dims = webp_dimensions(path)
        if dims is None:
            failures.append(f"README.md: required media dimensions could not be read: {rel}")
        elif dims != (policy["width"], policy["height"]):
            failures.append(f"README.md: required media dimensions are {dims[0]}x{dims[1]}, expected {policy['width']}x{policy['height']}: {rel}")


def webp_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    offset = 12
    while offset + 8 <= len(data):
        chunk = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload = offset + 8
        if chunk == b"VP8 " and payload + 10 <= len(data):
            if data[payload + 3 : payload + 6] != b"\x9d\x01\x2a":
                return None
            width = int.from_bytes(data[payload + 6 : payload + 8], "little") & 0x3FFF
            height = int.from_bytes(data[payload + 8 : payload + 10], "little") & 0x3FFF
            return width, height
        if chunk == b"VP8X" and payload + 10 <= len(data):
            width = int.from_bytes(data[payload + 4 : payload + 7], "little") + 1
            height = int.from_bytes(data[payload + 7 : payload + 10], "little") + 1
            return width, height
        offset = payload + size + (size % 2)
    return None


def main() -> int:
    failures: list[str] = []

    for rel in tracked_files():
        path = ROOT / rel
        if not path.exists():
            # Dirty local worktrees can include tracked files staged/marked for
            # deletion. A clean CI checkout will not have this mismatch after
            # the deletion is committed, so do not crash while preparing the
            # branch.
            continue
        suffix = path.suffix.lower()
        allowlisted = is_allowlisted(rel)
        size = path.stat().st_size

        if has_disallowed_part(rel):
            failures.append(f"{rel}: tracked path looks like generated scratch/artifact output")

        if suffix in GENERATED_SUFFIXES and not allowlisted:
            failures.append(f"{rel}: generated/media suffix {suffix} is not allowlisted")

        if allowlisted and size > MAX_ALLOWLISTED_BYTES:
            failures.append(f"{rel}: allowlisted fixture is too large ({size} bytes)")
        elif not allowlisted and size > MAX_UNALLOWLISTED_BYTES:
            failures.append(f"{rel}: unallowlisted file is too large ({size} bytes)")

    check_readme_media(failures)

    if failures:
        print("Repo artifact hygiene check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("OK - repo artifact hygiene check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
