#!/usr/bin/env python3
"""Build a real-fixture Bayer phase inventory dashboard.

The stills path has committed synthetic conformance for RGGB, GBRG, GRBG, and
BGGR. This audit answers a different product question: which of those normal
2x2 Bayer phases are backed by actual camera files on this workstation?
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "gpr.bayer_phase_fixture_inventory.v1"
NORMAL_BAYER_PHASES = ("RGGB", "GBRG", "GRBG", "BGGR")
DEFAULT_EXTENSIONS = (".dng", ".gpr", ".nef", ".arw", ".raf", ".cr3", ".3fr")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--root", type=Path, action="append", default=[], help="Fixture root to scan. Repeatable.")
    ap.add_argument("--manifest", type=Path, help="Optional newline or JSON list of files to scan.")
    ap.add_argument("--max-files", type=int, default=400)
    ap.add_argument(
        "--per-root-max",
        type=int,
        default=0,
        help="Optional cap per --root before applying --max-files. Useful for broad trees.",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Number of files per batch-exiftool invocation.",
    )
    ap.add_argument(
        "--exiftool-timeout",
        type=float,
        default=60.0,
        help="Seconds before a batch-exiftool metadata batch is marked timed out.",
    )
    ap.add_argument("--extensions", default=",".join(DEFAULT_EXTENSIONS))
    ap.add_argument(
        "--metadata-mode",
        choices=("auto", "rawpy", "exiftool", "batch-exiftool"),
        default="auto",
        help="Metadata reader. batch-exiftool is fastest for broad fixture discovery.",
    )
    ap.add_argument("--synthetic", action="store_true", help="Build a CI-safe synthetic inventory.")
    return ap.parse_args()


def normalize_phase(phase: str | None) -> str | None:
    if not phase:
        return None
    cleaned = "".join(ch for ch in phase.upper() if ch in "RGBGCMY")
    if len(cleaned) == 4:
        return cleaned.replace("G", "G")
    return cleaned or None


def phase_from_rawpy(path: Path) -> dict[str, Any]:
    try:
        import rawpy
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"missing optional dependency {exc.name}") from exc

    with rawpy.imread(str(path)) as raw:
        pattern = raw.raw_pattern
        desc = raw.color_desc
        if isinstance(desc, bytes):
            desc_text = desc.decode("ascii", "replace")
        else:
            desc_text = str(desc)
        rows = int(pattern.shape[0])
        cols = int(pattern.shape[1])
        letters: list[str] = []
        for y in range(min(2, rows)):
            for x in range(min(2, cols)):
                idx = int(pattern[y, x])
                letters.append(desc_text[idx] if 0 <= idx < len(desc_text) else "?")
        phase = normalize_phase("".join(letters))
        sizes = raw.sizes
        return {
            "phase": phase,
            "pattern_rows": rows,
            "pattern_cols": cols,
            "color_desc": desc_text,
            "width": int(getattr(sizes, "raw_width", 0) or 0),
            "height": int(getattr(sizes, "raw_height", 0) or 0),
            "method": "rawpy",
        }


def exiftool_available() -> bool:
    proc = subprocess.run(["/usr/bin/env", "bash", "-lc", "command -v exiftool"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def parse_exif_cfa(data: dict[str, Any]) -> str | None:
    cfa = data.get("CFAPattern")
    if isinstance(cfa, str):
        direct = normalize_phase(cfa)
        if direct in NORMAL_BAYER_PHASES:
            return direct
        nums = [int(tok) for tok in cfa.replace(",", " ").split() if tok.isdigit()]
    elif isinstance(cfa, list):
        nums = [int(v) for v in cfa if isinstance(v, int) or str(v).isdigit()]
    else:
        nums = []
    if len(nums) >= 6:
        rows, cols = nums[0], nums[1]
        if rows > 0 and cols > 0 and rows * cols == len(nums) - 2:
            nums = nums[2:]

    colors = data.get("CFAPlaneColor")
    numeric_color_lut = {0: "R", 1: "G", 2: "B", 3: "C", 4: "M", 5: "Y"}
    if isinstance(colors, str):
        color_parts = [part.strip().upper() for part in colors.replace(";", " ").replace(",", " ").split() if part.strip()]
        if color_parts and all(part.lstrip("-").isdigit() for part in color_parts):
            lut = [numeric_color_lut.get(int(part), "?") for part in color_parts]
        else:
            lut = []
            for name in color_parts:
                if name.startswith("RED"):
                    lut.append("R")
                elif name.startswith("GREEN"):
                    lut.append("G")
                elif name.startswith("BLUE"):
                    lut.append("B")
                else:
                    lut.append(name[:1] or "?")
    elif isinstance(colors, list):
        lut = []
        for part in colors:
            if isinstance(part, int) or str(part).lstrip("-").isdigit():
                lut.append(numeric_color_lut.get(int(part), "?"))
                continue
            name = str(part).strip().upper()
            if name.startswith("RED"):
                lut.append("R")
            elif name.startswith("GREEN"):
                lut.append("G")
            elif name.startswith("BLUE"):
                lut.append("B")
            else:
                lut.append(name[:1] or "?")
    else:
        lut = ["R", "G", "B"]
    if len(nums) >= 4 and lut:
        return normalize_phase("".join(lut[n] if 0 <= n < len(lut) else "?" for n in nums[:4]))
    return None


def phase_from_exiftool(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "exiftool",
            "-j",
            "-n",
            "-Make",
            "-Model",
            "-ImageWidth",
            "-ImageHeight",
            "-RawImageFullWidth",
            "-RawImageFullHeight",
            "-CFARepeatPatternDim",
            "-CFAPattern",
            "-CFAPlaneColor",
            "-CFALayout",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"exiftool failed with {proc.returncode}")
    records = json.loads(proc.stdout or "[]")
    if not records:
        raise RuntimeError("exiftool returned no record")
    data = records[0]
    phase = parse_exif_cfa(data)
    return {
        "phase": phase,
        "pattern_rows": None,
        "pattern_cols": None,
        "color_desc": str(data.get("CFAPlaneColor") or ""),
        "width": int(data.get("RawImageFullWidth") or data.get("ImageWidth") or 0),
        "height": int(data.get("RawImageFullHeight") or data.get("ImageHeight") or 0),
        "make": data.get("Make"),
        "model": data.get("Model"),
        "method": "exiftool",
    }


def row_for_missing(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "extension": path.suffix.lower(),
        "status": "skipped",
        "phase": None,
        "normal_bayer": False,
        "error": "missing" if not path.is_file() else None,
    }


def row_from_exif_record(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    phase = normalize_phase(parse_exif_cfa(data))
    row = row_for_missing(path)
    row.update(
        {
            "phase": phase,
            "pattern_rows": None,
            "pattern_cols": None,
            "color_desc": str(data.get("CFAPlaneColor") or ""),
            "width": int(data.get("RawImageFullWidth") or data.get("ImageWidth") or 0),
            "height": int(data.get("RawImageFullHeight") or data.get("ImageHeight") or 0),
            "make": data.get("Make"),
            "model": data.get("Model"),
            "method": "batch-exiftool",
            "normal_bayer": phase in NORMAL_BAYER_PHASES,
            "status": "parsed" if phase else "non_bayer_or_unknown",
            "error": None if phase else "no 2x2 Bayer phase found",
        }
    )
    return row


def inspect_files_batch_exiftool(paths: list[Path], chunk_size: int = 200, timeout: float = 60.0) -> list[dict[str, Any]]:
    rows_by_path: dict[str, dict[str, Any]] = {}
    for path in paths:
        rows_by_path[path.as_posix()] = row_for_missing(path)
    chunk_size = max(1, chunk_size)
    for start in range(0, len(paths), chunk_size):
        chunk = [path for path in paths[start : start + chunk_size] if path.is_file()]
        if not chunk:
            continue
        try:
            proc = subprocess.run(
                [
                    "exiftool",
                    "-j",
                    "-n",
                    "-Make",
                    "-Model",
                    "-ImageWidth",
                    "-ImageHeight",
                    "-RawImageFullWidth",
                    "-RawImageFullHeight",
                    "-CFARepeatPatternDim",
                    "-CFAPattern",
                    "-CFAPlaneColor",
                    "-CFALayout",
                    *[str(path) for path in chunk],
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            for path in chunk:
                row = rows_by_path[path.as_posix()]
                row["status"] = "timeout"
                row["error"] = f"exiftool timed out after {timeout:g}s"
            continue
        if proc.returncode != 0:
            error = proc.stderr.strip() or f"exiftool failed with {proc.returncode}"
            for path in chunk:
                row = rows_by_path[path.as_posix()]
                row["error"] = error
            continue
        try:
            records = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as exc:
            for path in chunk:
                row = rows_by_path[path.as_posix()]
                row["error"] = f"exiftool returned invalid JSON: {exc}"
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            source = record.get("SourceFile")
            if not source:
                continue
            source_path = Path(str(source))
            rows_by_path[source_path.as_posix()] = row_from_exif_record(source_path, record)
    return [rows_by_path[path.as_posix()] for path in paths]


def load_manifest(path: Path) -> list[Path]:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [Path(str(item)) for item in data]
        if isinstance(data, dict):
            values = data.get("files") or data.get("paths") or []
            return [Path(str(item)) for item in values]
    except json.JSONDecodeError:
        pass
    return [Path(line.strip()) for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def discover_files(args: argparse.Namespace) -> list[Path]:
    extensions = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in args.extensions.split(",") if ext.strip()}
    files: list[Path] = []
    if args.manifest:
        files.extend(load_manifest(args.manifest))
    for root in args.root:
        root_count = 0
        if root.is_file():
            if root.suffix.lower() in extensions:
                files.append(root)
            continue
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if args.per_root_max > 0 and root_count >= args.per_root_max:
                break
            if path.is_file() and path.suffix.lower() in extensions:
                files.append(path)
                root_count += 1
    seen: set[str] = set()
    unique: list[Path] = []
    for path in files:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
        if len(unique) >= args.max_files:
            break
    return unique


def inspect_file(path: Path, use_exiftool: bool, metadata_mode: str = "auto") -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "extension": path.suffix.lower(),
        "status": "skipped",
        "phase": None,
        "normal_bayer": False,
        "error": None,
    }
    if not path.is_file():
        row["error"] = "missing"
        return row

    errors: list[str] = []
    if metadata_mode == "rawpy":
        loaders = (phase_from_rawpy,)
    elif metadata_mode in {"exiftool", "batch-exiftool"}:
        loaders = (phase_from_exiftool if use_exiftool else None,)
    else:
        loaders = (phase_from_rawpy, phase_from_exiftool if use_exiftool else None)
    for loader in loaders:
        if loader is None:
            continue
        try:
            meta = loader(path)
        except Exception as exc:  # noqa: BLE001 - inventory must keep scanning.
            errors.append(f"{loader.__name__}: {exc}")
            continue
        row.update(meta)
        row["phase"] = normalize_phase(str(meta.get("phase") or ""))
        row["normal_bayer"] = row["phase"] in NORMAL_BAYER_PHASES
        row["status"] = "parsed" if row["phase"] else "non_bayer_or_unknown"
        if row["status"] == "non_bayer_or_unknown":
            row["error"] = "; ".join(errors) if errors else "no 2x2 Bayer phase found"
        return row

    row["error"] = "; ".join(errors) if errors else "no loader available"
    return row


def synthetic_rows() -> list[dict[str, Any]]:
    rows = []
    for i, phase in enumerate(NORMAL_BAYER_PHASES):
        rows.append(
            {
                "path": f"synthetic/{phase.lower()}_{i}.dng",
                "exists": True,
                "bytes": 1024 + i,
                "extension": ".dng",
                "status": "parsed",
                "phase": phase,
                "normal_bayer": True,
                "width": 64,
                "height": 64,
                "pattern_rows": 2,
                "pattern_cols": 2,
                "color_desc": "RGBG",
                "method": "synthetic",
                "error": None,
            }
        )
    rows.append(
        {
            "path": "synthetic/linear_rgb.dng",
            "exists": True,
            "bytes": 2048,
            "extension": ".dng",
            "status": "non_bayer_or_unknown",
            "phase": None,
            "normal_bayer": False,
            "width": 64,
            "height": 64,
            "method": "synthetic",
            "error": "linear RGB negative fixture",
        }
    )
    return rows


def summarize(
    rows: list[dict[str, Any]],
    roots: list[Path],
    max_files: int,
    mode: str,
    per_root_max: int = 0,
    batch_size: int = 200,
    exiftool_timeout: float = 60.0,
) -> dict[str, Any]:
    parsed = [row for row in rows if row.get("status") == "parsed"]
    phase_counts = Counter(str(row.get("phase")) for row in parsed if row.get("phase"))
    present = [phase for phase in NORMAL_BAYER_PHASES if phase_counts.get(phase, 0) > 0]
    missing = [phase for phase in NORMAL_BAYER_PHASES if phase not in present]
    real_rows = [row for row in parsed if row.get("method") != "synthetic"]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": mode,
        "roots": [root.as_posix() for root in roots],
        "max_files": max_files,
        "per_root_max": per_root_max,
        "batch_size": batch_size,
        "exiftool_timeout_seconds": exiftool_timeout,
        "summary": {
            "files_seen": len(rows),
            "parsed_count": len(parsed),
            "normal_bayer_count": sum(1 for row in parsed if row.get("normal_bayer")),
            "skipped_or_unknown_count": len(rows) - len(parsed),
            "phase_counts": dict(sorted(phase_counts.items())),
            "normal_bayer_phases_present": present,
            "normal_bayer_phases_missing": missing,
            "all_normal_phases_have_fixture": not missing,
            "real_normal_phase_count": len({row.get("phase") for row in real_rows if row.get("phase") in NORMAL_BAYER_PHASES}),
            "production_real_phase_coverage": mode == "real" and not missing,
        },
        "rows": rows,
    }


def render_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    cards = [
        ("Mode", data["mode"]),
        ("Files seen", summary["files_seen"]),
        ("Parsed", summary["parsed_count"]),
        ("Per-root cap", data.get("per_root_max") or "none"),
        ("Normal phases", ", ".join(summary["normal_bayer_phases_present"]) or "none"),
        ("Missing", ", ".join(summary["normal_bayer_phases_missing"]) or "none"),
    ]
    card_html = "\n".join(
        f'<section class="card"><div class="label">{html.escape(str(label))}</div><div class="value">{html.escape(str(value))}</div></section>'
        for label, value in cards
    )
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('phase') or ''))}</td>"
        f"<td>{html.escape(str(row.get('status') or ''))}</td>"
        f"<td>{html.escape(str(row.get('method') or ''))}</td>"
        f"<td>{html.escape(str(row.get('width') or ''))} x {html.escape(str(row.get('height') or ''))}</td>"
        f"<td>{html.escape(str(row.get('extension') or ''))}</td>"
        f"<td><code>{html.escape(str(row.get('path') or ''))}</code></td>"
        f"<td>{html.escape(str(row.get('error') or ''))}</td>"
        "</tr>"
        for row in data["rows"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Bayer Phase Fixture Inventory</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #121820; background: #f5f7f8; }}
main {{ max-width: 1220px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 24px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Bayer Phase Fixture Inventory</h1>
<p class="sub">Schema {html.escape(data["schema"])}. This audit separates committed synthetic Bayer conformance from real camera fixture coverage.</p>
<div class="grid">{card_html}</div>
<table><thead><tr><th>Phase</th><th>Status</th><th>Method</th><th>Dimensions</th><th>Ext</th><th>Path</th><th>Error</th></tr></thead><tbody>{rows}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    use_exiftool = exiftool_available() if not args.synthetic else False
    files = [] if args.synthetic else discover_files(args)
    if args.synthetic:
        rows = synthetic_rows()
    elif args.metadata_mode == "batch-exiftool":
        if not use_exiftool:
            raise RuntimeError("batch-exiftool mode requires exiftool")
        rows = inspect_files_batch_exiftool(files, chunk_size=args.batch_size, timeout=args.exiftool_timeout)
    else:
        rows = [inspect_file(path, use_exiftool, args.metadata_mode) for path in files]
    data = summarize(
        rows,
        args.root,
        args.max_files,
        "synthetic" if args.synthetic else "real",
        per_root_max=args.per_root_max,
        batch_size=args.batch_size,
        exiftool_timeout=args.exiftool_timeout,
    )
    (args.output_dir / "inventory.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(args.output_dir / "index.html")
    if not args.synthetic and not rows:
        print("build_bayer_phase_fixture_inventory: warning: no files scanned", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
