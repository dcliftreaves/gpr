#!/usr/bin/env python3
"""Build an inventory of large external CNN/SR datasets.

The project keeps large training corpora, checkpoints, dashboards, and review
media outside git under /Volumes/OWC_8TB/gpr_work. This dashboard makes the
current canonical datasets explicit so future training passes do not start from
stale or superseded artifact trees.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.cnn_dataset_inventory.v1"
DEFAULT_EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT") or "/Volumes/OWC_8TB/gpr_work")


DATASETS: list[dict[str, Any]] = [
    {
        "id": "mission1_z8_4k_cleanup_8k_sr_current",
        "label": "Mission/Z8 4K cleanup + 8K SR current corpus",
        "relpath": "artifacts/current_goal_bayer_rgb_target_cleanup_20260625",
        "status": "canonical_current",
        "pillars": ["raw_video_improvement", "raw_video_psf_sr"],
        "role": "Current approved offline 4K cleanup and 8K SR corpus/checkpoint tree.",
        "use_for_next": "Use for 4K cleanup softness review, 8K SR replacement attempts, and PSF-conditioned candidate comparisons.",
        "do_not_use_for": "Do not use to claim live-camera CNN readiness; camera-side capture/preview remains CNN-free.",
        "expected_artifacts": [
            "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4kcnn_sr_pairs_w96_t72.npz",
            "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/z8_all24_4kcnn_sr_pairs_w96_t72.npz",
            "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_z8_4kcnn_sr_pairs_w96_t72_merged.npz",
            "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/bayer_rgb_target_w40_d5_rs015_gamma2_grad1_raw2_bayer2_step1000.pt",
            "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_strict_rgb_cfa_candidate_decision.json",
            "train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/sr_4kcnn_input_alpha0p5_finetune_w96_d6_rs03_s600/mission1_8k_sr_4kcnn_input_alpha0p5_ft_w96_d6_rs03_s600.pt",
        ],
    },
    {
        "id": "premium_still_sr_expanded_rawcfa_targets",
        "label": "Premium still-SR expanded raw-CFA HF targets",
        "relpath": "artifacts/premium_still_sr_expanded_rawcfa_hf_targets_20260630",
        "status": "canonical_current",
        "pillars": ["premium_still_sr", "raw_stills"],
        "role": "13-scene / 351-row expanded still-SR target set with complete candidate_raw_cfa4 features.",
        "use_for_next": "Use as the fixed source target set when replacing the weak still-SR raw residual learner.",
        "do_not_use_for": "Do not promote directly; this is target material, not a passing checkpoint.",
        "expected_artifacts": [
            "expanded_target_build_receipt.json",
            "merged/merge_receipt.json",
            "merged/hf_residual_targets_merged.npz",
        ],
    },
    {
        "id": "premium_still_sr_raw_cfa_residual_targets",
        "label": "Premium still-SR raw-CFA residual targets",
        "relpath": "artifacts/premium_still_sr_raw_cfa_residual_targets_20260630",
        "status": "canonical_current",
        "pillars": ["premium_still_sr", "raw_stills"],
        "role": "Direct source-minus-candidate same-color raw residual supervision target.",
        "use_for_next": "Use for candidate-only runtime raw-CFA residual model training and X2D/Z8 holdout comparisons.",
        "do_not_use_for": "Do not use REF/source content at render time; source raw is training-target only.",
        "expected_artifacts": [
            "raw_cfa_residual_targets.npz",
            "raw_cfa_residual_targets.json",
            "index.html",
        ],
    },
    {
        "id": "premium_still_sr_expanded_rendered_hf_targets",
        "label": "Premium still-SR expanded rendered/HF targets",
        "relpath": "artifacts/premium_still_sr_expanded_hf_targets_20260630",
        "status": "diagnostic_current",
        "pillars": ["premium_still_sr"],
        "role": "Rendered/HF-expanded 13-scene still-SR target set used to rule out target coverage alone.",
        "use_for_next": "Use for ablations and band-analysis comparison against raw-CFA targets.",
        "do_not_use_for": "Do not treat rendered-context models from this tree as promoted; current learner remains too weak.",
        "expected_artifacts": [
            "expanded_target_build_receipt.json",
            "merged/merge_receipt.json",
            "merged/hf_residual_targets_merged.npz",
        ],
    },
    {
        "id": "premium_still_sr_x2d_multiscene_hf_seed",
        "label": "Premium still-SR X2D multiscene HF seed",
        "relpath": "artifacts/premium_still_sr_x2d_multiscene_hf_targets_20260630",
        "status": "superseded_by_expanded_rawcfa",
        "pillars": ["premium_still_sr"],
        "role": "Earlier X2D-focused multiscene HF target set.",
        "use_for_next": "Use only for historical comparison or reproducing earlier X2D probes.",
        "do_not_use_for": "Do not start new production training from this when the expanded raw-CFA set exists.",
        "expected_artifacts": [
            "merged/hf_residual_targets_merged.npz",
        ],
    },
    {
        "id": "mission1_sr_pairs_legacy",
        "label": "Mission 1 SR pairs legacy corpus",
        "relpath": "artifacts/mission1_sr_pairs_20260616",
        "status": "legacy_reference",
        "pillars": ["raw_video_improvement"],
        "role": "Older Mission 1 SR pair set from before the current corrected 4K cleanup/8K SR path.",
        "use_for_next": "Use for historical regression checks only.",
        "do_not_use_for": "Do not use as the primary current-contract SR training set.",
        "expected_artifacts": [],
    },
    {
        "id": "upresable_reference_corpus",
        "label": "UPRESABLE reference corpus",
        "relpath": "artifacts/upresable",
        "status": "large_reference",
        "pillars": ["premium_still_sr", "raw_stills"],
        "role": "Large editable raw upresable reference corpus and review outputs.",
        "use_for_next": "Use for reference/openability checks and historical UPRESABLE comparisons.",
        "do_not_use_for": "Do not confuse with the current Mission/Z8 4K cleanup or raw-CFA still-SR training corpora.",
        "expected_artifacts": [
            "summary.json",
            "upresable_timelapse.mov",
        ],
    },
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--synthetic", action="store_true", help="Build a tiny CI-safe inventory.")
    return ap.parse_args()


def du_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        proc = subprocess.run(
            ["du", "-sk", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return int(proc.stdout.split()[0]) * 1024
    except Exception:
        total = 0
        if path.is_file():
            return path.stat().st_size
        for root, _, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
        return total


def count_matching_files(path: Path) -> dict[str, int]:
    counts = {"npz": 0, "pt": 0, "json": 0, "html": 0}
    if not path.exists():
        return counts
    for root, _, files in os.walk(path):
        for name in files:
            suffix = Path(name).suffix.lower().lstrip(".")
            if suffix in counts:
                counts[suffix] += 1
    return counts


def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def synthetic_root(output_dir: Path) -> Path:
    root = output_dir / "_synthetic_external"
    for row in DATASETS[:3]:
        base = root / row["relpath"]
        base.mkdir(parents=True, exist_ok=True)
        for rel in row["expected_artifacts"]:
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((row["id"] + rel).encode("utf-8"))
    return root


def build_inventory(external_root: Path) -> dict[str, Any]:
    rows = []
    for spec in DATASETS:
        path = external_root / spec["relpath"]
        expected = []
        for rel in spec["expected_artifacts"]:
            artifact_path = path / rel
            expected.append(
                {
                    "relpath": rel,
                    "path": artifact_path.as_posix(),
                    "exists": artifact_path.exists(),
                    "bytes": artifact_path.stat().st_size if artifact_path.is_file() else 0,
                }
            )
        missing_expected = [row["relpath"] for row in expected if not row["exists"]]
        size_bytes = du_bytes(path)
        row = dict(spec)
        row.update(
            {
                "path": path.as_posix(),
                "exists": path.exists(),
                "bytes": size_bytes,
                "human_size": human_size(size_bytes),
                "file_counts": count_matching_files(path),
                "expected_artifacts": expected,
                "expected_artifact_count": len(expected),
                "missing_expected_artifacts": missing_expected,
                "ready_for_current_work": spec["status"] == "canonical_current" and path.exists() and not missing_expected,
            }
        )
        rows.append(row)
    canonical = [row for row in rows if row["status"] == "canonical_current"]
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "external_root": external_root.as_posix(),
        "summary": {
            "dataset_count": len(rows),
            "existing_dataset_count": sum(1 for row in rows if row["exists"]),
            "canonical_current_count": len(canonical),
            "canonical_ready_count": sum(1 for row in canonical if row["ready_for_current_work"]),
            "total_bytes": sum(int(row["bytes"]) for row in rows),
            "total_human_size": human_size(sum(int(row["bytes"]) for row in rows)),
        },
        "datasets": rows,
    }


def render_html(data: dict[str, Any]) -> str:
    summary = data["summary"]
    cards = [
        ("Datasets", summary["dataset_count"]),
        ("Existing", summary["existing_dataset_count"]),
        ("Canonical ready", f"{summary['canonical_ready_count']} / {summary['canonical_current_count']}"),
        ("Indexed size", summary["total_human_size"]),
    ]
    card_html = "\n".join(
        f'<section class="card"><div class="label">{html.escape(str(label))}</div><div class="value">{html.escape(str(value))}</div></section>'
        for label, value in cards
    )
    rows = []
    for row in data["datasets"]:
        counts = row["file_counts"]
        missing = ", ".join(row["missing_expected_artifacts"]) or ""
        pillars = ", ".join(row["pillars"])
        status_cls = "ok" if row["ready_for_current_work"] else "warn"
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(row['label'])}</strong><br><code>{html.escape(row['path'])}</code></td>"
            f"<td><span class=\"{status_cls}\">{html.escape(row['status'])}</span></td>"
            f"<td>{html.escape(pillars)}</td>"
            f"<td>{html.escape(row['human_size'])}</td>"
            f"<td>npz {counts['npz']}<br>pt {counts['pt']}<br>json {counts['json']}<br>html {counts['html']}</td>"
            f"<td>{html.escape(row['role'])}<br><br><strong>Next:</strong> {html.escape(row['use_for_next'])}</td>"
            f"<td>{html.escape(row['do_not_use_for'])}</td>"
            f"<td>{html.escape(missing)}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>GPR CNN Dataset Inventory</title>
<style>
body {{ margin: 30px; font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111820; background: #f5f7f8; }}
main {{ max-width: 1320px; margin: 0 auto; }}
h1 {{ font-size: 34px; margin: 0 0 8px; }}
.sub {{ color: #596572; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 22px 0; }}
.card {{ background: white; border: 1px solid #dce2e7; border-radius: 8px; padding: 14px; }}
.label {{ color: #596572; font-size: 12px; text-transform: uppercase; }}
.value {{ font-size: 24px; font-weight: 760; }}
table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e7; margin: 14px 0 26px; }}
th, td {{ border-bottom: 1px solid #e7ebef; padding: 8px; text-align: left; vertical-align: top; }}
th {{ background: #eef2f5; color: #4f5b67; font-size: 12px; text-transform: uppercase; }}
code {{ font-size: 12px; word-break: break-all; }}
.ok {{ color: #0c6b3d; font-weight: 700; }}
.warn {{ color: #8a5200; font-weight: 700; }}
</style></head><body><main>
<h1>GPR CNN Dataset Inventory</h1>
<p class="sub">Schema {html.escape(data["schema"])}. Large external datasets are indexed by current role so CNN/SR work starts from the right corpus.</p>
<div class="grid">{card_html}</div>
<table><thead><tr><th>Dataset</th><th>Status</th><th>Pillars</th><th>Size</th><th>Files</th><th>Role</th><th>Boundary</th><th>Missing expected artifacts</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</main></body></html>
"""


def main() -> int:
    args = parse_args()
    external_root = synthetic_root(args.output_dir) if args.synthetic else args.external_root
    data = build_inventory(external_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "cnn_dataset_inventory.json"
    html_path = args.output_dir / "index.html"
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_html(data), encoding="utf-8")
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
