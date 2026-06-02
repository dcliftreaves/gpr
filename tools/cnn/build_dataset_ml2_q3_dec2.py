"""Build (codec_dec, source) training pairs for ML-2 q=3 + decimate=2 codec.

For the BIBO_2x super-res retrain matched to the embedded-capture pipeline.

  codec output: 4140x2760 bayer (half-res, the actual Pi 5 capture data)
  target:       8280x5520 bayer (full-res, the desktop's restoration target)

Stored as separate raw files; tile builder packs them into the NPZ format
the existing train.py reads (super-res layout: codec_R 128×128, tgt_R 256×256).
"""
import os
import sys
import time
import subprocess
import numpy as np
import rawpy

REPO = "/Users/dcliftreaves/Documents/Github/gpr"
ROUNDTRIP = f"{REPO}/build-local/bin/test_fused_roundtrip"
OUT_DIR = os.environ.get("OUT_DIR", "/Volumes/OWC_8TB/gpr_work/cnn/pairs_ml2_q3_dec2")
_DEFAULT_DNG_DIRS = [
    "/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs",
    "/Volumes/OWC_8TB/gpr_work/cnn/source_dngs_expanded",
    "/Users/dcliftreaves/dering_proto_v2/source_dngs",
]
# Allow override via DNG_DIRS=dir1:dir2:dir3 — used to build pair sets that
# target only a specific corpus subset (e.g. just the 78 OOD DNGs for the
# corpus-axis BIDO retrain) without touching the historical pair dirs.
_env_dng_dirs = os.environ.get("DNG_DIRS", "").strip()
DNG_DIRS = ([d for d in _env_dng_dirs.split(":") if d]
            if _env_dng_dirs else _DEFAULT_DNG_DIRS)
MAX_PAIRS = int(os.environ.get("MAX_PAIRS", "200"))


def enumerate_dngs():
    seen = set()
    for d in DNG_DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".dng"):
                continue
            base = os.path.splitext(f)[0]
            if base in seen:
                continue
            seen.add(base)
            yield base, os.path.join(d, f)


def encode_decode(src_raw_path, w, h, out_codec_raw):
    env = os.environ.copy()
    env["GPR_INCLUDE_LL"] = "1"
    env["FUSED_MULTI_LEVEL"] = "1"
    env["FUSED_WAVELET_LEVELS"] = "2"
    env["GPR_COL_DECIMATE"] = "2"
    env["GPR_ROW_DECIMATE"] = "2"
    cmd = [ROUNDTRIP, src_raw_path, str(w), str(h), out_codec_raw]
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"codec failed: {res.stderr[-200:]}")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    n_done = 0
    n_skip = 0
    t0 = time.time()
    for base, dng in enumerate_dngs():
        if n_done >= MAX_PAIRS:
            break
        codec_path = os.path.join(OUT_DIR, f"{base}_codec.raw")
        target_path = os.path.join(OUT_DIR, f"{base}_target.raw")
        if os.path.exists(codec_path) and os.path.exists(target_path):
            n_skip += 1
            continue
        try:
            r = rawpy.imread(dng)
            bayer = r.raw_image.copy().astype("<u2")
            r.close()
        except Exception as e:
            print(f"  SKIP {base}: rawpy {e}", flush=True)
            continue
        h, w = bayer.shape
        if (h, w) != (5520, 8280):
            print(f"  SKIP {base}: wrong dims {bayer.shape}", flush=True)
            continue
        tmp_src = os.path.join(OUT_DIR, f"{base}_src.raw.tmp")
        bayer.tofile(tmp_src)
        try:
            encode_decode(tmp_src, w, h, codec_path)
        except Exception as e:
            print(f"  FAIL {base}: {e}", flush=True)
            os.unlink(tmp_src)
            continue
        # Codec emits half-res bayer; target is the full-res source bayer.
        expected = (h // 2) * (w // 2) * 2
        if os.path.getsize(codec_path) != expected:
            print(f"  WRONG SIZE {base}: got {os.path.getsize(codec_path)} expected {expected}",
                  flush=True)
            os.unlink(tmp_src); os.unlink(codec_path)
            continue
        bayer.tofile(target_path)
        os.unlink(tmp_src)
        n_done += 1
        elapsed = time.time() - t0
        rate = n_done / elapsed if elapsed > 0 else 0
        if n_done % 10 == 0 or n_done <= 3:
            print(f"  [{n_done}/{MAX_PAIRS}] {base} ({elapsed:.0f}s, rate={rate:.2f}/s)",
                  flush=True)
    print(f"\nDONE. {n_done} new pairs, {n_skip} pre-existing in {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
