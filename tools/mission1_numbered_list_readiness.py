#!/usr/bin/env python3
"""Audit the Mission 1 numbered-list production evidence.

The checker reads committed/external receipts and emits a compact JSON/Markdown
readiness report. It verifies objective evidence that can be checked without
manual visual review, while keeping production blockers explicit.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", "/Volumes/OWC_8TB/gpr_work"))
REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path(os.environ.get("GPR_REGISTRY_PATH", REPO_ROOT / "pipelines/registry.json"))
MISSION1_8K_SR_PIPELINE_ID = (
    "codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_q4t2_coord_detail_alpha0p5_v1"
    "+demosaic=sips_via_gpr_tools"
)
MISSION1_8K_SR_PRODUCTION_BLOCKER = (
    "Mission 1 8K SR registry candidate remains offline_review_only and needs production promotion evidence."
)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    evidence: str


@dataclass
class Item:
    id: int
    title: str
    status: str
    checks: list[Check] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)


def registry_pipeline(pipeline_id: str) -> dict[str, Any]:
    data = read_json(REGISTRY_PATH)
    pipelines = data.get("pipelines", {})
    if not isinstance(pipelines, dict):
        return {}
    pipeline = pipelines.get(pipeline_id, {})
    return pipeline if isinstance(pipeline, dict) else {}


def stat(values: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = values.get(key, default)
    return float(value if value is not None else default)


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64


def load_validate_receipt(script_name: str):
    path = Path(__file__).resolve().with_name(script_name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_receipt


def receipt_failures(script_name: str, data: dict[str, Any]) -> list[str]:
    return list(load_validate_receipt(script_name)(data))


def camera_handoff_is_production(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_labs_camera_handoff_receipt.py", data)
        and data.get("target", {}).get("role") == "camera"
        and data.get("verdict", {}).get("firmware_ready") is True
    )


def camera_handoff_is_blocked_stand_in(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_labs_camera_handoff_receipt.py", data)
        and data.get("target", {}).get("role") == "stand-in"
        and data.get("verdict", {}).get("firmware_ready") is False
        and bool(data.get("blocker", {}).get("cause"))
    )


def preview_ui_is_production(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_labs_preview_ui_receipt.py", data)
        and data.get("target", {}).get("role") == "camera"
        and data.get("verdict", {}).get("ui_ready") is True
    )


def preview_ui_is_blocked_stand_in(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_labs_preview_ui_receipt.py", data)
        and data.get("target", {}).get("role") == "stand-in"
        and data.get("verdict", {}).get("ui_ready") is False
        and bool(data.get("blocker", {}).get("cause"))
    )


def target_preflight_is_ready(data: dict[str, Any]) -> bool:
    return (
        data.get("schema") == "gpr.mission1_camera_target_preflight.v1"
        and data.get("verdict", {}).get("target_preflight_ready") is True
        and data.get("blockers") == []
        and all(check.get("passed") is True for check in data.get("checks", []))
    )


def target_preflight_is_production(data: dict[str, Any]) -> bool:
    return (
        target_preflight_is_ready(data)
        and data.get("target", {}).get("role") == "camera"
        and data.get("verdict", {}).get("camera_closure_possible") is True
    )


def cleanup_signoff_is_production(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_mission1_4k_cleanup_signoff_receipt.py", data)
        and data.get("verdict", {}).get("production_ready") is True
        and data.get("verdict", {}).get("accepted_role") == "production"
    )


def cleanup_signoff_is_blocked(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_mission1_4k_cleanup_signoff_receipt.py", data)
        and data.get("verdict", {}).get("production_ready") is False
        and data.get("verdict", {}).get("accepted_role") == "blocked"
        and bool(data.get("blocker", {}).get("cause"))
    )


def sr8k_promotion_is_production(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_mission1_8k_sr_production_promotion.py", data)
        and data.get("verdict", {}).get("production_ready") is True
        and data.get("verdict", {}).get("accepted_role") == "production"
    )


def sr8k_promotion_is_blocked(data: dict[str, Any]) -> bool:
    return (
        not receipt_failures("check_mission1_8k_sr_production_promotion.py", data)
        and data.get("verdict", {}).get("production_ready") is False
        and data.get("verdict", {}).get("accepted_role") == "blocked"
        and bool(data.get("blocker", {}).get("cause"))
    )


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def existing_json_paths(paths: list[Path]) -> list[Path]:
    return [path for path in paths if path.exists()]


def target_preflight_candidates(root: Path) -> list[Path]:
    return [
        root / "artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json",
        root
        / "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_camera_sensor_ring_20260625.json",
        root
        / "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_camera_codex_refresh2_20260625.json",
        root
        / "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_camera_refresh_20260625.json",
        root
        / "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_camera_latest_20260625.json",
        root
        / "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_camera_codex_followup_20260625.json",
        root
        / "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_camera_attempt_after_build_20260625.json",
        root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/target_preflight_receipt.json",
        root
        / "artifacts/mission1_camera_target_preflight_20260625/"
        "preflight_192_168_16_67_standin_after_build_20260625.json",
        root / "artifacts/mission1_camera_closure_run_20260625/current_standin/target_preflight_receipt.json",
        root / "artifacts/mission1_camera_target_preflight_20260625/preflight_192_168_16_67_standin_current_20260625.json",
    ]


def select_target_preflight(root: Path) -> tuple[Path, dict[str, Any]]:
    candidates = existing_json_paths(target_preflight_candidates(root))
    if not candidates:
        path = target_preflight_candidates(root)[0]
        return path, read_json(path)
    loaded = [(path, read_json(path)) for path in candidates]
    for path, data in loaded:
        if target_preflight_is_production(data):
            return path, data
    for path, data in loaded:
        if target_preflight_is_ready(data):
            return path, data
    return loaded[0]


def select_camera_role_target_preflight(root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    candidates = existing_json_paths(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_camera/target_preflight_receipt.json",
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "preflight_192_168_16_67_camera_sensor_ring_20260625.json",
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "preflight_192_168_16_67_camera_codex_refresh2_20260625.json",
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "preflight_192_168_16_67_camera_refresh_20260625.json",
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "preflight_192_168_16_67_camera_latest_20260625.json",
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "preflight_192_168_16_67_camera_codex_followup_20260625.json",
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "preflight_192_168_16_67_camera_attempt_after_build_20260625.json",
        ]
    )
    if not candidates:
        return None, None
    for path in candidates:
        data = read_json(path)
        if data.get("target", {}).get("role") == "camera":
            return path, data
    path = candidates[0]
    return path, read_json(path)


def select_camera_source_probe(root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    candidates = existing_json_paths(
        [
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "source_probe_192_168_16_67_camera_sensor_ring_followup_20260625.json",
            root
            / "artifacts/mission1_camera_target_preflight_20260625/"
            "source_probe_192_168_16_67_camera_sensor_ring_20260625.json",
        ]
    )
    if not candidates:
        return None, None
    path = candidates[0]
    return path, read_json(path)


def camera_role_preflight_blocked_only_by_camera_assertions(data: dict[str, Any] | None) -> bool:
    if data is None:
        return False
    camera_assertions = {
        "camera frame source ready",
        "camera storage path ready",
        "camera display path ready",
    }
    allowed_blocker_sets = {
        frozenset(camera_assertions),
        frozenset({"camera raw source endpoint is missing on target", *camera_assertions}),
    }
    blockers = set(data.get("blockers", []))
    return (
        data.get("schema") == "gpr.mission1_camera_target_preflight.v1"
        and data.get("target", {}).get("role") == "camera"
        and data.get("verdict", {}).get("target_preflight_ready") is False
        and data.get("verdict", {}).get("camera_closure_possible") is False
        and frozenset(blockers) in allowed_blocker_sets
    )


def camera_source_probe_blocked_on_missing_endpoint(data: dict[str, Any] | None) -> bool:
    if data is None:
        return False
    checks = data.get("checks")
    by_name = {row.get("name"): row for row in checks if isinstance(row, dict)} if isinstance(checks, list) else {}
    return (
        data.get("schema") == "gpr.mission1_camera_source_probe.v1"
        and data.get("target", {}).get("role") == "camera"
        and data.get("inputs", {}).get("raw") == "/dev/mission1/sensor_dma_ring"
        and data.get("inputs", {}).get("raw_source_kind") == "sensor_dma_capture"
        and by_name.get("ssh target probe", {}).get("passed") is True
        and by_name.get("camera raw source endpoint exists", {}).get("passed") is False
        and by_name.get("camera raw source endpoint is device-like", {}).get("passed") is False
        and data.get("blockers") == ["camera raw source endpoint is missing on target"]
        and data.get("verdict", {}).get("source_ready") is False
        and data.get("verdict", {}).get("remaining_blocker_count") == 1
    )


def labs_encoder_api_check() -> tuple[bool, str, str]:
    header = REPO_ROOT / "source/lib/vc5_encoder/gpr_labs_encoder.h"
    source = REPO_ROOT / "source/lib/vc5_encoder/gpr_labs_encoder.c"
    test = REPO_ROOT / "source/app/test_labs_encoder_api.c"
    bench = REPO_ROOT / "source/app/labs_encoder_bench_cli.c"
    bench_test = REPO_ROOT / "tools/test/test_labs_encoder_bench_cli.sh"
    cmake = REPO_ROOT / "CMakeLists.txt"
    ci = REPO_ROOT / ".github/workflows/ci.yml"
    sanitizer = REPO_ROOT / ".github/workflows/sanitizers.yml"
    docs = REPO_ROOT / "docs/LABS_FIRMWARE_API.md"
    required_paths = [header, source, test, bench, bench_test, cmake, ci, sanitizer, docs]
    missing = [rel(REPO_ROOT, path) for path in required_paths if not path.exists()]
    if missing:
        return False, "missing=" + ",".join(missing), rel(REPO_ROOT, header)

    text_checks = [
        (header, "gpr_labs_encoder_create"),
        (header, "gpr_labs_encoder_submit"),
        (source, "gpr_video_encoder_create"),
        (source, "gpr_video_write_clip_header"),
        (source, "gpr_video_write_frame_header"),
        (test, "gpr_video_validate_stream"),
        (test, "reject_out_of_order"),
        (bench, "gpr_labs_encoder_create"),
        (bench, "GPR_BENCH_GVID"),
        (bench_test, "run_labs_target_bench.py"),
        (cmake, "test_labs_encoder_api"),
        (cmake, "labs_encoder_bench_cli"),
        (ci, "Run test_labs_encoder_api"),
        (ci, "test_labs_encoder_bench_cli.sh"),
        (sanitizer, "Run test_labs_encoder_api"),
        (docs, "source/lib/vc5_encoder/gpr_labs_encoder.h"),
    ]
    missing_tokens = []
    for path, token in text_checks:
        if token not in path.read_text(encoding="utf-8"):
            missing_tokens.append(f"{rel(REPO_ROOT, path)}:{token}")
    if missing_tokens:
        return False, "missing_tokens=" + ",".join(missing_tokens), rel(REPO_ROOT, test)
    return (
        True,
        "gpr_labs_encoder API committed; padded-stride, sequential-tag, .gvid stream, and target-bench receipt tests covered",
        rel(REPO_ROOT, bench_test),
    )


def ffprobe_streams(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    ffprobe = receipt["ffprobe"]
    if "streams" in ffprobe:
        return ffprobe["streams"]
    if "stdout" in ffprobe:
        parsed = json.loads(ffprobe["stdout"])
        return parsed["streams"]
    raise KeyError("ffprobe streams not found")


def check_item1(root: Path) -> Item:
    receipt = root / "artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/labs_target_bench.json"
    handoff_path = root / "artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/camera_handoff_receipt.json"
    current_receipt_path = first_existing(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/labs_target_bench.json",
            root / "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/labs_target_bench.json",
        ]
    )
    current_handoff_path = first_existing(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_camera/camera_handoff_receipt.json",
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/camera_handoff_receipt.json",
            root / "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/camera_handoff_receipt.json",
        ]
    )
    closure_run_path = first_existing(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_camera/mission1_camera_closure_run.json",
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/mission1_camera_closure_run.json",
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin/mission1_camera_closure_run.json",
        ]
    )
    target_preflight_path, target_preflight = select_target_preflight(root)
    camera_preflight_path, camera_preflight = select_camera_role_target_preflight(root)
    source_probe_path, source_probe = select_camera_source_probe(root)
    pi_collection_path = root / (
        "artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/"
        "collection_receipt.json"
    )
    pi_collection_path = first_existing(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/collection_receipt.json",
            pi_collection_path,
        ]
    )
    labs_shim_receipt_path = root / (
        "artifacts/mission1_labs_shim_pi_standin_20260625/run_120f_dual/"
        "labs_target_bench.json"
    )
    data = read_json(receipt)
    handoff = read_json(handoff_path)
    current = read_json(current_receipt_path)
    current_handoff = read_json(current_handoff_path)
    closure_run = read_json(closure_run_path)
    pi_collection = read_json(pi_collection_path) if pi_collection_path.exists() else None
    labs_shim = read_json(labs_shim_receipt_path) if labs_shim_receipt_path.exists() else None
    capture = data["capture"]
    target = data["target"]
    writer = data["writer_handoff"]
    storage = data["storage"]["target"]
    handoff_verdict = handoff["verdict"]
    integration = handoff["integration"]
    sensor_dma = integration["sensor_dma_handoff"]
    storage_handoff = integration["storage_handoff"]
    output_sha = handoff["output"]["sha256"]
    handoff_ok = camera_handoff_is_blocked_stand_in(handoff) or camera_handoff_is_production(handoff)
    current_handoff_production = camera_handoff_is_production(current_handoff)
    current_handoff_ok = camera_handoff_is_blocked_stand_in(current_handoff) or current_handoff_production
    source_probe_ok = current_handoff_production or camera_source_probe_blocked_on_missing_endpoint(source_probe)
    target_preflight_ready = target_preflight_is_ready(target_preflight)
    target_preflight_production = target_preflight_is_production(target_preflight)
    closure_steps = {step.get("name"): step for step in closure_run.get("steps", [])}
    closure_handoff_step = closure_steps.get("validate_camera_handoff_receipt", {})
    closure_handoff_ok = (
        closure_run.get("schema") == "gpr.mission1_camera_closure_run.v1"
        and closure_handoff_step.get("returncode") == 0
        and closure_run.get("verdict", {}).get("firmware_ready") == current_handoff["verdict"]["firmware_ready"]
    )
    pi_collection_ok = (
        pi_collection is not None
        and pi_collection.get("schema") == "gpr.mission1_target_closure_collection.v1"
        and pi_collection.get("verdict", {}).get("collection_valid") is True
        and pi_collection.get("closure_verdict", {}).get("firmware_ready") is False
        and pi_collection.get("closure_verdict", {}).get("handoff_blocker")
        == "camera sensor/DMA and camera storage handoff not executed"
    )
    wall_fps = stat(target, "actual_wall_fps")
    loop_fps = stat(writer, "loop_fps_median")
    current_capture = current["capture"]
    current_target = current["target"]
    current_timing = current["timing"]
    current_storage = current["storage"]["target"]
    current_validation = current["gvid"]["validation"]
    current_wall_fps = stat(current_target, "actual_wall_fps")
    current_median_fps = stat(current_timing, "fps_median")
    labs_api_ok, labs_api_detail, labs_api_evidence = labs_encoder_api_check()
    item = Item(1, "RAW 4K Bayer to 4K Bayer .gvid at 20 fps+ on Pi 5", "pass_with_handoff_gap")
    item.checks.extend(
        [
            Check(
                "420 frames written",
                capture["frames_written"] == 420 and capture["dropped_frames"] == 0,
                f"frames_written={capture['frames_written']} dropped={capture['dropped_frames']}",
                rel(root, receipt),
            ),
            Check(
                "4096x3072 Bayer payload",
                capture["capture_width"] == 4096 and capture["capture_height"] == 3072,
                f"{capture['capture_width']}x{capture['capture_height']} pixel_format={capture['pixel_format']}",
                rel(root, receipt),
            ),
            Check(
                "20 fps wall target",
                wall_fps >= 20.0 and loop_fps >= 20.0,
                f"wall_fps={wall_fps:.2f} loop_fps_median={loop_fps:.2f}",
                rel(root, receipt),
            ),
            Check(
                "storage target",
                bool(storage["fits_target"]),
                f"required_write_MBps={storage['required_write_MBps']:.2f} budget_write_MBps={storage['budget_write_MBps']:.2f}",
                rel(root, receipt),
            ),
            Check(
                "firmware-facing Labs encoder shim",
                labs_api_ok,
                labs_api_detail,
                labs_api_evidence,
            ),
            Check(
                "camera handoff receipt",
                handoff_ok,
                (
                    "role={} firmware_ready={} sensor_dma={} storage_handoff={} blocker={} output_sha256={}".format(
                        handoff["target"]["role"],
                        handoff_verdict["firmware_ready"],
                        sensor_dma["executed"],
                        storage_handoff["executed"],
                        handoff.get("blocker", {}).get("cause"),
                        output_sha,
                    )
                ),
                rel(root, handoff_path),
            ),
            Check(
                "current-source Pi rerun 4K .gvid",
                current_capture["frames_written"] == 1440
                and current_capture["dropped_frames"] == 0
                and current_capture["capture_width"] == 4096
                and current_capture["capture_height"] == 3072
                and current_capture["pixel_format"] == 1
                and current_wall_fps >= 20.0
                and current_median_fps >= 20.0
                and current_validation["valid"] is True
                and current_validation["frame_count"] == 1440
                and current_storage["fits_target"] is True,
                (
                    "frames={} wall_fps={:.2f} median_fps={:.2f} payload_bytes={} required_write_MBps={:.2f}".format(
                        current_capture["frames_written"],
                        current_wall_fps,
                        current_median_fps,
                        current_validation["payload_bytes"],
                        current_storage["required_write_MBps"],
                    )
                ),
                rel(root, current_receipt_path),
            ),
            Check(
                "selected camera handoff receipt",
                current_handoff_ok,
                (
                    "role={} firmware_ready={} sensor_dma={} storage_handoff={} blocker={} output_sha256={}".format(
                        current_handoff["target"]["role"],
                        current_handoff["verdict"]["firmware_ready"],
                        current_handoff["integration"]["sensor_dma_handoff"]["executed"],
                        current_handoff["integration"]["storage_handoff"]["executed"],
                        current_handoff.get("blocker", {}).get("cause"),
                        current_handoff["output"]["sha256"],
                    )
                ),
                rel(root, current_handoff_path),
            ),
            Check(
                "selected camera closure runner handoff validation",
                closure_handoff_ok,
                "firmware_ready={} production_ready={} handoff_blocker={}".format(
                    closure_run.get("verdict", {}).get("firmware_ready"),
                    closure_run.get("verdict", {}).get("production_ready"),
                    closure_run.get("verdict", {}).get("handoff_blocker"),
                ),
                rel(root, closure_run_path),
            ),
            Check(
                "selected target preflight receipt",
                target_preflight_ready,
                "role={} target_preflight_ready={} camera_closure_possible={} blockers={}".format(
                    target_preflight.get("target", {}).get("role"),
                    target_preflight.get("verdict", {}).get("target_preflight_ready"),
                    target_preflight.get("verdict", {}).get("camera_closure_possible"),
                    ",".join(target_preflight.get("blockers", [])),
                ),
                rel(root, target_preflight_path),
            ),
        ]
    )
    if camera_preflight_path is not None:
        item.checks.append(
            Check(
                "camera-role target preflight blocker specificity",
                target_preflight_is_production(camera_preflight)
                or camera_role_preflight_blocked_only_by_camera_assertions(camera_preflight),
                "role={} target_preflight_ready={} camera_closure_possible={} blockers={}".format(
                    camera_preflight.get("target", {}).get("role"),
                    camera_preflight.get("verdict", {}).get("target_preflight_ready"),
                    camera_preflight.get("verdict", {}).get("camera_closure_possible"),
                    ",".join(camera_preflight.get("blockers", [])),
                ),
                rel(root, camera_preflight_path),
            )
        )
    if source_probe_path is not None:
        item.checks.append(
            Check(
                "camera source endpoint probe blocker specificity",
                source_probe_ok,
                "source_ready={} blockers={}".format(
                    source_probe.get("verdict", {}).get("source_ready"),
                    ",".join(source_probe.get("blockers", [])),
                ),
                rel(root, source_probe_path),
            )
        )
    if pi_collection is not None:
        item.checks.append(
            Check(
                "Pi-target aggregate closure collection handoff blocker",
                pi_collection_ok,
                "collection_valid={} firmware_ready={} handoff_blocker={}".format(
                    pi_collection.get("verdict", {}).get("collection_valid"),
                    pi_collection.get("closure_verdict", {}).get("firmware_ready"),
                    pi_collection.get("closure_verdict", {}).get("handoff_blocker"),
                ),
                rel(root, pi_collection_path),
            )
        )
    if labs_shim is not None:
        shim_target = labs_shim.get("target", {})
        shim_timing = labs_shim.get("timing", {})
        shim_storage = labs_shim.get("storage", {}).get("target", {})
        shim_gvid = labs_shim.get("gvid", {}).get("validation", {})
        shim_verdict = labs_shim.get("verdict", {})
        shim_target_fps = stat(shim_target, "fps")
        shim_wall_fps = stat(shim_target, "actual_wall_fps")
        shim_gap_ms = (
            max(0.0, 1000.0 / shim_wall_fps - 1000.0 / shim_target_fps)
            if shim_wall_fps > 0.0 and shim_target_fps > 0.0
            else 0.0
        )
        item.checks.append(
            Check(
                "Pi Labs shim target-bench receipt",
                shim_verdict.get("gvid_valid") is True
                and shim_verdict.get("no_drops") is True
                and shim_verdict.get("storage_target_met") is True
                and shim_gvid.get("frame_count") == 120,
                (
                    "functional=True wall_fps={:.2f} median_fps={:.2f} "
                    "storage_fit={} performance_gap_ms={:.2f}".format(
                        shim_wall_fps,
                        stat(shim_timing, "fps_median"),
                        shim_storage.get("fits_target"),
                        shim_gap_ms,
                    )
                ),
                rel(root, labs_shim_receipt_path),
            )
        )
    if current_handoff_production and target_preflight_production:
        item.status = "pass"
    elif current_handoff_production:
        item.blockers.append("Mission 1 camera target preflight receipt is still required.")
    else:
        item.blockers.append("Mission 1 firmware/camera-side handoff receipt is still required.")
    return item


def check_item2(root: Path) -> Item:
    receipt = root / (
        "artifacts/mission1_all42_4k_raw_pi20fps_20260624/run_420f_direct_gvid/"
        "preview_decode_ll_direct_named_1024x768_20260624/receipt.json"
    )
    current_receipt_path = first_existing(
        [
            root
            / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/"
            "preview_decode_1024x768/receipt.json",
            root
            / "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/"
            "preview_decode_1024x768/receipt.json",
        ]
    )
    preview_ui_receipt_path = first_existing(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_camera/preview_ui_receipt.json",
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/preview_ui_receipt.json",
            root / "artifacts/mission1_current_goal_sync_20260625/run_1440f_direct_gvid/preview_ui_receipt.json",
        ]
    )
    closure_run_path = first_existing(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_camera/mission1_camera_closure_run.json",
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/mission1_camera_closure_run.json",
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin/mission1_camera_closure_run.json",
        ]
    )
    target_preflight_path, target_preflight = select_target_preflight(root)
    camera_preflight_path, camera_preflight = select_camera_role_target_preflight(root)
    source_probe_path, source_probe = select_camera_source_probe(root)
    pi_collection_path = root / (
        "artifacts/mission1_camera_closure_run_20260625/pi_target_standin_20260625/"
        "collection_receipt.json"
    )
    pi_collection_path = first_existing(
        [
            root / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup/collection_receipt.json",
            pi_collection_path,
        ]
    )
    preview_ui_checker = Path(__file__).resolve().parent / "check_labs_preview_ui_receipt.py"
    data = read_json(receipt)
    current = read_json(current_receipt_path)
    preview_ui = read_json(preview_ui_receipt_path)
    closure_run = read_json(closure_run_path)
    pi_collection = read_json(pi_collection_path) if pi_collection_path.exists() else None
    summary = data["summary"]
    dims = summary["dims"]
    wall_fps = stat(summary, "actual_wall_fps_including_extract_process")
    median_fps = stat(summary["decode_plus_target"], "fps_median")
    current_summary = current["summary"]
    current_dims = current_summary["dims"]
    current_wall_fps = stat(current_summary, "actual_wall_fps_including_extract_process")
    current_median_fps = stat(current_summary["decode_plus_target"], "fps_median")
    preview_ui_production = preview_ui_is_production(preview_ui)
    preview_ui_ok = preview_ui_is_blocked_stand_in(preview_ui) or preview_ui_production
    source_probe_ok = preview_ui_production or camera_source_probe_blocked_on_missing_endpoint(source_probe)
    target_preflight_ready = target_preflight_is_ready(target_preflight)
    target_preflight_production = target_preflight_is_production(target_preflight)
    closure_steps = {step.get("name"): step for step in closure_run.get("steps", [])}
    closure_preview_step = closure_steps.get("validate_preview_ui_receipt", {})
    closure_preview_ok = (
        closure_run.get("schema") == "gpr.mission1_camera_closure_run.v1"
        and closure_preview_step.get("returncode") == 0
        and closure_run.get("verdict", {}).get("ui_ready") == preview_ui["verdict"]["ui_ready"]
    )
    pi_collection_ok = (
        pi_collection is not None
        and pi_collection.get("schema") == "gpr.mission1_target_closure_collection.v1"
        and pi_collection.get("verdict", {}).get("collection_valid") is True
        and pi_collection.get("closure_verdict", {}).get("ui_ready") is False
        and pi_collection.get("closure_verdict", {}).get("preview_blocker")
        == "Mission 1 camera UI/display path not executed"
    )
    item = Item(2, "4K Bayer .gvid to Mission screen-resolution preview at 20 fps+", "pass_with_handoff_gap")
    item.checks.extend(
        [
            Check(
                "1024x768 preview dimensions",
                dims == [[1024, 768]],
                f"dims={dims}",
                rel(root, receipt),
            ),
            Check(
                "420-frame preview run",
                data["frame_count"] == 420,
                f"frame_count={data['frame_count']}",
                rel(root, receipt),
            ),
            Check(
                "20 fps preview target",
                wall_fps >= 20.0 and median_fps >= 20.0,
                f"wall_fps={wall_fps:.2f} decode_plus_target_fps_median={median_fps:.2f}",
                rel(root, receipt),
            ),
            Check(
                "camera preview UI receipt validator",
                preview_ui_checker.exists(),
                "schema=gpr_labs_preview_ui_receipt.v1",
                rel(root, preview_ui_checker),
            ),
            Check(
                "current-source Pi rerun 1024x768 preview",
                current["frame_count"] == 1440
                and current_dims == [[1024, 768]]
                and current_wall_fps >= 20.0
                and current_median_fps >= 20.0,
                (
                    "frame_count={} wall_fps={:.2f} decode_plus_target_fps_median={:.2f}".format(
                        current["frame_count"],
                        current_wall_fps,
                        current_median_fps,
                    )
                ),
                rel(root, current_receipt_path),
            ),
            Check(
                "selected camera preview UI receipt",
                preview_ui_ok,
                (
                    "role={} ui_ready={} ui_path_executed={} blocker={}".format(
                        preview_ui["target"]["role"],
                        preview_ui["verdict"]["ui_ready"],
                        preview_ui["integration"]["ui_path_executed"],
                        preview_ui.get("blocker", {}).get("cause"),
                    )
                ),
                rel(root, preview_ui_receipt_path),
            ),
            Check(
                "selected camera closure runner preview validation",
                closure_preview_ok,
                "ui_ready={} production_ready={} preview_blocker={}".format(
                    closure_run.get("verdict", {}).get("ui_ready"),
                    closure_run.get("verdict", {}).get("production_ready"),
                    closure_run.get("verdict", {}).get("preview_blocker"),
                ),
                rel(root, closure_run_path),
            ),
            Check(
                "selected target preflight receipt",
                target_preflight_ready,
                "role={} target_preflight_ready={} camera_closure_possible={} blockers={}".format(
                    target_preflight.get("target", {}).get("role"),
                    target_preflight.get("verdict", {}).get("target_preflight_ready"),
                    target_preflight.get("verdict", {}).get("camera_closure_possible"),
                    ",".join(target_preflight.get("blockers", [])),
                ),
                rel(root, target_preflight_path),
            ),
        ]
    )
    if camera_preflight_path is not None:
        item.checks.append(
            Check(
                "camera-role target preflight blocker specificity",
                target_preflight_is_production(camera_preflight)
                or camera_role_preflight_blocked_only_by_camera_assertions(camera_preflight),
                "role={} target_preflight_ready={} camera_closure_possible={} blockers={}".format(
                    camera_preflight.get("target", {}).get("role"),
                    camera_preflight.get("verdict", {}).get("target_preflight_ready"),
                    camera_preflight.get("verdict", {}).get("camera_closure_possible"),
                    ",".join(camera_preflight.get("blockers", [])),
                ),
                rel(root, camera_preflight_path),
            )
        )
    if source_probe_path is not None:
        item.checks.append(
            Check(
                "camera source endpoint probe blocker specificity",
                source_probe_ok,
                "source_ready={} blockers={}".format(
                    source_probe.get("verdict", {}).get("source_ready"),
                    ",".join(source_probe.get("blockers", [])),
                ),
                rel(root, source_probe_path),
            )
        )
    if pi_collection is not None:
        item.checks.append(
            Check(
                "Pi-target aggregate closure collection preview blocker",
                pi_collection_ok,
                "collection_valid={} ui_ready={} preview_blocker={}".format(
                    pi_collection.get("verdict", {}).get("collection_valid"),
                    pi_collection.get("closure_verdict", {}).get("ui_ready"),
                    pi_collection.get("closure_verdict", {}).get("preview_blocker"),
                ),
                rel(root, pi_collection_path),
            )
        )
    if preview_ui_production and target_preflight_production:
        item.status = "pass"
    elif preview_ui_production:
        item.blockers.append("Mission 1 camera target preflight receipt is still required.")
    else:
        item.blockers.append("Mission 1 camera preview UI receipt is still required.")
    return item


def check_item3(root: Path) -> Item:
    base = root / "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2"
    sr_base = base / "sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600"
    rgb_summary_path = base / "mission42_rgb_cfa_target_gate_wb_review/summary.json"
    tone_path = base / "mission42_4k_cnn_tone_audit_20260625/summary.json"
    gvid4k_path = base / "mission42_4k_cnn_gvid_packaging_q8/labs_target_bench.json"
    sr8k_quality_mission_path = sr_base / "mission42_broad_fullframe/summary.json"
    sr8k_quality_z8_path = sr_base / "z8_all24_fullframe/summary.json"
    sr8k_decode_to_sr_path = sr_base / "mission42_4kcnn_gvid_to_8k_sr_full42/receipt.json"
    sr8k_path = sr_base / "mission42_4kcnn_8k_sr_gvid_packaging_q3_after_bounds_fix/receipt.json"
    sr8k_visual_review_path = root / "artifacts/mission1_8k_sr_visual_review_20260625/visual_review.json"
    sr8k_visual_review_index_path = sr8k_visual_review_path.with_name("index.html")
    sr8k_visual_review_contact_path = sr8k_visual_review_path.with_name("visual_review_contact_sheet.jpg")
    sr8k_promotion_path = first_existing(
        [
            root / "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion.json",
            root / "artifacts/mission1_8k_sr_production_promotion_20260625/production_promotion_blocked.json",
        ]
    )
    rgb_dashboard_path = rgb_summary_path.with_name("index.html")
    tone_dashboard_path = tone_path.with_name("index.html")
    visual_signoff_path = root / "artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff.json"
    visual_signoff_index_path = visual_signoff_path.with_name("index.html")
    visual_contact_path = visual_signoff_path.with_name("visual_signoff_contact_sheet.jpg")
    production_signoff_path = first_existing(
        [
            visual_signoff_path.with_name("production_signoff.json"),
            visual_signoff_path.with_name("production_signoff_blocked.json"),
        ]
    )
    production_signoff_checker = Path(__file__).resolve().parent / "check_mission1_4k_cleanup_signoff_receipt.py"

    rgb = read_json(rgb_summary_path)["summary"]
    tone = read_json(tone_path)["summary"]
    gvid4k = read_json(gvid4k_path)
    sr8k_quality_mission = read_json(sr8k_quality_mission_path)
    sr8k_quality_z8 = read_json(sr8k_quality_z8_path)
    sr8k_decode_to_sr = read_json(sr8k_decode_to_sr_path)
    sr8k = read_json(sr8k_path)
    sr8k_visual_review = read_json(sr8k_visual_review_path)
    sr8k_promotion = read_json(sr8k_promotion_path)
    visual_signoff = read_json(visual_signoff_path)
    production_signoff = read_json(production_signoff_path)
    production_signoff_ready = cleanup_signoff_is_production(production_signoff)
    production_signoff_ok = cleanup_signoff_is_blocked(production_signoff) or production_signoff_ready
    raw_guard = production_signoff.get("raw_domain_guard", {})
    raw_metrics = raw_guard.get("metrics", {}) if isinstance(raw_guard, dict) else {}
    sr8k_pipeline = registry_pipeline(MISSION1_8K_SR_PIPELINE_ID)
    sr8k_scope = sr8k_pipeline.get("production_scope")
    sr8k_promotion_ready = sr8k_promotion_is_production(sr8k_promotion)
    sr8k_promotion_ok = sr8k_promotion_is_blocked(sr8k_promotion) or sr8k_promotion_ready
    sr8k_promoted = sr8k_scope in {"offline_production", "production"} and sr8k_promotion_ready
    item = Item(3, "4K Bayer .gvid to 4K and 8K CNN Bayer outputs", "pass_with_production_gap")

    item.checks.extend(
        [
            Check(
                "4K CNN rendered RGB/CFA review metrics improve all Mission42 rows",
                rgb["rgb_rmse_improvement_pct"]["min"] > 0.0
                and rgb["cfa_raw_rmse_improvement_pct"]["min"] > 0.0
                and rgb["y_gradient_improvement_pct"]["min"] > 0.0,
                (
                    "rgb_rmse_min={:.2f}% cfa_rmse_min={:.2f}% ygrad_min={:.2f}%".format(
                        rgb["rgb_rmse_improvement_pct"]["min"],
                        rgb["cfa_raw_rmse_improvement_pct"]["min"],
                        rgb["y_gradient_improvement_pct"]["min"],
                    )
                ),
                rel(root, rgb_summary_path),
            ),
            Check(
                "4K CNN raw-domain guard receipt",
                isinstance(raw_guard.get("passed"), bool)
                and isinstance(raw_metrics.get("rmse_improvement_pct"), dict)
                and isinstance(raw_metrics.get("mae_improvement_pct"), dict)
                and isinstance(raw_metrics.get("psnr_delta_db"), dict),
                (
                    "passed={} rmse_min={} mae_min={} psnr_min={}".format(
                        raw_guard.get("passed"),
                        raw_metrics.get("rmse_improvement_pct", {}).get("min"),
                        raw_metrics.get("mae_improvement_pct", {}).get("min"),
                        raw_metrics.get("psnr_delta_db", {}).get("min"),
                    )
                ),
                rel(root, production_signoff_path),
            ),
            Check(
                "tone audit does not show green regression",
                tone["candidate_green_delta_vs_target"]["abs_p95"] <= tone["baseline_green_delta_vs_target"]["abs_p95"]
                and tone["candidate_better_display_mae_count"] > tone["candidate_worse_display_mae_count"],
                (
                    "candidate_green_abs_p95={:.4f} baseline_green_abs_p95={:.4f} better={}/{}".format(
                        tone["candidate_green_delta_vs_target"]["abs_p95"],
                        tone["baseline_green_delta_vs_target"]["abs_p95"],
                        tone["candidate_better_display_mae_count"],
                        tone["summary"]["row_count"] if "summary" in tone else tone["row_count"],
                    )
                ),
                rel(root, tone_path),
            ),
            Check(
                "4K CNN .gvid packaging",
                gvid4k["capture"]["frames_written"] == 42
                and gvid4k["gvid"]["validation"]["valid"]
                and gvid4k["gvid"]["validation"]["width"] == 4096
                and gvid4k["gvid"]["validation"]["height"] == 3072,
                (
                    "frames={} valid={} size={}x{} gvid_sha256={}".format(
                        gvid4k["capture"]["frames_written"],
                        gvid4k["gvid"]["validation"]["valid"],
                        gvid4k["gvid"]["validation"]["width"],
                        gvid4k["gvid"]["validation"]["height"],
                        gvid4k["gvid"]["sha256"],
                    )
                ),
                rel(root, gvid4k_path),
            ),
            Check(
                "4K CNN visual review package",
                rgb_dashboard_path.exists() and tone_dashboard_path.exists(),
                "rgb_dashboard={} tone_dashboard={}".format(
                    rgb_dashboard_path.exists(),
                    tone_dashboard_path.exists(),
                ),
                f"{rel(root, rgb_dashboard_path)}; {rel(root, tone_dashboard_path)}",
            ),
            Check(
                "4K CNN objective visual signoff package",
                visual_signoff["verdict"] == "objective_visual_metrics_pass_manual_signoff_required"
                and visual_signoff["production_ready"] is False
                and visual_signoff["manual_visual_signoff_required"] is True
                and all(check["passed"] for check in visual_signoff["checks"])
                and visual_contact_path.exists(),
                (
                    "verdict={} production_ready={} manual_required={} checks={}/{}".format(
                        visual_signoff["verdict"],
                        visual_signoff["production_ready"],
                        visual_signoff["manual_visual_signoff_required"],
                        sum(1 for check in visual_signoff["checks"] if check["passed"]),
                        len(visual_signoff["checks"]),
                    )
                ),
                f"{rel(root, visual_signoff_path)}; {rel(root, visual_contact_path)}",
            ),
            Check(
                "4K CNN visual signoff review page",
                visual_signoff_index_path.exists()
                and "Production Signoff Commands" in visual_signoff_index_path.read_text(encoding="utf-8")
                and "build_mission1_4k_cleanup_signoff_receipt.py" in visual_signoff_index_path.read_text(encoding="utf-8")
                and "check_mission1_4k_cleanup_signoff_receipt.py" in visual_signoff_index_path.read_text(encoding="utf-8"),
                "contains production and blocked receipt commands",
                rel(root, visual_signoff_index_path),
            ),
            Check(
                "4K CNN production signoff receipt validator",
                production_signoff_checker.exists(),
                "schema=gpr.mission1_4k_cleanup_production_signoff.v1",
                rel(root, production_signoff_checker),
            ),
            Check(
                "4K CNN production signoff receipt",
                production_signoff_ok,
                (
                    "production_ready={} accepted_role={} raw_guard_passed={} blocker={}".format(
                        production_signoff["verdict"]["production_ready"],
                        production_signoff["verdict"]["accepted_role"],
                        raw_guard.get("passed"),
                        production_signoff.get("blocker", {}).get("cause"),
                    )
                ),
                rel(root, production_signoff_path),
            ),
            Check(
                "8K SR .gvid packaging",
                sr8k["gvid_header"]["width"] == 8192
                and sr8k["gvid_header"]["height"] == 6144
                and sr8k["gvid_header"]["frame_count"] == 42
                and all(row["matches_source"] for row in sr8k["gvid_payload_checks"])
                and all(row["returncode"] == 0 for row in sr8k["gvid_decode_validation"]),
                (
                    "frames={} size={}x{} payload_checks={} decode_checks={}".format(
                        sr8k["gvid_header"]["frame_count"],
                        sr8k["gvid_header"]["width"],
                        sr8k["gvid_header"]["height"],
                        len(sr8k["gvid_payload_checks"]),
                        len(sr8k["gvid_decode_validation"]),
                    )
                ),
                rel(root, sr8k_path),
            ),
            Check(
                "8K SR broad quality gates",
                sr8k_quality_mission["image_count"] == 42
                and sr8k_quality_z8["image_count"] == 24
                and sr8k_quality_mission["rmse_improvement_pct"]["min"] > 0.0
                and sr8k_quality_mission["mae_improvement_pct"]["min"] > 0.0
                and sr8k_quality_mission["gradient_mae_improvement_pct"]["min"] > 0.0
                and sr8k_quality_z8["rmse_improvement_pct"]["min"] > 0.0
                and sr8k_quality_z8["mae_improvement_pct"]["min"] > 0.0
                and sr8k_quality_z8["gradient_mae_improvement_pct"]["min"] > 0.0,
                (
                    "mission42 rmse_min={:.2f}% mae_min={:.2f}% ygrad_min={:.2f}%; "
                    "z8 rmse_min={:.2f}% mae_min={:.2f}% ygrad_min={:.2f}%".format(
                        sr8k_quality_mission["rmse_improvement_pct"]["min"],
                        sr8k_quality_mission["mae_improvement_pct"]["min"],
                        sr8k_quality_mission["gradient_mae_improvement_pct"]["min"],
                        sr8k_quality_z8["rmse_improvement_pct"]["min"],
                        sr8k_quality_z8["mae_improvement_pct"]["min"],
                        sr8k_quality_z8["gradient_mae_improvement_pct"]["min"],
                    )
                ),
                f"{rel(root, sr8k_quality_mission_path)}; {rel(root, sr8k_quality_z8_path)}",
            ),
            Check(
                "8K SR visual review package",
                sr8k_visual_review["schema"] == "gpr.mission1_8k_sr_visual_review.v1"
                and sr8k_visual_review["verdict"] == "objective_visual_metrics_pass_manual_review_required"
                and sr8k_visual_review["production_ready"] is False
                and sr8k_visual_review["manual_visual_review_required"] is True
                and all(check["passed"] for check in sr8k_visual_review["checks"])
                and sr8k_visual_review_index_path.exists()
                and sr8k_visual_review_contact_path.exists(),
                (
                    "verdict={} production_ready={} manual_required={} checks={}/{}".format(
                        sr8k_visual_review["verdict"],
                        sr8k_visual_review["production_ready"],
                        sr8k_visual_review["manual_visual_review_required"],
                        sum(1 for check in sr8k_visual_review["checks"] if check["passed"]),
                        len(sr8k_visual_review["checks"]),
                    )
                ),
                (
                    f"{rel(root, sr8k_visual_review_path)}; "
                    f"{rel(root, sr8k_visual_review_index_path)}; "
                    f"{rel(root, sr8k_visual_review_contact_path)}"
                ),
            ),
            Check(
                "8K SR offline render timing receipt",
                sr8k_decode_to_sr["frames_rendered"] == 42
                and sr8k_decode_to_sr["summary"]["fps_median_decode_plus_sr"] > 0.0
                and sr8k_decode_to_sr["max_rss_mb"] > 0.0,
                (
                    "frames={} decode_plus_sr_fps_median={:.2f} max_rss_mb={:.1f}".format(
                        sr8k_decode_to_sr["frames_rendered"],
                        sr8k_decode_to_sr["summary"]["fps_median_decode_plus_sr"],
                        sr8k_decode_to_sr["max_rss_mb"],
                    )
                ),
                rel(root, sr8k_decode_to_sr_path),
            ),
            Check(
                "8K SR registry production boundary",
                bool(sr8k_pipeline)
                and sr8k_scope in {"offline_review_only", "offline_production", "production"},
                f"pipeline={MISSION1_8K_SR_PIPELINE_ID} production_scope={sr8k_scope}",
                rel(root, REGISTRY_PATH),
            ),
            Check(
                "8K SR production-promotion receipt",
                sr8k_promotion_ok,
                "production_ready={} accepted_role={} blocking_issues={}".format(
                    sr8k_promotion["verdict"]["production_ready"],
                    sr8k_promotion["verdict"]["accepted_role"],
                    ",".join(sr8k_promotion["verdict"]["blocking_issues"]),
                ),
                rel(root, sr8k_promotion_path),
            ),
        ]
    )
    if not production_signoff_ready:
        cause = production_signoff.get("blocker", {}).get("cause") or "unknown"
        item.blockers.append(f"Mission 1 4K cleanup production signoff is blocked by {cause}.")
    if not sr8k_promoted:
        item.blockers.append(MISSION1_8K_SR_PRODUCTION_BLOCKER)
    if not item.blockers:
        item.status = "pass"
    return item


def check_item4(root: Path) -> Item:
    base = root / "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2"
    prores4k_path = base / "mission42_4k_cnn_prores_review/receipt.json"
    prores8k_path = base / (
        "sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/"
        "mission42_4kcnn_8k_sr_gvid_to_prores_42f_after_bounds_fix/receipt.json"
    )
    prores4k = read_json(prores4k_path)
    prores8k = read_json(prores8k_path)
    stream4k = ffprobe_streams(prores4k)[0]
    stream8k = ffprobe_streams(prores8k)[0]
    item = Item(4, "4K and 8K Bayer .gvid to ProRes", "pass")
    item.checks.extend(
        [
            Check(
                "4K ProRes review",
                stream4k["codec_name"] == "prores"
                and stream4k["width"] == 4096
                and stream4k["height"] == 3072
                and stream4k["nb_frames"] == "42",
                f"{stream4k['codec_name']} {stream4k['width']}x{stream4k['height']} frames={stream4k['nb_frames']}",
                rel(root, prores4k_path),
            ),
            Check(
                "8K ProRes review",
                stream8k["codec_name"] == "prores"
                and stream8k["width"] == 8192
                and stream8k["height"] == 6144
                and stream8k["nb_frames"] == "42",
                f"{stream8k['codec_name']} {stream8k['width']}x{stream8k['height']} frames={stream8k['nb_frames']}",
                rel(root, prores8k_path),
            ),
        ]
    )
    return item


def item_to_json(item: Item) -> dict[str, Any]:
    checks_passed = all(check.passed for check in item.checks)
    return {
        "id": item.id,
        "title": item.title,
        "status": item.status,
        "checks": [check.__dict__ for check in item.checks],
        "blockers": item.blockers,
        "passed": checks_passed,
        "production_ready": checks_passed and item.status == "pass" and not item.blockers,
    }


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Mission 1 Numbered-List Readiness Audit",
        "",
        f"External root: `{payload['external_root']}`",
        f"Overall status: `{payload['overall_status']}`",
        "",
    ]
    for item in payload["items"]:
        lines.extend(
            [
                f"## {item['id']}. {item['title']}",
                "",
                f"Status: `{item['status']}`",
                f"Production ready: `{item['production_ready']}`",
                "",
            ]
        )
        lines.extend(["| check | result | detail | evidence |", "|---|---:|---|---|"])
        for check in item["checks"]:
            result = "PASS" if check["passed"] else "FAIL"
            lines.append(
                f"| {check['name']} | {result} | {check['detail']} | `{check['evidence']}` |"
            )
        if item["blockers"]:
            lines.extend(["", "Blockers:"])
            for blocker in item["blockers"]:
                lines.append(f"- {blocker}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_report(root: Path) -> dict[str, Any]:
    items = [check_item1(root), check_item2(root), check_item3(root), check_item4(root)]
    hard_checks_pass = all(all(check.passed for check in item.checks) for item in items)
    blockers = [blocker for item in items for blocker in item.blockers]
    if not hard_checks_pass:
        overall = "evidence_failed"
    elif blockers:
        overall = "evidence_passes_with_production_blockers"
    else:
        overall = "production_ready"
    return {
        "schema": "gpr.mission1_numbered_list_readiness.v1",
        "external_root": str(root),
        "overall_status": overall,
        "items": [item_to_json(item) for item in items],
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--require-production", action="store_true")
    args = parser.parse_args()

    report = build_report(args.external_root)
    print(json.dumps(report, indent=2))

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = args.output_dir / "readiness.json"
        md_path = args.output_dir / "readiness.md"
        json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        write_markdown(md_path, report)
        print(f"wrote {json_path}")
        print(f"wrote {md_path}")

    if report["overall_status"] == "evidence_failed":
        return 1
    if args.require_production and report["overall_status"] != "production_ready":
        print(
            f"Production promotion blocked: overall_status={report['overall_status']}",
            file=sys.stderr,
        )
        for blocker in report["blockers"]:
            print(f"- {blocker}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
