#!/usr/bin/env python3
"""Generate the closure plan for the Mission 1 numbered-list blockers."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", "/Volumes/OWC_8TB/gpr_work"))


def load_readiness_module():
    path = Path(__file__).resolve().with_name("mission1_numbered_list_readiness.py")
    spec = importlib.util.spec_from_file_location("mission1_numbered_list_readiness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def closure_steps() -> dict[str, dict[str, Any]]:
    return {
        "Mission 1 firmware/camera-side handoff receipt is still required.": {
            "blocker": "Mission 1 firmware/camera-side handoff receipt is still required.",
            "required_receipt": "artifacts/mission1_camera_closure_run_20260625/current_camera/camera_handoff_receipt.json",
            "validator": "tools/check_labs_camera_handoff_receipt.py",
            "closure_run_receipt": "artifacts/mission1_camera_closure_run_20260625/current_camera/mission1_camera_closure_run.json",
            "closure_run_validator": "tools/check_mission1_camera_closure_run.py",
            "validation_command": (
                "python3 tools/check_labs_camera_handoff_receipt.py "
                "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/"
                "current_camera/camera_handoff_receipt.json"
            ),
            "closure_run_command": (
                "python3 tools/run_mission1_camera_closure.py "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera "
                "--raw /dev/mission1/sensor_dma_ring "
                "--target-preflight-receipt /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json "
                "--target-name 'Mission 1' --target-role camera --target-fps 20 --pixel-format 1 "
                "--sensor-dma-executed --storage-handoff-executed --ui-path-executed --visual-checked "
                "--frame-source 'sensor DMA' --write-path 'Mission 1 camera storage .gvid path' "
                "--storage-medium 'Mission 1 SD path' "
                "--storage-ownership 'camera firmware owns write buffer through storage completion' "
                "--display-surface 'Mission 1 rear display' "
                "--presentation-path 'Mission 1 rear display presentation path' "
                "--source-width 4096 --source-height 3072 --capture-width 4096 --capture-height 3072 "
                "--quality 8 --wavelet-levels 1 --no-decimate --direct-gvid --use-mission1-fll2-profile"
            ),
            "closure_run_validation_command": (
                "python3 tools/check_mission1_camera_closure_run.py "
                "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/"
                "current_camera/mission1_camera_closure_run.json"
            ),
            "acceptance": [
                "target.role=camera",
                "target_preflight.target.role=camera",
                "target_preflight.verdict.target_preflight_ready=true",
                "target_preflight.verdict.camera_closure_possible=true",
                "verdict.firmware_ready=true",
                "integration.sensor_dma_handoff.executed=true",
                "integration.storage_handoff.executed=true",
                "verdict.fps_target_met=true",
                "verdict.no_drops=true",
                "output.validation.valid=true",
                "interruption_recovery.proven=true",
            ],
        },
        "Mission 1 camera preview UI receipt is still required.": {
            "blocker": "Mission 1 camera preview UI receipt is still required.",
            "required_receipt": "artifacts/mission1_camera_closure_run_20260625/current_camera/preview_ui_receipt.json",
            "validator": "tools/check_labs_preview_ui_receipt.py",
            "closure_run_receipt": "artifacts/mission1_camera_closure_run_20260625/current_camera/mission1_camera_closure_run.json",
            "closure_run_validator": "tools/check_mission1_camera_closure_run.py",
            "validation_command": (
                "python3 tools/check_labs_preview_ui_receipt.py "
                "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/"
                "current_camera/preview_ui_receipt.json"
            ),
            "closure_run_command": (
                "python3 tools/run_mission1_camera_closure.py "
                "--output-dir /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera "
                "--raw /dev/mission1/sensor_dma_ring "
                "--target-preflight-receipt /Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json "
                "--target-name 'Mission 1' --target-role camera --target-fps 20 --pixel-format 1 "
                "--sensor-dma-executed --storage-handoff-executed --ui-path-executed --visual-checked "
                "--frame-source 'sensor DMA' --write-path 'Mission 1 camera storage .gvid path' "
                "--storage-medium 'Mission 1 SD path' "
                "--storage-ownership 'camera firmware owns write buffer through storage completion' "
                "--display-surface 'Mission 1 rear display' "
                "--presentation-path 'Mission 1 rear display presentation path' "
                "--source-width 4096 --source-height 3072 --capture-width 4096 --capture-height 3072 "
                "--quality 8 --wavelet-levels 1 --no-decimate --direct-gvid --use-mission1-fll2-profile"
            ),
            "closure_run_validation_command": (
                "python3 tools/check_mission1_camera_closure_run.py "
                "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_camera_closure_run_20260625/"
                "current_camera/mission1_camera_closure_run.json"
            ),
            "acceptance": [
                "target.role=camera",
                "target_preflight.target.role=camera",
                "target_preflight.verdict.target_preflight_ready=true",
                "target_preflight.verdict.camera_closure_possible=true",
                "verdict.ui_ready=true",
                "integration.ui_path_executed=true",
                "preview.full_frame_downsample=true",
                "validation.output_valid=true",
                "validation.no_drops=true",
                "validation.visual_checked=true",
                "verdict.fps_target_met=true",
            ],
        },
        "Mission 1 4K cleanup production signoff is blocked by current_4k_cleanup_candidate_degrades_raw_rmse_mae.": {
            "blocker": (
                "Mission 1 4K cleanup production signoff is blocked by "
                "current_4k_cleanup_candidate_degrades_raw_rmse_mae."
            ),
            "required_receipt": "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json",
            "validator": "tools/check_mission1_4k_cleanup_signoff_receipt.py",
            "validation_command": (
                "python3 tools/check_mission1_4k_cleanup_signoff_receipt.py "
                "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_4k_cleanup_visual_signoff_20260625/"
                "production_signoff.json"
            ),
            "build_command": (
                "python3 tools/build_mission1_4k_cleanup_signoff_receipt.py "
                "--output /Volumes/OWC_8TB/gpr_work/artifacts/mission1_4k_cleanup_visual_signoff_20260625/"
                "production_signoff.json --reviewer-name '<reviewer>' --reviewed-at-utc '<UTC>' "
                "--visual-checked --production-ready"
            ),
            "acceptance": [
                "verdict.production_ready=true",
                "verdict.accepted_role=production",
                "objective_visual_signoff.all_checks_passed=true",
                "raw_domain_guard.passed=true",
                "raw_domain_guard.metrics.rmse_improvement_pct.min >= 0",
                "raw_domain_guard.metrics.mae_improvement_pct.min >= 0",
                "raw_domain_guard.metrics.psnr_delta_db.min >= 0",
                "review.visual_checked=true",
                "review.blocking_issues=[]",
            ],
        },
        "Mission 1 8K SR registry candidate remains offline_review_only and needs production promotion evidence.": {
            "blocker": (
                "Mission 1 8K SR registry candidate remains offline_review_only and needs "
                "production promotion evidence."
            ),
            "required_receipt": "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json",
            "validator": "tools/check_mission1_8k_sr_production_promotion.py",
            "validation_command": (
                "python3 tools/check_mission1_8k_sr_production_promotion.py "
                "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_sr_production_promotion_20260625/"
                "production_promotion.json"
            ),
            "build_command": (
                "python3 tools/build_mission1_8k_sr_production_promotion_receipt.py "
                "--output /Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_sr_production_promotion_20260625/"
                "production_promotion.json --visual-review-complete --editable-packaging-proven "
                "--metadata-transplant-proven --production-ready"
            ),
            "acceptance": [
                "candidate.pipeline_id=codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1+demosaic=sips_via_gpr_tools",
                "registry.production_scope=offline_production or production",
                "evidence.runtime_receipt_sha256 is a sha256",
                "evidence.gvid_packaging_receipt_sha256 is a sha256",
                "evidence.prores_receipt_sha256 is a sha256",
                "evidence.visual_review_complete=true",
                "evidence.editable_packaging_proven=true",
                "evidence.metadata_transplant_proven=true",
                "verdict.production_ready=true",
            ],
        },
    }


def build_plan(external_root: Path) -> dict[str, Any]:
    readiness = load_readiness_module()
    report = readiness.build_report(external_root)
    steps_by_blocker = closure_steps()
    blockers = []
    for item in report["items"]:
        for blocker in item["blockers"]:
            step = dict(steps_by_blocker.get(blocker, {}))
            step.update(
                {
                    "item_id": item["id"],
                    "item_title": item["title"],
                    "current_status": item["status"],
                    "current_blocker": blocker,
                }
            )
            blockers.append(step)

    return {
        "schema": "gpr.mission1_numbered_list_closure_plan.v1",
        "external_root": str(external_root),
        "readiness_status": report["overall_status"],
        "production_ready": report["overall_status"] == "production_ready",
        "blockers": blockers,
        "final_gate_command": (
            "python3 tools/mission1_numbered_list_readiness.py "
            f"--external-root {external_root} --require-production"
        ),
    }


def write_markdown(path: Path, plan: dict[str, Any]) -> None:
    lines = [
        "# Mission 1 Numbered-List Closure Plan",
        "",
        f"External root: `{plan['external_root']}`",
        f"Readiness status: `{plan['readiness_status']}`",
        f"Production ready: `{plan['production_ready']}`",
        "",
    ]
    if not plan["blockers"]:
        lines.append("No blockers remain. Run the final gate:")
        lines.extend(["", "```bash", plan["final_gate_command"], "```", ""])
    else:
        for blocker in plan["blockers"]:
            lines.extend(
                [
                    f"## {blocker['item_id']}. {blocker['item_title']}",
                    "",
                    f"Current status: `{blocker['current_status']}`",
                    f"Current blocker: {blocker['current_blocker']}",
                    f"Required receipt: `{blocker['required_receipt']}`",
                    f"Validator: `{blocker['validator']}`",
                    "",
                ]
            )
            if blocker.get("closure_run_command"):
                lines.extend(["Aggregate closure run:", "", "```bash", blocker["closure_run_command"], "```", ""])
            if blocker.get("closure_run_validation_command"):
                lines.extend(
                    [
                        "Aggregate closure validation:",
                        "",
                        "```bash",
                        blocker["closure_run_validation_command"],
                        "```",
                        "",
                    ]
                )
            if blocker.get("build_command"):
                lines.extend(["Build command:", "", "```bash", blocker["build_command"], "```", ""])
            lines.extend(["Validation command:", "", "```bash", blocker["validation_command"], "```", ""])
            lines.append("Acceptance:")
            for row in blocker["acceptance"]:
                lines.append(f"- `{row}`")
            lines.append("")
        lines.extend(["Final gate:", "", "```bash", plan["final_gate_command"], "```", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--output-json", type=Path)
    ap.add_argument("--output-md", type=Path)
    args = ap.parse_args()

    plan = build_plan(args.external_root)
    print(json.dumps(plan, indent=2))

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(args.output_md, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
