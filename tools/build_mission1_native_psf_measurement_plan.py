#!/usr/bin/env python3
"""Build the Mission 1 native PSF measurement plan.

The pair inventory answers "do we have plausible native high/low inputs?"
This plan answers "exactly what must be measured next?" without pretending the
measurement already exists.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import time
from pathlib import Path
from typing import Any


DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_NATIVE_PAIR_INVENTORY = "artifacts/mission1_native_psf_pair_inventory_20260630/inventory.json"
DEFAULT_PAIR_DERIVED_PSF = (
    "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/"
    "bayer_resize_psf_receipt.json"
)
SCHEMA = "gpr.mission1_native_psf_measurement_plan.v1"


def resolve_artifact(external_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return external_root / candidate


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bool_at(data: dict[str, Any] | None, keys: list[str], default: bool = False) -> bool:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return bool(cur)


def num_at(data: dict[str, Any] | None, keys: list[str]) -> float | None:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def list_at(data: dict[str, Any] | None, keys: list[str]) -> list[Any]:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return []
        cur = cur[key]
    return list(cur) if isinstance(cur, list) else []


def synthetic_inventory() -> dict[str, Any]:
    pairs = []
    for idx, delta in enumerate((15.0, 17.0, 23.0), start=1):
        pairs.append(
            {
                "low_stem": f"GP_LOW_{idx:02d}",
                "high_stem": f"GP_HIGH_{idx:02d}",
                "time_delta_s": delta,
                "low_iso": 100,
                "high_iso": 100,
                "production_candidate": True,
                "high_raw": {"path": f"/fixtures/GP_HIGH_{idx:02d}.raw", "exists": True, "bytes": 100},
                "low_raw": {"path": f"/fixtures/GP_LOW_{idx:02d}.raw", "exists": True, "bytes": 25},
            }
        )
    return {
        "schema": "gpr.mission1_native_psf_pair_inventory.v1",
        "summary": {
            "candidate_pair_count": 4,
            "decoded_candidate_pair_count": 3,
            "best_pair_count": 3,
            "native_psf_ready": False,
            "production_ready": False,
        },
        "best_pairs_by_low": pairs,
        "candidate_pairs": pairs,
    }


def synthetic_pair_psf() -> dict[str, Any]:
    return {
        "schema": "gpr.bayer_resize_psf_receipt.v1",
        "production_ready": False,
        "dataset": {"pair_count": 1024, "sharp_edge_count": 568, "texture_field_count": 632, "cfa_phases": ["RGGB"]},
        "psf_model": {
            "model_id": "real_pair_same_color_2x_psf_v1",
            "best_candidate_kernel": "same_color_box2",
            "normalized_weights": [0.25, 0.25, 0.25, 0.25],
            "rmse_14bit": 0.3,
        },
        "detail_budget": {
            "fine_share_of_residual_abs": 0.99999,
            "residual_to_target_cell_detail_ratio": 1.00001,
        },
    }


def pair_is_decoded(pair: dict[str, Any]) -> bool:
    return bool(pair.get("production_candidate")) and bool((pair.get("high_raw") or {}).get("exists")) and bool(
        (pair.get("low_raw") or {}).get("exists")
    )


def select_pairs(inventory: dict[str, Any] | None, max_pairs: int) -> list[dict[str, Any]]:
    if not inventory:
        return []
    source = inventory.get("best_pairs_by_low") or inventory.get("candidate_pairs") or []
    pairs = [row for row in source if isinstance(row, dict) and pair_is_decoded(row)]
    pairs.sort(key=lambda row: (float(row.get("time_delta_s") or 1e9), str(row.get("low_stem")), str(row.get("high_stem"))))
    selected = []
    for row in pairs[:max_pairs]:
        selected.append(
            {
                "low_stem": row.get("low_stem"),
                "high_stem": row.get("high_stem"),
                "time_delta_s": row.get("time_delta_s"),
                "low_iso": row.get("low_iso"),
                "high_iso": row.get("high_iso"),
                "high_raw_path": (row.get("high_raw") or {}).get("path"),
                "low_raw_path": (row.get("low_raw") or {}).get("path"),
                "measurement_role": "native high-to-low PSF candidate",
                "status": "selected_for_alignment_and_tile_mining",
            }
        )
    return selected


def build_plan(
    external_root: Path,
    native_pair_inventory_path: Path,
    pair_derived_psf_path: Path,
    max_pairs: int,
    synthetic: bool = False,
) -> dict[str, Any]:
    if synthetic:
        inventory = synthetic_inventory()
        pair_psf = synthetic_pair_psf()
    else:
        inventory = load_json(native_pair_inventory_path)
        pair_psf = load_json(pair_derived_psf_path)

    selected_pairs = select_pairs(inventory, max_pairs=max_pairs)
    native_candidate_pairs = int(num_at(inventory, ["summary", "candidate_pair_count"]) or 0)
    decoded_candidate_pairs = int(num_at(inventory, ["summary", "decoded_candidate_pair_count"]) or 0)
    best_pair_count = int(num_at(inventory, ["summary", "best_pair_count"]) or len(list_at(inventory, ["best_pairs_by_low"])))
    pair_derived_fixtures = int(num_at(pair_psf, ["dataset", "pair_count"]) or 0)
    pair_derived_edges = int(num_at(pair_psf, ["dataset", "sharp_edge_count"]) or 0)
    pair_derived_textures = int(num_at(pair_psf, ["dataset", "texture_field_count"]) or 0)

    plan_ready = len(selected_pairs) >= 3 and decoded_candidate_pairs >= 3 and pair_psf is not None
    stages = [
        {
            "id": "decode_and_normalize_bayer",
            "owner": "measurement",
            "output": "per-pair high/low Bayer planes with dimensions, CFA phase, black level, white level, ISO, and hashes",
            "done_when": "all selected high/low raw paths open and hash to the measurement receipt",
        },
        {
            "id": "scene_vetting",
            "owner": "measurement",
            "output": "downsampled high-vs-low contact sheet and reject list for scene motion/exposure changes",
            "done_when": "at least three pairs remain accepted after visual and metric scene-change checks",
        },
        {
            "id": "phase_correct_alignment",
            "owner": "measurement",
            "output": "integer/subpixel transform, crop window, CFA phase mapping, and residual alignment error per pair",
            "done_when": "edge residual is below the alignment threshold before any PSF fitting",
        },
        {
            "id": "edge_and_texture_tile_mining",
            "owner": "measurement",
            "output": "sharp-edge tiles plus texture-field tiles from aligned high/low pairs",
            "done_when": "tile support covers edges and texture fields across at least three accepted pairs",
        },
        {
            "id": "native_psf_estimation",
            "owner": "measurement",
            "output": "measured Bayer-domain kernel, RGB-preview equivalent kernel, fit error, and receipt hash",
            "done_when": "a native PSF receipt compares measured kernels against the current same-color 2x2 box model",
        },
        {
            "id": "psf_conditioned_sr_gate",
            "owner": "model",
            "output": "4K cleanup and/or 8K SR candidate trained with measured PSF conditioning",
            "done_when": "Mission42 and Z8 all24 gates beat the approved baselines with worst-row visual evidence",
        },
    ]

    acceptance = {
        "minimum_selected_pairs": 3,
        "minimum_accepted_after_scene_vetting": 3,
        "minimum_sharp_edge_tiles": 96,
        "minimum_texture_field_tiles": 96,
        "alignment_required_before_metrics": True,
        "must_compare_to_pair_derived_kernel": True,
        "promotion_requires_mission42_and_z8_all24": True,
        "promotion_requires_gvid_editable_raw_prores_timing_memory_hashes": True,
    }
    blockers = []
    if len(selected_pairs) < acceptance["minimum_selected_pairs"]:
        blockers.append(f"Only {len(selected_pairs)} decoded best native high/low pairs are selected; at least 3 are required.")
    if pair_psf is None:
        blockers.append("The modeled pair-derived PSF/detail receipt is missing, so the native measurement has no current baseline comparison.")
    blockers.extend(
        [
            "No selected pair has been aligned and scene-vetted yet.",
            "No native high-to-low Bayer-domain PSF kernel has been measured yet.",
            "No PSF-conditioned 4K/8K model has been trained and gated against the approved baselines yet.",
        ]
    )

    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "synthetic" if synthetic else "real",
        "external_root": str(external_root),
        "production_ready": False,
        "native_psf_measured": False,
        "measurement_plan_ready": plan_ready,
        "summary": {
            "candidate_pair_count": native_candidate_pairs,
            "decoded_candidate_pair_count": decoded_candidate_pairs,
            "best_pair_count": best_pair_count,
            "selected_pair_count": len(selected_pairs),
            "pair_derived_fixture_count": pair_derived_fixtures,
            "pair_derived_sharp_edge_count": pair_derived_edges,
            "pair_derived_texture_field_count": pair_derived_textures,
            "pair_derived_best_kernel": (pair_psf or {}).get("psf_model", {}).get("best_candidate_kernel"),
            "pair_derived_fine_residual_share": num_at(pair_psf, ["detail_budget", "fine_share_of_residual_abs"]),
        },
        "inputs": [
            {
                "label": "Mission 1 native high/low pair inventory",
                "path": str(native_pair_inventory_path),
                "exists": native_pair_inventory_path.exists() or synthetic,
                "sha256": None if synthetic else file_sha256(native_pair_inventory_path),
                "schema": (inventory or {}).get("schema"),
            },
            {
                "label": "Pair-derived PSF/detail receipt",
                "path": str(pair_derived_psf_path),
                "exists": pair_derived_psf_path.exists() or synthetic,
                "sha256": None if synthetic else file_sha256(pair_derived_psf_path),
                "schema": (pair_psf or {}).get("schema"),
            },
        ],
        "selected_pairs": selected_pairs,
        "measurement_stages": stages,
        "acceptance": acceptance,
        "blockers": blockers,
        "next_actions": [
            "Run the selected pairs through Bayer/RGB alignment and emit per-pair crop transforms.",
            "Mine sharp-edge and texture-field tiles from accepted aligned pairs.",
            "Fit a native Mission 1 high-to-low PSF kernel and compare it to the current same-color 2x2 pair-derived model.",
            "Use the measured kernel as conditioning for the next 4K cleanup / 8K SR candidate gate.",
        ],
    }


def render_html(data: dict[str, Any], out_json: Path) -> str:
    cards = [
        ("Plan ready", str(data["measurement_plan_ready"]).lower()),
        ("Selected pairs", data["summary"]["selected_pair_count"]),
        ("Decoded candidates", data["summary"]["decoded_candidate_pair_count"]),
        ("Pair fixtures", data["summary"]["pair_derived_fixture_count"]),
        ("Current kernel", data["summary"].get("pair_derived_best_kernel") or "missing"),
    ]
    card_html = "\n".join(
        f'<section class="card"><div class="k">{html.escape(str(k))}</div><div class="v">{html.escape(str(v))}</div></section>'
        for k, v in cards
    )
    pair_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(str(row['low_stem']))}</td>"
        f"<td>{html.escape(str(row['high_stem']))}</td>"
        f"<td>{html.escape(str(row.get('time_delta_s')))}</td>"
        f"<td>{html.escape(str(row.get('low_iso')))}</td>"
        f"<td>{html.escape(str(row.get('high_iso')))}</td>"
        f"<td>{html.escape(str(row['status']))}</td>"
        "</tr>"
        for row in data["selected_pairs"]
    )
    stage_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(stage['id'])}</td>"
        f"<td>{html.escape(stage['output'])}</td>"
        f"<td>{html.escape(stage['done_when'])}</td>"
        "</tr>"
        for stage in data["measurement_stages"]
    )
    blockers = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["blockers"])
    actions = "\n".join(f"<li>{html.escape(item)}</li>" for item in data["next_actions"])
    inputs = "\n".join(
        f"""<tr><td>{html.escape(inp["label"])}</td><td class="{'pass' if inp['exists'] else 'fail'}">{str(inp['exists']).lower()}</td><td>{html.escape(str(inp.get("schema") or "missing"))}</td><td>{html.escape(str(inp.get("sha256") or "synthetic"))}</td><td><a href="file://{html.escape(inp["path"])}">{html.escape(inp["path"])}</a></td></tr>"""
        for inp in data["inputs"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mission 1 Native PSF Measurement Plan</title>
  <style>
    body {{ margin: 0; background: #f4f6f7; color: #101820; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 30px; }}
    h1 {{ margin: 0; font-size: 38px; letter-spacing: 0; }}
    h2 {{ margin: 24px 0 10px; }}
    p {{ color: #52606d; max-width: 900px; }}
    a {{ color: #075c9f; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 20px 0; }}
    .card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
    .k {{ color: #53606d; font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .v {{ font-size: 26px; font-weight: 760; margin-top: 4px; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; }}
    th, td {{ padding: 9px; border-bottom: 1px solid #e6ebef; text-align: left; vertical-align: top; }}
    th {{ color: #53606d; font-size: 12px; text-transform: uppercase; }}
    .panel {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 16px; }}
    .pass {{ color: #16794c; font-weight: 760; }}
    .fail {{ color: #a33a32; font-weight: 760; }}
    .meta {{ color: #66727e; font-size: 13px; margin-top: 20px; }}
  </style>
</head>
<body><main>
  <h1>Mission 1 Native PSF Measurement Plan</h1>
  <p>This converts the native high/low pair inventory into an executable measurement protocol. It is still not a measured PSF receipt and does not promote a PSF-conditioned SR replacement.</p>
  <div class="grid">{card_html}</div>
  <h2>Selected Pairs</h2>
  <table><thead><tr><th>low</th><th>high</th><th>delta s</th><th>low ISO</th><th>high ISO</th><th>status</th></tr></thead><tbody>{pair_rows}</tbody></table>
  <h2>Measurement Stages</h2>
  <table><thead><tr><th>stage</th><th>output</th><th>done when</th></tr></thead><tbody>{stage_rows}</tbody></table>
  <h2>Blockers</h2><section class="panel"><ul>{blockers}</ul></section>
  <h2>Next Actions</h2><section class="panel"><ul>{actions}</ul></section>
  <h2>Inputs</h2>
  <table><thead><tr><th>input</th><th>exists</th><th>schema</th><th>sha256</th><th>path</th></tr></thead><tbody>{inputs}</tbody></table>
  <p class="meta">Generated {html.escape(data['created_utc'])}. JSON: {html.escape(str(out_json))}. Mode: {html.escape(data['mode'])}.</p>
</main></body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--native-pair-inventory", default=DEFAULT_NATIVE_PAIR_INVENTORY)
    ap.add_argument("--pair-derived-psf", default=DEFAULT_PAIR_DERIVED_PSF)
    ap.add_argument("--max-pairs", type=int, default=3)
    ap.add_argument("--output-dir", type=Path, default=None)
    ap.add_argument("--synthetic", action="store_true")
    args = ap.parse_args()

    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d", time.gmtime())
        output_dir = args.external_root / "artifacts" / f"mission1_native_psf_measurement_plan_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    native_pair_inventory_path = resolve_artifact(args.external_root, args.native_pair_inventory)
    pair_derived_psf_path = resolve_artifact(args.external_root, args.pair_derived_psf)
    data = build_plan(
        args.external_root,
        native_pair_inventory_path,
        pair_derived_psf_path,
        max_pairs=args.max_pairs,
        synthetic=args.synthetic,
    )

    out_json = output_dir / "measurement_plan.json"
    out_html = output_dir / "index.html"
    out_json.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_html.write_text(render_html(data, out_json), encoding="utf-8")
    print(out_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
