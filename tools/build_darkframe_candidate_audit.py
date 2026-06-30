#!/usr/bin/env python3
"""Find darkframe-like DNG candidates for camera-noise calibration.

This is a discovery/audit tool, not a sidecar builder. It scans bounded DNG
sets and records whether any frames are dark enough to justify conversion into
the production `gpr.camera_noise_calibration.v1` sidecar flow. A production
sidecar still requires a stack of at least four actual darkframes for the same
camera/ISO/settings.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "gpr.darkframe_candidate_audit.v1"
NORMAL_BAYER_PHASES = ("RGGB", "GBRG", "GRBG", "BGGR")
DEFAULT_EXTENSIONS = (".dng", ".DNG")


def normalize_phase(phase: str | None) -> str | None:
    if not phase:
        return None
    cleaned = "".join(ch for ch in phase.upper() if ch in "RGB")
    return cleaned if len(cleaned) == 4 else None


def phase_from_rawpy(raw: Any) -> str | None:
    pattern = raw.raw_pattern
    desc = raw.color_desc
    desc_text = desc.decode("ascii", "replace") if isinstance(desc, bytes) else str(desc)
    letters: list[str] = []
    for y in range(min(2, int(pattern.shape[0]))):
        for x in range(min(2, int(pattern.shape[1]))):
            idx = int(pattern[y, x])
            letters.append(desc_text[idx] if 0 <= idx < len(desc_text) else "?")
    return normalize_phase("".join(letters))


def exif_metadata(path: Path) -> dict[str, Any]:
    if subprocess.run(["/usr/bin/env", "bash", "-lc", "command -v exiftool"], stdout=subprocess.DEVNULL).returncode != 0:
        return {}
    proc = subprocess.run(
        ["exiftool", "-j", "-n", "-Make", "-Model", "-ISO", "-ExposureTime", "-FNumber", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if proc.returncode != 0:
        return {}
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {}
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def batch_exif_metadata(paths: list[Path], chunk_size: int = 200) -> dict[str, dict[str, Any]]:
    if subprocess.run(["/usr/bin/env", "bash", "-lc", "command -v exiftool"], stdout=subprocess.DEVNULL).returncode != 0:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(paths), chunk_size):
        chunk = [path for path in paths[start : start + chunk_size] if path.is_file()]
        if not chunk:
            continue
        proc = subprocess.run(
            [
                "exiftool",
                "-j",
                "-n",
                "-Make",
                "-Model",
                "-ISO",
                "-ExposureTime",
                "-FNumber",
                *[str(path) for path in chunk],
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if proc.returncode != 0:
            continue
        try:
            rows = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("SourceFile"):
                out[Path(str(row["SourceFile"])).as_posix()] = row
    return out


def discover_files(roots: list[Path], manifest: Path | None, max_files: int) -> list[Path]:
    files: list[Path] = []
    if manifest:
        files.extend(Path(line.strip()) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))
    for root in roots:
        if root.is_file() and root.suffix in DEFAULT_EXTENSIONS:
            files.append(root)
        elif root.exists():
            for path in root.rglob("*"):
                if len(files) >= max_files:
                    break
                if path.is_file() and path.suffix in DEFAULT_EXTENSIONS:
                    files.append(path)
        if len(files) >= max_files:
            break
    seen: set[str] = set()
    unique: list[Path] = []
    for path in files:
        key = path.as_posix()
        if key in seen:
            continue
        unique.append(path)
        seen.add(key)
        if len(unique) >= max_files:
            break
    return unique


def black_white(raw: Any) -> tuple[float, float]:
    black_levels = [float(v) for v in getattr(raw, "black_level_per_channel", []) if v is not None]
    black = sum(black_levels) / len(black_levels) if black_levels else 0.0
    white_values = getattr(raw, "camera_white_level_per_channel", None) or []
    white_candidates = [float(v) for v in white_values if v is not None and float(v) > black]
    white = min(white_candidates) if white_candidates else float(getattr(raw, "white_level", 0) or 0)
    if white <= black:
        white = 65535.0
    return black, white


def inspect_dng(path: Path, sample_limit: int, exif: dict[str, Any] | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "status": "error",
        "darkframe_like": False,
        "production_stack_ready": False,
        "error": None,
    }
    if not path.is_file():
        row["error"] = "missing"
        return row
    try:
        import numpy as np
        import rawpy
    except ModuleNotFoundError as exc:
        row["error"] = f"missing optional dependency {exc.name}"
        return row

    try:
        with rawpy.imread(str(path)) as raw:
            exif = exif if exif is not None else exif_metadata(path)
            try:
                image = raw.raw_image_visible
            except Exception as exc:  # noqa: BLE001 - Linear Raw/non-CFA DNGs can fail here.
                row.update(
                    {
                        "status": "non_bayer_or_unknown",
                        "make": exif.get("Make"),
                        "model": exif.get("Model"),
                        "iso": exif.get("ISO"),
                        "error": f"rawpy did not expose CFA raw_image_visible: {exc}",
                    }
                )
                return row
            if image is None or not hasattr(image, "shape"):
                row.update(
                    {
                        "status": "non_bayer_or_unknown",
                        "make": exif.get("Make"),
                        "model": exif.get("Model"),
                        "iso": exif.get("ISO"),
                        "error": "rawpy did not expose a CFA raw_image_visible array",
                    }
                )
                return row
            height, width = int(image.shape[0]), int(image.shape[1])
            stride = max(1, int((width * height / max(sample_limit, 1)) ** 0.5))
            sample = image[::stride, ::stride].astype(np.float32, copy=False)
            black, white = black_white(raw)
            raw_range = max(white - black, 1.0)
            norm = np.clip((sample - black) / raw_range, 0.0, 1.0)
            mean_norm = float(np.mean(norm))
            p95_norm = float(np.percentile(norm, 95))
            p99_norm = float(np.percentile(norm, 99))
            saturation_frac = float(np.mean(norm >= 0.98))
            phase = phase_from_rawpy(raw)
            darkframe_like = mean_norm <= 0.02 and p99_norm <= 0.08 and saturation_frac <= 0.0001
            row.update(
                {
                    "status": "parsed",
                    "make": exif.get("Make"),
                    "model": exif.get("Model"),
                    "iso": exif.get("ISO"),
                    "exposure_time": exif.get("ExposureTime"),
                    "f_number": exif.get("FNumber"),
                    "width": width,
                    "height": height,
                    "cfa_phase": phase,
                    "normal_bayer": phase in NORMAL_BAYER_PHASES,
                    "black_level": black,
                    "white_level": white,
                    "sample_stride": stride,
                    "sample_count": int(sample.size),
                    "mean_norm": mean_norm,
                    "p95_norm": p95_norm,
                    "p99_norm": p99_norm,
                    "saturation_frac": saturation_frac,
                    "darkframe_like": darkframe_like,
                    "production_stack_ready": False,
                    "candidate_reason": "dark raw statistics; needs >=4-frame same-camera/ISO stack" if darkframe_like else "scene-like or too bright for darkframe calibration",
                }
            )
    except Exception as exc:  # noqa: BLE001 - discovery should keep scanning.
        row["error"] = str(exc)
    return row


def synthetic_rows() -> list[dict[str, Any]]:
    rows = []
    for i, mean in enumerate((0.006, 0.009, 0.011, 0.013, 0.21)):
        rows.append(
            {
                "path": f"synthetic/mission1_dark_{i}.dng",
                "exists": True,
                "bytes": 1024 + i,
                "status": "parsed",
                "make": "GoPro",
                "model": "Mission 1",
                "iso": 800,
                "width": 4096,
                "height": 3072,
                "cfa_phase": "GBRG",
                "normal_bayer": True,
                "black_level": 64.0,
                "white_level": 16383.0,
                "sample_stride": 16,
                "sample_count": 1000,
                "mean_norm": mean,
                "p95_norm": mean + 0.01,
                "p99_norm": mean + 0.02,
                "saturation_frac": 0.0,
                "darkframe_like": mean < 0.02,
                "production_stack_ready": False,
                "candidate_reason": "synthetic",
                "error": None,
            }
        )
    return rows


def camera_key(row: dict[str, Any]) -> str:
    return f"{row.get('make') or 'unknown'}|{row.get('model') or 'unknown'}|ISO{row.get('iso') or 'unknown'}|{row.get('cfa_phase') or 'unknown'}"


def build_audit(rows: list[dict[str, Any]], mode: str, roots: list[Path], source_kind: str = "candidate_discovery") -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("darkframe_like"):
            groups[camera_key(row)].append(row)
    can_promote_stack = mode == "synthetic" or source_kind == "confirmed_darkframes"
    stack_groups = [
        {
            "key": key,
            "candidate_count": len(items),
            "candidate_stack_ready": len(items) >= 4,
            "production_stack_ready": len(items) >= 4 and can_promote_stack,
            "paths": [item["path"] for item in items],
        }
        for key, items in sorted(groups.items())
    ]
    ready_groups = [row for row in stack_groups if row["production_stack_ready"]]
    parsed = [row for row in rows if row.get("status") == "parsed"]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "source_kind": source_kind,
        "roots": [root.as_posix() for root in roots],
        "summary": {
            "files_seen": len(rows),
            "parsed_count": len(parsed),
            "darkframe_like_count": sum(1 for row in rows if row.get("darkframe_like")),
            "candidate_stack_group_count": len(stack_groups),
            "candidate_stack_ready_group_count": sum(1 for row in stack_groups if row["candidate_stack_ready"]),
            "production_stack_ready_group_count": len(ready_groups),
            "production_sidecar_ready": bool(ready_groups),
        },
        "stack_groups": stack_groups,
        "rows": rows,
        "policy": {
            "sidecar_promotion_requires": "at least four true darkframe-like raw frames for the same camera/ISO/CFA settings",
            "ordinary_scene_frames_are_not_noise_targets": True,
            "candidate_discovery_is_not_production_evidence": source_kind != "confirmed_darkframes" and mode != "synthetic",
        },
    }


def render_html(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    cards = "".join(
        f"<section class='card'><div>{html.escape(label)}</div><strong>{html.escape(str(value))}</strong></section>"
        for label, value in (
            ("Files", summary["files_seen"]),
            ("Parsed", summary["parsed_count"]),
            ("Dark-like", summary["darkframe_like_count"]),
            ("Candidate stacks", summary.get("candidate_stack_ready_group_count", 0)),
            ("Production stacks", summary["production_stack_ready_group_count"]),
        )
    )
    group_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['key'])}</td>"
        f"<td>{row['candidate_count']}</td>"
        f"<td>{html.escape(str(row.get('candidate_stack_ready')))}</td>"
        f"<td>{html.escape(str(row['production_stack_ready']))}</td>"
        f"<td><code>{html.escape(row['paths'][0]) if row['paths'] else ''}</code></td>"
        "</tr>"
        for row in audit["stack_groups"]
    )
    detail_rows = ""
    for row in audit["rows"]:
        mean = row.get("mean_norm")
        p99 = row.get("p99_norm")
        mean_text = f"{mean:.5f}" if isinstance(mean, float) else ""
        p99_text = f"{p99:.5f}" if isinstance(p99, float) else ""
        detail_rows += (
            "<tr>"
            f"<td>{html.escape(str(row.get('darkframe_like')))}</td>"
            f"<td>{html.escape(str(row.get('make') or ''))} {html.escape(str(row.get('model') or ''))}</td>"
            f"<td>{html.escape(str(row.get('iso') or ''))}</td>"
            f"<td>{html.escape(str(row.get('cfa_phase') or ''))}</td>"
            f"<td>{html.escape(mean_text)}</td>"
            f"<td>{html.escape(p99_text)}</td>"
            f"<td><code>{html.escape(str(row.get('path') or ''))}</code></td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Darkframe Candidate Audit</title>
<style>
body{{margin:28px;font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#111820;background:#f6f8fa}}
main{{max-width:1220px;margin:0 auto}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:20px 0}}
.card{{background:white;border:1px solid #dce2e7;border-radius:8px;padding:14px}} .card strong{{font-size:28px}}
table{{width:100%;border-collapse:collapse;background:white;border:1px solid #dce2e7;margin:14px 0 28px}}
th,td{{border-bottom:1px solid #e7ebef;padding:8px;text-align:left;vertical-align:top}} th{{background:#eef2f5}}
code{{font-size:12px;word-break:break-all}}
</style></head><body><main>
<h1>Darkframe Candidate Audit</h1>
<p>This audit finds possible darkframe stacks. It does not promote ordinary photos as noise calibration data.</p>
<div class="grid">{cards}</div>
<h2>Candidate Stack Groups</h2>
<table><thead><tr><th>Camera/ISO/CFA</th><th>Dark-like frames</th><th>Candidate stack</th><th>Production stack</th><th>Example</th></tr></thead><tbody>{group_rows}</tbody></table>
<h2>Scanned Files</h2>
<table><thead><tr><th>Dark-like</th><th>Camera</th><th>ISO</th><th>CFA</th><th>Mean</th><th>P99</th><th>Path</th></tr></thead><tbody>{detail_rows}</tbody></table>
</main></body></html>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--root", type=Path, action="append", default=[])
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--max-files", type=int, default=200)
    ap.add_argument("--sample-limit", type=int, default=1_000_000)
    ap.add_argument("--batch-exif", action="store_true", help="Read grouping metadata with one exiftool call per chunk.")
    ap.add_argument(
        "--source-kind",
        choices=("candidate_discovery", "confirmed_darkframes"),
        default="candidate_discovery",
        help="Use confirmed_darkframes only for roots known to contain true no-scene-signal darkframes.",
    )
    ap.add_argument("--synthetic", action="store_true")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    files = [] if args.synthetic else discover_files(args.root, args.manifest, args.max_files)
    if args.synthetic:
        rows = synthetic_rows()
    else:
        exif_cache = batch_exif_metadata(files) if args.batch_exif else {}
        rows = [inspect_dng(path, args.sample_limit, exif_cache.get(path.as_posix())) for path in files]
    audit = build_audit(rows, "synthetic" if args.synthetic else "real", args.root, args.source_kind)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "darkframe_candidate_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(audit), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
