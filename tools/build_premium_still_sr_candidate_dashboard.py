#!/usr/bin/env python3
"""Build a premium still-SR candidate metrics dashboard."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_candidate_dashboard.v1"

DEFAULT_RECEIPTS = [
    "artifacts/premium_still_sr_candidate_smoke_20260629/premium_still_sr_smoke_w24_d4_120.pt.json",
    "artifacts/premium_still_sr_candidate_large_20260629/premium_still_sr_w32_d5_1000_x2dholdout.pt.json",
]


def external_root() -> Path:
    return Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "exists": path.is_file(),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size if path.is_file() else None,
    }


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def row_from_receipt(path: Path) -> dict[str, Any]:
    data = load_json(path)
    checkpoint = Path(str(data.get("checkpoint", "")))
    pairs = Path(str(data.get("pairs", "")))
    best = data.get("best_eval") if isinstance(data.get("best_eval"), dict) else {}
    history = data.get("history") if isinstance(data.get("history"), list) else []
    final = history[-1] if history and isinstance(history[-1], dict) else {}
    best_step = int(best.get("step", 0) or 0)
    final_step = int(final.get("step", 0) or data.get("steps", 0) or 0)
    best_rmse = float(best.get("model_rmse_counts", 0.0) or 0.0)
    final_rmse = float(final.get("model_rmse_counts", best_rmse) or best_rmse)
    return {
        "receipt": artifact_ref(path),
        "checkpoint": artifact_ref(checkpoint),
        "pairs": artifact_ref(pairs),
        "architecture": data.get("architecture"),
        "width": data.get("width"),
        "depth": data.get("depth"),
        "steps": data.get("steps"),
        "holdout_image": data.get("holdout_image"),
        "train_tiles": data.get("train_tiles"),
        "eval_tiles": data.get("eval_tiles_total"),
        "device": data.get("device"),
        "elapsed_s": data.get("elapsed_s"),
        "best": best,
        "final": final,
        "best_step": best_step,
        "final_step": final_step,
        "selected_checkpoint_is_best": bool(best_step) and best_step <= final_step and checkpoint.is_file(),
        "final_regressed_from_best_rmse_counts": final_rmse - best_rmse,
        "production_grade": False,
        "blockers": [
            "raw-domain metrics are tile-level only",
            "no rendered visual dashboard or worst-row crop review",
            "no raw-editor latitude receipt",
            "noise-sidecar policy is not yet active in target construction",
        ],
    }


def build_dashboard(root: Path, receipts: list[Path]) -> dict[str, Any]:
    rows = [row_from_receipt(path if path.is_absolute() else root / path) for path in receipts]
    best_row = max(rows, key=lambda row: float(row["best"].get("rmse_improvement_pct", -1e9) or -1e9)) if rows else None
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": root.as_posix(),
        "rows": rows,
        "best_candidate": best_row,
        "production_ready": False,
        "production_blockers": [
            "candidate improvement is small and not validated on a broad still corpus",
            "rendered dashboard, worst-row visual review, and editor-latitude receipts are missing",
            "camera-noise removal/addback is not yet active in the still-SR target policy",
        ],
    }


def pct(value: Any) -> str:
    return f"{float(value):.4f}%" if isinstance(value, (int, float)) and not isinstance(value, bool) else "n/a"


def num(value: Any, digits: int = 2) -> str:
    return f"{float(value):.{digits}f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else "n/a"


def render_html(data: dict[str, Any]) -> str:
    rows_html = []
    for row in data["rows"]:
        best = row["best"]
        final = row["final"]
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(Path(row['checkpoint']['path']).name)}</td>"
            f"<td>{html.escape(str(row['holdout_image']))}</td>"
            f"<td>{row['train_tiles']}</td>"
            f"<td>{row['eval_tiles']}</td>"
            f"<td>{row['best_step']}</td>"
            f"<td>{pct(best.get('rmse_improvement_pct'))}</td>"
            f"<td>{pct(best.get('mae_improvement_pct'))}</td>"
            f"<td>{num(best.get('model_rmse_counts'))}</td>"
            f"<td>{num(best.get('baseline_rmse_counts'))}</td>"
            f"<td>{num(row['final_regressed_from_best_rmse_counts'])}</td>"
            f"<td>{html.escape(str(row['production_grade']))}</td>"
            "</tr>"
        )
        if final:
            final.setdefault("_unused", None)
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["production_blockers"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Premium Still-SR Candidate Dashboard</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; color: #17202a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 18px 0; }}
    th, td {{ border-bottom: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f4f6f8; }}
    .warn {{ display: inline-block; padding: 6px 10px; background: #fff3cd; border: 1px solid #d7a500; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>Premium Still-SR Candidate Dashboard</h1>
  <p class="warn">Not production-ready: tile-level raw metrics only.</p>
  <table>
    <thead><tr><th>Checkpoint</th><th>Holdout</th><th>Train tiles</th><th>Eval tiles</th><th>Best step</th><th>Best RMSE improvement</th><th>Best MAE improvement</th><th>Model RMSE</th><th>Baseline RMSE</th><th>Final-best RMSE delta</th><th>Production</th></tr></thead>
    <tbody>{''.join(rows_html)}</tbody>
  </table>
  <h2>Production Blockers</h2>
  <ul>{blockers}</ul>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=external_root())
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--receipt", action="append", type=Path)
    args = ap.parse_args()

    receipts = args.receipt or [Path(rel) for rel in DEFAULT_RECEIPTS]
    data = build_dashboard(args.external_root, receipts)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = args.output_dir / "candidate_dashboard.json"
    summary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "index.html").write_text(render_html(data), encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
