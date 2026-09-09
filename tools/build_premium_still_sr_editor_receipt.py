#!/usr/bin/env python3
"""Build a neutral premium still-SR editor/openability receipt.

This wraps the existing SR generation and packaging receipts into the still-SR
product vocabulary. It does not run inference or packaging itself; those steps
remain explicit so large raws stay under caller control.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_editor_receipt.v1"


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


def resolve_artifact(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    if value.startswith("artifacts/"):
        return root / value
    return path


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


def first_stream_dim(media: dict[str, Any]) -> dict[str, Any]:
    streams = media.get("ffprobe", {}).get("streams", [])
    if not streams:
        return {"width": None, "height": None, "frames": None, "codec": None}
    stream = streams[0]
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "frames": stream.get("nb_frames"),
        "codec": stream.get("codec_name"),
    }


def metadata_audit_summary(
    *,
    audit_path: Path | None,
    metadata_dng: Path | None,
    allowed_missing_recommended: set[str],
    allowed_diff_tags: set[str],
    root: Path,
) -> dict[str, Any]:
    if audit_path is None:
        return {
            "provided": False,
            "passed": False,
            "audit": artifact_ref(None, root),
            "metadata_dng": artifact_ref(metadata_dng, root),
            "candidates": [],
        }
    audit = load_json(audit_path)
    candidates = []
    passed = True
    for row in audit.get("candidates", []):
        if not isinstance(row, dict):
            passed = False
            continue
        missing_required = row.get("missing_required") if isinstance(row.get("missing_required"), list) else []
        missing_recommended = row.get("missing_recommended") if isinstance(row.get("missing_recommended"), list) else []
        diffs = row.get("diffs_from_reference") if isinstance(row.get("diffs_from_reference"), list) else []
        diff_tags = sorted(
            item.get("tag")
            for item in diffs
            if isinstance(item, dict) and isinstance(item.get("tag"), str)
        )
        missing_recommended_set = {str(item) for item in missing_recommended}
        diff_tag_set = {str(item) for item in diff_tags}
        row_passed = (
            row.get("readable_by_exiftool") is True
            and missing_required == []
            and missing_recommended_set <= allowed_missing_recommended
            and diff_tag_set <= allowed_diff_tags
        )
        passed = passed and row_passed
        candidates.append(
            {
                "source": row.get("source"),
                "passed": row_passed,
                "readable_by_exiftool": row.get("readable_by_exiftool"),
                "missing_required": missing_required,
                "missing_recommended": sorted(missing_recommended_set),
                "diff_tags": diff_tags,
            }
        )
    return {
        "provided": True,
        "passed": bool(candidates) and passed,
        "allowed_missing_recommended": sorted(allowed_missing_recommended),
        "allowed_diff_tags": sorted(allowed_diff_tags),
        "audit": artifact_ref(audit_path, root),
        "metadata_dng": artifact_ref(metadata_dng, root),
        "candidates": candidates,
    }


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    root = args.external_root
    bench = load_json(args.bench_receipt)
    packaging = load_json(args.packaging_receipt)
    metadata = metadata_audit_summary(
        audit_path=args.metadata_audit,
        metadata_dng=args.metadata_dng,
        allowed_missing_recommended=set(args.metadata_allowed_missing_recommended or []),
        allowed_diff_tags=set(args.metadata_allowed_diff_tag or []),
        root=root,
    )

    sr_raw = packaging.get("sr_raw", {}) if isinstance(packaging.get("sr_raw"), dict) else {}
    editable_dng = packaging.get("editable_dng", {}) if isinstance(packaging.get("editable_dng"), dict) else {}
    editable_gpr = packaging.get("editable_gpr", {}) if isinstance(packaging.get("editable_gpr"), dict) else {}
    prores = packaging.get("prores_review", {}) if isinstance(packaging.get("prores_review"), dict) else {}
    prores_fps = packaging.get("prores_fps_review", {}) if isinstance(packaging.get("prores_fps_review"), dict) else {}
    metrics = editable_gpr.get("readback_metrics", {}) if isinstance(editable_gpr.get("readback_metrics"), dict) else {}

    dng_open = isinstance(editable_dng.get("rawpy_open_shape"), list)
    gpr_dng_open = isinstance(editable_gpr.get("gpr_to_dng_rawpy_open_shape"), list)
    dng_lossless = editable_dng.get("raw_roundtrip_byte_identical") is True
    gpr_psnr = metrics.get("psnr14_db")
    rmse_dn = metrics.get("rmse_dn")
    raw_range_dn = float(args.raw_white_level) - float(args.raw_black_level)
    if isinstance(rmse_dn, (int, float)) and float(rmse_dn) > 0.0 and raw_range_dn > 0.0:
        gpr_psnr_range_db: float | None = 20.0 * math.log10(raw_range_dn / float(rmse_dn))
    elif isinstance(rmse_dn, (int, float)) and float(rmse_dn) == 0.0:
        gpr_psnr_range_db = 99.0
    else:
        gpr_psnr_range_db = None
    gpr_high_quality = (
        isinstance(gpr_psnr_range_db, (int, float))
        and float(gpr_psnr_range_db) >= args.min_gpr_psnr_range_db
    )

    blockers: list[str] = []
    if not dng_open:
        blockers.append("editable DNG did not open through rawpy")
    if not gpr_dng_open:
        blockers.append("GPR-derived DNG did not open through rawpy")
    if not dng_lossless:
        blockers.append("generic DNG did not roundtrip byte-identically to source raw")
    if not gpr_high_quality:
        blockers.append(f"editable GPR range PSNR below {args.min_gpr_psnr_range_db:.1f} dB")
    if not metadata["passed"]:
        blockers.append("source-camera metadata transplant is not proven")
    if not args.raw_editor_latitude:
        blockers.append("receipt proves openability/export, not full raw-editor latitude")

    production_ready = not blockers and args.production_ready
    if args.production_ready and blockers:
        raise SystemExit("refusing --production-ready with blockers: " + "; ".join(blockers))

    sr_raw_path = resolve_artifact(root, sr_raw.get("path"))
    editable_dng_path = resolve_artifact(root, editable_dng.get("path"))
    editable_gpr_path = resolve_artifact(root, editable_gpr.get("path"))
    prores_path = resolve_artifact(root, prores.get("path"))
    prores_fps_path = resolve_artifact(root, prores_fps.get("path"))

    timing = bench.get("timing", {}) if isinstance(bench.get("timing"), dict) else {}
    return {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "route": args.route,
        "camera": args.camera,
        "source_frame": args.source_frame,
        "production_ready": production_ready,
        "openability_pass": dng_open and gpr_dng_open and dng_lossless and gpr_high_quality,
        "blockers": blockers,
        "dimensions": {
            "width": sr_raw.get("width"),
            "height": sr_raw.get("height"),
            "rawpy_open_shape": editable_dng.get("rawpy_open_shape"),
            "gpr_to_dng_rawpy_open_shape": editable_gpr.get("gpr_to_dng_rawpy_open_shape"),
        },
        "sr_runtime": {
            "device": bench.get("device"),
            "fps_with_write": timing.get("fps_with_write"),
            "fps_inference_only": timing.get("fps_inference_only"),
            "total_with_write_s": timing.get("total_with_write_s"),
            "tile": timing.get("tile"),
            "overlap": timing.get("overlap"),
            "tile_count": timing.get("tile_count"),
        },
        "editable_gpr": {
            "quality": editable_gpr.get("quality"),
            "raw_to_gpr_mode": editable_gpr.get("raw_to_gpr_mode"),
            "psnr14_db": gpr_psnr,
            "psnr_range_db": gpr_psnr_range_db,
            "raw_black_level": args.raw_black_level,
            "raw_white_level": args.raw_white_level,
            "raw_range_dn": raw_range_dn,
            "mae_dn": metrics.get("mae_dn"),
            "rmse_dn": rmse_dn,
            "max_abs_dn": metrics.get("max_abs_dn"),
        },
        "metadata_transplant": metadata,
        "review_media": {
            "single_frame": first_stream_dim(prores),
            "two_frame_fps_check": first_stream_dim(prores_fps),
        },
        "inputs": {
            "bench_receipt": artifact_ref(args.bench_receipt, root),
            "packaging_receipt": artifact_ref(args.packaging_receipt, root),
        },
        "artifacts": {
            "sr_raw": artifact_ref(sr_raw_path, root),
            "editable_dng": artifact_ref(editable_dng_path, root),
            "editable_gpr": artifact_ref(editable_gpr_path, root),
            "prores_review": artifact_ref(prores_path, root),
            "prores_fps_review": artifact_ref(prores_fps_path, root),
        },
        "notes": [
            "Openability means rawpy can open the DNG and GPR-derived DNG, generic DNG raw roundtrip is lossless, and GPR readback exceeds the configured PSNR floor.",
            "Raw-editor latitude promotion still requires source-camera metadata, tone/color, exposure-stress, and worst-row visual receipts.",
        ],
    }


def render_html(receipt: dict[str, Any]) -> str:
    blockers = "".join(f"<li>{html.escape(item)}</li>" for item in receipt["blockers"]) or "<li>none</li>"
    artifacts = "".join(
        f"<tr><td>{html.escape(key)}</td><td>{html.escape(str(row.get('path')))}</td>"
        f"<td>{html.escape(str(row.get('bytes')))}</td><td>{html.escape(str(row.get('sha256')))}</td></tr>"
        for key, row in receipt["artifacts"].items()
    )
    sr = receipt["sr_runtime"]
    gpr = receipt["editable_gpr"]
    dims = receipt["dimensions"]
    metadata = receipt["metadata_transplant"]
    metadata_rows = "".join(
        f"<tr><td>{html.escape(str(row.get('source')))}</td><td>{row.get('passed')}</td>"
        f"<td>{html.escape(', '.join(row.get('missing_required') or []) or 'none')}</td>"
        f"<td>{html.escape(', '.join(row.get('missing_recommended') or []) or 'none')}</td>"
        f"<td>{html.escape(', '.join(row.get('diff_tags') or []) or 'none')}</td></tr>"
        for row in metadata.get("candidates", [])
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Premium Still SR Editor Receipt</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#111;color:#eee}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:18px 0}}
.card{{border:1px solid #333;background:#1a1a1a;padding:14px;border-radius:8px}}
.ok{{color:#7bd88f}} .bad{{color:#ff8a80}} table{{border-collapse:collapse;width:100%;margin-top:14px}}
td,th{{border-bottom:1px solid #333;padding:8px;text-align:left;vertical-align:top}} code{{color:#b7d7ff}}
</style></head><body>
<h1>Premium Still SR Editor Receipt</h1>
<p><b>Route:</b> {html.escape(receipt['route'])} &nbsp; <b>Camera:</b> {html.escape(receipt['camera'])}</p>
<p class="{'ok' if receipt['openability_pass'] else 'bad'}">openability_pass={receipt['openability_pass']} production_ready={receipt['production_ready']}</p>
<div class="grid">
<div class="card"><h2>Dimensions</h2><p>{dims.get('width')} x {dims.get('height')}</p><p>rawpy {html.escape(str(dims.get('rawpy_open_shape')))}</p></div>
<div class="card"><h2>SR Runtime</h2><p>{sr.get('fps_with_write')} fps with write</p><p>{sr.get('total_with_write_s')} s total</p></div>
<div class="card"><h2>Editable GPR</h2><p>{gpr.get('psnr_range_db')} dB range PSNR</p><p>{gpr.get('psnr14_db')} dB PSNR14</p><p>MAE {gpr.get('mae_dn')} DN</p></div>
<div class="card"><h2>Metadata</h2><p>passed={metadata.get('passed')}</p><p>{html.escape(str((metadata.get('metadata_dng') or {}).get('path')))}</p></div>
</div>
<h2>Blockers</h2><ul>{blockers}</ul>
<h2>Metadata Audit</h2><table><tr><th>candidate</th><th>passed</th><th>missing required</th><th>missing recommended</th><th>diff tags</th></tr>{metadata_rows}</table>
<h2>Artifacts</h2><table><tr><th>kind</th><th>path</th><th>bytes</th><th>sha256</th></tr>{artifacts}</table>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bench-receipt", type=Path, required=True)
    ap.add_argument("--packaging-receipt", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--external-root", type=Path, default=Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work"))
    ap.add_argument("--route", required=True)
    ap.add_argument("--camera", required=True)
    ap.add_argument("--source-frame", required=True)
    ap.add_argument("--raw-black-level", type=float, default=0.0)
    ap.add_argument("--raw-white-level", type=float, default=16383.0)
    ap.add_argument("--min-gpr-psnr-range-db", type=float, default=60.0)
    ap.add_argument("--metadata-audit", type=Path)
    ap.add_argument("--metadata-dng", type=Path)
    ap.add_argument("--metadata-allowed-missing-recommended", action="append", default=["OpcodeList2"])
    ap.add_argument("--metadata-allowed-diff-tag", action="append", default=["AsShotNeutral", "ActiveArea"])
    ap.add_argument("--raw-editor-latitude", action="store_true")
    ap.add_argument("--production-ready", action="store_true")
    args = ap.parse_args()

    receipt = build_receipt(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.output_dir / "editor_receipt.json"
    out_html = args.output_dir / "index.html"
    out_json.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    out_html.write_text(render_html(receipt), encoding="utf-8")
    print(json.dumps({"receipt": str(out_json), "dashboard": str(out_html), "openability_pass": receipt["openability_pass"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
