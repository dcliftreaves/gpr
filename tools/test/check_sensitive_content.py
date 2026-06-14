#!/usr/bin/env python3
"""Guard project-owned release docs/code against prohibited sensitive content.

This is intentionally narrower than a repository-wide word ban. Vendored SDKs
and licenses can contain rights-related text, and project docs legitimately use
phrases like "runtime-legal source". The guard targets the specific restricted
claims and product-comparison language that must not appear in committed GPR
release materials.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DEFAULT_INCLUDE = (
    "README.md",
    ".github",
    "docs",
    "pipelines",
    "tests/quality_gates",
    "tools/cnn",
    "tools/gpraw",
    "tools/gpr2prores",
    "tools/gvid_metadata.py",
    "tools/gvid_pack.py",
    "tools/test",
    "source/app",
    "source/lib/vc5_common",
    "source/lib/vc5_decoder",
    "source/lib/vc5_encoder",
)

EXCLUDE_PARTS = {
    ".git",
    "__pycache__",
    "build",
    "build-local",
    "source/app/common",
    "tools/test/check_sensitive_content.py",
}

TEXT_SUFFIXES = {
    "",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".json",
    ".m",
    ".md",
    ".mm",
    ".patch",
    ".py",
    ".sh",
    ".txt",
    ".yml",
    ".yaml",
}

RESTRICTED_RIGHTS_WORD = r"\bpa" r"tents?\b"

PATTERNS = (
    (re.compile(RESTRICTED_RIGHTS_WORD, re.IGNORECASE), "restricted rights wording"),
    (re.compile(r"\bRED\s*[`'\"\u2018\u2019]?\s*384\b", re.IGNORECASE), "third-party still-image reference"),
    (re.compile(r"\bRED\s*[`'\"\u2018\u2019]?\s*967\b", re.IGNORECASE), "third-party raw-video reference"),
    (re.compile(r"\b384\b.{0,80}\b2034\b", re.IGNORECASE), "384/2034 expiry discussion"),
    (re.compile(r"\b967\b.{0,80}\b2028\b", re.IGNORECASE), "967/2028 expiry discussion"),
    (re.compile(r"\bpriority\s+20\d{2}\b", re.IGNORECASE), "restricted-priority discussion"),
    (re.compile(r"\bexpiry\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", re.IGNORECASE), "restricted-expiry discussion"),
    (re.compile(r"\bREDCODE\b", re.IGNORECASE), "product-comparison wording"),
    (re.compile(r"\bBRAW\b", re.IGNORECASE), "product-comparison wording"),
    (re.compile(r"\bProRes\s+RAW\b", re.IGNORECASE), "product-comparison wording"),
)


def is_excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    parts = set(rel.split("/"))
    return bool(parts & EXCLUDE_PARTS) or any(rel == item or rel.startswith(item + "/") for item in EXCLUDE_PARTS)


def iter_files(paths: list[Path]):
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            if not is_excluded(base) and base.suffix in TEXT_SUFFIXES:
                yield base
            continue
        for path in base.rglob("*"):
            if path.is_file() and not is_excluded(path) and path.suffix in TEXT_SUFFIXES:
                yield path


def check_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="ignore")

    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for pattern, label in PATTERNS:
            if pattern.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{line_no}: {label}: {line.strip()}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="optional repo-relative paths to scan")
    args = parser.parse_args(argv)

    targets = [ROOT / path for path in args.paths] if args.paths else [ROOT / path for path in DEFAULT_INCLUDE]
    findings: list[str] = []
    for path in sorted(set(iter_files(targets))):
        findings.extend(check_file(path))

    if findings:
        print("Sensitive-content guard failed:", file=sys.stderr)
        for item in findings:
            print(f"  {item}", file=sys.stderr)
        return 1

    print("OK - sensitive-content guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
