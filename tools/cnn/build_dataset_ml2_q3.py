"""Build (codec_dec, source_dec) training pairs for ML-2 q=3 codec.

Output: <OUT_DIR>/<base>_codec.raw   (decoded bayer from ML-2 q=3 codec)
        <OUT_DIR>/<base>_target.raw  (the source bayer — REF target)

Pairs are full-resolution Z8 50 MP (8280x5520). No decimation.

This pairs with the BIBO_1x CNN architecture (input=output=4ch bayer at
1x). Pair the resulting checkpoint with codec=ml2_q3 in
pipelines/registry.json under a `cnn=bibo1x_ane_ml2_q3` entry once
trained, then run the gate.

Usage:
  OUT_DIR=/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3 \
      python3 tools/cnn/build_dataset_ml2_q3.py
"""
import os
import sys
import time
import subprocess
import numpy as np
import rawpy

REPO = "/Users/dcliftreaves/Documents/Github/gpr"
ROUNDTRIP = f"{REPO}/build-local/bin/test_fused_roundtrip"
OUT_DIR = os.environ.get("OUT_DIR", "/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3")
DNG_DIRS = [
    "/Volumes/OWC_8TB/barnsky_full_dngs",
    "/Volumes/OWC_8TB/gpr_cnn/source_dngs_expanded",
    "/Users/dcliftreaves/dering_proto_v2/source_dngs",
]
MAX_PAIRS = int(os.environ.get("MAX_PAIRS", "200"))  # cap to keep storage sane


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
            print(f"  SKIP {base}: rawpy error {e}", flush=True)
            continue
        h, w = bayer.shape
        # Z8 is 8280x5520; accept that exact shape only
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
        # Save target as raw
        bayer.tofile(target_path)
        os.unlink(tmp_src)
        n_done += 1
        elapsed = time.time() - t0
        rate = n_done / elapsed if elapsed > 0 else 0
        eta = (MAX_PAIRS - n_done - n_skip) / rate if rate > 0 else 0
        if n_done % 5 == 0 or n_done <= 3:
            print(f"  [{n_done}/{MAX_PAIRS}] {base} ({elapsed:.0f}s, rate={rate:.2f}/s, eta={eta:.0f}s)",
                  flush=True)
    print(f"\nDONE. {n_done} new pairs, {n_skip} pre-existing in {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
