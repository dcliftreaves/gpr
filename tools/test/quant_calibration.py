"""CNN-aware rate-distortion calibration harness for the GPR codec.

Sweeps codec quality presets across a DNG corpus and measures:
  - Encoded bytes per frame
  - Bayer-domain roundtrip PSNR vs source (no CNN)
  - CNN-corrected PSNR vs source (BIBO_1x by default)

Output: a CSV per-(image, quality) and a summary table that lets you see
where on the rate-distortion curve the CNN is "free" — i.e. quant
presets where the codec drops a lot of bits but the CNN gets the PSNR
back. That's the empirical signal that tells you which subbands the
CNN can recover.

This is the foundation pass for task #158 (AccelIR-style per-subband
quant calibration). Once the encoder/decoder gain a per-subband quant
override env var (waiting on task #155's decoder work to land), this
script grows a `--per-subband-sweep` mode that walks individual qt[]
slots, not whole presets.

Usage:
  python3 tools/test/quant_calibration.py \\
      --corpus /Volumes/OWC_8TB/gpr_work/artifacts/fixtures/barn_sky_dngs \\
      --max-images 4 \\
      --qualities 0,1,2,3,4,5,6,7,8 \\
      --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/quant_calibration

Optional:
  --with-cnn           also measure CNN-corrected PSNR (slower)
  --cnn-ckpt PATH      Metal weights dir (default F_ane_1x_weights_metal)
  --build-dir DIR      cmake build root (default build-local)
"""
from __future__ import annotations
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root()))
ARTIFACT_ROOT = Path(os.environ.get("GPR_ARTIFACT_ROOT", EXTERNAL_ROOT / "artifacts"))
CHECKPOINT_ROOT = Path(os.environ.get("GPR_CHECKPOINT_ROOT", EXTERNAL_ROOT / "checkpoints"))
DERING_DIR = Path(os.environ.get("GPR_DERING_DIR", EXTERNAL_ROOT / "external" / "dering_proto_v2"))
TMPDIR = Path(os.environ.get("TMPDIR", EXTERNAL_ROOT / "tmp"))


def find_tool(build_dir: Path, name: str) -> Path:
    candidates = [
        build_dir / "source/app/gpr_tools/gpr_tools",
        build_dir / "source/app/bench_fused/bench_fused",
        REPO / "tools/gpr2prores/gpr2prores",
        REPO / "tools/gpr2prores/gpr_mov_tool",
    ]
    for c in candidates:
        if c.name == name and c.exists() and os.access(c, os.X_OK):
            return c
    raise SystemExit(f"can't find {name} under {build_dir} or repo")


def infer_peak(white_level: int) -> int:
    """Map rawpy's reported white_level to the codec's encoded bit-depth peak.

    Sensors report a saturation white_level slightly below 2^bits-1 (Z8
    reports 15892 for 14-bit, X2D reports ~60000 for 16-bit). PSNR vs source
    must use the encoded peak (16383 for 14-bit, 65535 for 16-bit), not the
    sensor's saturation level.
    """
    if white_level >= 32768:
        return 65535          # 16-bit
    if white_level >= 8192:
        return 16383          # 14-bit (Z8 ~15892 fits here, well above 8192)
    if white_level >= 2048:
        return 4095           # 12-bit
    return white_level


def extract_bayer(dng_path: Path, out_raw: Path) -> tuple[int, int, int]:
    """Return (width, height, peak) of the DNG bayer plane."""
    import rawpy

    r = rawpy.imread(str(dng_path))
    bayer = r.raw_image.copy().astype("<u2")
    h, w = bayer.shape
    peak = infer_peak(int(r.white_level))
    r.close()
    bayer.tofile(out_raw)
    return w, h, peak


def encode_at_quality(gtools: Path, dng_in: Path, gpr_out: Path, quality: int) -> float:
    """Run gpr_tools dng→gpr at the given quality. Return encode wall-clock ms."""
    t0 = time.time()
    subprocess.run(
        [str(gtools), "-i", str(dng_in), "-o", str(gpr_out), "-q", str(quality)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return (time.time() - t0) * 1000


def decode_to_dng(gtools: Path, gpr_in: Path, dng_out: Path) -> float:
    t0 = time.time()
    subprocess.run(
        [str(gtools), "-i", str(gpr_in), "-o", str(dng_out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return (time.time() - t0) * 1000


def bayer_psnr(src_dng: Path, dec_dng: Path, peak: int) -> float:
    import rawpy
    import numpy as np
    a = rawpy.imread(str(src_dng)); src = a.raw_image.copy().astype("float64"); a.close()
    b = rawpy.imread(str(dec_dng)); dec = b.raw_image.copy().astype("float64"); b.close()
    if src.shape != dec.shape:
        return float("nan")
    mse = ((src - dec) ** 2).mean()
    return float(10 * (np.log10(peak * peak / mse))) if mse > 0 else float("inf")


def cnn_render_psnr(gpr2prores: Path, gpr_in: Path, meta_dng: Path,
                    ckpt: Path, out_mov: Path) -> float | None:
    """Run gpr2prores playback on a single .gpr, extract frame 0 RGB,
    PSNR against the no-codec rawpy AHD render of the source DNG.

    Returns brightness-matched Y-PSNR on the masked middle (matches
    test_cnn_regression.py methodology). None if CNN run failed.
    """
    try:
        import cv2
        import numpy as np
        import rawpy
    except Exception as e:
        print(f"  (CNN PSNR skipped: missing dep {e})")
        return None

    # gpr2prores needs a directory of .gpr or a packed .mov. Single .gpr → tmp dir.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        frame_dst = td_path / "frame_0000.gpr"
        frame_dst.symlink_to(gpr_in)
        rc = subprocess.run([
            str(gpr2prores),
            "--meta-dng", str(meta_dng),
            "--cnn-backend", "mpsgraph",
            "--ckpt", str(ckpt),
            "--cnn-scale", "1x",
            "--demosaic", "metal-bilinear",
            "--out-resolution", "uhd",
            str(td_path), str(out_mov),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc.returncode != 0:
            return None

    # Extract frame 0 RGB16, render reference DNG at UHD, compute masked PSNR.
    rgb_test = td_path / "test.png"
    subprocess.run(["ffmpeg", "-y", "-i", str(out_mov), "-frames:v", "1",
                    "-pix_fmt", "rgb48", str(rgb_test)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if not rgb_test.exists():
        return None

    from PIL import Image
    test = np.asarray(Image.open(rgb_test)).astype(np.float64)
    raw = rawpy.imread(str(meta_dng))
    src = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=16,
                          gamma=(2.222, 4.5), output_color=rawpy.ColorSpace.sRGB,
                          demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD)
    raw.close()

    if src.shape[:2] != test.shape[:2]:
        # Downscale src to test dims (test is UHD, src is native sensor)
        src_resized = cv2.resize(src.astype(np.float32),
                                  (test.shape[1], test.shape[0]),
                                  interpolation=cv2.INTER_AREA).astype(np.float64)
        src = src_resized
    # brightness-match per channel
    test_bm = test.copy()
    for c in range(3):
        test_bm[..., c] = np.clip(test[..., c] + (src[..., c].mean() - test[..., c].mean()),
                                   0, 65535)
    # masked Y-PSNR
    rs = (src / 256.0)
    ts = (test_bm / 256.0)
    ry = 0.299 * rs[..., 0] + 0.587 * rs[..., 1] + 0.114 * rs[..., 2]
    ty = 0.299 * ts[..., 0] + 0.587 * ts[..., 1] + 0.114 * ts[..., 2]
    mask = (ry > 10) & (ry < 250)
    mse = ((ry[mask] - ty[mask]) ** 2).mean()
    if mse <= 0:
        return float("inf")
    return float(20 * np.log10(255.0 / np.sqrt(mse)))


# FUSED quant table slot semantics.
# Single-level + LL: slots 0..3 are { LL, LH1, HL1, HH1 } (only level 1 exists).
# Multi-level: slots 0..9 are { LL3, LH3, HL3, HH3, LH2, HL2, HH2, LH1, HL1, HH1 }.
# Quality preset (q=3 default): {1, 24, 24, 12, 24, 24, 12, 96, 96, 144}.
SINGLE_LEVEL_SLOTS = {
    1: "LH1",
    2: "HL1",
    3: "HH1",
}
MULTI_LEVEL_SLOTS = {
    1: "LH3", 2: "HL3", 3: "HH3",   # level 3 — coarsest highpass (smallest)
    4: "LH2", 5: "HL2", 6: "HH2",   # level 2
    7: "LH1", 8: "HL1", 9: "HH1",   # level 1 — finest highpass (largest bands)
}
QUALITY_3_TABLE = [1, 24, 24, 12, 24, 24, 12, 96, 96, 144]  # quality_tables[3]


def slot_map_for_mode(mode: str) -> dict:
    return MULTI_LEVEL_SLOTS if mode == "multi-level" else SINGLE_LEVEL_SLOTS


def default_quant_for_slot(slot: int) -> int:
    return QUALITY_3_TABLE[slot] if 0 <= slot < len(QUALITY_3_TABLE) else 1


def encode_fused(bench: Path, raw_in: Path, w: int, h: int, gpr_out: Path,
                 override: str | None = None, n_frames: int = 2) -> int:
    """Run bench_fused in half-res single-level+LL mode, dumping the first
    frame to gpr_out. Returns the file size in bytes."""
    env = os.environ.copy()
    env["GPR_INCLUDE_LL"] = "1"
    env["GPR_COL_DECIMATE"] = "2"
    env["GPR_ROW_DECIMATE"] = "2"
    env["GPR_BENCH_DUMP"] = str(gpr_out)
    if override:
        env["GPR_QUANT_OVERRIDE"] = override
    subprocess.run([str(bench), str(raw_in), str(w), str(h), str(n_frames)],
                   env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return gpr_out.stat().st_size


def render_via_gpr2prores(gpr2prores: Path, gpr_in: Path, meta_dng: Path,
                          out_mov: Path, cnn_ckpt: Path | None,
                          override: str | None = None) -> Path | None:
    """Play a single .gpr through gpr2prores with optional CNN. Returns the
    path to a frame-0 PNG extracted via ffmpeg, or None on failure."""
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        (td_path / "frame_0000.gpr").symlink_to(gpr_in.resolve())
        env = os.environ.copy()
        if override:
            env["GPR_QUANT_OVERRIDE"] = override
        cmd = [str(gpr2prores), "--meta-dng", str(meta_dng)]
        if cnn_ckpt:
            cmd += ["--cnn-backend", "mpsgraph", "--ckpt", str(cnn_ckpt),
                    "--cnn-scale", "1x"]
        else:
            cmd += ["--no-cnn"]
        cmd += ["--demosaic", "metal-bilinear", "--out-resolution", "uhd",
                str(td_path), str(out_mov)]
        rc = subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        if rc.returncode != 0:
            return None
    png = out_mov.with_suffix(".png")
    subprocess.run(["ffmpeg", "-y", "-i", str(out_mov), "-frames:v", "1",
                    "-pix_fmt", "rgb48", str(png)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=False)
    return png if png.exists() else None


def rgb_psnr_against_dng(rgb_path: Path, meta_dng: Path) -> float | None:
    """Brightness-matched masked Y-PSNR of an extracted UHD ProRes frame
    against rawpy-AHD render of the source DNG (downscaled to the frame's
    dims). Mirror of test_cnn_regression.py methodology."""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import rawpy
    except ImportError:
        return None
    test = np.asarray(Image.open(rgb_path)).astype(np.float64)
    raw = rawpy.imread(str(meta_dng))
    src = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=16,
                          gamma=(2.222, 4.5), output_color=rawpy.ColorSpace.sRGB,
                          demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD)
    raw.close()
    if src.shape[:2] != test.shape[:2]:
        src = cv2.resize(src.astype(np.float32),
                          (test.shape[1], test.shape[0]),
                          interpolation=cv2.INTER_AREA).astype(np.float64)
    test_bm = test.copy()
    for c in range(3):
        test_bm[..., c] = np.clip(test[..., c] + (src[..., c].mean()
                                                    - test[..., c].mean()),
                                   0, 65535)
    rs = src / 256.0
    ts = test_bm / 256.0
    ry = 0.299 * rs[..., 0] + 0.587 * rs[..., 1] + 0.114 * rs[..., 2]
    ty = 0.299 * ts[..., 0] + 0.587 * ts[..., 1] + 0.114 * ts[..., 2]
    mask = (ry > 10) & (ry < 250)
    mse = ((ry[mask] - ty[mask]) ** 2).mean()
    if mse <= 0:
        return float("inf")
    return float(20 * np.log10(255.0 / np.sqrt(mse)))


def encode_decode_fused(roundtrip: Path, raw_in: Path, w: int, h: int,
                         dec_out: Path, override: str | None = None,
                         encoder_mode: str = "single-ll") -> tuple[int, int, int]:
    """Run test_fused_roundtrip in the chosen encoder topology, half-res
    decimated. Returns (encoded_bytes, dec_w, dec_h). Decoded bayer at dec_out.

    encoder_mode:
      "single-ll" : single-level + LL (GPR_INCLUDE_LL=1) — slots 0..3 only
      "multi-level": multi-level (FUSED_MULTI_LEVEL=1) — slots 0..9 available
    """
    env = os.environ.copy()
    env["GPR_COL_DECIMATE"] = "2"
    env["GPR_ROW_DECIMATE"] = "2"
    if encoder_mode == "multi-level":
        env["FUSED_MULTI_LEVEL"] = "1"
        env.pop("GPR_INCLUDE_LL", None)
    else:
        env["GPR_INCLUDE_LL"] = "1"
        env.pop("FUSED_MULTI_LEVEL", None)
    if override:
        env["GPR_QUANT_OVERRIDE"] = override
    res = subprocess.run([str(roundtrip), str(raw_in), str(w), str(h), str(dec_out)],
                          env=env, check=True, capture_output=True, text=True)
    # test_fused_decode_roundtrip writes progress lines to stderr; parse both.
    enc_bytes = 0
    dw, dh = 0, 0
    for line in (res.stdout + "\n" + res.stderr).splitlines():
        if line.startswith("ENCODE:"):
            enc_bytes = int(line.split()[1])
        elif line.startswith("DECODE:") and "x" in line:
            wh = line.split()[1]
            try:
                dw, dh = (int(x) for x in wh.split("x"))
            except ValueError:
                pass
    if not dw:
        # If decode didn't print dims, fall back to file size / row stride
        # (decimate=2 → 4140×2760 for 8280×5520 input, 2 bytes/px).
        dw, dh = w // 2, h // 2
    return enc_bytes, dw, dh


def bayer_array_psnr(ref_raw: Path, test_raw: Path, w: int, h: int,
                      peak: int = 16383) -> float:
    """PSNR between two raw bayer files of the same dims (uint16 LE)."""
    ref = np.fromfile(ref_raw, dtype=np.uint16).reshape(h, w).astype(np.float64)
    tst = np.fromfile(test_raw, dtype=np.uint16).reshape(h, w).astype(np.float64)
    mse = ((ref - tst) ** 2).mean()
    if mse <= 0:
        return float("inf")
    return float(10 * np.log10(peak * peak / mse))


_CNN_CACHE: dict = {}


def cnn_apply_bayer(bayer_raw: Path, w: int, h: int,
                    out_raw: Path, ckpt_path: Path = None) -> bool:
    """Apply BIBO_1x to a half-res bayer, write corrected bayer.
    Mirror of test_cnn_regression.py::run_inference (sr2x=False path).

    Returns True on success. Loads model once into _CNN_CACHE keyed by ckpt path.
    """
    try:
        import torch
        import torch.nn.functional as F
    except ImportError:
        return False
    sys.path.insert(0, str(DERING_DIR))
    try:
        from model_F_ane import build as build_ane
    except ImportError:
        return False

    if ckpt_path is None:
        ckpt_path = CHECKPOINT_ROOT / "BayInBayOut_1x_AAon_w16_ANE.pt"
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    if str(ckpt_path) not in _CNN_CACHE:
        ck = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
        variant = ck.get("variant", "F_ane")
        m = build_ane(variant)
        m.load_state_dict(ck["backbone_state"])
        m.to(device).eval()
        _CNN_CACHE[str(ckpt_path)] = m
    model = _CNN_CACHE[str(ckpt_path)]

    bayer = np.fromfile(bayer_raw, dtype=np.uint16).reshape(h, w)
    # Force even dims so the 4-plane split produces equal-sized arrays. Odd
    # dimensions (e.g. X2D 5832×4375 codec-domain output) would otherwise
    # break the np.stack.
    even_h = h - (h & 1)
    even_w = w - (w & 1)
    bayer_even = bayer[:even_h, :even_w]
    R = bayer_even[0::2, 0::2]; G1 = bayer_even[0::2, 1::2]
    G2 = bayer_even[1::2, 0::2]; B = bayer_even[1::2, 1::2]
    pl = np.stack([R, G1, G2, B], 0).astype(np.float32) / 16383.0
    x = torch.from_numpy(pl).unsqueeze(0).to(device)
    H, W = x.shape[-2:]
    pad_h = (16 - H % 16) % 16
    pad_w = (16 - W % 16) % 16
    if pad_h or pad_w:
        x = F.pad(x, (0, pad_w, 0, pad_h), mode='reflect')
    RESIDUAL_SCALE = 0.01
    with torch.no_grad():
        y = (x + RESIDUAL_SCALE * model(x)).clamp(0, 1)
    y = y[..., :H, :W]
    yn = y.squeeze(0).cpu().numpy()

    # Write the CNN-corrected even region back; trailing odd row/column (if
    # any) stays as the pre-CNN bayer value — these are codec-edge pixels
    # never visible at displayed resolution.
    out = bayer.copy()
    out[:even_h:2, :even_w:2] = np.clip(yn[0] * 16383, 0, 16383).astype(np.uint16)
    out[:even_h:2, 1:even_w:2] = np.clip(yn[1] * 16383, 0, 16383).astype(np.uint16)
    out[1:even_h:2, :even_w:2] = np.clip(yn[2] * 16383, 0, 16383).astype(np.uint16)
    out[1:even_h:2, 1:even_w:2] = np.clip(yn[3] * 16383, 0, 16383).astype(np.uint16)
    out.tofile(out_raw)
    return True


def run_per_subband_sweep(args, build_dir: Path, images: list[Path]):
    """Sweep per-subband quant multipliers in single-level + LL half-res mode.

    PSNR is bayer-domain against the production-default encode of the SAME
    image (mult=1.0, no override) — that's the reference everyone uses today.
    The point of the sweep is: for each subband, how many bits do I save by
    moving up the multiplier ladder, and how many dB do I sacrifice. The CNN
    "free recovery" question becomes: how much of the per-mult dB cost can a
    CNN trained on (codec_at_mult_x, codec_at_mult_1.0) close.
    """
    roundtrip = build_dir / "bin/test_fused_roundtrip"
    if not roundtrip.exists():
        raise SystemExit(f"need test_fused_roundtrip at {roundtrip} — "
                          "build with: clang -O2 source/app/test_fused_decode_roundtrip.c "
                          "<libs> -o build-local/bin/test_fused_roundtrip")

    multipliers = [float(m) for m in args.multipliers.split(",")]
    slots = [int(s) for s in args.slots.split(",")]
    slot_names = slot_map_for_mode(args.encoder_mode)
    rows = []
    print(f"== Per-subband sweep (bayer-domain PSNR vs default encode) ==")
    print(f"  encoder={args.encoder_mode}  images={len(images)}  slots={slots}  multipliers={multipliers}")
    print()

    for dng in images:
        # Extract bayer once
        TMPDIR.mkdir(parents=True, exist_ok=True)
        raw_in = TMPDIR / f"_qcal_{dng.stem}.raw"
        w, h, _peak = extract_bayer(dng, raw_in)
        print(f"  {dng.name} ({w}×{h})")

        # Reference: production default encode (no override → uses q=3 table)
        ref_dec = args.out_dir / f"{dng.stem}_ref_{args.encoder_mode}.raw"
        ref_bytes, dw, dh = encode_decode_fused(roundtrip, raw_in, w, h, ref_dec,
                                                  encoder_mode=args.encoder_mode)
        print(f"    REF (mult=1.0, {args.encoder_mode})  {ref_bytes/1024:8.0f}KB  → {dw}×{dh}")

        # CNN-corrected reference: run BIBO_1x on the default-encode decode.
        # All test outputs are CNN-corrected too and compared to this same ref —
        # so the CNN's own bias washes out and what we measure is the codec
        # delta the CNN can or can't close.
        ref_cnn_dec = args.out_dir / f"{dng.stem}_ref_cnn.raw"
        cnn_available = False
        if args.with_cnn:
            cnn_available = cnn_apply_bayer(ref_dec, dw, dh, ref_cnn_dec,
                                              ckpt_path=args.cnn_ckpt_pt)

        for slot in slots:
            if slot not in slot_names:
                print(f"    slot {slot}: unsupported in {args.encoder_mode} mode")
                continue
            default_q = default_quant_for_slot(slot)
            for mult in multipliers:
                value = max(1, round(default_q * mult))
                override = f"{slot}:{value}"
                dec_out = args.out_dir / f"{dng.stem}_s{slot}m{mult:.1f}_{args.encoder_mode}.raw"
                bytes_, ddw, ddh = encode_decode_fused(roundtrip, raw_in, w, h,
                                                       dec_out, override,
                                                       encoder_mode=args.encoder_mode)
                psnr = (bayer_array_psnr(ref_dec, dec_out, ddw, ddh)
                         if (ddw, ddh) == (dw, dh) else float("nan"))
                # CNN-corrected PSNR vs the SAME-image CNN-corrected reference.
                psnr_cnn = float("nan")
                if cnn_available:
                    cnn_dec_out = args.out_dir / f"{dng.stem}_s{slot}m{mult:.1f}_{args.encoder_mode}_cnn.raw"
                    if cnn_apply_bayer(dec_out, ddw, ddh, cnn_dec_out,
                                         ckpt_path=args.cnn_ckpt_pt):
                        psnr_cnn = bayer_array_psnr(ref_cnn_dec, cnn_dec_out, ddw, ddh)
                row = dict(image=dng.name, slot=slot,
                            slot_name=slot_names[slot],
                            multiplier=mult, quant_value=value,
                            gpr_bytes=bytes_, gpr_bytes_ref=ref_bytes,
                            bytes_saved=ref_bytes - bytes_,
                            ratio_to_ref=bytes_ / ref_bytes if ref_bytes else 0,
                            bayer_psnr_vs_ref=psnr,
                            bayer_psnr_vs_ref_cnn=psnr_cnn)
                rows.append(row)
                gap = "*" if mult > 1.0 else " "
                cnn_str = (f"  cnn={psnr_cnn:6.2f}dB"
                            if psnr_cnn == psnr_cnn else "")
                print(f"    {gap} slot={slot}({slot_names[slot]:<4s}) "
                      f"mult={mult:.1f} q={value:3d}  "
                      f"{bytes_/1024:8.0f}KB ({100*bytes_/ref_bytes:5.1f}% of ref)  "
                      f"PSNR_vs_ref={psnr:6.2f}dB{cnn_str}")
        try:
            raw_in.unlink()
            ref_dec.unlink(missing_ok=True)
        except FileNotFoundError:
            pass

    csv_path = args.out_dir / "per_subband_sweep.csv"
    with csv_path.open("w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for r in rows:
                w.writerow(r)
    print(f"\nWrote {csv_path}")

    # Aggregate: mean bytes saved + mean PSNR drop per (slot, multiplier).
    # AccelIR's "bits-saved per dB lost" metric is the per-subband signal: high
    # value = a subband worth dropping bits in (small distortion impact for big
    # rate savings). The CNN sweep is the follow-on — when we have a candidate
    # subband to crank, train the CNN on (codec_at_mult_x, codec_at_default)
    # pairs and re-measure with CNN PSNR.
    if rows:
        agg = {}
        for r in rows:
            k = (r["slot"], r["slot_name"], r["multiplier"], r["quant_value"])
            agg.setdefault(k, []).append(r)
        print("\n== Summary (mean across corpus) — bayer-domain vs production-default ==")
        has_cnn = any("bayer_psnr_vs_ref_cnn" in r and r["bayer_psnr_vs_ref_cnn"]
                      == r["bayer_psnr_vs_ref_cnn"] for r in rows)
        if has_cnn:
            print(f"{'slot':6s} {'mult':>5s} {'q':>3s} {'KB/frame':>10s} "
                  f"{'%saved':>8s} {'PSNR_nocnn':>12s} {'PSNR_cnn':>10s} {'CNN_gain':>10s}")
        else:
            print(f"{'slot':6s} {'mult':>5s} {'q':>3s} {'KB/frame':>10s} "
                  f"{'%saved':>8s} {'PSNR_vs_ref':>13s}")
        for (slot, name, mult, q), rs in sorted(agg.items()):
            mean_kb = sum(r["gpr_bytes"] for r in rs) / len(rs) / 1024
            mean_pct = sum(r["ratio_to_ref"] for r in rs) / len(rs) * 100
            psnrs = [r["bayer_psnr_vs_ref"] for r in rs
                     if r["bayer_psnr_vs_ref"] == r["bayer_psnr_vs_ref"]]
            mean_psnr = sum(psnrs) / len(psnrs) if psnrs else float("nan")
            saved_pct = 100 - mean_pct if mult > 1.0 else 0.0
            if has_cnn:
                cnn_psnrs = [r["bayer_psnr_vs_ref_cnn"] for r in rs
                              if r.get("bayer_psnr_vs_ref_cnn") ==
                                  r.get("bayer_psnr_vs_ref_cnn")]
                mean_cnn = sum(cnn_psnrs) / len(cnn_psnrs) if cnn_psnrs else float("nan")
                gain = mean_cnn - mean_psnr if (mean_cnn == mean_cnn
                                                 and mean_psnr == mean_psnr) else float("nan")
                print(f"{name:6s} {mult:>5.1f} {q:>3d} {mean_kb:>10.1f} "
                      f"{saved_pct:>7.1f}% {mean_psnr:>9.2f}dB {mean_cnn:>7.2f}dB "
                      f"{gain:>+7.2f}dB")
            else:
                print(f"{name:6s} {mult:>5.1f} {q:>3d} {mean_kb:>10.1f} "
                      f"{saved_pct:>7.1f}% {mean_psnr:>10.2f}dB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["presets", "per-subband"],
                    default="presets",
                    help="presets = sweep q=0..8; per-subband = sweep GPR_QUANT_OVERRIDE slots")
    ap.add_argument("--corpus", required=True, type=Path,
                    help="directory of source DNGs to sweep")
    ap.add_argument("--max-images", type=int, default=4,
                    help="limit number of corpus images (deterministic)")
    ap.add_argument("--qualities", default="0,1,2,3,4,5,6,7,8",
                    help="(presets mode) comma-separated quality presets to sweep")
    ap.add_argument("--encoder-mode", choices=["single-ll", "multi-level"],
                    default="single-ll",
                    help="(per-subband mode) which FUSED topology to encode under. "
                         "single-ll: 4 quant slots (LL+LH1+HL1+HH1). "
                         "multi-level: 10 slots (LL3 + 9 highpass across 3 levels)")
    ap.add_argument("--slots", default="1,2,3",
                    help="(per-subband mode) comma-separated slot indices to sweep. "
                         "single-ll: 1=LH1, 2=HL1, 3=HH1. "
                         "multi-level: 1..3=L3 highpass, 4..6=L2, 7..9=L1.")
    ap.add_argument("--multipliers", default="1.0,1.5,2.0,3.0,4.0",
                    help="(per-subband mode) multipliers to apply to default quant")
    ap.add_argument("--build-dir", type=Path, default=Path("build-local"))
    ap.add_argument("--out-dir", type=Path,
                    default=ARTIFACT_ROOT / "quant_calibration")
    ap.add_argument("--with-cnn", action="store_true",
                    help="also measure CNN-corrected PSNR (much slower)")
    ap.add_argument("--cnn-ckpt", type=Path,
                    default=ARTIFACT_ROOT / "weights/F_ane_1x_weights_metal",
                    help="Metal weights dir (gpr2prores render path)")
    ap.add_argument("--cnn-ckpt-pt", type=Path,
                    default=CHECKPOINT_ROOT / "BayInBayOut_1x_AAon_w16_ANE.pt",
                    help="PyTorch checkpoint (per-subband bayer-domain CNN PSNR path)")
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    build_dir = (args.build_dir if args.build_dir.is_absolute()
                 else REPO / args.build_dir)

    images = sorted(args.corpus.glob("*.dng"))[: args.max_images]
    if not images:
        raise SystemExit(f"no DNGs under {args.corpus}")

    if args.mode == "per-subband":
        run_per_subband_sweep(args, build_dir, images)
        return

    # --- presets mode (default) ---
    gtools = find_tool(build_dir, "gpr_tools")
    gpr2prores = find_tool(build_dir, "gpr2prores") if args.with_cnn else None
    qualities = [int(q) for q in args.qualities.split(",")]

    rows = []
    print(f"== Sweeping {len(images)} images × {len(qualities)} qualities ==")
    print(f"== Corpus: {args.corpus}")
    print(f"== Output: {args.out_dir}")
    if args.with_cnn:
        print(f"== CNN ckpt: {args.cnn_ckpt}")
    print()

    for dng in images:
        # Pre-extract raw + dims once per image (cheaper than re-reading every quality)
        # Then run encode/decode/PSNR per quality.
        print(f"  {dng.name}")
        for q in qualities:
            gpr_path = args.out_dir / f"{dng.stem}_q{q}.gpr"
            dec_dng = args.out_dir / f"{dng.stem}_q{q}_dec.dng"
            try:
                enc_ms = encode_at_quality(gtools, dng, gpr_path, q)
                dec_ms = decode_to_dng(gtools, gpr_path, dec_dng)
            except subprocess.CalledProcessError as e:
                print(f"    q={q}: FAILED encode/decode ({e})")
                continue

            gpr_bytes = gpr_path.stat().st_size
            raw_bytes = dng.stat().st_size
            ratio = gpr_bytes / raw_bytes if raw_bytes else float("nan")

            # Read the DNG to get peak
            import rawpy
            r = rawpy.imread(str(dng))
            peak = infer_peak(int(r.white_level))
            r.close()

            psnr_bayer = bayer_psnr(dng, dec_dng, peak)

            psnr_cnn = None
            if args.with_cnn:
                out_mov = args.out_dir / f"{dng.stem}_q{q}_cnn.mov"
                psnr_cnn = cnn_render_psnr(gpr2prores, gpr_path, dng,
                                            args.cnn_ckpt, out_mov)

            row = {
                "image": dng.name,
                "quality": q,
                "encode_ms": round(enc_ms, 2),
                "decode_ms": round(dec_ms, 2),
                "gpr_bytes": gpr_bytes,
                "ratio_vs_dng": round(ratio, 4),
                "bayer_psnr_dB": round(psnr_bayer, 2),
                "cnn_psnr_dB": round(psnr_cnn, 2) if psnr_cnn is not None else None,
            }
            rows.append(row)
            extra = f" cnn={psnr_cnn:.2f}dB" if psnr_cnn is not None else ""
            print(f"    q={q}: enc={enc_ms:6.0f}ms dec={dec_ms:6.0f}ms "
                  f"{gpr_bytes/1024:8.0f}KB bayer={psnr_bayer:5.2f}dB{extra}")

    csv_path = args.out_dir / "calibration.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            w.writeheader()
            for r in rows:
                w.writerow(r)
    print(f"\nWrote {csv_path}")

    # Aggregate: mean across images per quality
    if rows:
        by_q = {}
        for r in rows:
            by_q.setdefault(r["quality"], []).append(r)
        print("\n== Summary (mean across corpus) ==")
        print(f"{'q':>3s} {'kb/frame':>10s} {'ratio':>8s} {'bayer_dB':>10s}", end="")
        if args.with_cnn:
            print(f" {'cnn_dB':>10s}", end="")
        print()
        for q in qualities:
            if q not in by_q:
                continue
            mean_kb = sum(r["gpr_bytes"] for r in by_q[q]) / len(by_q[q]) / 1024
            mean_ratio = sum(r["ratio_vs_dng"] for r in by_q[q]) / len(by_q[q])
            mean_bayer = sum(r["bayer_psnr_dB"] for r in by_q[q]) / len(by_q[q])
            line = f"{q:>3d} {mean_kb:>10.1f} {mean_ratio:>8.4f} {mean_bayer:>10.2f}"
            if args.with_cnn:
                vals = [r["cnn_psnr_dB"] for r in by_q[q] if r["cnn_psnr_dB"] is not None]
                if vals:
                    line += f" {sum(vals)/len(vals):>10.2f}"
                else:
                    line += " " * 11 + "—"
            print(line)


if __name__ == "__main__":
    main()
