#!/usr/bin/env python3
"""Regression-test Mission 1 SR phase reconstruction diagnostics."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools/cnn/analyze_mission1_sr_phase_reconstruction.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("analyze_mission1_sr_phase_reconstruction_test", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_raw(path: Path, raw: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw.astype("<u2", copy=False).tofile(path)


def make_raw(sign: int) -> np.ndarray:
    raw = np.full((16, 16), 1000, dtype=np.uint16)
    for y in range(0, 16, 2):
        for x in range(0, 16, 2):
            raw[y, x] = 1000 + sign * (40 if ((x // 2) + (y // 2)) % 2 == 0 else -40)
    return raw


def main() -> int:
    tool = import_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sr_phase_recon_", dir=work_parent) as td:
        root = Path(td)
        clean_a = make_raw(1)
        codec_a = make_raw(-1)
        clean_b = make_raw(1)
        codec_b = clean_b.copy()
        write_raw(root / "clean/a.raw", clean_a)
        write_raw(root / "codec/a.raw", codec_a)
        write_raw(root / "clean/b.raw", clean_b)
        write_raw(root / "codec/b.raw", codec_b)
        sidecar = {
            "schema": "mission1_sr_pairs.v1",
            "images": [
                {
                    "image_id": "a",
                    "low_source_raw": str(root / "codec/a.raw"),
                    "low_clean_raw": str(root / "clean/a.raw"),
                    "low_width": 16,
                    "low_height": 16,
                },
                {
                    "image_id": "b",
                    "low_source_raw": str(root / "codec/b.raw"),
                    "low_clean_raw": str(root / "clean/b.raw"),
                    "low_width": 16,
                    "low_height": 16,
                },
            ],
        }
        sr_summary = {
            "schema": "mission1_sr_fullframe_broad_eval.v1",
            "images": [
                {
                    "image": "a",
                    "rmse_improvement_pct": 20.0,
                    "mae_improvement_pct": 10.0,
                    "gradient_mae_improvement_pct": 4.0,
                    "model_psnr14_db": 50.0,
                },
                {
                    "image": "b",
                    "rmse_improvement_pct": 40.0,
                    "mae_improvement_pct": 25.0,
                    "gradient_mae_improvement_pct": 9.0,
                    "model_psnr14_db": 55.0,
                },
            ],
        }
        write_json(root / "pairs.json", sidecar)
        write_json(root / "sr.json", sr_summary)
        args = Namespace(
            pair_sidecar=root / "pairs.json",
            sr_summary=root / "sr.json",
            out_dir=root / "out",
            stem=None,
            significant_detail_threshold=2.0,
            rmse_floor=30.0,
            mae_floor=20.0,
            gradient_floor=8.0,
            psnr14_floor=45.0,
        )
        floors = {
            "rmse_improvement_pct": args.rmse_floor,
            "mae_improvement_pct": args.mae_floor,
            "gradient_mae_improvement_pct": args.gradient_floor,
            "model_psnr14_db": args.psnr14_floor,
        }
        rows_by_sr = tool.sr_rows(args.sr_summary)
        specs = tool.collect_image_specs(tool.read_json(args.pair_sidecar), None)
        fallback_specs = tool.collect_image_specs(
            {
                "images": [
                    {
                        "image_id": "GP017346",
                        "low_source_raw": str(root / "codec/a.raw"),
                        "low_clean_raw": str(root / "clean/a.raw"),
                    },
                    {
                        "image_id": "Z8Z_1349",
                        "low_source_raw": str(root / "codec/b.raw"),
                        "low_clean_raw": str(root / "clean/b.raw"),
                    },
                ]
            },
            {"GP017346", "Z8Z_1349"},
        )
        assert fallback_specs[0]["width"] == 4096
        assert fallback_specs[1]["width"] == 4140
        rows = [tool.analyze_image(spec, rows_by_sr.get(spec["image"]), floors, 2.0) for spec in specs]
        summary = tool.build_summary(
            pair_sidecar=args.pair_sidecar,
            sr_summary=args.sr_summary,
            rows=rows,
            floors=floors,
            threshold=2.0,
            out_dir=args.out_dir,
        )
        assert summary["schema"] == tool.SCHEMA
        assert summary["worst_by_phase_error"][0]["image"] == "a"
        by_image = {row["image"]: row for row in rows}
        assert by_image["a"]["phase_error_score"] > by_image["b"]["phase_error_score"]
        assert by_image["a"]["sign_mismatch_max_pct"] > 50.0
        assert by_image["b"]["detail_rmse_counts"] == 0.0

    print("test_analyze_mission1_sr_phase_reconstruction: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
