#!/usr/bin/env python3
"""Prevent accidental generated artifacts from landing in the repo.

Production receipts, dashboards, renders, models, and scratch media belong
under /Volumes/OWC_8TB/gpr_work. The repo may still carry small deterministic
fixtures and README assets; those are allowlisted here.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAX_UNALLOWLISTED_BYTES = 1_000_000
MAX_ALLOWLISTED_BYTES = 10_000_000

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

    if failures:
        print("Repo artifact hygiene check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("OK - repo artifact hygiene check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
