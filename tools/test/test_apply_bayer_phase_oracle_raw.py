#!/usr/bin/env python3
"""Regression tests for the CFA-preserving Bayer phase-oracle diagnostic."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/apply_bayer_phase_oracle_raw.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("apply_bayer_phase_oracle_raw_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_raw(sign: int) -> np.ndarray:
    raw = np.full((16, 16), 1000, dtype=np.uint16)
    for y in range(0, 16, 2):
        for x in range(0, 16, 2):
            raw[y, x] = 1000 + sign * (40 if ((x // 2) + (y // 2)) % 2 == 0 else -40)
    return raw


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    tool = import_tool()
    work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
    work_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase_oracle_", dir=work_parent) as td:
        root = Path(td)
        clean = make_raw(1)
        codec = make_raw(-1)
        identity = tool.phase_oracle(codec, clean, "codec", 2.0, 65535)
        sign_fixed = tool.phase_oracle(codec, clean, "codec_lf_clean_phase_codec_mag", 2.0, 65535)
        detail_fixed = tool.phase_oracle(codec, clean, "codec_lf_clean_detail", 2.0, 65535)

        np.testing.assert_array_equal(identity, codec)
        assert tool.metrics(codec, clean, sign_fixed)["output_clean_rmse"] < tool.metrics(codec, clean, codec)["codec_clean_rmse"]
        assert tool.metrics(codec, clean, detail_fixed)["output_clean_rmse"] <= tool.metrics(codec, clean, sign_fixed)["output_clean_rmse"]

        codec_path = root / "codec.raw"
        clean_path = root / "clean.raw"
        codec.astype("<u2").tofile(codec_path)
        clean.astype("<u2").tofile(clean_path)
        sidecar = {
            "images": [
                {
                    "image_id": "GP017346",
                    "low_source_raw": str(codec_path),
                    "low_clean_raw": str(clean_path),
                }
            ]
        }
        write_json(root / "pairs.json", sidecar)
        specs = tool.sidecar_specs(root / "pairs.json", {"GP017346"})
        assert specs[0]["width"] == 4096
        assert specs[0]["height"] == 3072

    print("test_apply_bayer_phase_oracle_raw: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
