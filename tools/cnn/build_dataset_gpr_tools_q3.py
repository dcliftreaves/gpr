"""Build (legacy_q3_decoded_bayer, source_bayer) training pairs for a
BIBO_1x CNN matched to the legacy gpr_tools q=3 encoder.

Goal: target the actual production-stills shipping goal — codec at q=3
(7.8 MB on Z8 50MP) + matched CNN → visually equivalent to q=8 (16 MB).
That's ~50% smaller files than legacy q=8 alone and ~70% smaller than
the current FUSED-based ship.

For each source DNG:
  1. Encode via gpr_tools DNG → GPR at q=3 (writes 7.8 MB-ish .gpr)
  2. Decode via gpr_tools GPR → DNG (writes uncompressed DNG)
  3. Read decoded bayer from output DNG
  4. Save (decoded_bayer, source_bayer) pair as <base>_codec.raw + <base>_target.raw
"""
import os
import sys
import time
import subprocess
import tempfile
import numpy as np
import tifffile

REPO = "/Users/dcliftreaves/Documents/Github/gpr"
GTOOLS = f"{REPO}/build-local/source/app/gpr_tools/gpr_tools"
OUT_DIR = os.environ.get("OUT_DIR", "/Volumes/OWC_8TB/gpr_cnn/pairs_gpr_tools_q3")
DNG_DIRS = [
    "/Volumes/OWC_8TB/barnsky_full_dngs",
    "/Volumes/OWC_8TB/gpr_cnn/source_dngs_expanded",
    "/Users/dcliftreaves/dering_proto_v2/source_dngs",
]
MAX_PAIRS = int(os.environ.get("MAX_PAIRS", "200"))
QUALITY = int(os.environ.get("QUALITY", "3"))


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


def find_bayer_page(pages):
    """Return the largest 2D uint16 page — the bayer plane."""
    best = None
    best_size = 0
    for p in pages:
        try:
            sh = p.shape
            if len(sh) == 2:
                sz = sh[0] * sh[1]
                if sz > best_size:
                    best = p
                    best_size = sz
        except Exception:
            pass
        # SubIFD
        try:
            sub_pages = getattr(p, "pages", None) or []
            for sp in sub_pages:
                try:
                    sh = sp.shape
                    if len(sh) == 2:
                        sz = sh[0] * sh[1]
                        if sz > best_size:
                            best = sp
                            best_size = sz
                except Exception:
                    pass
        except Exception:
            pass
    return best


def encode_decode_legacy(src_dng, out_codec_raw_path):
    """Encode src_dng with gpr_tools at q=QUALITY, decode, return decoded bayer."""
    with tempfile.TemporaryDirectory() as tmp:
        gpr_path = f"{tmp}/out.gpr"
        dng_path = f"{tmp}/out.dng"
        # Encode
        r = subprocess.run(
            [GTOOLS, "-i", src_dng, "-q", str(QUALITY), "-o", gpr_path],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            raise RuntimeError(f"encode failed: {r.stderr[-200:]}")
        # Decode
        r = subprocess.run(
            [GTOOLS, "-i", gpr_path, "-o", dng_path],
            capture_output=True, text=True
        )
        if r.returncode != 0:
            raise RuntimeError(f"decode failed: {r.stderr[-200:]}")
        # Read decoded bayer
        with tifffile.TiffFile(dng_path) as tf:
            page = find_bayer_page(tf.pages)
            if page is None:
                raise RuntimeError("no bayer page in decoded DNG")
            bayer = page.asarray().astype("<u2")
        bayer.tofile(out_codec_raw_path)
        return bayer.shape


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
        # Read source bayer
        try:
            with tifffile.TiffFile(dng) as tf:
                page = find_bayer_page(tf.pages)
                if page is None:
                    print(f"  {base}: skip (no bayer page)", flush=True)
                    continue
                source_bayer = page.asarray().astype("<u2")
        except Exception as e:
            print(f"  {base}: skip ({e})", flush=True)
            continue

        try:
            dec_shape = encode_decode_legacy(dng, codec_path)
        except Exception as e:
            print(f"  {base}: enc/dec fail ({e})", flush=True)
            continue

        # Sanity: shapes match
        if dec_shape != source_bayer.shape:
            print(f"  {base}: shape mismatch dec={dec_shape} vs src={source_bayer.shape}",
                  flush=True)
            os.unlink(codec_path)
            continue

        # Save target as source bayer
        source_bayer.tofile(target_path)
        n_done += 1
        if n_done % 5 == 0:
            print(f"  {n_done}/{MAX_PAIRS}  ({(time.time()-t0):.0f}s)", flush=True)

    print(f"\nDone: {n_done} pairs in {OUT_DIR}, {n_skip} skipped, "
          f"{(time.time()-t0):.0f}s elapsed", flush=True)


if __name__ == "__main__":
    main()
