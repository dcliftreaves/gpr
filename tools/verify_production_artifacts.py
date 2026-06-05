#!/usr/bin/env python3
"""Verify production artifacts referenced by pipelines/registry.json.

Checkpoint binaries stay off main. Registry paths remain portable
(`models/name.pt`) and resolve from:

  1. the repo path itself, for local developer copies;
  2. GPR_MODEL_ROOT and GPR_CHECKPOINT_ROOT, os.pathsep-separated;
  3. GPR_EXTERNAL_ROOT/{models,checkpoints};
  4. /Volumes/OWC_8TB/gpr_work/{models,checkpoints}.

Default mode reports missing artifacts but exits 0 so CI can surface the
inventory without requiring private model files. Use --strict for release
verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "pipelines/registry.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def candidates(path_value: str) -> list[Path]:
    path = Path(path_value)
    if path.is_absolute():
        return [path]

    roots: list[tuple[Path, bool]] = [(REPO, False)]
    for key in ("GPR_MODEL_ROOT", "GPR_CHECKPOINT_ROOT"):
        for item in os.environ.get(key, "").split(os.pathsep):
            if item:
                roots.append((Path(item), True))
    external_root = Path(os.environ.get("GPR_EXTERNAL_ROOT", "/Volumes/OWC_8TB/gpr_work"))
    roots.extend([
        (external_root, False),
        (external_root / "models", True),
        (external_root / "checkpoints", True),
        (Path("/Volumes/OWC_8TB/gpr_work/models"), True),
        (Path("/Volumes/OWC_8TB/gpr_work/checkpoints"), True),
    ])

    out: list[Path] = []
    seen = set()
    for root, prefer_stripped in roots:
        root_path = root / path
        stripped = None
        if path.parts and path.parts[0] in {"models", "checkpoints"}:
            stripped = root / Path(*path.parts[1:])
        ordered = ([stripped, root_path] if prefer_stripped and stripped is not None
                   else [root_path] + ([stripped] if stripped is not None else []))
        for candidate in ordered:
            key = str(candidate)
            if key not in seen:
                seen.add(key)
                out.append(candidate)
    return out


def checkpoint_specs(cnn: dict) -> list[tuple[str, str, str, str | None]]:
    specs = []
    if "ckpt_path" in cnn:
        specs.append(("ckpt_path", cnn["ckpt_path"], "ckpt_sha256", cnn.get("ckpt_sha256")))
    for suffix in ("y", "cb", "cr", "chroma", "detail", "rgb_detail"):
        path_key = f"ckpt_{suffix}"
        if path_key in cnn:
            specs.append((path_key, cnn[path_key], f"{path_key}_sha256", cnn.get(f"{path_key}_sha256")))
    if "luma_detail_refiner" in cnn:
        specs.append((
            "luma_detail_refiner",
            cnn["luma_detail_refiner"],
            "luma_detail_refiner_sha256",
            cnn.get("luma_detail_refiner_sha256"),
        ))
    return specs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true", help="exit nonzero on missing/hash mismatch")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = ap.parse_args()

    reg = json.loads(REGISTRY.read_text())
    rows = []
    failures = 0
    for cnn_name, cnn in reg.get("cnns", {}).items():
        if str(cnn_name).startswith("$") or cnn_name == "none" or not isinstance(cnn, dict):
            continue
        for path_field, path_value, sha_field, expected_sha in checkpoint_specs(cnn):
            found = next((p for p in candidates(path_value) if p.exists()), None)
            status = "missing"
            actual_sha = None
            if found is not None:
                actual_sha = sha256_file(found)
                status = "ok" if actual_sha == expected_sha else "sha_mismatch"
            if status != "ok":
                failures += 1
            rows.append({
                "cnn": cnn_name,
                "path_field": path_field,
                "path": path_value,
                "resolved": str(found) if found else None,
                "sha_field": sha_field,
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "status": status,
                "searched": [str(p) for p in candidates(path_value)[:8]],
            })

    if args.json:
        print(json.dumps({"failures": failures, "artifacts": rows}, indent=2))
    else:
        print("=== production artifact verification ===")
        print(f"GPR_MODEL_ROOT={os.environ.get('GPR_MODEL_ROOT', '')}")
        print(f"GPR_CHECKPOINT_ROOT={os.environ.get('GPR_CHECKPOINT_ROOT', '')}")
        for row in rows:
            loc = row["resolved"] or row["path"]
            print(f"{row['status']:12s} {row['cnn']} {row['path_field']} {loc}")
        if failures:
            print(f"\n{failures} artifact(s) missing or mismatched")
            print("Use --strict for release gating; default mode is inventory-only.")

    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    sys.exit(main())
