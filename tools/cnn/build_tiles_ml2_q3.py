"""Build NPZ tile pairs from ML-2 q=3 codec output (FULL resolution).

For the BIBO_1x retrain on ML-2 q=3. Codec and target are BOTH at full
Z8 resolution (8280x5520 bayer → 4140x2760 per deinterleaved plane).
That's different from the historical super-res NPZ which had tgt at 2x
the codec resolution.

NPZ schema (compatible with tools/cnn/train.py's loader):
  codec_R/G1/G2/B  shape (N, 128, 128)  uint16
  tgt_R/G1/G2/B    shape (N, 128, 128)  uint16   <- SAME as codec, not 2x
  src              shape (N,)           int32    image-id lookup
  src_lookup_names shape (n_imgs,)      object   id -> name

train.py with model.sr2x=False (F_ane_no_sr) calls
`downsample_tgt_to_codec_dims(tgt)` to halve tgt to match codec dims;
that's a no-op-by-shrinkage when both are 128x128, so the patched
train script must skip that downsample. See train_native_1x.py.
"""
import os
import sys
import time
import numpy as np

PAIRS_DIR = os.environ.get("PAIRS_DIR", "/Volumes/OWC_8TB/gpr_work/cnn/pairs_ml2_q3")
OUT_NPZ = os.environ.get("TILES_OUT", "/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3.npz")
TILE = 128
# Default stride=256 keeps total tile count around 33K — matches the historical
# super-res NPZ size that the trainer is tuned for, and avoids OOM during stacking.
STRIDE = int(os.environ.get("TILES_STRIDE", "256"))
TARGET_BAYER_DIMS = (5520, 8280)  # H, W
EXPECTED_BYTES = TARGET_BAYER_DIMS[0] * TARGET_BAYER_DIMS[1] * 2


def deinterleave(bayer_u16):
    R  = bayer_u16[0::2, 0::2]
    G1 = bayer_u16[0::2, 1::2]
    G2 = bayer_u16[1::2, 0::2]
    B  = bayer_u16[1::2, 1::2]
    return R, G1, G2, B


def main():
    bases = []
    for f in sorted(os.listdir(PAIRS_DIR)):
        if not f.endswith("_codec.raw"):
            continue
        path = os.path.join(PAIRS_DIR, f)
        if os.path.getsize(path) != EXPECTED_BYTES:
            continue
        base = f[:-len("_codec.raw")]
        target = os.path.join(PAIRS_DIR, f"{base}_target.raw")
        if not os.path.exists(target):
            continue
        bases.append(base)
    print(f"pairs to tile: {len(bases)}", flush=True)

    t0 = time.time()
    accum = {k: [] for k in ["codec_R", "codec_G1", "codec_G2", "codec_B",
                             "tgt_R",   "tgt_G1",   "tgt_G2",   "tgt_B"]}
    src_ids = []
    src_names = []
    for sid, base in enumerate(bases):
        src_names.append(base)
        codec = np.fromfile(os.path.join(PAIRS_DIR, f"{base}_codec.raw"),
                            dtype=np.uint16).reshape(TARGET_BAYER_DIMS)
        tgt   = np.fromfile(os.path.join(PAIRS_DIR, f"{base}_target.raw"),
                            dtype=np.uint16).reshape(TARGET_BAYER_DIMS)
        c_planes = deinterleave(codec)
        t_planes = deinterleave(tgt)
        H, W = c_planes[0].shape  # plane dims
        n_tiles = 0
        for y in range(0, H - TILE + 1, STRIDE):
            for x in range(0, W - TILE + 1, STRIDE):
                for ci, key in enumerate(["codec_R", "codec_G1", "codec_G2", "codec_B"]):
                    accum[key].append(c_planes[ci][y:y+TILE, x:x+TILE])
                for ci, key in enumerate(["tgt_R", "tgt_G1", "tgt_G2", "tgt_B"]):
                    accum[key].append(t_planes[ci][y:y+TILE, x:x+TILE])
                src_ids.append(sid)
                n_tiles += 1
        if sid % 10 == 0 or sid < 5:
            print(f"  [{sid+1}/{len(bases)}] {base}: {n_tiles} tiles (t={time.time()-t0:.0f}s)",
                  flush=True)

    print(f"\nstacking arrays (memory-conservative)...", flush=True)
    # Stack and write one array at a time; free intermediate lists to keep
    # working set small. Build a temp dir of .npy files, then assemble into
    # the final NPZ.
    import shutil
    import zipfile
    tmp_dir = OUT_NPZ + ".staging"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    for k in list(accum.keys()):
        arr = np.stack(accum.pop(k)).astype(np.uint16)
        print(f"  {k}: {arr.shape}  ({arr.nbytes/(1024**3):.2f} GB) → saving", flush=True)
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
