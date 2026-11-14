#!/usr/bin/env python3
"""
Scene-Adaptive Auto Mode (`AUTO_12MP_50MP`) + Sparse-8K Wavelet Hierarchy Controller
====================================================================================
Implements the radiometric & optical physics controller that decides between:
  1. `12MP_HIGH_SNR_DR` (4096 x 3072 2x2-binned Bayer capture, +6.02 dB shot-noise
     SNR gain, +1 to +2 stops dynamic range, ~4x faster capture/encode, paired with
     optional Clean-Sheet Zero-DC 2x SR when 8K output is desired) when the scene is
     **DARK** or **HIGH-CONTRAST**.
  2. `50MP_SPARSE_8K` (8192 x 6144 full-sensor capture with `GPR_SPARSE_8K=1` and
     `GPR_OPTICAL_CORING=1`, preserving the 12 MP `LL1` wavelet base at ~70 dB while
     sparsely encoding only high-SNR Stage-0 8K edges) when the scene is
     **BRIGHT AND LOW-CONTRAST**.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

PEAK_14BIT = 16383.0


@dataclass(frozen=True)
class AutoModeThresholds:
    """Calibrated radiometric thresholds in 14-bit linear Bayer counts (above black)."""
    dark_median_counts: float = 300.0
    high_contrast_stops_p99_p10: float = 5.80
    high_contrast_stops_p95_p5: float = 5.20
    min_8k_innovation_snr: float = 1.15
    read_noise_counts: float = 4.0
    shot_gain_counts_per_e: float = 1.5
    stride_blocks: int = 8  # 8 x 4 = 32-pixel stride -> 256 x 192 grid on 8K (< 0.4 ms)


@dataclass(frozen=True)
class SceneRadiometry:
    width: int
    height: int
    estimated_black_level: float
    p01_counts: float
    p05_counts: float
    p10_counts: float
    p50_counts: float
    p90_counts: float
    p95_counts: float
    p99_counts: float
    contrast_stops_p99_p10: float
    contrast_stops_p95_p5: float
    shadow_fraction_below_300: float
    highlight_fraction_above_12000: float
    innovation_8k_snr_p90: float
    expected_binning_snr_gain_db: float
    analysis_latency_ms: float


@dataclass(frozen=True)
class AutoModeDecision:
    selected_mode: str  # "12MP_HIGH_SNR_DR" or "50MP_SPARSE_8K"
    target_resolution: Tuple[int, int]
    is_dark: bool
    is_high_contrast: bool
    reasons: List[str]
    recommended_env: Dict[str, str]
    recommended_8k_delivery: str
    radiometry: SceneRadiometry


def analyze_bayer_scene(
    raw_u16: np.ndarray,
    thresholds: AutoModeThresholds = AutoModeThresholds(),
    black_level: Optional[float] = None,
) -> AutoModeDecision:
    """
    Evaluate scene illuminance, dynamic range / contrast span, and 8K spatial innovation
    on a strided 4x4 RGGB super-block grid in < 0.5 ms.
    """
    t0 = time.perf_counter()
    if raw_u16.ndim != 2:
        raise ValueError(f"Expected 2D Bayer array, got shape {raw_u16.shape}")
    h, w = raw_u16.shape
    step = max(4, int(thresholds.stride_blocks) * 4)

    # Sample 2x2 same-color green quads from 4x4 RGGB super-blocks
    # In RGGB: (0,1), (0,3), (2,1), (2,3) are G1; (1,0), (1,2), (3,0), (3,2) are G2
    if w >= 4 and h >= 4:
        g00 = raw_u16[0 : h - 3 : step, 1 : w - 2 : step].astype(np.float32)
        g01 = raw_u16[0 : h - 3 : step, 3 : w : step].astype(np.float32)
        g10 = raw_u16[2 : h - 1 : step, 1 : w - 2 : step].astype(np.float32)
        g11 = raw_u16[2 : h - 1 : step, 3 : w : step].astype(np.float32)
    else:
        g00 = raw_u16.astype(np.float32)
        g01 = g00
        g10 = g00
        g11 = g00

    if black_level is None:
        p_min = float(np.percentile(g00, 0.1))
        est_black = 512.0 if p_min > 256.0 else 0.0
    else:
        est_black = float(black_level)

    # 12 MP (2x2 binned) linear luminance proxy above black
    y_12mp = np.maximum(0.25 * (g00 + g01 + g10 + g11) - est_black, 1.0)
    p01, p05, p10, p50, p90, p95, p99 = [
        float(v) for v in np.percentile(y_12mp, [1, 5, 10, 50, 90, 95, 99])
    ]

    floor_c = max(thresholds.read_noise_counts, 4.0)
    contrast_p99_p10 = float(np.log2(max(p99, 8.0) / max(p10, floor_c)))
    contrast_p95_p5 = float(np.log2(max(p95, 8.0) / max(p05, floor_c)))

    shadow_frac = float(np.mean(y_12mp < thresholds.dark_median_counts))
    highlight_frac = float(np.mean(y_12mp > 12000.0))

    # 8K spatial innovation above local Poisson shot + read noise
    diff_8k = 0.5 * (np.abs(g00 - g01) + np.abs(g00 - g10))
    shot_sigma = np.sqrt(
        np.maximum(y_12mp, 16.0) * thresholds.shot_gain_counts_per_e
        + thresholds.read_noise_counts ** 2
    )
    innovation_snr_p90 = float(np.percentile(diff_8k / shot_sigma, 90))

    # Theoretical 2x2 charge/digital binning SNR gain in the median illuminance regime:
    # SNR_12MP / SNR_50MP = 4 * sqrt((g*Y + sigma_r^2) / (4*g*Y + sigma_r^2)) -> >= 2.0x (+6.02 dB)
    var_single = p50 * thresholds.shot_gain_counts_per_e + thresholds.read_noise_counts ** 2
    var_binned = 4.0 * p50 * thresholds.shot_gain_counts_per_e + thresholds.read_noise_counts ** 2
    snr_ratio = 4.0 * np.sqrt(var_single / max(var_binned, 1e-6))
    snr_gain_db = float(20.0 * np.log10(max(snr_ratio, 1.0)))

    dt_ms = (time.perf_counter() - t0) * 1000.0

    radiometry = SceneRadiometry(
        width=w,
        height=h,
        estimated_black_level=est_black,
        p01_counts=p01,
        p05_counts=p05,
        p10_counts=p10,
        p50_counts=p50,
        p90_counts=p90,
        p95_counts=p95,
        p99_counts=p99,
        contrast_stops_p99_p10=contrast_p99_p10,
        contrast_stops_p95_p5=contrast_p95_p5,
        shadow_fraction_below_300=shadow_frac,
        highlight_fraction_above_12000=highlight_frac,
        innovation_8k_snr_p90=innovation_snr_p90,
        expected_binning_snr_gain_db=snr_gain_db,
        analysis_latency_ms=dt_ms,
    )

    is_dark = p50 < thresholds.dark_median_counts
    is_high_contrast = (
        contrast_p99_p10 > thresholds.high_contrast_stops_p99_p10
        or contrast_p95_p5 > thresholds.high_contrast_stops_p95_p5
    )

    reasons: List[str] = []
    if is_dark:
        reasons.append(
            f"DARK_SCENE (median={p50:.1f} < {thresholds.dark_median_counts:.0f} counts; "
            f"2x2 binning yields +{snr_gain_db:.2f} dB SNR)"
        )
    if is_high_contrast:
        reasons.append(
            f"HIGH_CONTRAST_SCENE (C_99/10={contrast_p99_p10:.2f} stops > "
            f"{thresholds.high_contrast_stops_p99_p10:.2f} stops; 12 MP maximizes shadow DR)"
        )

    if is_dark or is_high_contrast:
        selected_mode = "12MP_HIGH_SNR_DR"
        target_res = (4096, 3072)
        rec_env = {
            "GPR_FAST_ENCODE": "1",
            "GPR_OPTICAL_CORING": "1",
            "GPR_SPARSE_8K": "0",
        }
        rec_8k = "Clean-Sheet Zero-DC 2x SR (`models/stock-q3-rggb14-sr-diagnostic/selected.pt`)"
    else:
        selected_mode = "50MP_SPARSE_8K"
        target_res = (8192, 6144)
        reasons.append(
            f"BRIGHT_LOW_CONTRAST_SCENE (median={p50:.1f} >= {thresholds.dark_median_counts:.0f}, "
            f"C_99/10={contrast_p99_p10:.2f} <= {thresholds.high_contrast_stops_p99_p10:.2f} stops; "
            f"encode 12 MP LL1 base + sparse Stage-0 8K innovation)"
        )
        rec_env = {
            "GPR_FAST_ENCODE": "1",
            "GPR_OPTICAL_CORING": "1",
            "GPR_SPARSE_8K": "1",
        }
        rec_8k = "Direct 50 MP VC-5 Decode (12 MP LL1 hierarchy + Sparse Stage-0 8K subbands)"

    return AutoModeDecision(
        selected_mode=selected_mode,
        target_resolution=target_res,
        is_dark=is_dark,
        is_high_contrast=is_high_contrast,
        reasons=reasons,
        recommended_env=rec_env,
        recommended_8k_delivery=rec_8k,
        radiometry=radiometry,
    )


def bin_50mp_to_12mp_rggb(raw_50mp: np.ndarray) -> np.ndarray:
    """
    Same-color 2x2 Bayer binning from (6144, 8192) RGGB to (3072, 4096) RGGB,
    matching Mission 1 12 MP readout and Stage-0 VC-5 LL1 wavelet formation.
    """
    h, w = raw_50mp.shape
    if (h % 4) != 0 or (w % 4) != 0:
        raise ValueError(f"Expected dimensions divisible by 4, got {(h, w)}")
    out = np.empty((h // 2, w // 2), dtype=np.uint16)
    f = raw_50mp.astype(np.uint32)
    # R at even rows, even cols
    out[0::2, 0::2] = ((f[0::4, 0::4] + f[0::4, 2::4] + f[2::4, 0::4] + f[2::4, 2::4] + 2) >> 2).astype(np.uint16)
    # G1 at even rows, odd cols
    out[0::2, 1::2] = ((f[0::4, 1::4] + f[0::4, 3::4] + f[2::4, 1::4] + f[2::4, 3::4] + 2) >> 2).astype(np.uint16)
    # G2 at odd rows, even cols
    out[1::2, 0::2] = ((f[1::4, 0::4] + f[1::4, 2::4] + f[3::4, 0::4] + f[3::4, 2::4] + 2) >> 2).astype(np.uint16)
    # B at odd rows, odd cols
    out[1::2, 1::2] = ((f[1::4, 1::4] + f[1::4, 3::4] + f[3::4, 1::4] + f[3::4, 3::4] + 2) >> 2).astype(np.uint16)
    return out


def execute_auto_encode(
    raw_u16: np.ndarray,
    output_gpr: Path,
    gpr_tools_bin: Path,
    thresholds: AutoModeThresholds = AutoModeThresholds(),
    quality: int = 3,
) -> Dict:
    """
    Run `analyze_bayer_scene` and encode the frame either as:
      - 12 MP (4096 x 3072) RAW when `12MP_HIGH_SNR_DR` is selected (binning 50 MP -> 12 MP if needed), or
      - 50 MP (8192 x 6144) Sparse-8K RAW (`GPR_SPARSE_8K=1`, `GPR_OPTICAL_CORING=1`) when `50MP_SPARSE_8K` is selected.
    """
    decision = analyze_bayer_scene(raw_u16, thresholds=thresholds)
    h, w = raw_u16.shape

    if decision.selected_mode == "12MP_HIGH_SNR_DR" and w == 8192 and h == 6144:
        encode_arr = bin_50mp_to_12mp_rggb(raw_u16)
    else:
        encode_arr = raw_u16

    eh, ew = encode_arr.shape
    env = dict(os.environ)
    env.update({
        "GPR_FAST_ENCODE": "1",
        "GPR_BAND_STREAM": "1",
        "GPR_COMPACT_BANDS": "1",
        "GPR_DIRECT_BANDS": "1",
        "GPR_STREAM_UNPACK": "1",
        "GPR_CHANNEL_ASM": "1",
    })
    env.update(decision.recommended_env)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_raw = Path(tmpdir) / "input.raw"
        encode_arr.tofile(tmp_raw)
        if output_gpr.exists():
            output_gpr.unlink()
        t0 = time.perf_counter()
        subprocess.run(
            [
                str(gpr_tools_bin),
                "-i",
                str(tmp_raw),
                "-o",
                str(output_gpr),
                "-w",
                str(ew),
                "-h",
                str(eh),
                "-p",
                str(ew * 2),
                "-q",
                str(quality),
            ],
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        encode_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "decision": asdict(decision),
        "encoded_width": ew,
        "encoded_height": eh,
        "gpr_size_bytes": output_gpr.stat().st_size,
        "encode_ms": encode_ms,
    }


def main():
    parser = argparse.ArgumentParser(description="Mission 1 Scene-Adaptive Auto Mode (12 MP vs 50 MP Sparse-8K)")
    parser.add_argument("--input", type=Path, required=True, help="Input .raw Bayer file")
    parser.add_argument("--width", type=int, default=8192, help="Bayer width (default: 8192)")
    parser.add_argument("--height", type=int, default=6144, help="Bayer height (default: 6144)")
    parser.add_argument("--output-gpr", type=Path, default=None, help="Optional output .gpr path to encode")
    parser.add_argument(
        "--gpr-tools",
        type=Path,
        default=Path("/tmp/gpr-native-build/source/app/gpr_tools/gpr_tools"),
        help="Path to gpr_tools binary",
    )
    args = parser.parse_args()

    raw_u16 = np.fromfile(args.input, dtype="<u2").reshape(args.height, args.width)
    if args.output_gpr is not None:
        res = execute_auto_encode(raw_u16, args.output_gpr, args.gpr_tools)
        print(json.dumps(res, indent=2))
    else:
        decision = analyze_bayer_scene(raw_u16)
        print(json.dumps(asdict(decision), indent=2))


if __name__ == "__main__":
    main()
