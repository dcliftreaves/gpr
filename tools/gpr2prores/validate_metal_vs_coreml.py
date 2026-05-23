"""Validate SuperResMetal output vs SuperResCNN (CoreML) output on the same input.

Approach: run both backends on the same DNG via gpr2prores in --no-cnn-validate
mode (a hidden mode I'll add), or simpler: extract a Bayer plane from both
.mov files and compare. ProRes is lossy (chroma + 10-bit) so direct decode
comparison loses precision. Instead, dump the *Bayer* output to a file before
demosaic.

For this validation script we use a separate harness: we run a Python
PyTorch reference on the F backbone, save the residual, and compare it to
the Metal residual extracted via a small ObjC test tool.

Simpler: dump the bayer output of the CNN to a .raw file. Compare the two
.raw files numerically (per-pixel mean abs diff).
"""
import argparse
import os
import subprocess
import sys
import numpy as np


def run(backend, ckpt, dng, raw_out):
    # Use a known-bad output .mov that the tool overwrites
    out_mov = "/tmp/validate_dummy.mov"
    env = os.environ.copy()
    env["SUPERRES_DUMP_BAYER"] = raw_out
    args = [
        "./gpr2prores",
        "--max-frames", "1",
        "--cnn-backend", backend,
        "--ckpt", ckpt,
        dng,
        out_mov,
    ]
    r = subprocess.run(args, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout); print(r.stderr)
        raise SystemExit(f"backend {backend} failed: {r.returncode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dng", default="/Users/dcliftreaves/Documents/dering_proto_v2/source_dngs/Z8Z_1579.dng")
    ap.add_argument("--coreml-ckpt", default="/tmp/super_res_F_aa_off_ep8.mlpackage")
    ap.add_argument("--metal-ckpt", default="/tmp/F_weights")
    ap.add_argument("--w", type=int, default=8280)
    ap.add_argument("--h", type=int, default=5520)
    args = ap.parse_args()

    coreml_raw = "/tmp/bayer_coreml.raw"
    metal_raw  = "/tmp/bayer_metal.raw"
    run("coreml",   args.coreml_ckpt, args.dng, coreml_raw)
    run("mpsgraph", args.metal_ckpt,  args.dng, metal_raw)

    a = np.fromfile(coreml_raw, dtype=np.uint16).reshape(args.h, args.w)
    b = np.fromfile(metal_raw,  dtype=np.uint16).reshape(args.h, args.w)

    diff = a.astype(np.int32) - b.astype(np.int32)
    print(f"  CoreML output stats: min={a.min()} max={a.max()} mean={a.mean():.1f}")
    print(f"  Metal  output stats: min={b.min()} max={b.max()} mean={b.mean():.1f}")
    print(f"  max abs diff: {np.abs(diff).max()}  mean abs diff: {np.abs(diff).mean():.2f}")
    print(f"  diff p99: {np.percentile(np.abs(diff), 99):.1f}")
    print(f"  > 16 (~0.1% of full range): {(np.abs(diff) > 16).sum()} / {a.size}  ({100*(np.abs(diff) > 16).sum()/a.size:.2f}%)")


if __name__ == "__main__":
    main()
