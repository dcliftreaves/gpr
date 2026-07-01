#!/usr/bin/env python3
"""Regression test for deduplicating premium still-SR raw targets."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/cnn/deduplicate_premium_still_sr_raw_targets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("dedup_raw_targets", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_deduplicate_premium_still_sr_raw_targets: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="gpr_dedup_raw_targets_", dir=tmp_parent) as td:
        root = Path(td)
        base = np.arange(8 * 8 * 4, dtype=np.float32).reshape(8, 8, 4) / 255.0
        residual = np.flip(base, axis=0)
        render0 = np.arange(8 * 8, dtype=np.float32).reshape(8, 8) / 100.0
        rows = []
        raw_arrays = {name: [] for name in tool.RAW_ARRAYS}
        render_rows = []
        for ev in (-2.0, 0.0, 2.0):
            rows.append(
                {
                    "scene_id": "scene_a",
                    "crop": "center",
                    "ev": ev,
                    "source_dng": "/fixtures/scene_a.dng",
                    "candidate_raw": "/fixtures/scene_a_candidate.raw",
                    "render_hf_residual_y_abs_mean": float(np.mean(np.abs(render0 + ev * 0.01))),
                }
            )
            raw_arrays["candidate_raw_cfa4"].append(base.astype(np.float16))
            raw_arrays["candidate_raw_hf_cfa4"].append((base * 0.1).astype(np.float16))
            raw_arrays["raw_hf_residual_cfa4"].append(residual.astype(np.float16))
            raw_arrays["source_raw_hf_cfa4"].append((residual * 0.25).astype(np.float16))
            render_rows.append((render0 + ev * 0.01).astype(np.float16))

        targets = root / "targets.npz"
        np.savez_compressed(
            targets,
            **{name: np.stack(values) for name, values in raw_arrays.items()},
            render_hf_residual_y=np.stack(render_rows),
            meta=np.asarray(json.dumps(rows, sort_keys=True)),
        )
        args = type(
            "Args",
            (),
            {
                "targets": targets,
                "output_dir": root / "out",
                "raw_epsilon": 0.0,
                "allow_raw_conflicts": False,
            },
        )()
        payload = tool.build(args)
        assert payload["schema"] == tool.SCHEMA
        assert payload["summary"]["source_row_count"] == 3
        assert payload["summary"]["deduplicated_row_count"] == 1
        assert payload["summary"]["duplicate_factor"] == 3.0
        assert payload["summary"]["raw_conflict_group_count"] == 0
        assert payload["summary"]["multi_row_group_count"] == 1
        assert payload["production_ready"] is True

        with np.load(root / "out/raw_cfa_residual_targets_dedup.npz", allow_pickle=False) as z:
            assert z["candidate_raw_cfa4"].shape == (1, 8, 8, 4)
            assert z["raw_hf_residual_cfa4"].shape == (1, 8, 8, 4)
            assert z["render_hf_residual_y"].shape == (1, 8, 8)
            np.testing.assert_allclose(z["candidate_raw_cfa4"][0], base.astype(np.float16))
            np.testing.assert_allclose(z["render_hf_residual_y"][0], np.mean(np.stack(render_rows).astype(np.float32), axis=0).astype(np.float16))
            meta = json.loads(str(z["meta"]))
            assert meta[0]["raw_deduplicated"] is True
            assert meta[0]["raw_deduplicated_row_count"] == 3
            assert meta[0]["raw_deduplicated_review_evs"] == [-2.0, 0.0, 2.0]
            assert len(meta[0]["raw_deduplicated_review_rows"]) == 3

        html = (root / "out/index.html").read_text(encoding="utf-8")
        assert "Premium Still-SR Deduplicated Raw Targets" in html

    print("test_deduplicate_premium_still_sr_raw_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
