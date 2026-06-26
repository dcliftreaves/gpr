#!/usr/bin/env python3
"""Verify external artifacts referenced by docs/release_evidence_manifest.json.

The release manifest indexes dashboards, JSON receipts, rendered media, run
logs, and directory receipts that stay outside git. Default mode inventories
those paths and exits 0 so hosted CI can exercise the resolver without the
external drive. Use --strict for release promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs/release_evidence_manifest.json"
TOOL_ROOT = Path(__file__).resolve().parent
PRODUCTION_ARTIFACTS = "docs/PRODUCTION_ARTIFACTS.md"
STANDIN_TOKENS = (
    "stand-in",
    "file-backed",
    "bench_fused",
    "page-cache",
    "filesystem",
    "off-camera",
    "pi 5",
    "pi5",
)


def external_root(manifest: dict[str, Any]) -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or manifest.get("external_root") or "/Volumes/OWC_8TB/gpr_work")


def artifact_root(manifest: dict[str, Any]) -> Path:
    return Path(os.environ.get("GPR_ARTIFACT_ROOT") or external_root(manifest) / "artifacts")


def artifact_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str):
        if value.startswith("artifacts/"):
            refs.add(value)
        return refs
    if isinstance(value, list):
        for item in value:
            refs.update(artifact_refs(item))
        return refs
    if isinstance(value, dict):
        for item in value.values():
            refs.update(artifact_refs(item))
    return refs


def candidate_paths(ref: str, manifest: dict[str, Any]) -> list[Path]:
    path = Path(ref)
    if path.is_absolute():
        return [path]
    candidates = [external_root(manifest) / path]
    if path.parts and path.parts[0] == "artifacts":
        candidates.append(artifact_root(manifest) / Path(*path.parts[1:]))
    out: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            out.append(candidate)
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def production_artifact_hashes() -> dict[str, str]:
    path = REPO / PRODUCTION_ARTIFACTS
    if not path.exists():
        return {}
    pattern = re.compile(r"\|\s*[^|]+\|\s*`(artifacts/[^`]+)`\s*\|\s*`([0-9a-f]{64})`\s*\|")
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def classify(path: Path | None) -> tuple[str, str | None, int | None]:
    if path is None:
        return "missing", None, None
    if path.is_dir():
        try:
            has_child = any(path.iterdir())
        except OSError as exc:
            return "unreadable", str(exc), None
        return ("ok" if has_child else "empty_dir"), None, None
    if not path.is_file():
        return "not_file_or_dir", None, None
    try:
        size = path.stat().st_size
    except OSError as exc:
        return "unreadable", str(exc), None
    if size <= 0:
        return "empty_file", None, size
    if path.suffix == ".json":
        try:
            with path.open("r", encoding="utf-8") as f:
                json.load(f)
        except Exception as exc:
            return "bad_json", str(exc), size
    return "ok", None, size


def verify_documented_hash_ref(ref: str, expected_sha: str, manifest: dict[str, Any]) -> dict[str, Any]:
    candidates = candidate_paths(ref, manifest)
    resolved = next((path for path in candidates if path.exists()), None)
    status, error, size = classify(resolved)
    actual_sha = None
    if status == "ok" and resolved is not None and resolved.is_file():
        actual_sha = sha256_file(resolved)
        if actual_sha != expected_sha:
            status = "sha_mismatch"
            error = f"{PRODUCTION_ARTIFACTS} records {expected_sha}, actual {actual_sha}"
    return {
        "ref": ref,
        "resolved": str(resolved) if resolved else None,
        "status": status,
        "size_bytes": size,
        "error": error,
        "expected_sha256": expected_sha,
        "actual_sha256": actual_sha,
        "searched": [str(path) for path in candidates],
    }


def mission1_closure_plan_entry(manifest: dict[str, Any]) -> dict[str, Any] | None:
    dashboards = manifest.get("dashboards")
    if not isinstance(dashboards, list):
        return None
    for entry in dashboards:
        if isinstance(entry, dict) and entry.get("id") == "mission1_numbered_list_closure_plan":
            return entry
    return None


def load_repo_validator(script_name: str):
    path = TOOL_ROOT / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "validate"):
        return module.validate
    if hasattr(module, "validate_receipt"):
        return module.validate_receipt
    raise RuntimeError(f"{path} does not expose validate or validate_receipt")


def validate_mission1_camera_closure_package(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"camera closure package JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "camera closure package must be a JSON object"
    try:
        failures = load_repo_validator("check_mission1_camera_closure_package.py")(data)
    except Exception as exc:
        return f"camera closure package validator failed: {exc}"
    if failures:
        return "camera closure package failed validation: " + "; ".join(str(row) for row in failures[:6])
    return None


def validate_mission1_4k_cleanup_signoff(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"4K cleanup signoff JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "4K cleanup signoff must be a JSON object"
    try:
        failures = load_repo_validator("check_mission1_4k_cleanup_signoff_receipt.py")(data)
    except Exception as exc:
        return f"4K cleanup signoff validator failed: {exc}"
    if failures:
        return "4K cleanup signoff failed validation: " + "; ".join(str(row) for row in failures[:6])
    raw_guard = data.get("raw_domain_guard")
    if not isinstance(raw_guard, dict):
        return "4K cleanup signoff must include raw_domain_guard"
    if raw_guard.get("kind") != "high_res_cfa_target":
        return "current 4K cleanup signoff must use high_res_cfa_target raw guard"
    if raw_guard.get("passed") is not True:
        return "current 4K cleanup signoff must have raw_domain_guard.passed=true"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict) or verdict.get("production_ready") is not True:
        return "current 4K cleanup signoff must claim production_ready after high-res CFA raw guard passes"
    if data.get("blocker") is not None:
        return "current 4K cleanup production signoff must not include blocker"
    diagnostics = data.get("diagnostics")
    if not isinstance(diagnostics, dict) or "legacy_clean_low_raw_guard" not in diagnostics:
        return "current 4K cleanup signoff must retain legacy clean-low diagnostic"
    return None


def has_flag_with_nonempty_value(cmd: list[Any], flag: str) -> bool:
    for idx, arg in enumerate(cmd[:-1]):
        if arg == flag and isinstance(cmd[idx + 1], str) and bool(cmd[idx + 1].strip()):
            return True
    return False


def validate_preflight_label_command(cmd: Any, prefix: str) -> str | None:
    if not isinstance(cmd, list):
        return f"{prefix} command must be a list"
    for flag in ("--frame-source", "--write-path", "--storage-medium", "--display-surface", "--presentation-path"):
        if not has_flag_with_nonempty_value(cmd, flag):
            return f"{prefix} command must include {flag}"
    if "--raw-source-kind" not in cmd or not any(arg in {"sensor_dma_capture", "camera_ring_buffer"} for arg in cmd):
        return f"{prefix} command must include camera raw-source-kind"
    return None


def command_flag_value(cmd: list[Any], flag: str) -> str | None:
    for idx, arg in enumerate(cmd[:-1]):
        if arg == flag and isinstance(cmd[idx + 1], str) and cmd[idx + 1].strip():
            return cmd[idx + 1]
    return None


def contains_standin_path_token(value: str) -> str | None:
    lowered = value.lower()
    for token in ("fixture", "fixtures", "file-backed", "stand-in", "standin", "mission1_native12", "gp017"):
        if token in lowered:
            return token
    return None


def validate_camera_raw_path(value: str | None, prefix: str) -> str | None:
    if not value:
        return f"{prefix} command must include a non-empty camera raw path"
    token = contains_standin_path_token(value)
    if token:
        return f"{prefix} command cannot use stand-in token {token!r} in camera raw path: {value}"
    return None


def validate_mission1_camera_closure_launch(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"camera closure launch JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "camera closure launch must be a JSON object"
    if data.get("schema") != "gpr.mission1_target_closure_package_run.v1":
        return "camera closure launch schema mismatch"
    if data.get("dry_run") is not True:
        return "camera closure launch must be a dry-run artifact"
    target = data.get("target")
    if not isinstance(target, dict) or target.get("role") != "camera":
        return "camera closure launch target.role must be camera"
    if target.get("raw_source_kind") not in {"sensor_dma_capture", "camera_ring_buffer"}:
        return "camera closure launch target.raw_source_kind must be sensor_dma_capture or camera_ring_buffer"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        return "camera closure launch verdict must be an object"
    if verdict.get("command_ready") is not True:
        return "camera closure launch must have command_ready=true"
    if verdict.get("production_ready") is not False:
        return "camera closure launch dry-run must not claim production_ready"
    repo_root = data.get("repo_root")
    if isinstance(repo_root, str) and not repo_root.startswith("/mnt/ssd/"):
        return "camera closure launch repo_root must be a target-side /mnt/ssd path"
    steps = data.get("steps")
    if not isinstance(steps, list):
        return "camera closure launch steps must be a list"
    step_names = [step.get("name") for step in steps if isinstance(step, dict)]
    expected = [
        "validate_dispatch_inputs",
        "camera_hardware_audit",
        "target_preflight",
        "camera_closure_run",
        "collect_compact_receipts",
    ]
    if step_names != expected:
        return f"camera closure launch step names mismatch: {step_names!r}"
    if not all(step.get("returncode") == 0 for step in steps if isinstance(step, dict)):
        return "camera closure launch all planned steps must have returncode=0"
    collection_cmd = steps[-1].get("cmd") if isinstance(steps[-1], dict) else None
    if not isinstance(collection_cmd, list) or "--include-timing-receipts" not in collection_cmd:
        return "camera closure launch collection command must include --include-timing-receipts"
    hardware_cmd = steps[1].get("cmd") if isinstance(steps[1], dict) else None
    if not isinstance(hardware_cmd, list) or "--require-camera" not in hardware_cmd:
        return "camera closure launch hardware audit command must include --require-camera"
    preflight_cmd = steps[2].get("cmd") if isinstance(steps[2], dict) else None
    preflight_error = validate_preflight_label_command(preflight_cmd, "camera closure launch target_preflight")
    if preflight_error:
        return preflight_error
    dispatch_cmd = steps[0].get("cmd") if isinstance(steps[0], dict) else None
    if (
        not isinstance(dispatch_cmd, list)
        or "--raw-source-kind" not in dispatch_cmd
        or not any(arg in {"sensor_dma_capture", "camera_ring_buffer"} for arg in dispatch_cmd)
    ):
        return "camera closure launch dispatch command must include camera raw-source-kind"
    raw_path_error = validate_camera_raw_path(
        command_flag_value(dispatch_cmd, "--raw-path"),
        "camera closure launch dispatch",
    )
    if raw_path_error:
        return raw_path_error
    closure_cmd = steps[3].get("cmd") if isinstance(steps[3], dict) else None
    if (
        not isinstance(closure_cmd, list)
        or "--raw-source-kind" not in closure_cmd
        or not any(arg in {"sensor_dma_capture", "camera_ring_buffer"} for arg in closure_cmd)
    ):
        return "camera closure launch closure command must include camera raw-source-kind"
    if "--target-preflight-receipt" not in closure_cmd:
        return "camera closure launch closure command must include --target-preflight-receipt"
    raw_path_error = validate_camera_raw_path(
        command_flag_value(closure_cmd, "--raw"),
        "camera closure launch closure",
    )
    if raw_path_error:
        return raw_path_error
    forbidden_prefixes = ("/Volumes/", "/Users/", "/opt/homebrew/")
    for step in steps:
        cmd = step.get("cmd") if isinstance(step, dict) else None
        if not isinstance(cmd, list):
            return "camera closure launch step cmd must be a list"
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith(forbidden_prefixes):
                return f"camera closure launch command contains host-local path: {arg}"
    return None


def validate_mission1_remote_closure_launch(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"remote closure launch JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "remote closure launch must be a JSON object"
    if data.get("schema") != "gpr.mission1_remote_closure_package_run.v1":
        return "remote closure launch schema mismatch"
    if data.get("dry_run") is not True:
        return "remote closure launch manifest artifact must be dry-run"
    if data.get("target_host") != "192.168.16.67":
        return "remote closure launch target_host mismatch"
    repo_root = data.get("remote_repo_root")
    if not isinstance(repo_root, str) or not repo_root.startswith("/mnt/ssd/"):
        return "remote closure launch remote_repo_root must be a target-side /mnt/ssd path"
    if data.get("target_role") != "camera":
        return "remote closure launch target_role must be camera"
    if data.get("raw_source_kind") not in {"sensor_dma_capture", "camera_ring_buffer"}:
        return "remote closure launch raw_source_kind must be sensor_dma_capture or camera_ring_buffer"
    camera_flags = data.get("camera_ready_flags")
    if not isinstance(camera_flags, dict) or not all(value is True for value in camera_flags.values()):
        return "remote closure launch camera_ready_flags must all be true"
    package_step = data.get("package_step")
    if not isinstance(package_step, dict) or package_step.get("returncode") != 0:
        return "remote closure launch package_step.returncode must be 0"
    package_cmd = package_step.get("cmd")
    package_cmd_text = " ".join(str(arg) for arg in package_cmd) if isinstance(package_cmd, list) else ""
    if (
        not isinstance(package_cmd, list)
        or "--raw-source-kind" not in package_cmd_text
        or not any(kind in package_cmd_text for kind in ("sensor_dma_capture", "camera_ring_buffer"))
    ):
        return "remote closure launch package_step command must include camera raw-source-kind"
    if "/dev/mission1/sensor_dma_ring" not in package_cmd_text:
        return "remote closure launch package_step command must include camera ring-buffer raw path"
    for flag in ("--frame-source", "--write-path", "--storage-medium", "--display-surface", "--presentation-path"):
        if flag not in package_cmd_text:
            return f"remote closure launch package_step command must include {flag}"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict) or verdict.get("launch_valid") is not True:
        return "remote closure launch verdict.launch_valid must be true"
    if verdict.get("production_ready") is not False:
        return "remote closure launch dry-run must not claim production_ready"
    target_package = data.get("target_package")
    if not isinstance(target_package, dict):
        return "remote closure launch target_package must be an object"
    if target_package.get("schema") != "gpr.mission1_target_closure_package_run.v1":
        return "remote closure launch target_package schema mismatch"
    if target_package.get("dry_run") is not True:
        return "remote closure launch target_package must be dry-run"
    target = target_package.get("target")
    if not isinstance(target, dict) or target.get("role") != "camera":
        return "remote closure launch target_package target.role must be camera"
    if target.get("raw_source_kind") not in {"sensor_dma_capture", "camera_ring_buffer"}:
        return "remote closure launch target_package target.raw_source_kind must be sensor_dma_capture or camera_ring_buffer"
    target_verdict = target_package.get("verdict")
    if not isinstance(target_verdict, dict) or target_verdict.get("command_ready") is not True:
        return "remote closure launch target_package command_ready must be true"
    if target_verdict.get("production_ready") is not False:
        return "remote closure launch target_package dry-run must not claim production_ready"
    target_steps = target_package.get("steps")
    if not isinstance(target_steps, list):
        return "remote closure launch target_package steps must be a list"
    target_step_names = [step.get("name") for step in target_steps if isinstance(step, dict)]
    expected_target_steps = [
        "validate_dispatch_inputs",
        "camera_hardware_audit",
        "target_preflight",
        "camera_closure_run",
        "collect_compact_receipts",
    ]
    if target_step_names != expected_target_steps:
        return f"remote closure launch target_package step names mismatch: {target_step_names!r}"
    forbidden_prefixes = ("/Volumes/", "/Users/", "/opt/homebrew/")
    for step in target_steps:
        cmd = step.get("cmd") if isinstance(step, dict) else None
        if not isinstance(cmd, list):
            return "remote closure launch target_package step cmd must be a list"
        if step.get("name") == "camera_hardware_audit":
            if "--require-camera" not in cmd:
                return "remote closure launch target_package hardware audit must include --require-camera"
        if step.get("name") == "target_preflight":
            preflight_error = validate_preflight_label_command(
                cmd,
                "remote closure launch target_package target_preflight",
            )
            if preflight_error:
                return preflight_error
        if step.get("name") in {"validate_dispatch_inputs", "camera_closure_run"}:
            if "--raw-source-kind" not in cmd or not any(arg in {"sensor_dma_capture", "camera_ring_buffer"} for arg in cmd):
                return "remote closure launch target_package camera command must include camera raw-source-kind"
            raw_flag = "--raw-path" if step.get("name") == "validate_dispatch_inputs" else "--raw"
            raw_path_error = validate_camera_raw_path(
                command_flag_value(cmd, raw_flag),
                f"remote closure launch target_package {step.get('name')}",
            )
            if raw_path_error:
                return raw_path_error
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith(forbidden_prefixes):
                return f"remote closure launch target_package contains host-local path: {arg}"
    return None


def validate_mission1_camera_hw_blocked_target_package_data(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "camera hardware-blocked target package must be a JSON object"
    if data.get("schema") != "gpr.mission1_target_closure_package_run.v1":
        return "camera hardware-blocked target package schema mismatch"
    if data.get("dry_run") is not False:
        return "camera hardware-blocked target package must be a real non-dry run"
    target = data.get("target")
    if not isinstance(target, dict) or target.get("role") != "camera":
        return "camera hardware-blocked target package target.role must be camera"
    if target.get("raw_source_kind") != "sensor_dma_capture":
        return "camera hardware-blocked target package raw_source_kind must be sensor_dma_capture"
    for key in ("repo_root", "output_dir", "collection_output_dir"):
        value = data.get(key)
        if not isinstance(value, str) or not value.startswith("/mnt/ssd/"):
            return f"camera hardware-blocked target package {key} must be target-side /mnt/ssd path"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        return "camera hardware-blocked target package verdict must be an object"
    if verdict.get("command_ready") is not False:
        return "camera hardware-blocked target package must not claim command_ready"
    if verdict.get("production_ready") is not False:
        return "camera hardware-blocked target package must not claim production_ready"
    if verdict.get("reason") != "camera_hardware_audit_failed":
        return "camera hardware-blocked target package reason must be camera_hardware_audit_failed"
    steps = data.get("steps")
    if not isinstance(steps, list):
        return "camera hardware-blocked target package steps must be a list"
    step_names = [step.get("name") for step in steps if isinstance(step, dict)]
    if step_names != ["validate_dispatch_inputs", "camera_hardware_audit"]:
        return f"camera hardware-blocked target package step names mismatch: {step_names!r}"
    dispatch_cmd = steps[0].get("cmd") if isinstance(steps[0], dict) else None
    if not isinstance(dispatch_cmd, list) or steps[0].get("returncode") != 0:
        return "camera hardware-blocked target package dispatch step must pass"
    if command_flag_value(dispatch_cmd, "--raw-source-kind") != "sensor_dma_capture":
        return "camera hardware-blocked target package dispatch raw-source-kind mismatch"
    if command_flag_value(dispatch_cmd, "--raw-path") != "/dev/mission1/sensor_dma_ring":
        return "camera hardware-blocked target package dispatch must target the sensor DMA ring"
    hardware_cmd = steps[1].get("cmd") if isinstance(steps[1], dict) else None
    if not isinstance(hardware_cmd, list) or steps[1].get("returncode") != 2:
        return "camera hardware-blocked target package hardware audit step must fail with returncode=2"
    if "--require-camera" not in hardware_cmd:
        return "camera hardware-blocked target package hardware audit must require camera enumeration"
    if command_flag_value(hardware_cmd, "--output-json") is None:
        return "camera hardware-blocked target package hardware audit must write a receipt"
    forbidden_prefixes = ("/Volumes/", "/Users/", "/opt/homebrew/")
    for step in steps:
        cmd = step.get("cmd") if isinstance(step, dict) else None
        if not isinstance(cmd, list):
            return "camera hardware-blocked target package step cmd must be a list"
        for arg in cmd:
            if isinstance(arg, str) and arg.startswith(forbidden_prefixes):
                return f"camera hardware-blocked target package contains host-local path: {arg}"
    return None


def validate_mission1_camera_hw_blocked_target_package(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"camera hardware-blocked target package JSON could not be loaded: {exc}"
    return validate_mission1_camera_hw_blocked_target_package_data(data)


def validate_mission1_camera_hw_blocked_remote_run(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"camera hardware-blocked remote run JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "camera hardware-blocked remote run must be a JSON object"
    if data.get("schema") != "gpr.mission1_remote_closure_package_run.v1":
        return "camera hardware-blocked remote run schema mismatch"
    if data.get("dry_run") is not False:
        return "camera hardware-blocked remote run must be a real non-dry run"
    if data.get("target_host") != "192.168.16.67":
        return "camera hardware-blocked remote run target_host mismatch"
    if data.get("target_role") != "camera":
        return "camera hardware-blocked remote run target_role must be camera"
    if data.get("raw_source_kind") != "sensor_dma_capture":
        return "camera hardware-blocked remote run raw_source_kind must be sensor_dma_capture"
    repo_root = data.get("remote_repo_root")
    if not isinstance(repo_root, str) or not repo_root.startswith("/mnt/ssd/"):
        return "camera hardware-blocked remote run remote_repo_root must be target-side /mnt/ssd path"
    camera_flags = data.get("camera_ready_flags")
    if not isinstance(camera_flags, dict) or not all(value is True for value in camera_flags.values()):
        return "camera hardware-blocked remote run camera_ready_flags must all be true"
    package_step = data.get("package_step")
    if not isinstance(package_step, dict) or package_step.get("returncode") != 1:
        return "camera hardware-blocked remote run package_step.returncode must be 1"
    package_cmd = package_step.get("cmd")
    package_cmd_text = " ".join(str(arg) for arg in package_cmd) if isinstance(package_cmd, list) else ""
    if "/dev/mission1/sensor_dma_ring" not in package_cmd_text:
        return "camera hardware-blocked remote run package step must target the sensor DMA ring"
    if "sensor_dma_capture" not in package_cmd_text:
        return "camera hardware-blocked remote run package step must use sensor_dma_capture"
    target_package = data.get("target_package")
    target_error = validate_mission1_camera_hw_blocked_target_package_data(target_package)
    if target_error:
        return f"camera hardware-blocked remote run target_package invalid: {target_error}"
    if data.get("collection_step") is not None:
        return "camera hardware-blocked remote run must not collect final closure receipts after failed package"
    failure_collection = data.get("failure_collection_step")
    if not isinstance(failure_collection, dict) or failure_collection.get("returncode") != 0:
        return "camera hardware-blocked remote run must collect early failure receipts"
    files = failure_collection.get("files")
    if not isinstance(files, list):
        return "camera hardware-blocked remote run failure_collection_step.files must be a list"
    by_name = {row.get("file"): row for row in files if isinstance(row, dict)}
    expected_copied = {
        "target_closure_package_run.json": True,
        "hardware_audit_receipt.json": True,
        "target_preflight_receipt.json": False,
    }
    for name, copied in expected_copied.items():
        row = by_name.get(name)
        if not isinstance(row, dict) or row.get("copied") is not copied:
            return f"camera hardware-blocked remote run expected copied={copied} for {name}"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        return "camera hardware-blocked remote run verdict must be an object"
    if verdict.get("launch_valid") is not False:
        return "camera hardware-blocked remote run must not claim launch_valid"
    if verdict.get("production_ready") is not False:
        return "camera hardware-blocked remote run must not claim production_ready"
    if verdict.get("reason") != "package_or_collection_failed":
        return "camera hardware-blocked remote run reason must be package_or_collection_failed"
    return None


def validate_mission1_camera_target_preflight(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"camera target preflight JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "camera target preflight must be a JSON object"
    if data.get("schema") != "gpr.mission1_camera_target_preflight.v1":
        return "camera target preflight schema mismatch"
    target = data.get("target")
    if not isinstance(target, dict) or target.get("role") != "camera":
        return "camera target preflight target.role must be camera"
    checks = data.get("checks")
    if not isinstance(checks, list) or not checks:
        return "camera target preflight checks must be a non-empty list"
    by_name = {row.get("name"): row for row in checks if isinstance(row, dict)}
    camera_assertions = {
        "camera frame source ready",
        "camera storage path ready",
        "camera display path ready",
    }
    sensor_ring_receipt = path.name == "preflight_192_168_16_67_camera_sensor_ring_20260625.json"
    expected_blockers = set(camera_assertions)
    if sensor_ring_receipt:
        expected_blockers.add("camera raw source endpoint is missing on target")
    blockers = data.get("blockers")
    if set(blockers or []) != expected_blockers:
        return f"camera target preflight blockers mismatch: {blockers!r}"
    for name in camera_assertions:
        row = by_name.get(name)
        if not isinstance(row, dict) or row.get("passed") is not False:
            return f"camera target preflight {name!r} check must be present and failed"
    if sensor_ring_receipt:
        raw_row = by_name.get("camera raw source endpoint exists")
        if not isinstance(raw_row, dict) or raw_row.get("passed") is not False:
            return "sensor-ring camera target preflight must fail camera raw source endpoint exists"
        raw_device_row = by_name.get("camera raw source endpoint is device-like")
        if not isinstance(raw_device_row, dict) or raw_device_row.get("passed") is not False:
            return "sensor-ring camera target preflight must fail camera raw source endpoint device check"
    non_camera_failures = [
        row.get("name")
        for row in checks
        if isinstance(row, dict)
        and row.get("name") not in expected_blockers
        and not (
            sensor_ring_receipt
            and row.get("name") in {
                "camera raw source endpoint exists",
                "camera raw source endpoint is device-like",
            }
        )
        and row.get("passed") is not True
    ]
    if non_camera_failures:
        return "camera target preflight has non-camera failures: " + ", ".join(str(name) for name in non_camera_failures)
    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        return "camera target preflight verdict must be an object"
    if verdict.get("target_preflight_ready") is not False:
        return "camera target preflight must not claim target_preflight_ready"
    if verdict.get("camera_closure_possible") is not False:
        return "camera target preflight must not claim camera_closure_possible"
    if verdict.get("remaining_blocker_count") != len(expected_blockers):
        return f"camera target preflight remaining_blocker_count must be {len(expected_blockers)}"
    if path.name in {
        "preflight_192_168_16_67_camera_sensor_ring_20260625.json",
        "preflight_fixture_camera_20260625.json",
    }:
        inputs = data.get("inputs")
        if not isinstance(inputs, dict):
            return "current camera target preflight inputs must be an object"
        if inputs.get("raw_source_kind") not in {"sensor_dma_capture", "camera_ring_buffer"}:
            return "current camera target preflight inputs.raw_source_kind must be sensor_dma_capture or camera_ring_buffer"
        for key in ("frame_source", "write_path", "storage_medium", "display_surface", "presentation_path"):
            value = inputs.get(key)
            if not isinstance(value, str) or not value.strip():
                return f"current camera target preflight inputs.{key} must be non-empty"
            lowered = value.lower()
            for token in STANDIN_TOKENS:
                if token in lowered:
                    return f"current camera target preflight inputs.{key} contains stand-in token {token!r}"
    return None


def validate_mission1_closure_plan(path: Path, manifest: dict[str, Any]) -> str | None:
    entry = mission1_closure_plan_entry(manifest)
    if not entry:
        return "manifest is missing mission1_numbered_list_closure_plan entry"
    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        return "mission1_numbered_list_closure_plan entry is missing metrics"

    try:
        expected_blockers = int(metrics["blockers"])
        expected_ready = bool(int(metrics["production_ready"]))
    except (KeyError, TypeError, ValueError):
        return "mission1_numbered_list_closure_plan metrics need numeric blockers and production_ready"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"closure plan JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "closure plan must be a JSON object"
    if data.get("schema") != "gpr.mission1_numbered_list_closure_plan.v1":
        return "closure plan schema mismatch"

    blockers = data.get("blockers")
    if not isinstance(blockers, list):
        return "closure plan blockers must be a list"
    if len(blockers) != expected_blockers:
        return f"closure plan blockers={len(blockers)} but manifest metrics expect {expected_blockers}"
    if bool(data.get("production_ready")) != expected_ready:
        return (
            f"closure plan production_ready={data.get('production_ready')!r} "
            f"but manifest metrics expect {expected_ready}"
        )
    if "--require-production" not in str(data.get("final_gate_command", "")):
        return "closure plan final_gate_command must include --require-production"

    for blocker in blockers:
        if not isinstance(blocker, dict):
            return "closure plan blocker entries must be objects"
        for key in ("item_id", "current_blocker", "required_receipt", "validator", "validation_command"):
            if not blocker.get(key):
                return f"closure plan blocker missing {key}"
        if not str(blocker["required_receipt"]).startswith("artifacts/"):
            return f"closure plan required receipt must be under artifacts/: {blocker['required_receipt']}"
        if not str(blocker["validator"]).startswith("tools/"):
            return f"closure plan validator must be a repo tool: {blocker['validator']}"
    return None


def validate_mission1_readiness(path: Path, manifest: dict[str, Any]) -> str | None:
    entry = mission1_closure_plan_entry(manifest)
    if not entry:
        return "manifest is missing mission1_numbered_list_closure_plan entry"
    metrics = entry.get("metrics")
    if not isinstance(metrics, dict):
        return "mission1_numbered_list_closure_plan entry is missing metrics"

    try:
        expected_blockers = int(metrics["blockers"])
        expected_ready = bool(int(metrics["production_ready"]))
    except (KeyError, TypeError, ValueError):
        return "mission1_numbered_list_closure_plan metrics need numeric blockers and production_ready"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"readiness JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "readiness must be a JSON object"
    if data.get("schema") != "gpr.mission1_numbered_list_readiness.v1":
        return "readiness schema mismatch"

    overall_status = data.get("overall_status")
    if not isinstance(overall_status, str) or not overall_status:
        return "readiness overall_status must be a non-empty string"
    if (overall_status == "production_ready") != expected_ready:
        return (
            f"readiness overall_status={overall_status!r} implies production_ready="
            f"{overall_status == 'production_ready'} but manifest metrics expect {expected_ready}"
        )

    items = data.get("items")
    if not isinstance(items, list) or len(items) != 4:
        return "readiness must contain exactly four numbered items"
    expected_ids = {1, 2, 3, 4}
    seen_ids: set[int] = set()
    blocker_total = 0
    ready_total = 0
    allowed_statuses = {
        "pass",
        "pass_with_handoff_gap",
        "pass_with_visual_signoff_gap",
        "pass_with_production_gap",
    }
    for item in items:
        if not isinstance(item, dict):
            return "readiness item entries must be objects"
        item_id = item.get("id")
        if not isinstance(item_id, int):
            return "readiness item id must be an integer"
        seen_ids.add(item_id)
        if item.get("status") not in allowed_statuses:
            return f"readiness item {item_id} has invalid status {item.get('status')!r}"
        if item.get("passed") is not True:
            return f"readiness item {item_id} must have passed=true for review-blocker closure tracking"
        item_ready = item.get("production_ready")
        if not isinstance(item_ready, bool):
            return f"readiness item {item_id} must include boolean production_ready"
        if item_ready != (item.get("status") == "pass" and not item.get("blockers")):
            return f"readiness item {item_id} production_ready does not match status/blockers"
        if item_ready:
            ready_total += 1
        checks = item.get("checks")
        if not isinstance(checks, list) or not checks:
            return f"readiness item {item_id} must include checks"
        blockers = item.get("blockers")
        if not isinstance(blockers, list):
            return f"readiness item {item_id} blockers must be a list"
        blocker_total += len(blockers)
    if seen_ids != expected_ids:
        return f"readiness item ids mismatch: {sorted(seen_ids)}"

    blockers = data.get("blockers")
    if not isinstance(blockers, list):
        return "readiness top-level blockers must be a list"
    if len(blockers) != blocker_total:
        return "readiness top-level blocker count must match per-item blocker count"
    if len(blockers) != expected_blockers:
        return f"readiness blockers={len(blockers)} but manifest metrics expect {expected_blockers}"
    if "production_ready_items" in metrics:
        try:
            expected_ready_items = int(metrics["production_ready_items"])
        except (TypeError, ValueError):
            return "mission1_numbered_list_closure_plan production_ready_items metric must be numeric"
        if ready_total != expected_ready_items:
            return (
                f"readiness production_ready_items={ready_total} "
                f"but manifest metrics expect {expected_ready_items}"
            )
    return None


def cross_validate_mission1_readiness_and_closure(ref: str, path: Path, manifest: dict[str, Any]) -> str | None:
    sibling_name = "readiness.json" if ref.endswith("closure_plan.json") else "closure_plan.json"
    sibling = path.with_name(sibling_name)
    if not sibling.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        other = json.loads(sibling.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"readiness/closure cross-check could not load sibling artifact: {exc}"
    if not isinstance(data, dict) or not isinstance(other, dict):
        return "readiness/closure cross-check artifacts must be JSON objects"

    if ref.endswith("closure_plan.json"):
        closure = data
        readiness = other
    else:
        readiness = data
        closure = other
    if closure.get("readiness_status") != readiness.get("overall_status"):
        return "closure readiness_status must match readiness overall_status"
    readiness_blockers = readiness.get("blockers")
    closure_blockers = closure.get("blockers")
    if not isinstance(readiness_blockers, list) or not isinstance(closure_blockers, list):
        return "readiness and closure blockers must both be lists"
    if len(readiness_blockers) != len(closure_blockers):
        return "closure blocker count must match readiness blocker count"
    return None


def validate_mission1_target_closure_collection(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"target closure collection JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "target closure collection must be a JSON object"
    if data.get("schema") != "gpr.mission1_target_closure_collection.v1":
        return "target closure collection schema mismatch"

    expected_files = {
        "target_preflight_receipt.json": "gpr.mission1_camera_target_preflight.v1",
        "labs_target_bench.json": "gpr_labs_target_bench.v1",
        "mission1_camera_closure_run.json": "gpr.mission1_camera_closure_run.v1",
        "camera_handoff_receipt.json": "gpr_labs_camera_handoff_receipt.v1",
        "preview_ui_receipt.json": "gpr_labs_preview_ui_receipt.v1",
    }
    files = data.get("files")
    if not isinstance(files, list):
        return "target closure collection files must be a list"
    by_name = {row.get("file"): row for row in files if isinstance(row, dict)}
    missing = sorted(set(expected_files) - set(by_name))
    if missing:
        return f"target closure collection missing compact files: {', '.join(missing)}"
    extra_missing = [
        name
        for name, row in by_name.items()
        if name in expected_files and row.get("exists") is not True
    ]
    if extra_missing:
        return f"target closure collection has missing compact file rows: {', '.join(sorted(extra_missing))}"
    for name, schema in expected_files.items():
        if by_name[name].get("schema") != schema:
            return f"target closure collection {name} schema mismatch"

    validation = data.get("validation")
    if not isinstance(validation, dict) or validation.get("returncode") != 0:
        return "target closure collection validation.returncode must be 0"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict) or not isinstance(verdict.get("collection_valid"), bool):
        return "target closure collection verdict.collection_valid must be boolean"
    if not isinstance(verdict.get("production_ready"), bool):
        return "target closure collection verdict.production_ready must be boolean"
    closure_verdict = data.get("closure_verdict")
    if not isinstance(closure_verdict, dict):
        return "target closure collection closure_verdict must be an object"
    for key in ("production_ready", "target_preflight_ready", "camera_closure_possible"):
        if not isinstance(closure_verdict.get(key), bool):
            return f"target closure collection closure_verdict.{key} must be boolean"
    expected_production_ready = verdict["collection_valid"] and closure_verdict["production_ready"]
    if verdict["production_ready"] != expected_production_ready:
        return (
            "target closure collection verdict.production_ready must match "
            "collection_valid and closure_verdict.production_ready"
        )

    preflight = by_name["target_preflight_receipt.json"]
    preflight_verdict = preflight.get("verdict")
    if not isinstance(preflight_verdict, dict):
        return "target closure collection preflight verdict must be an object"
    for key in ("target_preflight_ready", "camera_closure_possible"):
        if not isinstance(preflight_verdict.get(key), bool):
            return f"target closure collection preflight verdict.{key} must be boolean"
        if closure_verdict.get(key) != preflight_verdict.get(key):
            return f"target closure collection closure_verdict.{key} must match preflight verdict"
    return None


def validate_mission1_camera_source_probe(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"camera source probe JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "camera source probe must be a JSON object"
    if data.get("schema") != "gpr.mission1_camera_source_probe.v1":
        return "camera source probe schema mismatch"
    target = data.get("target")
    if not isinstance(target, dict) or target.get("role") != "camera":
        return "camera source probe target.role must be camera"
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        return "camera source probe inputs must be an object"
    if inputs.get("raw") != "/dev/mission1/sensor_dma_ring":
        return "camera source probe must target /dev/mission1/sensor_dma_ring"
    if inputs.get("raw_source_kind") != "sensor_dma_capture":
        return "camera source probe raw_source_kind must be sensor_dma_capture"
    checks = data.get("checks")
    if not isinstance(checks, list):
        return "camera source probe checks must be a list"
    by_name = {row.get("name"): row for row in checks if isinstance(row, dict)}
    for name in ("camera raw source endpoint exists", "camera raw source endpoint is device-like"):
        row = by_name.get(name)
        if not isinstance(row, dict) or row.get("passed") is not False:
            return f"current camera source probe must fail {name!r}"
    blockers = data.get("blockers")
    if blockers != ["camera raw source endpoint is missing on target"]:
        return "current camera source probe blockers must name only the missing source endpoint"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        return "camera source probe verdict must be an object"
    if verdict.get("source_ready") is not False:
        return "current camera source probe must not claim source_ready"
    if verdict.get("remaining_blocker_count") != 1:
        return "current camera source probe remaining_blocker_count must be 1"
    return None


def validate_mission1_camera_hardware_audit(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"camera hardware audit JSON could not be loaded: {exc}"
    if not isinstance(data, dict):
        return "camera hardware audit must be a JSON object"
    if data.get("schema") != "gpr.mission1_camera_hardware_audit.v1":
        return "camera hardware audit schema mismatch"
    target = data.get("target")
    if not isinstance(target, dict) or target.get("role") != "camera":
        return "camera hardware audit target.role must be camera"
    summary = data.get("summary")
    if not isinstance(summary, dict):
        return "camera hardware audit summary must be an object"
    if summary.get("camera_enumerated") is not False:
        return "current camera hardware audit must not claim camera_enumerated"
    if summary.get("rpicam_has_camera") is not False:
        return "current camera hardware audit must not claim rpicam_has_camera"
    if summary.get("libcamera_has_camera") is not False:
        return "current camera hardware audit must not claim libcamera_has_camera"
    if summary.get("sensor_like_v4l_node_count") != 0:
        return "current camera hardware audit must have zero sensor-like V4L nodes"
    tools = summary.get("tools")
    if not isinstance(tools, dict):
        return "camera hardware audit summary.tools must be an object"
    for name in ("v4l2-ctl", "media-ctl", "libcamera-hello", "rpicam-hello", "rpicam-raw"):
        if not isinstance(tools.get(name), str) or not tools.get(name):
            return f"camera hardware audit missing target tool path for {name}"
    blockers = data.get("blockers")
    if blockers != ["no camera sensor is enumerated by rpicam/libcamera/V4L"]:
        return "current camera hardware audit blockers must name only missing camera enumeration"
    verdict = data.get("verdict")
    if not isinstance(verdict, dict):
        return "camera hardware audit verdict must be an object"
    if verdict.get("hardware_ready_for_camera_source") is not False:
        return "current camera hardware audit must not claim hardware_ready_for_camera_source"
    if verdict.get("remaining_blocker_count") != 1:
        return "current camera hardware audit remaining_blocker_count must be 1"
    return None


def semantic_error(ref: str, path: Path | None, manifest: dict[str, Any]) -> str | None:
    if path is None:
        return None
    if ref == "artifacts/mission1_numbered_list_readiness_20260625/closure_plan.json":
        return validate_mission1_closure_plan(path, manifest) or cross_validate_mission1_readiness_and_closure(ref, path, manifest)
    if ref == "artifacts/mission1_numbered_list_readiness_20260625/readiness.json":
        return validate_mission1_readiness(path, manifest) or cross_validate_mission1_readiness_and_closure(ref, path, manifest)
    if ref == "artifacts/mission1_camera_closure_package_20260625/closure_package.json":
        return validate_mission1_camera_closure_package(path)
    if ref == "artifacts/mission1_4k_cleanup_visual_signoff_20260625/production_signoff.json":
        return validate_mission1_4k_cleanup_signoff(path)
    if ref == "artifacts/mission1_camera_closure_launch_20260625/mission1_camera_closure_package_dry_run.json":
        return validate_mission1_camera_closure_launch(path)
    if ref == "artifacts/mission1_camera_closure_launch_20260625/mission1_remote_closure_package_dry_run.json":
        return validate_mission1_remote_closure_launch(path)
    if ref == "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/remote_closure_summary.json":
        return validate_mission1_camera_hw_blocked_remote_run(path)
    if ref == "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/target_closure_package_run.json":
        return validate_mission1_camera_hw_blocked_target_package(path)
    if (
        ref.startswith("artifacts/mission1_camera_target_preflight_20260625/preflight_")
        and "_camera" in Path(ref).name
    ):
        return validate_mission1_camera_target_preflight(path)
    if (
        ref.startswith("artifacts/mission1_camera_target_preflight_20260625/source_probe_")
        and ref.endswith(".json")
    ):
        return validate_mission1_camera_source_probe(path)
    if (
        ref.startswith("artifacts/mission1_camera_target_discovery_20260625/hardware_audit_")
        and ref.endswith(".json")
    ) or ref == "artifacts/mission1_camera_closure_run_20260625/current_camera_hw_blocked_20260625/hardware_audit_receipt.json":
        return validate_mission1_camera_hardware_audit(path)
    if ref.endswith("/collection_receipt.json"):
        return validate_mission1_target_closure_collection(path)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit nonzero when any manifest artifact is missing or unreadable")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="emit counts and failing rows only; JSON output is unchanged",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    refs = sorted(artifact_refs(manifest))
    documented_hashes = production_artifact_hashes()
    rows: list[dict[str, Any]] = []
    production_rows: list[dict[str, Any]] = []
    failures = 0

    for ref in refs:
        candidates = candidate_paths(ref, manifest)
        resolved = next((path for path in candidates if path.exists()), None)
        status, error, size = classify(resolved)
        expected_sha = documented_hashes.get(ref)
        actual_sha = None
        if status == "ok":
            semantic = semantic_error(ref, resolved, manifest)
            if semantic:
                status = "bad_semantics"
                error = semantic
        if status == "ok" and expected_sha and resolved is not None and resolved.is_file():
            actual_sha = sha256_file(resolved)
            if actual_sha != expected_sha:
                status = "sha_mismatch"
                error = f"{PRODUCTION_ARTIFACTS} records {expected_sha}, actual {actual_sha}"
        if status != "ok":
            failures += 1
        rows.append({
            "ref": ref,
            "resolved": str(resolved) if resolved else None,
            "status": status,
            "size_bytes": size,
            "error": error,
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "searched": [str(path) for path in candidates],
        })

    for ref, expected_sha in sorted(documented_hashes.items()):
        row = verify_documented_hash_ref(ref, expected_sha, manifest)
        if row["status"] != "ok":
            failures += 1
        production_rows.append(row)

    payload = {
        "manifest": str(MANIFEST.relative_to(REPO)),
        "external_root": str(external_root(manifest)),
        "artifact_root": str(artifact_root(manifest)),
        "count": len(rows),
        "production_artifact_count": len(production_rows),
        "failures": failures,
        "artifacts": rows,
        "production_artifacts": production_rows,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.summary:
        print("=== release manifest artifact verification ===")
        print(f"manifest={payload['manifest']}")
        print(f"GPR_EXTERNAL_ROOT={payload['external_root']}")
        print(f"GPR_ARTIFACT_ROOT={payload['artifact_root']}")
        print(f"manifest_artifacts={payload['count']}")
        print(f"production_artifact_hash_rows={payload['production_artifact_count']}")
        print(f"failures={failures}")
        if failures:
            print("\n=== artifact failures ===")
            for row in rows + production_rows:
                if row["status"] == "ok":
                    continue
                loc = row["resolved"] or row["ref"]
                print(f"{row['status']:15s} {loc}")
                if row.get("error"):
                    print(f"  error: {row['error']}")
                if row.get("expected_sha256") and row.get("actual_sha256"):
                    print(f"  expected_sha256: {row['expected_sha256']}")
                    print(f"  actual_sha256:   {row['actual_sha256']}")
            print("\nUse --json for the full artifact inventory.")
    else:
        print("=== release manifest artifact verification ===")
        print(f"manifest={payload['manifest']}")
        print(f"GPR_EXTERNAL_ROOT={payload['external_root']}")
        print(f"GPR_ARTIFACT_ROOT={payload['artifact_root']}")
        for row in rows:
            loc = row["resolved"] or row["ref"]
            print(f"{row['status']:15s} {loc}")
        if production_rows:
            print("\n=== production artifact hash table verification ===")
            for row in production_rows:
                loc = row["resolved"] or row["ref"]
                print(f"{row['status']:15s} {loc}")
        if failures:
            print(f"\n{failures} manifest artifact(s) missing or unreadable")
            print("Use --strict for release gating; default mode is inventory-only.")

    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    sys.exit(main())
