#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.cnn.apply_bayer_detail_residual_oracle_raw import (
    apply_detail_residual,
    deinterleave,
    parse_planes,
)


TOOL = REPO / "tools/cnn/apply_bayer_detail_residual_oracle_raw.py"


def test_quantized_residual_improves_codec_detail() -> None:
    codec = np.full((8, 8), 1000, dtype=np.uint16)
    clean = codec.copy()
    clean[0::4, 0::4] += 16
    out, receipt = apply_detail_residual(
        codec,
        clean,
        significant_detail_threshold=0.0,
        residual_threshold=0.0,
        quant_step=4.0,
        planes={0},
        max_value=16383,
    )
    codec_rmse = float(np.sqrt(np.mean((codec.astype(np.float32) - clean.astype(np.float32)) ** 2)))
    out_rmse = float(np.sqrt(np.mean((out.astype(np.float32) - clean.astype(np.float32)) ** 2)))
    assert out_rmse < codec_rmse
    planes = deinterleave(out)
    assert np.any(planes[0] != 1000)
    assert np.all(planes[1:] == 1000)
    assert receipt["sidecar"]["nonzero_samples"] > 0
    assert receipt["sidecar"]["bitmap_values_zlib_bytes"] > 0


def test_plane_parser() -> None:
    assert parse_planes("r,g2") == {0, 2}
    assert parse_planes("all") == {0, 1, 2, 3}


def test_cli_pair_sidecar_receipt() -> None:
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(dir=tmp_parent) as td:
        root = Path(td)
        low = root / "low"
        clean_dir = root / "clean"
        out = root / "out"
        low.mkdir()
        clean_dir.mkdir()
        codec = np.full((8, 8), 1000, dtype=np.uint16)
        clean = codec.copy()
        clean[0::4, 0::4] += 12
        codec.tofile(low / "A.raw")
        clean.tofile(clean_dir / "A.raw")
        sidecar = root / "pairs.json"
        sidecar.write_text(
            json.dumps(
                {
                    "width12": 8,
                    "height12": 8,
                    "images": [
                        {
                            "image_id": "A",
                            "low_source_raw": str(low / "A.raw"),
                            "low_clean_raw": str(clean_dir / "A.raw"),
                        }
                    ],
                }
            )
        )
        receipt = root / "receipt.json"
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--pair-sidecar",
                str(sidecar),
                "--out-dir",
                str(out),
                "--planes",
                "r",
                "--quant-step",
                "2",
                "--receipt",
                str(receipt),
            ],
            check=True,
            cwd=REPO,
        )
        payload = json.loads(receipt.read_text())
        assert payload["schema"] == "gpr.bayer_detail_residual_oracle_raw.v1"
        assert payload["summary"]["image_count"] == 1
        assert payload["summary"]["bitmap_values_zlib_bytes_mean"] > 0
        assert (out / "A.raw").exists()


if __name__ == "__main__":
    test_quantized_residual_improves_codec_detail()
    test_plane_parser()
    test_cli_pair_sidecar_receipt()
    print("test_apply_bayer_detail_residual_oracle_raw: PASS")
