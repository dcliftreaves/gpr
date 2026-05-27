"""Build super-res NPZ tile pairs from ML-2 q=3 + decimate=2 codec output.

NPZ schema (matches the historical super-res training NPZ that train.py
loads for the F_ane variant):
  codec_R/G1/G2/B  shape (N, 128, 128)  uint16   <- half-res codec output
  tgt_R/G1/G2/B    shape (N, 256, 256)  uint16   <- full-res source target
  src              shape (N,)           int32
  src_lookup_names shape (n_imgs,)      object

The 2x dim mismatch tells train.py to use the super-res code path
(model.sr2x=True): bicubic-2x baseline + CNN residual = 256×256 output
to match tgt.

Tile geometry per source image:
  Codec bayer plane:  2070 × 1380 (per channel after deinterleave at 4140×2760)
  Target bayer plane: 4140 × 2760
  Codec tile 128 × 128 corresponds to a target tile 256 × 256 at the same
  pixel coords scaled 2×. Stride sweeps both in lock-step.
"""
import os
import sys
import time
import zipfile
import shutil
import numpy as np

PAIRS_DIR = os.environ.get("PAIRS_DIR", "/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3_dec2")
OUT_NPZ = os.environ.get("TILES_OUT", "/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2.npz")
TILE_CODEC = 128
TILE_TGT = 256
STRIDE_CODEC = int(os.environ.get("TILES_STRIDE", "128"))  # 128 codec ≡ 256 tgt
STRIDE_TGT = STRIDE_CODEC * 2

CODEC_DIMS = (2760, 4140)         # full bayer, before deinterleave (H, W)
TARGET_DIMS = (5520, 8280)        # full bayer
CODEC_BYTES = CODEC_DIMS[0] * CODEC_DIMS[1] * 2
TARGET_BYTES = TARGET_DIMS[0] * TARGET_DIMS[1] * 2


def deinterleave(bayer_u16):
    return (bayer_u16[0::2, 0::2], bayer_u16[0::2, 1::2],
            bayer_u16[1::2, 0::2], bayer_u16[1::2, 1::2])


def main():
    bases = []
    for f in sorted(os.listdir(PAIRS_DIR)):
        if not f.endswith("_codec.raw"):
            continue
        cp = os.path.join(PAIRS_DIR, f)
        tp = os.path.join(PAIRS_DIR, f[:-len("_codec.raw")] + "_target.raw")
        if os.path.getsize(cp) != CODEC_BYTES or os.path.getsize(tp) != TARGET_BYTES:
            print(f"  skip {f}: size mismatch")
            continue
        bases.append(f[:-len("_codec.raw")])
    print(f"pairs to tile: {len(bases)}", flush=True)

    accum = {k: [] for k in ["codec_R", "codec_G1", "codec_G2", "codec_B",
                             "tgt_R",   "tgt_G1",   "tgt_G2",   "tgt_B"]}
    src_ids = []
    src_names = []
    t0 = time.time()
    for sid, base in enumerate(bases):
        src_names.append(base)
        codec = np.fromfile(os.path.join(PAIRS_DIR, f"{base}_codec.raw"),
                            dtype=np.uint16).reshape(CODEC_DIMS)
        tgt   = np.fromfile(os.path.join(PAIRS_DIR, f"{base}_target.raw"),
                            dtype=np.uint16).reshape(TARGET_DIMS)
        c_planes = deinterleave(codec)   # each (1380, 2070)
        t_planes = deinterleave(tgt)     # each (2760, 4140)
        Hc, Wc = c_planes[0].shape
        n_tiles = 0
        for yc in range(0, Hc - TILE_CODEC + 1, STRIDE_CODEC):
            for xc in range(0, Wc - TILE_CODEC + 1, STRIDE_CODEC):
                yt, xt = yc * 2, xc * 2
                for ci, key in enumerate(["codec_R", "codec_G1", "codec_G2", "codec_B"]):
                    accum[key].append(c_planes[ci][yc:yc+TILE_CODEC, xc:xc+TILE_CODEC])
                for ci, key in enumerate(["tgt_R", "tgt_G1", "tgt_G2", "tgt_B"]):
                    accum[key].append(t_planes[ci][yt:yt+TILE_TGT, xt:xt+TILE_TGT])
                src_ids.append(sid)
                n_tiles += 1
        if sid % 25 == 0 or sid < 3:
            print(f"  [{sid+1}/{len(bases)}] {base}: {n_tiles} tiles "
                  f"(t={time.time()-t0:.0f}s)", flush=True)

    # Stream-write each array to a temp dir, then bundle into an NPZ —
    # keeps working-set memory well under what `np.savez(**out)` would use.
    tmp_dir = OUT_NPZ + ".staging"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    print(f"\nstacking arrays...", flush=True)
    for k in list(accum.keys()):
        arr = np.stack(accum.pop(k)).astype(np.uint16)
        print(f"  {k}: {arr.shape}  ({arr.nbytes/(1024**3):.2f} GB) → saving",
              flush=True)
        np.save(os.path.join(tmp_dir, k + ".npy"), arr)
        del arr
    np.save(os.path.join(tmp_dir, "src.npy"), np.array(src_ids, dtype=np.int32))
    np.save(os.path.join(tmp_dir, "src_lookup_names.npy"),
            np.array(src_names, dtype=object), allow_pickle=True)
    print(f"assembling {OUT_NPZ}...", flush=True)
    with zipfile.ZipFile(OUT_NPZ, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for fn in sorted(os.listdir(tmp_dir)):
            zf.write(os.path.join(tmp_dir, fn), arcname=fn)
    shutil.rmtree(tmp_dir)
    print(f"DONE. Total {time.time()-t0:.0f}s, file size: "
          f"{os.path.getsize(OUT_NPZ)/(1024**3):.2f} GB", flush=True)


if __name__ == "__main__":
    main()
