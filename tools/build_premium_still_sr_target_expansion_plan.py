#!/usr/bin/env python3
"""Build the next premium still-SR target expansion plan.

This is the bridge between the blocker audit and the next expensive CNN run.
It consumes the routed fixture manifest plus current HF target receipts and
emits a concrete, reproducible scene list for the next raw-domain/noise-aware
still-SR target build.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_target_expansion_plan.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_FIXTURE_MANIFEST = "artifacts/premium_still_sr_fixture_manifest_routed_20260630/fixture_manifest.json"
DEFAULT_MERGED_TARGET = "artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630/merged/merge_receipt.json"
DEFAULT_BLOCKER_AUDIT = "artifacts/premium_still_sr_blocker_audit_20260630/blocker_audit.json"
ROWS_PER_SCENE = 27
DEFAULT_Z8_SCENES = 4


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def resolve(root: Path, path: Path | str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else root / p


def nested(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return default if cur is None else cur


def int_nested(data: dict[str, Any], keys: list[str], default: int) -> int:
    value = nested(data, keys)
    return int(value) if isinstance(value, int) else default


def target_scenes(merged_target: dict[str, Any]) -> list[str]:
    scenes = nested(merged_target, ["summary", "scenes"], [])
    return [str(scene) for scene in scenes] if isinstance(scenes, list) else []


def current_scene_tokens(scenes: list[str]) -> set[str]:
    tokens: set[str] = set()
    for scene in scenes:
        lower = scene.lower()
        tokens.add(lower)
        for number in re.findall(r"\d{3,5}", lower):
            tokens.add(number)
    return tokens


def fixture_route(fixture: dict[str, Any]) -> str:
    return f"{fixture.get('camera_key', 'unknown')}:{fixture.get('class', 'unknown')}:{fixture.get('extension', 'unknown')}"


def fixture_scene_id(fixture: dict[str, Any]) -> str:
    source = fixture.get("source") if isinstance(fixture.get("source"), dict) else {}
    stem = Path(str(source.get("path") or fixture.get("label") or "unknown")).stem
    return stem.lower()


def read_source_iso(path: str | None) -> int | None:
    if not path:
        return None
    try:
        rows = json.loads(subprocess.check_output(["exiftool", "-j", "-n", "-ISO", path], text=True, stderr=subprocess.DEVNULL))
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return None
    if not rows or not isinstance(rows[0], dict):
        return None
    values = re.findall(r"\d+", str(rows[0].get("ISO", "")))
    return int(values[0]) if values else None


def sidecar_iso(path: str | None) -> int | None:
    if not path:
        return None
    match = re.search(r"ISO(\d+)", path, re.I)
    return int(match.group(1)) if match else None


def select_noise_sidecars(noise_sidecars: list[dict[str, Any]], source_iso: int | None) -> list[dict[str, Any]]:
    if not noise_sidecars:
        return []
    if source_iso is None:
        return [noise_sidecars[0]]

    def distance(sidecar: dict[str, Any]) -> tuple[float, str]:
        iso = sidecar_iso(str(sidecar.get("path") or ""))
        if iso is None or iso <= 0:
            return (999.0, str(sidecar.get("path") or ""))
        return (abs(math.log2(max(iso, 1) / max(source_iso, 1))), str(sidecar.get("path") or ""))

    return [min(noise_sidecars, key=distance)]


def is_existing_target(fixture: dict[str, Any], tokens: set[str]) -> bool:
    haystack = " ".join(
        [
            str(fixture.get("label") or "").lower(),
            fixture_scene_id(fixture),
            str(nested(fixture, ["source", "path"], "")).lower(),
        ]
    )
    return any(token and token in haystack for token in tokens)


def eligible_fixtures(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for fixture in manifest.get("fixtures", []):
        if not isinstance(fixture, dict):
            continue
        if fixture.get("premium_still_sr_eligible") is not True:
            continue
        if nested(fixture, ["source", "exists"]) is not True:
            continue
        rows.append(fixture)
    return rows


def has_noise(fixture: dict[str, Any]) -> bool:
    sidecars = fixture.get("noise_sidecars")
    return isinstance(sidecars, list) and bool(sidecars)


def sample_evenly(fixtures: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0 or not fixtures:
        return []
    if len(fixtures) <= count:
        return fixtures
    if count == 1:
        return [fixtures[0]]
    chosen = []
    seen: set[int] = set()
    for idx in [round(i * (len(fixtures) - 1) / (count - 1)) for i in range(count)]:
        if idx not in seen:
            chosen.append(fixtures[idx])
            seen.add(idx)
    return chosen


def fixture_ref(fixture: dict[str, Any], *, reason: str) -> dict[str, Any]:
    source = fixture.get("source") if isinstance(fixture.get("source"), dict) else {}
    sidecars = fixture.get("noise_sidecars", [])
    noise_sidecars = [
        {
            "path": nested(sidecar, ["path"], sidecar.get("resolved_path") if isinstance(sidecar, dict) else None),
            "sha256": sidecar.get("sha256") if isinstance(sidecar, dict) else None,
        }
        for sidecar in sidecars
        if isinstance(sidecar, dict)
    ]
    source_iso = read_source_iso(str(source.get("path") or ""))
    selected_noise_sidecars = select_noise_sidecars(noise_sidecars, source_iso)
    return {
        "label": fixture.get("label"),
        "scene_id": fixture_scene_id(fixture),
        "camera": fixture.get("camera"),
        "camera_key": fixture.get("camera_key"),
        "class": fixture.get("class"),
        "route": fixture_route(fixture),
        "extension": fixture.get("extension"),
        "width": fixture.get("width"),
        "height": fixture.get("height"),
        "source_path": source.get("path"),
        "source_sha256": source.get("sha256"),
        "source_iso": source_iso,
        "noise_sidecar_count": len(noise_sidecars),
        "noise_sidecars": noise_sidecars,
        "selected_noise_sidecars": selected_noise_sidecars,
        "reason": reason,
    }


def summarize_pool(fixtures: list[dict[str, Any]], existing_tokens: set[str]) -> list[dict[str, Any]]:
    routes = sorted({fixture_route(f) for f in fixtures})
    rows = []
    for route in routes:
        group = [f for f in fixtures if fixture_route(f) == route]
        rows.append(
            {
                "route": route,
                "fixture_count": len(group),
                "with_noise_sidecars": sum(1 for f in group if has_noise(f)),
                "already_targeted_estimate": sum(1 for f in group if is_existing_target(f, existing_tokens)),
                "examples": [str(f.get("label")) for f in group[:6]],
            }
        )
    return rows


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = args.external_root
    manifest_path = resolve(root, args.fixture_manifest)
    merged_target_path = resolve(root, args.merged_target)
    blocker_path = resolve(root, args.blocker_audit)
    manifest = load_json(manifest_path)
    merged_target = load_json(merged_target_path)
    blocker = load_json(blocker_path)

    scenes = target_scenes(merged_target)
    existing_tokens = current_scene_tokens(scenes)
    fixtures = eligible_fixtures(manifest)
    x2d = sorted([f for f in fixtures if fixture_route(f) == "x2d:100mp:dng"], key=lambda f: str(f.get("label")))
    z8 = sorted([f for f in fixtures if fixture_route(f) == "z8:50mp:dng"], key=lambda f: str(f.get("label")))
    mission = sorted([f for f in fixtures if str(f.get("camera_key")) == "mission1"], key=lambda f: str(f.get("label")))

    new_x2d = [f for f in x2d if not is_existing_target(f, existing_tokens)]
    z8_with_noise = [f for f in z8 if has_noise(f)]
    mission_without_noise = [f for f in mission if not has_noise(f)]

    acceptance = nested(blocker, ["recommended_next_experiment", "minimum_acceptance"], {})
    min_rows = int(nested(acceptance, ["minimum_target_rows"], args.minimum_rows))
    min_scenes = int(nested(acceptance, ["minimum_target_scenes"], args.minimum_scenes))
    current_rows = int_nested(merged_target, ["summary", "row_count"], 0)
    current_scene_count = int_nested(merged_target, ["summary", "scene_count"], len(scenes))
    scenes_needed_for_rows = max(0, math.ceil((min_rows - current_rows) / ROWS_PER_SCENE))
    scenes_needed_for_count = max(0, min_scenes - current_scene_count)
    minimum_new_scene_count = max(scenes_needed_for_rows, scenes_needed_for_count)

    selected_x2d = new_x2d
    selected_z8 = sample_evenly(z8_with_noise, args.z8_scenes)
    selected = selected_x2d + selected_z8
    planned_total_scenes = current_scene_count + len(selected)
    planned_total_rows = current_rows + len(selected) * ROWS_PER_SCENE
    meets_minimum = planned_total_scenes >= min_scenes and planned_total_rows >= min_rows and len(selected) >= minimum_new_scene_count

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": root.as_posix(),
        "sources": {
            "fixture_manifest": manifest_path.as_posix(),
            "merged_target": merged_target_path.as_posix(),
            "blocker_audit": blocker_path.as_posix(),
        },
        "policy": {
            "rows_per_scene": ROWS_PER_SCENE,
            "mission1_policy": "defer_until_validated_same_camera_noise_sidecars_exist",
            "z8_selection": f"evenly sample {args.z8_scenes} Z8 scenes with validated noise sidecars",
            "x2d_selection": "add all X2D 100MP fixtures not already represented in the current HF target scene tokens",
            "render_time_inputs": "candidate render/raw metadata, camera/ISO noise sidecars, deterministic CFA coordinates; no source HF at runtime",
        },
        "current_target": {
            "scene_count": current_scene_count,
            "row_count": current_rows,
            "scenes": scenes,
        },
        "acceptance": {
            "minimum_target_rows": min_rows,
            "minimum_target_scenes": min_scenes,
            "minimum_new_scene_count": minimum_new_scene_count,
            "promotion_recovery_pct": nested(acceptance, ["holdout_recovery_mae_pct"], 15.0),
            "full_still_editor_latitude_gate": bool(nested(acceptance, ["full_still_editor_latitude_gate"], True)),
        },
        "fixture_pool": summarize_pool(fixtures, existing_tokens),
        "selected_new_targets": [fixture_ref(f, reason="x2d_100mp_noise_sidecar_covered_not_in_current_target") for f in selected_x2d]
        + [fixture_ref(f, reason="z8_50mp_noise_sidecar_covered_balanced_holdout_coverage") for f in selected_z8],
        "deferred_targets": [fixture_ref(f, reason="mission1_missing_validated_noise_sidecar") for f in mission_without_noise[:12]],
        "deferred_target_count": len(mission_without_noise),
        "planned_target": {
            "new_scene_count": len(selected),
            "new_rows": len(selected) * ROWS_PER_SCENE,
            "total_scene_count": planned_total_scenes,
            "total_rows": planned_total_rows,
            "has_100mp_x2d": bool(selected_x2d or x2d),
            "has_50mp_z8": bool(selected_z8),
            "has_noise_sidecar_for_every_selected_scene": all(has_noise(f) for f in selected),
            "meets_minimum_target_coverage": meets_minimum,
        },
        "commands": [
            {
                "step": "build_degraded_candidate_raw_per_selected_scene",
                "command_template": "python3 tools/cnn/build_premium_still_sr_degraded_candidate_raw.py --source-dng <selected source_path> --output-raw /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/candidate_raws/<scene_id>_box2_candidate.raw",
            },
            {
                "step": "build_hf_targets_per_selected_scene",
                "command_template": "python3 tools/cnn/build_premium_still_sr_hf_residual_targets.py --source-dng <selected source_path> --candidate-raw /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/candidate_raws/<scene_id>_box2_candidate.raw --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/<scene_id> --noise-sidecar <best camera/ISO noise sidecar> --crop-size 768 --crop-grid 3 --block 16 --output-bps 16",
            },
            {
                "step": "merge_targets",
                "command_template": "python3 tools/cnn/merge_premium_still_sr_hf_residual_targets.py --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/merged <all hf_residual_targets.npz>",
            },
            {
                "step": "train_next_model",
                "command_template": "python3 tools/cnn/train_premium_still_sr_hf_residual.py --targets /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_hf_targets_20260630/merged/hf_residual_targets_merged.npz --feature-mode rgb_multiscale_coord_luma_ev_noise_bright --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_expanded_render_context_model_20260630",
            },
        ],
        "production_ready": False,
        "next_gate": "train expanded target candidate, then run full 50MP/100MP still/editor-latitude promotion gate",
    }


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_html(plan: dict[str, Any]) -> str:
    cards = "".join(
        f"<div class='card'><span>{html.escape(key)}</span><strong>{html.escape(fmt(value))}</strong></div>"
        for key, value in plan["planned_target"].items()
    )
    selected_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['label']))}</td>"
        f"<td>{html.escape(str(row['route']))}</td>"
        f"<td>{html.escape(str(row['scene_id']))}</td>"
        f"<td>{html.escape(str(row.get('source_iso')))}</td>"
        f"<td>{html.escape(str(row['noise_sidecar_count']))}</td>"
        f"<td>{html.escape(', '.join(str(s.get('path')) for s in row.get('selected_noise_sidecars', [])))}</td>"
        f"<td>{html.escape(str(row['reason']))}</td>"
        "</tr>"
        for row in plan["selected_new_targets"]
    )
    pool_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['route']))}</td>"
        f"<td>{row['fixture_count']}</td>"
        f"<td>{row['with_noise_sidecars']}</td>"
        f"<td>{row['already_targeted_estimate']}</td>"
        f"<td>{html.escape(', '.join(row['examples']))}</td>"
        "</tr>"
        for row in plan["fixture_pool"]
    )
    commands = "".join(
        f"<li><strong>{html.escape(cmd['step'])}</strong><br><code>{html.escape(cmd['command_template'])}</code></li>"
        for cmd in plan["commands"]
    )
    current = plan["current_target"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Premium Still-SR Target Expansion Plan</title>
  <style>
    body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #12171c; background: #f5f7f8; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0 0 6px; font-size: 34px; letter-spacing: 0; }}
    h2 {{ margin: 22px 0 8px; }}
    table {{ border-collapse: collapse; width: 100%; background: white; }}
    th, td {{ border-bottom: 1px solid #dce2e7; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #edf1f4; }}
    code {{ white-space: normal; background: #eef2f5; padding: 2px 4px; border-radius: 4px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 18px 0; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 12px; }}
    .card span {{ display: block; color: #5d6873; font-size: 12px; }}
    .card strong {{ display: block; font-size: 22px; margin-top: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Premium Still-SR Target Expansion Plan</h1>
  <p>Current target: {current['scene_count']} scenes / {current['row_count']} rows. This plan expands coverage before another expensive no-REF CNN pass.</p>
  <section class="cards">{cards}</section>
  <h2>Selected New Target Scenes</h2>
  <table><thead><tr><th>Label</th><th>Route</th><th>Scene</th><th>ISO</th><th>Noise Sidecars</th><th>Selected Sidecar</th><th>Reason</th></tr></thead><tbody>{selected_rows}</tbody></table>
  <h2>Fixture Pool</h2>
  <table><thead><tr><th>Route</th><th>Fixtures</th><th>With Noise</th><th>Already Targeted Estimate</th><th>Examples</th></tr></thead><tbody>{pool_rows}</tbody></table>
  <h2>Build Commands</h2>
  <ol>{commands}</ol>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--fixture-manifest", type=Path, default=Path(DEFAULT_FIXTURE_MANIFEST))
    ap.add_argument("--merged-target", type=Path, default=Path(DEFAULT_MERGED_TARGET))
    ap.add_argument("--blocker-audit", type=Path, default=Path(DEFAULT_BLOCKER_AUDIT))
    ap.add_argument("--minimum-rows", type=int, default=256)
    ap.add_argument("--minimum-scenes", type=int, default=6)
    ap.add_argument("--z8-scenes", type=int, default=DEFAULT_Z8_SCENES)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    plan = build_plan(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.output_dir / "target_expansion_plan.json"
    out_html = args.output_dir / "index.html"
    out_json.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(plan), encoding="utf-8")
    print(out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
