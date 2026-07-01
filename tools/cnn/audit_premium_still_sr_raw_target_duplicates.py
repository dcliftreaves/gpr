#!/usr/bin/env python3
"""Audit duplicate raw-domain targets across premium still-SR EV rows.

The raw-CFA residual target NPZ can contain multiple rendered exposure rows for
the same scene/crop. This audit checks whether the raw-domain arrays actually
change across those EV rows. If they do not, raw-domain model training should
not treat the row count as independent raw supervision.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_raw_target_duplicate_audit.v1"
RAW_ARRAYS = ("candidate_raw_cfa4", "candidate_raw_hf_cfa4", "raw_hf_residual_cfa4", "source_raw_hf_cfa4")
REVIEW_ARRAYS = ("render_hf_residual_y",)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "median": 0.0, "mean": 0.0, "max": 0.0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "min": float(arr.min()),
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "max": float(arr.max()),
    }


def load_meta(z: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    rows = json.loads(str(z["meta"]))
    if not isinstance(rows, list):
        raise ValueError("target meta must be a JSON list")
    return [row if isinstance(row, dict) else {} for row in rows]


def diff_summary(arr: np.ndarray, indices: list[int]) -> dict[str, float]:
    if len(indices) < 2:
        return {"pair_count": 0, "max_abs_diff": 0.0, "mean_abs_diff": 0.0}
    ref = arr[indices[0]].astype(np.float32, copy=False)
    maxes: list[float] = []
    maes: list[float] = []
    for idx in indices[1:]:
        other = arr[idx].astype(np.float32, copy=False)
        diff = np.abs(ref - other)
        maxes.append(float(np.max(diff)))
        maes.append(float(np.mean(diff)))
    return {
        "pair_count": len(indices) - 1,
        "max_abs_diff": float(max(maxes)) if maxes else 0.0,
        "mean_abs_diff": float(np.mean(maes)) if maes else 0.0,
    }


def build_audit(args: argparse.Namespace) -> dict[str, Any]:
    with np.load(args.targets, allow_pickle=False) as z:
        rows = load_meta(z)
        missing = [name for name in (*RAW_ARRAYS, *REVIEW_ARRAYS) if name not in z.files]
        if missing:
            raise ValueError(f"target NPZ is missing required arrays: {missing}")
        arrays = {name: z[name] for name in (*RAW_ARRAYS, *REVIEW_ARRAYS)}
        groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(rows):
            groups[(str(row.get("scene_id") or ""), str(row.get("crop") or ""))].append(idx)

        group_rows: list[dict[str, Any]] = []
        duplicate_raw_groups = 0
        varying_render_groups = 0
        ev_multi_groups = 0
        for (scene, crop), indices in sorted(groups.items()):
            evs = [rows[idx].get("ev") for idx in indices]
            if len(indices) > 1:
                ev_multi_groups += 1
            raw_diffs = {name: diff_summary(arrays[name], indices) for name in RAW_ARRAYS}
            review_diffs = {name: diff_summary(arrays[name], indices) for name in REVIEW_ARRAYS}
            raw_max = max(float(row["max_abs_diff"]) for row in raw_diffs.values())
            render_max = max(float(row["max_abs_diff"]) for row in review_diffs.values())
            if len(indices) > 1 and raw_max <= float(args.raw_duplicate_epsilon):
                duplicate_raw_groups += 1
            if len(indices) > 1 and render_max > float(args.render_vary_epsilon):
                varying_render_groups += 1
            group_rows.append(
                {
                    "scene_id": scene,
                    "crop": crop,
                    "row_indices": indices,
                    "row_count": len(indices),
                    "evs": evs,
                    "raw_max_abs_diff": raw_max,
                    "render_max_abs_diff": render_max,
                    "raw_diffs": raw_diffs,
                    "review_diffs": review_diffs,
                }
            )

    row_count = len(rows)
    unique_scene_crop_count = len(groups)
    duplicate_factor = float(row_count / max(unique_scene_crop_count, 1))
    production_ready = duplicate_factor <= 1.05
    interpretation = (
        "Raw-domain arrays are duplicated across EV rows while rendered review targets vary. "
        "Raw-CFA residual training and metrics should report unique scene/crop counts or deduplicate raw rows; "
        "the rendered EV rows are still useful for review, but they are not independent raw supervision."
        if duplicate_raw_groups and varying_render_groups
        else "The raw-domain target rows are mostly unique across EV groups."
    )
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_npz": str(args.targets),
        "target_npz_sha256": sha256_file(args.targets),
        "production_ready": production_ready,
        "thresholds": {
            "raw_duplicate_epsilon": float(args.raw_duplicate_epsilon),
            "render_vary_epsilon": float(args.render_vary_epsilon),
        },
        "summary": {
            "row_count": row_count,
            "unique_scene_crop_count": unique_scene_crop_count,
            "duplicate_factor": duplicate_factor,
            "ev_multi_group_count": ev_multi_groups,
            "raw_duplicate_ev_group_count": duplicate_raw_groups,
            "render_varying_ev_group_count": varying_render_groups,
            "raw_max_abs_diff": stats([float(row["raw_max_abs_diff"]) for row in group_rows]),
            "render_max_abs_diff": stats([float(row["render_max_abs_diff"]) for row in group_rows]),
        },
        "interpretation": interpretation,
        "groups": group_rows,
    }


def render_html(payload: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['scene_id']))}</td>"
        f"<td>{html.escape(str(row['crop']))}</td>"
        f"<td>{int(row['row_count'])}</td>"
        f"<td>{html.escape(str(row['evs']))}</td>"
        f"<td>{float(row['raw_max_abs_diff']):.6g}</td>"
        f"<td>{float(row['render_max_abs_diff']):.6g}</td>"
        "</tr>"
        for row in payload["groups"][:120]
    )
    summary = payload["summary"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Raw Target Duplicate Audit</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #131820; background: #f7f8fa; }}
main {{ max-width: 1180px; margin: 0 auto; }}
h1 {{ font-size: 32px; margin: 0 0 8px; letter-spacing: 0; }}
.sub {{ color: #5b6673; max-width: 900px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 20px 0; }}
.card {{ background: white; border: 1px solid #dde3e9; border-radius: 8px; padding: 14px; }}
.label {{ color: #5b6673; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 26px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dde3e9; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #edf1f4; color: #4d5965; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
</style></head><body><main>
<h1>Premium Still-SR Raw Target Duplicate Audit</h1>
<p class="sub">Groups the raw-CFA residual target by scene/crop and compares raw-domain arrays across EV rows. Rendered HF review variation is reported separately.</p>
<div class="grid">
  <section class="card"><div class="label">Production ready</div><div class="value">{str(payload['production_ready']).lower()}</div></section>
  <section class="card"><div class="label">Rows</div><div class="value">{summary['row_count']}</div></section>
  <section class="card"><div class="label">Unique scene/crop</div><div class="value">{summary['unique_scene_crop_count']}</div></section>
  <section class="card"><div class="label">Duplicate factor</div><div class="value">{summary['duplicate_factor']:.2f}x</div></section>
  <section class="card"><div class="label">Raw duplicate EV groups</div><div class="value">{summary['raw_duplicate_ev_group_count']}</div></section>
  <section class="card"><div class="label">Rendered varying EV groups</div><div class="value">{summary['render_varying_ev_group_count']}</div></section>
</div>
<h2>Interpretation</h2>
<p>{html.escape(payload['interpretation'])}</p>
<h2>Groups</h2>
<table><tr><th>scene</th><th>crop</th><th>rows</th><th>EVs</th><th>raw max abs diff</th><th>render max abs diff</th></tr>{rows}</table>
</main></body></html>
"""


def run(args: argparse.Namespace) -> dict[str, Any]:
    payload = build_audit(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "raw_target_duplicate_audit.json"
    html_path = args.output_dir / "index.html"
    payload["artifacts"] = {"receipt": str(json_path), "dashboard": str(html_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")
    print(html_path)
    return payload


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--raw-duplicate-epsilon", type=float, default=0.0)
    ap.add_argument("--render-vary-epsilon", type=float, default=1.0e-6)
    return ap.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
