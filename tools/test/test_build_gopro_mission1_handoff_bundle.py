#!/usr/bin/env python3
"""Smoke-test the GoPro Mission 1 handoff bundle builder."""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_gopro_mission1_handoff_bundle.py"


def write_gvid(path: Path) -> None:
    payloads = [b"mission1-test-frame-0", b"mission1-test-frame-1"]
    data = bytearray()
    data += struct.pack("<IBBHHHIIIII", 0x44495647, 1, 0, 1, 8, 0, 4096, 3072, 20000, 0, len(payloads))
    for tag, payload in enumerate(payloads):
        data += struct.pack("<IIQ", 0x004D5246, len(payload), tag)
        data += payload
    path.write_bytes(data)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        inputs = root / "inputs"
        inputs.mkdir()
        sample = inputs / "sample.gvid"
        write_gvid(sample)
        review = inputs / "review.webp"
        review.write_bytes(b"review")
        doc = inputs / "doc.md"
        doc.write_text("# doc\n", encoding="utf-8")
        producer = inputs / "producer.json"
        write_json(producer, {"schema": "test.producer", "frames": 2})
        bench = inputs / "labs_target_bench.json"
        handoff = inputs / "camera_handoff_receipt.json"
        preview = inputs / "preview_ui_receipt.json"
        closure = inputs / "mission1_camera_closure_run.json"
        for path in (bench, handoff, preview, closure):
            write_json(path, {"schema": "test.receipt", "path": path.name})

        out = root / "bundle"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(out),
                "--repo-commit",
                "synthetic-handoff-smoke",
                "--ci-run",
                "https://github.com/dcliftreaves/gpr/actions/runs/0",
                "--sample-gvid",
                str(sample),
                "--producer-report",
                str(producer),
                "--labs-target-bench",
                str(bench),
                "--camera-handoff",
                str(handoff),
                "--preview-ui",
                str(preview),
                "--closure-run",
                str(closure),
                "--review-media",
                str(review),
                "--doc",
                str(doc),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        manifest = Path(result["manifest"])
        assert manifest.is_file()
        data = json.loads(manifest.read_text(encoding="utf-8"))
        pillar_ids = {row["id"] for row in data.get("product_pillars", [])}
        assert pillar_ids == {"raw_stills", "raw_video_mvp", "premium_still_sr", "raw_video_reconstruction"}
        paths = {row["path"] for row in data["artifacts"]}
        assert "samples/mission1_4k_stream_source_8f.gvid" in paths
        assert "receipts/quick_validation_dry_run.json" in paths
        assert "review/review.webp" in paths
        assert "docs/doc.md" in paths
        assert "hashes/sha256sums.txt" in paths
        readme = (out / "README.md").read_text(encoding="utf-8")
        assert "Product Pillars In This Bundle" in readme
        assert "RAW video MVP" in readme
        assert "production capture requirements" in readme

        verify = subprocess.run(
            [sys.executable, str(ROOT / "tools/verify_labs_bundle.py"), str(manifest)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert verify.returncode == 0, verify.stderr

        default_proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                str(root / "default_bundle"),
                "--repo-commit",
                "synthetic-handoff-smoke",
                "--ci-run",
                "https://github.com/dcliftreaves/gpr/actions/runs/0",
                "--sample-gvid",
                str(sample),
                "--producer-report",
                str(producer),
                "--labs-target-bench",
                str(bench),
                "--camera-handoff",
                str(handoff),
                "--preview-ui",
                str(preview),
                "--closure-run",
                str(closure),
                "--review-media",
                str(review),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert default_proc.returncode == 0, default_proc.stderr
        default_manifest = json.loads((root / "default_bundle/manifest.json").read_text(encoding="utf-8"))
        default_paths = {row["path"] for row in default_manifest["artifacts"]}
        assert "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.md" in default_paths
        assert "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.json" in default_paths
    print("test_build_gopro_mission1_handoff_bundle: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
