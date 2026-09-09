#!/usr/bin/env python3
"""Regression test for the Mission 1 native PSF corpus audit."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_mission1_native_psf_corpus_audit.py"


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_psf_corpus_audit_") as td:
        tmp = Path(td)
        high_source = tmp / "HIGH.dng"
        low_source = tmp / "LOW.dng"
        high_raw = tmp / "HIGH.raw"
        low_raw = tmp / "LOW.raw"
        high_source.write_bytes(b"high-source")
        low_source.write_bytes(b"low-source")
        high_raw.write_bytes(b"high-raw")
        low_raw.write_bytes(b"low-raw")

        media = tmp / "media.json"
        inventory = tmp / "inventory.json"
        measurement = tmp / "measurement.json"
        capture = tmp / "capture.json"
        out = tmp / "out"

        write_json(
            media,
            {
                "stems": [
                    {
                        "stem": "HIGH",
                        "files": {"DNG": str(high_source)},
                        "dims": {"DNG": [8192, 6144]},
                    },
                    {
                        "stem": "LOW",
                        "files": {"DNG": str(low_source)},
                        "dims": {"DNG": [4096, 3072]},
                    },
                ]
            },
        )
        write_json(
            inventory,
            {
                "schema": "gpr.mission1_native_psf_pair_inventory.v1",
                "summary": {
                    "mission1_high_count": 1,
                    "mission1_low_count": 1,
                    "candidate_pair_count": 1,
                    "decoded_candidate_pair_count": 1,
                },
                "candidate_pairs": [
                    {
                        "high_stem": "HIGH",
                        "low_stem": "LOW",
                        "time_delta_s": 2.0,
                        "iso_ratio": 1.0,
                        "production_candidate": True,
                        "high_raw": {"path": str(high_raw), "exists": True, "bytes": high_raw.stat().st_size},
                        "low_raw": {"path": str(low_raw), "exists": True, "bytes": low_raw.stat().st_size},
                    }
                ],
            },
        )
        write_json(
            measurement,
            {
                "schema": "gpr.mission1_native_psf_measurement.v1",
                "summary": {"accepted_pair_count": 1, "kernel_stable": False},
                "native_psf_ready_for_model_conditioning": False,
            },
        )
        write_json(
            capture,
            {
                "schema": "gpr.raw_video_psf_capture_request.v1",
                "summary": {"minimum_new_controlled_pair_count": 3},
                "promotion_policy": {
                    "pair_promotion_requires_negative_controls": True,
                    "pair_promotion_requires_source_hashes_and_decoded_raw_hashes": True,
                    "pair_promotion_requires_fixed_camera_settings": True,
                },
            },
        )

        subprocess.check_call(
            [
                sys.executable,
                str(TOOL),
                "--media-summary",
                str(media),
                "--pair-inventory",
                str(inventory),
                "--measurement",
                str(measurement),
                "--capture-request",
                str(capture),
                "--output-dir",
                str(out),
                "--hash-files",
            ],
            cwd=ROOT,
        )
        data = json.loads((out / "mission1_native_psf_corpus_audit.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.mission1_native_psf_corpus_audit.v1"
        assert data["local_corpus_can_close_psf_gap"] is False
        assert data["summary"]["hashed_candidate_pair_count"] == 1
        assert data["summary"]["strict_controlled_pair_count"] == 0
        assert any("fixed WB/lens" in item for item in data["candidate_pairs"][0]["missing"])
        assert any("unstable native kernel" in item for item in data["blockers"])
        assert (out / "index.html").exists()
    print("test_build_mission1_native_psf_corpus_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
