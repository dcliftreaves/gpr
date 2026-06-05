"""Tripwire test: detects the FUSED multi-level wavelet quality regression.

The regression: multi-level cascade attenuates ~8-23 dB on mid/low-frequency
content compared to single-level. Reproducible with horizontal stripes at
varying periods.

This test FAILS until the multi-level cascade bug (task #172) is fixed.
Once fixed, the assertions below should all pass.

Usage:
    python3 tools/test/test_multilevel_regression.py [BUILD_DIR]
"""
from __future__ import annotations
import sys, os, subprocess
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", "/Volumes/OWC_8TB/gpr_work"))
TMPDIR = Path(os.environ.get("TMPDIR", EXTERNAL_ROOT / "tmp"))
BUILD_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "build-local"
BIN = BUILD_DIR / "bin/test_fused_roundtrip"

# Pass/fail thresholds: single-level vs multi-level PSNR delta.
# These represent the expected behavior of a CORRECTLY-WORKING multi-level
# wavelet. Multi-level should be no worse than ~3 dB below single-level
# on these signals (the natural rounding accumulation across 3 levels).
PATTERNS = [
    ("period 8 stripes",  8, 3.0),
    ("period 16 stripes", 16, 3.0),
    ("period 32 stripes", 32, 3.0),
    ("period 64 stripes", 64, 3.0),
    ("period 256 stripes", 256, 3.0),
]


def run_codec(input_raw: Path, w: int, h: int, output_raw: Path, multi_level: bool) -> None:
    env = os.environ.copy()
    env["GPR_INCLUDE_LL"] = "1"
    env["FUSED_MULTI_LEVEL"] = "1" if multi_level else "0"
    r = subprocess.run([str(BIN), str(input_raw), str(w), str(h), str(output_raw)],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"codec failed rc={r.returncode}: {r.stderr.strip()}")


def psnr(ref: np.ndarray, test: np.ndarray, peak: float = 16383.0) -> float:
    mse = float(np.mean((ref.astype(np.int64) - test.astype(np.int64)) ** 2))
    if mse <= 0:
        return float("inf")
    return 10 * np.log10(peak * peak / mse)


def main() -> int:
    if not BIN.exists():
        print(f"FAIL: {BIN} not found. Build it with:")
        print("  clang -O2 source/app/test_fused_decode_roundtrip.c <libs> -o build-local/bin/test_fused_roundtrip")
        return 2

    W, H = 1024, 768
    TMPDIR.mkdir(parents=True, exist_ok=True)
    src_raw = TMPDIR / "multilevel_regression_src.raw"
    dec_raw = TMPDIR / "multilevel_regression_dec.raw"

    print(f"Multi-level regression tripwire — {W}×{H} synthetic patterns")
    print(f"{'pattern':22s}  {'SL PSNR':>8s}  {'ML PSNR':>8s}  {'delta':>8s}  result")

    failures = []
    for name, period, allowed_delta in PATTERNS:
        half = period // 2
        row = np.tile(np.array([2000] * half + [4000] * half, dtype=np.uint16),
                       W // period + 1)[:W]
        src = np.tile(row, (H, 1))
        src.tofile(src_raw)

        run_codec(src_raw, W, H, dec_raw, multi_level=False)
        dec_sl = np.fromfile(dec_raw, dtype=np.uint16).reshape(H, W)
        psnr_sl = psnr(src, dec_sl)

        run_codec(src_raw, W, H, dec_raw, multi_level=True)
        dec_ml = np.fromfile(dec_raw, dtype=np.uint16).reshape(H, W)
        psnr_ml = psnr(src, dec_ml)

        delta = psnr_ml - psnr_sl
        ok = delta >= -allowed_delta
        result = "PASS" if ok else f"FAIL (delta < -{allowed_delta:.1f} dB)"
        if not ok:
            failures.append(name)

        print(f"{name:22s}  {psnr_sl:>8.2f}  {psnr_ml:>8.2f}  {delta:>+8.2f}  {result}")

    src_raw.unlink(missing_ok=True)
    dec_raw.unlink(missing_ok=True)

    print()
    if failures:
        print(f"REGRESSION DETECTED on {len(failures)} pattern(s): {', '.join(failures)}")
        print("See docs/REGRESSION_2026-05-25.md for context.")
        print("Task #172 tracks the fix.")
        return 1
    print("All multi-level patterns within tolerance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
