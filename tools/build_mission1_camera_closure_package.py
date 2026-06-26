#!/usr/bin/env python3
"""Build the Mission 1 camera-side closure package.

The numbered-list readiness audit now leaves only camera-side receipts open.
This package records the exact remaining blockers, current stand-in receipts,
validators, acceptance fields, and target-access probe in one compact artifact.
It does not promote stand-in evidence to camera evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_camera_closure_package.v1"
DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_READINESS_REL = "artifacts/mission1_numbered_list_readiness_20260625/readiness.json"
DEFAULT_CLOSURE_REL = "artifacts/mission1_numbered_list_readiness_20260625/closure_plan.json"
DEFAULT_PREFLIGHT_REL = "artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_camera_sensor_ring_20260625.json"
FINAL_CAMERA_RECEIPTS = (
    "artifacts/mission1_camera_closure_run_20260625/current_camera/camera_handoff_receipt.json",
    "artifacts/mission1_camera_closure_run_20260625/current_camera/preview_ui_receipt.json",
)


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def receipt_row(root: Path, rel_path: str) -> dict[str, Any]:
    path = root / rel_path
    row: dict[str, Any] = {
        "path": rel_path,
        "exists": path.exists(),
    }
    if path.exists():
        row["sha256"] = sha256_file(path)
        try:
            data = read_json(path)
        except Exception as exc:
            row["json_error"] = str(exc)
        else:
            row["schema"] = data.get("schema")
            if isinstance(data.get("target"), dict):
                row["target"] = data["target"]
            if isinstance(data.get("inputs"), dict):
                row["inputs"] = data["inputs"]
            if isinstance(data.get("integration"), dict):
                row["integration"] = data["integration"]
            if isinstance(data.get("verdict"), dict):
                row["verdict"] = data["verdict"]
            if isinstance(data.get("blocker"), dict):
                row["blocker"] = data["blocker"]
            if isinstance(data.get("blockers"), list):
                row["blockers"] = data["blockers"]
    return row


def expected_value(value: str) -> Any:
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def dotted_get(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def acceptance_audit(root: Path, blocker: dict[str, Any]) -> dict[str, Any]:
    receipt_rel = blocker.get("required_receipt")
    acceptance = blocker.get("acceptance")
    checks: list[dict[str, Any]] = []
    receipt_data: dict[str, Any] | None = None
    if isinstance(receipt_rel, str):
        path = root / receipt_rel
        if path.exists():
            try:
                receipt_data = read_json(path)
            except Exception:
                receipt_data = None
    if isinstance(acceptance, list):
        for expression in acceptance:
            if not isinstance(expression, str) or "=" not in expression:
                continue
            key, raw_expected = expression.split("=", 1)
            key = key.strip()
            expected = expected_value(raw_expected.strip())
            observed = dotted_get(receipt_data or {}, key)
            checks.append(
                {
                    "expression": expression,
                    "path": key,
                    "expected": expected,
                    "observed": observed,
                    "passed": observed == expected,
                }
            )
    return {
        "item_id": blocker.get("item_id"),
        "item_title": blocker.get("item_title"),
        "required_receipt": receipt_rel,
        "receipt_exists": bool(isinstance(receipt_rel, str) and (root / receipt_rel).exists()),
        "checks": checks,
        "passed": bool(checks) and all(check.get("passed") is True for check in checks),
        "satisfied_count": sum(1 for check in checks if check.get("passed") is True),
        "check_count": len(checks),
    }


def ssh_probe(host: str, timeout_s: int) -> dict[str, Any]:
    if not host:
        return {"requested": False}
    started = time.time()
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={timeout_s}",
            host,
            "hostname; uname -m; df -h / /mnt/ssd 2>/dev/null || df -h /",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "requested": True,
        "host": host,
        "returncode": proc.returncode,
        "elapsed_s": round(time.time() - started, 3),
        "stdout": proc.stdout.strip().splitlines()[:12],
        "stderr": proc.stderr.strip().splitlines()[:12],
    }


def build_package(args: argparse.Namespace) -> dict[str, Any]:
    root = args.external_root
    readiness_path = root / args.readiness
    closure_path = root / args.closure_plan
    readiness = read_json(readiness_path)
    closure = read_json(closure_path)
    blockers = closure.get("blockers")
    if not isinstance(blockers, list):
        raise TypeError("closure_plan.blockers must be a list")

    current_receipts = []
    audits = []
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        receipt = blocker.get("required_receipt")
        if isinstance(receipt, str) and receipt:
            current_receipts.append(receipt_row(root, receipt))
        audits.append(acceptance_audit(root, blocker))
    if not blockers:
        current_receipts = [receipt_row(root, receipt) for receipt in FINAL_CAMERA_RECEIPTS]

    target_preflight = receipt_row(root, args.target_preflight) if args.target_preflight else {"exists": False}

    package: dict[str, Any] = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": str(root),
        "readiness": {
            "path": rel(readiness_path, root),
            "sha256": sha256_file(readiness_path),
            "overall_status": readiness.get("overall_status"),
            "production_ready": readiness.get("overall_status") == "production_ready",
            "blockers": readiness.get("blockers", []),
        },
        "closure_plan": {
            "path": rel(closure_path, root),
            "sha256": sha256_file(closure_path),
            "production_ready": closure.get("production_ready"),
            "final_gate_command": closure.get("final_gate_command"),
        },
        "remaining_blockers": blockers,
        "current_receipts": current_receipts,
        "acceptance_audit": audits,
        "target_preflight": target_preflight,
        "target_access": ssh_probe(args.target_host, args.ssh_timeout_s),
        "runbook": {
            "camera_handoff_validator": "python3 tools/check_labs_camera_handoff_receipt.py <camera_handoff_receipt.json>",
            "preview_ui_validator": "python3 tools/check_labs_preview_ui_receipt.py <preview_ui_receipt.json>",
            "target_preflight_validator": "python3 tools/mission1_camera_target_preflight.py --require-ready ...",
            "final_gate": "python3 tools/mission1_numbered_list_readiness.py --external-root /Volumes/OWC_8TB/gpr_work --require-production",
            "dispatch_reference": "docs/LABS_MISSION1_RUNBOOK.md",
            "firmware_api_reference": "docs/LABS_FIRMWARE_API.md",
        },
        "verdict": {
            "production_ready": False,
            "reason": "camera_receipts_missing" if blockers else "ready_to_run_final_gate",
            "remaining_blocker_count": len(blockers),
        },
    }
    if not blockers and readiness.get("overall_status") == "production_ready":
        package["verdict"] = {
            "production_ready": True,
            "reason": "numbered_list_final_gate_ready",
            "remaining_blocker_count": 0,
        }
    return package


def write_markdown(package: dict[str, Any], path: Path) -> None:
    lines = [
        "# Mission 1 Camera Closure Package",
        "",
        f"- readiness: `{package['readiness']['overall_status']}`",
        f"- production ready: `{package['verdict']['production_ready']}`",
        f"- remaining blockers: `{package['verdict']['remaining_blocker_count']}`",
        "",
        "## Remaining Receipts",
        "",
        "| item | blocker | required receipt | validator |",
        "|---:|---|---|---|",
    ]
    for blocker in package["remaining_blockers"]:
        lines.append(
            "| {item} | {blocker} | `{receipt}` | `{validator}` |".format(
                item=blocker.get("item_id", ""),
                blocker=blocker.get("blocker", ""),
                receipt=blocker.get("required_receipt", ""),
                validator=blocker.get("validator", ""),
            )
        )
    command_rows = [
        blocker
        for blocker in package["remaining_blockers"]
        if isinstance(blocker, dict) and blocker.get("closure_run_command")
    ]
    if command_rows:
        first = command_rows[0]
        lines.extend(
            [
                "",
                "## Aggregate Camera Closure Run",
                "",
                "This single run produces the camera handoff receipt, preview decode receipt,",
                "preview UI receipt, and aggregate `mission1_camera_closure_run.json`.",
                "",
                "```bash",
                str(first["closure_run_command"]),
                "```",
                "",
            ]
        )
        if first.get("closure_run_validation_command"):
            lines.extend(
                [
                    "Validate the aggregate receipt:",
                    "",
                    "```bash",
                    str(first["closure_run_validation_command"]),
                    "```",
                    "",
                ]
            )
    target_access = package.get("target_access")
    if isinstance(target_access, dict):
        lines.extend(
            [
                "",
                "## Target Access Probe",
                "",
                "| field | value |",
                "|---|---|",
                f"| requested | `{target_access.get('requested')}` |",
                f"| host | `{target_access.get('host', '')}` |",
                f"| return code | `{target_access.get('returncode', '')}` |",
                f"| elapsed | `{target_access.get('elapsed_s', '')}` s |",
            ]
        )
        stdout = target_access.get("stdout")
        stderr = target_access.get("stderr")
        if isinstance(stdout, list) and stdout:
            lines.extend(["", "stdout:", "", "```text", *[str(row) for row in stdout], "```"])
        if isinstance(stderr, list) and stderr:
            lines.extend(["", "stderr:", "", "```text", *[str(row) for row in stderr], "```"])
    preflight = package.get("target_preflight")
    if isinstance(preflight, dict):
        verdict = preflight.get("verdict") if isinstance(preflight.get("verdict"), dict) else {}
        blockers = preflight.get("blockers") if isinstance(preflight.get("blockers"), list) else []
        lines.extend(
            [
                "",
                "## Target Preflight",
                "",
                f"- receipt: `{preflight.get('path', '')}`",
                f"- exists: `{preflight.get('exists')}`",
                f"- target preflight ready: `{verdict.get('target_preflight_ready', '')}`",
                f"- camera closure possible: `{verdict.get('camera_closure_possible', '')}`",
            ]
        )
        if blockers:
            lines.extend(["", "Remaining preflight blockers:"])
            for blocker in blockers:
                lines.append(f"- `{blocker}`")
    lines.extend(["", "## Current Receipt State", "", "| receipt | target role | ready | blocker |", "|---|---|---:|---|"])
    for receipt in package["current_receipts"]:
        target = receipt.get("target") if isinstance(receipt.get("target"), dict) else {}
        verdict = receipt.get("verdict") if isinstance(receipt.get("verdict"), dict) else {}
        blocker = receipt.get("blocker") if isinstance(receipt.get("blocker"), dict) else {}
        ready = verdict.get("firmware_ready", verdict.get("ui_ready", ""))
        lines.append(
            f"| `{receipt.get('path')}` | `{target.get('role', '')}` | `{ready}` | {blocker.get('cause', '')} |"
        )
    audit_rows = [
        row
        for row in package.get("acceptance_audit", [])
        if isinstance(row, dict) and isinstance(row.get("checks"), list)
    ]
    if audit_rows:
        lines.extend(
            [
                "",
                "## Acceptance Audit",
                "",
                "| item | satisfied | required receipt | missing / false fields |",
                "|---:|---:|---|---|",
            ]
        )
        for audit in audit_rows:
            failed = [
                check.get("expression", "")
                for check in audit.get("checks", [])
                if isinstance(check, dict) and check.get("passed") is not True
            ]
            lines.append(
                "| {item} | {ok}/{total} | `{receipt}` | {failed} |".format(
                    item=audit.get("item_id", ""),
                    ok=audit.get("satisfied_count", 0),
                    total=audit.get("check_count", 0),
                    receipt=audit.get("required_receipt", ""),
                    failed=", ".join(str(x) for x in failed[:8]) if failed else "none",
                )
            )
    lines.extend(
        [
            "",
            "## Final Gate",
            "",
            "```bash",
            str(package["runbook"]["final_gate"]),
            "```",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--readiness", default=DEFAULT_READINESS_REL)
    ap.add_argument("--closure-plan", default=DEFAULT_CLOSURE_REL)
    ap.add_argument("--target-preflight", default=DEFAULT_PREFLIGHT_REL)
    ap.add_argument("--target-host", default="")
    ap.add_argument("--ssh-timeout-s", type=int, default=5)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-md", type=Path, required=True)
    args = ap.parse_args()

    package = build_package(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    write_markdown(package, args.output_md)
    print(json.dumps({"output_json": str(args.output_json), "output_md": str(args.output_md), "remaining_blockers": package["verdict"]["remaining_blocker_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
