#!/usr/bin/env python3
"""Deduplicate premium still-SR raw-CFA targets across rendered EV rows.

The raw-CFA residual target can contain multiple rendered exposure rows for the
same scene/crop. Those rows are useful for rendered review, but they are not
independent raw-domain supervision when the raw arrays are identical. This tool
collapses those groups into one raw row while retaining rendered-review EV
metadata in the row sidecar.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np


SCHEMA = "gpr.premium_still_sr_raw_cfa_residual_targets_dedup.v1"
RAW_ARRAYS = ("candidate_raw_cfa4", "candidate_raw_hf_cfa4", "raw_hf_residual_cfa4", "source_raw_hf_cfa4")
REVIEW_ARRAYS = ("render_hf_residual_y",)
CFA_PHASES = ("RGGB", "GBRG", "GRBG", "BGGR", "unknown")


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
        "mean": float(arr.mean()),
        "max": float(arr.max()),
    }


def load_meta(z: np.lib.npyio.NpzFile) -> list[dict[str, Any]]:
    rows = json.loads(str(z["meta"]))
    if not isinstance(rows, list):
        raise ValueError("target meta must be a JSON list")
    return [row if isinstance(row, dict) else {} for row in rows]


def normalize_cfa_phase(value: Any) -> str:
    if value is None:
        return "unknown"
    text = "".join(ch for ch in str(value).upper() if ch in {"R", "G", "B"})
    return text if text in CFA_PHASES[:-1] else "unknown"


def group_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return the raw-supervision key.

    Scene/crop is the human-facing grouping. Source and candidate paths are
    included so two unrelated target builds cannot accidentally collapse rows
    that share a label.
    """

    return (
        str(row.get("scene_id") or ""),
        str(row.get("crop") or ""),
        str(row.get("source_dng") or ""),
        str(row.get("candidate_raw") or ""),
    )


def raw_diff(arr: np.ndarray, indices: list[int]) -> float:
    if len(indices) < 2:
        return 0.0
    ref = arr[indices[0]].astype(np.float32, copy=False)
    max_abs = 0.0
    for idx in indices[1:]:
        diff = np.max(np.abs(ref - arr[idx].astype(np.float32, copy=False)))
        max_abs = max(max_abs, float(diff))
    return max_abs


def review_diff(arr: np.ndarray, indices: list[int]) -> float:
    if len(indices) < 2:
        return 0.0
    ref = arr[indices[0]].astype(np.float32, copy=False)
    max_abs = 0.0
    for idx in indices[1:]:
        diff = np.max(np.abs(ref - arr[idx].astype(np.float32, copy=False)))
        max_abs = max(max_abs, float(diff))
    return max_abs


def representative_meta(rows: list[dict[str, Any]], indices: list[int], raw_max: float, render_max: float) -> dict[str, Any]:
    first = dict(rows[indices[0]])
    review_rows = [rows[idx] for idx in indices]
    evs: list[float] = []
    for row in review_rows:
        try:
            evs.append(float(row.get("ev", 0.0)))
        except (TypeError, ValueError):
            evs.append(0.0)
    first.update(
        {
            "raw_deduplicated": True,
            "raw_deduplicated_row_count": len(indices),
            "raw_deduplicated_source_indices": indices,
            "raw_deduplicated_review_evs": evs,
            "raw_deduplicated_policy": "one_raw_row_per_scene_crop_source_candidate",
            "raw_deduplicated_render_policy": "mean_render_hf_residual_y_for_review_only",
            "raw_deduplicated_raw_max_abs_diff": raw_max,
            "raw_deduplicated_render_max_abs_diff": render_max,
            "raw_deduplicated_review_rows": [
                {
                    "target_index": int(idx),
                    "scene_id": rows[idx].get("scene_id"),
                    "crop": rows[idx].get("crop"),
                    "ev": rows[idx].get("ev"),
                    "render_hf_residual_y_abs_mean": rows[idx].get("render_hf_residual_y_abs_mean"),
                }
                for idx in indices
            ],
        }
    )
    return first


def build(args: argparse.Namespace) -> dict[str, Any]:
    with np.load(args.targets, allow_pickle=False) as z:
        missing = [name for name in (*RAW_ARRAYS, *REVIEW_ARRAYS, "meta") if name not in z.files]
        if missing:
            raise ValueError(f"target NPZ is missing required arrays: {missing}")
        rows = load_meta(z)
        arrays = {name: z[name] for name in (*RAW_ARRAYS, *REVIEW_ARRAYS)}
        groups: dict[tuple[str, str, str, str], list[int]] = defaultdict(list)
        for idx, row in enumerate(rows):
            groups[group_key(row)].append(idx)

        out_arrays: dict[str, list[np.ndarray]] = {name: [] for name in (*RAW_ARRAYS, *REVIEW_ARRAYS)}
        out_rows: list[dict[str, Any]] = []
        group_summaries: list[dict[str, Any]] = []
        raw_conflicts: list[dict[str, Any]] = []

        for key, indices in sorted(groups.items()):
            raw_max_by_array = {name: raw_diff(arrays[name], indices) for name in RAW_ARRAYS}
            render_max_by_array = {name: review_diff(arrays[name], indices) for name in REVIEW_ARRAYS}
            raw_max = max(raw_max_by_array.values())
            render_max = max(render_max_by_array.values())
            if raw_max > float(args.raw_epsilon):
                raw_conflicts.append(
                    {
                        "group_key": key,
                        "row_indices": indices,
                        "raw_max_abs_diff": raw_max,
                        "raw_max_by_array": raw_max_by_array,
                    }
                )
                if not args.allow_raw_conflicts:
                    continue

            first_idx = indices[0]
            for name in RAW_ARRAYS:
                out_arrays[name].append(arrays[name][first_idx])
            for name in REVIEW_ARRAYS:
                out_arrays[name].append(np.mean(arrays[name][indices].astype(np.float32), axis=0).astype(arrays[name].dtype))
            representative = representative_meta(rows, indices, raw_max, render_max)
            out_rows.append(representative)
            group_summaries.append(
                {
                    "scene_id": key[0],
                    "crop": key[1],
                    "cfa_phase": representative.get("cfa_phase"),
                    "cfa_phase_source": representative.get("cfa_phase_source"),
                    "row_indices": indices,
                    "source_row_count": len(indices),
                    "raw_max_abs_diff": raw_max,
                    "render_max_abs_diff": render_max,
                    "raw_max_by_array": raw_max_by_array,
                    "render_max_by_array": render_max_by_array,
                }
            )

    if raw_conflicts and not args.allow_raw_conflicts:
        raise ValueError(f"raw arrays differ within {len(raw_conflicts)} dedupe group(s); use --allow-raw-conflicts to keep first rows")
    if not out_rows:
        raise ValueError("deduplication produced no rows")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    npz_path = args.output_dir / "raw_cfa_residual_targets_dedup.npz"
    np.savez_compressed(
        npz_path,
        **{name: np.stack(values, axis=0).astype(arrays[name].dtype) for name, values in out_arrays.items()},
        meta=np.asarray(json.dumps(out_rows, sort_keys=True)),
    )

    row_count = len(rows)
    dedup_row_count = len(out_rows)
    duplicate_factor = float(row_count / max(dedup_row_count, 1))
    cfa_counts = Counter(normalize_cfa_phase(row.get("cfa_phase")) for row in out_rows)
    cfa_source_counts = Counter(str(row.get("cfa_phase_source") or "unknown") for row in out_rows)
    payload = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_npz": str(args.targets),
        "source_npz_sha256": sha256_file(args.targets),
        "output_npz": str(npz_path),
        "output_npz_sha256": sha256_file(npz_path),
        "production_ready": not raw_conflicts,
        "policy": {
            "raw_group_key": "scene_id + crop + source_dng + candidate_raw",
            "raw_arrays": list(RAW_ARRAYS),
            "review_arrays": list(REVIEW_ARRAYS),
            "render_review_rows_are_averaged": True,
            "render_review_rows_are_not_independent_raw_supervision": True,
            "raw_conflict_policy": "keep_first" if args.allow_raw_conflicts else "fail",
        },
        "thresholds": {"raw_epsilon": float(args.raw_epsilon)},
        "summary": {
            "source_row_count": row_count,
            "deduplicated_row_count": dedup_row_count,
            "duplicate_factor": duplicate_factor,
            "raw_conflict_group_count": len(raw_conflicts),
            "multi_row_group_count": sum(1 for row in group_summaries if row["source_row_count"] > 1),
            "cfa_phase_counts": {phase: int(cfa_counts.get(phase, 0)) for phase in CFA_PHASES},
            "cfa_phase_source_counts": dict(sorted(cfa_source_counts.items())),
            "cfa_phase_known_row_count": int(sum(cfa_counts.get(phase, 0) for phase in CFA_PHASES[:-1])),
            "raw_max_abs_diff": stats([float(row["raw_max_abs_diff"]) for row in group_summaries]),
            "render_max_abs_diff": stats([float(row["render_max_abs_diff"]) for row in group_summaries]),
        },
        "raw_conflicts": raw_conflicts,
        "groups": group_summaries,
    }
    json_path = args.output_dir / "raw_cfa_residual_targets_dedup.json"
    html_path = args.output_dir / "index.html"
    payload["artifacts"] = {"receipt": str(json_path), "dashboard": str(html_path)}
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(payload), encoding="utf-8")
    print(html_path)
    return payload


def render_html(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['scene_id']))}</td>"
        f"<td>{html.escape(str(row['crop']))}</td>"
        f"<td>{html.escape(str(row.get('cfa_phase') or 'unknown'))}</td>"
        f"<td>{int(row['source_row_count'])}</td>"
        f"<td>{float(row['raw_max_abs_diff']):.6g}</td>"
        f"<td>{float(row['render_max_abs_diff']):.6g}</td>"
        f"<td>{html.escape(str(row['row_indices']))}</td>"
        "</tr>"
        for row in payload["groups"][:120]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Premium Still-SR Deduplicated Raw Targets</title>
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
<h1>Premium Still-SR Deduplicated Raw Targets</h1>
<p class="sub">One raw-supervision row per scene/crop/source/candidate group. Rendered EV rows are averaged for review only and preserved in metadata.</p>
<div class="grid">
  <section class="card"><div class="label">Production ready</div><div class="value">{str(payload['production_ready']).lower()}</div></section>
  <section class="card"><div class="label">Source rows</div><div class="value">{summary['source_row_count']}</div></section>
  <section class="card"><div class="label">Dedup rows</div><div class="value">{summary['deduplicated_row_count']}</div></section>
  <section class="card"><div class="label">Duplicate factor</div><div class="value">{summary['duplicate_factor']:.2f}x</div></section>
  <section class="card"><div class="label">Raw conflicts</div><div class="value">{summary['raw_conflict_group_count']}</div></section>
  <section class="card"><div class="label">Multi-row groups</div><div class="value">{summary['multi_row_group_count']}</div></section>
  <section class="card"><div class="label">Known CFA rows</div><div class="value">{summary['cfa_phase_known_row_count']}</div></section>
</div>
<h2>CFA Phase Coverage</h2>
<p class="sub">{html.escape(json.dumps(summary['cfa_phase_counts'], sort_keys=True))}</p>
<h2>Groups</h2>
<table><tr><th>scene</th><th>crop</th><th>CFA</th><th>source rows</th><th>raw max abs diff</th><th>render max abs diff</th><th>indices</th></tr>{rows}</table>
</main></body></html>
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--raw-epsilon", type=float, default=0.0)
    ap.add_argument("--allow-raw-conflicts", action="store_true")
    return ap.parse_args()


def main() -> int:
    build(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
