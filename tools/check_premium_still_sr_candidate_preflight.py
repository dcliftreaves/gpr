#!/usr/bin/env python3
"""Validate a proposed premium still-SR candidate before a long run.

The next-experiment contract is intentionally strict: the current local-CNN,
clean-signal U-Net, residual-pixelshuffle, routed clean-source, and scalar-loss
families are rejection evidence, not launchable primary production attempts.
This checker gives future runs a small machine-checkable intake gate before
they spend hours on training.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_candidate_preflight_audit.v1"
MANIFEST_SCHEMA = "gpr.premium_still_sr_candidate_preflight.v1"

FORBIDDEN_RUNTIME_INPUTS = {
    "ref",
    "reference",
    "reference_image",
    "source_raw",
    "source_rgb",
    "source_hf",
    "jpeg",
    "jpeg_target",
    "source_residual_noise",
}
REQUIRED_RUNTIME_INPUTS = {"candidate_raw", "camera_metadata"}
ARCHITECTURE_DELTA_TOKENS = {
    "non-local",
    "nonlocal",
    "full-image",
    "full image",
    "full-frame",
    "full frame",
    "shifted-window",
    "hybrid-attention",
    "restormer",
    "rbsformer",
    "swinir",
    "hat",
    "raw-sr transformer",
    "self-supervised clean-source",
    "burst",
    "multi-frame",
}
DEGRADATION_DELTA_TOKENS = {
    "blur",
    "psf",
    "noise",
    "iso",
    "bit depth",
    "bit-depth",
    "compression",
    "decode",
    "sensor",
    "camera-specific",
    "cfa",
}
REJECTED_REPEAT_TOKENS = {
    "residual_pixelshuffle",
    "local-cnn-only",
    "local cnn only",
    "clean_signal_unet",
    "clean-signal u-net",
    "clean signal u-net",
    "source-hf",
    "source_hf",
    "stored-hf",
    "stored_hf",
    "framectx",
    "pyramid_unet",
    "global-context u-net",
    "random context masking",
    "nearest-neighbor residual patch",
    "12k-step psf/cfa window-attention",
    "12k psf/cfa window-attention",
    "routed clean-source 1500",
}
REQUIRED_RECEIPT_TOKENS = {
    "checkpoint",
    "config",
    "dashboard",
    "timing",
    "memory",
    "editor",
    "editable",
    "noise",
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path, help="gpr.premium_still_sr_candidate_preflight.v1 proposal")
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--html-out", type=Path)
    ap.add_argument(
        "--require-launchable",
        action="store_true",
        help="Exit nonzero unless the proposed run passes the launch preflight.",
    )
    return ap.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def as_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str) and value:
        return [value]
    return []


def text_blob(*values: Any) -> str:
    chunks: list[str] = []
    for value in values:
        if isinstance(value, dict):
            chunks.extend(str(item) for item in value.values())
        elif isinstance(value, list):
            chunks.extend(str(item) for item in value)
        elif value not in (None, ""):
            chunks.append(str(value))
    return " ".join(chunks).lower()


def contains_any(text: str, tokens: set[str]) -> bool:
    return any(token in text for token in tokens)


def matching_tokens(text: str, tokens: set[str]) -> list[str]:
    return sorted(token for token in tokens if token in text)


def add_failure(failures: list[str], message: str) -> None:
    failures.append(message)


def validate_preflight(manifest: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    if manifest.get("schema") not in {MANIFEST_SCHEMA, None}:
        add_failure(failures, f"schema must be {MANIFEST_SCHEMA}")

    candidate_id = str(manifest.get("candidate_id") or "").strip()
    if not candidate_id:
        add_failure(failures, "candidate_id is required")
    if manifest.get("requires_material_edits_before_launch") is True:
        add_failure(
            failures,
            "generated proposal template still requires material edits before launch",
        )
    material_change = str(manifest.get("material_change_summary") or "").strip()
    if not material_change or material_change.startswith("<"):
        add_failure(
            failures,
            "material_change_summary must describe the concrete change from rejected receipts",
        )

    runtime_inputs = {item.lower() for item in as_strings(manifest.get("runtime_inputs"))}
    missing_runtime = sorted(REQUIRED_RUNTIME_INPUTS - runtime_inputs)
    if missing_runtime:
        add_failure(failures, f"runtime_inputs missing required values: {', '.join(missing_runtime)}")
    forbidden_runtime = sorted(runtime_inputs & FORBIDDEN_RUNTIME_INPUTS)
    if forbidden_runtime:
        add_failure(failures, f"runtime_inputs include forbidden render-time content: {', '.join(forbidden_runtime)}")
    if manifest.get("forbidden_runtime_inputs_absent") is not True:
        add_failure(failures, "forbidden_runtime_inputs_absent must be true")

    architecture_text = text_blob(
        manifest.get("candidate_id"),
        manifest.get("model_arch"),
        manifest.get("architecture_family"),
        manifest.get("architecture_deltas"),
        manifest.get("notes"),
    )
    rejected = matching_tokens(architecture_text, REJECTED_REPEAT_TOKENS)
    if rejected:
        add_failure(failures, f"proposal matches rejected primary path tokens: {', '.join(rejected)}")
    if "naf" in architecture_text and ("detail" in architecture_text or "gradient" in architecture_text):
        degradation_text_for_naf = text_blob(manifest.get("degradation_deltas"))
        if not contains_any(degradation_text_for_naf, {"psf", "noise", "compression", "decode", "camera-specific"}):
            add_failure(failures, "NAF/detail-style proposals need a new realistic degradation policy")
    architecture_matches = matching_tokens(architecture_text, ARCHITECTURE_DELTA_TOKENS)
    if not architecture_matches:
        add_failure(
            failures,
            "architecture_deltas must include a material non-local/full-image/restoration-teacher change",
        )

    candidate_kind = str(manifest.get("candidate_kind") or "").lower()
    if candidate_kind == "student" and manifest.get("teacher_gate_before_student") is not True:
        add_failure(failures, "candidate-only student proposals require teacher_gate_before_student=true")

    degradation_text = text_blob(manifest.get("degradation_deltas"), manifest.get("degradation_policy"))
    degradation_matches = matching_tokens(degradation_text, DEGRADATION_DELTA_TOKENS)
    if len(degradation_matches) < 2:
        add_failure(
            failures,
            "degradation_deltas must include realistic RAW degradation beyond same-color box downsample",
        )
    if "same-color box" in degradation_text and len(degradation_matches) < 3:
        add_failure(failures, "same-color box downsample alone is not a valid next degradation policy")

    validation_text = text_blob(manifest.get("validation_plan"), manifest.get("holdouts"))
    if "x2d" not in validation_text:
        add_failure(failures, "validation_plan must include held-out X2D evidence")
    if "z8" not in validation_text:
        add_failure(failures, "validation_plan must include held-out Z8 evidence")
    if not contains_any(validation_text, {"full-image", "full image", "full-frame", "full frame", "overlapped-tile", "overlapped tile"}):
        add_failure(failures, "validation_plan must include full-image or overlapped-tile evaluation")

    baseline_text = text_blob(manifest.get("baseline_comparisons"))
    if "same-color" not in baseline_text or "interpolation" not in baseline_text:
        add_failure(failures, "baseline_comparisons must include same-color Bayer interpolation")
    if not contains_any(baseline_text, {"current still", "current baseline", "scoreboard", "12k", "window-attention rejection"}):
        add_failure(failures, "baseline_comparisons must include the current still/SR baseline or rejection scoreboard")

    receipt_text = text_blob(manifest.get("planned_receipts"), manifest.get("promotion_receipts"))
    missing_receipts = sorted(token for token in REQUIRED_RECEIPT_TOKENS if token not in receipt_text)
    if missing_receipts:
        add_failure(failures, f"planned_receipts missing production evidence classes: {', '.join(missing_receipts)}")

    noise = manifest.get("noise_policy") if isinstance(manifest.get("noise_policy"), dict) else {}
    if noise.get("exact_sidecars_only") is not True:
        add_failure(failures, "noise_policy.exact_sidecars_only must be true")
    if noise.get("forbids_source_residual_noise") is not True:
        add_failure(failures, "noise_policy.forbids_source_residual_noise must be true")
    if noise.get("missing_sidecars") not in {"metadata_only", "reject_nonzero_addback"}:
        add_failure(
            failures,
            "noise_policy.missing_sidecars must be metadata_only or reject_nonzero_addback",
        )

    if manifest.get("promotion_claimed") is True:
        add_failure(failures, "preflight manifests must not claim promotion before the full still-SR gate")
    if manifest.get("production_ready") is True:
        add_failure(failures, "preflight manifests must not set production_ready=true")
    if manifest.get("uses_ref_or_source_content_at_render_time") is True:
        add_failure(failures, "render-time REF/source content is forbidden")

    if manifest.get("launchable_for_production_attempt") is not True:
        add_failure(failures, "launchable_for_production_attempt must be true after material edits")

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": candidate_id,
        "launchable_for_production_attempt": not failures,
        "production_ready": False,
        "promotion_claimed": False,
        "architecture_delta_matches": architecture_matches,
        "degradation_delta_matches": degradation_matches,
        "failures": failures,
        "warnings": warnings,
        "verdict": (
            "launchable_preflight_passed"
            if not failures
            else "blocked_before_long_run"
        ),
    }


def write_html(audit: dict[str, Any], path: Path) -> None:
    failures = audit.get("failures") if isinstance(audit.get("failures"), list) else []
    warnings = audit.get("warnings") if isinstance(audit.get("warnings"), list) else []
    status = "PASS" if audit.get("launchable_for_production_attempt") else "BLOCKED"
    rows = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in failures
    ) or "<li>None</li>"
    warning_rows = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in warnings
    ) or "<li>None</li>"
    body = f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Candidate Preflight</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #17202a; }}
.status {{ display: inline-block; padding: 6px 10px; border-radius: 4px; background: {'#d5f5e3' if status == 'PASS' else '#fadbd8'}; }}
code {{ background: #f4f6f7; padding: 2px 4px; border-radius: 3px; }}
</style>
<h1>Premium Still-SR Candidate Preflight</h1>
<p class="status"><b>{status}</b> {html.escape(str(audit.get('candidate_id') or ''))}</p>
<p>This is a launch preflight only. It does not claim production readiness.</p>
<h2>Failures</h2>
<ul>{rows}</ul>
<h2>Warnings</h2>
<ul>{warning_rows}</ul>
<h2>Matched Deltas</h2>
<p><b>Architecture:</b> {html.escape(', '.join(audit.get('architecture_delta_matches') or []))}</p>
<p><b>Degradation:</b> {html.escape(', '.join(audit.get('degradation_delta_matches') or []))}</p>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def main() -> int:
    args = parse_args()
    audit = validate_preflight(load_json(args.manifest))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.html_out:
        write_html(audit, args.html_out)
    print(json.dumps({"candidate_id": audit["candidate_id"], "verdict": audit["verdict"]}, sort_keys=True))
    if args.require_launchable and not audit["launchable_for_production_attempt"]:
        for failure in audit["failures"]:
            print(f"preflight failure: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
