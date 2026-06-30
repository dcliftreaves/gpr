#!/usr/bin/env python3
"""Regression test for raw-CFA premium still-SR residual target builder."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/build_premium_still_sr_raw_cfa_residual_targets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("raw_cfa_target_builder", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_raw_cfa_residual_targets: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_raw_cfa_targets_", dir=tmp_parent) as td:
        root = Path(td)
        y, x = np.indices((32, 32))
        candidate = (0.25 + x * 0.001 + y * 0.002).astype(np.float32)
        raw_detail = ((((x + y) % 4) == 0).astype(np.float32) - 0.25) * 0.04
        source = np.clip(candidate + raw_detail, 0.0, 1.0)
        render_residual_y = tool.same_color_highpass(source - candidate, 8)
        rgb_residual = np.repeat(render_residual_y[:, :, None], 3, axis=2).astype(np.float32)
        meta = [
            {
                "scene_id": "synthetic",
                "source_dng": str(root / "source.dng"),
                "candidate_raw": str(root / "candidate.raw"),
                "crop": "full",
                "crop_xy": [0, 0],
                "crop_size": 32,
                "block": 8,
                "ev": 0.0,
            }
        ]
        source_npz = root / "source_targets.npz"
        np.savez_compressed(
            source_npz,
            hf_residuals=rgb_residual[None].astype(np.float16),
            source_hf_targets=rgb_residual[None].astype(np.float16),
            inputs=np.zeros_like(rgb_residual[None], dtype=np.float16),
            meta=json.dumps(meta, sort_keys=True),
        )
        receipt = root / "source_target.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_hf_residual_targets.v1",
                    "arrays": {"npz": str(source_npz)},
                }
            ),
            encoding="utf-8",
        )
        (root / "source.dng").write_bytes(b"synthetic source placeholder")
        (root / "candidate.raw").write_bytes((candidate * 65535.0).astype("<u2").tobytes())

        def fake_source_raw_norm(path: Path):
            assert path == root / "source.dng"
            return source.copy(), 0.0, 65535.0

        def fake_candidate_raw_norm(path: Path, *, shape, black, white):
            assert path == root / "candidate.raw"
            assert shape == source.shape
            return candidate.copy()

        tool.source_raw_norm = fake_source_raw_norm
        tool.candidate_raw_norm = fake_candidate_raw_norm
        args = type("Args", (), {"target_receipt": receipt, "output_dir": root / "out", "max_rows_per_npz": None})()
        payload = tool.build(args)
        assert payload["schema"] == "gpr.premium_still_sr_raw_cfa_residual_targets.v1"
        assert payload["summary"]["row_count"] == 1
        assert payload["summary"]["render_y_to_raw_same_color_hf_corr_abs"]["median"] > 0.95
        out_npz = Path(payload["output_npz"])
        assert out_npz.stat().st_size > 0
        with np.load(out_npz, allow_pickle=False) as z:
            assert z["candidate_raw_cfa4"].shape == (1, 32, 32, 4)
            assert z["candidate_raw_hf_cfa4"].shape == (1, 32, 32, 4)
            assert z["raw_hf_residual_cfa4"].shape == (1, 32, 32, 4)
            assert z["source_raw_hf_cfa4"].shape == (1, 32, 32, 4)
            assert z["render_hf_residual_y"].shape == (1, 32, 32)
            assert float(np.mean(np.abs(z["raw_hf_residual_cfa4"]))) > 0.0
        html = (root / "out" / "index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Raw CFA Residual Targets" in html

    print("test_build_premium_still_sr_raw_cfa_residual_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
