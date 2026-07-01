#!/usr/bin/env python3
"""Build the next-experiment contract for raw-video PSF/SR work.

This contract separates useful local PSF/SR experiments from production
promotion. The current modeled-pair PSF receipt is useful for ablations, but
the native Mission 1 high/low kernel is unstable and must not condition a
replacement model until controlled pairs close the measurement gate.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.raw_video_psf_next_experiment_contract.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")
DEFAULT_MODELED_PSF = (
    "artifacts/bayer_resize_psf_from_pairs_xlarge_detail_budget_20260630/"
    "bayer_resize_psf_receipt.json"
)
DEFAULT_NATIVE_STABILITY = (
    "artifacts/mission1_native_psf_kernel_stability_audit_20260630/"
    "kernel_stability_audit.json"
)
DEFAULT_SR_SCOREBOARD = "artifacts/raw_video_sr_candidate_scoreboard_20260630/scoreboard.json"
DEFAULT_GAP_PLAN = "artifacts/raw_video_psf_gap_plan_20260630/raw_video_psf_gap_plan.json"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return data


def resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def num_at(data: dict[str, Any], path: tuple[str, ...], default: float = 0.0) -> float:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return float(cur) if isinstance(cur, (int, float)) and not isinstance(cur, bool) else default


def bool_at(data: dict[str, Any], path: tuple[str, ...], default: bool = False) -> bool:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if isinstance(cur, bool) else default


def build_contract(
    *,
    external_root: Path,
    modeled_psf_path: Path,
    native_stability_path: Path,
    sr_scoreboard_path: Path,
    gap_plan_path: Path,
    created_utc: str | None = None,
) -> dict[str, Any]:
    modeled_psf = load_json(modeled_psf_path)
    native_stability = load_json(native_stability_path)
    sr_scoreboard = load_json(sr_scoreboard_path)
    gap_plan = load_json(gap_plan_path)

    modeled_kernel = modeled_psf.get("psf_model", {}) if isinstance(modeled_psf.get("psf_model"), dict) else {}
    detail_budget = modeled_psf.get("detail_budget", {}) if isinstance(modeled_psf.get("detail_budget"), dict) else {}
    native_summary = (
        native_stability.get("summary", {}) if isinstance(native_stability.get("summary"), dict) else {}
    )
    gap_summary = gap_plan.get("summary", {}) if isinstance(gap_plan.get("summary"), dict) else {}
    scoreboard_best = sr_scoreboard.get("best_candidate") if isinstance(sr_scoreboard.get("best_candidate"), dict) else None

    native_kernel_ready = bool_at(native_stability, ("summary", "native_psf_ready_for_model_conditioning"))
    stable_native_kernel = bool_at(native_stability, ("summary", "combined_kernel_stable_in_source_receipt"))
    promotable_sr_rows = int(num_at(sr_scoreboard, ("promotable_row_count",)))
    modeled_fine_share = num_at(modeled_psf, ("detail_budget", "fine_share_of_residual_abs"))

    local_experiments_allowed = bool(modeled_kernel) and modeled_fine_share > 0.95
    production_ready = bool_at(gap_plan, ("summary", "production_psf_closure_ready"))

    return {
        "schema": SCHEMA,
        "created_utc": created_utc or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "production_ready": production_ready,
        "local_experiments_allowed": local_experiments_allowed,
        "sources": {
            "modeled_psf": modeled_psf_path.as_posix(),
            "native_stability": native_stability_path.as_posix(),
            "sr_scoreboard": sr_scoreboard_path.as_posix(),
            "gap_plan": gap_plan_path.as_posix(),
        },
        "current_state": {
            "modeled_pair_kernel": {
                "best_candidate_kernel": modeled_kernel.get("best_candidate_kernel"),
                "normalized_weights": modeled_kernel.get("normalized_weights"),
                "rmse_14bit": modeled_kernel.get("rmse_14bit"),
                "production_ready": bool(modeled_psf.get("production_ready")),
            },
            "modeled_detail_budget": {
                "fine_share_of_residual_abs": detail_budget.get("fine_share_of_residual_abs"),
                "mid_share_of_residual_abs": detail_budget.get("mid_share_of_residual_abs"),
                "coarse_share_of_residual_abs": detail_budget.get("coarse_share_of_residual_abs"),
                "residual_to_target_cell_detail_ratio": detail_budget.get("residual_to_target_cell_detail_ratio"),
            },
            "native_kernel": {
                "selected_pair_count": native_summary.get("selected_pair_count"),
                "accepted_pair_count": native_summary.get("accepted_pair_count"),
                "rejected_pair_count": native_summary.get("rejected_pair_count"),
                "weight_std_max": native_summary.get("combined_weight_std_max"),
                "weight_mean_min": native_summary.get("combined_weight_mean_min"),
                "accepted_negative_weight_pair_count": native_summary.get("accepted_negative_weight_pair_count"),
                "ready_for_model_conditioning": native_kernel_ready,
                "stable_in_source_receipt": stable_native_kernel,
            },
            "sr_scoreboard": {
                "decision_count": sr_scoreboard.get("decision_count"),
                "promotable_row_count": promotable_sr_rows,
                "best_candidate": scoreboard_best,
            },
            "gap_plan_summary": gap_summary,
        },
        "next_experiment_contract": {
            "recommended_first_local_track": "modeled-PSF same-cell fine-detail ablation",
            "allowed_local_tracks": [
                "Use the modeled same_color_box2 PSF/detail budget as non-production conditioning for 4K cleanup or 8K SR ablations.",
                "Add explicit same-cell fine-detail residual metrics to Mission42 and Z8 all24 gates before changing a registered baseline.",
                "Build a controlled-pair intake validator or dry-run model gate that refuses unstable native kernels.",
            ],
            "do_not_promote_or_repeat_as_production": [
                "Do not condition a production model on the current unstable native Mission 1 kernel.",
                "Do not rerun the same near-time high/low pair fitting and call it closure without controlled pairs.",
                "Do not count crop dashboards, side-by-side videos, or contact sheets as standalone scene-video evidence.",
                "Do not promote historical SR/detail rows that lack both Mission42 and Z8 all24-scale gate coverage.",
                "Do not claim PSF-aware replacement when the output lacks .gvid, editable DNG/GPR, ProRes, timing, memory, config, and hash receipts.",
            ],
            "success_gates": [
                "Native path: at least three controlled high/low pairs, stable nonnegative kernel, source hashes, decoded Bayer hashes, fixed settings, and negative controls.",
                "Modeled-only path: artifact must be explicitly marked non-production and compared against approved 4K cleanup and 8K SR baselines.",
                "Replacement path: Mission42 and Z8 all24 gates improve worst-row RMSE/gradient/detail metrics with no severe visual regressions.",
                "Packaging path: emits .gvid, editable DNG/GPR, ProRes review, timing, memory, checkpoint/config, dashboard, and artifact hash receipts.",
            ],
            "early_reject_if": [
                "Kernel has negative normalized weights or max coefficient std above 0.10.",
                "Mission42 improves but Z8 all24 coverage is missing or regresses.",
                "Improvement only appears in crop-local metrics and not full-frame scene review.",
                "The candidate changes tone/color while chasing PSF/detail metrics.",
                "Runtime or offline throughput/memory receipt is missing for the claimed role.",
            ],
        },
    }


def render_html(contract: dict[str, Any]) -> str:
    state = contract["current_state"]
    model = state["modeled_pair_kernel"]
    detail = state["modeled_detail_budget"]
    native = state["native_kernel"]
    scoreboard = state["sr_scoreboard"]
    next_contract = contract["next_experiment_contract"]

    cards = [
        ("Production ready", contract["production_ready"]),
        ("Local ablations allowed", contract["local_experiments_allowed"]),
        ("Modeled kernel", model.get("best_candidate_kernel")),
        ("Fine residual share", detail.get("fine_share_of_residual_abs")),
        ("Native accepted pairs", native.get("accepted_pair_count")),
        ("Native kernel std max", native.get("weight_std_max")),
        ("Promotable SR rows", scoreboard.get("promotable_row_count")),
    ]
    card_html = "".join(
        "<section class='card'>"
        f"<div class='label'>{html.escape(str(label))}</div>"
        f"<div class='value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )
    lists = []
    for label, key in (
        ("Allowed Local Tracks", "allowed_local_tracks"),
        ("Do Not Promote Or Repeat", "do_not_promote_or_repeat_as_production"),
        ("Success Gates", "success_gates"),
        ("Early Reject If", "early_reject_if"),
    ):
        items = "".join(f"<li>{html.escape(str(item))}</li>" for item in next_contract[key])
        lists.append(f"<section><h2>{html.escape(label)}</h2><ul>{items}</ul></section>")
    sources = "".join(
        f"<tr><td>{html.escape(label)}</td><td><code>{html.escape(path)}</code></td></tr>"
        for label, path in contract["sources"].items()
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Raw Video PSF Next Experiment Contract</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;background:#101214;color:#eceff1}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:18px 0}}
.card{{background:#181b1f;border:1px solid #30363d;border-radius:8px;padding:14px}}
.label{{color:#9aa4ad;font-size:13px}}.value{{font-size:22px;margin-top:6px}}
section{{margin-top:24px}}li{{margin:8px 0}}code{{color:#b6d7ff}}table{{border-collapse:collapse;width:100%}}td{{border-top:1px solid #30363d;padding:8px}}
</style></head><body>
<h1>Raw Video PSF Next Experiment Contract</h1>
<p>This is a local-experiment contract, not a production promotion receipt.</p>
<div class="grid">{card_html}</div>
{''.join(lists)}
<section><h2>Sources</h2><table>{sources}</table></section>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--modeled-psf", type=Path, default=Path(DEFAULT_MODELED_PSF))
    ap.add_argument("--native-stability", type=Path, default=Path(DEFAULT_NATIVE_STABILITY))
    ap.add_argument("--sr-scoreboard", type=Path, default=Path(DEFAULT_SR_SCOREBOARD))
    ap.add_argument("--gap-plan", type=Path, default=Path(DEFAULT_GAP_PLAN))
    ap.add_argument("--created-utc", default=None)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = build_contract(
        external_root=args.external_root,
        modeled_psf_path=resolve(args.external_root, args.modeled_psf),
        native_stability_path=resolve(args.external_root, args.native_stability),
        sr_scoreboard_path=resolve(args.external_root, args.sr_scoreboard),
        gap_plan_path=resolve(args.external_root, args.gap_plan),
        created_utc=args.created_utc,
    )
    json_path = output_dir / "raw_video_psf_next_experiment_contract.json"
    html_path = output_dir / "index.html"
    json_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_html(contract), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
