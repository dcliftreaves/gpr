#!/usr/bin/env python3
"""Build the Premium still-SR model-floor gap receipt.

The promotion rollup says the first open step is `model_promotion_floor`.
This receipt turns that blocker into a quantitative, machine-readable contract:
how far the best current evidence is from the 15% / 15% floor, which lanes are
rejected, and what the next candidate must prove before any long run.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_model_floor_gap.v1"
DEFAULT_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_SCOREBOARD = DEFAULT_ROOT / "artifacts/premium_still_sr_experiment_scoreboard_masked_detail_20260702/scoreboard.json"
DEFAULT_SELECTOR_SMOKE = DEFAULT_ROOT / "artifacts/premium_still_sr_gate14_selector_smoke_20260702/selector_smoke.json"
DEFAULT_PROMOTION_ROLLUP = DEFAULT_ROOT / "artifacts/premium_still_sr_promotion_receipts_20260702/premium_still_sr_promotion_receipts.json"
DEFAULT_SELECTOR_SIDECAR = DEFAULT_ROOT / "artifacts/premium_still_sr_gate14_candidate_intake_20260702/selector_sidecar.json"
PROMOTION_FLOOR_PCT = 15.0


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    return float(value) if isinstance(value, (int, float)) else default


def integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    return int(value) if isinstance(value, int) else default


def scoreboard_summary(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    best = as_dict(data.get("best_runtime_safe_candidate"))
    best_mae = num(best.get("holdout_residual_mae_reduction_pct_median"), -999.0)
    best_rmse = num(best.get("holdout_residual_rmse_reduction_pct_median"), -999.0)
    return {
        "artifact": artifact(path),
        "receipt_count": integer(data.get("receipt_count")),
        "runtime_safe_candidate_count": integer(data.get("runtime_safe_candidate_count")),
        "promotable_candidate_count": integer(data.get("promotable_candidate_count")),
        "production_ready": data.get("production_ready") is True,
        "best_runtime_safe_experiment": best.get("experiment"),
        "best_runtime_safe_receipt": best.get("path"),
        "best_runtime_safe_checkpoint_sha256": best.get("checkpoint_sha256"),
        "best_runtime_safe_mae_pct": best_mae,
        "best_runtime_safe_rmse_pct": best_rmse,
        "best_runtime_safe_mae_gap_pct": max(0.0, PROMOTION_FLOOR_PCT - best_mae),
        "best_runtime_safe_rmse_gap_pct": max(0.0, PROMOTION_FLOOR_PCT - best_rmse),
    }


def selector_summary(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    metrics = as_dict(data.get("selector_smoke_metrics"))
    by_image = as_dict(metrics.get("by_image"))
    image_medians = [
        num(row.get("median"), 0.0)
        for row in by_image.values()
        if isinstance(row, dict)
    ]
    selector_median = num(metrics.get("median"), 0.0)
    return {
        "artifact": artifact(path),
        "passed": data.get("gate14_selector_smoke_passed") is True,
        "production_ready": data.get("production_ready") is True,
        "promotion_gate_allowed": data.get("promotion_gate_allowed") is True,
        "global_median_mae_pct": selector_median,
        "global_floor_gap_pct": max(0.0, PROMOTION_FLOOR_PCT - selector_median),
        "negative_row_count": integer(metrics.get("negative_row_count")),
        "selected_row_count": integer(metrics.get("selected_row_count")),
        "worst_image_median_mae_pct": min(image_medians) if image_medians else 0.0,
        "best_image_median_mae_pct": max(image_medians) if image_medians else 0.0,
    }


def rollup_summary(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": artifact(path),
        "production_ready": data.get("production_ready") is True,
        "completion_percent": num(data.get("completion_percent")),
        "done_step_count": integer(data.get("done_step_count")),
        "total_step_count": integer(data.get("total_step_count")),
        "first_open_step": data.get("first_open_step"),
        "blocker_classifications": as_list(data.get("blocker_classifications")),
    }


def sidecar_summary(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    runtime = as_dict(data.get("runtime_policy"))
    return {
        "artifact": artifact(path),
        "selector_id": data.get("selector_id"),
        "rule_count": len(as_list(data.get("rules"))),
        "source_count": len(as_list(data.get("sources"))),
        "allowed_runtime_inputs": as_list(runtime.get("allowed_runtime_inputs")),
        "forbidden_runtime_inputs": as_list(runtime.get("forbidden_runtime_inputs")),
        "fallback": runtime.get("fallback"),
        "rule_resolution": runtime.get("rule_resolution"),
    }


def build_contract(scoreboard: dict[str, Any], selector: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": "premium_still_sr_gate14_floor_student_v1",
        "candidate_goal": (
            "Distill the Gate 14 routed selector/source ensemble into a true candidate-only "
            "student or replace the source evidence with measured high/low raw evidence; "
            "do not scale any rejected single-source branch."
        ),
        "minimum_before_long_run": {
            "x2d_and_z8_smoke_required": True,
            "median_mae_recovery_pct": 1.0,
            "worst_row_mae_recovery_pct": 0.0,
            "selector_replay_must_remain_tail_safe": True,
            "z8_exact_noop_or_positive_source_evidence_required": True,
        },
        "promotion_floor": {
            "median_mae_recovery_pct": PROMOTION_FLOOR_PCT,
            "median_rmse_recovery_pct": PROMOTION_FLOOR_PCT,
            "best_current_runtime_safe_mae_gap_pct": scoreboard["best_runtime_safe_mae_gap_pct"],
            "best_current_runtime_safe_rmse_gap_pct": scoreboard["best_runtime_safe_rmse_gap_pct"],
            "gate14_selector_global_mae_gap_pct": selector["global_floor_gap_pct"],
        },
        "required_material_change": [
            "Use Gate 14 selector decisions as pseudo-label/source selection for a student, not as the final product.",
            "Train/evaluate with 50 MP and 100 MP route rows, not crop-only selector rows.",
            "Preserve exact no-op for low-confidence/low-error tiles and for Z8 until positive source evidence exists.",
            "Add timing and peak RSS around the actual render path before production submission.",
            "Keep runtime inputs limited to candidate_raw, camera metadata, candidate-derived features, and exact validated noise sidecars.",
        ],
        "rejected_as_primary_next_steps": [
            "another Gate 14 intake or selector-smoke replay",
            "frequency-pyramid source-evidence long run",
            "gated-residual source-evidence long run",
            "masked-detail/no-op threshold tuning",
            "raw-CFA source-frequency objective",
            "raw-CFA residual-signal objective",
            "candidate-HF no-op threshold-only tuning",
            "architecture-only Restormer/window-attention swap on the same clean-source pair objective",
        ],
    }


def render_html(receipt: dict[str, Any]) -> str:
    cards = [
        ("Verdict", receipt["verdict"]),
        ("Floor", f"{PROMOTION_FLOOR_PCT:.1f}%"),
        ("Best runtime-safe MAE", f"{receipt['scoreboard']['best_runtime_safe_mae_pct']:.3f}%"),
        ("Best runtime-safe RMSE", f"{receipt['scoreboard']['best_runtime_safe_rmse_pct']:.3f}%"),
        ("Gate 14 median MAE", f"{receipt['gate14_selector']['global_median_mae_pct']:.3f}%"),
        ("Next candidate", receipt["next_candidate_contract"]["candidate_id"]),
    ]
    card_html = "\n".join(
        f"<section class='card'><div class='label'>{html.escape(label)}</div><div class='value'>{html.escape(value)}</div></section>"
        for label, value in cards
    )
    rejected = "\n".join(
        f"<li>{html.escape(item)}</li>" for item in receipt["next_candidate_contract"]["rejected_as_primary_next_steps"]
    )
    required = "\n".join(
        f"<li>{html.escape(item)}</li>" for item in receipt["next_candidate_contract"]["required_material_change"]
    )
    inputs = "\n".join(
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td><code>{html.escape(section['artifact']['path'])}</code></td>"
        f"<td><code>{html.escape(str(section['artifact']['sha256']))}</code></td>"
        "</tr>"
        for label, section in receipt["inputs"].items()
    )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Model-Floor Gap</title>
<style>
body {{ margin: 30px; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f6f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ margin: 0 0 8px; font-size: 31px; }}
.sub {{ color: #5c6773; max-width: 960px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(185px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dbe2e8; border-radius: 8px; padding: 14px; }}
.label {{ color: #5c6773; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 21px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe2e8; margin: 14px 0 24px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; }}
</style>
<main>
<h1>Premium Still-SR Model-Floor Gap</h1>
<p class="sub">This is the first-open-step receipt behind the 4/8 promotion rollup. It quantifies the gap to the 15% / 15% floor and defines the next candidate contract.</p>
<div class="grid">{card_html}</div>
<h2>Required Material Change</h2>
<ul>{required}</ul>
<h2>Rejected As Primary Next Steps</h2>
<ul>{rejected}</ul>
<h2>Inputs</h2>
<table><tr><th>input</th><th>path</th><th>sha256</th></tr>{inputs}</table>
</main>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    scoreboard = scoreboard_summary(args.scoreboard, load_json(args.scoreboard))
    selector = selector_summary(args.selector_smoke, load_json(args.selector_smoke))
    rollup = rollup_summary(args.promotion_rollup, load_json(args.promotion_rollup))
    sidecar = sidecar_summary(args.selector_sidecar, load_json(args.selector_sidecar))
    contract = build_contract(scoreboard, selector)
    production_ready = (
        scoreboard["promotable_candidate_count"] > 0
        and scoreboard["production_ready"]
        and rollup["production_ready"]
    )
    verdict = "model_floor_passed" if production_ready else "blocked_below_model_promotion_floor"
    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_ready": production_ready,
        "verdict": verdict,
        "promotion_floor_pct": PROMOTION_FLOOR_PCT,
        "scoreboard": scoreboard,
        "gate14_selector": selector,
        "promotion_rollup": rollup,
        "selector_sidecar": sidecar,
        "next_candidate_contract": contract,
        "inputs": {
            "scoreboard": scoreboard,
            "gate14_selector": selector,
            "promotion_rollup": rollup,
            "selector_sidecar": sidecar,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "model_floor_gap.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": json_path.as_posix(),
                "dashboard": html_path.as_posix(),
                "verdict": verdict,
                "best_runtime_safe_mae_gap_pct": scoreboard["best_runtime_safe_mae_gap_pct"],
                "best_runtime_safe_rmse_gap_pct": scoreboard["best_runtime_safe_rmse_gap_pct"],
                "gate14_selector_global_mae_gap_pct": selector["global_floor_gap_pct"],
            },
            indent=2,
        )
    )
    if args.require_pass and not production_ready:
        return receipt | {"_exit_code": 1}
    return receipt | {"_exit_code": 0}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scoreboard", type=Path, default=DEFAULT_SCOREBOARD)
    ap.add_argument("--selector-smoke", type=Path, default=DEFAULT_SELECTOR_SMOKE)
    ap.add_argument("--promotion-rollup", type=Path, default=DEFAULT_PROMOTION_ROLLUP)
    ap.add_argument("--selector-sidecar", type=Path, default=DEFAULT_SELECTOR_SIDECAR)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--require-pass", action="store_true")
    return ap.parse_args()


def main() -> int:
    return int(build(parse_args()).get("_exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
