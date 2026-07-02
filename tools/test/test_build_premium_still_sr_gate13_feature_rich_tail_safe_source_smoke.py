#!/usr/bin/env python3
"""Regression test for the Gate 13 feature-rich tail-safe smoke builder."""
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
TOOL = ROOT / "tools/build_premium_still_sr_gate13_feature_rich_tail_safe_source_smoke.py"


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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate13_feature_", dir=temp_root()) as td:
        base = Path(td)
        pairs = base / "pairs.npz"
        write_npz(pairs)
        write_json(
            base / "source.json",
            {
                "schema": "gpr.premium_still_sr_clean_source_pair_model.v1",
                "pairs": str(pairs),
                "eval": {
                    "holdout": {
                        "rows": [
                            {"image_id": "x2d_a", "tile_index": 0, "mae_improvement_pct": 1.0},
                            {"image_id": "x2d_a", "tile_index": 1, "mae_improvement_pct": -1.0},
                            {"image_id": "x2d_b", "tile_index": 2, "mae_improvement_pct": 1.2},
                            {"image_id": "x2d_b", "tile_index": 3, "mae_improvement_pct": -1.0},
                        ]
                    }
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
        previous = base / "previous.json"
        write_json(previous, {"schema": "previous"})
        out = base / "out"
        proc = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--source-receipt",
                str(base / "source.json"),
                "--gate12-acceptance",
                str(base / "gate12.json"),
                "--previous-tail-safe-smoke",
                str(previous),
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
        data = json.loads((out / "feature_rich_tail_safe_source_smoke.json").read_text(encoding="utf-8"))
        assert data["schema"] == "gpr.premium_still_sr_gate13_feature_rich_tail_safe_source_smoke.v1"
        assert data["smoke_gate_passed"] is True
        assert data["safe_feature_or_upper_bound"]["passes_strict"] is True
        assert data["best_compact_safe_or_rule"]["term_count"] >= 1
        assert "Feature-Rich Tail-Safe" in (out / "index.html").read_text(encoding="utf-8")
    print("test_build_premium_still_sr_gate13_feature_rich_tail_safe_source_smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
