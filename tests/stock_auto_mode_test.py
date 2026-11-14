#!/usr/bin/env python3
"""
Unit & Integration Tests for Sparse-8K Wavelet Encoding (`GPR_SPARSE_8K`) and
Scene-Adaptive Auto Mode (`tools/stock_auto_mode.py`).
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import stock_auto_mode as auto_mode


def find_gpr_tools() -> Path:
    candidates = [
        Path(os.environ.get("GPR_TOOLS_BIN", "")),
        Path("/tmp/gpr-native-build/source/app/gpr_tools/gpr_tools"),
        Path("/mnt/ssd/gpr_work/stock-pi5-validation-20261113/build/source/app/gpr_tools/gpr_tools"),
        REPO_ROOT / "build" / "source" / "app" / "gpr_tools" / "gpr_tools",
    ]
    for c in candidates:
        if c.name and c.exists() and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError("Could not locate compiled gpr_tools binary")


class StockAutoModeAndSparse8KTests(unittest.TestCase):
    def test_dark_scene_selects_12mp_high_snr_dr(self):
        rng = np.random.default_rng(42)
        # Dark scene with median around 140 counts above black=0
        dark_bayer = rng.integers(80, 200, size=(512, 512), dtype=np.uint16)
        decision = auto_mode.analyze_bayer_scene(dark_bayer)
        self.assertTrue(decision.is_dark)
        self.assertFalse(decision.is_high_contrast)
        self.assertEqual(decision.selected_mode, "12MP_HIGH_SNR_DR")
        self.assertEqual(decision.target_resolution, (4096, 3072))
        self.assertGreater(decision.radiometry.expected_binning_snr_gain_db, 5.95)

    def test_high_contrast_scene_selects_12mp_high_snr_dr(self):
        # High contrast scene: bottom half ~120 counts, top half ~11000 counts (median > 300, C_99/10 > 6 stops)
        hc_bayer = np.full((512, 512), 450, dtype=np.uint16)
        hc_bayer[:100, :] = 90
        hc_bayer[350:, :] = 11500
        decision = auto_mode.analyze_bayer_scene(hc_bayer)
        self.assertFalse(decision.is_dark)
        self.assertTrue(decision.is_high_contrast)
        self.assertEqual(decision.selected_mode, "12MP_HIGH_SNR_DR")
        self.assertEqual(decision.target_resolution, (4096, 3072))

    def test_bright_low_contrast_scene_selects_50mp_sparse_8k(self):
        rng = np.random.default_rng(7)
        # Bright, well-exposed low-contrast daylight scene: 800..2400 counts
        bright_bayer = rng.integers(800, 2400, size=(512, 512), dtype=np.uint16)
        decision = auto_mode.analyze_bayer_scene(bright_bayer)
        self.assertFalse(decision.is_dark)
        self.assertFalse(decision.is_high_contrast)
        self.assertEqual(decision.selected_mode, "50MP_SPARSE_8K")
        self.assertEqual(decision.target_resolution, (8192, 6144))
        self.assertEqual(decision.recommended_env["GPR_SPARSE_8K"], "1")

    def test_sparse_8k_bit_exact_default_and_12mp_ll1_preservation(self):
        gpr_tools = find_gpr_tools()
        w, h = 1024, 1024
        rng = np.random.default_rng(1234)
        # Construct a synthetic 14-bit RGGB image with smooth 12 MP gradients, sharp 8K edges, and realistic Poisson shot noise
        yy, xx = np.mgrid[0:h, 0:w]
        base = (800.0 + 400.0 * np.sin(xx / 40.0) + 300.0 * np.cos(yy / 40.0)).astype(np.float64)
        # Add sharp 8K checkerboard/bars in a localized bright region
        edge_patch = ((xx >= 320) & (xx < 704) & (yy >= 320) & (yy < 704))
        base[edge_patch] += 900.0 * ((xx[edge_patch] // 2 + yy[edge_patch] // 2) % 2)
        noise = rng.normal(0.0, np.sqrt(base * 1.5 + 16.0))
        raw_u16 = np.clip(base + noise, 64, 15000).astype(np.uint16)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            raw_in = tmp / "in.raw"
            raw_u16.tofile(raw_in)

            def encode_and_decode(tag: str, extra_env: dict):
                env = dict(os.environ)
                env.pop("GPR_OPTICAL_CORING", None)
                env.pop("GPR_SPARSE_8K", None)
                env.update(extra_env)
                gpr_out = tmp / f"{tag}.gpr"
                raw_out = tmp / f"{tag}.raw"
                subprocess.run(
                    [str(gpr_tools), "-i", str(raw_in), "-o", str(gpr_out), "-w", str(w), "-h", str(h), "-p", str(w * 2), "-q", "3"],
                    env=env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                clean_env = dict(os.environ)
                clean_env.pop("GPR_OPTICAL_CORING", None)
                clean_env.pop("GPR_SPARSE_8K", None)
                subprocess.run(
                    [str(gpr_tools), "-i", str(gpr_out), "-o", str(raw_out)],
                    env=clean_env,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                gpr_bytes = gpr_out.read_bytes()
                dec = np.fromfile(raw_out, dtype=np.uint16).reshape(h, w)
                return gpr_bytes, dec

            b_unset, dec_unset = encode_and_decode("unset", {})
            b_zero, dec_zero = encode_and_decode("zero", {"GPR_SPARSE_8K": "0", "GPR_OPTICAL_CORING": "0"})
            b_sparse, dec_sparse = encode_and_decode("sparse", {"GPR_SPARSE_8K": "1", "GPR_OPTICAL_CORING": "1"})

            # 1. Default unset and explicit 0 must be 100% bit-exact
            self.assertEqual(hashlib.sha256(b_unset).hexdigest(), hashlib.sha256(b_zero).hexdigest())
            np.testing.assert_array_equal(dec_unset, dec_zero)

            # 2. Sparse-8K must reduce .gpr byte size significantly
            self.assertLess(len(b_sparse), int(len(b_unset) * 0.85))

            # 3. 12 MP 2x2-binned hierarchy (LL1) must remain ultra-high fidelity (> 60 dB PSNR)
            ref_12mp = auto_mode.bin_50mp_to_12mp_rggb(raw_u16).astype(np.float64)
            dec_12mp = auto_mode.bin_50mp_to_12mp_rggb(dec_sparse).astype(np.float64)
            mse_12mp = float(np.mean((ref_12mp - dec_12mp) ** 2))
            psnr_12mp = 10.0 * np.log10((16383.0 ** 2) / mse_12mp)
            self.assertGreater(psnr_12mp, 60.0)


if __name__ == "__main__":
    unittest.main()
