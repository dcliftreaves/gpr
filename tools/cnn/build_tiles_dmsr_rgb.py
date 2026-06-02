"""Build NPZ tiles with sips-rendered RGB targets for the F_ane_dm_sr
joint-demosaic+super-res CNN.

Why this exists: the first attempt trained against bilinear-demosaiced
target bayer (sensor RGB), but the gate compares against sips-rendered
RGB (Adobe-DCP-processed RGB). The model learned the wrong target and
gate LPIPS landed at 0.55+ even with val PSNR climbing nicely. Fixing
by generating targets in the SAME color space as the gate's REF.

For each source DNG:
  1. Find the source DNG path (barnsky_full_dngs or the Adobe-converted
     diverse_dngs directory).
  2. sips render to PNG (full-res, Adobe-processed RGB).
  3. Tile in 512×512 windows at positions that match each existing
     codec tile (input is 128×128 deinterleaved → spans 512×512 in
     source bayer space).
  4. Save as `tgt_rgb` field alongside the existing `codec_R/G1/G2/B`
     fields.

Output: tiles_ml2_q3_dec2_dmsr.npz with the same N tiles as the input
codec NPZ, but `tgt_rgb` (N, 512, 512, 3) uint8 instead of `tgt_*` 4ch
bayer.
"""
import os, sys, time, subprocess, json, shutil, zipfile, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

REPO = "/Users/dcliftreaves/Documents/Github/gpr"
IN_NPZ = os.environ.get(
    "IN_NPZ", "/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_combined.npz")
OUT_NPZ = os.environ.get(
    "OUT_NPZ", "/Volumes/OWC_8TB/gpr_work/cnn/tiles_ml2_q3_dec2_dmsr.npz")
RENDER_CACHE = Path("/Volumes/OWC_8TB/gpr_work/cnn/render_cache")
RENDER_CACHE.mkdir(exist_ok=True)

# Map base name → source DNG path. SOURCE_DIRS env (colon-separated) appends
# extra DNG locations on top of the default {barnsky, diverse_dngs} pair so
# new corpora (e.g. ood_dngs_2025-04-20) can be referenced without a code edit.
_default_dirs = ["/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs",
                 "/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs"]
_extra = [d for d in os.environ.get("SOURCE_DIRS", "").split(":") if d]
SOURCE_PATHS = {}
for d in _default_dirs + _extra:
    if not os.path.isdir(d): continue
    for f in os.listdir(d):
        if f.lower().endswith('.dng'):
            base = os.path.splitext(f)[0]
            SOURCE_PATHS[base] = os.path.join(d, f)

TILE_CODEC = 128                  # codec tile dim (per channel)
TILE_TGT_RGB = 512                # target RGB tile dim
# Spatial scale from codec-tile coords (yc, xc) to source-bayer (Y, X):
# codec is half-res of source bayer (decimate=2) and deinterleaved planes
# are 1/2 of bayer, so source_bayer Y = yc * 4.
SCALE_TO_BAYER = 4
# Source DNG dims (Z8 sensor active area):
SOURCE_BAYER_H, SOURCE_BAYER_W = 5520, 8280


def sips_render(dng_path: str, png_path: Path):
    if png_path.exists() and png_path.stat().st_size > 1000:
        return
    subprocess.run(["sips", "-s", "format", "png", dng_path, "--out", str(png_path)],
                   check=True, capture_output=True)


def main():
    print(f"loading codec NPZ {IN_NPZ}...", flush=True)
    npz = np.load(IN_NPZ, mmap_mode="r", allow_pickle=True)
    src = np.asarray(npz["src"])
    lookup = np.asarray(npz["src_lookup_names"])
    names = [s.decode() if isinstance(s, bytes) else s for s in lookup.tolist()]
    N = len(src)
    print(f"  {N} tiles across {len(names)} source images", flush=True)

    # Diverse pair names have a "div_" prefix. The corresponding DNG basename
    # is what's after "div_". Strip it for source lookup. For non-diverse,
    # the name IS the basename.
    def dng_path_for(name):
        base = name[4:] if name.startswith("div_") else name
        return SOURCE_PATHS.get(base)

    # Render each source DNG to PNG (cached on disk)
    print("rendering source DNGs via sips (cached)...", flush=True)
    t0 = time.time()
    renders = {}
    for i, n in enumerate(names):
        dng = dng_path_for(n)
        if dng is None:
            print(f"  WARN no source for {n}", flush=True)
            renders[n] = None
            continue
        png = RENDER_CACHE / f"{n}.png"
        sips_render(dng, png)
        renders[n] = png
        if i % 50 == 0:
            print(f"  [{i+1}/{len(names)}] {n}  t={time.time()-t0:.0f}s", flush=True)
    print(f"  done rendering in {time.time()-t0:.0f}s", flush=True)

    # Reconstruct tile spatial positions. Tile builder iterated (yc, xc) with
    # stride 256 codec across deinterleaved plane (1380x2070 codec-side).
    # Tiles for image_i: indices where src == i, in stride-order.
    print("extracting target RGB tiles...", flush=True)
    H_codec, W_codec = 1380, 2070
    STRIDE = 256
    n_per_image = sum(1 for yc in range(0, H_codec - TILE_CODEC + 1, STRIDE)
                       for xc in range(0, W_codec - TILE_CODEC + 1, STRIDE))
    print(f"  expecting {n_per_image} tiles per image; total {n_per_image * len(names)}", flush=True)

    tgt_rgb = np.zeros((N, TILE_TGT_RGB, TILE_TGT_RGB, 3), dtype=np.uint8)
    written = 0
    t0 = time.time()
    for sid, n in enumerate(names):
        if renders[n] is None: continue
        img = np.array(Image.open(renders[n]).convert("RGB"))
        # Sips render may be 8256x5504 (after active-area crop) instead of
        # 8280x5520. Pad with zeros to match bayer dims, so coord math holds.
        if img.shape[0] != SOURCE_BAYER_H or img.shape[1] != SOURCE_BAYER_W:
            padded = np.zeros((SOURCE_BAYER_H, SOURCE_BAYER_W, 3), dtype=np.uint8)
            hh = min(img.shape[0], SOURCE_BAYER_H); ww = min(img.shape[1], SOURCE_BAYER_W)
            padded[:hh, :ww] = img[:hh, :ww]
            img = padded
        # Indices for tiles of this source image
        tile_indices = np.where(src == sid)[0]
        i = 0
        for yc in range(0, H_codec - TILE_CODEC + 1, STRIDE):
            for xc in range(0, W_codec - TILE_CODEC + 1, STRIDE):
                if i >= len(tile_indices): break
                Y, X = yc * SCALE_TO_BAYER, xc * SCALE_TO_BAYER
                # Bounds-check
                if Y + TILE_TGT_RGB > SOURCE_BAYER_H or X + TILE_TGT_RGB > SOURCE_BAYER_W:
                    i += 1; continue
                tgt_rgb[tile_indices[i]] = img[Y:Y+TILE_TGT_RGB, X:X+TILE_TGT_RGB, :]
                i += 1; written += 1
        if sid % 25 == 0 or sid < 3:
            print(f"  [{sid+1}/{len(names)}] {n} tiles={i} (t={time.time()-t0:.0f}s)", flush=True)
    print(f"  wrote {written} RGB tiles", flush=True)

    # Save: keep codec planes as-is, replace tgt_* with tgt_rgb.
    print(f"writing {OUT_NPZ}...", flush=True)
    tmp_dir = OUT_NPZ + ".staging"
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    for k in ["codec_R", "codec_G1", "codec_G2", "codec_B"]:
        arr = np.asarray(npz[k])
        np.save(os.path.join(tmp_dir, k + ".npy"), arr)
        print(f"  {k}: {arr.shape}", flush=True)
        del arr
    np.save(os.path.join(tmp_dir, "tgt_rgb.npy"), tgt_rgb)
    print(f"  tgt_rgb: {tgt_rgb.shape}", flush=True)
    np.save(os.path.join(tmp_dir, "src.npy"), np.asarray(npz["src"]))
    np.save(os.path.join(tmp_dir, "src_lookup_names.npy"),
            np.asarray(npz["src_lookup_names"]), allow_pickle=True)
    with zipfile.ZipFile(OUT_NPZ, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for fn in sorted(os.listdir(tmp_dir)):
            zf.write(os.path.join(tmp_dir, fn), arcname=fn)
    shutil.rmtree(tmp_dir)
    print(f"DONE. size: {os.path.getsize(OUT_NPZ)/(1024**3):.2f} GB", flush=True)


if __name__ == "__main__":
    main()
