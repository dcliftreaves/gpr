#!/usr/bin/env python3
"""Smoke-test Mission 1 native12 8K SR frontier classification."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/mission1_native12_sr_frontier_summary.py"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def import_tool():
    spec = importlib.util.spec_from_file_location("mission1_native12_sr_frontier_summary_smoke", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def summary_payload(
    *,
    checkpoint: str,
    image_count: int,
    rmse_min: float,
    rmse_median: float,
    mae_min: float,
    mae_median: float,
    grad_min: float,
    grad_median: float,
    psnr_min: float,
    psnr_median: float,
    fps_median: float,
) -> dict:
    return {
        "schema": "mission1_sr_fullframe_broad_eval.v1",
        "checkpoint": checkpoint,
        "image_count": image_count,
        "dashboard": checkpoint + ".html",
        "fps_with_write": {"median": fps_median},
        "rmse_improvement_pct": {"min": rmse_min, "median": rmse_median},
        "mae_improvement_pct": {"min": mae_min, "median": mae_median},
        "gradient_mae_improvement_pct": {"min": grad_min, "median": grad_median},
        "model_psnr14_db": {"min": psnr_min, "median": psnr_median},
        "worst_by_rmse_improvement": {"image": "worst-rmse"},
        "worst_by_mae_improvement": {"image": "worst-mae"},
        "worst_by_gradient_mae_improvement": {"image": "worst-gradient"},
    }


def build_fixture(external_root: Path) -> None:
    artifact_root = external_root / "artifacts"
    write_json(
        artifact_root / "mission1_sr_all24_holdout8_fullframe_20260618/summary.json",
        summary_payload(
            checkpoint="t233.pt",
            image_count=8,
            rmse_min=34.0,
            rmse_median=47.6,
            mae_min=21.6,
            mae_median=29.0,
            grad_min=8.2,
            grad_median=14.7,
            psnr_min=47.9,
            psnr_median=54.9,
            fps_median=2.65,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t233_registered_z8_holdout5_regen_fullframe_20260618/summary.json",
        summary_payload(
            checkpoint="t233.pt",
            image_count=5,
            rmse_min=24.9,
            rmse_median=27.4,
            mae_min=6.0,
            mae_median=6.0,
            grad_min=1.57,
            grad_median=1.62,
            psnr_min=51.2,
            psnr_median=51.6,
            fps_median=3.2,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t233_focus_hardrows_fullframe_holdout8_20260618/summary.json",
        summary_payload(
            checkpoint="t233-focus.pt",
            image_count=8,
            rmse_min=37.7,
            rmse_median=49.2,
            mae_min=24.8,
            mae_median=33.4,
            grad_min=9.9,
            grad_median=17.5,
            psnr_min=47.9,
            psnr_median=55.3,
            fps_median=2.6,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t233_focus_hardrows_z8_holdout5_fullframe_20260618/summary.json",
        summary_payload(
            checkpoint="t233-focus.pt",
            image_count=5,
            rmse_min=24.8,
            rmse_median=27.3,
            mae_min=6.0,
            mae_median=6.0,
            grad_min=1.63,
            grad_median=1.68,
            psnr_min=51.1,
            psnr_median=51.6,
            fps_median=3.2,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t233_guardrail_focus_fullframe_holdout8_20260618/summary.json",
        summary_payload(
            checkpoint="t233-guardrail.pt",
            image_count=8,
            rmse_min=37.8,
            rmse_median=48.9,
            mae_min=24.8,
            mae_median=33.6,
            grad_min=9.7,
            grad_median=17.6,
            psnr_min=47.8,
            psnr_median=55.4,
            fps_median=2.6,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t233_guardrail_light_w15_800_fullframe_holdout8_20260618/summary.json",
        summary_payload(
            checkpoint="t233-light.pt",
            image_count=8,
            rmse_min=37.4,
            rmse_median=49.8,
            mae_min=24.9,
            mae_median=33.3,
            grad_min=9.6,
            grad_median=17.3,
            psnr_min=48.0,
            psnr_median=55.4,
            fps_median=2.6,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t233_guardrail_light_w15_800_z8_holdout5_fullframe_20260618/summary.json",
        summary_payload(
            checkpoint="t233-light.pt",
            image_count=5,
            rmse_min=25.8,
            rmse_median=28.2,
            mae_min=6.2,
            mae_median=6.2,
            grad_min=1.68,
            grad_median=1.73,
            psnr_min=51.3,
            psnr_median=51.7,
            fps_median=3.3,
        ),
    )
    write_json(
        artifact_root / "mission1_native12_gvid_to_8k_sr_light_multiframe_20260618/receipt.json",
        {
            "schema": "mission1_native12_gvid_to_8k_sr_multiframe.v1",
            "frames_rendered": 3,
            "max_rss_mb": 1201.0,
            "summary": {
                "fps_median_decode_plus_sr": 2.8,
                "decode_plus_sr_total_s": {"median": 0.357},
            },
        },
    )
    write_json(
        artifact_root / "mission1_native12_gvid_to_8k_sr_light_packaging_q3_20260618/packaging_receipt.json",
        {
            "schema": "mission1_native12_gvid_to_8k_sr_packaging.v2",
            "editable_dng": {"rawpy_open_shape": [6144, 8192]},
            "editable_gpr": {
                "quality": 3,
                "raw_to_gpr_mode": "direct_fallback_after_scratch_failure",
                "readback_metrics": {"psnr14_db": 56.3},
                "gpr_to_dng_rawpy_open_shape": [6144, 8192],
            },
        },
    )
    write_json(
        artifact_root / "mission1_native12_gvid_to_8k_sr_light_wrapper_probe_20260618/summary.json",
        {
            "schema": "mission1_native12_sr_light_wrapper_probe.v1",
            "decision": "q3_direct_fallback_packaging_pass",
        },
    )
    write_json(
        artifact_root / "mission1_sr_t236_holdout8_fullframe_20260618/summary.json",
        summary_payload(
            checkpoint="t236.pt",
            image_count=8,
            rmse_min=32.0,
            rmse_median=53.0,
            mae_min=20.5,
            mae_median=24.0,
            grad_min=8.1,
            grad_median=10.0,
            psnr_min=47.2,
            psnr_median=54.0,
            fps_median=2.6,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t236_gw08_holdout8_fullframe_20260618/summary.json",
        summary_payload(
            checkpoint="t236-gw08.pt",
            image_count=8,
            rmse_min=27.0,
            rmse_median=55.0,
            mae_min=17.0,
            mae_median=23.5,
            grad_min=4.2,
            grad_median=8.9,
            psnr_min=46.9,
            psnr_median=54.8,
            fps_median=2.5,
        ),
    )
    write_json(
        artifact_root / "mission1_sr_t356_holdout8_fullframe_20260618/summary.json",
        summary_payload(
            checkpoint="t356.pt",
            image_count=8,
            rmse_min=24.0,
            rmse_median=52.0,
            mae_min=15.0,
            mae_median=21.0,
            grad_min=3.2,
            grad_median=7.4,
            psnr_min=46.6,
            psnr_median=54.4,
            fps_median=2.6,
        ),
    )


def main() -> int:
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mission1_sr_frontier_", dir=work_parent) as td:
        external_root = Path(td)
        build_fixture(external_root)
        tool = import_tool()
        summary = tool.build_summary(external_root)

    assert summary["schema"] == "mission1_native12_sr_frontier_summary.v1"
    assert summary["decision"] == "promoted_registered_offline_candidate"
    by_profile = {row["profile"]: row for row in summary["profiles"]}
    assert by_profile["t233_registered"]["status"] == "registered_offline_candidate"
    assert by_profile["t233_registered"]["gate_pass"] is True
    assert by_profile["t233_focus_hardrows_2500"]["status"] == "hold_boundary_not_promoted"
    assert by_profile["t233_focus_hardrows_2500"]["gate_pass"] is True
    assert by_profile["t233_focus_hardrows_2500"]["requires_z8_guardrail"] is True
    assert by_profile["t233_focus_hardrows_2500"]["z8_rmse_improvement_min"] == 24.8
    assert "regresses regenerated Z8 guardrail metrics" in by_profile["t233_focus_hardrows_2500"]["decision_reason"]
    assert by_profile["t233_guardrail_focus_1500"]["status"] == "hold_boundary_not_promoted"
    assert by_profile["t233_guardrail_focus_1500"]["gate_pass"] is True
    assert by_profile["t233_guardrail_light_w15_800"]["status"] == "registered_offline_candidate"
    assert by_profile["t233_guardrail_light_w15_800"]["registered"] is True
    assert by_profile["t233_guardrail_light_w15_800"]["gate_pass"] is True
    assert by_profile["t233_guardrail_light_w15_800"]["requires_packaging"] is True
    assert by_profile["t233_guardrail_light_w15_800"]["requires_z8_guardrail"] is True
    assert by_profile["t233_guardrail_light_w15_800"]["z8_rmse_improvement_min"] == 25.8
    assert by_profile["t233_guardrail_light_w15_800"]["packaging_gpr_psnr14_db"] == 56.3
    assert by_profile["t233_guardrail_light_w15_800"]["packaging_raw_to_gpr_mode"] == "direct_fallback_after_scratch_failure"
    assert by_profile["t233_guardrail_light_w15_800"]["worst_gradient_image"] == "worst-gradient"
    assert "registered as an offline 8K candidate" in by_profile["t233_guardrail_light_w15_800"]["decision_reason"]
    assert by_profile["t236_ch2lh3"]["status"] == "hold_boundary_not_promoted"
    assert by_profile["t236_ch2lh3"]["gate_pass"] is True
    assert by_profile["t236_ch2lh3_gw08"]["status"] == "rejected_worst_row_regression"
    assert by_profile["t356_ch2lh3"]["status"] == "rejected_worst_row_regression"
    assert "T233" in summary["production_direction"]

    with tempfile.TemporaryDirectory(prefix="mission1_sr_frontier_bad_packaging_", dir=work_parent) as td:
        bad_root = Path(td)
        build_fixture(bad_root)
        write_json(
            bad_root
            / "artifacts/mission1_native12_gvid_to_8k_sr_light_packaging_q3_20260618/packaging_receipt.json",
            {
                "schema": "mission1_native12_gvid_to_8k_sr_packaging.v2",
                "editable_dng": {"rawpy_open_shape": [6144, 8192]},
                "editable_gpr": {
                    "quality": 3,
                    "raw_to_gpr_mode": "direct_fallback_after_scratch_failure",
                    "readback_metrics": {"psnr14_db": 49.9},
                    "gpr_to_dng_rawpy_open_shape": [6144, 8192],
                },
            },
        )
        bad_summary = tool.build_summary(bad_root)
    bad_by_profile = {row["profile"]: row for row in bad_summary["profiles"]}
    bad_light = bad_by_profile["t233_guardrail_light_w15_800"]
    assert bad_light["gate_pass"] is True
    assert bad_light["requires_packaging"] is True
    assert bad_light["status"] == "hold_boundary_not_promoted"
    assert "runtime or packaging receipt is below promotion floor" in bad_light["decision_reason"]

    with tempfile.TemporaryDirectory(prefix="mission1_sr_frontier_bad_wrapper_", dir=work_parent) as td:
        bad_root = Path(td)
        build_fixture(bad_root)
        write_json(
            bad_root
            / "artifacts/mission1_native12_gvid_to_8k_sr_light_wrapper_probe_20260618/summary.json",
            {
                "schema": "mission1_native12_sr_light_wrapper_probe.v1",
                "decision": "q3_wrapper_status_unknown",
            },
        )
        bad_summary = tool.build_summary(bad_root)
    bad_by_profile = {row["profile"]: row for row in bad_summary["profiles"]}
    bad_light = bad_by_profile["t233_guardrail_light_w15_800"]
    assert bad_light["gate_pass"] is True
    assert bad_light["requires_packaging"] is True
    assert bad_light["status"] == "hold_boundary_not_promoted"
    assert "runtime or packaging receipt is below promotion floor" in bad_light["decision_reason"]

    with tempfile.TemporaryDirectory(prefix="mission1_sr_frontier_bad_pack_mode_", dir=work_parent) as td:
        bad_root = Path(td)
        build_fixture(bad_root)
        write_json(
            bad_root
            / "artifacts/mission1_native12_gvid_to_8k_sr_light_packaging_q3_20260618/packaging_receipt.json",
            {
                "schema": "mission1_native12_gvid_to_8k_sr_packaging.v2",
                "editable_dng": {"rawpy_open_shape": [6144, 8192]},
                "editable_gpr": {
                    "quality": 3,
                    "raw_to_gpr_mode": "scratch_wrapper_only",
                    "readback_metrics": {"psnr14_db": 56.3},
                    "gpr_to_dng_rawpy_open_shape": [6144, 8192],
                },
            },
        )
        bad_summary = tool.build_summary(bad_root)
    bad_by_profile = {row["profile"]: row for row in bad_summary["profiles"]}
    bad_light = bad_by_profile["t233_guardrail_light_w15_800"]
    assert bad_light["gate_pass"] is True
    assert bad_light["requires_packaging"] is True
    assert bad_light["status"] == "hold_boundary_not_promoted"
    assert "runtime or packaging receipt is below promotion floor" in bad_light["decision_reason"]

    print("test_mission1_native12_sr_frontier_summary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
