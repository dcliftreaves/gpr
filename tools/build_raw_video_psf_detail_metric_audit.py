#!/usr/bin/env python3
"""Audit whether raw-video SR summaries carry PSF/detail metrics.

The PSF-aware video pillar should not promote a candidate from RMSE/gradient
alone. This audit checks that Mission42 and Z8 all24 full-frame summaries
carry explicit same-cell Bayer fine-detail metrics before a PSF-conditioned
replacement can be claimed.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_video_psf_detail_metric_audit.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_SCOREBOARD = "artifacts/raw_video_sr_candidate_scoreboard_20260701/scoreboard.json"
REQUIRED_METRIC_KEYS = (
    "same_cell_detail_mae_improvement_pct",
    "same_cell_fine_detail_mae_improvement_pct",
    "cfa_plane_detail_mae_improvement_pct",
)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def resolve(root: Path, value: str | Path | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def file_sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def nested_has_metric(obj: Any, key: str) -> bool:
    if isinstance(obj, dict):
        if key in obj:
            return True
        return any(nested_has_metric(value, key) for value in obj.values())
    if isinstance(obj, list):
        return any(nested_has_metric(value, key) for value in obj)
    return False


def summary_audit(label: str, path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "label": label,
            "path": None,
            "exists": False,
            "ready": False,
            "missing_metric_keys": list(REQUIRED_METRIC_KEYS),
            "image_count": 0,
            "sha256": None,
        }
    if not path.exists():
        return {
            "label": label,
            "path": path.as_posix(),
            "exists": False,
            "ready": False,
            "missing_metric_keys": list(REQUIRED_METRIC_KEYS),
            "image_count": 0,
            "sha256": None,
        }
    data = load_json(path)
    missing = [key for key in REQUIRED_METRIC_KEYS if not nested_has_metric(data, key)]
    return {
        "label": label,
        "path": path.as_posix(),
        "exists": True,
        "schema": data.get("schema"),
        "ready": not missing,
        "missing_metric_keys": missing,
        "image_count": int(data.get("image_count") or 0),
        "sha256": file_sha256(path),
    }


def summaries_from_scoreboard(scoreboard: dict[str, Any]) -> dict[str, str | None]:
    best = scoreboard.get("best_candidate") if isinstance(scoreboard.get("best_candidate"), dict) else {}
    mission = best.get("mission") if isinstance(best.get("mission"), dict) else {}
    z8 = best.get("z8") if isinstance(best.get("z8"), dict) else {}
    return {
        "mission_candidate": mission.get("candidate_summary"),
        "mission_baseline": mission.get("baseline_summary"),
        "z8_candidate": z8.get("candidate_summary"),
        "z8_baseline": z8.get("baseline_summary"),
    }


def build_audit(
    *,
    external_root: Path,
    scoreboard_path: Path,
    mission_candidate: Path | None,
    mission_baseline: Path | None,
    z8_candidate: Path | None,
    z8_baseline: Path | None,
    created_utc: str | None = None,
) -> dict[str, Any]:
    scoreboard = load_json(scoreboard_path)
    derived = summaries_from_scoreboard(scoreboard)
    mission_candidate = mission_candidate or resolve(external_root, derived["mission_candidate"])
    mission_baseline = mission_baseline or resolve(external_root, derived["mission_baseline"])
    z8_candidate = z8_candidate or resolve(external_root, derived["z8_candidate"])
    z8_baseline = z8_baseline or resolve(external_root, derived["z8_baseline"])

    summaries = [
        summary_audit("mission_candidate", mission_candidate),
        summary_audit("mission_baseline", mission_baseline),
        summary_audit("z8_candidate", z8_candidate),
        summary_audit("z8_baseline", z8_baseline),
    ]
    current_metric_ready = all(row["ready"] for row in summaries)
    coverage_ready = (
        summaries[0]["image_count"] >= 42
        and summaries[1]["image_count"] >= 42
        and summaries[2]["image_count"] >= 24
        and summaries[3]["image_count"] >= 24
    )
    missing_by_summary = {
        row["label"]: row["missing_metric_keys"]
        for row in summaries
        if row["missing_metric_keys"]
    }
    return {
        "schema": SCHEMA,
        "created_utc": created_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "scoreboard": {
            "path": scoreboard_path.as_posix(),
            "sha256": file_sha256(scoreboard_path),
            "decision_count": scoreboard.get("decision_count"),
            "promotable_row_count": scoreboard.get("promotable_row_count"),
            "best_candidate_experiment": (
                scoreboard.get("best_candidate", {}).get("experiment")
                if isinstance(scoreboard.get("best_candidate"), dict)
                else None
            ),
        },
        "required_metric_keys": list(REQUIRED_METRIC_KEYS),
        "summary_audits": summaries,
        "metrics": {
            "summary_count": len(summaries),
            "ready_summary_count": sum(1 for row in summaries if row["ready"]),
            "missing_summary_count": sum(1 for row in summaries if not row["ready"]),
            "mission_candidate_image_count": summaries[0]["image_count"],
            "z8_candidate_image_count": summaries[2]["image_count"],
            "coverage_ready": coverage_ready,
            "same_cell_detail_metric_ready": current_metric_ready,
            "psf_detail_gate_ready": coverage_ready and current_metric_ready,
        },
        "missing_by_summary": missing_by_summary,
        "production_status": (
            "psf_detail_metrics_present"
            if coverage_ready and current_metric_ready
            else "blocked_missing_same_cell_detail_metrics"
        ),
        "next_actions": [
            "Add same-cell Bayer detail and fine-detail metrics to the full-frame Mission42 and Z8 all24 evaluation summaries.",
            "Compare those metrics for the approved baseline and every PSF-conditioned candidate before promotion.",
            "Keep modeled-PSF experiments non-production until controlled native high/low pairs provide a stable PSF kernel.",
        ],
    }


def render_html(audit: dict[str, Any]) -> str:
    metric_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in audit["metrics"].items()
    )
    summary_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['label']))}</td>"
        f"<td>{html.escape(str(row['image_count']))}</td>"
        f"<td>{html.escape(str(row['ready']).lower())}</td>"
        f"<td>{html.escape(', '.join(row['missing_metric_keys']) or 'none')}</td>"
        f"<td><code>{html.escape(str(row['path']))}</code></td>"
        "</tr>"
        for row in audit["summary_audits"]
    )
    actions = "".join(f"<li>{html.escape(item)}</li>" for item in audit["next_actions"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Raw Video PSF Detail Metric Audit</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#f6f8fa;color:#1f2328}}
main{{max-width:1180px;margin:0 auto}}table{{border-collapse:collapse;width:100%;background:white;margin-top:12px}}
td,th{{border:1px solid #d0d7de;padding:8px;text-align:left;vertical-align:top}}code{{color:#0550ae}}
.status{{font-size:28px;font-weight:700;margin:16px 0}}.blocked{{color:#9a3412}}.ready{{color:#116329}}
</style></head><body><main>
<h1>Raw Video PSF Detail Metric Audit</h1>
<p>This audit checks whether current Mission42 and Z8 all24 SR summaries include explicit same-cell Bayer fine-detail metrics.</p>
<div class="status {'ready' if audit['metrics']['psf_detail_gate_ready'] else 'blocked'}">{html.escape(audit['production_status'])}</div>
<h2>Metrics</h2><table>{metric_rows}</table>
<h2>Summaries</h2><table><tr><th>summary</th><th>images</th><th>ready</th><th>missing metrics</th><th>path</th></tr>{summary_rows}</table>
<h2>Next Actions</h2><ul>{actions}</ul>
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--scoreboard", default=DEFAULT_SCOREBOARD)
    ap.add_argument("--mission-candidate")
    ap.add_argument("--mission-baseline")
    ap.add_argument("--z8-candidate")
    ap.add_argument("--z8-baseline")
    ap.add_argument("--created-utc")
    ap.add_argument("--output-dir", type=Path, default=None)
    args = ap.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d", time.gmtime())
        output_dir = args.external_root / "artifacts" / f"raw_video_psf_detail_metric_audit_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    audit = build_audit(
        external_root=args.external_root,
        scoreboard_path=resolve(args.external_root, args.scoreboard) or Path(args.scoreboard),
        mission_candidate=resolve(args.external_root, args.mission_candidate),
        mission_baseline=resolve(args.external_root, args.mission_baseline),
        z8_candidate=resolve(args.external_root, args.z8_candidate),
        z8_baseline=resolve(args.external_root, args.z8_baseline),
        created_utc=args.created_utc,
    )
    json_path = output_dir / "raw_video_psf_detail_metric_audit.json"
    html_path = output_dir / "index.html"
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(audit), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
