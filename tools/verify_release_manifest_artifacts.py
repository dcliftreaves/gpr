#!/usr/bin/env python3
"""Verify external artifacts referenced by docs/release_evidence_manifest.json.

The release manifest indexes dashboards, JSON receipts, rendered media, run
logs, and directory receipts that stay outside git. Default mode inventories
those paths and exits 0 so hosted CI can exercise the resolver without the
external drive. Use --strict for release promotion.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs/release_evidence_manifest.json"


def external_root(manifest: dict[str, Any]) -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or manifest.get("external_root") or "/Volumes/OWC_8TB/gpr_work")


def artifact_root(manifest: dict[str, Any]) -> Path:
    return Path(os.environ.get("GPR_ARTIFACT_ROOT") or external_root(manifest) / "artifacts")


def artifact_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str):
        if value.startswith("artifacts/"):
            refs.add(value)
        return refs
    if isinstance(value, list):
        for item in value:
            refs.update(artifact_refs(item))
        return refs
    if isinstance(value, dict):
        for item in value.values():
            refs.update(artifact_refs(item))
    return refs


def candidate_paths(ref: str, manifest: dict[str, Any]) -> list[Path]:
    path = Path(ref)
    if path.is_absolute():
        return [path]
    candidates = [external_root(manifest) / path]
    if path.parts and path.parts[0] == "artifacts":
        candidates.append(artifact_root(manifest) / Path(*path.parts[1:]))
    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


def classify(path: Path | None) -> tuple[str, str | None, int | None]:
    if path is None:
        return "missing", None, None
    if path.is_dir():
        try:
            has_child = any(path.iterdir())
        except OSError as exc:
            return "unreadable", str(exc), None
        return ("ok" if has_child else "empty_dir"), None, None
    if not path.is_file():
        return "not_file_or_dir", None, None
    try:
        size = path.stat().st_size
    except OSError as exc:
        return "unreadable", str(exc), None
    if size <= 0:
        return "empty_file", None, size
    if path.suffix == ".json":
        try:
            with path.open("r", encoding="utf-8") as f:
                json.load(f)
        except Exception as exc:
            return "bad_json", str(exc), size
    return "ok", None, size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit nonzero when any manifest artifact is missing or unreadable")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    refs = sorted(artifact_refs(manifest))
    rows: list[dict[str, Any]] = []
    failures = 0

    for ref in refs:
        candidates = candidate_paths(ref, manifest)
        resolved = next((path for path in candidates if path.exists()), None)
        status, error, size = classify(resolved)
        if status != "ok":
            failures += 1
        rows.append({
            "ref": ref,
            "resolved": str(resolved) if resolved else None,
            "status": status,
            "size_bytes": size,
            "error": error,
            "searched": [str(path) for path in candidates],
        })

    payload = {
        "manifest": str(MANIFEST.relative_to(REPO)),
        "external_root": str(external_root(manifest)),
        "artifact_root": str(artifact_root(manifest)),
        "count": len(rows),
        "failures": failures,
        "artifacts": rows,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("=== release manifest artifact verification ===")
        print(f"manifest={payload['manifest']}")
        print(f"GPR_EXTERNAL_ROOT={payload['external_root']}")
        print(f"GPR_ARTIFACT_ROOT={payload['artifact_root']}")
        for row in rows:
            loc = row["resolved"] or row["ref"]
            print(f"{row['status']:15s} {loc}")
        if failures:
            print(f"\n{failures} manifest artifact(s) missing or unreadable")
            print("Use --strict for release gating; default mode is inventory-only.")

    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    sys.exit(main())
