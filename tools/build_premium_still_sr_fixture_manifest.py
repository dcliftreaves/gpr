#!/usr/bin/env python3
"""Build a premium still-SR fixture manifest from a compatibility receipt."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_fixture_manifest.v1"
RUN_RE = re.compile(r"^RUN\s+(?P<kind>\S+)\s+(?P<label>\S+)\s+src=(?P<src>.+)$")


def external_root() -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def classify(label: str) -> dict[str, Any]:
    lower = label.lower()
    if "x2d" in lower:
        return {"camera": "Hasselblad X2D 100C", "camera_key": "x2d", "class": "100mp", "premium_still_sr_eligible": True}
    if "z8" in lower:
        return {"camera": "Nikon Z8", "camera_key": "z8", "class": "50mp", "premium_still_sr_eligible": True}
    if "mission1_50mp" in lower:
        return {"camera": "GoPro Mission 1", "camera_key": "mission1", "class": "50mp", "premium_still_sr_eligible": True}
    if "mission1_12mp" in lower:
        return {"camera": "GoPro Mission 1", "camera_key": "mission1", "class": "12mp", "premium_still_sr_eligible": False}
    if "iphone" in lower:
        return {"camera": "iPhone CFA DNG", "camera_key": "iphone", "class": "mobile_cfa", "premium_still_sr_eligible": False}
    return {"camera": "unknown", "camera_key": "unknown", "class": "unknown", "premium_still_sr_eligible": False}


def sidecars_for(root: Path, camera_key: str) -> list[dict[str, Any]]:
    if camera_key not in {"x2d", "z8", "mission1", "iphone"}:
        return []
    base = root / "artifacts/camera_noise_sidecars_20260629" / camera_key
    refs = []
    for path in sorted(base.glob("*_noise_calibration.json")):
        refs.append(artifact_ref(path))
    return refs


def parse_receipt(path: Path, root: Path) -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = RUN_RE.match(line)
        if not match:
            continue
        src = Path(match.group("src"))
        meta = classify(match.group("label"))
        item: dict[str, Any] = {
            "label": match.group("label"),
            "compatibility_kind": match.group("kind"),
            "source": {
                "path": src.as_posix(),
                "exists": src.is_file(),
            },
            "extension": src.suffix.lower().lstrip("."),
            **meta,
            "noise_sidecars": sidecars_for(root, meta["camera_key"]),
        }
        if src.is_file():
            item["source"].update(artifact_ref(src))
        fixtures.append(item)
    return fixtures


def summarize(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [f for f in fixtures if f.get("premium_still_sr_eligible") is True and f["source"].get("exists") is True]
    missing = [f["label"] for f in fixtures if f["source"].get("exists") is not True]
    return {
        "fixture_count": len(fixtures),
        "eligible_fixture_count": len(eligible),
        "fifty_mp_or_larger_count": sum(1 for f in eligible if f.get("class") in {"50mp", "100mp"}),
        "hundred_mp_or_larger_count": sum(1 for f in eligible if f.get("class") == "100mp"),
        "with_noise_sidecars_count": sum(1 for f in eligible if f.get("noise_sidecars")),
        "missing_sources": missing,
        "ready_for_first_training_manifest": bool(eligible) and not missing and any(f.get("class") == "100mp" for f in eligible),
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Premium Still-SR Fixture Manifest",
        "",
        f"Created: {data['created_utc']}",
        "",
        "## Summary",
        "",
    ]
    for key, value in data["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Fixtures", ""])
    for fixture in data["fixtures"]:
        lines.append(
            f"- `{fixture['label']}`: {fixture['camera']} {fixture['class']} "
            f"{fixture['extension']} eligible={fixture['premium_still_sr_eligible']} "
            f"noise_sidecars={len(fixture['noise_sidecars'])}"
        )
    lines.append("")
    return "\n".join(lines)


def render_html(data: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(f['label'])}</td>"
        f"<td>{html.escape(f['camera'])}</td>"
        f"<td>{html.escape(f['class'])}</td>"
        f"<td>{html.escape(f['extension'])}</td>"
        f"<td>{html.escape(str(f['premium_still_sr_eligible']))}</td>"
        f"<td>{len(f['noise_sidecars'])}</td>"
        f"<td>{html.escape(str(f['source'].get('exists')))}</td>"
        "</tr>"
        for f in data["fixtures"]
    )
    summary = "\n".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in data["summary"].items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Fixtures</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #17202a; }}
table {{ border-collapse: collapse; width: 100%; margin: 18px 0; }}
th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #f4f6f8; }}
</style></head><body>
<h1>Premium Still-SR Fixtures</h1>
<h2>Summary</h2><table><tbody>{summary}</tbody></table>
<h2>Fixtures</h2>
<table><thead><tr><th>Label</th><th>Camera</th><th>Class</th><th>Type</th><th>Eligible</th><th>Noise Sidecars</th><th>Source Exists</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>
"""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compat-receipt", type=Path, required=True)
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    fixtures = parse_receipt(args.compat_receipt, args.external_root)
    data = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "compatibility_receipt": artifact_ref(args.compat_receipt),
            "external_root": args.external_root.as_posix(),
        },
        "summary": summarize(fixtures),
        "fixtures": fixtures,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "fixture_manifest.json", data)
    (args.output_dir / "fixture_manifest.md").write_text(render_markdown(data), encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(args.output_dir / "fixture_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
