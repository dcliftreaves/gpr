#!/usr/bin/env python3
"""Regression test for darkframe source-provenance validation."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_darkframe_source_provenance.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("check_darkframe_source_provenance", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    module = import_tool()
    return module.sha256_file(path)


def main() -> int:
    module = import_tool()
    with tempfile.TemporaryDirectory(prefix="gpr_darkframe_prov_") as td:
        root = Path(td)
        frames = []
        for idx in range(4):
            raw = root / f"dark_{idx}.raw"
            original = root / f"dark_{idx}.DNG"
            receipt = root / f"extract_{idx}.json"
            raw_sha = write(raw, f"raw-{idx}".encode())
            original_sha = write(original, f"dng-{idx}".encode())
            receipt_sha = write(receipt, json.dumps({"idx": idx}).encode())
            frames.append(
                {
                    "raw_path": raw.as_posix(),
                    "raw_sha256": raw_sha,
                    "original_path": original.as_posix(),
                    "original_sha256": original_sha,
                    "extract_receipt": receipt.as_posix(),
                    "extract_receipt_sha256": receipt_sha,
                    "no_scene_signal": True,
                    "capture_setup": "lens cap on; no light leak",
                }
            )
        manifest = {
            "schema": "gpr.darkframe_source_provenance_manifest.v1",
            "frames": frames,
        }
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        audit = module.validate_manifest(
            manifest,
            manifest_path,
            require_existing_files=True,
        )
        assert audit["production_ready"] is True
        assert audit["ready_frame_count"] == 4
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(manifest_path),
                "--require-existing-files",
                "--json-out",
                str(root / "audit.json"),
            ],
            check=True,
        )
        written = json.loads((root / "audit.json").read_text(encoding="utf-8"))
        assert written["production_ready"] is True

        bad = json.loads(json.dumps(manifest))
        bad["frames"][0]["no_scene_signal"] = False
        bad["frames"][1]["extract_receipt_sha256"] = "<64_hex_extract_receipt_sha256>"
        bad_path = root / "bad.json"
        bad_path.write_text(json.dumps(bad), encoding="utf-8")
        bad_audit = module.validate_manifest(bad, bad_path)
        assert bad_audit["production_ready"] is False
        assert any("no_scene_signal" in item for item in bad_audit["failures"])
        assert any("extract_receipt_sha256" in item for item in bad_audit["failures"])
        proc = subprocess.run([sys.executable, str(TOOL), str(bad_path)], check=False)
        assert proc.returncode == 1
    print("test_check_darkframe_source_provenance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
