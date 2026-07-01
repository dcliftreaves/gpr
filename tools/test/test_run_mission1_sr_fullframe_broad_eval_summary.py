#!/usr/bin/env python3
"""Regression test for Mission/Z8 full-frame SR summary metric reduction."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/run_mission1_sr_fullframe_broad_eval.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("run_mission1_sr_fullframe_broad_eval_test", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    tool = load_tool()
    with tempfile.TemporaryDirectory(prefix="gpr_sr_fullframe_summary_") as td:
        root = Path(td)
        image_dir = root / "frame"
        bench = image_dir / "frame_ckpt_sr8k_512_ov64_bench.json"
        compare = image_dir / "frame_fullframe_compare.json"
        contact = image_dir / "frame_fullframe_contact.jpg"
        write_json(
            bench,
            {
                "timing": {
                    "fps_with_write": 2.5,
                    "total_with_write_s": 0.4,
                    "inference_plus_copy_s": 0.3,
                    "write_output_s": 0.1,
                }
            },
        )
        write_json(
            compare,
            {
                "improvement_pct": {
                    "rmse": 12.0,
                    "mae": 10.0,
                    "gradient_mae": 5.0,
                    "same_cell_detail_mae": 4.0,
                    "same_cell_fine_detail_mae": 3.0,
                    "cfa_plane_detail_mae": 2.0,
                },
                "baseline_bilinear": {"psnr14_db": 40.0, "rmse_counts": 100.0},
                "model": {"psnr14_db": 42.0, "rmse_counts": 88.0},
                "baseline_same_cell_detail": {"same_cell_detail_mae_counts": 30.0},
                "model_same_cell_detail": {"same_cell_detail_mae_counts": 28.8},
            },
        )
        paths = {
            "bench_json": bench,
            "compare_json": compare,
            "contact_sheet": contact,
        }
        row = tool.row_from_receipts("frame", paths)
        assert row["same_cell_detail_mae_improvement_pct"] == 4.0
        assert row["same_cell_fine_detail_mae_improvement_pct"] == 3.0
        assert row["cfa_plane_detail_mae_improvement_pct"] == 2.0
        assert row["baseline_same_cell_detail_mae"] == 30.0
        assert row["model_same_cell_detail_mae"] == 28.8

        summary = tool.build_summary(root / "out", root / "ckpt.pt", [row], elapsed_s=1.0)
        assert summary["same_cell_detail_mae_improvement_pct"]["median"] == 4.0
        assert summary["same_cell_fine_detail_mae_improvement_pct"]["median"] == 3.0
        assert summary["cfa_plane_detail_mae_improvement_pct"]["median"] == 2.0
        assert summary["worst_by_same_cell_detail_improvement"]["image"] == "frame"

    print("test_run_mission1_sr_fullframe_broad_eval_summary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
