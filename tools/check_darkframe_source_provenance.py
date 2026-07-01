#!/usr/bin/env python3
"""Validate a darkframe source-provenance manifest before noise-sidecar promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA = "gpr.darkframe_source_provenance_audit.v1"
ACCEPTED_MANIFEST_SCHEMAS = {
    "gpr.darkframe_source_provenance_manifest.v1",
    "gpr.darkframe_raw_source_provenance.v1",
}
SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--minimum-count", type=int, default=4)
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--require-existing-files", action="store_true")
    ap.add_argument("--path-root", type=Path)
    ap.add_argument(
        "--allow-missing-extract-receipt-sha256",
        action="store_true",
        help="Compatibility mode for older diagnostic manifests. Do not use for production promotion.",
    )
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def non_placeholder(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("<"):
        return ""
    return text


def valid_sha(value: Any) -> bool:
    return bool(SHA_RE.match(str(value or "")))


def first_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        text = non_placeholder(row.get(key))
        if text:
            return text
    return ""


def first_sha(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = str(row.get(key) or "")
        if valid_sha(value):
            return value
    return ""


def resolve_path(text: str, manifest_path: Path, path_root: Path | None) -> Path:
    path = Path(text)
    if path.is_absolute():
        return path
    if path_root is not None:
        return path_root / path
    return manifest_path.parent / path


def check_file_hash(
    label: str,
    path_text: str,
    expected_sha: str,
    manifest_path: Path,
    path_root: Path | None,
    failures: list[str],
) -> None:
    path = resolve_path(path_text, manifest_path, path_root)
    if not path.is_file():
        failures.append(f"{label} {path_text} does not exist")
        return
    actual = sha256_file(path)
    if actual.lower() != expected_sha.lower():
        failures.append(f"{label} {path_text} sha256 mismatch: expected {expected_sha}, got {actual}")


def validate_frame(
    row: dict[str, Any],
    index: int,
    manifest_path: Path,
    path_root: Path | None,
    require_existing_files: bool,
    require_extract_receipt_sha256: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    raw_path = first_text(row, ("raw_path", "path"))
    raw_sha = first_sha(row, ("raw_sha256", "sha256"))
    original_path = first_text(row, ("original_path", "original_raw_path", "source_dng", "source_path"))
    original_sha = first_sha(row, ("original_sha256", "source_sha256"))
    extract_receipt = first_text(row, ("extract_receipt", "extraction_receipt"))
    extract_receipt_sha = first_sha(row, ("extract_receipt_sha256", "extraction_receipt_sha256"))
    capture_setup = first_text(row, ("capture_setup", "proof"))

    if not raw_path:
        failures.append("raw_path/path is missing or still a placeholder")
    if not raw_sha:
        failures.append("raw_sha256/sha256 must be a 64-character hex digest")
    if not original_path:
        failures.append("original_path/source_dng/source_path is missing or still a placeholder")
    if not original_sha:
        failures.append("original_sha256/source_sha256 must be a 64-character hex digest")
    if not extract_receipt:
        failures.append("extract_receipt is missing or still a placeholder")
    if require_extract_receipt_sha256 and not extract_receipt_sha:
        failures.append("extract_receipt_sha256 must be a 64-character hex digest")
    if row.get("no_scene_signal") is not True:
        failures.append("no_scene_signal must be true")
    if not capture_setup:
        failures.append("capture_setup/proof is missing or still a placeholder")

    if require_existing_files:
        if raw_path and raw_sha:
            check_file_hash("raw_path", raw_path, raw_sha, manifest_path, path_root, failures)
        if original_path and original_sha:
            check_file_hash("original_path", original_path, original_sha, manifest_path, path_root, failures)
        if extract_receipt and extract_receipt_sha:
            check_file_hash("extract_receipt", extract_receipt, extract_receipt_sha, manifest_path, path_root, failures)

    return {
        "index": index,
        "raw_path": raw_path or None,
        "raw_sha256": raw_sha or None,
        "original_path": original_path or None,
        "original_sha256": original_sha or None,
        "extract_receipt": extract_receipt or None,
        "extract_receipt_sha256": extract_receipt_sha or None,
        "no_scene_signal": row.get("no_scene_signal") is True,
        "capture_setup_present": bool(capture_setup),
        "ready": not failures,
        "failures": failures,
    }


def validate_manifest(
    manifest: dict[str, Any],
    manifest_path: Path,
    minimum_count: int = 4,
    require_existing_files: bool = False,
    path_root: Path | None = None,
    require_extract_receipt_sha256: bool = True,
) -> dict[str, Any]:
    failures: list[str] = []
    schema = manifest.get("schema")
    if schema not in ACCEPTED_MANIFEST_SCHEMAS:
        failures.append(f"schema must be one of {sorted(ACCEPTED_MANIFEST_SCHEMAS)}, got {schema!r}")
    frames_raw = manifest.get("frames") or manifest.get("rows") or []
    if not isinstance(frames_raw, list):
        failures.append("frames/rows must be a list of objects")
        frames_raw = []
    frames = [row for row in frames_raw if isinstance(row, dict)]
    if len(frames) != len(frames_raw):
        failures.append("frames/rows must be a list of objects")
    rows = [
        validate_frame(
            row,
            idx,
            manifest_path,
            path_root,
            require_existing_files,
            require_extract_receipt_sha256,
        )
        for idx, row in enumerate(frames)
    ]
    ready_rows = [row for row in rows if row["ready"]]
    raw_hashes = [str(row.get("raw_sha256")) for row in rows if row.get("raw_sha256")]
    duplicate_hashes = sorted({sha for sha in raw_hashes if raw_hashes.count(sha) > 1})
    if duplicate_hashes:
        failures.append(f"duplicate extracted raw sha256 value(s): {', '.join(duplicate_hashes)}")
    if len(ready_rows) < minimum_count:
        failures.append(f"ready frame count is {len(ready_rows)}, need {minimum_count}")
    if not frames:
        failures.append("manifest must contain frames/rows")
    frame_failures = [
        f"frame {row['index']}: {failure}"
        for row in rows
        for failure in row["failures"]
    ]
    failures.extend(frame_failures)
    return {
        "schema": SCHEMA,
        "source_manifest": manifest_path.as_posix(),
        "source_manifest_schema": schema,
        "minimum_count": minimum_count,
        "require_existing_files": require_existing_files,
        "require_extract_receipt_sha256": require_extract_receipt_sha256,
        "frame_count": len(rows),
        "ready_frame_count": len(ready_rows),
        "production_ready": not failures,
        "failures": failures,
        "frames": rows,
    }


def main() -> int:
    args = parse_args()
    audit = validate_manifest(
        load_json(args.manifest),
        args.manifest,
        minimum_count=args.minimum_count,
        require_existing_files=args.require_existing_files,
        path_root=args.path_root,
        require_extract_receipt_sha256=not args.allow_missing_extract_receipt_sha256,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if audit["production_ready"]:
        print("OK - darkframe source provenance is production-ready")
        return 0
    print("darkframe source provenance check failed:", file=sys.stderr)
    for failure in audit["failures"]:
        print(f"  {failure}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
