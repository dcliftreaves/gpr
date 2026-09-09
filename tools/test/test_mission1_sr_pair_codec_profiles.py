#!/usr/bin/env python3
"""Smoke-test Mission 1 SR pair-builder codec profile wiring."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional for bare-Python CI smoke
    np = None


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "cnn"))

from build_mission1_sr_pairs import MISSION1_CODEC_PROFILES, mission1_codec_env  # noqa: E402


def assert_env(codec: str, expected: dict[str, str]) -> None:
    env = mission1_codec_env(codec)
    for key, value in expected.items():
        actual = env.get(key)
        if actual != value:
            raise AssertionError(f"{codec}: {key}={actual!r}, expected {value!r}")
    if env.get("FUSED_RAW_LL") != "1" or env.get("FUSED_LL_PREDICTOR") != "avg":
        raise AssertionError(f"{codec}: missing base FLL2 profile env")


def main() -> int:
    required = {"current_t233", "t236_ch2lh3", "t356_ch2lh3", "t468_ch2lh4"}
    missing = required - set(MISSION1_CODEC_PROFILES)
    if missing:
        raise AssertionError(f"missing codec profiles: {sorted(missing)}")

    assert_env("current_t233", {
        "FUSED_LL_RICE_KS": "7,5,5,5",
        "GPR_INLINE_DENOISE_T_LH": "2",
        "GPR_INLINE_DENOISE_T_HL": "3",
        "GPR_INLINE_DENOISE_T_HH": "3",
    })
    assert_env("t236_ch2lh3", {
        "FUSED_LL_RICE_KS": "6,6,5,6",
        "GPR_INLINE_DENOISE_T_LH": "2",
        "GPR_INLINE_DENOISE_T_HL": "3",
        "GPR_INLINE_DENOISE_T_HH": "6",
        "GPR_INLINE_DENOISE_T_CH2_LH": "3",
    })
    assert_env("t356_ch2lh3", {
        "FUSED_LL_RICE_KS": "6,6,5,6",
        "GPR_INLINE_DENOISE_T_LH": "3",
        "GPR_INLINE_DENOISE_T_HL": "5",
        "GPR_INLINE_DENOISE_T_HH": "6",
        "GPR_INLINE_DENOISE_T_CH2_LH": "3",
    })
    assert_env("t468_ch2lh4", {
        "FUSED_LL_RICE_KS": "6,6,5,6",
        "GPR_INLINE_DENOISE_T_LH": "4",
        "GPR_INLINE_DENOISE_T_HL": "6",
        "GPR_INLINE_DENOISE_T_HH": "8",
        "GPR_INLINE_DENOISE_T_CH2_LH": "4",
    })

    if np is not None:
        from bayer_resample import cfa_downsample_2x
        from build_mission1_sr_pairs import synthesize_12mp_from_50mp

        src = np.zeros((16, 16), dtype=np.uint16)
        for y in range(src.shape[0]):
            for x in range(src.shape[1]):
                phase = (y & 1, x & 1)
                base = {
                    (0, 0): 1000,
                    (0, 1): 2000,
                    (1, 0): 3000,
                    (1, 1): 4000,
                }[phase]
                src[y, x] = base + y * 17 + x
        for mode in ("gaussian_area", "area", "sample"):
            got = synthesize_12mp_from_50mp(src, mode)
            want = cfa_downsample_2x(src, mode=mode)
            if not np.array_equal(got, want):
                raise AssertionError(f"{mode}: SR pair builder diverged from shared CFA downsampler")

        work_parent = Path(os.environ.get("GPR_TMPDIR", os.environ.get("RUNNER_TEMP", tempfile.gettempdir())))
        work_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mission1_sr_pairs_meta_", dir=work_parent) as td:
            work = Path(td)
            raw_dir = work / "raw50"
            raw_dir.mkdir()
            raw_path = raw_dir / "synthetic_gp50.raw"
            src.astype("<u2", copy=False).tofile(raw_path)
            out = work / "pairs.npz"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "cnn" / "build_mission1_sr_pairs.py"),
                    "--raw50-dir",
                    str(raw_dir),
                    "--high-width",
                    "16",
                    "--high-height",
                    "16",
                    "--out",
                    str(out),
                    "--work-dir",
                    str(work / "work"),
                    "--codec",
                    "none",
                    "--tiles-per-image",
                    "2",
                    "--low-tile",
                    "2",
                    "--downsample",
                    "gaussian_area",
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            meta = json.loads(out.with_suffix(out.suffix + ".json").read_text())
            if meta.get("downsample_implementation") != "tools/bayer_resample.py:cfa_downsample_2x":
                raise AssertionError(f"unexpected downsample implementation: {meta.get('downsample_implementation')}")
            if meta.get("downsample_policy") != "cfa_same_color_gaussian_area_2x":
                raise AssertionError(f"unexpected downsample policy: {meta.get('downsample_policy')}")
            if meta.get("production_downsample") is not True:
                raise AssertionError("gaussian_area metadata must mark production_downsample=true")
            if meta.get("allow_diagnostic_downsample") is not False:
                raise AssertionError("production pair generation must not allow diagnostic downsample by default")
            if meta.get("cfa_preserving") is not True:
                raise AssertionError("SR pair metadata must mark cfa_preserving=true")
            if meta.get("codec") != "none":
                raise AssertionError(f"unexpected codec in metadata: {meta.get('codec')}")
            if meta.get("width12") != 8 or meta.get("height12") != 8:
                raise AssertionError(f"unexpected low dimensions: {meta.get('width12')}x{meta.get('height12')}")
            image_rows = meta.get("images") or []
            if len(image_rows) != 1 or image_rows[0].get("cfa_preserving") is not True:
                raise AssertionError("per-image metadata missing cfa_preserving=true")
            if image_rows[0].get("downsample_implementation") != meta.get("downsample_implementation"):
                raise AssertionError("per-image downsample implementation does not match top-level metadata")
            if image_rows[0].get("downsample_policy") != meta.get("downsample_policy"):
                raise AssertionError("per-image downsample policy does not match top-level metadata")
            if image_rows[0].get("production_downsample") is not True:
                raise AssertionError("per-image metadata missing production_downsample=true")

            manifest = work / "hard_tiles.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "mission1_sr_hard_tile_manifest.v1",
                        "low_tile": 2,
                        "tiles": [
                            {
                                "image_id": "synthetic_gp50",
                                "low_x": 1,
                                "low_y": 2,
                                "low_tile": 2,
                                "score": 12.5,
                                "rank": 1,
                                "score_mode": "unit_test",
                            }
                        ],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            manifest_out = work / "manifest_pairs.npz"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "cnn" / "build_mission1_sr_pairs.py"),
                    "--raw50-dir",
                    str(raw_dir),
                    "--high-width",
                    "16",
                    "--high-height",
                    "16",
                    "--out",
                    str(manifest_out),
                    "--work-dir",
                    str(work / "manifest_work"),
                    "--codec",
                    "none",
                    "--tiles-per-image",
                    "0",
                    "--low-tile",
                    "2",
                    "--downsample",
                    "gaussian_area",
                    "--tile-manifest",
                    str(manifest),
                    "--manifest-only",
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            manifest_meta = json.loads(manifest_out.with_suffix(manifest_out.suffix + ".json").read_text())
            if manifest_meta.get("tile_manifest") != str(manifest) or manifest_meta.get("manifest_only") is not True:
                raise AssertionError("manifest metadata was not recorded")
            manifest_tiles = manifest_meta.get("tiles") or []
            if len(manifest_tiles) != 1:
                raise AssertionError(f"expected one manifest tile, got {len(manifest_tiles)}")
            tile = manifest_tiles[0]
            if tile.get("sample_source") != "tile_manifest" or tile.get("low_x") != 1 or tile.get("low_y") != 2:
                raise AssertionError(f"manifest tile was not preserved: {tile}")
            manifest_npz = np.load(manifest_out, allow_pickle=False)
            if manifest_npz["inputs"].shape[0] != 1 or manifest_npz["targets"].shape[0] != 1:
                raise AssertionError("manifest-only pair build should contain exactly one tile")

            bad_out = work / "bad_pairs.npz"
            bad = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "cnn" / "build_mission1_sr_pairs.py"),
                    "--raw50-dir",
                    str(raw_dir),
                    "--high-width",
                    "16",
                    "--high-height",
                    "16",
                    "--out",
                    str(bad_out),
                    "--work-dir",
                    str(work / "bad_work"),
                    "--codec",
                    "none",
                    "--tiles-per-image",
                    "2",
                    "--low-tile",
                    "2",
                    "--downsample",
                    "sample",
                ],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if bad.returncode == 0 or "--allow-diagnostic-downsample" not in (bad.stderr + bad.stdout):
                raise AssertionError("diagnostic downsample should require explicit opt-in")

            diag_out = work / "diag_pairs.npz"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "cnn" / "build_mission1_sr_pairs.py"),
                    "--raw50-dir",
                    str(raw_dir),
                    "--high-width",
                    "16",
                    "--high-height",
                    "16",
                    "--out",
                    str(diag_out),
                    "--work-dir",
                    str(work / "diag_work"),
                    "--codec",
                    "none",
                    "--tiles-per-image",
                    "2",
                    "--low-tile",
                    "2",
                    "--downsample",
                    "sample",
                    "--allow-diagnostic-downsample",
                ],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            diag_meta = json.loads(diag_out.with_suffix(diag_out.suffix + ".json").read_text())
            if diag_meta.get("production_downsample") is not False:
                raise AssertionError("diagnostic pair metadata must mark production_downsample=false")
            if diag_meta.get("allow_diagnostic_downsample") is not True:
                raise AssertionError("diagnostic pair metadata must record explicit opt-in")
            if diag_meta.get("downsample_policy") != "diagnostic_cfa_same_color_sample_2x":
                raise AssertionError(f"unexpected diagnostic policy: {diag_meta.get('downsample_policy')}")

    print("test_mission1_sr_pair_codec_profiles: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
