"""Build (codec_dec, source_dec) training pairs for the ml2_q3_l2x2_l1x4
cranked codec. Differs from build_dataset_ml2_q3.py only in the codec env
(adds GPR_QUANT_OVERRIDE=4:48,5:48,6:24,7:384,8:384,9:576).

This pairs with a NEW BIBO_1x CNN matched to the cranked distribution
(cnn=bibo1x_ane_ml2_q3_l2x2_l1x4). The hypothesis: a CNN trained
in-distribution against this codec's output recovers the 0.020 LPIPS
over the 0.08 ceiling that the standard ml2_q3-matched CNN can't quite
close, while preserving the 45.6% file-size win.

Output: <OUT_DIR>/<base>_codec.raw   (decoded bayer from cranked ML-2)
        <OUT_DIR>/<base>_target.raw  (source bayer — REF target)
"""
import os
import sys
import time
import subprocess
import numpy as np
import rawpy

REPO = "/Users/dcliftreaves/Documents/Github/gpr"
ROUNDTRIP = f"{REPO}/build-local/bin/test_fused_roundtrip"
OUT_DIR = os.environ.get("OUT_DIR", "/Volumes/OWC_8TB/gpr_work/cnn/pairs_ml2_q3_l2x2_l1x4")
# diverse_dngs FIRST so the broadened-corpus contribution always lands in the
# build even at modest MAX_PAIRS (barnsky has thousands of bases and would
# otherwise saturate the cap on its own).
DNG_DIRS = [
    "/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs",
    "/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs",
    "/Volumes/OWC_8TB/gpr_work/cnn/source_dngs_expanded",
    "/Users/dcliftreaves/dering_proto_v2/source_dngs",
]
MAX_PAIRS = int(os.environ.get("MAX_PAIRS", "500"))

# Gate test images — never train on these (Z8Z_0067 is allowed as val source).
EXCLUDE_BASES = {"Z8Z_0001", "Z8Z_5323", "Z8Z_6693"}


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
            if base in EXCLUDE_BASES:
                continue
            seen.add(base)
            yield base, os.path.join(d, f)


def encode_cranked_ml2(src_raw_path, w, h, out_codec_raw):
    env = os.environ.copy()
    env["GPR_INCLUDE_LL"] = "1"
    env["FUSED_MULTI_LEVEL"] = "1"
    env["FUSED_WAVELET_LEVELS"] = "2"
    env["GPR_QUANT_OVERRIDE"] = "4:48,5:48,6:24,7:384,8:384,9:576"
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
        except Exception as e:
            print(f"  {base}: skip ({e})", flush=True)
            continue
        h, w = bayer.shape
        if (h, w) != (5520, 8280):
            print(f"  {base}: skip wrong dims {bayer.shape}", flush=True)
            continue
        src_raw_tmp = f"/tmp/_src_{base}.raw"
        bayer.tofile(src_raw_tmp)
        try:
            encode_cranked_ml2(src_raw_tmp, w, h, codec_path)
        except Exception as e:
            os.unlink(src_raw_tmp)
            print(f"  {base}: encode fail ({e})", flush=True)
            continue
        # Save target (the source bayer)
        bayer.tofile(target_path)
        os.unlink(src_raw_tmp)
        n_done += 1
        if n_done % 10 == 0:
            print(f"  {n_done}/{MAX_PAIRS}  ({(time.time()-t0):.0f}s)", flush=True)

    print(f"\nDone: {n_done} pairs in {OUT_DIR}, "
          f"{n_skip} skipped (already done), "
          f"{(time.time()-t0):.0f}s elapsed", flush=True)


if __name__ == "__main__":
    main()
