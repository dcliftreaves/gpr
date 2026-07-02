#!/usr/bin/env python3
"""Audit premium still-SR raw-editor/openability coverage by production route."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_editor_latitude_coverage.v1"
EDITOR_SCHEMA = "gpr.premium_still_sr_editor_receipt.v1"
LATITUDE_SCHEMA = "gpr.premium_still_sr_latitude_review.v1"
DEFAULT_REQUIRED_ROUTES = (
    "mission1:50mp:dng",
    "mission1:50mp:gpr",
    "z8:50mp:dng",
    "x2d:100mp:dng",
)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def parse_mapping(values: list[str]) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"expected route=path, got {value!r}")
        route, path = value.split("=", 1)
        route = route.strip()
        if not route:
            raise SystemExit(f"empty route in {value!r}")
        out[route] = Path(path)
    return out


def artifact_ref(path: Path | None, root: Path) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "bytes": None, "sha256": None}
    try:
        rel = "artifacts/" + path.resolve().relative_to((root / "artifacts").resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    return {
        "path": rel,
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path),
    }


def resolve_ref_path(value: str | None, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    if value.startswith("artifacts/"):
        return root / value
    return path


def editor_status(route: str, path: Path | None, root: Path) -> dict[str, Any]:
    status: dict[str, Any] = {
        "route": route,
        "provided": path is not None,
        "receipt": artifact_ref(path, root),
        "schema_ok": False,
        "route_matches": False,
        "openability_pass": False,
        "metadata_transplant_pass": False,
        "raw_editor_latitude_claimed": False,
        "ready": False,
        "blockers": [],
    }
    blockers: list[str] = status["blockers"]
    if path is None:
        blockers.append("editor/openability receipt is missing")
        return status
    if not path.is_file():
        blockers.append("editor/openability receipt path does not exist")
        return status
    data = load_json(path)
    status["schema"] = data.get("schema")
    status["schema_ok"] = data.get("schema") == EDITOR_SCHEMA
    status["route_in_receipt"] = data.get("route")
    status["route_matches"] = data.get("route") == route
    status["camera"] = data.get("camera")
    status["source_frame"] = data.get("source_frame")
    status["production_ready"] = data.get("production_ready") is True
    status["openability_pass"] = data.get("openability_pass") is True
    metadata = data.get("metadata_transplant", {})
    status["metadata_transplant_pass"] = isinstance(metadata, dict) and metadata.get("passed") is True
    status["raw_editor_latitude_claimed"] = "receipt proves openability/export, not full raw-editor latitude" not in data.get(
        "blockers", []
    )
    artifacts = data.get("artifacts", {}) if isinstance(data.get("artifacts"), dict) else {}
    editable_dng_path = resolve_ref_path(
        artifacts.get("editable_dng", {}).get("path") if isinstance(artifacts.get("editable_dng"), dict) else None,
        root,
    )
    editable_gpr_path = resolve_ref_path(
        artifacts.get("editable_gpr", {}).get("path") if isinstance(artifacts.get("editable_gpr"), dict) else None,
        root,
    )
    status["editable_dng"] = artifact_ref(editable_dng_path, root)
    status["editable_gpr"] = artifact_ref(editable_gpr_path, root)
    if not status["schema_ok"]:
        blockers.append(f"editor/openability schema is not {EDITOR_SCHEMA}")
    if not status["route_matches"]:
        blockers.append("editor/openability route does not match required route")
    if not status["openability_pass"]:
        blockers.append("editable DNG/GPR openability did not pass")
    if not status["metadata_transplant_pass"]:
        blockers.append("source-camera metadata transplant is not proven")
    if not status["editable_dng"]["exists"]:
        blockers.append("editable DNG artifact is missing")
    if not status["editable_gpr"]["exists"]:
        blockers.append("editable GPR artifact is missing")
    status["ready"] = not blockers
    return status


def latitude_status(route: str, path: Path | None, root: Path, min_rows: int) -> dict[str, Any]:
    status: dict[str, Any] = {
        "route": route,
        "provided": path is not None,
        "receipt": artifact_ref(path, root),
        "schema_ok": False,
        "engine_ok": False,
        "row_count_ok": False,
        "no_source_hf_oracle": False,
        "source_dng": artifact_ref(None, root),
        "candidate_dng": artifact_ref(None, root),
        "ready": False,
        "blockers": [],
    }
    blockers: list[str] = status["blockers"]
    if path is None:
        blockers.append("raw-editor latitude review is missing")
        return status
    if not path.is_file():
        blockers.append("raw-editor latitude review path does not exist")
        return status
    data = load_json(path)
    status["schema"] = data.get("schema")
    status["schema_ok"] = data.get("schema") == LATITUDE_SCHEMA
    render = data.get("render", {}) if isinstance(data.get("render"), dict) else {}
    summary = data.get("summary", {}) if isinstance(data.get("summary"), dict) else {}
    row_count = summary.get("row_count")
    status["row_count"] = row_count
    status["row_count_ok"] = isinstance(row_count, int) and row_count >= min_rows
    status["engine"] = render.get("engine")
    status["engine_ok"] = render.get("engine") == "rawpy/libraw"
    status["use_camera_wb"] = render.get("use_camera_wb") is True
    status["oracle_hf_addback"] = render.get("oracle_hf_addback") is True
    status["no_source_hf_oracle"] = render.get("oracle_hf_addback") is not True
    status["candidate_dng_sha256"] = data.get("candidate_dng_sha256")
    status["source_dng_sha256"] = data.get("source_dng_sha256")
    status["source_dng"] = artifact_ref(resolve_ref_path(data.get("source_dng"), root), root)
    status["candidate_dng"] = artifact_ref(resolve_ref_path(data.get("candidate_dng"), root), root)
    metrics = {}
    for key in ("mae", "y_mae", "lf_y_mae", "hf_y_mae", "psnr_db"):
        if isinstance(summary.get(key), dict):
            metrics[key] = summary[key]
    status["metrics"] = metrics
    if not status["schema_ok"]:
        blockers.append(f"raw-editor latitude schema is not {LATITUDE_SCHEMA}")
    if not status["engine_ok"]:
        blockers.append("latitude render engine is not rawpy/libraw")
    if not status["use_camera_wb"]:
        blockers.append("latitude review did not use camera white balance")
    if not status["row_count_ok"]:
        blockers.append(f"latitude review has fewer than {min_rows} rows")
    if not status["no_source_hf_oracle"]:
        blockers.append("latitude review uses source-HF oracle addback")
    if not status["source_dng"]["exists"]:
        blockers.append("source DNG used for latitude review is missing")
    if not status["candidate_dng"]["exists"]:
        blockers.append("candidate DNG used for latitude review is missing")
    status["ready"] = not blockers
    return status


def build_coverage(args: argparse.Namespace) -> dict[str, Any]:
    root = args.external_root
    required_routes = args.required_route or list(DEFAULT_REQUIRED_ROUTES)
    editors = parse_mapping(args.editor or [])
    latitudes = parse_mapping(args.latitude or [])
    rows = []
    blockers = []
    for route in required_routes:
        editor = editor_status(route, editors.get(route), root)
        latitude = latitude_status(route, latitudes.get(route), root, args.min_latitude_rows)
        route_blockers = [*editor["blockers"], *latitude["blockers"]]
        row = {
            "route": route,
            "ready": not route_blockers,
            "editor": editor,
            "latitude": latitude,
            "blockers": route_blockers,
        }
        rows.append(row)
        if route_blockers:
            blockers.append(f"{route}: " + "; ".join(route_blockers))
    ready_routes = [row["route"] for row in rows if row["ready"]]
    missing_routes = [row["route"] for row in rows if not row["ready"]]
    openability_ready = all(row["editor"]["ready"] for row in rows)
    latitude_ready = all(row["latitude"]["ready"] for row in rows)
    return {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "external_root": str(root),
        "required_routes": required_routes,
        "route_count": len(rows),
        "ready_route_count": len(ready_routes),
        "ready_routes": ready_routes,
        "missing_routes": missing_routes,
        "openability_route_coverage_ready": openability_ready,
        "latitude_route_coverage_ready": latitude_ready,
        "production_ready": openability_ready and latitude_ready and not blockers and args.production_ready,
        "blockers": blockers,
        "routes": rows,
        "next_unambiguous_steps": [
            "Package Mission 1 DNG/GPR and Z8 routed still-SR candidates into editable DNG/GPR with source-camera metadata transplant receipts.",
            "Run build_premium_still_sr_editor_receipt.py for every Mission 1 and Z8 route and require openability_pass=true.",
            "Run build_premium_still_sr_latitude_review.py for every Mission 1 and Z8 candidate DNG using rawpy/LibRaw camera-WB EV stress.",
            "Rerun this coverage audit; then wire exact-sidecar-only noise policy and run check_production_capture_submission.py.",
        ],
    }


def render_html(data: dict[str, Any]) -> str:
    rows = []
    for row in data["routes"]:
        blockers = "<br>".join(html.escape(item) for item in row["blockers"]) or "none"
        editor = row["editor"]
        latitude = row["latitude"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(row['route'])}</td>"
            f"<td>{'ready' if row['ready'] else 'blocked'}</td>"
            f"<td>{'ready' if editor['ready'] else 'blocked'}</td>"
            f"<td>{html.escape(str(editor.get('openability_pass')))}</td>"
            f"<td>{html.escape(str(editor.get('metadata_transplant_pass')))}</td>"
            f"<td>{'ready' if latitude['ready'] else 'blocked'}</td>"
            f"<td>{html.escape(str(latitude.get('row_count')))}</td>"
            f"<td>{html.escape(str(latitude.get('engine')))}</td>"
            f"<td>{blockers}</td>"
            "</tr>"
        )
    next_steps = "".join(f"<li>{html.escape(step)}</li>" for step in data["next_unambiguous_steps"])
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"]) or "<li>none</li>"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR Editor Latitude Coverage</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#111;color:#eee}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;border-radius:8px;padding:14px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}}td,th{{border-bottom:1px solid #333;padding:8px;text-align:left;vertical-align:top}}
code{{color:#b7d7ff}}
</style></head><body>
<h1>Premium Still SR Editor Latitude Coverage</h1>
<p>External root: <code>{html.escape(data['external_root'])}</code></p>
<div class="grid">
<div class="card"><h2>Routes Ready</h2><p>{data['ready_route_count']} / {data['route_count']}</p></div>
<div class="card"><h2>Openability</h2><p>{data['openability_route_coverage_ready']}</p></div>
<div class="card"><h2>Latitude</h2><p>{data['latitude_route_coverage_ready']}</p></div>
<div class="card"><h2>Production Ready</h2><p>{data['production_ready']}</p></div>
</div>
<h2>Blockers</h2><ul>{blockers}</ul>
<h2>Next Unambiguous Steps</h2><ol>{next_steps}</ol>
<table><tr><th>route</th><th>route</th><th>editor</th><th>openability</th><th>metadata</th><th>latitude</th><th>rows</th><th>engine</th><th>blockers</th></tr>
{''.join(rows)}
</table></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=Path("/Volumes/OWC_8TB/gpr_work"))
    ap.add_argument("--required-route", action="append")
    ap.add_argument("--editor", action="append", default=[])
    ap.add_argument("--latitude", action="append", default=[])
    ap.add_argument("--min-latitude-rows", type=int, default=9)
    ap.add_argument("--production-ready", action="store_true")
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    data = build_coverage(args)
    if args.production_ready and data["blockers"]:
        raise SystemExit("refusing --production-ready with blockers")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "coverage.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(
        json.dumps(
            {
                "receipt": str(args.output_dir / "coverage.json"),
                "dashboard": str(args.output_dir / "index.html"),
                "ready_routes": data["ready_route_count"],
                "route_count": data["route_count"],
                "production_ready": data["production_ready"],
                "blocker_count": len(data["blockers"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
