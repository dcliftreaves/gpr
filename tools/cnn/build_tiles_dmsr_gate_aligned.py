"""Build NPZ tiles for F_ane_dm_sr using the gate's REF rendering path
(sips of gpr_tools-wrap-of-source-bayer), so the CNN learns the exact
distribution the gate compares against.

The prior dmsr training used direct `sips(source.dng)` as targets, but
the gate's REF for cnn=*+demosaic=sips_via_gpr_tools pipelines goes
through gpr_tools (extract bayer, wrap with source params, sips render).
That path differs from direct sips by ~30 levels per RGB channel
(verified on Z8Z_0067), so the trained CNN learned the wrong target
and the gate scored 19 dB Y-PSNR vs the 43 dB val PSNR during training.

For each source DNG:
  1. rawpy → 16-bit bayer
  2. gpr_tools wrap with source-DNG params → out.dng (matches gate path)
  3. sips → PNG (cached on 8TB)
  4. Tile to 512×512 aligned with codec tiles

Output: tiles_ml2_q3_dec2_dmsr_gate.npz (replaces _dmsr.npz).
"""
import os, sys, time, subprocess, json, shutil, zipfile, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

REPO = "/Users/dcliftreaves/Documents/Github/gpr"
IN_NPZ = "/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_combined.npz"
OUT_NPZ = "/Volumes/OWC_8TB/gpr_cnn/tiles_ml2_q3_dec2_dmsr_gate.npz"
RENDER_CACHE = Path("/Volumes/OWC_8TB/gpr_cnn/render_cache_gate")
RENDER_CACHE.mkdir(exist_ok=True)
GPR_TOOLS = f"{REPO}/build-local/source/app/gpr_tools/gpr_tools"

SOURCE_PATHS = {}
for d in ["/Volumes/OWC_8TB/barnsky_full_dngs",
          "/Volumes/OWC_8TB/gpr_cnn/diverse_dngs"]:
    if not os.path.isdir(d): continue
    for f in os.listdir(d):
        if f.lower().endswith('.dng'):
            base = os.path.splitext(f)[0]
            SOURCE_PATHS[base] = os.path.join(d, f)

TILE_CODEC = 128
TILE_TGT_RGB = 512
SCALE_TO_BAYER = 4
SOURCE_BAYER_H, SOURCE_BAYER_W = 5520, 8280


def gate_render_path(dng_path: str, png_path: Path):
    """Replicate the gate's REF path: extract bayer via tifffile (matches
    gate's read_source_bayer) → gpr_tools wrap with source params → sips
    render. Cached on disk."""
    if png_path.exists() and png_path.stat().st_size > 1000:
        return
    import tifffile
    workdir = Path(tempfile.mkdtemp(prefix="dmsr_gate_"))
    try:
        # 1. Extract bayer via tifffile — same path as gate's read_source_bayer
        with tifffile.TiffFile(dng_path) as tf:
            bayer = tf.pages[0].pages[0].asarray().astype("<u2")
        h, w = bayer.shape

        # 2. Dump source params via gpr_tools -d 1
        params_cache = workdir / "params.json"
        cp = subprocess.run([GPR_TOOLS, "-i", dng_path, "-d", "1"],
                            capture_output=True, text=True, check=True)
        lines = [l for l in cp.stdout.splitlines() if not l.startswith("[")]
        params_cache.write_text("\n".join(lines))
        params = json.loads(params_cache.read_text())
        params["input_width"] = w
        params["input_height"] = h
        params["input_pitch"] = w * 2
        params_run = workdir / f"params_{w}x{h}.json"
        params_run.write_text(json.dumps(params))

        # 3. Write bayer.raw, gpr_tools wrap → out.dng
        raw_in = workdir / "bayer.raw"
        bayer.astype(np.uint16).tofile(raw_in)
        dng_out = workdir / "out.dng"
        subprocess.run([GPR_TOOLS, "-i", str(raw_in), "-w", str(w), "-h", str(h),
                        "-x", "rggb14", "-a", str(params_run),
                        "-o", str(dng_out)], check=True, capture_output=True)
        # 4. sips render
        subprocess.run(["sips", "-s", "format", "png", str(dng_out),
                        "--out", str(png_path)], check=True, capture_output=True)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    print(f"loading codec NPZ {IN_NPZ}...", flush=True)
    npz = np.load(IN_NPZ, mmap_mode="r", allow_pickle=True)
    src = np.asarray(npz["src"])
    lookup = np.asarray(npz["src_lookup_names"])
    names = [s.decode() if isinstance(s, bytes) else s for s in lookup.tolist()]
    N = len(src)
    print(f"  {N} tiles across {len(names)} source images", flush=True)

    def dng_path_for(name):
        base = name[4:] if name.startswith("div_") else name
        return SOURCE_PATHS.get(base)

    print("rendering via gate path (gpr_tools wrap + sips)...", flush=True)
    t0 = time.time()
    renders = {}
    for i, n in enumerate(names):
        dng = dng_path_for(n)
        if dng is None:
            print(f"  WARN no source for {n}", flush=True)
            renders[n] = None
            continue
        png = RENDER_CACHE / f"{n}.png"
        try:
            gate_render_path(dng, png)
            renders[n] = png
        except Exception as e:
            print(f"  ERROR {n}: {e}", flush=True)
            renders[n] = None
        if i % 25 == 0:
            print(f"  [{i+1}/{len(names)}] {n}  t={time.time()-t0:.0f}s", flush=True)
    print(f"  done rendering in {time.time()-t0:.0f}s", flush=True)

    # Tile extraction (same as before)
    print("extracting RGB tiles...", flush=True)
    H_codec, W_codec = 1380, 2070
    STRIDE = 256
    tgt_rgb = np.zeros((N, TILE_TGT_RGB, TILE_TGT_RGB, 3), dtype=np.uint8)
    written = 0
    t0 = time.time()
    for sid, n in enumerate(names):
        if renders[n] is None: continue
        img = np.array(Image.open(renders[n]).convert("RGB"))
        if img.shape[0] != SOURCE_BAYER_H or img.shape[1] != SOURCE_BAYER_W:
            padded = np.zeros((SOURCE_BAYER_H, SOURCE_BAYER_W, 3), dtype=np.uint8)
            hh = min(img.shape[0], SOURCE_BAYER_H); ww = min(img.shape[1], SOURCE_BAYER_W)
            padded[:hh, :ww] = img[:hh, :ww]
            img = padded
        tile_indices = np.where(src == sid)[0]
        i = 0
        for yc in range(0, H_codec - TILE_CODEC + 1, STRIDE):
            for xc in range(0, W_codec - TILE_CODEC + 1, STRIDE):
                if i >= len(tile_indices): break
                Y, X = yc * SCALE_TO_BAYER, xc * SCALE_TO_BAYER
                if Y + TILE_TGT_RGB > SOURCE_BAYER_H or X + TILE_TGT_RGB > SOURCE_BAYER_W:
                    i += 1; continue
                tgt_rgb[tile_indices[i]] = img[Y:Y+TILE_TGT_RGB, X:X+TILE_TGT_RGB, :]
                i += 1; written += 1
        if sid % 25 == 0 or sid < 3:
            print(f"  [{sid+1}/{len(names)}] {n} tiles={i} (t={time.time()-t0:.0f}s)", flush=True)
    print(f"  wrote {written} RGB tiles", flush=True)

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
