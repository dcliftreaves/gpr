#!/usr/bin/env python3
"""Regression test for the premium still-SR raw CFA residual audit."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/audit_premium_still_sr_raw_cfa_residual.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("raw_cfa_audit", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_audit_premium_still_sr_raw_cfa_residual: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_raw_cfa_audit_", dir=tmp_parent) as td:
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
        npz = root / "targets.npz"
        np.savez_compressed(
            npz,
            hf_residuals=rgb_residual[None].astype(np.float16),
            source_hf_targets=rgb_residual[None].astype(np.float16),
            inputs=np.zeros_like(rgb_residual[None], dtype=np.float16),
            meta=json.dumps(meta, sort_keys=True),
        )
        receipt = root / "target.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_hf_residual_targets.v1",
                    "arrays": {"npz": str(npz)},
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
        payload = tool.build_audit(type("Args", (), {"target_receipt": receipt, "max_rows_per_npz": None})())
        assert payload["summary"]["row_count"] == 1
        row = payload["rows"][0]
        assert row["raw_same_color_hf_residual_abs_mean"] > 0.0
        assert row["raw_to_render_hf_abs_ratio"] > 0.0
        assert abs(row["render_y_to_raw_same_color_hf_corr"]) > 0.95
        html = tool.render_html(payload)
        assert "Premium Still-SR Raw CFA Residual Audit" in html

    print("test_audit_premium_still_sr_raw_cfa_residual: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
