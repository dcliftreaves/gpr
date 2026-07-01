#!/usr/bin/env python3
"""Build a manual visual-signoff receipt for a Mission 1 8K SR candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


SCHEMA = "gpr.mission1_8k_sr_visual_signoff.v1"
DEFAULT_CNN_ID = "mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1"
DEFAULT_VISUAL_REVIEW = Path(
    "/Volumes/OWC_8TB/gpr_work/artifacts/mission1_8k_sr_coord_detail_psf_focus_step0075_visual_review_20260701/visual_review.json"
)
DEFAULT_SIGNOFF_STATEMENT = "User reviewed the GoPro 8K SR dashboard and stated: 8k gopro SR approved."


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def build(args: argparse.Namespace) -> dict[str, Any]:
    visual = load_json(args.visual_review)
    checks = visual.get("checks") if isinstance(visual.get("checks"), list) else []
    objective_pass = bool(checks) and all(
        isinstance(check, dict) and check.get("passed") is True for check in checks
    )
    manual_complete = bool(args.approved and objective_pass)
    return {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate": {
            "cnn_id": args.cnn_id,
        },
        "visual_review": {
            "path": args.visual_review.as_posix(),
            "sha256": sha256_file(args.visual_review),
            "schema": visual.get("schema"),
            "objective_checks_pass": objective_pass,
            "check_count": len(checks),
            "manual_visual_review_required": visual.get("manual_visual_review_required"),
            "source_manual_visual_review_complete": visual.get("manual_visual_review_complete"),
            "contact_sheet": visual.get("contact_sheet"),
            "contact_sheet_sha256": visual.get("contact_sheet_sha256"),
        },
        "signoff": {
            "approved": bool(args.approved),
            "manual_visual_review_complete": manual_complete,
            "reviewer_role": args.reviewer_role,
            "statement": args.statement,
            "scope": args.scope,
        },
        "production_boundary": {
            "closes_manual_visual_review_blocker": manual_complete,
            "does_not_prove_controlled_native_psf": True,
            "does_not_change_live_camera_scope": True,
            "controlled_native_psf_evidence_still_required": True,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cnn-id", default=DEFAULT_CNN_ID)
    ap.add_argument("--visual-review", type=Path, default=DEFAULT_VISUAL_REVIEW)
    ap.add_argument("--reviewer-role", default="project_owner")
    ap.add_argument("--statement", default=DEFAULT_SIGNOFF_STATEMENT)
    ap.add_argument(
        "--scope",
        default="Manual review approval for the GoPro Mission 1 8K SR dashboard/review artifact only.",
    )
    ap.add_argument("--approved", action="store_true")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    data = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": args.output.as_posix(),
        "manual_visual_review_complete": data["signoff"]["manual_visual_review_complete"],
        "controlled_native_psf_evidence_still_required": data["production_boundary"][
            "controlled_native_psf_evidence_still_required"
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
