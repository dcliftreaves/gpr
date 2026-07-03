#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate16_target_row_audit.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("gate16_target_row_audit", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    tool = load_tool()
    rows = [
        {
            "class": "100mp",
            "crop": "gate14_tile_02688",
            "crop_size": 384,
            "high_raw_tile": 384,
            "raw_residual_mae_reduction_pct": 20.0,
            "raw_residual_rmse_reduction_pct": 21.0,
            "exact_raw_mae_reduction_pct": 2.0,
        },
        {
            "class": "100mp",
            "crop": "gate14_tile_02689",
            "crop_size": 384,
            "high_raw_tile": 384,
            "raw_residual_mae_reduction_pct": 18.0,
            "raw_residual_rmse_reduction_pct": 19.0,
            "exact_raw_mae_reduction_pct": 1.0,
        },
    ]
    summary = tool.summarize_rows(rows)
    assert summary["100mp"]["row_count"] == 2
    assert summary["100mp"]["raw_residual_mae_reduction_pct"]["median"] == 19.0
    assert tool.is_full_frame_evidence(rows) is False
    decision = tool.gate_decision(summary, full_frame_evidence=False)
    assert decision["production_promotable_from_this_audit"] is False
    assert decision["first_open_step"] == "full_frame_gate_50mp_100mp"
    assert "50mp target rows" in decision["missing_evidence"]
    assert "full-frame 50 MP / 100 MP evidence; current audit is target-row/tile scope" in decision["missing_evidence"]
    print("test_build_premium_still_sr_gate16_target_row_audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
