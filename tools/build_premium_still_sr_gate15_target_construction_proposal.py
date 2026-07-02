#!/usr/bin/env python3
"""Build a Gate15 target-construction proposal from Gate14 target rows.

The proposal is intentionally a pre-training artifact. It does not claim model
quality; it only proves that the next target construction has enough row-level
candidate signal to justify paired smoke training. It reads only the compressed
metadata scalar from the Gate14 target NPZ so it can run in CI/dev shells
without numpy or loading multi-GB arrays.
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import statistics
import struct
import time
import zipfile
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate15_target_construction_proposal.v1"
ARTIFACT_ROOT = Path("/Volumes/OWC_8TB/gpr_work/artifacts")
DEFAULT_GATE14_TARGET_BUILDER = ARTIFACT_ROOT / "premium_still_sr_gate14_floor_student_targets_20260702" / "gate14_floor_student_targets.json"
DEFAULT_GATE14_TARGET_NPZ = ARTIFACT_ROOT / "premium_still_sr_gate14_floor_student_targets_20260702" / "gate14_floor_student_targets.npz"
DEFAULT_OUTPUT_DIR = ARTIFACT_ROOT / "premium_still_sr_gate15_target_construction_proposal_20260702"


def sha256_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def npy_scalar_text_from_npz(npz_path: Path, member: str = "meta.npy") -> str:
    with zipfile.ZipFile(npz_path) as z:
        data = z.read(member)
    if data[:6] != b"\x93NUMPY":
        raise ValueError(f"{npz_path}:{member} is not a .npy member")
    version = (data[6], data[7])
    if version == (1, 0):
        header_len = struct.unpack("<H", data[8:10])[0]
        offset = 10
    else:
        header_len = struct.unpack("<I", data[8:12])[0]
        offset = 12
    header = ast.literal_eval(data[offset : offset + header_len].decode("latin1"))
    if header.get("shape") != ():
        raise ValueError(f"{npz_path}:{member} must be a scalar string array")
    descr = str(header.get("descr"))
    payload = data[offset + header_len :]
    if descr.startswith("<U"):
        return payload.decode("utf-32le").rstrip("\x00")
    if descr.startswith("|S"):
        return payload.decode("utf-8").rstrip("\x00")
    raise ValueError(f"unsupported scalar string dtype {descr!r} in {npz_path}:{member}")


def load_target_rows(npz_path: Path) -> list[dict[str, Any]]:
    rows = json.loads(npy_scalar_text_from_npz(npz_path))
    if not isinstance(rows, list):
        raise TypeError(f"{npz_path} metadata must contain a JSON list")
    return [row for row in rows if isinstance(row, dict)]


def as_float(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p25": None, "median": None, "p75": None, "p95": None, "p99": None, "max": None}
    values = sorted(values)

    def q(frac: float) -> float:
        return values[min(len(values) - 1, int(frac * (len(values) - 1)))]

    return {
        "min": values[0],
        "p25": q(0.25),
        "median": statistics.median(values),
        "p75": q(0.75),
        "p95": q(0.95),
        "p99": q(0.99),
        "max": values[-1],
    }


def compact_row(row: dict[str, Any], *, positive: bool, exact_noop: bool, tail_safe: bool, reason: str) -> dict[str, Any]:
    keys = [
        "domain",
        "camera",
        "camera_key",
        "class",
        "image_id",
        "scene_id",
        "tile_index",
        "gate14_output_index",
        "crop_xy",
        "crop_size",
        "cfa_phase",
        "candidate_raw_same_color_hf_abs_mean",
        "raw_same_color_hf_residual_abs_mean",
        "render_hf_residual_y_abs_mean",
        "source_raw_same_color_hf_abs_mean",
        "noise_sidecars",
    ]
    out = {key: row.get(key) for key in keys if key in row}
    out.update(
        {
            "candidate_only_positive_floor": positive,
            "positive_source_evidence": False,
            "exact_noop": exact_noop,
            "tail_safe": tail_safe,
            "selection_reason": reason,
        }
    )
    return out


def build_proposal(args: argparse.Namespace) -> dict[str, Any]:
    target_builder = load_json(args.gate14_target_builder)
    rows = load_target_rows(args.gate14_target_npz)
    domains = Counter(str(row.get("domain") or "unknown") for row in rows)
    x2d_rows = [row for row in rows if str(row.get("domain")) == "x2d"]
    z8_rows = [row for row in rows if str(row.get("domain")) == "z8"]
    if not x2d_rows or not z8_rows:
        raise ValueError("Gate15 proposal requires both x2d and z8 target rows")

    x2d_residuals = [as_float(row, "raw_same_color_hf_residual_abs_mean") for row in x2d_rows]
    x2d_candidate_hf = [as_float(row, "candidate_raw_same_color_hf_abs_mean") for row in x2d_rows]
    z8_residuals = [as_float(row, "raw_same_color_hf_residual_abs_mean") for row in z8_rows]

    pretraining_rows: list[dict[str, Any]] = []
    positive_count = 0
    for row in x2d_rows:
        candidate_hf = as_float(row, "candidate_raw_same_color_hf_abs_mean")
        residual_hf = as_float(row, "raw_same_color_hf_residual_abs_mean")
        render_y = as_float(row, "render_hf_residual_y_abs_mean")
        positive = (
            candidate_hf >= args.x2d_candidate_hf_floor
            and residual_hf >= args.x2d_residual_hf_floor
            and render_y >= args.x2d_render_y_floor
            and residual_hf <= args.x2d_residual_hf_cap
        )
        positive_count += int(positive)
        reason = (
            "x2d_positive_candidate_hf_and_target_residual"
            if positive
            else "x2d_noop_or_low_confidence_row"
        )
        pretraining_rows.append(
            compact_row(row, positive=positive, exact_noop=not positive, tail_safe=True, reason=reason)
        )

    for row in z8_rows:
        pretraining_rows.append(
            compact_row(
                row,
                positive=False,
                exact_noop=True,
                tail_safe=True,
                reason="z8_exact_noop_until_positive_source_evidence_exists",
            )
        )

    x2d_needed = len(x2d_rows) // 2 + 1
    proposal_passes_internal_floor = positive_count >= x2d_needed
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": "premium_still_sr_gate15_x2d_positive_z8_noop_v1",
        "production_ready": False,
        "promotion_claimed": False,
        "paired_smoke_requested": proposal_passes_internal_floor,
        "long_run_allowed": False,
        "runtime_policy": {
            "allowed_runtime_inputs": [
                "candidate_raw",
                "camera_metadata",
                "candidate_tile_statistics",
                "candidate_tile_coordinates",
                "candidate_scene_normalized_tile_statistics",
                "validated_noise_sidecar_optional",
            ],
            "forbidden_runtime_inputs_absent": True,
            "forbidden_runtime_inputs": [
                "REF",
                "source_raw",
                "source_rgb",
                "source_hf",
                "JPEG",
                "target_mae",
                "gate_metric",
                "oracle_row_label",
            ],
        },
        "target_construction": {
            "description": (
                "Train X2D only on rows with candidate-derived HF and target residual above the "
                "preflight floor; keep Z8 exact no-op until separate positive source evidence exists."
            ),
            "uses_ref_or_source_at_render_time": False,
            "teacher_gate_before_student": True,
            "exact_noop_fallback": True,
            "x2d_candidate_hf_floor": args.x2d_candidate_hf_floor,
            "x2d_residual_hf_floor": args.x2d_residual_hf_floor,
            "x2d_render_y_floor": args.x2d_render_y_floor,
            "x2d_residual_hf_cap": args.x2d_residual_hf_cap,
            "z8_policy": "exact_noop_until_positive_source_evidence_exists",
        },
        "inputs": {
            "gate14_target_builder": {
                "path": str(args.gate14_target_builder),
                "sha256": sha256_file(args.gate14_target_builder),
                "target_builder_passed": target_builder.get("target_builder_passed"),
            },
            "gate14_target_npz": {
                "path": str(args.gate14_target_npz),
                "sha256": sha256_file(args.gate14_target_npz),
                "role": "row metadata source; arrays are not loaded by this proposal builder",
            },
        },
        "row_evidence": {
            "all_domain_counts": dict(sorted(domains.items())),
            "x2d_row_count": len(x2d_rows),
            "x2d_candidate_only_positive_floor_row_count": positive_count,
            "x2d_minimum_rows_needed_for_median_floor": x2d_needed,
            "z8_row_count": len(z8_rows),
            "z8_exact_noop_row_count": len(z8_rows),
            "x2d_residual_hf_quantiles": quantiles(x2d_residuals),
            "x2d_candidate_hf_quantiles": quantiles(x2d_candidate_hf),
            "z8_residual_hf_quantiles": quantiles(z8_residuals),
            "proposal_internal_floor_passed": proposal_passes_internal_floor,
        },
        "pretraining_signal_rows": pretraining_rows,
        "next_unambiguous_action": (
            "Run Gate15 target-construction preflight with this proposal, then paired X2D/Z8 smokes only if it passes."
            if proposal_passes_internal_floor
            else "Revise thresholds or target construction before Gate15 preflight; not enough X2D positive rows."
        ),
    }


def render_html(proposal: dict[str, Any]) -> str:
    evidence = proposal["row_evidence"]
    thresholds = proposal["target_construction"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Gate15 Target Construction Proposal</title>
<style>
body {{ margin: 28px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }}
.card {{ border: 1px solid #d8dde3; border-radius: 8px; padding: 14px; }}
.value {{ font-size: 22px; font-weight: 760; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; }}
th {{ background: #eef2f7; }}
code {{ word-break: break-all; }}
</style></head><body>
<h1>Gate15 Target Construction Proposal</h1>
<div class="grid">
  <section class="card"><div>Candidate</div><div class="value">{html.escape(str(proposal['candidate_id']))}</div></section>
  <section class="card"><div>X2D positive rows</div><div class="value">{evidence['x2d_candidate_only_positive_floor_row_count']} / {evidence['x2d_minimum_rows_needed_for_median_floor']}</div></section>
  <section class="card"><div>Z8 no-op rows</div><div class="value">{evidence['z8_exact_noop_row_count']} / {evidence['z8_row_count']}</div></section>
  <section class="card"><div>Smoke requested</div><div class="value">{proposal['paired_smoke_requested']}</div></section>
</div>
<h2>Thresholds</h2>
<pre>{html.escape(json.dumps({k: thresholds[k] for k in sorted(thresholds) if k.endswith('_floor') or k.endswith('_cap') or k == 'z8_policy'}, indent=2, sort_keys=True))}</pre>
<h2>Row Evidence</h2>
<pre>{html.escape(json.dumps(evidence, indent=2, sort_keys=True))}</pre>
<p><strong>Next action:</strong> {html.escape(proposal['next_unambiguous_action'])}</p>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate14-target-builder", type=Path, default=DEFAULT_GATE14_TARGET_BUILDER)
    ap.add_argument("--gate14-target-npz", type=Path, default=DEFAULT_GATE14_TARGET_NPZ)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    ap.add_argument("--x2d-candidate-hf-floor", type=float, default=0.001)
    ap.add_argument("--x2d-residual-hf-floor", type=float, default=0.001)
    ap.add_argument("--x2d-render-y-floor", type=float, default=0.0005)
    ap.add_argument("--x2d-residual-hf-cap", type=float, default=0.04)
    args = ap.parse_args()

    proposal = build_proposal(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "target_construction_proposal.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(proposal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(proposal), encoding="utf-8")
    print(
        json.dumps(
            {
                "proposal": str(json_path),
                "dashboard": str(html_path),
                "candidate_id": proposal["candidate_id"],
                "paired_smoke_requested": proposal["paired_smoke_requested"],
                "x2d_positive_rows": proposal["row_evidence"]["x2d_candidate_only_positive_floor_row_count"],
                "x2d_rows_needed": proposal["row_evidence"]["x2d_minimum_rows_needed_for_median_floor"],
                "z8_exact_noop_rows": proposal["row_evidence"]["z8_exact_noop_row_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
