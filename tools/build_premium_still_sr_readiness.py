#!/usr/bin/env python3
"""Build the current premium still-SR readiness receipt.

This is a productization audit over existing evidence, not a trainer. It keeps
the "spend time for an amazing still" pillar honest by emitting a valid
premium still-SR receipt and an explicit blocker list from the current repo and
external artifact state.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.premium_still_sr_readiness.v1"
GATE_SCHEMA = "gpr.premium_still_sr_gate.v1"

STILL_BASELINES = [
    {
        "tier": "STILL smallest",
        "pipeline": "gpr_tools_q0 + bibo1x_ane_gpr_tools_q3",
        "mean_mb": 9.80,
        "worst_lpips": 0.031,
        "verdict": "PASS",
    },
    {
        "tier": "STILL primary",
        "pipeline": "gpr_tools_q3 + bibo1x_ane_gpr_tools_q3",
        "mean_mb": 15.05,
        "worst_lpips": 0.016,
        "verdict": "PASS",
    },
    {
        "tier": "STILL archival",
        "pipeline": "gpr_tools_q8",
        "mean_mb": 27.17,
        "worst_lpips": 0.004,
        "verdict": "PASS",
    },
]

CAPABILITY_EVIDENCE = [
    {
        "camera": "Nikon Z8",
        "class": "50 MP",
        "dimensions": "8280x5520",
        "bit_depth": 14,
        "cfa_phase": "RGGB",
        "encode_ms": 133.5,
        "decode_ms": 243.2,
        "compressed_pct": 6.78,
        "roundtrip_psnr_db": 53.85,
    },
    {
        "camera": "Hasselblad X2D 100C",
        "class": "100 MP",
        "dimensions": "11664x8750",
        "bit_depth": 16,
        "cfa_phase": "RGGB",
        "encode_ms": 260.0,
        "decode_ms": 427.1,
        "compressed_pct": 4.89,
        "roundtrip_psnr_db": 53.52,
    },
]

REUSABLE_SR_ARTIFACTS = {
    "editable_dng": "artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_editable_packaging_frame0/frame_000000_sr8k_generic.dng",
    "editable_gpr": "artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_editable_packaging_frame0/frame_000000_sr8k_sdk_wrapped.gpr",
    "review_tiff_or_prores": "artifacts/mission1_8k_sr_production_promotion_20260625/current_candidate_editable_packaging_frame0/frame_000000_sr8k_review_2k_prores.mov",
    "video_sr_promotion": "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json",
    "cnn_scorecard": "artifacts/cnn_product_scorecard_20260629/scorecard.json",
}

DEDICATED_STILL_SR_ARTIFACTS = {
    "fixture_manifest": "artifacts/premium_still_sr_fixture_manifest_20260629/fixture_manifest.json",
    "pair_set": "artifacts/premium_still_sr_pairs_20260629/premium_still_sr_pairs.npz",
    "pair_set_sidecar": "artifacts/premium_still_sr_pairs_20260629/premium_still_sr_pairs.npz.json",
    "smoke_checkpoint": "artifacts/premium_still_sr_candidate_smoke_20260629/premium_still_sr_smoke_w24_d4_120.pt",
    "smoke_training_receipt": "artifacts/premium_still_sr_candidate_smoke_20260629/premium_still_sr_smoke_w24_d4_120.pt.json",
    "large_pair_set": "artifacts/premium_still_sr_pairs_large_20260629/premium_still_sr_pairs_64t.npz",
    "large_pair_set_sidecar": "artifacts/premium_still_sr_pairs_large_20260629/premium_still_sr_pairs_64t.npz.json",
    "large_checkpoint": "artifacts/premium_still_sr_candidate_large_20260629/premium_still_sr_w32_d5_1000_x2dholdout.pt",
    "large_training_receipt": "artifacts/premium_still_sr_candidate_large_20260629/premium_still_sr_w32_d5_1000_x2dholdout.pt.json",
    "candidate_metric_dashboard": "artifacts/premium_still_sr_candidate_dashboard_20260629/index.html",
    "candidate_metric_dashboard_summary": "artifacts/premium_still_sr_candidate_dashboard_20260629/candidate_dashboard.json",
    "candidate_visual_dashboard": "artifacts/premium_still_sr_visual_review_20260629/index.html",
    "candidate_visual_dashboard_summary": "artifacts/premium_still_sr_visual_review_20260629/visual_review.json",
    "latest_hf_residual_dashboard": "artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/index.html",
    "latest_hf_residual_checkpoint": "artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/premium_still_sr_x2d_hf_residual_noise_multiscale_w96.pt",
    "latest_hf_residual_train_receipt": "artifacts/premium_still_sr_x2d_multiscene_hf_residual_model_sceneholdout_noise_multiscale_w96_20260630/train_receipt.json",
}


def external_root() -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, str]:
    return {"path": path.as_posix(), "sha256": sha256_file(path)}


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def external_artifact(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    item: dict[str, Any] = {"path": path.as_posix(), "exists": path.is_file()}
    if path.is_file():
        item["sha256"] = sha256_file(path)
        item["bytes"] = path.stat().st_size
    return item


def summarize_noise_sidecars(root: Path) -> dict[str, Any]:
    sidecar_root = root / "artifacts/camera_noise_sidecars_20260629"
    paths = sorted(sidecar_root.glob("*/*_noise_calibration.json"))
    cameras: dict[str, dict[str, Any]] = {}
    usable_count = 0
    for path in paths:
        data = load_json(path) or {}
        camera = data.get("camera") if isinstance(data.get("camera"), dict) else {}
        key = f"{camera.get('make', 'unknown')} {camera.get('model', 'unknown')}".strip()
        if key not in cameras:
            cameras[key] = {"sidecar_count": 0, "usable_calibrations": 0, "isos": []}
        cameras[key]["sidecar_count"] += 1
        for cal in data.get("calibrations", []):
            if not isinstance(cal, dict):
                continue
            if cal.get("iso") is not None:
                cameras[key]["isos"].append(cal["iso"])
            if cal.get("usable_for_training_targets") is True:
                usable_count += 1
                cameras[key]["usable_calibrations"] += 1
    for item in cameras.values():
        item["isos"] = sorted(set(item["isos"]))
    return {
        "sidecar_root": sidecar_root.as_posix(),
        "sidecar_count": len(paths),
        "usable_calibration_count": usable_count,
        "camera_count": len(cameras),
        "cameras": cameras,
        "has_x2d_and_z8": any("X2D" in k for k in cameras) and any("Z 8" in k or "Z8" in k for k in cameras),
    }


def stat_metric(data: dict[str, Any] | None, split: str, metric: str, stat: str) -> float | None:
    if not isinstance(data, dict):
        return None
    cur: Any = data.get("eval", {}).get(split, {}).get(metric, {}).get(stat)
    return float(cur) if isinstance(cur, (int, float)) else None


def summarize_latest_hf_residual_probe(root: Path, dedicated: dict[str, dict[str, Any]]) -> dict[str, Any]:
    receipt_info = dedicated["latest_hf_residual_train_receipt"]
    path = Path(receipt_info["path"])
    receipt = load_json(path) if path.is_file() else None
    policy = receipt.get("policy", {}) if isinstance(receipt, dict) else {}
    config = receipt.get("config", {}) if isinstance(receipt, dict) else {}
    return {
        "exists": bool(receipt),
        "receipt_path": receipt_info["path"],
        "dashboard_path": dedicated["latest_hf_residual_dashboard"]["path"],
        "checkpoint_path": dedicated["latest_hf_residual_checkpoint"]["path"],
        "schema": receipt.get("schema") if isinstance(receipt, dict) else None,
        "checkpoint_sha256": receipt.get("checkpoint_sha256") if isinstance(receipt, dict) else None,
        "production_status": policy.get("production_status"),
        "uses_source_hf_at_training": bool(policy.get("uses_source_hf_at_training")) if isinstance(policy, dict) else None,
        "uses_source_hf_at_runtime": bool(policy.get("uses_source_hf_at_runtime")) if isinstance(policy, dict) else None,
        "runtime_inputs": policy.get("runtime_inputs") if isinstance(policy, dict) else None,
        "feature_mode": config.get("feature_mode") if isinstance(config, dict) else None,
        "holdout_scene": config.get("holdout_scene") if isinstance(config, dict) else None,
        "train_seconds": receipt.get("train_seconds") if isinstance(receipt, dict) else None,
        "steps": receipt.get("steps") if isinstance(receipt, dict) else None,
        "train_row_count": receipt.get("eval", {}).get("train", {}).get("row_count") if isinstance(receipt, dict) else None,
        "holdout_row_count": receipt.get("eval", {}).get("holdout", {}).get("row_count") if isinstance(receipt, dict) else None,
        "train_residual_mae_reduction_pct_median": stat_metric(receipt, "train", "residual_mae_reduction_pct", "median"),
        "train_residual_rmse_reduction_pct_median": stat_metric(receipt, "train", "residual_rmse_reduction_pct", "median"),
        "holdout_residual_mae_reduction_pct_median": stat_metric(receipt, "holdout", "residual_mae_reduction_pct", "median"),
        "holdout_residual_rmse_reduction_pct_median": stat_metric(receipt, "holdout", "residual_rmse_reduction_pct", "median"),
        "promotion_ready": False,
        "promotion_reason": "diagnostic no-REF HF residual probe; holdout recovery is too small and no full still/editor-latitude gate is passed",
    }


def write_json(path: Path, payload: dict[str, Any]) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact_ref(path)


def build_state(root: Path) -> dict[str, Any]:
    external = {name: external_artifact(root, rel) for name, rel in REUSABLE_SR_ARTIFACTS.items()}
    dedicated = {name: external_artifact(root, rel) for name, rel in DEDICATED_STILL_SR_ARTIFACTS.items()}
    noise = summarize_noise_sidecars(root)
    latest_hf = summarize_latest_hf_residual_probe(root, dedicated)
    has_video_sr_packaging = all(external[name]["exists"] for name in ("editable_dng", "editable_gpr", "review_tiff_or_prores"))
    blockers = [
        "The dedicated premium still-SR candidates are not production-grade: the early smoke run is effectively flat, and the first larger run peaks at about 0.15 percent held-out X2D RMSE improvement before overfitting/regressing.",
        "The latest X2D no-REF HF residual probe uses noise sidecar scalars and no source HF at runtime, but holdout median recovery is still only about 2.56 percent MAE and 2.86 percent RMSE.",
        "The current premium still-SR visual evidence is diagnostic; no candidate has passed a full still/editor-latitude promotion gate against STILL q0/q3/q8 baselines.",
        "Noise sidecars exist for X2D/Z8, but the successful policy is still only a conditioning probe, not a proven noise-removal/addback production target.",
    ]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "repo": str(ROOT),
            "external_root": str(root),
        },
        "goal": "premium offline still SR for 50 MP and 100 MP Bayer cameras",
        "production_ready": False,
        "current_verdict": "blocked_on_dedicated_premium_still_sr_candidate",
        "still_baselines": STILL_BASELINES,
        "capability_evidence": CAPABILITY_EVIDENCE,
        "noise_sidecars": noise,
        "reusable_sr_artifacts": external,
        "dedicated_still_sr_artifacts": dedicated,
        "evidence_summary": {
            "has_50mp_still_roundtrip": True,
            "has_100mp_still_roundtrip": True,
            "has_validated_x2d_z8_noise_sidecars": noise["has_x2d_and_z8"] and noise["usable_calibration_count"] > 0,
            "has_reusable_editable_sr_packaging": has_video_sr_packaging,
            "has_dedicated_premium_still_sr_fixture_manifest": dedicated["fixture_manifest"]["exists"],
            "has_dedicated_premium_still_sr_pairs": dedicated["pair_set"]["exists"],
            "has_dedicated_premium_still_sr_smoke_checkpoint": dedicated["smoke_checkpoint"]["exists"],
            "has_larger_premium_still_sr_pairs": dedicated["large_pair_set"]["exists"],
            "has_larger_premium_still_sr_candidate_checkpoint": dedicated["large_checkpoint"]["exists"],
            "has_premium_still_sr_metric_dashboard": dedicated["candidate_metric_dashboard"]["exists"],
            "has_latest_no_ref_hf_residual_probe": latest_hf["exists"],
            "latest_no_ref_hf_runtime_uses_ref_content": bool(latest_hf.get("uses_source_hf_at_runtime")),
            "latest_no_ref_hf_holdout_mae_reduction_pct_median": latest_hf["holdout_residual_mae_reduction_pct_median"],
            "latest_no_ref_hf_holdout_rmse_reduction_pct_median": latest_hf["holdout_residual_rmse_reduction_pct_median"],
            "has_production_grade_premium_still_sr_checkpoint": False,
            "has_rendered_visual_premium_still_sr_dashboard": dedicated["candidate_visual_dashboard"]["exists"],
            "has_raw_editor_latitude_receipt": False,
        },
        "latest_hf_residual_probe": latest_hf,
        "blockers": blockers,
        "next_steps": [
            "Replace the small-crop HF residual probe with a larger-context raw-domain texture/noise model that can use full-image placement cues.",
            "Use camera/ISO noise sidecars as conditioning and target-cleaning policy, but prove removed content is noise before adding synthetic or original texture back.",
            "Evaluate on dedicated 50 MP and 100 MP still gates with full-frame panels, 100 percent crops, raw-domain metrics, rendered metrics, and editor-latitude checks.",
            "Promote only if the candidate beats STILL q0/q3/q8 baselines without tone, color, CFA, or noise-texture regressions and without REF content at render time.",
        ],
    }


def render_markdown(state: dict[str, Any]) -> str:
    lines = [
        "# Premium Still-SR Readiness",
        "",
        f"Created: {state['created_utc']}",
        "",
        f"Verdict: `{state['current_verdict']}`",
        "",
        "## What Exists",
        "",
    ]
    summary = state["evidence_summary"]
    for key, value in summary.items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Blockers", ""])
    for blocker in state["blockers"]:
        lines.append(f"- {blocker}")
    latest = state.get("latest_hf_residual_probe", {})
    if latest:
        lines.extend(["", "## Latest No-REF HF Residual Probe", ""])
        for key in (
            "exists",
            "production_status",
            "uses_source_hf_at_training",
            "uses_source_hf_at_runtime",
            "holdout_residual_mae_reduction_pct_median",
            "holdout_residual_rmse_reduction_pct_median",
            "promotion_reason",
        ):
            lines.append(f"- `{key}`: {latest.get(key)}")
    lines.extend(["", "## Next Steps", ""])
    for step in state["next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def render_html(state: dict[str, Any]) -> str:
    summary_rows = "\n".join(
        f"<tr><td>{html.escape(key)}</td><td>{html.escape(str(value))}</td></tr>"
        for key, value in state["evidence_summary"].items()
    )
    baseline_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(row['tier'])}</td>"
        f"<td>{html.escape(row['pipeline'])}</td>"
        f"<td>{row['mean_mb']:.2f}</td>"
        f"<td>{row['worst_lpips']:.3f}</td>"
        f"<td>{html.escape(row['verdict'])}</td>"
        "</tr>"
        for row in state["still_baselines"]
    )
    blocker_items = "\n".join(f"<li>{html.escape(item)}</li>" for item in state["blockers"])
    latest = state.get("latest_hf_residual_probe", {})
    latest_rows = "\n".join(
        f"<tr><td>{html.escape(key)}</td><td>{html.escape(str(latest.get(key)))}</td></tr>"
        for key in (
            "exists",
            "production_status",
            "uses_source_hf_at_training",
            "uses_source_hf_at_runtime",
            "holdout_residual_mae_reduction_pct_median",
            "holdout_residual_rmse_reduction_pct_median",
            "promotion_reason",
            "dashboard_path",
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Premium Still-SR Readiness</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #17202a; }}
    h1 {{ margin-bottom: 0.2rem; }}
    .verdict {{ display: inline-block; padding: 6px 10px; background: #fff3cd; border: 1px solid #d7a500; border-radius: 6px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 18px 0; }}
    th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f4f6f8; }}
    code {{ background: #eef2f5; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>Premium Still-SR Readiness</h1>
  <p class="verdict">{html.escape(state['current_verdict'])}</p>
  <h2>Evidence Summary</h2>
  <table><tbody>{summary_rows}</tbody></table>
  <h2>Current Still Baselines</h2>
  <table><thead><tr><th>Tier</th><th>Pipeline</th><th>Mean MB</th><th>Worst LPIPS</th><th>Verdict</th></tr></thead><tbody>{baseline_rows}</tbody></table>
  <h2>Latest No-REF HF Residual Probe</h2>
  <table><tbody>{latest_rows}</tbody></table>
  <h2>Blockers</h2>
  <ul>{blocker_items}</ul>
</body>
</html>
"""


def build_gate_receipt(state: dict[str, Any], output_refs: dict[str, dict[str, str]]) -> dict[str, Any]:
    candidate_hash = sha256_bytes(json.dumps(state["evidence_summary"], sort_keys=True).encode("utf-8"))
    return {
        "schema": GATE_SCHEMA,
        "candidate": {
            "pipeline_id": "premium_still_sr_current_state_blocked_v1",
            "checkpoint_sha256": candidate_hash,
            "target_role": "offline_premium_still",
        },
        "fixture_summary": {
            "camera_count": 2,
            "fifty_mp_or_larger_count": 1,
            "hundred_mp_or_larger_count": 1,
            "cfa_phases": ["RGGB"],
        },
        "outputs": output_refs,
        "baseline_comparison": {
            "passed_gate": False,
            "worst_lpips": 1.0,
            "worst_delta_e2000": 99.0,
            "min_raw_psnr_delta_db": 0.0,
            "editor_latitude_score_delta": 0.0,
        },
        "noise_policy": {
            "mode": "validated_sidecars_available_but_not_yet_wired_into_still_sr_candidate",
            "raw_noise_signal_audit_passed": False,
        },
        "production_ready": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    state = build_state(args.external_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    state_ref = write_json(args.output_dir / "readiness.json", state)
    markdown_path = args.output_dir / "readiness.md"
    markdown_path.write_text(render_markdown(state), encoding="utf-8")
    markdown_ref = artifact_ref(markdown_path)
    dashboard_path = args.output_dir / "index.html"
    dashboard_path.write_text(render_html(state), encoding="utf-8")
    dashboard_ref = artifact_ref(dashboard_path)

    output_refs = {
        "editable_dng": write_json(args.output_dir / "editable_dng_evidence.json", {"role": "editable_dng", "state": state_ref, "external": state["reusable_sr_artifacts"]["editable_dng"]}),
        "editable_gpr": write_json(args.output_dir / "editable_gpr_evidence.json", {"role": "editable_gpr", "state": state_ref, "external": state["reusable_sr_artifacts"]["editable_gpr"]}),
        "review_tiff_or_prores": write_json(args.output_dir / "review_tiff_or_prores_evidence.json", {"role": "review_tiff_or_prores", "state": state_ref, "external": state["reusable_sr_artifacts"]["review_tiff_or_prores"]}),
        "dashboard": dashboard_ref,
    }
    gate = build_gate_receipt(state, output_refs)
    gate_ref = write_json(args.output_dir / "premium_still_sr_gate_receipt.json", gate)

    index = {
        "schema": "gpr.premium_still_sr_readiness_index.v1",
        "readiness": state_ref,
        "readiness_markdown": markdown_ref,
        "dashboard": dashboard_ref,
        "gate_receipt": gate_ref,
    }
    write_json(args.output_dir / "index.json", index)
    print(gate_ref["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
