"""Streaming variant of build_tiles_ml2_q3.py.

Same NPZ schema, but writes each source's tiles to memmap'd staging files
incrementally — avoids the OOM on large corpora (e.g. 900+ pairs at full Z8
resolution) that the in-memory accumulator hits on M3 Max (36 GB).

Pre-counts total tile count, allocates per-array memmaps, then fills them
source-by-source while freeing the source bayer between iterations.

Same env vars as the original:
  PAIRS_DIR, TILES_OUT, TILES_STRIDE
"""
import gc
import os
import shutil
import sys
import time
import zipfile
import numpy as np

PAIRS_DIR = os.environ.get("PAIRS_DIR", "/Volumes/OWC_8TB/gpr_cnn/pairs_ml2_q3")
OUT_NPZ = os.environ.get("TILES_OUT", "/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3.npz")
TILE = 128
STRIDE = int(os.environ.get("TILES_STRIDE", "256"))
TARGET_BAYER_DIMS = (5520, 8280)
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

    # Tile-count math: each source produces ny*nx tiles per plane after
    # deinterleave. Deinterleave makes plane dims (H/2, W/2). We sweep with
    # STRIDE inside (4140, 2760).
    plane_h = TARGET_BAYER_DIMS[0] // 2
    plane_w = TARGET_BAYER_DIMS[1] // 2
    ny = (plane_h - TILE) // STRIDE + 1
    nx = (plane_w - TILE) // STRIDE + 1
    tiles_per_src = ny * nx
    total = len(bases) * tiles_per_src
    print(f"  ny={ny}  nx={nx}  tiles_per_src={tiles_per_src}  total={total}",
          flush=True)

    # Allocate staging memmaps so the working set is bounded by disk, not RAM.
    tmp_dir = OUT_NPZ + ".staging"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)

    keys = ["codec_R", "codec_G1", "codec_G2", "codec_B",
            "tgt_R", "tgt_G1", "tgt_G2", "tgt_B"]
    mmaps = {}
    for k in keys:
        path = os.path.join(tmp_dir, k + ".npy")
        # Use numpy .npy v3.0 format via np.lib.format
        arr = np.lib.format.open_memmap(path, mode="w+", dtype=np.uint16,
                                         shape=(total, TILE, TILE))
        mmaps[k] = arr
    src_ids = np.zeros(total, dtype=np.int32)
    src_names = []

    t0 = time.time()
    idx = 0
    for sid, base in enumerate(bases):
        src_names.append(base)
        codec = np.fromfile(os.path.join(PAIRS_DIR, f"{base}_codec.raw"),
                            dtype=np.uint16).reshape(TARGET_BAYER_DIMS)
        tgt = np.fromfile(os.path.join(PAIRS_DIR, f"{base}_target.raw"),
                          dtype=np.uint16).reshape(TARGET_BAYER_DIMS)
        c_planes = deinterleave(codec)
        t_planes = deinterleave(tgt)
        for y in range(0, plane_h - TILE + 1, STRIDE):
            for x in range(0, plane_w - TILE + 1, STRIDE):
                for ci, key in enumerate(["codec_R", "codec_G1", "codec_G2", "codec_B"]):
                    mmaps[key][idx] = c_planes[ci][y:y+TILE, x:x+TILE]
                for ci, key in enumerate(["tgt_R", "tgt_G1", "tgt_G2", "tgt_B"]):
                    mmaps[key][idx] = t_planes[ci][y:y+TILE, x:x+TILE]
                src_ids[idx] = sid
                idx += 1
        # Drop refs so the allocator can reuse the 91 MB buffer.
        del codec, tgt, c_planes, t_planes
        if sid % 50 == 0 or sid < 5 or sid == len(bases) - 1:
            print(f"  [{sid+1}/{len(bases)}] {base}: idx={idx} "
                  f"(t={time.time()-t0:.0f}s)", flush=True)
            gc.collect()

    assert idx == total, f"idx={idx} != total={total}"

    # Flush memmaps and save src/lookup.
    for k in keys:
        mmaps[k].flush()
    del mmaps
    gc.collect()
    np.save(os.path.join(tmp_dir, "src.npy"), src_ids)
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
