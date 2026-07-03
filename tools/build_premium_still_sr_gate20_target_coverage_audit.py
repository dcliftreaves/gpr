#!/usr/bin/env python3
"""Audit Gate20 rebuilt-supervision target coverage before training."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_gate20_target_coverage_audit.v1"
ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_PLAN = (
    ROOT
    / "artifacts/premium_still_sr_gate20_rebuilt_supervision_targets_20260703/target_expansion_plan/target_expansion_plan.json"
)
DEFAULT_BUILD_RECEIPT = (
    ROOT
    / "artifacts/premium_still_sr_gate20_rebuilt_supervision_targets_20260703/expanded_hf_targets/expanded_target_build_receipt.json"
)
DEFAULT_STRICT_PLAN = (
    ROOT
    / "artifacts/premium_still_sr_gate20_rebuilt_supervision_targets_strict_20260703/target_expansion_plan/target_expansion_plan.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/premium_still_sr_gate20_target_coverage_audit_20260703"
ROWS_PER_CLASS_FLOOR = 576
TOTAL_ROW_FLOOR = 1152


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def source_class(scene: dict[str, Any]) -> str:
    source_path = str(scene.get("source_path") or "").lower()
    scene_id = str(scene.get("scene_id") or "").lower()
    if "z8" in source_path or scene_id.startswith("z8"):
        return "50mp"
    if "mission" in source_path or "gopro" in source_path:
        return "50mp"
    if "x2d" in source_path or "austin" in scene_id or "x2d" in scene_id:
        return "100mp"
    return "unknown"


def rows_from_scene(scene: dict[str, Any]) -> int:
    for result in reversed(scene.get("command_results") or []):
        stdout = result.get("stdout")
        if not isinstance(stdout, str) or not stdout.strip():
            continue
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            continue
        rows = payload.get("rows")
        if isinstance(rows, int):
            return rows
    return 0


def actual_coverage(build_receipt: dict[str, Any]) -> dict[str, Any]:
    by_class = {"50mp": 0, "100mp": 0, "unknown": 0}
    scenes_by_class = {"50mp": 0, "100mp": 0, "unknown": 0}
    for scene in build_receipt.get("scene_results") or []:
        if not isinstance(scene, dict) or scene.get("built") is not True:
            continue
        cls = source_class(scene)
        by_class[cls] = by_class.get(cls, 0) + rows_from_scene(scene)
        scenes_by_class[cls] = scenes_by_class.get(cls, 0) + 1
    return {
        "rows_by_class": by_class,
        "scenes_by_class": scenes_by_class,
        "total_rows": sum(by_class.values()),
        "total_scenes": sum(scenes_by_class.values()),
    }


def planned_coverage(plan: dict[str, Any]) -> dict[str, Any]:
    rows_by_class = {"50mp": 0, "100mp": 0, "unknown": 0}
    scenes_by_class = {"50mp": 0, "100mp": 0, "unknown": 0}
    current = plan.get("current_target") or {}
    current_rows = int(current.get("row_count") or 0)
    current_scenes = int(current.get("scene_count") or 0)
    if current_rows:
        rows_by_class["100mp"] += current_rows
        scenes_by_class["100mp"] += current_scenes
    for target in plan.get("selected_new_targets") or []:
        if not isinstance(target, dict):
            continue
        cls = str(target.get("class") or "unknown")
        if cls not in rows_by_class:
            cls = "unknown"
        rows_by_class[cls] += 27
        scenes_by_class[cls] += 1
    return {
        "rows_by_class": rows_by_class,
        "scenes_by_class": scenes_by_class,
        "total_rows": sum(rows_by_class.values()),
        "total_scenes": sum(scenes_by_class.values()),
    }


def pass_summary(coverage: dict[str, Any]) -> dict[str, Any]:
    rows = coverage["rows_by_class"]
    return {
        "row_floor_50mp_passed": int(rows.get("50mp") or 0) >= ROWS_PER_CLASS_FLOOR,
        "row_floor_100mp_passed": int(rows.get("100mp") or 0) >= ROWS_PER_CLASS_FLOOR,
        "total_row_floor_passed": int(coverage.get("total_rows") or 0) >= TOTAL_ROW_FLOOR,
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_json(args.plan)
    build = load_json(args.build_receipt)
    strict = load_json(args.strict_plan)
    actual = actual_coverage(build)
    strict_cov = planned_coverage(strict)
    actual_pass = pass_summary(actual)
    strict_pass = pass_summary(strict_cov)
    training_authorized = all(actual_pass.values())
    strict_plan_can_authorize = all(strict_pass.values())
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "production_ready": False,
        "gate20_training_authorized": training_authorized,
        "strict_plan_can_authorize_training": strict_plan_can_authorize,
        "inputs": {
            "plan": str(args.plan),
            "plan_sha256": sha256_file(args.plan),
            "build_receipt": str(args.build_receipt),
            "build_receipt_sha256": sha256_file(args.build_receipt),
            "strict_plan": str(args.strict_plan),
            "strict_plan_sha256": sha256_file(args.strict_plan),
        },
        "actual_rebuilt_target_coverage": actual,
        "actual_pass_summary": actual_pass,
        "strict_plan_coverage": strict_cov,
        "strict_plan_pass_summary": strict_pass,
        "thresholds": {
            "rows_per_class_floor": ROWS_PER_CLASS_FLOOR,
            "total_row_floor": TOTAL_ROW_FLOOR,
            "promotion_mae_rmse_floor_pct": 15.0,
        },
        "next_decision": (
            "gate20_training_authorized"
            if training_authorized
            else "gate20_target_coverage_blocked_add_100mp_rebuilt_supervision_sources"
        ),
        "next_steps": [
            "Add or locate more X2D/100 MP DNG sources with validated camera-noise sidecars.",
            "Rerun the strict Gate20 target expansion plan until 100 MP rebuilt-supervision rows reach 576.",
            "Only then run expanded target generation, no-REF preflight, Gate20 training, and broad target-row audit.",
        ],
    }


def render_html(receipt: dict[str, Any]) -> str:
    def table(title: str, coverage: dict[str, Any], passed: dict[str, Any]) -> str:
        rows = "".join(
            f"<tr><th>{html.escape(cls)}</th><td>{coverage['scenes_by_class'].get(cls, 0)}</td>"
            f"<td>{coverage['rows_by_class'].get(cls, 0)}</td><td>{ROWS_PER_CLASS_FLOOR}</td></tr>"
            for cls in ("50mp", "100mp", "unknown")
        )
        return (
            f"<h2>{html.escape(title)}</h2><table><tr><th>class</th><th>scenes</th><th>rows</th>"
            f"<th>row floor</th></tr>{rows}</table><pre>{html.escape(json.dumps(passed, indent=2))}</pre>"
        )

    return f"""<!doctype html>
<meta charset="utf-8">
<title>Gate20 Target Coverage Audit</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:32px;color:#18202a;line-height:1.45}}
table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #d9dee7;padding:8px;text-align:left}}th{{background:#f4f6f9}}
code,pre{{background:#f4f6f9;padding:8px;border-radius:4px;white-space:pre-wrap}}
.bad{{color:#9d1d20;font-weight:700}}
</style>
<h1>Gate20 Target Coverage Audit</h1>
<p class="bad">Decision: <code>{html.escape(receipt["next_decision"])}</code></p>
<p>Gate20 training authorized: <code>{str(receipt["gate20_training_authorized"]).lower()}</code></p>
{table("Actual Rebuilt Targets", receipt["actual_rebuilt_target_coverage"], receipt["actual_pass_summary"])}
{table("Strict Planner Upper Bound", receipt["strict_plan_coverage"], receipt["strict_plan_pass_summary"])}
<h2>Next Steps</h2>
<ol>{''.join(f"<li>{html.escape(item)}</li>" for item in receipt["next_steps"])}</ol>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    ap.add_argument("--build-receipt", type=Path, default=DEFAULT_BUILD_RECEIPT)
    ap.add_argument("--strict-plan", type=Path, default=DEFAULT_STRICT_PLAN)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args)
    receipt_path = args.output_dir / "gate20_target_coverage_audit.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "dashboard": str(html_path), "next_decision": receipt["next_decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
