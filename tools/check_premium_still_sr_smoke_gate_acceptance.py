#!/usr/bin/env python3
"""Check whether premium still-SR smoke receipts earn a longer run.

Candidate preflight proves that a proposed run is not an obvious repeat. This
checker closes the next loop: it reads the exact X2D/Z8 smoke receipts named by
the preflight manifest and decides whether a longer training run is allowed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shlex
import sys
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_smoke_gate_acceptance.v1"
MANIFEST_SCHEMA = "gpr.premium_still_sr_candidate_preflight.v1"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path, help="candidate_preflight.json")
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--html-out", type=Path)
    ap.add_argument(
        "--require-pass",
        action="store_true",
        help="Exit nonzero unless every required smoke receipt passes.",
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


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def nested(data: dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def output_dirs_for_command(command: str) -> list[Path]:
    try:
        parts = shlex.split(command)
    except ValueError:
        return []
    out: list[Path] = []
    for idx, part in enumerate(parts):
        if part == "--output-dir" and idx + 1 < len(parts):
            out.append(Path(parts[idx + 1]))
        elif part.startswith("--output-dir="):
            out.append(Path(part.split("=", 1)[1]))
    return out


def holdout_for_command(command: str) -> str | None:
    text = command.lower()
    if "x2d" in text:
        return "x2d"
    if "z8" in text:
        return "z8"
    return None


def config_sha256(receipt: dict[str, Any]) -> str | None:
    config = receipt.get("config")
    if not isinstance(config, dict):
        return None
    payload = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def holdout_metric(receipt: dict[str, Any], key: str) -> Any:
    value = nested(receipt, ["eval", "holdout", key])
    if value is not None:
        return value
    raw_key = {
        "mae_improvement_pct": "raw_residual_mae_reduction_pct",
        "rmse_improvement_pct": "raw_residual_rmse_reduction_pct",
    }.get(key)
    if raw_key:
        return nested(receipt, ["eval", "holdout", raw_key])
    return None


def receipt_row(
    holdout: str,
    receipt_path: Path,
    receipt: dict[str, Any] | None,
    median_floor: float,
    worst_floor: float,
) -> dict[str, Any]:
    failures: list[str] = []
    if receipt is None:
        return {
            "holdout": holdout,
            "receipt": receipt_path.as_posix(),
            "loaded": False,
            "passed": False,
            "failures": [f"missing or unreadable receipt: {receipt_path}"],
        }

    mae_metric = holdout_metric(receipt, "mae_improvement_pct")
    rmse_metric = holdout_metric(receipt, "rmse_improvement_pct")
    median_mae = number(mae_metric.get("median") if isinstance(mae_metric, dict) else None)
    worst_mae = number(mae_metric.get("min") if isinstance(mae_metric, dict) else None)
    median_rmse = number(rmse_metric.get("median") if isinstance(rmse_metric, dict) else None)
    baseline = nested(receipt, ["promotion", "baseline"])
    baseline_beaten = nested(receipt, ["promotion", "baseline_beaten_on_holdout"])
    if baseline is None and receipt.get("schema") == "gpr.premium_still_sr_raw_cfa_residual_model.v1":
        baseline = "same-color Bayer interpolation raw residual"
    if baseline_beaten is None and receipt.get("schema") == "gpr.premium_still_sr_raw_cfa_residual_model.v1":
        baseline_beaten = (
            median_mae is not None
            and worst_mae is not None
            and median_mae >= median_floor
            and worst_mae >= worst_floor
        )
    checkpoint_sha = receipt.get("checkpoint_sha256")
    cfg_sha = receipt.get("training_config_sha256") or receipt.get("config_sha256") or config_sha256(receipt)

    if median_mae is None or median_mae < median_floor:
        failures.append(
            f"median MAE improvement {median_mae} is below required floor {median_floor}"
        )
    if worst_mae is None or worst_mae < worst_floor:
        failures.append(
            f"worst-row MAE improvement {worst_mae} is below required floor {worst_floor}"
        )
    if baseline_beaten is not True:
        failures.append("receipt promotion.baseline_beaten_on_holdout is not true")
    if not checkpoint_sha:
        failures.append("checkpoint_sha256 is missing")
    if not cfg_sha:
        failures.append("training config hash is missing and could not be derived")

    return {
        "holdout": holdout,
        "receipt": receipt_path.as_posix(),
        "loaded": True,
        "passed": not failures,
        "failures": failures,
        "baseline": baseline,
        "baseline_beaten_on_holdout": baseline_beaten,
        "holdout_tile_count": (
            mae_metric.get("count")
            if isinstance(mae_metric, dict) and mae_metric.get("count") is not None
            else nested(receipt, ["eval", "holdout", "row_count"])
        ),
        "median_mae_improvement_pct": median_mae,
        "worst_row_mae_improvement_pct": worst_mae,
        "median_rmse_improvement_pct": median_rmse,
        "checkpoint_sha256": checkpoint_sha,
        "training_config_sha256": cfg_sha,
        "elapsed_seconds": receipt.get("elapsed_seconds") or receipt.get("train_seconds"),
    }


def build_audit(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    failures: list[str] = []
    if manifest.get("schema") not in {MANIFEST_SCHEMA, None}:
        failures.append(f"manifest schema must be {MANIFEST_SCHEMA}")

    acceptance = manifest.get("smoke_gate_acceptance")
    if not isinstance(acceptance, dict):
        acceptance = {}
        failures.append("manifest missing smoke_gate_acceptance")
    median_floor = number(acceptance.get("minimum_median_mae_reduction_pct"))
    worst_floor = number(acceptance.get("minimum_worst_row_mae_reduction_pct"))
    if median_floor is None:
        median_floor = 0.001
        failures.append("minimum_median_mae_reduction_pct missing; defaulted to 0.001")
    if worst_floor is None:
        worst_floor = 0.0
        failures.append("minimum_worst_row_mae_reduction_pct missing; defaulted to 0.0")

    commands = as_strings(manifest.get("smoke_gate_commands"))
    command_by_holdout: dict[str, str] = {}
    receipt_by_holdout: dict[str, Path] = {}
    for command in commands:
        holdout = holdout_for_command(command)
        if holdout is None or holdout in receipt_by_holdout:
            continue
        output_dirs = output_dirs_for_command(command)
        if output_dirs:
            command_by_holdout[holdout] = command
            receipt_by_holdout[holdout] = output_dirs[0] / "train_receipt.json"

    required_holdouts = {item.lower() for item in as_strings(acceptance.get("required_holdouts"))}
    if not required_holdouts:
        required_holdouts = {"x2d", "z8"}
    missing_holdouts = sorted(required_holdouts - set(receipt_by_holdout))
    if missing_holdouts:
        failures.append("missing smoke receipt command for holdout(s): " + ", ".join(missing_holdouts))

    rows: list[dict[str, Any]] = []
    for holdout in sorted(required_holdouts):
        path = receipt_by_holdout.get(holdout)
        receipt = None
        if path is not None and path.exists():
            try:
                receipt = load_json(path)
            except (OSError, json.JSONDecodeError, TypeError):
                receipt = None
        rows.append(
            receipt_row(
                holdout,
                path or Path(f"<missing-{holdout}-receipt>"),
                receipt,
                median_floor,
                worst_floor,
            )
        )

    for row in rows:
        failures.extend(f"{row['holdout']}: {item}" for item in row.get("failures", []))

    passed = not failures and all(row.get("passed") for row in rows)
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": manifest.get("candidate_id"),
        "manifest": manifest_path.as_posix(),
        "production_ready": False,
        "long_run_allowed": passed,
        "smoke_gate_passed": passed,
        "acceptance": {
            "baseline": acceptance.get("baseline"),
            "required_holdouts": sorted(required_holdouts),
            "minimum_median_mae_reduction_pct": median_floor,
            "minimum_worst_row_mae_reduction_pct": worst_floor,
        },
        "commands": command_by_holdout,
        "rows": rows,
        "failures": failures,
        "verdict": "long_run_allowed" if passed else "blocked_before_long_run",
    }


def write_html(audit: dict[str, Any], path: Path) -> None:
    status = "PASS" if audit.get("smoke_gate_passed") else "BLOCKED"
    row_html = []
    for row in audit.get("rows", []):
        failures = "; ".join(str(item) for item in row.get("failures", [])) or "None"
        row_html.append(
            "<tr>"
            f"<td>{html.escape(str(row.get('holdout')))}</td>"
            f"<td>{'PASS' if row.get('passed') else 'FAIL'}</td>"
            f"<td>{html.escape(str(row.get('median_mae_improvement_pct')))}</td>"
            f"<td>{html.escape(str(row.get('worst_row_mae_improvement_pct')))}</td>"
            f"<td>{html.escape(str(row.get('median_rmse_improvement_pct')))}</td>"
            f"<td>{html.escape(failures)}</td>"
            f"<td><code>{html.escape(str(row.get('receipt')))}</code></td>"
            "</tr>"
        )
    failures = "".join(f"<li>{html.escape(str(item))}</li>" for item in audit.get("failures", [])) or "<li>None</li>"
    body = f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Smoke Gate Acceptance</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #17202a; }}
.status {{ display: inline-block; padding: 6px 10px; border-radius: 4px; background: {'#d5f5e3' if status == 'PASS' else '#fadbd8'}; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
th, td {{ border-bottom: 1px solid #d6dbdf; padding: 8px; text-align: left; vertical-align: top; }}
code {{ background: #f4f6f7; padding: 2px 4px; border-radius: 3px; }}
</style>
<h1>Premium Still-SR Smoke Gate Acceptance</h1>
<p class="status"><b>{status}</b> {html.escape(str(audit.get('candidate_id') or ''))}</p>
<p>This gate decides whether a short candidate smoke earns a longer Premium Still-SR run. It does not claim production readiness.</p>
<table>
<thead><tr><th>Holdout</th><th>Status</th><th>Median MAE %</th><th>Worst MAE %</th><th>Median RMSE %</th><th>Failures</th><th>Receipt</th></tr></thead>
<tbody>{''.join(row_html)}</tbody>
</table>
<h2>Failures</h2>
<ul>{failures}</ul>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def main() -> int:
    args = parse_args()
    audit = build_audit(args.manifest)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.html_out:
        write_html(audit, args.html_out)
    print(json.dumps({"candidate_id": audit.get("candidate_id"), "verdict": audit["verdict"]}, sort_keys=True))
    if args.require_pass and not audit["smoke_gate_passed"]:
        for failure in audit["failures"]:
            print(f"smoke gate failure: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
