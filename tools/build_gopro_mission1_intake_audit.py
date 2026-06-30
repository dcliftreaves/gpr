#!/usr/bin/env python3
"""Build a GoPro Mission 1 firmware-intake audit.

This is a review layer over the portable handoff bundle. It answers two
separate questions:

* Is the bundle complete and easy for a GoPro reviewer to validate?
* Has the real Mission 1 camera path replaced the stand-in receipts?
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTERNAL = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_MANIFEST = DEFAULT_EXTERNAL / "artifacts/gopro_mission1_handoff_bundle_capture_requirements_20260630/manifest.json"
REQUIRED_PRODUCT_PILLARS = {
    "raw_stills": "RAW stills",
    "raw_video_mvp": "RAW video MVP",
    "premium_still_sr": "Premium still/SR",
    "raw_video_psf_sr": "PSF-aware video/SR",
}


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def safe_child(root: Path, rel: str) -> Path:
    path = Path(rel)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe bundle path: {rel}")
    return root / path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_bundle(manifest: Path) -> tuple[bool, dict[str, Any]]:
    proc = run([sys.executable, str(ROOT / "tools/verify_labs_bundle.py"), str(manifest), "--json"])
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        report = {"failures": [proc.stderr.strip() or proc.stdout.strip() or "bundle verifier emitted invalid JSON"]}
    return proc.returncode == 0 and not report.get("failures"), report


def artifact_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = manifest.get("artifacts")
    if not isinstance(rows, list):
        return {}
    return {str(row.get("path")): row for row in rows if isinstance(row, dict) and row.get("path")}


def find_gvid_sample(verify_report: dict[str, Any]) -> dict[str, Any] | None:
    for row in verify_report.get("artifacts", []):
        if isinstance(row, dict) and row.get("kind") == "gvid" and str(row.get("path", "")).startswith("samples/"):
            return row
    return None


def check(name: str, passed: bool, detail: str, *, production_gate: bool = False) -> dict[str, Any]:
    return {
        "id": name,
        "passed": bool(passed),
        "detail": detail,
        "production_gate": bool(production_gate),
    }


def product_pillar_rows(manifest: dict[str, Any]) -> list[dict[str, str]]:
    rows = manifest.get("product_pillars")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append({
            "id": str(row.get("id", "")),
            "release_label": str(row.get("release_label", "")),
            "status": str(row.get("status", "")),
            "summary": str(row.get("summary", "")),
            "open_gate": str(row.get("open_gate", "")),
        })
    return out


def validate_product_pillars(rows: list[dict[str, str]]) -> tuple[bool, str]:
    by_id = {row["id"]: row for row in rows if row.get("id")}
    missing = set(REQUIRED_PRODUCT_PILLARS) - set(by_id)
    extra = set(by_id) - set(REQUIRED_PRODUCT_PILLARS)
    label_mismatches = [
        pillar_id
        for pillar_id, expected in REQUIRED_PRODUCT_PILLARS.items()
        if pillar_id in by_id and by_id[pillar_id].get("release_label") != expected
    ]
    empty_fields = [
        pillar_id
        for pillar_id, row in by_id.items()
        if not row.get("status") or not row.get("summary") or not row.get("open_gate")
    ]
    failures = []
    if missing:
        failures.append("missing: " + ", ".join(sorted(missing)))
    if extra:
        failures.append("unexpected: " + ", ".join(sorted(extra)))
    if label_mismatches:
        failures.append("label mismatch: " + ", ".join(sorted(label_mismatches)))
    if empty_fields:
        failures.append("empty fields: " + ", ".join(sorted(empty_fields)))
    if failures:
        return False, "; ".join(failures)
    return True, "bundle manifest exposes RAW stills, RAW video MVP, premium still/SR, and PSF-aware video/SR labels"


def build_audit(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    bundle_root = manifest_path.parent
    manifest = read_json(manifest_path)
    artifacts = artifact_index(manifest)
    verify_ok, verify_report = verify_bundle(manifest_path)
    gvid = find_gvid_sample(verify_report) or {}
    gvid_meta = gvid.get("gvid") if isinstance(gvid.get("gvid"), dict) else {}

    def bundle_json(rel: str) -> dict[str, Any]:
        return read_json(safe_child(bundle_root, rel))

    quick: dict[str, Any] = {}
    bench: dict[str, Any] = {}
    handoff: dict[str, Any] = {}
    preview: dict[str, Any] = {}
    closure: dict[str, Any] = {}
    json_failures: list[str] = []
    for rel, target in [
        ("receipts/quick_validation_dry_run.json", "quick"),
        ("receipts/labs_target_bench.json", "bench"),
        ("receipts/camera_handoff_receipt.json", "handoff"),
        ("receipts/preview_ui_receipt.json", "preview"),
        ("receipts/mission1_camera_closure_run.json", "closure"),
    ]:
        try:
            value = bundle_json(rel)
        except Exception as exc:
            json_failures.append(f"{rel}: {exc}")
            value = {}
        if target == "quick":
            quick = value
        elif target == "bench":
            bench = value
        elif target == "handoff":
            handoff = value
        elif target == "preview":
            preview = value
        else:
            closure = value

    required_docs = {
        "docs/REPO_README.md",
        "docs/source/docs__GOPRO_MISSION1_QUICK_VALIDATION.md",
        "docs/source/docs__LABS_FIRMWARE_API.md",
        "docs/source/docs__LABS_MISSION1_RUNBOOK.md",
        "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.md",
        "docs/source/docs__PRODUCTION_CAPTURE_REQUIREMENTS.json",
        "docs/source/docs__RELEASE_ARTIFACTS.md",
        "docs/source/docs__release_evidence_manifest.json",
        "docs/source/tools__run_gopro_mission1_quick_validation.py",
        "docs/source/tools__check_mission1_camera_source_probe.py",
    }
    missing_docs = sorted(required_docs - set(artifacts))

    bench_verdict = bench.get("verdict") if isinstance(bench.get("verdict"), dict) else {}
    handoff_verdict = handoff.get("verdict") if isinstance(handoff.get("verdict"), dict) else {}
    preview_verdict = preview.get("verdict") if isinstance(preview.get("verdict"), dict) else {}
    closure_verdict = closure.get("verdict") if isinstance(closure.get("verdict"), dict) else {}
    handoff_target = handoff.get("target") if isinstance(handoff.get("target"), dict) else {}
    preview_target = preview.get("target") if isinstance(preview.get("target"), dict) else {}
    quick_verdict = quick.get("verdict") if isinstance(quick.get("verdict"), dict) else {}
    quick_target = quick.get("target") if isinstance(quick.get("target"), dict) else {}
    pillars = product_pillar_rows(manifest)
    pillars_ok, pillars_detail = validate_product_pillars(pillars)

    checks = [
        check(
            "bundle_manifest_verifies",
            verify_ok,
            "portable bundle manifest, hashes, JSON, media, and .gvid sample verify cleanly"
            if verify_ok
            else "; ".join(str(x) for x in verify_report.get("failures", [])),
        ),
        check(
            "sample_is_4k_bayer_gvid",
            gvid_meta.get("width") == 4096 and gvid_meta.get("height") == 3072 and gvid_meta.get("frame_count", 0) > 0,
            f"sample={gvid.get('path')} dimensions={gvid_meta.get('width')}x{gvid_meta.get('height')} frames={gvid_meta.get('frame_count')}",
        ),
        check(
            "quick_validation_dry_run_present",
            quick.get("schema") == "gpr.gopro_mission1_quick_validation.v1"
            and quick_verdict.get("command_ready") is True
            and quick_target.get("role") == "camera",
            "dry-run command is packaged for a camera-role Mission 1 raw endpoint",
        ),
        check(
            "firmware_docs_packaged",
            not missing_docs,
            "required firmware-facing docs and quick-validation tools are packaged"
            if not missing_docs
            else "missing: " + ", ".join(missing_docs),
        ),
        check(
            "product_pillar_labels_packaged",
            pillars_ok,
            pillars_detail,
        ),
        check(
            "standin_encode_receipt_passes_20fps",
            all(
                bench_verdict.get(key) is True
                for key in ("fps_target_met", "fps_wall_target_met", "no_drops", "gvid_valid", "interruption_recovery_proven")
            ),
            f"bench target={bench.get('target', {}).get('name')} wall_fps={bench.get('target', {}).get('actual_wall_fps')}",
        ),
        check(
            "standin_preview_receipt_passes_20fps",
            preview_target.get("role") == "stand-in"
            and preview_verdict.get("target_evidence") is True
            and preview_verdict.get("fps_target_met") is True,
            f"preview target_role={preview_target.get('role')} ui_ready={preview_verdict.get('ui_ready')}",
        ),
        check(
            "camera_handoff_receipts_are_real_camera",
            handoff_target.get("role") == "camera"
            and preview_target.get("role") == "camera"
            and handoff_verdict.get("firmware_ready") is True
            and preview_verdict.get("ui_ready") is True
            and closure_verdict.get("production_ready") is True,
            "requires camera-role sensor/DMA, storage, display, and aggregate closure receipts",
            production_gate=True,
        ),
    ]

    review_ready = all(row["passed"] for row in checks if not row["production_gate"]) and not json_failures
    camera_ready = checks[-1]["passed"]
    readiness_percent = 82 if review_ready else round(100 * sum(row["passed"] for row in checks) / len(checks))
    if camera_ready:
        readiness_percent = 100

    blockers: list[str] = []
    if json_failures:
        blockers.extend(json_failures)
    if not review_ready:
        blockers.extend(row["detail"] for row in checks if not row["passed"] and not row["production_gate"])
    if not camera_ready:
        blockers.append("real Mission 1 camera-role sensor/DMA, storage, and rear-display receipts are still missing")

    return {
        "schema": "gpr.gopro_mission1_intake_audit.v1",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "manifest": str(manifest_path),
        "bundle_root": str(bundle_root),
        "readiness_percent": readiness_percent,
        "handoff_review_ready": review_ready,
        "camera_production_ready": camera_ready,
        "production_ready": camera_ready,
        "checks": checks,
        "blockers": blockers,
        "product_pillars": pillars,
        "summary": {
            "artifact_count": len(artifacts),
            "sample_gvid": {
                "path": gvid.get("path"),
                "width": gvid_meta.get("width"),
                "height": gvid_meta.get("height"),
                "fps_x1000": gvid_meta.get("fps_x1000"),
                "frame_count": gvid_meta.get("frame_count"),
                "payload_bytes": gvid_meta.get("payload_bytes"),
            },
            "bench_wall_fps": bench.get("target", {}).get("actual_wall_fps") if isinstance(bench.get("target"), dict) else None,
            "target_role": manifest.get("target", {}).get("role") if isinstance(manifest.get("target"), dict) else None,
            "handoff_target_role": handoff_target.get("role"),
            "preview_target_role": preview_target.get("role"),
            "closure_blocker": closure_verdict.get("handoff_blocker"),
            "preview_blocker": closure_verdict.get("preview_blocker"),
        },
    }


def render_html(data: dict[str, Any], out_json: Path) -> str:
    checks = "\n".join(
        f"""<tr><td>{html.escape(row["id"])}</td><td class="{'pass' if row['passed'] else 'fail'}">{str(row['passed']).lower()}</td><td>{html.escape(row['detail'])}</td></tr>"""
        for row in data["checks"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    pillars = "\n".join(
        f"""<tr><td>{html.escape(row["release_label"])}</td><td>{html.escape(row["status"])}</td><td>{html.escape(row["summary"])}</td><td>{html.escape(row["open_gate"])}</td></tr>"""
        for row in data.get("product_pillars", [])
    )
    summary = data["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GoPro Mission 1 Intake Audit</title>
  <style>
    body {{ margin: 0; background: #f3f5f6; color: #101418; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 38px; letter-spacing: 0; }}
    h2 {{ margin: 24px 0 10px; }}
    .hero {{ padding: 10px 0 24px; }}
    .score {{ font-size: 58px; font-weight: 780; margin-top: 12px; }}
    .sub {{ color: #53606d; font-size: 17px; max-width: 820px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
    .k {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .v {{ font-size: 22px; font-weight: 720; margin-top: 4px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
    th, td {{ padding: 10px; border-bottom: 1px solid #e5eaee; text-align: left; vertical-align: top; }}
    th {{ color: #53606d; font-size: 12px; text-transform: uppercase; }}
    .pass {{ color: #16794c; font-weight: 760; }}
    .fail {{ color: #a33a32; font-weight: 760; }}
    .panel {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>GoPro Mission 1 Intake Audit</h1>
    <p class="sub">Firmware-review readiness is separated from camera-production readiness. The bundle can be review-ready while still requiring real Mission 1 sensor/DMA, storage, and rear-display receipts.</p>
    <div class="score">{data["readiness_percent"]}%</div>
    <p>handoff review ready: <strong>{str(data["handoff_review_ready"]).lower()}</strong>; camera production ready: <strong>{str(data["camera_production_ready"]).lower()}</strong></p>
  </section>
  <section class="grid">
    <div class="card"><div class="k">Sample</div><div class="v">{summary["sample_gvid"]["width"]} x {summary["sample_gvid"]["height"]}</div></div>
    <div class="card"><div class="k">Frames</div><div class="v">{summary["sample_gvid"]["frame_count"]}</div></div>
    <div class="card"><div class="k">Bench wall fps</div><div class="v">{summary["bench_wall_fps"]}</div></div>
    <div class="card"><div class="k">Receipt role</div><div class="v">{summary["handoff_target_role"]}</div></div>
  </section>
  <h2>Product Pillars</h2>
  <table><thead><tr><th>pillar</th><th>status</th><th>what this bundle says</th><th>open gate</th></tr></thead><tbody>{pillars}</tbody></table>
  <h2>Checks</h2>
  <table><thead><tr><th>check</th><th>passed</th><th>detail</th></tr></thead><tbody>{checks}</tbody></table>
  <h2>Blockers</h2>
  <section class="panel"><ul>{blockers}</ul></section>
  <p class="meta">Generated {html.escape(data["created_utc"])}. Manifest: {html.escape(data["manifest"])}. JSON: {html.escape(str(out_json))}.</p>
</main>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--output-dir", type=Path, default=None)
    args = ap.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        output_dir = DEFAULT_EXTERNAL / "artifacts" / f"gopro_mission1_intake_audit_{time.strftime('%Y%m%d', time.gmtime())}"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        data = build_audit(args.manifest)
    except Exception as exc:
        print(f"build_gopro_mission1_intake_audit: {exc}", file=sys.stderr)
        return 1

    out_json = output_dir / "intake_audit.json"
    out_html = output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, out_json), encoding="utf-8")
    print(out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
