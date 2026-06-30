#!/usr/bin/env python3
"""Regression test for premium still-SR degraded raw helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_premium_still_sr_degraded_candidate_raw.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("degraded_raw_tool", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_degraded_candidate_raw: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    raw = np.arange(7 * 10, dtype=np.uint16).reshape(7, 10)
    out = tool.same_color_box2_roundtrip(raw)
    assert out.shape == raw.shape
    assert out.dtype == raw.dtype
    # Same CFA position should be constant over each 2x2 block in plane space.
    assert out[0, 0] == out[0, 2] == out[2, 0] == out[2, 2]
    assert out[1, 1] == out[1, 3] == out[3, 1] == out[3, 3]
    assert out[-1, 0] == out[-2, 0]

    print("test_build_premium_still_sr_degraded_candidate_raw: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
