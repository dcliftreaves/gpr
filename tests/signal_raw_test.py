"""Portable correctness checks and an optional separate-process codec round trip."""

import argparse
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import raw_media as media
import signal_only_raw_sr_pipeline as s
import signal_raw as workflow
from optical_psf_deconvolution import estimate_empirical_sensor_noise_profile


def metadata(w=128, h=128):
    def t(code, kind, fmt, values):
        return media.record(
            code,
            kind,
            len(values) // 2 if kind in (5, 10) else len(values),
            struct.pack("<" + fmt * len(values), *values),
        )

    return dict(
        schema=media.SCHEMA,
        width=w,
        height=h,
        sample_bits=14,
        cfa="RGGB",
        image=[
            media.record(271, 2, 5, b"Test\0"),
            media.record(272, 2, 7, b"Camera\0"),
            media.record(50708, 2, 12, b"Test Camera\0"),
            media.record(50706, 1, 4, bytes((1, 4, 0, 0))),
            t(33421, 3, "H", (2, 2)),
            media.record(33422, 1, 4, bytes((0, 1, 1, 2))),
            t(50713, 3, "H", (1, 1)),
            t(50714, 4, "I", (256,)),
            t(50717, 4, "I", (16383,)),
            t(50728, 5, "I", (1, 1, 1, 1, 1, 1)),
            t(50721, 10, "i", (1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1)),
            t(50778, 3, "H", (21,)),
            t(50829, 4, "I", (0, 0, h, w)),
            t(50719, 4, "I", (0, 0)),
            t(50720, 4, "I", (w, h)),
        ],
        exif=[],
        gps=[],
    )


def write_fixture(root):
    root.mkdir(parents=True, exist_ok=False)
    yy, xx = np.mgrid[0:256, 0:256]
    clean = 1800 + 3 * xx + 180 * np.sin(yy * 0.07)
    clean += (xx > yy * 0.7 + 30) * 180 + ((xx > 128) & (xx < 144)) * 12
    clean = np.rint(clean).astype(np.uint16)
    noisy = np.clip(
        np.rint(clean + np.random.default_rng(20261121).normal(0, 12, clean.shape)),
        0,
        16383,
    ).astype(np.uint16)
    for name, raw in (("source", noisy), ("clean", clean)):
        media.write(
            root / (name + ".dng"), metadata(256, 256), raw.astype("<u2").tobytes()
        )
    return root / "source.dng", root / "clean.dng"


class Correctness(unittest.TestCase):
    def test_bounded_and_integer_conservation_at_black_and_saturation(self):
        rng = np.random.default_rng(1)
        low = rng.integers(0, 16384, (4, 13, 17), dtype=np.uint16)
        low[:, :, 0] = 0
        low[:, :, -1] = 16383
        proposal = rng.normal(0.5, 2, (4, 26, 34)).astype(np.float32)
        out = s.bounded_cell_consistent_4ch(proposal, low.astype(np.float32) / 16383)
        self.assertTrue(np.all((out >= 0) & (out <= 1)))
        np.testing.assert_allclose(
            s.box_2x2_downsample_4ch(out), low / 16383, atol=2e-7
        )
        counts = s.quantize_cell_consistent_4ch(proposal, low)
        sums = sum(
            counts[:, y::2, x::2].astype(np.int32) for y in range(2) for x in range(2)
        )
        np.testing.assert_array_equal(sums, low.astype(np.int32) * 4)

    def test_model_zero_residual_saturated_step_and_checkpoint(self):
        model = s.build_large_area_wavelet_sr_model().eval()
        cp = torch.load(
            workflow.DEFAULT_CHECKPOINT, map_location="cpu", weights_only=True
        )
        model.load_state_dict(cp["model_state"], strict=True)
        self.assertEqual(sum(p.numel() for p in model.parameters()), 388500)
        for p in model.parameters():
            p.data.zero_()
        x = torch.zeros(1, 4, 16, 20)
        x[:, :, :, 10:] = 1
        with torch.no_grad():
            out = model(x, torch.zeros(1, 2, 16, 20))
        torch.testing.assert_close(F.avg_pool2d(out, 2), x, rtol=0, atol=2e-7)

    def test_phase_aligned_tiling_and_odd_plane_dimensions(self):
        torch.manual_seed(5)
        model = s.build_large_area_wavelet_sr_model().eval()
        # Use the shipped weights rather than a special translation-friendly fixture.
        model.load_state_dict(
            torch.load(
                workflow.DEFAULT_CHECKPOINT, map_location="cpu", weights_only=True
            )["model_state"]
        )
        low = np.random.default_rng(4).integers(
            300, 15000, (4, 75, 79), dtype=np.uint16
        )
        full = s.restore_tiled(low, model, tile=128)
        tiled = s.restore_tiled(low, model, tile=32)
        self.assertLessEqual(
            int(np.abs(full.astype(np.int32) - tiled.astype(np.int32)).max()), 1
        )
        for value in (full, tiled):
            sums = sum(
                value[:, y::2, x::2].astype(np.int32)
                for y in range(2)
                for x in range(2)
            )
            np.testing.assert_array_equal(sums, low.astype(np.int32) * 4)
        with self.assertRaises(ValueError):
            s.restore_tiled(low, model, tile=31)

    def test_uniform_profiles_and_wire_validation(self):
        for value in (0, 256, 1000, 16383):
            p = estimate_empirical_sensor_noise_profile(
                np.full((128, 128), value, dtype=np.uint16)
            )
            self.assertTrue(p["flat_bin_fallback"])
            self.assertEqual(p["lut_sigma_counts"], [0])
            wire = workflow.freeze_profile(p)
            self.assertEqual(wire["sigma_bytes"], 64)
            self.assertEqual(workflow.thaw_profile(wire)["lut_sigma_counts"], [0] * 32)
        with self.assertRaises(ValueError):
            workflow.thaw_profile(dict(encoding="unknown"))

    def test_grain_covariance_temporal_variation_and_crop_identity(self):
        clean = np.full((4, 192, 192), 0.5, dtype=np.float32)
        profile = dict(lut_intensity_counts=[0, 16383], lut_sigma_counts=[10, 10])
        _, a = s.synthesize_empirical_sensor_grain_4ch(
            clean, profile, seed=8, frame_index=2
        )
        _, b = s.synthesize_empirical_sensor_grain_4ch(
            clean[:, 11:71, 13:73], profile, seed=8, frame_index=2, origin=(11, 13)
        )
        np.testing.assert_array_equal(a[:, 11:71, 13:73], b)
        _, c = s.synthesize_empirical_sensor_grain_4ch(
            clean, profile, seed=8, frame_index=3
        )
        self.assertFalse(np.array_equal(a, c))
        corr = np.corrcoef(a.reshape(4, -1))
        np.fill_diagonal(corr, 0)
        self.assertLess(float(np.max(np.abs(corr))), 0.03)
        np.testing.assert_allclose(a.reshape(4, -1).std(axis=1), 10, rtol=0.03)

    def test_metadata_collision_invalid_lut_and_seed(self):
        p = estimate_empirical_sensor_noise_profile(
            np.full((128, 128), 1000, dtype=np.uint16)
        )
        wire = workflow.freeze_profile(p)
        c = dict(
            schema="gpr.signal_raw.v1", mode="stock", sample_peak=16383, noise=wire
        )
        meta, _ = workflow.attach(metadata(), c)
        self.assertEqual(workflow.contract_from(meta), c)
        with self.assertRaises(ValueError):
            workflow.attach(meta, c)
        with self.assertRaises(ValueError):
            s.synthesize_empirical_sensor_grain_4ch(
                np.zeros((4, 2, 2)), dict(lut_intensity_counts=[], lut_sigma_counts=[])
            )

    def test_real_codec_and_separate_decoder_without_original(self):
        if not ENCODER or not DECODER:
            self.skipTest("pass --encoder and --decoder for actual codec checks")
        import tifffile

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.dng"
            rng = np.random.default_rng(3)
            pixels = rng.integers(1000, 5000, (128, 128), dtype=np.uint16)
            media.write(source, metadata(), pixels.astype("<u2").tobytes())
            for mode in ("stock", "denoised", "simulated_sr"):
                gpr = root / (mode + ".gpr")
                workflow.encode(
                    source,
                    gpr,
                    ENCODER,
                    DECODER,
                    mode,
                    3,
                    1.0,
                    workflow.DEFAULT_CHECKPOINT,
                    42,
                )
                # Decoder receives only the GPR, codec executable and checkpoint.
                hidden = root / "hidden-original"
                source.rename(hidden)
                out = root / (mode + ".dng")
                receipt = root / (mode + ".json")
                cmd = [
                    sys.executable,
                    str(Path(workflow.__file__)),
                    "decode",
                    str(gpr),
                    "--output",
                    str(out),
                    "--decoder",
                    str(DECODER),
                    "--receipt",
                    str(receipt),
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                hidden.rename(source)
                result = json.loads(receipt.read_text())
                self.assertTrue(result["complete"])
                self.assertEqual(tifffile.imread(out).shape, (128, 128))
                self.assertEqual(
                    workflow.contract_from(media.extract(gpr, 14))["noise"][
                        "sigma_bytes"
                    ],
                    64,
                )
                if mode == "simulated_sr":
                    self.assertEqual(
                        result["max_integer_cell_sum_error_before_grain"], 0
                    )
                    self.assertEqual(result["reconstruction"], "analytical_bounded")
                    neural_out = root / "neural.dng"
                    neural_log = root / "neural.json"
                    neural_cmd = [
                        sys.executable,
                        str(Path(workflow.__file__)),
                        "decode",
                        str(gpr),
                        "--output",
                        str(neural_out),
                        "--decoder",
                        str(DECODER),
                        "--receipt",
                        str(neural_log),
                        "--neural",
                    ]
                    source.rename(hidden)
                    subprocess.run(neural_cmd, check=True, capture_output=True)
                    hidden.rename(source)
                    self.assertEqual(
                        json.loads(neural_log.read_text())["reconstruction"],
                        "frozen_neural",
                    )
                    meta, payload = media.extract(gpr, 14, with_payload=True)
                    corrupt = root / "corrupt.gpr"
                    changed = bytearray(payload)
                    changed[-8] ^= 1
                    media.write(corrupt, meta, bytes(changed), "gpr")
                    rejected = subprocess.run(
                        [
                            sys.executable,
                            str(Path(workflow.__file__)),
                            "decode",
                            str(corrupt),
                            "--output",
                            str(root / "should-not-exist.dng"),
                            "--decoder",
                            str(DECODER),
                        ],
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn("payload digest differs", rejected.stderr)
                    self.assertFalse((root / "should-not-exist.dng").exists())
                    c = workflow.contract_from(meta)
                    c["model"]["checkpoint_sha256"] = "0" * 64
                    clean_meta = dict(
                        meta,
                        image=[t for t in meta["image"] if t["code"] != workflow.TAG],
                    )
                    bad_meta, _ = workflow.attach(clean_meta, c)
                    mismatch = root / "mismatch.gpr"
                    media.write(mismatch, bad_meta, payload, "gpr")
                    rejected = subprocess.run(
                        [
                            sys.executable,
                            str(Path(workflow.__file__)),
                            "decode",
                            str(mismatch),
                            "--neural",
                            "--output",
                            str(root / "should-not-exist.dng"),
                            "--decoder",
                            str(DECODER),
                        ],
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(rejected.returncode, 0)
                    self.assertIn("checkpoint binding differs", rejected.stderr)
                with self.assertRaises(FileExistsError):
                    workflow.decode(
                        gpr,
                        out,
                        DECODER,
                        workflow.DEFAULT_CHECKPOINT,
                        "cpu",
                        128,
                        64,
                        0.0,
                        0,
                    )


ENCODER = DECODER = None
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-fixture", type=Path)
    parser.add_argument("--encoder", type=Path)
    parser.add_argument("--decoder", type=Path)
    args, remaining = parser.parse_known_args()
    if args.write_fixture:
        print(*write_fixture(args.write_fixture))
        sys.exit(0)
    ENCODER = args.encoder
    DECODER = args.decoder
    torch.set_num_threads(2)
    unittest.main(argv=[sys.argv[0], *remaining])
