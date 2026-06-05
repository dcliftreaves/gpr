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
import tempfile
from pathlib import Path
import numpy as np

def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root()))
TMPDIR = Path(os.environ.get("TMPDIR", EXTERNAL_ROOT / "tmp"))


def run(backend, ckpt, dng, raw_out):
    # Use a known-bad output .mov that the tool overwrites
    TMPDIR.mkdir(parents=True, exist_ok=True)
    out_mov = str(TMPDIR / "validate_dummy.mov")
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
    artifact_root = Path(os.environ.get("GPR_ARTIFACT_ROOT", EXTERNAL_ROOT / "artifacts"))
    model_root = Path(os.environ.get("GPR_MODEL_ROOT", EXTERNAL_ROOT / "models"))
    ap.add_argument("--dng", default=str(EXTERNAL_ROOT / "external/dering_proto_v2/source_dngs/Z8Z_1579.dng"))
    ap.add_argument("--coreml-ckpt", default=str(model_root / "super_res_F_aa_off_ep8.mlpackage"))
    ap.add_argument("--metal-ckpt", default=str(artifact_root / "weights/F_weights"))
    ap.add_argument("--w", type=int, default=8280)
    ap.add_argument("--h", type=int, default=5520)
    args = ap.parse_args()

    TMPDIR.mkdir(parents=True, exist_ok=True)
    coreml_raw = str(TMPDIR / "bayer_coreml.raw")
    metal_raw = str(TMPDIR / "bayer_metal.raw")
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
