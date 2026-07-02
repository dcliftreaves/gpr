#!/usr/bin/env python3
"""Build a launch packet for the next premium still-SR production attempt.

This is a CI-safe planning artifact. It writes the candidate preflight proposal,
the preflight audit, a compact HTML view, and the exact next command sequence.
It does not train a model and does not claim production readiness.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from build_premium_still_sr_candidate_preflight_template import build_manifest
from check_premium_still_sr_candidate_preflight import validate_preflight, write_html


SCHEMA = "gpr.premium_still_sr_launch_packet.v1"
DEFAULT_EXTERNAL_ROOT = Path("/Volumes/OWC_8TB/gpr_work")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    ap.add_argument(
        "--template",
        choices=("clean_source_restormer_teacher", "rejected_repeat_fixture"),
        default="clean_source_restormer_teacher",
    )
    ap.add_argument("--candidate-id", default=None)
    ap.add_argument(
        "--manifest",
        type=Path,
        help=(
            "Explicit gpr.premium_still_sr_candidate_preflight.v1 proposal to "
            "use for a launchable production attempt. Without this, the packet "
            "is a planning/template artifact and --require-launchable will fail."
        ),
    )
    ap.add_argument(
        "--require-launchable",
        action="store_true",
        help="Exit nonzero if the candidate preflight blocks the launch packet.",
    )
    return ap.parse_args()


def rel(path: Path) -> str:
    return path.as_posix()


def as_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str) and value:
        return [value]
    return []


def command_sequence(
    output_dir: Path,
    external_root: Path,
    template: str,
    candidate_id: str | None,
    manifest_path: Path | None = None,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    pair_dir = external_root / "artifacts/premium_still_sr_clean_source_pairs_<date>"
    model_dir = external_root / "artifacts/premium_still_sr_clean_source_teacher_smoke_<date>"
    scoreboard_dir = external_root / "artifacts/premium_still_sr_experiment_scoreboard_<date>"
    promotion_dir = external_root / "artifacts/premium_still_sr_promotion_gate_<date>"
    work_dir = external_root / "tmp/premium_still_sr_pairs_<date>"
    fixture_manifest = external_root / "artifacts/premium_still_sr_fixture_manifest_<date>/fixture_manifest.json"
    pairs = pair_dir / "premium_still_sr_clean_source_pairs.npz"
    smoke_commands = as_strings(manifest.get("smoke_gate_commands")) if manifest is not None else []

    template_args = ""
    if template != "clean_source_restormer_teacher":
        template_args += f" --template {template}"
    if candidate_id:
        template_args += f" --candidate-id {candidate_id}"

    first_steps = []
    if manifest_path is None:
        first_steps.append({
            "step": "write_candidate_preflight",
            "command": (
                "python3 tools/build_premium_still_sr_candidate_preflight_template.py "
                f"--output {rel(output_dir / 'candidate_preflight.json')}"
                f"{template_args}"
            ),
            "receipt": rel(output_dir / "candidate_preflight.json"),
        })
    else:
        first_steps.append({
            "step": "copy_explicit_candidate_preflight",
            "command": (
                "python3 tools/build_premium_still_sr_launch_packet.py "
                f"--manifest {rel(manifest_path)} "
                f"--output-dir {rel(output_dir)} "
                "--require-launchable"
            ),
            "receipt": rel(output_dir / "candidate_preflight.json"),
        })

    command_items = [
        *first_steps,
        {
            "step": "check_candidate_preflight",
            "command": (
                "python3 tools/check_premium_still_sr_candidate_preflight.py "
                f"{rel(output_dir / 'candidate_preflight.json')} "
                f"--json-out {rel(output_dir / 'preflight_audit.json')} "
                f"--html-out {rel(output_dir / 'index.html')} "
                "--require-launchable"
            ),
            "receipt": rel(output_dir / "preflight_audit.json"),
        },
        {
            "step": "build_clean_source_pairs",
            "command": (
                "python3 tools/cnn/build_premium_still_sr_pairs.py "
                f"--fixture-manifest {rel(fixture_manifest)} "
                f"--out {rel(pairs)} "
                f"--work-dir {rel(work_dir)} "
                "--tiles-per-fixture 64 "
                "--low-plane-tile 96 "
                "--dataset-label premium_still_sr_clean_source_pairs"
            ),
            "receipt": rel(pairs),
        },
        {
            "step": "audit_clean_source_pairs",
            "command": (
                "python3 tools/cnn/audit_premium_still_sr_pairs.py "
                f"--pairs {rel(pairs)} "
                f"--output-dir {rel(pair_dir / 'audit')}"
            ),
            "receipt": rel(pair_dir / "audit/index.html"),
        },
    ]
    if smoke_commands:
        for idx, command in enumerate(smoke_commands, start=1):
            command_items.append(
                {
                    "step": f"candidate_smoke_gate_{idx}",
                    "command": command,
                    "receipt": "defined by explicit candidate_preflight.json smoke_gate_commands",
                }
            )
        command_items.append(
            {
                "step": "check_smoke_gate_acceptance",
                "command": (
                    "Compare the X2D and Z8 smoke receipts against "
                    "candidate_preflight.json smoke_gate_acceptance. Stop before "
                    "any long run unless both holdouts beat same-color Bayer "
                    "interpolation and meet the median/worst-row floors."
                ),
                "receipt": "x2d_smoke_receipt and z8_smoke_receipt with baseline_comparison, checkpoint_hash, and training_config_hash",
            }
        )
    else:
        command_items.append(
            {
                "step": "candidate_smoke_gates_required",
                "command": (
                    "Edit candidate_preflight.json and add smoke_gate_commands for "
                    "held-out X2D and Z8 before running a launchable packet."
                ),
                "receipt": rel(model_dir / "<candidate_smoke>/train_receipt.json"),
            }
        )
    command_items.extend(
        [
        {
            "step": "build_scoreboard",
            "command": (
                "python3 tools/build_premium_still_sr_experiment_scoreboard.py "
                f"--external-root {rel(external_root)} "
                f"--output-dir {rel(scoreboard_dir)}"
            ),
            "receipt": rel(scoreboard_dir / "scoreboard.json"),
        },
        {
            "step": "check_promotion_gate",
            "command": (
                "python3 tools/check_premium_still_sr_promotion_gate.py "
                f"--scoreboard {rel(scoreboard_dir / 'scoreboard.json')} "
                f"--output-dir {rel(promotion_dir)}"
            ),
            "receipt": rel(promotion_dir / "promotion_gate.json"),
        },
        ]
    )
    return command_items


def build_packet(
    *,
    output_dir: Path,
    external_root: Path,
    template: str,
    candidate_id: str | None,
    manifest_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise TypeError(f"{manifest_path} must contain a JSON object")
        manifest_source = manifest_path.as_posix()
    else:
        manifest = build_manifest(template, candidate_id)
        manifest_source = "generated_template"
    audit = validate_preflight(manifest)
    if manifest_path is None:
        failures = list(audit.get("failures") or [])
        failures.append(
            "explicit --manifest is required before a launch packet can pass --require-launchable; "
            "the built-in template is reference/planning material only"
        )
        audit = {
            **audit,
            "launchable_for_production_attempt": False,
            "failures": failures,
            "verdict": "blocked_before_long_run",
        }
    commands = command_sequence(output_dir, external_root, template, candidate_id, manifest_path, manifest)
    packet = {
        "schema": SCHEMA,
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidate_id": audit["candidate_id"],
        "manifest_source": manifest_source,
        "explicit_manifest_required_for_launchable": True,
        "production_ready": False,
        "promotion_claimed": False,
        "preflight": {
            "launchable_for_production_attempt": audit["launchable_for_production_attempt"],
            "verdict": audit["verdict"],
            "failures": audit["failures"],
            "warnings": audit["warnings"],
        },
        "next_commands": commands,
        "blocked_repeats": [
            "residual_pixelshuffle local-CNN-only primary path",
            "clean-signal U-Net repeat without a new degradation/objective",
            "restormer_pixelshuffle same-color pair trainer beyond smoke unless X2D and Z8 holdouts both improve",
            "source-HF or stored-HF render-time content",
            "same-color box downsample as the only degradation policy",
            "train-split-only or crop-only promotion evidence",
        ],
        "promotion_stop_conditions": [
            "candidate-only runtime inputs: candidate_raw and camera_metadata, with no REF/source/JPEG content",
            "held-out X2D and Z8 full-image or overlapped-tile evidence",
            "both X2D and Z8 smoke holdouts beat same-color interpolation before any longer run",
            "candidate_preflight.json smoke_gate_acceptance passes: positive median MAE recovery, nonnegative worst-row MAE recovery, and required receipt fields",
            "50 MP and 100 MP full-frame rows",
            "positive median MAE/RMSE recovery and nonnegative worst-row recovery",
            "editable DNG/GPR receipts and editor-latitude review",
            "seconds per 50 MP frame, seconds per 100 MP frame, and peak RSS",
            "exact-sidecar-only noise policy with source residual noise forbidden",
        ],
        "notes": (
            "This launch packet is an intake/control artifact. Passing it means "
            "the next long run is worth attempting; it does not promote a model."
        ),
    }
    return manifest, audit, packet


def write_markdown(packet: dict[str, Any], path: Path) -> None:
    commands = packet.get("next_commands") if isinstance(packet.get("next_commands"), list) else []
    command_lines = "\n".join(f"{idx}. `{item['command']}`" for idx, item in enumerate(commands, start=1))
    repeats = "\n".join(f"- {item}" for item in packet.get("blocked_repeats", []))
    stops = "\n".join(f"- {item}" for item in packet.get("promotion_stop_conditions", []))
    text = f"""# Premium Still-SR Launch Packet

Candidate: `{packet.get('candidate_id')}`

Preflight verdict: `{packet.get('preflight', {}).get('verdict')}`

This packet does not claim production readiness. It only defines the next
launchable premium still-SR attempt and the receipts needed before promotion.

## Next Commands

{command_lines}

## Blocked Repeats

{repeats}

## Promotion Stop Conditions

{stops}
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest, audit, packet = build_packet(
        output_dir=args.output_dir,
        external_root=args.external_root,
        template=args.template,
        candidate_id=args.candidate_id,
        manifest_path=args.manifest,
    )

    candidate_path = args.output_dir / "candidate_preflight.json"
    audit_path = args.output_dir / "preflight_audit.json"
    packet_path = args.output_dir / "launch_packet.json"
    markdown_path = args.output_dir / "launch_packet.md"
    html_path = args.output_dir / "index.html"

    candidate_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(packet, markdown_path)
    write_html(audit, html_path)

    print(json.dumps({"launch_packet": str(packet_path), "verdict": audit["verdict"]}, sort_keys=True))
    if args.require_launchable and not audit["launchable_for_production_attempt"]:
        for failure in audit["failures"]:
            print(f"preflight failure: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
