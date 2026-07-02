#!/usr/bin/env python3
"""Regression test for Gate14 floor-student target generation."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_premium_still_sr_gate14_floor_student_targets.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("gate14_floor_student_targets", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tmp_parent() -> Path | None:
    root = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    return Path(root) if root else None


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        print(f"test_build_premium_still_sr_gate14_floor_student_targets: SKIP missing {exc.name}")
        return 0

    tool = load_tool()
    with tempfile.TemporaryDirectory(prefix="gpr_gate14_floor_targets_", dir=tmp_parent()) as td:
        root = Path(td)
        low = np.zeros((2, 4, 4, 4), dtype=np.uint16)
        target = np.zeros((2, 4, 8, 8), dtype=np.uint16)
        for idx in range(2):
            for ch in range(4):
                base = 512 + idx * 200 + ch * 50
                yy, xx = np.indices((8, 8))
                target[idx, ch] = base + xx * 11 + yy * 7
                low[idx, ch] = target[idx, ch].reshape(4, 2, 4, 2).mean(axis=(1, 3)).astype(np.uint16)
        meta = {
            "schema": "gpr.premium_still_sr_pairs.v1",
            "images": [
                {
                    "image_id": "x2d_scene",
                    "camera": "Hasselblad X2D",
                    "camera_key": "x2d",
                    "class": "100mp",
                    "source": {"path": str(root / "x2d.dng"), "sha256": "x" * 64},
                    "raw_extract": str(root / "x2d.raw"),
                    "noise_sidecars": [],
                },
                {
                    "image_id": "Z8Z_1353",
                    "camera": "Nikon Z8",
                    "camera_key": "z8",
                    "class": "45mp",
                    "source": {"path": str(root / "Z8Z_1353.dng"), "sha256": "z" * 64},
                    "raw_extract": str(root / "Z8Z_1353.raw"),
                    "noise_sidecars": [],
                },
            ],
            "tiles": [
                {"image_id": "x2d_scene", "high_x": 0, "high_y": 0, "low_x": 0, "low_y": 0, "low_tile": 4, "high_raw_tile": 8},
                {"image_id": "Z8Z_1353", "high_x": 2, "high_y": 2, "low_x": 1, "low_y": 1, "low_tile": 4, "high_raw_tile": 8},
            ],
        }
        pairs = root / "pairs.npz"
        np.savez_compressed(pairs, inputs=low, targets=target, meta=json.dumps(meta, sort_keys=True))
        sidecar = root / "selector_sidecar.json"
        sidecar.write_text(
            json.dumps(
                {
                    "schema": "gpr.premium_still_sr_multi_source_selector_sidecar.v1",
                    "sources": [{"source_id": "source"}],
                    "rules": [{"rule_id": "rule"}],
                }
            ),
            encoding="utf-8",
        )
        smoke = root / "selector_smoke.json"
        smoke.write_text(
            json.dumps(
                {
                    "gate14_selector_smoke_passed": True,
                    "selector_smoke_metrics": {"selected_row_count": 2},
                }
            ),
            encoding="utf-8",
        )
        launch = root / "launch_packet.json"
        launch.write_text(
            json.dumps(
                {
                    "candidate_id": "premium_still_sr_gate14_floor_student_v1",
                    "preflight": {"launchable_for_production_attempt": True},
                    "next_commands": ["train x2d", "train z8"],
                }
            ),
            encoding="utf-8",
        )
        raw_targets = root / "legacy_raw_targets.npz"
        np.savez_compressed(raw_targets, meta=json.dumps([]))
        args = type(
            "Args",
            (),
            {
                "output_dir": root / "out",
                "raw_targets": raw_targets,
                "gate14_pairs": pairs,
                "selector_sidecar": sidecar,
                "selector_smoke": smoke,
                "launch_packet": launch,
                "domains": "all",
                "max_tiles": None,
                "highpass_block": 3,
            },
        )()
        receipt = tool.build(args)
        assert receipt["target_builder_passed"] is True
        assert receipt["blocker_classification"] is None
        assert receipt["coverage"]["built_target_row_count"] == 2
        assert receipt["coverage"]["built_target_domain_counts"] == {"x2d": 1, "z8": 1}
        assert receipt["target_policy"]["teacher_gate_before_student"] is True
        with np.load(receipt["output_npz"], allow_pickle=False) as z:
            assert z["candidate_raw_cfa4"].shape == (2, 8, 8, 4)
            assert z["raw_hf_residual_cfa4"].shape == (2, 8, 8, 4)
            rows = json.loads(str(z["meta"]))
            assert rows[0]["selected_source_id"] == "gate14_clean_source_pair_high_tile"
            assert rows[0]["candidate_raw"] == "gate14_pair_low_bayer_same_color_2x_repeat"
            assert rows[1]["scene_id"] == "Z8Z_1353"

    print("test_build_premium_still_sr_gate14_floor_student_targets: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
