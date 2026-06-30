#!/usr/bin/env python3
"""Regression test for the real-pair Bayer resize PSF receipt builder."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_bayer_resize_psf_from_pairs.py"
CHECKER = ROOT / "tools/check_product_pillar_receipts.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_fixture(np, path: Path) -> None:
    targets = []
    inputs = []
    tiles = []
    for idx, image_id in enumerate(("synthetic_a", "synthetic_b")):
        base = np.arange(4 * 16 * 16, dtype=np.uint16).reshape(4, 16, 16)
        target = (base + idx * 100).astype(np.uint16)
        low = (
            target[:, 0::2, 0::2].astype(np.uint32)
            + target[:, 0::2, 1::2].astype(np.uint32)
            + target[:, 1::2, 0::2].astype(np.uint32)
            + target[:, 1::2, 1::2].astype(np.uint32)
            + 2
        ) // 4
        targets.append(target)
        inputs.append(low.astype(np.uint16))
        tiles.append({"image_id": image_id, "sample_source": "synthetic_box2"})
    meta = {
        "schema": "gpr.premium_still_sr_pairs.v1",
        "downsample": "same-color 2x2 average within each Bayer plane",
        "images": [{"image_id": "synthetic_a", "cfa_phase": "RGGB"}, {"image_id": "synthetic_b", "cfa_phase": "RGGB"}],
        "tiles": tiles,
    }
    np.savez_compressed(path, inputs=np.stack(inputs), targets=np.stack(targets), meta=json.dumps(meta))
    path.with_suffix(path.suffix + ".json").write_text(json.dumps(meta), encoding="utf-8")


def main() -> int:
    try:
        import numpy as np
    except ModuleNotFoundError:
        print("test_build_bayer_resize_psf_from_pairs: SKIP missing numpy")
        return 0

    with tempfile.TemporaryDirectory(prefix="gpr_psf_pairs_", dir=temp_root()) as tmp:
        tmp_path = Path(tmp)
        pairs = tmp_path / "pairs.npz"
        out_dir = tmp_path / "out"
        write_fixture(np, pairs)
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--pairs",
                str(pairs),
                "--out-dir",
                str(out_dir),
                "--max-samples-per-image",
                "1000",
            ],
            check=True,
        )
        receipt = out_dir / "bayer_resize_psf_receipt.json"
        subprocess.run([sys.executable, str(CHECKER), str(receipt)], check=True)

        payload = json.loads(receipt.read_text(encoding="utf-8"))
        model = payload["psf_model"]
        assert payload["schema"] == "gpr.bayer_resize_psf_receipt.v1"
        assert payload["production_ready"] is False
        assert payload["dataset"]["pair_count"] == 2
        assert model["best_candidate_kernel"] == "same_color_box2"
        assert model["kernel_width_px"] == 2.0
        assert model["kernel_height_px"] == 2.0
        assert model["normalized_rmse"] < 0.001
        assert payload["detail_budget"]["residual_abs_mean_14bit"] > 0.0
        assert payload["detail_budget"]["fine_share_of_residual_abs"] > 0.0
        assert payload["per_image_detail_budget"]["residual_abs_mean_14bit"]["median"] > 0.0
        assert (out_dir / "index.html").is_file()

    print("test_build_bayer_resize_psf_from_pairs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
