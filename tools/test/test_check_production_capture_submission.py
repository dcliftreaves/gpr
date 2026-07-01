#!/usr/bin/env python3
"""Regression-test production capture submission manifest validation."""
from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/check_production_capture_submission.py"
SHA = "a" * 64
SHA_B = "b" * 64


def path_hash_key(key: str) -> str | None:
    if key == "source_path":
        return "sha256"
    if key == "gvid_path":
        return "gvid_sha256"
    if key.endswith("_path"):
        return f"{key[:-5]}_sha256"
    return None


def materialize_path_hashes(value, bundle: Path, counter: list[int]) -> None:
    if isinstance(value, dict):
        for key in list(value):
            hash_key = path_hash_key(key)
            if hash_key and isinstance(value.get(hash_key), str):
                counter[0] += 1
                rel = Path("evidence") / f"{counter[0]:03d}_{key}.bin"
                full = bundle / rel
                full.parent.mkdir(parents=True, exist_ok=True)
                payload = f"{key}:{counter[0]}\n".encode("utf-8")
                full.write_bytes(payload)
                value[key] = rel.as_posix()
                value[hash_key] = hashlib.sha256(payload).hexdigest()
            materialize_path_hashes(value[key], bundle, counter)
    elif isinstance(value, list):
        for item in value:
            materialize_path_hashes(item, bundle, counter)


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or "/Volumes/OWC_8TB/gpr_work/tmp")
    if not root.exists():
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def fixture(phase: str) -> dict:
    return {
        "source_path": f"/captures/{phase}.dng",
        "sha256": SHA,
        "make": "Example",
        "model": "RawCam",
        "width": 4000,
        "height": 3000,
        "cfa_phase": phase,
        "bit_depth": 14,
        "black_level": 512,
        "white_level": 16383,
        "iso": 100,
        "original_camera_raw": True,
        "linear_raw": False,
    }


def darkframe(model: str, idx: int, *, iphone: bool = False) -> dict:
    return {
        "source_path": f"/captures/{model}_{idx}.dng",
        "sha256": SHA,
        "extract_receipt_sha256": SHA_B,
        "make": "Apple" if iphone else "GoPro",
        "model": model,
        "width": 4032,
        "height": 3024,
        "cfa_phase": "RGGB",
        "bit_depth": 12,
        "black_level": 64,
        "white_level": 4095,
        "iso": 232,
        "exposure": "1/30",
        "no_scene_signal": True,
        "linear_raw": False,
    }


def pair(idx: int, *, negative: bool = False) -> dict:
    return {
        "id": f"pair_{idx}",
        "high_source_path": f"/captures/pair_{idx}_high.dng",
        "low_source_path": f"/captures/pair_{idx}_low.dng",
        "high_source_sha256": SHA,
        "low_source_sha256": SHA_B,
        "high_bayer_path": f"/captures/pair_{idx}_high.raw",
        "low_bayer_path": f"/captures/pair_{idx}_low.raw",
        "high_bayer_sha256": SHA,
        "low_bayer_sha256": SHA_B,
        "high_extract_receipt_sha256": SHA,
        "low_extract_receipt_sha256": SHA_B,
        "settings_receipt_sha256": SHA,
        "measurement_receipt_sha256": SHA_B,
        "high_width": 8192,
        "high_height": 6144,
        "low_width": 4096,
        "low_height": 3072,
        "high_bayer_bytes": 100663296,
        "low_bayer_bytes": 25165824,
        "cfa_phase": "GBRG",
        "iso": 100,
        "exposure": "1/240",
        "white_balance": "5500K",
        "lens_mode": "wide",
        "stabilization": "off",
        "sharpening": "off",
        "lens_correction": "off",
        "fixed_settings": not negative,
        "static_scene": not negative,
        "accepted_by_measurement": not negative,
        "negative_control": negative,
        "expected_reject": negative,
        "rejected_by_measurement": negative,
        "rejection_reason": "alignment mismatch" if negative else "",
    }


def valid_submission() -> dict:
    return {
        "schema": "gpr.production_capture_submission.v1",
        "requirements": [
            {"id": "real_grbg_fixture", "evidence": [fixture("GRBG")]},
            {"id": "real_bggr_fixture", "evidence": [fixture("BGGR")]},
            {
                "id": "mission1_darkframe_stack",
                "evidence": [darkframe("MISSION 1", idx) for idx in range(4)],
            },
            {
                "id": "iphone_cfa_darkframe_stack",
                "evidence": [darkframe("iPhone 15 Pro", idx, iphone=True) for idx in range(4)],
            },
            {
                "id": "mission1_camera_role_receipts",
                "target_role": "camera",
                "source_kind": "real_sensor_dma",
                "valid_gvid": True,
                "dropped_frames": 0,
                "encode_fps": 20.5,
                "preview_fps": 21.0,
                "preview_full_frame": True,
                "receipts": {
                    "target_preflight_receipt": {"sha256": SHA},
                    "labs_target_bench": {"sha256": SHA},
                    "camera_handoff_receipt": {"sha256": SHA},
                    "preview_decode_receipt": {"sha256": SHA},
                    "preview_ui_receipt": {"sha256": SHA},
                    "mission1_camera_closure_run": {"sha256": SHA},
                },
            },
            {
                "id": "controlled_mission1_psf_pairs",
                "pairs": [pair(0), pair(1), pair(2), pair(99, negative=True)],
            },
            {
                "id": "premium_still_sr_promotion_receipts",
                "checkpoint_sha256": SHA,
                "training_config_sha256": SHA,
                "training_target_sha256": SHA,
                "editable_raw_receipt_sha256": SHA,
                "review_dashboard_sha256": SHA,
                "timing_memory_receipt_sha256": SHA,
                "noise_policy_receipt_sha256": SHA,
                "runtime_inputs": [
                    "candidate_raw",
                    "camera_metadata",
                    "validated_noise_sidecar_optional",
                ],
                "full_frame_gate_50mp_passed": True,
                "full_frame_gate_100mp_passed": True,
                "full_frame_gate_50mp_row_count": 8,
                "full_frame_gate_100mp_row_count": 6,
                "median_mae_reduction_pct_50mp": 4.5,
                "median_mae_reduction_pct_100mp": 2.25,
                "worst_row_mae_reduction_pct_50mp": 0.0,
                "worst_row_mae_reduction_pct_100mp": 0.1,
                "editor_latitude_passed": True,
                "no_ref_runtime": True,
                "beats_current_baseline": True,
                "severe_worst_row_failures": False,
                "render_seconds_per_50mp_frame": 120.0,
                "render_seconds_per_100mp_frame": 310.0,
                "peak_rss_gb": 14.5,
                "noise_policy_exact_sidecars_only": True,
                "noise_policy_forbids_source_residual_noise": True,
            },
        ],
    }


def run_tool(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), str(path), *extra],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_capture_submission_", dir=temp_root()) as td:
        work = Path(td)
        manifest = work / "submission.json"
        out_json = work / "audit.json"
        out_html = work / "audit.html"
        manifest.write_text(json.dumps(valid_submission(), indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--json-out", str(out_json), "--html-out", str(out_html))
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        audit = json.loads(out_json.read_text(encoding="utf-8"))
        assert audit["schema"] == "gpr.production_capture_submission_audit.v1"
        assert audit["all_requirements_closed"] is True
        assert audit["pass_count"] == 7
        assert "Production Capture Submission Audit" in out_html.read_text(encoding="utf-8")

        bad = valid_submission()
        bad["requirements"][2]["evidence"] = bad["requirements"][2]["evidence"][:3]
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "mission1_darkframe_stack" in proc.stdout
        assert "need 4" in proc.stdout

        bad = valid_submission()
        bad["requirements"][4]["target_role"] = "pi_stand_in"
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "target_role must be camera" in proc.stdout

        bad = valid_submission()
        bad["requirements"][6]["no_ref_runtime"] = False
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "no_ref_runtime must be true" in proc.stdout

        bad = valid_submission()
        bad["requirements"][6]["runtime_inputs"].append("REF")
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "forbidden render-time input" in proc.stdout

        bad = valid_submission()
        bad["requirements"][6]["median_mae_reduction_pct_100mp"] = 0.0
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "median_mae_reduction_pct_100mp must be > 0" in proc.stdout

        bad = valid_submission()
        bad["requirements"][5]["pairs"][-1]["rejected_by_measurement"] = False
        bad["requirements"][5]["pairs"][-1]["rejection_reason"] = ""
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest)
        assert proc.returncode == 1
        assert "negative control must set expected_reject=true" in proc.stdout

        strict = valid_submission()
        bundle = work / "bundle"
        materialize_path_hashes(strict, bundle, [0])
        manifest.write_text(json.dumps(strict, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode

        bad = json.loads(manifest.read_text(encoding="utf-8"))
        bad["requirements"][0]["evidence"][0]["sha256"] = SHA
        manifest.write_text(json.dumps(bad, indent=2) + "\n", encoding="utf-8")
        proc = run_tool(manifest, "--require-existing-files", "--path-root", str(bundle))
        assert proc.returncode == 1
        assert "sha256 mismatch" in proc.stdout

    print("test_check_production_capture_submission: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
