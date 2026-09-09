#!/usr/bin/env python3
"""Expand the premium still-SR fixture manifest with audited X2D scene DNGs."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_x2d_manifest_expansion.v1"
MANIFEST_SCHEMA = "gpr.premium_still_sr_fixture_manifest.v1"
X2D_WIDTH = 11664
X2D_HEIGHT = 8750


def external_root() -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def load_metadata(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    data = load_json(path)
    out: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            out[str(Path(key))] = value
    return out


def read_exiftool_metadata(path: Path) -> dict[str, Any]:
    try:
        raw = subprocess.check_output(
            [
                "exiftool",
                "-j",
                "-n",
                "-Make",
                "-Model",
                "-ImageWidth",
                "-ImageHeight",
                "-ISO",
                "-BlackLevel",
                "-WhiteLevel",
                "-CFARepeatPatternDim",
                "-CFAPattern",
                path.as_posix(),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"exiftool metadata read failed for {path}: {exc}") from exc
    rows = json.loads(raw)
    if not rows or not isinstance(rows[0], dict):
        raise RuntimeError(f"exiftool returned no metadata for {path}")
    return rows[0]


def metadata_for(path: Path, metadata_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for key in (path.as_posix(), str(path), path.resolve().as_posix()):
        if key in metadata_map:
            return metadata_map[key]
    return read_exiftool_metadata(path)


def int_value(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        if match:
            return int(match.group(0))
    return None


def validate_x2d(path: Path, meta: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    make = str(meta.get("Make") or "").lower()
    model = str(meta.get("Model") or "").lower()
    width = int_value(meta.get("ImageWidth"))
    height = int_value(meta.get("ImageHeight"))
    if "hasselblad" not in make:
        failures.append("make is not Hasselblad")
    if "x2d" not in model or "100" not in model:
        failures.append("model is not Hasselblad X2D 100C")
    if width != X2D_WIDTH or height != X2D_HEIGHT:
        failures.append(f"dimensions are {width}x{height}, expected {X2D_WIDTH}x{X2D_HEIGHT}")
    if path.suffix.lower() != ".dng":
        failures.append("source is not a DNG")
    return failures


def sidecars_for(sidecar_root: Path) -> list[dict[str, Any]]:
    return [artifact_ref(path) for path in sorted(sidecar_root.glob("*_noise_calibration.json"))]


def label_for(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
    return f"x2d_scene_{slug}"


def source_key(fixture: dict[str, Any]) -> str | None:
    source = fixture.get("source") if isinstance(fixture.get("source"), dict) else {}
    path = source.get("path")
    return str(Path(str(path)).resolve()) if path else None


def discover_dngs(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in paths:
        if root.is_file() and root.suffix.lower() == ".dng":
            found.append(root)
        elif root.is_dir():
            found.extend(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".dng")
    return sorted({path.resolve() for path in found}, key=lambda p: p.as_posix())


def route_counts(fixtures: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for fixture in fixtures:
        route = f"{fixture.get('camera_key')}:{fixture.get('class')}:{fixture.get('extension')}"
        counts[route] += 1
    return dict(sorted(counts.items()))


def build(args: argparse.Namespace) -> dict[str, Any]:
    base = load_json(args.base_manifest)
    if base.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"{args.base_manifest} is not a {MANIFEST_SCHEMA} manifest")
    sidecars = sidecars_for(args.sidecar_root)
    if not sidecars:
        raise FileNotFoundError(f"no X2D noise sidecars found in {args.sidecar_root}")

    metadata_map = load_metadata(args.metadata_json)
    fixtures = list(base.get("fixtures", []))
    existing_paths = {key for fixture in fixtures if (key := source_key(fixture))}
    existing_labels = {str(f.get("label")) for f in fixtures if isinstance(f, dict)}

    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for path in discover_dngs(args.x2d_dng_dir):
        resolved = path.resolve()
        if resolved.as_posix() in existing_paths:
            skipped.append({"path": resolved.as_posix(), "reason": "already_in_manifest_path"})
            continue
        meta = metadata_for(resolved, metadata_map)
        failures = validate_x2d(resolved, meta)
        if failures:
            skipped.append({"path": resolved.as_posix(), "reason": "metadata_validation_failed", "failures": failures})
            continue
        label = label_for(resolved)
        if label in existing_labels:
            skipped.append({"path": resolved.as_posix(), "reason": "already_in_manifest_label", "label": label})
            continue
        source = artifact_ref(resolved)
        fixture = {
            "label": label,
            "compatibility_kind": "audited_x2d_scene_dng",
            "source": {"exists": True, **source},
            "extension": "dng",
            "camera": "Hasselblad X2D 100C",
            "camera_key": "x2d",
            "class": "100mp",
            "premium_still_sr_eligible": True,
            "width": int_value(meta.get("ImageWidth")),
            "height": int_value(meta.get("ImageHeight")),
            "iso": int_value(meta.get("ISO")),
            "black_level": meta.get("BlackLevel"),
            "white_level": meta.get("WhiteLevel"),
            "cfa_repeat_pattern_dim": meta.get("CFARepeatPatternDim"),
            "cfa_pattern": meta.get("CFAPattern"),
            "noise_sidecars": sidecars,
        }
        fixtures.append(fixture)
        added.append({"label": label, "path": resolved.as_posix(), "iso": fixture["iso"], "sha256": source["sha256"]})
        existing_paths.add(resolved.as_posix())
        existing_labels.add(label)

    eligible = [f for f in fixtures if isinstance(f, dict) and f.get("premium_still_sr_eligible") is True and f.get("source", {}).get("exists") is True]
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "base_manifest": artifact_ref(args.base_manifest),
            "x2d_dng_dirs": [path.as_posix() for path in args.x2d_dng_dir],
            "x2d_noise_sidecar_root": args.sidecar_root.as_posix(),
            "metadata_json": artifact_ref(args.metadata_json) if args.metadata_json else None,
            "external_root": args.external_root.as_posix(),
        },
        "summary": {
            "fixture_count": len(fixtures),
            "eligible_fixture_count": len(eligible),
            "added_x2d_scene_count": len(added),
            "skipped_x2d_scene_count": len(skipped),
            "hundred_mp_or_larger_count": sum(1 for f in eligible if f.get("class") == "100mp"),
            "with_noise_sidecars_count": sum(1 for f in eligible if f.get("noise_sidecars")),
            "route_counts": route_counts(fixtures),
            "ready_for_gate20_strict_planning": sum(1 for f in eligible if f.get("camera_key") == "x2d" and f.get("class") == "100mp") * 27 >= 576,
        },
        "fixtures": fixtures,
    }
    receipt = {
        "schema": SCHEMA,
        "created_utc": manifest["created_utc"],
        "base_manifest": args.base_manifest.as_posix(),
        "expanded_manifest": (args.output_dir / "fixture_manifest.json").as_posix(),
        "sidecar_count": len(sidecars),
        "added_x2d_scenes": added,
        "skipped_x2d_scenes": skipped,
        "summary": manifest["summary"],
    }
    return {"manifest": manifest, "receipt": receipt}


def render_markdown(payload: dict[str, Any]) -> str:
    receipt = payload["receipt"]
    lines = [
        "# X2D Fixture Manifest Expansion",
        "",
        f"Created: {receipt['created_utc']}",
        "",
        "## Summary",
        "",
    ]
    for key, value in receipt["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Added X2D Scenes", ""])
    for row in receipt["added_x2d_scenes"]:
        lines.append(f"- `{row['label']}` ISO {row.get('iso')}: `{row['path']}`")
    lines.append("")
    return "\n".join(lines)


def render_html(payload: dict[str, Any]) -> str:
    receipt = payload["receipt"]
    cards = "".join(
        f"<div class='card'><span>{html.escape(str(k))}</span><strong>{html.escape(str(v))}</strong></div>"
        for k, v in receipt["summary"].items()
        if k != "route_counts"
    )
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['label']))}</td>"
        f"<td>{html.escape(str(row.get('iso')))}</td>"
        f"<td><code>{html.escape(str(row['path']))}</code></td>"
        f"<td><code>{html.escape(str(row['sha256']))}</code></td>"
        "</tr>"
        for row in receipt["added_x2d_scenes"]
    )
    skipped = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(row['path']))}</code></td>"
        f"<td>{html.escape(str(row['reason']))}</td>"
        f"<td>{html.escape(str(row.get('failures', '')))}</td>"
        "</tr>"
        for row in receipt["skipped_x2d_scenes"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>X2D Manifest Expansion</title>
<style>
body {{ margin: 0; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #14191f; background: #f5f7f8; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
h1 {{ margin: 0 0 6px; font-size: 34px; letter-spacing: 0; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin: 18px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 12px; }}
.card span {{ display: block; color: #58636e; font-size: 12px; }}
.card strong {{ display: block; font-size: 20px; margin-top: 4px; }}
table {{ width: 100%; border-collapse: collapse; background: white; margin: 14px 0 24px; }}
th, td {{ border-bottom: 1px solid #dce2e7; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf1f4; }}
code {{ white-space: normal; }}
</style></head><body><main>
<h1>X2D Manifest Expansion</h1>
<p>Adds audited Hasselblad X2D 100C scene DNGs to the routed premium still-SR manifest before Gate20 target planning.</p>
<section class="cards">{cards}</section>
<h2>Added Scenes</h2>
<table><thead><tr><th>Label</th><th>ISO</th><th>Path</th><th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Skipped Scenes</h2>
<table><thead><tr><th>Path</th><th>Reason</th><th>Failures</th></tr></thead><tbody>{skipped}</tbody></table>
</main></body></html>
"""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-manifest", type=Path, required=True)
    ap.add_argument("--x2d-dng-dir", type=Path, action="append", required=True)
    ap.add_argument("--sidecar-root", type=Path, default=external_root() / "artifacts/camera_noise_sidecars_20260629/x2d")
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--metadata-json", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    payload = build(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "fixture_manifest.json", payload["manifest"])
    write_json(args.output_dir / "x2d_manifest_expansion_receipt.json", payload["receipt"])
    (args.output_dir / "fixture_manifest.md").write_text(render_markdown(payload), encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(payload), encoding="utf-8")
    print(args.output_dir / "fixture_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
