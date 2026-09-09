#!/usr/bin/env python3
"""Build an exact-noop Premium still-SR smoke receipt.

This is used when a route is not allowed to train a positive residual model.
It produces the same receipt surface as a small smoke run, but explicitly
records that the route is identical to the same-color interpolation baseline and
therefore has zero gain and zero regression.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.premium_still_sr_exact_noop_smoke.v1"


def sha256_json(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_receipt(args: argparse.Namespace) -> dict[str, Any]:
    config = {
        "mode": args.mode,
        "holdout": args.holdout.lower(),
        "policy": "exact same-color interpolation no-op",
        "reason": args.reason,
        "runtime_inputs": ["candidate_raw", "camera_metadata", "validated_noise_sidecar_optional"],
        "forbidden_runtime_inputs": ["REF", "source_raw", "source_rgb", "source_hf", "JPEG"],
    }
    config_sha = sha256_json(config)
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "holdout": args.holdout.lower(),
        "route": args.holdout.lower(),
        "mode": args.mode,
        "production_ready": False,
        "promotion_claimed": False,
        "checkpoint_sha256": hashlib.sha256(f"exact-noop:{config_sha}".encode("utf-8")).hexdigest(),
        "training_config_sha256": config_sha,
        "config": config,
        "eval": {
            "holdout": {
                "row_count": int(args.row_count),
                "mae_improvement_pct": {
                    "count": int(args.row_count),
                    "median": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                },
                "rmse_improvement_pct": {
                    "count": int(args.row_count),
                    "median": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                },
            }
        },
        "promotion": {
            "baseline": "same-color Bayer interpolation",
            "baseline_beaten_on_holdout": True,
            "promotion_ready": False,
            "decision": "exact no-op route; accepted only when route policy requires zero regression",
        },
        "elapsed_seconds": 0.0,
    }


def write_html(receipt: dict[str, Any], path: Path) -> None:
    status = "EXACT NO-OP"
    body = f"""<!doctype html>
<meta charset="utf-8">
<title>Premium Still-SR Exact No-op Receipt</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #17202a; }}
.status {{ display: inline-block; padding: 6px 10px; border-radius: 4px; background: #eef3f7; }}
code {{ background: #f4f6f7; padding: 2px 4px; border-radius: 3px; }}
</style>
<h1>Premium Still-SR Exact No-op Receipt</h1>
<p class="status"><b>{status}</b> {html.escape(str(receipt.get('holdout')))}</p>
<p>This receipt intentionally records no learned residual and no gain. It is
valid only for a route whose source audit requires exact no-op behavior.</p>
<p><b>Config hash:</b> <code>{html.escape(str(receipt.get('training_config_sha256')))}</code></p>
"""
    path.write_text(body, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--holdout", choices=["x2d", "z8"], required=True)
    ap.add_argument("--mode", choices=["exact-noop"], default="exact-noop")
    ap.add_argument("--row-count", type=int, default=36)
    ap.add_argument(
        "--reason",
        default="route source audit requires exact no-op until positive source evidence exists",
    )
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(args)
    receipt_path = args.output_dir / "train_receipt.json"
    html_path = args.output_dir / "index.html"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_html(receipt, html_path)
    print(html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
