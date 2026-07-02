#!/usr/bin/env python3
"""Check the premium still-SR promotion boundary.

This is the product-level gate for the expensive still-SR pillar.  The project
has many diagnostic model receipts; this checker keeps those experiments from
being counted as a production 50 MP / 100 MP still-SR claim until the
scoreboard, no-REF/runtime policy, full still gate receipt, timing/memory, and
noise policy all agree.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_promotion_gate.v1"
SCOREBOARD_SCHEMA = "gpr.premium_still_sr_experiment_scoreboard.v1"
NOISE_GATE_SCHEMA = "gpr.premium_still_sr_noise_policy_gate.v1"
STILL_SR_GATE_SCHEMA = "gpr.premium_still_sr_gate.v1"
NEXT_CONTRACT_SCHEMA = "gpr.premium_still_sr_next_experiment_contract.v1"
REQUIREMENT_ID = "premium_still_sr_promotion_receipts"

DEFAULT_SCOREBOARD = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_experiment_scoreboard_restormer_t64_20260702/scoreboard.json"
)
DEFAULT_NOISE_GATE = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_noise_policy_gate_20260702/"
    "premium_still_sr_noise_policy_gate.json"
)
DEFAULT_GATE_RECEIPT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_readiness_20260701_refresh/"
    "premium_still_sr_gate_receipt.json"
)
DEFAULT_NEXT_CONTRACT = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_self_supervised_raw_sr_contract_20260702/"
    "premium_still_sr_next_experiment_contract.json"
)


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


def num(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    return float(value) if isinstance(value, (int, float)) else default


def integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    return int(value) if isinstance(value, int) else default


def nested(data: dict[str, Any], keys: list[str]) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def scoreboard_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if data.get("schema") != SCOREBOARD_SCHEMA:
        blockers.append("scoreboard schema mismatch")
    receipt_count = integer(data.get("receipt_count"))
    runtime_safe = integer(data.get("runtime_safe_candidate_count"))
    promotable = integer(data.get("promotable_candidate_count"))
    production_ready = bool(data.get("production_ready"))
    thresholds = data.get("promotion_thresholds") if isinstance(data.get("promotion_thresholds"), dict) else {}
    mae_floor = num(thresholds.get("holdout_residual_mae_reduction_pct_median"), 15.0)
    rmse_floor = num(thresholds.get("holdout_residual_rmse_reduction_pct_median"), 15.0)
    best_runtime_safe = data.get("best_runtime_safe_candidate") if isinstance(data.get("best_runtime_safe_candidate"), dict) else {}
    best_mae = num(best_runtime_safe.get("holdout_residual_mae_reduction_pct_median"), -999.0)
    best_rmse = num(best_runtime_safe.get("holdout_residual_rmse_reduction_pct_median"), -999.0)
    if receipt_count <= 0:
        blockers.append("scoreboard has no experiment receipts")
    if runtime_safe <= 0:
        blockers.append("scoreboard has no runtime-safe rows")
    if production_ready and promotable <= 0:
        blockers.append("scoreboard claims production_ready without promotable rows")
    if promotable > 0 and (best_mae < mae_floor or best_rmse < rmse_floor):
        blockers.append("scoreboard promotable count conflicts with best runtime-safe metrics")
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "receipt_count": receipt_count,
        "runtime_safe_candidate_count": runtime_safe,
        "promotable_candidate_count": promotable,
        "production_ready": production_ready,
        "mae_floor_pct": mae_floor,
        "rmse_floor_pct": rmse_floor,
        "best_runtime_safe_candidate": {
            "experiment": best_runtime_safe.get("experiment"),
            "path": best_runtime_safe.get("path"),
            "checkpoint_sha256": best_runtime_safe.get("checkpoint_sha256"),
            "holdout_mae_gain_pct": best_mae,
            "holdout_rmse_gain_pct": best_rmse,
            "runtime_safe": best_runtime_safe.get("runtime_safe"),
            "promotion_ready": best_runtime_safe.get("promotion_ready"),
        },
        "policy_pass": not blockers,
        "blockers": blockers,
    }


def noise_gate_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if data.get("schema") != NOISE_GATE_SCHEMA:
        blockers.append("noise policy gate schema mismatch")
    clean = data.get("clean_signal") if isinstance(data.get("clean_signal"), dict) else {}
    models = data.get("model_receipts") if isinstance(data.get("model_receipts"), list) else []
    clean_pass = clean.get("policy_pass") is True
    model_policy_pass_count = sum(1 for row in models if isinstance(row, dict) and row.get("policy_pass") is True)
    promotion_claim_count = sum(1 for row in models if isinstance(row, dict) and row.get("promotion_ready_claimed") is True)
    unsafe_promotion_claim_count = sum(
        1
        for row in models
        if isinstance(row, dict) and row.get("promotion_ready_claimed") is True and row.get("policy_pass") is not True
    )
    if not clean_pass:
        blockers.append("clean-signal/noise target policy does not pass")
    if bool(data.get("production_ready")) and model_policy_pass_count <= 0:
        blockers.append("noise gate claims production_ready without a passing model receipt")
    if unsafe_promotion_claim_count:
        blockers.append("one or more model receipts claim promotion despite policy blockers")
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "production_ready": bool(data.get("production_ready")),
        "decision": data.get("decision"),
        "clean_signal_policy_pass": clean_pass,
        "clean_signal_rows": integer(clean.get("row_count")),
        "rows_with_noise_sidecars": integer(clean.get("rows_with_noise_sidecars")),
        "model_receipt_count": len(models),
        "model_policy_pass_count": model_policy_pass_count,
        "promotion_claim_count": promotion_claim_count,
        "unsafe_promotion_claim_count": unsafe_promotion_claim_count,
        "policy_pass": not blockers,
        "blockers": blockers,
    }


def full_gate_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if data.get("schema") != STILL_SR_GATE_SCHEMA:
        blockers.append("premium still-SR gate receipt schema mismatch")
    production_ready = bool(data.get("production_ready"))
    runtime = data.get("runtime_policy") if isinstance(data.get("runtime_policy"), dict) else {}
    promotion = data.get("promotion_metrics") if isinstance(data.get("promotion_metrics"), dict) else {}
    fixtures = data.get("fixture_summary") if isinstance(data.get("fixture_summary"), dict) else {}
    performance = data.get("performance") if isinstance(data.get("performance"), dict) else {}
    noise = data.get("noise_policy") if isinstance(data.get("noise_policy"), dict) else {}
    if runtime.get("no_ref_runtime") is not True:
        blockers.append("gate receipt does not prove no-REF runtime")
    if runtime.get("forbidden_source_content_absent") is not True:
        blockers.append("gate receipt does not prove forbidden source content is absent")
    if production_ready:
        required_true = {
            "full_frame_gate_50mp_passed": promotion.get("full_frame_gate_50mp_passed"),
            "full_frame_gate_100mp_passed": promotion.get("full_frame_gate_100mp_passed"),
            "editor_latitude_passed": promotion.get("editor_latitude_passed"),
            "beats_current_baseline": promotion.get("beats_current_baseline"),
            "raw_noise_signal_audit_passed": noise.get("raw_noise_signal_audit_passed"),
            "exact_sidecars_only": noise.get("exact_sidecars_only"),
            "forbids_source_residual_noise": noise.get("forbids_source_residual_noise"),
        }
        for key, value in required_true.items():
            if value is not True:
                blockers.append(f"production gate receipt missing {key}=true")
        if promotion.get("severe_worst_row_failures") is not False:
            blockers.append("production gate receipt must have severe_worst_row_failures=false")
        if integer(fixtures.get("fifty_mp_or_larger_count")) <= 0:
            blockers.append("production gate receipt needs 50 MP-class fixtures")
        if integer(fixtures.get("hundred_mp_or_larger_count")) <= 0:
            blockers.append("production gate receipt needs 100 MP-class fixtures")
        if integer(promotion.get("full_frame_gate_50mp_row_count")) <= 0:
            blockers.append("production gate receipt needs 50 MP gate rows")
        if integer(promotion.get("full_frame_gate_100mp_row_count")) <= 0:
            blockers.append("production gate receipt needs 100 MP gate rows")
        if num(promotion.get("median_mae_reduction_pct_50mp")) <= 0:
            blockers.append("production gate receipt needs positive 50 MP median MAE reduction")
        if num(promotion.get("median_mae_reduction_pct_100mp")) <= 0:
            blockers.append("production gate receipt needs positive 100 MP median MAE reduction")
        if num(promotion.get("worst_row_mae_reduction_pct_50mp")) < 0:
            blockers.append("production gate receipt needs nonnegative 50 MP worst-row MAE reduction")
        if num(promotion.get("worst_row_mae_reduction_pct_100mp")) < 0:
            blockers.append("production gate receipt needs nonnegative 100 MP worst-row MAE reduction")
        if num(performance.get("render_seconds_per_50mp_frame")) <= 0:
            blockers.append("production gate receipt needs 50 MP render timing")
        if num(performance.get("render_seconds_per_100mp_frame")) <= 0:
            blockers.append("production gate receipt needs 100 MP render timing")
        if num(performance.get("peak_rss_gb")) <= 0:
            blockers.append("production gate receipt needs peak RSS")
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "production_ready": production_ready,
        "candidate": data.get("candidate"),
        "fixture_summary": fixtures,
        "promotion_metrics": {
            "full_frame_gate_50mp_passed": promotion.get("full_frame_gate_50mp_passed"),
            "full_frame_gate_100mp_passed": promotion.get("full_frame_gate_100mp_passed"),
            "full_frame_gate_50mp_row_count": integer(promotion.get("full_frame_gate_50mp_row_count")),
            "full_frame_gate_100mp_row_count": integer(promotion.get("full_frame_gate_100mp_row_count")),
            "median_mae_reduction_pct_50mp": num(promotion.get("median_mae_reduction_pct_50mp")),
            "median_mae_reduction_pct_100mp": num(promotion.get("median_mae_reduction_pct_100mp")),
            "beats_current_baseline": promotion.get("beats_current_baseline"),
            "editor_latitude_passed": promotion.get("editor_latitude_passed"),
            "severe_worst_row_failures": promotion.get("severe_worst_row_failures"),
        },
        "performance": performance,
        "noise_policy": noise,
        "policy_pass": not blockers,
        "blockers": blockers,
    }


def next_contract_status(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if data.get("schema") != NEXT_CONTRACT_SCHEMA:
        blockers.append("next-experiment contract schema mismatch")
    requirement = data.get("requirement") if isinstance(data.get("requirement"), dict) else {}
    if requirement.get("id") != REQUIREMENT_ID:
        blockers.append("next contract does not point at premium_still_sr_promotion_receipts")
    if requirement.get("status") != "open":
        blockers.append("premium still-SR requirement is not recorded as open")
    current = data.get("current_model_state") if isinstance(data.get("current_model_state"), dict) else {}
    if integer(current.get("scoreboard_promotable_candidate_count")) != 0:
        blockers.append("next contract model state says there are promotable candidates")
    if integer(current.get("scoreboard_receipt_count")) <= 0:
        blockers.append("next contract model state has no scoreboard receipts")
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "schema": data.get("schema"),
        "production_ready": bool(data.get("production_ready")),
        "requirement_id": requirement.get("id"),
        "requirement_status": requirement.get("status"),
        "scoreboard_receipt_count": integer(current.get("scoreboard_receipt_count")),
        "scoreboard_promotable_candidate_count": integer(current.get("scoreboard_promotable_candidate_count")),
        "blockers": blockers,
        "policy_pass": not blockers,
    }


def render_html(receipt: dict[str, Any]) -> str:
    cards = [
        ("Promotion safe", receipt["promotion_safe"]),
        ("Production ready", receipt["production_ready"]),
        ("Scoreboard receipts", receipt["scoreboard"]["receipt_count"]),
        ("Promotable rows", receipt["scoreboard"]["promotable_candidate_count"]),
        ("Best runtime-safe MAE", f"{receipt['scoreboard']['best_runtime_safe_candidate']['holdout_mae_gain_pct']:.3f}%"),
        ("Noise policy", "pass" if receipt["noise_policy_gate"]["clean_signal_policy_pass"] else "blocked"),
    ]
    card_html = "\n".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value)).lower()}</div>"
        "</section>"
        for label, value in cards
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in receipt["blockers"])
    if not blockers:
        blockers = "<li>None. The current non-promotion boundary is internally consistent.</li>"
    source_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td><code>{html.escape(section['path'])}</code></td>"
        f"<td>{html.escape(str(section.get('policy_pass'))).lower()}</td>"
        f"<td><code>{html.escape(section['sha256'])}</code></td>"
        "</tr>"
        for label, section in (
            ("scoreboard", receipt["scoreboard"]),
            ("noise policy", receipt["noise_policy_gate"]),
            ("full gate receipt", receipt["full_gate_receipt"]),
            ("next contract", receipt["next_contract"]),
        )
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Promotion Gate</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #121820; background: #f6f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; }}
.sub {{ color: #5c6773; max-width: 940px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dbe2e8; border-radius: 8px; padding: 14px; }}
.label {{ color: #5c6773; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 22px; font-weight: 760; overflow-wrap: anywhere; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dbe2e8; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Promotion Gate</h1>
<p class="sub">Consolidates the current experiment scoreboard, clean-signal/noise gate, formal still-SR gate receipt, and next-experiment contract. It is a shipment-boundary guard, not a trainer.</p>
<div class="grid">{card_html}</div>
<h2>Decision</h2>
<p>{html.escape(receipt["decision"])}</p>
<h2>Blockers</h2>
<ul>{blockers}</ul>
<h2>Inputs</h2>
<table><tr><th>input</th><th>path</th><th>policy pass</th><th>sha256</th></tr>{source_rows}</table>
</main></body></html>
"""


def build(args: argparse.Namespace) -> dict[str, Any]:
    scoreboard = scoreboard_status(args.scoreboard, load_json(args.scoreboard))
    noise = noise_gate_status(args.noise_policy_gate, load_json(args.noise_policy_gate))
    full_gate = full_gate_status(args.gate_receipt, load_json(args.gate_receipt))
    next_contract = next_contract_status(args.next_contract, load_json(args.next_contract))

    blockers: list[str] = []
    for label, section in (
        ("scoreboard", scoreboard),
        ("noise_policy_gate", noise),
        ("full_gate_receipt", full_gate),
        ("next_contract", next_contract),
    ):
        blockers.extend(f"{label}: {item}" for item in section["blockers"])

    production_ready = (
        scoreboard["production_ready"]
        and scoreboard["promotable_candidate_count"] > 0
        and noise["production_ready"]
        and noise["model_policy_pass_count"] > 0
        and full_gate["production_ready"]
        and not blockers
    )
    if full_gate["production_ready"] and not production_ready:
        blockers.append("full gate receipt claims production_ready but scoreboard/noise/current contract do not all pass")
    if scoreboard["production_ready"] and not production_ready:
        blockers.append("scoreboard claims production_ready but full promotion gate is incomplete")
    if noise["production_ready"] and not production_ready:
        blockers.append("noise policy claims production_ready but full promotion gate is incomplete")

    promotion_safe = not blockers
    if production_ready:
        decision = "premium still-SR production promotion is fully supported by the current receipts"
    elif promotion_safe:
        decision = (
            "premium still-SR is safely not promoted: current receipts are diagnostic, the requirement remains open, "
            "and no runtime-safe model clears the full 50 MP / 100 MP promotion boundary"
        )
    else:
        decision = "premium still-SR promotion boundary is inconsistent; fix receipts or product claims before shipping"

    receipt = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_ready": production_ready,
        "promotion_safe": promotion_safe,
        "decision": decision,
        "scoreboard": scoreboard,
        "noise_policy_gate": noise,
        "full_gate_receipt": full_gate,
        "next_contract": next_contract,
        "blockers": blockers,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "premium_still_sr_promotion_gate.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": json_path.as_posix(),
                "dashboard": html_path.as_posix(),
                "promotion_safe": promotion_safe,
                "production_ready": production_ready,
            },
            indent=2,
        )
    )
    if args.require_promotion_safe and not promotion_safe:
        return receipt | {"_exit_code": 1}
    if args.require_production_ready and not production_ready:
        return receipt | {"_exit_code": 1}
    return receipt | {"_exit_code": 0}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scoreboard", type=Path, default=DEFAULT_SCOREBOARD)
    ap.add_argument("--noise-policy-gate", type=Path, default=DEFAULT_NOISE_GATE)
    ap.add_argument("--gate-receipt", type=Path, default=DEFAULT_GATE_RECEIPT)
    ap.add_argument("--next-contract", type=Path, default=DEFAULT_NEXT_CONTRACT)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--require-promotion-safe", action="store_true")
    ap.add_argument("--require-production-ready", action="store_true")
    return ap.parse_args()


def main() -> int:
    return int(build(parse_args()).get("_exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
