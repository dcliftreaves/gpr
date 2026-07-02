#!/usr/bin/env python3
"""Regression test for Gate15 target-construction proposal builder."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate15_target_construction_proposal.py"


def temp_root() -> Path:
    root = Path(os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR") or tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def npy_scalar_unicode(text: str) -> bytes:
    payload = text.encode("utf-32le")
    char_count = len(text)
    header = f"{{'descr': '<U{char_count}', 'fortran_order': False, 'shape': (), }}"
    padding = 16 - ((10 + len(header) + 1) % 16)
    header_bytes = (header + " " * padding + "\n").encode("latin1")
    return b"\x93NUMPY\x01\x00" + len(header_bytes).to_bytes(2, "little") + header_bytes + payload


def write_meta_npz(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("meta.npy", npy_scalar_unicode(json.dumps(rows, sort_keys=True)))


def row(domain: str, idx: int, candidate_hf: float, residual_hf: float, render_y: float) -> dict:
    return {
        "domain": domain,
        "camera_key": domain,
        "image_id": f"{domain}_{idx}",
        "scene_id": f"{domain}_{idx}",
        "tile_index": idx,
        "gate14_output_index": idx,
        "candidate_raw_same_color_hf_abs_mean": candidate_hf,
        "raw_same_color_hf_residual_abs_mean": residual_hf,
        "render_hf_residual_y_abs_mean": render_y,
        "source_raw_same_color_hf_abs_mean": residual_hf + candidate_hf,
        "noise_sidecars": [],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_gate15_proposal_", dir=temp_root()) as td:
        base = Path(td)
        target_builder = base / "target_builder.json"
        write_json(
            target_builder,
            {
                "schema": "gpr.premium_still_sr_gate14_floor_student_targets.v1",
                "target_builder_passed": True,
            },
        )
        rows = [
            row("x2d", 0, 0.002, 0.002, 0.001),
            row("x2d", 1, 0.003, 0.003, 0.002),
            row("x2d", 2, 0.004, 0.004, 0.003),
            row("x2d", 3, 0.0002, 0.0002, 0.0001),
            row("z8", 4, 0.005, 0.005, 0.002),
            row("z8", 5, 0.0002, 0.0002, 0.0001),
            row("z8", 6, 0.0003, 0.0003, 0.0001),
            row("z8", 7, 0.0004, 0.0004, 0.0001),
        ]
        npz = base / "targets.npz"
        write_meta_npz(npz, rows)
        out = base / "out"
        cmd = [
            sys.executable,
            str(TOOL),
            "--gate14-target-builder",
            str(target_builder),
            "--gate14-target-npz",
            str(npz),
            "--output-dir",
            str(out),
        ]
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            raise SystemExit(proc.returncode)
        proposal = json.loads((out / "target_construction_proposal.json").read_text(encoding="utf-8"))
        assert proposal["schema"] == "gpr.premium_still_sr_gate15_target_construction_proposal.v1"
        assert proposal["paired_smoke_requested"] is True
        assert proposal["row_evidence"]["x2d_candidate_only_positive_floor_row_count"] == 3
        assert proposal["row_evidence"]["x2d_minimum_rows_needed_for_median_floor"] == 3
        assert proposal["row_evidence"]["z8_exact_noop_row_count"] == 4
        assert all(not item["candidate_only_positive_floor"] for item in proposal["pretraining_signal_rows"] if item["domain"] == "z8")
    print("test_build_premium_still_sr_gate15_target_construction_proposal: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
