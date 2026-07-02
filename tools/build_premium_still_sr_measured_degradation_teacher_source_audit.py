#!/usr/bin/env python3
"""Build the Gate 12 Premium still-SR measured/synthetic teacher-source audit.

Gate 11 proved that route-isolated raw-HF residual training is still not a
production path. This receipt decides what source family is allowed before the
next candidate intake: measured paired degradation if present, synthetic
known-degradation clean-source Bayer pairs if they have route evidence, or an
exact no-op/selector baseline when neither route has positive evidence.

The tool does not train, does not authorize a long run, and does not claim
production readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_measured_degradation_teacher_source_audit.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_ARTIFACT_ROOT = DEFAULT_EXTERNAL_ROOT / "artifacts"
DEFAULT_GATE11_ACCEPTANCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_gate11_smoke_acceptance_20260702"
    / "smoke_gate_acceptance.json"
)
DEFAULT_GATE11_AUDIT = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_degradation_source_audit_20260702"
    / "degradation_source_audit.json"
)
DEFAULT_TARGET_SNR = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_raw_target_snr_audit_20260701"
    / "raw_target_snr_audit.json"
)
DEFAULT_PAIR_META = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_clean_source_pairs_routed_t64_20260702"
    / "premium_still_sr_clean_source_pairs_routed_t64.npz.json"
)
DEFAULT_X2D_SOURCE_EVIDENCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_source_evidence_x2dholdout_t64_20260702"
    / "source_evidence_audit.json"
)
DEFAULT_Z8_SOURCE_EVIDENCE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_source_evidence_z8holdout_t64_20260702"
    / "source_evidence_audit.json"
)
DEFAULT_X2D_TEACHER_SMOKE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_source_evidence_split_teacher_x2d_smoke_20260702_next"
    / "train_receipt.json"
)
DEFAULT_Z8_TEACHER_SMOKE = (
    DEFAULT_ARTIFACT_ROOT
    / "premium_still_sr_source_evidence_split_teacher_z8_smoke_20260702_next"
    / "train_receipt.json"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def median(values: list[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def min_value(values: list[float]) -> float:
    return float(min(values)) if values else 0.0


def source_evidence_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "holdout_camera": data.get("holdout_camera"),
        "source_evidence_present": bool(nested(data, ["acceptance", "source_evidence_present"], False)),
        "median_mae_recovery_pct": as_float(nested(data, ["summary", "linear_probe_mae_recovery_pct", "median"])),
        "median_rmse_recovery_pct": as_float(nested(data, ["summary", "linear_probe_rmse_recovery_pct", "median"])),
        "min_required_recovery_pct": as_float(nested(data, ["acceptance", "min_median_mae_recovery_pct"], 1.0), 1.0),
        "runtime_inputs": nested(data, ["probe", "runtime_inputs"], []),
        "forbidden_inputs": nested(data, ["probe", "forbidden_inputs"], []),
    }


def teacher_smoke_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    rows = nested(data, ["eval", "holdout", "rows"], [])
    if not isinstance(rows, list):
        rows = []
    mae_values = [as_float(row.get("mae_improvement_pct")) for row in rows if isinstance(row, dict)]
    rmse_values = [as_float(row.get("rmse_improvement_pct")) for row in rows if isinstance(row, dict)]
    promotion = data.get("promotion") if isinstance(data.get("promotion"), dict) else {}
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "pairs": data.get("pairs"),
        "pairs_sha256": data.get("pairs_sha256"),
        "checkpoint_sha256": data.get("checkpoint_sha256"),
        "holdout_tile_count": nested(data, ["eval", "holdout", "baseline_mae", "count"], 0),
        "median_mae_recovery_pct": median(mae_values),
        "worst_mae_recovery_pct": min_value(mae_values),
        "median_rmse_recovery_pct": median(rmse_values),
        "baseline_beaten_on_holdout": bool(promotion.get("baseline_beaten_on_holdout")),
        "promotion_ready": bool(promotion.get("promotion_ready")),
        "coverage_sufficient_for_promotion": bool(promotion.get("coverage_sufficient_for_promotion")),
        "decision": promotion.get("decision"),
    }


def camera_snr_rows(data: dict[str, Any], camera: str) -> dict[str, Any]:
    for row in data.get("by_camera", []):
        if isinstance(row, dict) and str(row.get("camera")).lower() == camera.lower():
            classes = row.get("classifications") if isinstance(row.get("classifications"), dict) else {}
            row_count = int(row.get("row_count") or 0)
            noise_floor = int(classes.get("noise_floor") or 0)
            return {
                "row_count": row_count,
                "classifications": classes,
                "noise_floor_rows": noise_floor,
                "signal_dominated_rows": int(classes.get("signal_dominated") or 0),
                "mixed_signal_noise_rows": int(classes.get("mixed_signal_noise") or 0),
                "noise_floor_fraction": float(noise_floor / row_count) if row_count else 0.0,
                "median_target_rmse_to_noise_sigma": nested(row, ["target_rmse_to_noise_sigma", "median"], 0.0),
                "median_target_p95_to_noise_p95": nested(row, ["target_p95_to_noise_p95", "median"], 0.0),
            }
    return {
        "row_count": 0,
        "classifications": {},
        "noise_floor_rows": 0,
        "signal_dominated_rows": 0,
        "mixed_signal_noise_rows": 0,
        "noise_floor_fraction": 0.0,
        "median_target_rmse_to_noise_sigma": 0.0,
        "median_target_p95_to_noise_p95": 0.0,
    }


def pair_meta_summary(path: Path) -> dict[str, Any]:
    data = load_json(path)
    images = data.get("images") if isinstance(data.get("images"), list) else []
    camera_counts: dict[str, int] = {}
    class_counts: dict[str, int] = {}
    source_shapes: set[tuple[int, int]] = set()
    for image in images:
        if not isinstance(image, dict):
            continue
        camera = str(image.get("camera_key") or "unknown")
        camera_counts[camera] = camera_counts.get(camera, 0) + 1
        cls = str(image.get("class") or "unknown")
        class_counts[cls] = class_counts.get(cls, 0) + 1
        source_shapes.add((int(image.get("source_width") or 0), int(image.get("source_height") or 0)))
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "dataset_label": data.get("dataset_label"),
        "created_from": data.get("created_from"),
        "downsample": data.get("downsample"),
        "image_count": len(images),
        "camera_counts": camera_counts,
        "class_counts": class_counts,
        "low_tile": data.get("low_tile"),
        "high_tile": data.get("high_tile"),
        "source_shapes": sorted([list(shape) for shape in source_shapes]),
        "fixture_manifest": data.get("fixture_manifest"),
        "fixture_manifest_sha256": data.get("fixture_manifest_sha256"),
    }


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    gate11_acceptance = load_json(args.gate11_acceptance)
    gate11_audit = load_json(args.gate11_audit)
    target_snr = load_json(args.target_snr)
    pairs = pair_meta_summary(args.clean_source_pair_meta)
    x2d_source = source_evidence_summary(args.x2d_source_evidence)
    z8_source = source_evidence_summary(args.z8_source_evidence)
    x2d_teacher = teacher_smoke_summary(args.x2d_teacher_smoke)
    z8_teacher = teacher_smoke_summary(args.z8_teacher_smoke)
    x2d_snr = camera_snr_rows(target_snr, "x2d")
    z8_snr = camera_snr_rows(target_snr, "z8")

    gate11_failed = gate11_acceptance.get("long_run_allowed") is False and gate11_acceptance.get("smoke_gate_passed") is False
    synthetic_pair_available = (
        pairs.get("downsample") == "same-color 2x2 average within each Bayer plane"
        and int(pairs.get("image_count") or 0) >= args.min_pair_image_count
        and "x2d" in pairs.get("camera_counts", {})
    )
    measured_pair_available = False
    x2d_route_allowed = (
        synthetic_pair_available
        and x2d_source["source_evidence_present"]
        and x2d_teacher["baseline_beaten_on_holdout"]
        and x2d_teacher["median_mae_recovery_pct"] > args.minimum_smoke_median_improvement_pct
    )
    z8_route_allowed = (
        synthetic_pair_available
        and z8_source["source_evidence_present"]
        and z8_teacher["baseline_beaten_on_holdout"]
        and z8_teacher["median_mae_recovery_pct"] > args.minimum_smoke_median_improvement_pct
        and z8_snr["noise_floor_fraction"] < args.z8_noise_floor_noop_fraction
    )

    selected_family = "deterministic_noop_selector_only"
    gate12_allowed = False
    if measured_pair_available:
        selected_family = "measured_paired_degradation_teacher"
        gate12_allowed = True
    elif x2d_route_allowed:
        selected_family = "synthetic_known_degradation_teacher_x2d_plus_z8_noop"
        gate12_allowed = True

    route_policy = {
        "x2d": {
            "policy": "train_synthetic_known_degradation_teacher_route" if x2d_route_allowed else "no_train_until_source_evidence_passes",
            "teacher_source": "clean-source high Bayer to same-color 2x2 average low Bayer pairs",
            "positive_training_allowed": bool(x2d_route_allowed),
            "source_evidence_present": bool(x2d_source["source_evidence_present"]),
            "source_evidence_median_mae_recovery_pct": x2d_source["median_mae_recovery_pct"],
            "teacher_smoke_median_mae_recovery_pct": x2d_teacher["median_mae_recovery_pct"],
            "teacher_smoke_worst_mae_recovery_pct": x2d_teacher["worst_mae_recovery_pct"],
            "reason": (
                "X2D has candidate-only local source evidence and the synthetic known-degradation "
                "teacher smoke beats nearest same-color 2x on the short holdout."
                if x2d_route_allowed
                else "X2D does not yet satisfy the source-evidence plus teacher-smoke route requirements."
            ),
        },
        "z8": {
            "policy": "train_synthetic_known_degradation_teacher_route" if z8_route_allowed else "exact_noop_or_new_source_required",
            "teacher_source": "none for positive residual training until source evidence improves",
            "positive_training_allowed": bool(z8_route_allowed),
            "source_evidence_present": bool(z8_source["source_evidence_present"]),
            "source_evidence_median_mae_recovery_pct": z8_source["median_mae_recovery_pct"],
            "teacher_smoke_median_mae_recovery_pct": z8_teacher["median_mae_recovery_pct"],
            "teacher_smoke_worst_mae_recovery_pct": z8_teacher["worst_mae_recovery_pct"],
            "noise_floor_rows": z8_snr["noise_floor_rows"],
            "row_count": z8_snr["row_count"],
            "noise_floor_fraction": z8_snr["noise_floor_fraction"],
            "reason": (
                "Z8 lacks positive source evidence and remains mostly noise-floor, so it must be "
                "exact no-op or use a new measured/synthetic source-evidence receipt before "
                "positive training."
                if not z8_route_allowed
                else "Z8 source evidence and teacher smoke satisfy the route requirements."
            ),
        },
    }

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "verdict": (
            "gate12_synthetic_teacher_preflight_allowed_x2d_z8_noop"
            if gate12_allowed
            else "gate12_noop_selector_only_until_teacher_source_passes"
        ),
        "production_ready": False,
        "long_run_allowed": False,
        "gate12_candidate_intake_allowed": gate12_allowed,
        "paired_smoke_allowed": False,
        "selected_family": selected_family,
        "measured_paired_source_available": measured_pair_available,
        "synthetic_known_degradation_source_available": synthetic_pair_available,
        "failed_source_family_rejected": True,
        "inputs": {
            "gate11_acceptance": {
                "path": str(args.gate11_acceptance),
                "sha256": sha256_file(args.gate11_acceptance),
                "schema": gate11_acceptance.get("schema"),
                "candidate_id": gate11_acceptance.get("candidate_id"),
                "smoke_gate_passed": bool(gate11_acceptance.get("smoke_gate_passed")),
                "long_run_allowed": bool(gate11_acceptance.get("long_run_allowed")),
                "gate11_failed": gate11_failed,
            },
            "gate11_degradation_source_audit": {
                "path": str(args.gate11_audit),
                "sha256": sha256_file(args.gate11_audit),
                "schema": gate11_audit.get("schema"),
                "selected_family": gate11_audit.get("selected_family"),
            },
            "target_snr": {
                "path": str(args.target_snr),
                "sha256": sha256_file(args.target_snr),
                "schema": target_snr.get("schema"),
                "x2d": x2d_snr,
                "z8": z8_snr,
            },
            "synthetic_known_degradation_pairs": pairs,
            "x2d_source_evidence": x2d_source,
            "z8_source_evidence": z8_source,
            "x2d_teacher_smoke": x2d_teacher,
            "z8_teacher_smoke": z8_teacher,
        },
        "target_source_decision": {
            "forbidden_training_target_family": "source_minus_candidate_raw_hf_residual",
            "allowed_training_target_family": "clean_source_high_bayer_to_synthetic_low_bayer_pairs",
            "degradation_process": "same-color 2x2 average within each Bayer plane",
            "render_time_source_content_allowed": False,
            "exact_source_noise_addback_allowed_at_runtime": False,
        },
        "route_policy": route_policy,
        "gate12_preflight_requirements": [
            "candidate runtime inputs: candidate_raw plus camera metadata and exact validated noise sidecar scalars only",
            "training may use clean-source high/low Bayer pairs, but render time must not use source RAW, source HF, REF, RGB target, or JPEG target",
            "X2D may train against the synthetic known-degradation teacher only if the preflight carries the source-evidence and teacher-smoke hashes from this audit",
            "Z8 must be exact no-op unless a new measured or synthetic source-evidence receipt beats the required floor and its smoke beats same-color 2x",
            "paired smoke must pass X2D and Z8 with median MAE improvement >0.001%, worst-row MAE >=0%, and baseline_beaten_on_holdout=true before any long run",
        ],
        "forbidden_gate12_sources": [
            "source_minus_candidate_raw_hf_residual target",
            "raw-HF residual target from candidate/source highpass arrays",
            "Gate 11 route-isolated residual teacher/router rerun",
            "Z8 positive residual training from current noise-floor rows",
            "any render-time REF/source/JPEG image content",
        ],
        "next_receipts": [
            {
                "order": 1,
                "receipt": "premium_still_sr_gate12_candidate_intake_<date>",
                "done_when": "A launchable preflight encodes this source audit, X2D synthetic teacher route, and Z8 no-op/new-source policy.",
            },
            {
                "order": 2,
                "receipt": "premium_still_sr_gate12_smoke_acceptance_<date>",
                "done_when": "Paired X2D/Z8 smoke passes before any long run.",
            },
            {
                "order": 3,
                "receipt": "premium_still_sr_promotion_receipts",
                "done_when": "50 MP / 100 MP promotion clears 15% / 15% recovery, nonnegative worst rows, editor/openability, timing/memory, hashes, and production submission validation.",
            },
        ],
    }


def render_html(data: dict[str, Any], json_path: Path) -> str:
    policies = "\n".join(
        "<tr>"
        f"<td>{html.escape(route)}</td>"
        f"<td>{html.escape(str(policy['policy']))}</td>"
        f"<td>{html.escape(str(policy['positive_training_allowed']))}</td>"
        f"<td>{html.escape(str(policy['reason']))}</td>"
        "</tr>"
        for route, policy in data["route_policy"].items()
    )
    requirements = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["gate12_preflight_requirements"])
    forbidden = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["forbidden_gate12_sources"])
    next_rows = "\n".join(
        "<tr>"
        f"<td>{row['order']}</td>"
        f"<td>{html.escape(row['receipt'])}</td>"
        f"<td>{html.escape(row['done_when'])}</td>"
        "</tr>"
        for row in data["next_receipts"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Gate 12 Teacher Source Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #18212b; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dfe5ea; border-radius: 8px; padding: 14px; }}
.label {{ color: #61707c; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 21px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dfe5ea; margin: 16px 0; }}
th, td {{ border-bottom: 1px solid #e8edf2; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf2f6; color: #4e5d69; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Gate 12 Teacher Source Audit</h1>
<p>This receipt replaces the failed raw-HF residual target family with a measured/synthetic teacher-source policy. It allows only a small preflight and does not authorize a long run.</p>
<div class="grid">
  <section class="card"><div class="label">Verdict</div><div class="value">{html.escape(data['verdict'])}</div></section>
  <section class="card"><div class="label">Selected family</div><div class="value">{html.escape(data['selected_family'])}</div></section>
  <section class="card"><div class="label">Gate 12 intake allowed</div><div class="value">{data['gate12_candidate_intake_allowed']}</div></section>
  <section class="card"><div class="label">Long run allowed</div><div class="value">{data['long_run_allowed']}</div></section>
</div>
<div class="grid">
  <section class="card"><div class="label">Synthetic source</div><div class="value">{data['synthetic_known_degradation_source_available']}</div></section>
  <section class="card"><div class="label">Measured paired source</div><div class="value">{data['measured_paired_source_available']}</div></section>
  <section class="card"><div class="label">Failed residual source rejected</div><div class="value">{data['failed_source_family_rejected']}</div></section>
</div>
<h2>Route Policy</h2>
<table><tr><th>Route</th><th>Policy</th><th>Positive training</th><th>Reason</th></tr>{policies}</table>
<h2>Gate 12 Requirements</h2>
<ul>{requirements}</ul>
<h2>Forbidden Sources</h2>
<ul>{forbidden}</ul>
<h2>Next Receipts</h2>
<table><tr><th>Order</th><th>Receipt</th><th>Done when</th></tr>{next_rows}</table>
<p>JSON receipt: <code>{html.escape(str(json_path))}</code></p>
</main></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate11-acceptance", type=Path, default=DEFAULT_GATE11_ACCEPTANCE)
    parser.add_argument("--gate11-audit", type=Path, default=DEFAULT_GATE11_AUDIT)
    parser.add_argument("--target-snr", type=Path, default=DEFAULT_TARGET_SNR)
    parser.add_argument("--clean-source-pair-meta", type=Path, default=DEFAULT_PAIR_META)
    parser.add_argument("--x2d-source-evidence", type=Path, default=DEFAULT_X2D_SOURCE_EVIDENCE)
    parser.add_argument("--z8-source-evidence", type=Path, default=DEFAULT_Z8_SOURCE_EVIDENCE)
    parser.add_argument("--x2d-teacher-smoke", type=Path, default=DEFAULT_X2D_TEACHER_SMOKE)
    parser.add_argument("--z8-teacher-smoke", type=Path, default=DEFAULT_Z8_TEACHER_SMOKE)
    parser.add_argument("--minimum-smoke-median-improvement-pct", type=float, default=0.001)
    parser.add_argument("--z8-noise-floor-noop-fraction", type=float, default=0.5)
    parser.add_argument("--min-pair-image-count", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    data = build_audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "measured_degradation_teacher_source_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data, json_path), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
