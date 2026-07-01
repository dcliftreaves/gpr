#!/usr/bin/env python3
"""Audit Mission/Z8 SR rows where PSF detail gains trade off against gradients."""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_video_psf_gradient_detail_blocker_audit.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_BASE = (
    "artifacts/raw_video_psf_detail_metrics_fullframe_rerun_20260701/"
    "mission42_baseline_fullframe/summary.json"
)
DEFAULT_CANDIDATE = (
    "artifacts/raw_video_psf_detail_metrics_fullframe_rerun_20260701/"
    "mission42_candidate_fullframe/summary.json"
)


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def file_sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows_by_image(summary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = summary.get("images")
    if not isinstance(rows, list):
        raise ValueError("summary must contain an images list")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("image"):
            out[str(row["image"])] = row
    return out


def f(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"row {row.get('image')} missing numeric {key}")
    return float(value)


def build_audit(
    *,
    external_root: Path,
    baseline_summary_path: Path,
    candidate_summary_path: Path,
    created_utc: str | None = None,
) -> dict[str, Any]:
    baseline = load_json(baseline_summary_path)
    candidate = load_json(candidate_summary_path)
    base_rows = rows_by_image(baseline)
    cand_rows = rows_by_image(candidate)
    shared = sorted(set(base_rows) & set(cand_rows))
    per_image: list[dict[str, Any]] = []
    for image in shared:
        b = base_rows[image]
        c = cand_rows[image]
        row = {
            "image": image,
            "baseline_gradient_pct": f(b, "gradient_mae_improvement_pct"),
            "candidate_gradient_pct": f(c, "gradient_mae_improvement_pct"),
            "baseline_same_cell_detail_pct": f(b, "same_cell_detail_mae_improvement_pct"),
            "candidate_same_cell_detail_pct": f(c, "same_cell_detail_mae_improvement_pct"),
            "baseline_same_cell_fine_detail_pct": f(b, "same_cell_fine_detail_mae_improvement_pct"),
            "candidate_same_cell_fine_detail_pct": f(c, "same_cell_fine_detail_mae_improvement_pct"),
            "baseline_rmse_pct": f(b, "rmse_improvement_pct"),
            "candidate_rmse_pct": f(c, "rmse_improvement_pct"),
            "candidate_contact_sheet": c.get("contact_sheet"),
            "baseline_contact_sheet": b.get("contact_sheet"),
        }
        row["delta_gradient_pct"] = row["candidate_gradient_pct"] - row["baseline_gradient_pct"]
        row["delta_same_cell_detail_pct"] = (
            row["candidate_same_cell_detail_pct"] - row["baseline_same_cell_detail_pct"]
        )
        row["delta_same_cell_fine_detail_pct"] = (
            row["candidate_same_cell_fine_detail_pct"] - row["baseline_same_cell_fine_detail_pct"]
        )
        row["delta_rmse_pct"] = row["candidate_rmse_pct"] - row["baseline_rmse_pct"]
        row["gradient_regressed"] = row["delta_gradient_pct"] < 0.0
        row["same_cell_detail_regressed"] = row["delta_same_cell_detail_pct"] < 0.0
        row["combined_blocker"] = row["gradient_regressed"] and row["same_cell_detail_regressed"]
        per_image.append(row)

    blockers = [row for row in per_image if row["combined_blocker"]]
    gradient_regressions = [row for row in per_image if row["gradient_regressed"]]
    detail_regressions = [row for row in per_image if row["same_cell_detail_regressed"]]
    blockers_sorted = sorted(blockers, key=lambda row: (row["delta_gradient_pct"], row["delta_same_cell_detail_pct"]))
    return {
        "schema": SCHEMA,
        "created_utc": created_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "baseline_summary": {
            "path": baseline_summary_path.as_posix(),
            "sha256": file_sha256(baseline_summary_path),
            "image_count": baseline.get("image_count"),
        },
        "candidate_summary": {
            "path": candidate_summary_path.as_posix(),
            "sha256": file_sha256(candidate_summary_path),
            "image_count": candidate.get("image_count"),
        },
        "metrics": {
            "shared_image_count": len(shared),
            "gradient_regression_count": len(gradient_regressions),
            "same_cell_detail_regression_count": len(detail_regressions),
            "combined_gradient_detail_regression_count": len(blockers),
            "candidate_promotable_by_gradient_detail": len(blockers) == 0,
            "worst_gradient_delta_pct": min((row["delta_gradient_pct"] for row in per_image), default=0.0),
            "worst_same_cell_detail_delta_pct": min(
                (row["delta_same_cell_detail_pct"] for row in per_image), default=0.0
            ),
        },
        "worst_blockers": blockers_sorted[:8],
        "per_image": sorted(per_image, key=lambda row: row["delta_gradient_pct"]),
        "production_status": (
            "candidate_preserves_gradient_and_detail"
            if not blockers
            else "blocked_by_mission_gradient_detail_regressions"
        ),
        "next_actions": [
            "Build the next raw-video SR candidate around the combined blocker rows, starting with GP017346 and GP017600.",
            "Keep the current same-cell detail median gains, but add a hard-row gradient floor objective or sampler.",
            "Re-run the PSF-detail-aware scoreboard and promote only when Mission42 and Z8 rows clear RMSE, gradient, and same-cell detail gates.",
        ],
    }


def render_html(audit: dict[str, Any]) -> str:
    metric_rows = "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in audit["metrics"].items()
    )
    blocker_rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['image'])}</td>"
        f"<td>{row['delta_gradient_pct']:.3f}</td>"
        f"<td>{row['delta_same_cell_detail_pct']:.3f}</td>"
        f"<td>{row['delta_rmse_pct']:.3f}</td>"
        f"<td><code>{html.escape(str(row.get('candidate_contact_sheet')))}</code></td>"
        "</tr>"
        for row in audit["worst_blockers"]
    )
    action_rows = "".join(f"<li>{html.escape(item)}</li>" for item in audit["next_actions"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Raw Video PSF Gradient/Detail Blocker Audit</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#f6f8fa;color:#1f2328}}
main{{max-width:1180px;margin:0 auto}}table{{border-collapse:collapse;width:100%;background:white;margin-top:12px}}
td,th{{border:1px solid #d0d7de;padding:8px;text-align:left;vertical-align:top}}code{{color:#0550ae;font-size:12px}}
.status{{font-size:28px;font-weight:700;margin:16px 0;color:#9a3412}}
</style></head><body><main>
<h1>Raw Video PSF Gradient/Detail Blocker Audit</h1>
<p>This audit compares metric-bearing Mission42 baseline and candidate summaries and identifies rows where the candidate regresses both gradient and same-cell Bayer detail.</p>
<div class="status">{html.escape(audit['production_status'])}</div>
<h2>Metrics</h2><table>{metric_rows}</table>
<h2>Worst Combined Blockers</h2>
<table><tr><th>image</th><th>delta gradient</th><th>delta same-cell detail</th><th>delta RMSE</th><th>candidate contact</th></tr>{blocker_rows}</table>
<h2>Next Actions</h2><ul>{action_rows}</ul>
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--baseline-summary", default=DEFAULT_BASE)
    ap.add_argument("--candidate-summary", default=DEFAULT_CANDIDATE)
    ap.add_argument("--created-utc")
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    audit = build_audit(
        external_root=args.external_root,
        baseline_summary_path=resolve(args.external_root, args.baseline_summary),
        candidate_summary_path=resolve(args.external_root, args.candidate_summary),
        created_utc=args.created_utc,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "gradient_detail_blocker_audit.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(audit), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
