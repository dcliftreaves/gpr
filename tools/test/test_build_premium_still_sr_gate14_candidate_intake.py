#!/usr/bin/env python3
"""Regression test for the Gate 14 Premium still-SR selector intake."""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate14_candidate_intake.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def npy_bytes_u2(shape: tuple[int, ...], values: list[int]) -> bytes:
    header = {"descr": "<u2", "fortran_order": False, "shape": shape}
    header_text = repr(header)
    header_len = len(header_text) + 1
    pad = (16 - ((10 + header_len) % 16)) % 16
    header_blob = (header_text + " " * pad + "\n").encode("latin1")
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header_blob)) + header_blob + struct.pack("<" + "H" * len(values), *values)


def npy_bytes_unicode_json(data: dict) -> bytes:
    text = json.dumps(data, sort_keys=True)
    raw = text.encode("utf-32le")
    header = {"descr": f"<U{len(text)}", "fortran_order": False, "shape": ()}
    header_text = repr(header)
    header_len = len(header_text) + 1
    pad = (16 - ((10 + header_len) % 16)) % 16
    header_blob = (header_text + " " * pad + "\n").encode("latin1")
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header_blob)) + header_blob + raw


def write_npz(path: Path) -> None:
    rows = [
        [0, 100, 0, 100],
        [10, 10, 10, 10],
        [0, 120, 0, 120],
        [12, 12, 12, 12],
    ]
    values = [value for row in rows for value in row]
    meta = {
        "images": [
            {"image_id": "x2d_a", "low_width": 16, "low_height": 16, "high_width": 32, "high_height": 32},
            {"image_id": "x2d_b", "low_width": 16, "low_height": 16, "high_width": 32, "high_height": 32},
        ],
        "tiles": [
            {"image_id": "x2d_a", "low_x": 0, "low_y": 0, "high_x": 0, "high_y": 0},
            {"image_id": "x2d_a", "low_x": 8, "low_y": 0, "high_x": 16, "high_y": 0},
            {"image_id": "x2d_b", "low_x": 0, "low_y": 8, "high_x": 0, "high_y": 16},
            {"image_id": "x2d_b", "low_x": 8, "low_y": 8, "high_x": 16, "high_y": 16},
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("inputs.npy", npy_bytes_u2((4, 1, 2, 2), values))
        z.writestr("meta.npy", npy_bytes_unicode_json(meta))


def source_receipt(pairs: Path, checkpoint: Path, values: list[float]) -> dict:
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"fixture checkpoint")
    return {
        "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
        "pairs": str(pairs),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": "fixture-sha",
        "config": {"model_arch": "fixture_model"},
        "promotion": {"baseline_beaten_on_holdout": True},
        "eval": {
            "holdout": {
                "mae_improvement_pct": {"median": 0.1, "min": min(values)},
                "rows": [
                    {"image_id": "x2d_a", "tile_index": 0, "mae_improvement_pct": values[0]},
                    {"image_id": "x2d_a", "tile_index": 1, "mae_improvement_pct": values[1]},
                    {"image_id": "x2d_b", "tile_index": 2, "mae_improvement_pct": values[2]},
                    {"image_id": "x2d_b", "tile_index": 3, "mae_improvement_pct": values[3]},
                ],
            }
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate14_intake_", dir=temp_root()) as td:
        base = Path(td)
        pairs = base / "pairs.npz"
        write_npz(pairs)
        source_a = base / "source_a" / "train_receipt.json"
        source_b = base / "source_b" / "train_receipt.json"
        write_json(source_a, source_receipt(pairs, base / "source_a" / "model.pt", [1.0, -1.0, 0.0, -1.0]))
        write_json(source_b, source_receipt(pairs, base / "source_b" / "model.pt", [0.0, -1.0, 1.2, -1.0]))
        write_json(
            base / "gate13.json",
            {
                "source_or_objective_revision_passed": True,
                "inputs": {
                    "anchor_source_receipt": {"path": str(source_a)},
                    "gate12_acceptance": {"path": str(base / "gate12.json")},
                },
            },
        )
        write_json(
            base / "gate12.json",
            {
                "rows": [
                    {
                        "holdout": "z8",
                        "passed": True,
                        "exact_noop": True,
                        "median_mae_improvement_pct": 0.0,
                        "worst_row_mae_improvement_pct": 0.0,
                    }
                ]
            },
        )
        out = base / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--gate13-revision",
                str(base / "gate13.json"),
                "--artifact-root",
                str(base),
                "--receipt-glob",
                "source_*/train_receipt.json",
                "--output-dir",
                str(out),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        receipt = json.loads((out / "candidate_preflight.json").read_text(encoding="utf-8"))
        sidecar = json.loads((out / "selector_sidecar.json").read_text(encoding="utf-8"))
        assert receipt["schema"] == "gpr.premium_still_sr_gate14_candidate_intake.v1"
        assert sidecar["schema"] == "gpr.premium_still_sr_multi_source_selector_sidecar.v1"
        assert receipt["gate14_candidate_intake_passed"] is True
        assert receipt["sidecar_replay_passed"] is True
        assert receipt["selector_sidecar_summary"]["rule_count"] >= 1
        assert sidecar["runtime_policy"]["fallback"] == "exact_noop"
        assert "Gate 14 Candidate Intake" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_gate14_candidate_intake: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
