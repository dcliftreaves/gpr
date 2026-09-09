#!/usr/bin/env python3
"""Summarize Mission 1 native12 12MP-to-8K SR frontier evidence."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any


PROFILES = {
    "t233_registered": {
        "summary": "mission1_sr_all24_holdout8_fullframe_20260618/summary.json",
        "z8_regenerated_summary": "mission1_sr_t233_registered_z8_holdout5_regen_fullframe_20260618/summary.json",
        "codec": "mission1_native12_t233",
        "registered": True,
    },
    "t233_focus_hardrows_2500": {
        "summary": "mission1_sr_t233_focus_hardrows_fullframe_holdout8_20260618/summary.json",
        "z8_regenerated_summary": "mission1_sr_t233_focus_hardrows_z8_holdout5_fullframe_20260618/summary.json",
        "codec": "mission1_native12_t233",
        "registered": False,
        "requires_z8_guardrail": True,
    },
    "t233_guardrail_focus_1500": {
        "summary": "mission1_sr_t233_guardrail_focus_fullframe_holdout8_20260618/summary.json",
        "codec": "mission1_native12_t233",
        "registered": False,
    },
    "t233_guardrail_light_w15_800": {
        "summary": "mission1_sr_t233_guardrail_light_w15_800_fullframe_holdout8_20260618/summary.json",
        "z8_regenerated_summary": "mission1_sr_t233_guardrail_light_w15_800_z8_holdout5_fullframe_20260618/summary.json",
        "multiframe_receipt": "mission1_native12_gvid_to_8k_sr_light_multiframe_20260618/receipt.json",
        "packaging_receipt": "mission1_native12_gvid_to_8k_sr_light_packaging_q3_20260618/packaging_receipt.json",
        "wrapper_probe": "mission1_native12_gvid_to_8k_sr_light_wrapper_probe_20260618/summary.json",
        "codec": "mission1_native12_t233",
        "registered": True,
        "requires_packaging": True,
        "requires_z8_guardrail": True,
    },
    "t236_ch2lh3": {
        "summary": "mission1_sr_t236_holdout8_fullframe_20260618/summary.json",
        "codec": "mission1_native12_t236_ch2lh3",
        "registered": False,
    },
    "t236_ch2lh3_gw08": {
        "summary": "mission1_sr_t236_gw08_holdout8_fullframe_20260618/summary.json",
        "codec": "mission1_native12_t236_ch2lh3",
        "registered": False,
    },
    "t356_ch2lh3": {
        "summary": "mission1_sr_t356_holdout8_fullframe_20260618/summary.json",
        "codec": "mission1_native12_t356_ch2lh3",
        "registered": False,
    },
}

THRESHOLDS = {
    "image_count_min": 8,
    "rmse_improvement_min": 30.0,
    "mae_improvement_min": 20.0,
    "gradient_improvement_min": 8.0,
    "psnr14_min": 47.0,
    "fps_with_write_min": 2.0,
}


def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def stat(summary: dict[str, Any], key: str, field: str) -> float:
    value = summary.get(key)
    if isinstance(value, dict):
        return float(value.get(field, 0.0))
    return 0.0


def worst_image(summary: dict[str, Any], key: str) -> str | None:
    row = summary.get(key)
    if isinstance(row, dict):
        image = row.get("image")
        return str(image) if image is not None else None
    return None


def add_z8_guardrail(row: dict[str, Any], cfg: dict[str, Any], artifact_root: Path) -> None:
    summary_name = cfg.get("z8_regenerated_summary")
    if not summary_name:
        return
    path = artifact_root / summary_name
    summary = read_json(path)
    row.update(
        {
            "z8_regenerated_summary": str(path),
            "z8_image_count": int(summary.get("image_count", 0)),
            "z8_rmse_improvement_min": stat(summary, "rmse_improvement_pct", "min"),
            "z8_mae_improvement_min": stat(summary, "mae_improvement_pct", "min"),
            "z8_gradient_improvement_min": stat(summary, "gradient_mae_improvement_pct", "min"),
            "z8_psnr14_min": stat(summary, "model_psnr14_db", "min"),
            "z8_worst_rmse_image": worst_image(summary, "worst_by_rmse_improvement"),
        }
    )


def add_runtime_packaging(row: dict[str, Any], cfg: dict[str, Any], artifact_root: Path) -> None:
    multiframe_name = cfg.get("multiframe_receipt")
    if multiframe_name:
        path = artifact_root / multiframe_name
        receipt = read_json(path)
        timing = (receipt.get("summary") or {}).get("decode_plus_sr_total_s") or {}
        row.update(
            {
                "multiframe_receipt": str(path),
                "multiframe_frames": int(receipt.get("frames_rendered", 0)),
                "multiframe_fps_median": float((receipt.get("summary") or {}).get("fps_median_decode_plus_sr", 0.0)),
                "multiframe_median_s": float(timing.get("median", 0.0)),
                "multiframe_max_rss_mb": float(receipt.get("max_rss_mb", 0.0)),
            }
        )
    packaging_name = cfg.get("packaging_receipt")
    if packaging_name:
        path = artifact_root / packaging_name
        receipt = read_json(path)
        gpr = receipt.get("editable_gpr") or {}
        gpr_metrics = gpr.get("readback_metrics") or {}
        row.update(
            {
                "packaging_receipt": str(path),
                "packaging_gpr_quality": int(gpr.get("quality", -1)),
                "packaging_raw_to_gpr_mode": str(gpr.get("raw_to_gpr_mode", "")),
                "packaging_gpr_psnr14_db": float(gpr_metrics.get("psnr14_db", 0.0)),
                "packaging_dng_shape": (receipt.get("editable_dng") or {}).get("rawpy_open_shape"),
                "packaging_gpr_dng_shape": gpr.get("gpr_to_dng_rawpy_open_shape"),
            }
        )
    wrapper_name = cfg.get("wrapper_probe")
    if wrapper_name:
        path = artifact_root / wrapper_name
        probe = read_json(path)
        row.update(
            {
                "wrapper_probe": str(path),
                "wrapper_probe_decision": probe.get("decision"),
            }
        )


def summarize_profile(profile_id: str, cfg: dict[str, Any], artifact_root: Path) -> dict[str, Any]:
    path = artifact_root / cfg["summary"]
    summary = read_json(path)
    row = {
        "profile": profile_id,
        "codec": cfg["codec"],
        "registered": bool(cfg["registered"]),
        "requires_packaging": bool(cfg.get("requires_packaging")),
        "requires_z8_guardrail": bool(cfg.get("requires_z8_guardrail")),
        "summary": str(path),
        "checkpoint": summary.get("checkpoint"),
        "dashboard": summary.get("dashboard"),
        "image_count": int(summary.get("image_count", 0)),
        "fps_with_write_median": stat(summary, "fps_with_write", "median"),
        "rmse_improvement_min": stat(summary, "rmse_improvement_pct", "min"),
        "rmse_improvement_median": stat(summary, "rmse_improvement_pct", "median"),
        "mae_improvement_min": stat(summary, "mae_improvement_pct", "min"),
        "mae_improvement_median": stat(summary, "mae_improvement_pct", "median"),
        "gradient_improvement_min": stat(summary, "gradient_mae_improvement_pct", "min"),
        "gradient_improvement_median": stat(summary, "gradient_mae_improvement_pct", "median"),
        "psnr14_min": stat(summary, "model_psnr14_db", "min"),
        "psnr14_median": stat(summary, "model_psnr14_db", "median"),
        "worst_rmse_image": worst_image(summary, "worst_by_rmse_improvement"),
        "worst_mae_image": worst_image(summary, "worst_by_mae_improvement"),
        "worst_gradient_image": (
            worst_image(summary, "worst_by_gradient_mae_improvement")
            or worst_image(summary, "worst_by_gradient_improvement")
        ),
    }
    row["gate_pass"] = (
        row["image_count"] >= THRESHOLDS["image_count_min"]
        and row["rmse_improvement_min"] >= THRESHOLDS["rmse_improvement_min"]
        and row["mae_improvement_min"] >= THRESHOLDS["mae_improvement_min"]
        and row["gradient_improvement_min"] >= THRESHOLDS["gradient_improvement_min"]
        and row["psnr14_min"] >= THRESHOLDS["psnr14_min"]
        and row["fps_with_write_median"] >= THRESHOLDS["fps_with_write_min"]
    )
    add_z8_guardrail(row, cfg, artifact_root)
    add_runtime_packaging(row, cfg, artifact_root)
    return row


def classify(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    by_id = {row["profile"]: row for row in rows}
    registered = by_id.get("t233_registered")
    if not registered:
        return "missing_registered_t233", rows

    for row in rows:
        status = "diagnostic"
        reasons: list[str] = []
        if row["profile"] == "t233_registered":
            status = "registered_offline_candidate"
            reasons.append("registered pipeline and broad holdout gate pass")
        elif not row["gate_pass"]:
            status = "rejected_worst_row_regression"
            reasons.append("fails broad holdout thresholds")
        else:
            worse_than_registered = []
            for metric in (
                "rmse_improvement_min",
                "mae_improvement_min",
                "gradient_improvement_min",
                "psnr14_min",
            ):
                if float(row[metric]) < float(registered[metric]):
                    worse_than_registered.append(metric)
            if worse_than_registered:
                status = "hold_boundary_not_promoted"
                reasons.append("passes thresholds but worsens registered worst-row metrics: " + ",".join(worse_than_registered))
            else:
                status = "promotion_candidate"
                reasons.append("passes broad holdout and does not worsen registered worst-row metrics")

            if row.get("z8_regenerated_summary") and registered.get("z8_regenerated_summary"):
                z8_worse = []
                for metric in (
                    "z8_rmse_improvement_min",
                    "z8_mae_improvement_min",
                    "z8_gradient_improvement_min",
                    "z8_psnr14_min",
                ):
                    if float(row.get(metric, 0.0)) < float(registered.get(metric, 0.0)):
                        z8_worse.append(metric)
                if z8_worse:
                    status = "hold_boundary_not_promoted"
                    reasons.append("regresses regenerated Z8 guardrail metrics: " + ",".join(z8_worse))
                elif not z8_worse:
                    reasons.append("regenerated Z8 guardrail is no worse than registered T233")

            if row.get("packaging_receipt"):
                raw_to_gpr_mode = str(row.get("packaging_raw_to_gpr_mode", ""))
                wrapper_decision = str(row.get("wrapper_probe_decision", ""))
                packaging_ok = (
                    int(row.get("packaging_gpr_quality", -1)) == 3
                    and float(row.get("packaging_gpr_psnr14_db", 0.0)) >= 50.0
                    and "direct" in raw_to_gpr_mode
                    and "fallback" in raw_to_gpr_mode
                    and row.get("packaging_dng_shape") == [6144, 8192]
                    and row.get("packaging_gpr_dng_shape") == [6144, 8192]
                    and float(row.get("multiframe_fps_median", 0.0)) >= 2.5
                    and wrapper_decision.startswith("q3_direct_fallback_packaging_pass")
                )
                if packaging_ok:
                    reasons.append("runtime and q3 packaging receipts pass")
                elif row.get("requires_packaging"):
                    status = "hold_boundary_not_promoted"
                    reasons.append("runtime or packaging receipt is below promotion floor")

            if row["codec"] != registered["codec"]:
                reasons.append("codec path is not the registered production capture profile")

            if row.get("registered") and status == "promotion_candidate":
                status = "registered_offline_candidate"
                reasons.append("registered as an offline 8K candidate")

        row["status"] = status
        row["decision_reason"] = "; ".join(reasons)

    promotion_candidates = [row for row in rows if row.get("status") == "promotion_candidate"]
    promoted_candidates = [
        row for row in rows
        if row.get("status") == "registered_offline_candidate" and row.get("profile") != "t233_registered"
    ]
    if promoted_candidates:
        decision = "promoted_registered_offline_candidate"
    elif promotion_candidates:
        decision = "candidate_ready_for_registry_review"
    elif registered.get("gate_pass") is True:
        decision = "keep_registered_t233"
    else:
        decision = "registered_sr_blocked"
    return decision, rows


def build_summary(external_root: Path) -> dict[str, Any]:
    artifact_root = external_root / "artifacts"
    rows = [
        summarize_profile(profile_id, cfg, artifact_root)
        for profile_id, cfg in PROFILES.items()
    ]
    decision, rows = classify(rows)
    return {
        "schema": "mission1_native12_sr_frontier_summary.v1",
        "artifact_root": str(artifact_root),
        "thresholds": THRESHOLDS,
        "decision": decision,
        "profiles": rows,
        "production_direction": (
            "Use T233 for native-12 capture. The guardrail-light SR checkpoint is now "
            "registered as an offline 12MP-to-8K candidate because it preserves the "
            "T233 codec boundary, passes broad Mission and regenerated Z8 guardrails, "
            "and has runtime plus q3 packaging receipts. Hold T236/T356 as "
            "codec-boundary evidence until a candidate improves worst-row texture/detail "
            "metrics without regressing registered broad-holdout minima and until its "
            "codec path is promoted for capture."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--external-root",
        type=Path,
        default=Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root())),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    summary = build_summary(args.external_root)
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
