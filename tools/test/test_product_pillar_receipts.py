#!/usr/bin/env python3
"""Smoke-test high-level product-pillar receipt schemas."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "tools/check_product_pillar_receipts.py"
SHA = "a" * 64


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def import_checker():
    spec = importlib.util.spec_from_file_location("check_product_pillar_receipts", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def artifact(name: str) -> dict:
    return {"path": f"artifacts/product_pillar_fixture/{name}", "sha256": SHA}


def noise_receipt() -> dict:
    plane = {
        "noise_profile_scale": 0.00012,
        "noise_profile_offset": 0.000001,
        "sigma_black": 1.2,
    }
    return {
        "schema": "gpr.camera_noise_calibration.v1",
        "camera": {
            "make": "Fixture",
            "model": "Large Bayer",
            "bit_depth": 14,
            "cfa_phase": "GBRG",
            "black_level": 64,
            "white_level": 16383,
        },
        "calibrations": [
            {
                "iso": 1600,
                "source_kind": "darkframes",
                "sample_count": 16,
                "source": artifact("darkframes.json"),
                "per_plane": {"r": plane, "g1": plane, "b": plane, "g2": plane},
                "noise_signal_audit": {
                    "separates_noise_from_signal": True,
                    "method": "darkframe_stack_sigma",
                    "evidence": "darkframes contain no scene signal",
                },
                "usable_for_training_targets": True,
            }
        ],
        "production_ready": True,
    }


def still_sr_receipt() -> dict:
    return {
        "schema": "gpr.premium_still_sr_gate.v1",
        "candidate": {
            "pipeline_id": "fixture_still_sr_v1",
            "checkpoint_sha256": SHA,
            "target_role": "offline_premium_still",
        },
        "fixture_summary": {
            "camera_count": 2,
            "fifty_mp_or_larger_count": 4,
            "hundred_mp_or_larger_count": 2,
            "cfa_phases": ["RGGB", "GBRG"],
        },
        "outputs": {
            "editable_dng": artifact("still_sr.dng"),
            "editable_gpr": artifact("still_sr.gpr"),
            "review_tiff_or_prores": artifact("still_sr_review.tiff"),
            "dashboard": artifact("still_sr_dashboard/index.html"),
        },
        "baseline_comparison": {
            "passed_gate": True,
            "worst_lpips": 0.02,
            "worst_delta_e2000": 1.3,
            "min_raw_psnr_delta_db": 0.4,
            "editor_latitude_score_delta": 0.2,
        },
        "noise_policy": {
            "mode": "calibrated_darkframe_sidecar",
            "raw_noise_signal_audit_passed": True,
        },
        "production_ready": True,
    }


def psf_receipt() -> dict:
    return {
        "schema": "gpr.bayer_resize_psf_receipt.v1",
        "psf_model": {
            "model_id": "fixture_resize_psf_v1",
            "estimation_method": "sharp_edges_plus_texture_pairs",
            "kernel_width_px": 3.4,
            "kernel_height_px": 3.1,
            "fit_rmse_px": 0.12,
        },
        "dataset": {
            "pair_count": 42,
            "sharp_edge_count": 12,
            "texture_field_count": 18,
            "cfa_phases": ["RGGB", "GBRG"],
        },
        "gate_results": {
            "mission42_passed": True,
            "z8_all24_passed": True,
            "min_raw_psnr_delta_db": 0.3,
            "min_gradient_mae_improvement_pct": 2.0,
        },
        "receipts": {
            "gvid": artifact("sr.gvid"),
            "editable_dng_or_gpr": artifact("sr.dng"),
            "prores": artifact("sr.mov"),
            "timing_memory": artifact("timing_memory.json"),
        },
        "production_ready": True,
    }


def expect_ok(module, payload: dict) -> None:
    failures = module.validate_receipt(payload)
    assert failures == [], failures


def expect_fail(module, payload: dict, needle: str) -> None:
    failures = module.validate_receipt(payload)
    assert any(needle in failure for failure in failures), failures


def main() -> int:
    module = import_checker()

    receipts = [noise_receipt(), still_sr_receipt(), psf_receipt()]
    for payload in receipts:
        expect_ok(module, payload)

    bad_noise = copy.deepcopy(receipts[0])
    bad_noise["calibrations"][0]["noise_signal_audit"]["separates_noise_from_signal"] = False
    expect_fail(module, bad_noise, "noise/signal audit")

    bad_still = copy.deepcopy(receipts[1])
    bad_still["fixture_summary"]["hundred_mp_or_larger_count"] = 0
    expect_fail(module, bad_still, "100 MP-class")

    bad_psf = copy.deepcopy(receipts[2])
    bad_psf["gate_results"]["z8_all24_passed"] = False
    expect_fail(module, bad_psf, "z8_all24_passed")

    with tempfile.TemporaryDirectory(prefix="gpr_product_pillar_receipts_", dir=temp_root()) as tmp:
        paths = []
        for idx, payload in enumerate(receipts):
            path = Path(tmp) / f"receipt_{idx}.json"
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            paths.append(path)
        subprocess.run([sys.executable, str(CHECKER), *map(str, paths)], check=True)

    print("test_product_pillar_receipts: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
