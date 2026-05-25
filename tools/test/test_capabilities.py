#!/usr/bin/env python3
"""test_capabilities.py — single source of truth for every capability we
claim + a regression test that asserts each one against an explicit,
human-readable criterion.

Each capability row carries:
  - what it measures (still encode/decode roundtrip, at a specific
    bit depth × resolution × quality)
  - explicit pass criterion for every metric, with direction:
      encode_ms ≤ ceiling
      decode_ms ≤ ceiling
      compress_ratio ≤ ceiling   (smaller = more compression = better)
      psnr_db ≥ floor

The test:
  1. measures live encode_ms, decode_ms, compress_ratio, psnr_db per cell
  2. compares against the stated criterion for each metric, classifying:
       MET       — passes criterion within margin
       EXCEEDED  — passes by a comfortable margin (≥ 10 % better)
       FAILED    — breaks the criterion
  3. asserts every metric is MET or EXCEEDED
  4. writes docs/CAPABILITIES.md so the doc is always in sync with the
     test results

Run from the repo root:
    python3 tools/test/test_capabilities.py            # assert mode
    python3 tools/test/test_capabilities.py --refresh  # learn baselines,
                                                         # don't assert,
                                                         # rewrite the doc

Env:
    BUILD_DIR=build-local
    ARTIFACT_DIR=/Volumes/OWC_8TB/gpr_artifacts/capabilities
    FAST=1  → skip ≥23 MP cells for quick CI
"""

from __future__ import annotations
import argparse, os, subprocess, sys, time, shutil
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np


REPO = Path(__file__).resolve().parents[2]
BUILD_DIR = Path(os.environ.get("BUILD_DIR", "build-local"))
if not BUILD_DIR.is_absolute():
    BUILD_DIR = REPO / BUILD_DIR
GTOOLS = Path(os.environ.get("GTOOLS", BUILD_DIR / "source/app/gpr_tools/gpr_tools"))

# Timing-ceiling multiplier. Debug builds run ~2-3x slower than Release, so a
# single set of locked ceilings can't gate both. Default 1.0 (Release ceilings).
# CI's Debug job sets GPR_TIMING_TOLERANCE=3.0 so a Debug ms reading that's
# within 3x of the Release ceiling still passes. Quality criteria (PSNR,
# compression ratio) ignore this — they're build-type independent.
TIMING_TOLERANCE = float(os.environ.get("GPR_TIMING_TOLERANCE", "1.0"))

DEFAULT_ART = "/Volumes/OWC_8TB/gpr_artifacts/capabilities"
if not Path("/Volumes/OWC_8TB/gpr_artifacts").exists():
    DEFAULT_ART = "/tmp/gpr-capabilities"
ART_DIR = Path(os.environ.get("ARTIFACT_DIR", DEFAULT_ART))
FAST = os.environ.get("FAST", "0") == "1"


# ---------------------------------------------------------------------------
# Capability list.
#
# Each row's `criteria` dict states the explicit pass condition per metric:
#   "encode_ms":   {"max": ms, "exceed_below": ms_for_EXCEEDED}
#   "decode_ms":   {"max": ms, "exceed_below": ms}
#   "compress_ratio": {"max": fraction, "exceed_below": fraction}
#   "psnr_db":     {"min": dB,  "exceed_above": dB}
#
# Baselines locked from a clean M3 Max run on 2026-05-24. Ceilings set
# at +50 % vs measured for time, +0.02 vs measured for compress_ratio,
# −1.5 dB vs measured for PSNR. EXCEEDED bar at +10 % better.
# ---------------------------------------------------------------------------

CAPABILITIES = [
    # ---- 1024² cells: bit-depth × Bayer × quality coverage --------------
    dict(id="still_rggb12_1024_q3",
         display="Stills · rggb12 · 1024² · q=3 (Filmscan-1)",
         kind="still_roundtrip",
         W=1024, H=1024, pf="rggb12", peak=4095, quality=3,
         criteria=dict(
             encode_ms={"max": 50, "exceed_below": 25},
             decode_ms={"max": 40, "exceed_below": 22},
             compress_ratio={"max": 0.08, "exceed_below": 0.055},
             psnr_db={"min": 42.0, "exceed_above": 44.0})),
    dict(id="still_rggb12p_1024_q3",
         display="Stills · rggb12p (packed) · 1024² · q=3",
         kind="still_roundtrip",
         W=1024, H=1024, pf="rggb12p", peak=4095, quality=3, packed=True,
         criteria=dict(
             encode_ms={"max": 50, "exceed_below": 25},
             decode_ms={"max": 40, "exceed_below": 22},
             compress_ratio={"max": 0.08, "exceed_below": 0.055},
             psnr_db={"min": 42.0, "exceed_above": 44.0})),
    dict(id="still_rggb14_1024_q3",
         display="Stills · rggb14 · 1024² · q=3",
         kind="still_roundtrip",
         W=1024, H=1024, pf="rggb14", peak=16383, quality=3,
         criteria=dict(
             encode_ms={"max": 50, "exceed_below": 25},
             decode_ms={"max": 40, "exceed_below": 25},
             compress_ratio={"max": 0.10, "exceed_below": 0.075},
             psnr_db={"min": 52.0, "exceed_above": 54.5})),
    dict(id="still_rggb14_1024_q0",
         display="Stills · rggb14 · 1024² · q=0 (Low)",
         kind="still_roundtrip",
         W=1024, H=1024, pf="rggb14", peak=16383, quality=0,
         criteria=dict(
             encode_ms={"max": 50, "exceed_below": 25},
             decode_ms={"max": 40, "exceed_below": 22},
             compress_ratio={"max": 0.05, "exceed_below": 0.035},
             psnr_db={"min": 51.5, "exceed_above": 54.0})),
    dict(id="still_rggb14_1024_q5",
         display="Stills · rggb14 · 1024² · q=5 (Filmscan-2, quality peak)",
         kind="still_roundtrip",
         W=1024, H=1024, pf="rggb14", peak=16383, quality=5,
         # q=5 is the empirical PSNR peak across the 9 quality presets on
         # real Z8 50 MP photographic content (see docs/quant_calibration_findings.md).
         # q=6/7/8 regress (task #159). Locking q=5 here so future codec
         # changes can't quietly break the actual quality peak.
         criteria=dict(
             encode_ms={"max": 50, "exceed_below": 25},
             decode_ms={"max": 50, "exceed_below": 25},
             compress_ratio={"max": 0.14, "exceed_below": 0.095},
             psnr_db={"min": 55.0, "exceed_above": 58.0})),
    dict(id="still_rggb14_1024_q8",
         display="Stills · rggb14 · 1024² · q=8 (Filmscan-5)",
         kind="still_roundtrip",
         W=1024, H=1024, pf="rggb14", peak=16383, quality=8,
         criteria=dict(
             encode_ms={"max": 60, "exceed_below": 35},
             decode_ms={"max": 60, "exceed_below": 35},
             compress_ratio={"max": 0.25, "exceed_below": 0.205},
             psnr_db={"min": 60.5, "exceed_above": 63.0})),
    dict(id="still_rggb16_1024_q3",
         display="Stills · rggb16 · 1024² · q=3",
         kind="still_roundtrip",
         W=1024, H=1024, pf="rggb16", peak=65535, quality=3,
         criteria=dict(
             encode_ms={"max": 50, "exceed_below": 25},
             decode_ms={"max": 50, "exceed_below": 27},
             compress_ratio={"max": 0.08, "exceed_below": 0.055},
             psnr_db={"min": 52.0, "exceed_above": 54.5})),
    dict(id="still_gbrg16_1024_q3",
         display="Stills · gbrg16 (alt Bayer) · 1024² · q=3",
         kind="still_roundtrip",
         W=1024, H=1024, pf="gbrg16", peak=65535, quality=3,
         criteria=dict(
             encode_ms={"max": 50, "exceed_below": 25},
             decode_ms={"max": 50, "exceed_below": 27},
             compress_ratio={"max": 0.08, "exceed_below": 0.055},
             psnr_db={"min": 52.0, "exceed_above": 54.5})),
    # ---- resolution-scaling cells ---------------------------------------
    dict(id="still_rggb12_12MP_q3",
         display="Stills · rggb12 · 12 MP (4032×3024) · q=3",
         kind="still_roundtrip",
         W=4032, H=3024, pf="rggb12", peak=4095, quality=3,
         criteria=dict(
             encode_ms={"max": 300, "exceed_below": 175},
             decode_ms={"max": 250, "exceed_below": 160},
             compress_ratio={"max": 0.07, "exceed_below": 0.05},
             psnr_db={"min": 42.0, "exceed_above": 44.0})),
    dict(id="still_rggb14_h10_q3",
         display="Stills · rggb14 · 23 MP HERO10 (5568×4176) · q=3",
         kind="still_roundtrip",
         W=5568, H=4176, pf="rggb14", peak=16383, quality=3,
         criteria=dict(
             encode_ms={"max": 600, "exceed_below": 370},
             decode_ms={"max": 600, "exceed_below": 375},
             compress_ratio={"max": 0.10, "exceed_below": 0.07},
             psnr_db={"min": 52.0, "exceed_above": 54.5}),
         fast_skip=True),
    dict(id="still_rggb14_Z8_q3",
         display="Stills · rggb14 · 50 MP Z8 (8280×5520) · q=3",
         kind="still_roundtrip",
         W=8280, H=5520, pf="rggb14", peak=16383, quality=3,
         criteria=dict(
             encode_ms={"max": 1100, "exceed_below": 740},
             decode_ms={"max": 1100, "exceed_below": 720},
             compress_ratio={"max": 0.10, "exceed_below": 0.07},
             psnr_db={"min": 52.0, "exceed_above": 54.5}),
         fast_skip=True),
    dict(id="still_rggb16_X2D_q3",
         display="Stills · rggb16 · 100 MP X2D (11664×8750) · q=3",
         kind="still_roundtrip",
         W=11664, H=8750, pf="rggb16", peak=65535, quality=3,
         criteria=dict(
             encode_ms={"max": 2500, "exceed_below": 1700},
             decode_ms={"max": 2500, "exceed_below": 1800},
             compress_ratio={"max": 0.08, "exceed_below": 0.055},
             psnr_db={"min": 52.0, "exceed_above": 54.5}),
         fast_skip=True),
]


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def synth_bayer(W, H, pf, peak, seed, packed, out: Path):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot(xx - W/2, yy - H/2) / np.hypot(W/2, H/2)
    bright = (peak * (1.0 - np.minimum(r, 1.0))).astype(np.int32)
    img = np.zeros((H, W), dtype=np.int32)
    off_r = max(1, peak // 82); off_g = max(1, peak // 20); off_b = max(1, peak // 41)
    if pf.startswith("gbrg"):
        img[0::2, 0::2] = bright[0::2, 0::2] + off_g
        img[0::2, 1::2] = bright[0::2, 1::2] + off_b
        img[1::2, 0::2] = bright[1::2, 0::2] + off_r
        img[1::2, 1::2] = bright[1::2, 1::2] + off_g
    else:
        img[0::2, 0::2] = bright[0::2, 0::2] + off_r
        img[0::2, 1::2] = bright[0::2, 1::2] + off_g
        img[1::2, 0::2] = bright[1::2, 0::2] + off_g
        img[1::2, 1::2] = bright[1::2, 1::2] + off_b
    amp = max(50, peak // 256)
    img += rng.integers(-amp, amp + 1, size=(H, W), dtype=np.int32)
    np.clip(img, 0, peak, out=img)
    if packed:
        flat = img.astype(np.uint16).ravel()
        b = np.empty(flat.size * 3 // 2, dtype=np.uint8)
        b[0::3] = (flat[0::2] & 0xFF).astype(np.uint8)
        b[1::3] = (((flat[0::2] >> 8) & 0x0F) | ((flat[1::2] & 0x0F) << 4)).astype(np.uint8)
        b[2::3] = ((flat[1::2] >> 4) & 0xFF).astype(np.uint8)
        b.tofile(out)
    else:
        img.astype("<u2").tofile(out)


def _run_timed(args):
    t0 = time.perf_counter()
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, (time.perf_counter() - t0) * 1000.0


def measure_still_roundtrip(cap, work: Path) -> Dict[str, float]:
    W, H, pf, peak, q = cap["W"], cap["H"], cap["pf"], cap["peak"], cap["quality"]
    packed = cap.get("packed", False)
    seed = abs(hash(cap["id"])) % (2**31)
    raw = work / f"{cap['id']}.raw"
    dng = work / f"{cap['id']}.dng"
    gpr = work / f"{cap['id']}.gpr"
    out = work / f"{cap['id']}_dec.dng"

    synth_bayer(W, H, pf, peak, seed, packed, raw)
    rc, _ = _run_timed([str(GTOOLS), "-i", str(raw), "-w", str(W), "-h", str(H),
                       "-x", pf, "-o", str(dng)])
    if rc != 0:
        raise RuntimeError("raw→dng failed")
    rc, encode_ms = _run_timed([str(GTOOLS), "-i", str(dng), "-q", str(q), "-o", str(gpr)])
    if rc != 0:
        raise RuntimeError("dng→gpr failed")
    gpr_bytes = gpr.stat().st_size
    rc, decode_ms = _run_timed([str(GTOOLS), "-i", str(gpr), "-o", str(out)])
    if rc != 0:
        raise RuntimeError("gpr→dng failed")

    import rawpy
    a = rawpy.imread(str(dng)); src = a.raw_image.copy().astype(np.float64); a.close()
    b = rawpy.imread(str(out)); dec = b.raw_image.copy().astype(np.float64); b.close()
    if src.shape != dec.shape:
        raise RuntimeError(f"shape mismatch {src.shape} vs {dec.shape}")
    mse = float(((src - dec) ** 2).mean())
    psnr = 10 * np.log10(peak * peak / mse) if mse > 0 else float("inf")
    raw_equiv = W * H * 2
    return dict(encode_ms=encode_ms, decode_ms=decode_ms,
                compress_ratio=gpr_bytes / raw_equiv, psnr_db=psnr,
                gpr_bytes=gpr_bytes, raw_bytes=raw_equiv)


# ---------------------------------------------------------------------------
# Criterion classification: MET / EXCEEDED / FAILED
# ---------------------------------------------------------------------------

def classify(value: float, crit: Dict[str, Any]) -> Tuple[str, str]:
    """Classify a measured value against a criterion dict.
    Returns (verdict, criterion_text)."""
    if "max" in crit:
        # lower is better
        cmax = crit["max"]
        excd = crit.get("exceed_below")
        text = f"≤ {cmax:g}"
        if value > cmax:
            return "FAILED", text
        if excd is not None and value <= excd:
            return "EXCEEDED", text
        return "MET", text
    if "min" in crit:
        # higher is better
        cmin = crit["min"]
        excd = crit.get("exceed_above")
        text = f"≥ {cmin:g}"
        if value < cmin:
            return "FAILED", text
        if excd is not None and value >= excd:
            return "EXCEEDED", text
        return "MET", text
    return "MET", "(no criterion)"


METRIC_ORDER = [
    ("encode_ms",      "Encode",        "ms",  "{:.1f}"),
    ("decode_ms",      "Decode",        "ms",  "{:.1f}"),
    ("compress_ratio", "Size vs raw",   "%",   "{:.2%}"),
    ("psnr_db",        "Roundtrip PSNR","dB",  "{:.2f}"),
]


def check_cap(cap: dict, m: Dict[str, float]) -> Tuple[str, list]:
    """Returns (overall_verdict, [(metric_id, value, verdict, criterion_text)])."""
    crits = cap["criteria"]
    rows = []
    overall = "MET"
    has_exceeded = False
    for mid, *_ in METRIC_ORDER:
        if mid not in crits:
            continue
        # Apply timing tolerance only to ms-based metrics; quality/size criteria
        # are build-type independent and stay strict.
        crit = crits[mid]
        if mid in ("encode_ms", "decode_ms") and TIMING_TOLERANCE != 1.0:
            crit = dict(crit)
            if "max" in crit:
                crit["max"] = crit["max"] * TIMING_TOLERANCE
            if "exceed_below" in crit and crit["exceed_below"] is not None:
                crit["exceed_below"] = crit["exceed_below"] * TIMING_TOLERANCE
        v, c = classify(m[mid], crit)
        rows.append((mid, m[mid], v, c))
        if v == "FAILED":
            overall = "FAILED"
        elif v == "EXCEEDED" and overall != "FAILED":
            has_exceeded = True
    if overall == "MET" and has_exceeded:
        # If at least one metric exceeded and none failed, mark overall as EXCEEDED.
        overall = "EXCEEDED"
    return overall, rows


# ---------------------------------------------------------------------------
# Markdown emission
# ---------------------------------------------------------------------------

VERDICT_ICONS = {"MET": "✅ MET", "EXCEEDED": "✨ EXCEEDED", "FAILED": "❌ FAILED"}


def emit_markdown(rows: list, out_path: Path):
    """rows: list of (cap, measured, overall_verdict, per_metric_rows)."""
    lines = [
        "# Capabilities — measured, criteria-stated, regression-tested",
        "",
        "Each row is one capability we claim. The four metric columns show the",
        "**measured value** alongside the **explicit criterion** the test asserts,",
        "and the verdict — MET, EXCEEDED, or FAILED.",
        "",
        "- **MET**     — measured value passes the stated criterion.",
        "- **EXCEEDED** — measured value comfortably beats the criterion",
        "  (≥ 10 % better on time/size metrics, ≥ 2 dB better on PSNR).",
        "- **FAILED**  — measured value breaks the criterion.",
        "",
        "Regenerated on every run of `tools/test/test_capabilities.py`. Adding a",
        "capability = adding one row to that script with its criteria.",
        "",
        "## Summary",
        "",
    ]
    n_met  = sum(1 for _, _, v, _ in rows if v == "MET")
    n_exc  = sum(1 for _, _, v, _ in rows if v == "EXCEEDED")
    n_fail = sum(1 for _, _, v, _ in rows if v == "FAILED")
    lines += [
        f"- **{n_exc}** EXCEEDED",
        f"- **{n_met}** MET",
        f"- **{n_fail}** FAILED",
        f"- last run: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- build dir: `{BUILD_DIR.relative_to(REPO) if str(BUILD_DIR).startswith(str(REPO)) else BUILD_DIR}`",
        "",
        "## Stills · encode → decode → PSNR roundtrip",
        "",
        "| Capability | Encode | Decode | Compressed size | Roundtrip PSNR | Overall |",
        "|---|---|---|---|---|---|",
    ]
    for cap, m, overall, metric_rows in rows:
        if cap["kind"] != "still_roundtrip":
            continue
        cells = []
        for mid, name, unit, fmt in METRIC_ORDER:
            mr = next((r for r in metric_rows if r[0] == mid), None)
            if mr is None:
                cells.append("—")
                continue
            _, val, verdict, crit_text = mr
            v_str = fmt.format(val if mid != "compress_ratio" else val) + (
                "" if mid == "compress_ratio" else f" {unit}"
            )
            crit_str = crit_text + (f" {unit}" if mid != "compress_ratio" else "")
            cells.append(f"{v_str}<br/>_{crit_str}_<br/>{VERDICT_ICONS[verdict]}")
        lines.append(f"| {cap['display']} | {' | '.join(cells)} | **{VERDICT_ICONS[overall]}** |")

    lines += [
        "",
        "## Metric definitions",
        "",
        "- **Encode ms** — wall-clock time for `gpr_tools dng→gpr` at the stated quality.",
        "- **Decode ms** — wall-clock time for `gpr_tools gpr→dng`.",
        "- **Compressed size** — output GPR bytes ÷ raw bayer bytes (W·H·2). Lower = more compression.",
        "- **Roundtrip PSNR** — bayer-domain PSNR (decoded vs original synth raw), peak set per bit depth.",
        "",
        "## Test methodology",
        "",
        "Each cell uses a deterministic synthetic Bayer fixture (radial gradient +",
        "per-channel DC offsets + noise) sized to match the stated resolution.",
        "The fixture is designed so 3-level wavelet LL coefficients exceed 32767,",
        "exercising the sign-extension path that has historically been a regression",
        "hotspot. All measurements are wall-clock, single invocation; no warmup or",
        "pinning, because in production users invoke `gpr_tools` once per file.",
        "",
        "Run `python3 tools/test/test_capabilities.py` to assert; add `--refresh`",
        "to recompute baselines (don't commit the script changes without revisiting",
        "tolerances).",
        "",
    ]
    out_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="measure + rewrite doc only; don't assert; print baseline-update suggestions")
    ap.add_argument("--filter", default=None,
                    help="substring filter on capability id")
    args = ap.parse_args()

    if not GTOOLS.exists():
        print(f"ERROR: gpr_tools not at {GTOOLS}", file=sys.stderr)
        return 2

    ART_DIR.mkdir(parents=True, exist_ok=True)
    work = ART_DIR / "live"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    print(f"=== test_capabilities · {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"GTOOLS    : {GTOOLS}")
    print(f"ARTIFACT  : {ART_DIR}")
    print(f"FAST      : {FAST}")
    print(f"refresh   : {args.refresh}")
    print()

    rows = []
    any_failed = False
    print(f"{'Capability':<55s} {'enc(ms)':>9s} {'dec(ms)':>9s} {'ratio':>7s} {'PSNR(dB)':>9s}  overall")
    print("-" * 110)
    for cap in CAPABILITIES:
        if args.filter and args.filter not in cap["id"]:
            continue
        if FAST and cap.get("fast_skip"):
            print(f"  {cap['display']:<53s} ... (FAST: skipped)")
            continue
        try:
            if cap["kind"] == "still_roundtrip":
                m = measure_still_roundtrip(cap, work)
            else:
                continue
        except Exception as e:
            print(f"  {cap['display']:<53s} ... ERROR: {e}")
            rows.append((cap, dict(encode_ms=0, decode_ms=0, compress_ratio=0, psnr_db=0),
                        "FAILED", [(mid, 0.0, "FAILED", "n/a") for mid, *_ in METRIC_ORDER]))
            any_failed = True
            continue
        overall, mr = check_cap(cap, m)
        if overall == "FAILED":
            any_failed = True
        print(f"  {cap['display']:<55s} {m['encode_ms']:>8.1f} {m['decode_ms']:>8.1f}  "
              f"{m['compress_ratio']*100:>6.2f}% {m['psnr_db']:>8.2f}  {overall}")
        rows.append((cap, m, overall, mr))

    docs = REPO / "docs/CAPABILITIES.md"
    docs.parent.mkdir(exist_ok=True)
    emit_markdown(rows, docs)
    print()
    print(f"=== docs/CAPABILITIES.md written ({len(rows)} rows) ===")

    if args.refresh:
        print()
        print("=== refresh: copy these baselines into the script if you accept them ===")
        for cap, m, *_ in rows:
            print(f"  {cap['id']}:")
            for mid, _, unit, fmt in METRIC_ORDER:
                if mid not in cap["criteria"]:
                    continue
                v = m[mid]
                if mid == "compress_ratio":
                    print(f"    {mid}: {v:.3f}  (suggest max={v*1.5:.2f}, exceed_below={v*0.9:.3f})")
                elif mid == "psnr_db":
                    print(f"    {mid}: {v:.2f}  (suggest min={v-1.5:.1f}, exceed_above={v+0.3:.2f})")
                else:
                    print(f"    {mid}: {v:.0f}  (suggest max={int(v*1.5)}, exceed_below={int(v*0.85)})")
        return 0

    print()
    if any_failed:
        n_fail = sum(1 for _, _, v, _ in rows if v == "FAILED")
        print(f"❌ {n_fail} capability/capabilities FAILED")
        return 1
    n_exc = sum(1 for _, _, v, _ in rows if v == "EXCEEDED")
    n_met = sum(1 for _, _, v, _ in rows if v == "MET")
    print(f"✅ {n_exc} EXCEEDED, {n_met} MET ({len(rows)} total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
