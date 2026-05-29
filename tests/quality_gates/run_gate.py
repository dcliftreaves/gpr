#!/usr/bin/env python3
"""Quality-gate runner — the SINGLE source of truth for ship verdicts.

This script is the only thing allowed to produce a "PASS" / "FAIL" verdict
for any pipeline. If you're claiming a pipeline ships, you must reference
a run-hash this script emitted.

Design constraints (don't undo these without reading docs/quality_gates.md):
  - Per-image evaluation, never aggregate-only. Worst image governs.
  - Crop positions, eval resolution, and thresholds are file-fixed in
    test_set.json and gates.json. The script never picks them.
  - Pipelines are looked up by name in pipelines/registry.json. No
    inline overrides.
  - Visual diff PNG is written. If it isn't, verdict is INDETERMINATE.
  - The script writes a JSON run log to tests/quality_gates/runs/. The
    run-hash is deterministic from inputs — same inputs = same hash.
  - A failing image is reported with its filename AND the metric values
    that failed. No silent failures.

Usage:
  python3 tests/quality_gates/run_gate.py PIPELINE_NAME [--update-baseline]

Example:
  python3 tests/quality_gates/run_gate.py \
      'codec=ml2_q3+cnn=none+demosaic=sips_via_gpr_tools'

Exit codes:
  0   PASS — all per-image metrics under their gate-class thresholds
  1   FAIL — at least one image failed at least one metric
  2   INDETERMINATE — visual diff wasn't produced, source missing, etc.
  3   USAGE_ERROR — bad invocation, unknown pipeline, etc.
"""
from __future__ import annotations
import argparse
import concurrent.futures as _cf
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
GATES_PATH = REPO / "tests/quality_gates/gates.json"
TEST_SET_PATH = REPO / "tests/quality_gates/test_set.json"
REGISTRY_PATH = REPO / "pipelines/registry.json"
RUNS_DIR = REPO / "tests/quality_gates/runs"
CLAIMS_LOG = REPO / "docs/claims_log.md"

sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics, bayer_psnr  # noqa: E402


# --------------------------------------------------------------------- helpers


def die(code: int, msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_env(env: dict) -> str:
    return ";".join(f"{k}={env[k]}" for k in sorted(env))


def load_json(p: Path) -> dict:
    if not p.exists():
        die(3, f"missing: {p}")
    return json.loads(p.read_text())


# --------------------------------------------------------------------- core


def read_source_bayer(dng_path: str) -> tuple[np.ndarray, int, int]:
    import tifffile
    with tifffile.TiffFile(dng_path) as tf:
        raw = tf.pages[0].pages[0].asarray()
    h, w = raw.shape
    return raw.astype("<u2"), w, h


def _encode_decode_legacy_gpr_tools(codec: dict, bayer: np.ndarray,
                                    w: int, h: int, workdir: Path,
                                    src_dng: str) -> tuple[np.ndarray, int, float]:
    """Encode via legacy gpr_tools. Different CLI than test_fused_roundtrip
    AND different encode mode: gpr_tools' raw-input path produces .gpr files
    that the decoder can't always reconstruct (missing tags). Instead we
    encode the source DNG directly (matches build_dataset_gpr_tools_q3.py).
    Bayer argument is unused — we go from src_dng to .gpr to bayer."""
    binary = REPO / codec["binary"]
    if not binary.exists():
        die(2, f"codec binary not built: {binary}")
    quality = codec.get("quality", 3)
    gpr_path = workdir / "encoded.gpr"
    t0 = time.time()
    r = subprocess.run([str(binary), "-i", str(src_dng), "-q", str(quality),
                        "-o", str(gpr_path)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        die(2, f"legacy encode failed: {r.stderr[-200:]}")
    enc_bytes = gpr_path.stat().st_size
    dec_dng = workdir / "decoded.dng"
    r = subprocess.run([str(binary), "-i", str(gpr_path), "-o", str(dec_dng)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        die(2, f"legacy decode failed: {r.stderr[-200:]}")
    enc_ms = (time.time() - t0) * 1000.0
    import tifffile
    def _find_bayer(pages):
        best = None; best_size = 0
        for pg in pages:
            try:
                sh = pg.shape
                if len(sh) == 2 and sh[0]*sh[1] > best_size:
                    best, best_size = pg, sh[0]*sh[1]
            except Exception: pass
            try:
                for sp in getattr(pg, "pages", None) or []:
                    try:
                        sh = sp.shape
                        if len(sh) == 2 and sh[0]*sh[1] > best_size:
                            best, best_size = sp, sh[0]*sh[1]
                    except Exception: pass
            except Exception: pass
        return best
    with tifffile.TiffFile(dec_dng) as tf:
        page = _find_bayer(tf.pages)
        if page is None:
            die(2, "legacy decode: no bayer page")
        dec_bayer = page.asarray().astype("<u2")
    return dec_bayer, enc_bytes, enc_ms


def encode_decode(codec: dict, bayer: np.ndarray, w: int, h: int,
                  workdir: Path, src_dng: str = None) -> tuple[np.ndarray, int, float]:
    """Returns (decoded_bayer, enc_bytes, enc_ms). Decoded dims may be
    half of (w, h) when GPR_ROW_DECIMATE=2 and GPR_COL_DECIMATE=2 are set
    in the codec env — the codec emits a half-res bayer. Caller is
    expected to detect this and apply a super-res CNN to restore to
    (w, h) before metric comparison against the full-res REF."""
    if codec.get("encoder_kind") == "legacy_gpr_tools":
        if src_dng is None:
            die(3, "legacy_gpr_tools codec requires src_dng to be passed to encode_decode")
        return _encode_decode_legacy_gpr_tools(codec, bayer, w, h, workdir, src_dng)
    binary = REPO / codec["binary"]
    if not binary.exists():
        die(2, f"codec binary not built: {binary}")
    env = os.environ.copy()
    env.update({k: str(v) for k, v in codec.get("env", {}).items()})
    if "quality" in codec and "FUSED_QUALITY" not in env:
        env["FUSED_QUALITY"] = str(codec["quality"])
    in_raw = workdir / "in.raw"
    out_raw = workdir / "out.raw"
    if not in_raw.exists():
        bayer.tofile(in_raw)
    t0 = time.time()
    r = subprocess.run(
        [str(binary), str(in_raw), str(w), str(h), str(out_raw)],
        env=env, capture_output=True, text=True, timeout=300,
    )
    enc_ms = (time.time() - t0) * 1000.0
    if r.returncode != 0:
        die(2, f"codec failed rc={r.returncode}: {r.stderr[-300:]}")
    import re
    m = re.search(r"ENCODE: (\d+) bytes", r.stderr)
    enc_bytes = int(m.group(1)) if m else 0
    me = re.search(r"ENCODE.*in ([\d.]+) ms", r.stderr)
    enc_ms_reported = float(me.group(1)) if me else enc_ms
    # Detect actual decoded dims from the output file size — the codec
    # halves (w, h) when decimation is on. Reading at the wrong dims
    # yields a misshaped numpy array which is obvious to catch.
    nbytes = os.path.getsize(out_raw)
    dec_w, dec_h = w, h
    if nbytes == (w // 2) * (h // 2) * 2:
        dec_w, dec_h = w // 2, h // 2
    elif nbytes != w * h * 2:
        die(2, f"decoded bayer size {nbytes} bytes doesn't match either "
               f"full ({w}x{h}={w*h*2}) or half ({w//2}x{h//2}={(w//2)*(h//2)*2})")
    dec = np.fromfile(out_raw, dtype=np.uint16).reshape(dec_h, dec_w)
    return dec, enc_bytes, enc_ms_reported


def apply_cnn(bayer: np.ndarray, cnn: dict):
    """Apply a CNN to a bayer plane. Supports four architectures:
      - 1x denoise (variant F_ane_no_sr): output dims = input dims.
        Result = input + residual_scale * CNN(input). Returns bayer (np.uint16).
      - 2x super-res (variant F_ane): output dims = 2*input dims.
        Result = bicubic(input, 2x) + residual_scale * CNN(input). Returns bayer.
      - Joint demosaic+super-res (variant F_ane_dm_sr): output is 4×spatial RGB,
        not bayer. Returns ("rgb", H×W×3 uint8 image).
      - Post-RGB filter (variant restormer_post_rgb): Restormer (or any RGB-
        in/RGB-out CNN) applied AFTER demosaic, not on bayer. The bayer path
        is a no-op here; a separate apply_post_rgb_cnn() runs on the rendered
        PNG. We signal this by returning the bayer untouched and recording
        the post-RGB CNN config out-of-band (the caller checks
        cnn["cnn_arch_variant"] before calling demosaic_to_png).
    The variant is read from the checkpoint metadata; the registry's
    cnn_arch_variant is a fallback. The "rgb" return tag signals downstream
    code to skip demosaic_to_png and use the RGB result directly."""
    if cnn.get("ckpt_path") is None and cnn.get("cnn_arch_variant") != "ycbcr_decomp":
        return bayer
    if cnn.get("cnn_arch_variant") == "restormer_post_rgb":
        # Bayer path is a no-op; the post-RGB stage runs after demosaic.
        return bayer
    if cnn.get("cnn_arch_variant") == "ycbcr_decomp":
        # Per-channel decomposition (PREVIEW_CHANNEL_DECOMP_PLAN Variant A).
        # Three CNNs in YCbCr space, recombined via inverse BT.709. The CNN
        # entry must carry ckpt_y / ckpt_cb / ckpt_cr fields with relative
        # paths inside the repo (under models/).
        sys.path.insert(0, str(REPO / "tools/cnn"))
        from run_ycbcr_decomp import run_ycbcr_decomp
        ckpts = {}
        for k in ("ckpt_y", "ckpt_cb", "ckpt_cr"):
            p = cnn.get(k)
            if p is None:
                die(2, f"ycbcr_decomp CNN entry missing field '{k}'")
            cp = REPO / p
            if not cp.exists():
                die(2, f"ycbcr_decomp checkpoint missing: {cp}")
            ckpts[k] = str(cp)
        raw_norm = cnn.get("raw_norm", 16383.0)
        rgb_u8 = run_ycbcr_decomp(bayer, ckpts["ckpt_y"], ckpts["ckpt_cb"],
                                  ckpts["ckpt_cr"], raw_norm=raw_norm)
        return ("rgb", rgb_u8)
    import torch
    import torch.nn.functional as F
    sys.path.insert(0, str(REPO / "tools/cnn"))
    from model import build as build_variant
    ckpt_path = REPO / cnn["ckpt_path"]
    if not ckpt_path.exists():
        die(2, f"CNN checkpoint not in repo: {ckpt_path}. "
               f"Migrate the checkpoint with proper metadata before testing.")
    ck = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    variant = ck.get("variant", cnn["cnn_arch_variant"])
    # BIDO = Bayer In, Demosaic Out (joint demosaic + super-res). Legacy
    # variant name "dm_sr" still recognized.
    is_dm_sr = "dm_sr" in variant or "bido" in variant.lower()
    is_sr2x = (not is_dm_sr) and "no_sr" not in variant
    m = build_variant(variant)
    m.load_state_dict(ck["backbone_state"])
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    m.to(dev).eval()
    h, w = bayer.shape
    eh, ew = h - (h & 1), w - (w & 1)
    b = bayer[:eh, :ew]
    pl = np.stack([b[0::2, 0::2], b[0::2, 1::2], b[1::2, 0::2], b[1::2, 1::2]], 0)
    raw_norm = cnn.get("raw_norm", 16383.0)
    res_scale = cnn.get("residual_scale", 0.01)
    x = torch.from_numpy(pl.astype(np.float32) / raw_norm).unsqueeze(0).to(dev)
    H, W = x.shape[-2:]
    ph = (16 - H % 16) % 16
    pw = (16 - W % 16) % 16
    if ph or pw:
        x = F.pad(x, (0, pw, 0, ph), mode="reflect")
    with torch.no_grad():
        if is_dm_sr:
            # Joint demosaic + super-res: output is 3ch RGB at 4× spatial.
            # No baseline-plus-residual — the model produces RGB directly.
            y = m(x).clamp(0, 1)
            # Output dims: (B, 3, 4H, 4W). Convert to (H', W', 3) uint8 for PNG.
            y = y[..., :4*H, :4*W].squeeze(0).cpu().numpy()       # (3, 4H, 4W)
            y = np.transpose(y, (1, 2, 0))                          # (4H, 4W, 3)
            rgb_u8 = np.clip(y * 255.0, 0, 255).astype(np.uint8)
            return ("rgb", rgb_u8)
        if is_sr2x:
            base = F.interpolate(x, scale_factor=2, mode="bicubic", align_corners=False).clamp(0, 1)
            cnn_out = m(x)
            y = (base + res_scale * cnn_out).clamp(0, 1)
            y = y[..., :2 * H, :2 * W].squeeze(0).cpu().numpy()
            # Output is 2x in plane dims → 2x in bayer dims
            out_eh, out_ew = 2 * eh, 2 * ew
            out = np.zeros((out_eh, out_ew), dtype=np.uint16)
            out[0::2, 0::2] = np.clip(y[0] * raw_norm, 0, raw_norm).astype(np.uint16)
            out[0::2, 1::2] = np.clip(y[1] * raw_norm, 0, raw_norm).astype(np.uint16)
            out[1::2, 0::2] = np.clip(y[2] * raw_norm, 0, raw_norm).astype(np.uint16)
            out[1::2, 1::2] = np.clip(y[3] * raw_norm, 0, raw_norm).astype(np.uint16)
            return out
        else:
            y = (x + res_scale * m(x)).clamp(0, 1)
            y = y[..., :H, :W].squeeze(0).cpu().numpy()
            out = bayer.copy()
            out[:eh:2, :ew:2] = np.clip(y[0] * raw_norm, 0, raw_norm).astype(np.uint16)
            out[:eh:2, 1:ew:2] = np.clip(y[1] * raw_norm, 0, raw_norm).astype(np.uint16)
            out[1:eh:2, :ew:2] = np.clip(y[2] * raw_norm, 0, raw_norm).astype(np.uint16)
            out[1:eh:2, 1:ew:2] = np.clip(y[3] * raw_norm, 0, raw_norm).astype(np.uint16)
            return out


_RESTORMER_MODEL_CACHE = {}


def _load_restormer(ckpt_path: str, device):
    """Load Restormer real_denoising-style weights. Cached per (ckpt, device)
    so per-image workers pay the load cost once, not per image. The arch
    module path is repo-local (tools/cnn/restormer_arch.py — rsynced from the
    Restormer GitHub release). Checkpoint is the 'params' dict from
    Denoising/pretrained_models/.../real_denoising.pth.

    Why not just import basicsr: the upstream package pulls in lmdb / cv2 /
    yapf and a bunch of training-only deps. The arch file is self-contained;
    using it directly avoids that bloat."""
    key = (ckpt_path, str(device))
    if key in _RESTORMER_MODEL_CACHE:
        return _RESTORMER_MODEL_CACHE[key]
    import importlib.util
    import torch
    arch_path = REPO / "tools/cnn/restormer_arch.py"
    if not arch_path.exists():
        die(2, f"Restormer arch missing at {arch_path}. "
               f"Rsync from gpr-m5:external/Restormer/basicsr/models/archs/restormer_arch.py.")
    spec = importlib.util.spec_from_file_location("restormer_arch", str(arch_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not Path(ckpt_path).exists():
        die(2, f"Restormer checkpoint missing: {ckpt_path}")
    m = mod.Restormer(LayerNorm_type="BiasFree")
    sd = torch.load(ckpt_path, map_location="cpu")
    m.load_state_dict(sd.get("params", sd))
    m.eval()
    m.to(device)
    _RESTORMER_MODEL_CACHE[key] = m
    return m


def apply_post_rgb_cnn(png_path: Path, cnn: dict, tile: int = 512,
                        overlap: int = 64) -> None:
    """Apply an RGB-in/RGB-out CNN (Restormer-class) to an existing PNG.
    Overwrites png_path with the filtered output. Tiled with reflect-pad
    overlap so we don't OOM on 4K+ inputs — 50 MP 8280x5520 RGB at fp32 on
    MPS is 2.7 GB just for the input tensor; Restormer's intermediates
    push that into swap.

    Caller is responsible for only invoking this when
    cnn['cnn_arch_variant'] == 'restormer_post_rgb'."""
    import os
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import torch
    import torch.nn.functional as F
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    ckpt_raw = cnn["ckpt_path"]
    # Allow absolute paths (the Restormer weight lives off-repo on OWC drive).
    ckpt_path = ckpt_raw if Path(ckpt_raw).is_absolute() else str(REPO / ckpt_raw)
    model = _load_restormer(ckpt_path, device)

    img = Image.open(png_path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0  # (H, W, 3)
    H, W, _ = arr.shape
    # Pad up to multiple of 16 for Restormer's downsampling stages.
    ph = (16 - H % 16) % 16
    pw = (16 - W % 16) % 16
    arr_p = np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode="reflect")
    Hp, Wp, _ = arr_p.shape
    out = np.zeros_like(arr_p)
    weight = np.zeros((Hp, Wp), dtype=np.float32)
    # Cosine taper makes tile blending smooth across overlap (1px from
    # neighbor on edge, full weight in centre). Constant in the centre,
    # cos taper across the overlap band.
    def _taper(n: int, ov: int) -> np.ndarray:
        w = np.ones(n, dtype=np.float32)
        if ov > 0:
            ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, ov, dtype=np.float32))
            w[:ov] = ramp
            w[-ov:] = ramp[::-1]
        return w
    stride = tile - overlap
    with torch.no_grad():
        for y0 in range(0, Hp, stride):
            for x0 in range(0, Wp, stride):
                y1 = min(y0 + tile, Hp)
                x1 = min(x0 + tile, Wp)
                ty0, tx0 = y1 - tile, x1 - tile
                ty0, tx0 = max(0, ty0), max(0, tx0)
                t = arr_p[ty0:ty0 + tile, tx0:tx0 + tile, :]
                # Pad tile if at the edge of a sub-tile-sized image.
                th, tw = t.shape[:2]
                if th < tile or tw < tile:
                    t = np.pad(t, ((0, tile - th), (0, tile - tw), (0, 0)),
                               mode="reflect")
                x = torch.from_numpy(t.transpose(2, 0, 1)[None]).to(device)
                y = model(x).clamp(0, 1)
                yt = y.squeeze(0).cpu().numpy().transpose(1, 2, 0)
                yt = yt[:th, :tw]
                wy = _taper(th, min(overlap, th // 2))
                wx = _taper(tw, min(overlap, tw // 2))
                wmask = np.outer(wy, wx)
                out[ty0:ty0 + th, tx0:tx0 + tw, :] += yt * wmask[..., None]
                weight[ty0:ty0 + th, tx0:tx0 + tw] += wmask
                if y1 >= Hp:
                    break
            if x1 >= Wp:
                continue
    out = out / np.clip(weight[..., None], 1e-6, None)
    out = out[:H, :W, :]
    out_u8 = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    Image.fromarray(out_u8).save(png_path)


def demosaic_to_png(bayer: np.ndarray, dms: dict, src_dng: Path,
                    workdir: Path, out_png: Path,
                    upscale_to: tuple[int, int] | None = None) -> None:
    """Demosaic a bayer plane to a PNG via gpr_tools + sips. The PNG
    natural dims = bayer dims. If `upscale_to` is given, the PNG is
    bicubic-resized to those (width, height) — used for half-res
    pipelines so crop coords and metric comparisons match the source-DNG
    reference space."""
    binary = REPO / dms["binary"]
    if not binary.exists():
        die(2, f"demosaic binary not built: {binary}")
    # Extract source-DNG params (color matrix etc.)
    params_cache = workdir / "params.json"
    if not params_cache.exists():
        cp = subprocess.run([str(binary), "-i", str(src_dng), "-d", "1"],
                            capture_output=True, text=True)
        if cp.returncode != 0:
            die(2, f"gpr_tools params dump failed: {cp.stderr[-200:]}")
        lines = [l for l in cp.stdout.splitlines() if not l.startswith("[")]
        params_cache.write_text("\n".join(lines))
    params = json.loads(params_cache.read_text())
    h, w = bayer.shape
    params["input_width"] = w
    params["input_height"] = h
    params["input_pitch"] = w * 2
    params_run = workdir / f"params_{w}x{h}.json"
    params_run.write_text(json.dumps(params))
    raw_in = workdir / "bayer.raw"
    bayer.tofile(raw_in)
    dng_out = workdir / "out.dng"
    r = subprocess.run([str(binary), "-i", str(raw_in), "-w", str(w), "-h", str(h),
                        "-x", "rggb14", "-o", str(dng_out), "-a", str(params_run)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(2, f"gpr_tools DNG write failed: {r.stderr[-200:]}")
    r = subprocess.run(["sips", "-s", "format", "png", str(dng_out), "--out", str(out_png)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(2, f"sips render failed: {r.stderr[-200:]}")
    # Bicubic-upscale the rendered PNG to reference dims so crops in
    # test_set.json coords are content-aligned across all pipelines,
    # regardless of whether the codec decimated. Without this step a
    # half-res pipeline's PNG is at half-source-dims and the gate's
    # crop coords point at completely different content from the REF.
    if upscale_to is not None:
        img = Image.open(out_png).convert("RGB")
        if img.size != upscale_to:
            img.resize(upscale_to, Image.BICUBIC).save(out_png)


def downsample_for_metrics(png_path: Path, target_w: int) -> np.ndarray:
    img = Image.open(png_path).convert("RGB")
    W, H = img.size
    if W > target_w:
        scale = target_w / W
        img = img.resize((target_w, int(H * scale)), Image.LANCZOS)
    return np.array(img)


def crop_at(png_path: Path, crop: dict, out_path: Path) -> None:
    img = Image.open(png_path).convert("RGB")
    W, H = img.size
    x, y, cw, ch = crop["x"], crop["y"], crop["w"], crop["h"]
    x = max(0, min(x, W - cw))
    y = max(0, min(y, H - ch))
    img.crop((x, y, x + cw, y + ch)).save(out_path)


def build_visual_diff(ref_crop: Path, test_crop: Path, last_best_crop: Path | None,
                      out_path: Path, title: str) -> None:
    """Side-by-side image: REF | this pipeline | (optional) last-best.
    Forces visual inspection at fixed dimensions."""
    parts = [Image.open(ref_crop).convert("RGB"), Image.open(test_crop).convert("RGB")]
    if last_best_crop and last_best_crop.exists():
        parts.append(Image.open(last_best_crop).convert("RGB"))
    cw = max(p.width for p in parts)
    ch = max(p.height for p in parts)
    pad = 8
    total_w = cw * len(parts) + pad * (len(parts) + 1)
    total_h = ch + pad * 2 + 24  # space for label band
    diff = Image.new("RGB", (total_w, total_h), (24, 24, 24))
    for i, p in enumerate(parts):
        diff.paste(p, (pad + i * (cw + pad), pad))
    from PIL import ImageDraw
    d = ImageDraw.Draw(diff)
    labels = ["REF", "PIPELINE"] + (["LAST_BEST"] if len(parts) == 3 else [])
    for i, lbl in enumerate(labels):
        d.text((pad + i * (cw + pad) + 4, ch + pad + 4), f"{lbl}  {title}", fill=(220, 220, 220))
    diff.save(out_path)


# --------------------------------------------------------------------- per-image worker


def _process_one_image(
    im: dict,
    codec: dict,
    cnn: dict,
    dms: dict,
    gate_thresholds: dict,
    crops: dict,
    target_w: int,
    run_dir_str: str,
    workdir_str: str,
) -> tuple[str, dict, str]:
    """Run the complete per-image pipeline.

    Returns (image_id, result_dict, captured_stdout_text). Designed to be
    invoked via ProcessPoolExecutor — all args are picklable, the function
    is module-level, and stdout is captured per-image so the parent can
    re-emit it in the original (sequential) image order for deterministic
    log output.

    The output is bit-identical to the sequential path: same numpy ops,
    same metric inputs, same PNG bytes, same crop coords. The metrics
    library's LPIPS model is loaded inside this process (it lives in a
    module-level cache so it persists across images in the same worker,
    but each worker process loads it independently)."""
    run_dir = Path(run_dir_str)
    workdir = Path(workdir_str)
    src_dng = Path(im["path"])
    buf = io.StringIO()
    with redirect_stdout(buf):
        print(f"\n  -- {im['id']} ({im['character']})")
        bayer, w, h = read_source_bayer(im["path"])
        img_work = workdir / im["id"]
        img_work.mkdir(exist_ok=True)
        # 1. encode/decode through codec
        dec, enc_bytes, enc_ms = encode_decode(codec, bayer, w, h, img_work,
                                                src_dng=im["path"])
        # bayer_psnr requires matched dims. If the codec decimated, downsample
        # the source bayer by 2x2 box average to compare in codec-output space.
        if dec.shape != bayer.shape:
            assert dec.shape[0] * 2 == bayer.shape[0] and dec.shape[1] * 2 == bayer.shape[1]
            bayer_for_codec_metric = (
                bayer[0::2, 0::2].astype(np.int32)
                + bayer[0::2, 1::2].astype(np.int32)
                + bayer[1::2, 0::2].astype(np.int32)
                + bayer[1::2, 1::2].astype(np.int32)
            ) // 4
            bayer_for_codec_metric = bayer_for_codec_metric.astype(np.uint16)
        else:
            bayer_for_codec_metric = bayer
        bp_codec = bayer_psnr(bayer_for_codec_metric, dec)
        # 2. apply CNN (no-op if cnn=none).
        post = apply_cnn(dec, cnn)
        is_rgb_output = isinstance(post, tuple) and post[0] == "rgb"
        if is_rgb_output:
            post_rgb = post[1]
            post_bayer = None
            bp_final = None
        else:
            post_bayer = post
            post_rgb = None
            if post.shape == bayer.shape:
                bp_final = bayer_psnr(bayer, post)
            elif post.shape == bayer_for_codec_metric.shape:
                bp_final = bayer_psnr(bayer_for_codec_metric, post)
            else:
                bp_final = None
        # 3. demosaic both REF and pipeline output to PNG.
        ref_png = run_dir / f"{im['id']}_REF.png"
        pipe_png = run_dir / f"{im['id']}_PIPELINE.png"
        if not ref_png.exists():
            demosaic_to_png(bayer, dms, src_dng, img_work, ref_png)
        if is_rgb_output:
            img = Image.fromarray(post_rgb)
            if img.size != (w, h):
                img = img.resize((w, h), Image.BICUBIC)
            img.save(pipe_png)
        else:
            demosaic_to_png(post_bayer, dms, src_dng, img_work, pipe_png,
                            upscale_to=(w, h))
        # Post-RGB CNN stage (Restormer-class): runs over the demosaiced PNG.
        # Detected by the CNN's cnn_arch_variant field — the bayer pass
        # (apply_cnn above) was a no-op for these CNNs.
        if cnn.get("cnn_arch_variant") == "restormer_post_rgb":
            t_rgb0 = time.time()
            apply_post_rgb_cnn(pipe_png, cnn)
            print(f"     restormer post-RGB: {time.time()-t_rgb0:.1f}s")
        # 4. crop A_detail
        ref_crop_path = run_dir / f"{im['id']}_REF_crop_A_detail.png"
        pipe_crop_path = run_dir / f"{im['id']}_PIPELINE_crop_A_detail.png"
        crop_at(ref_png, crops["A_detail"], ref_crop_path)
        crop_at(pipe_png, crops["A_detail"], pipe_crop_path)
        # 5. downsample to target_w for metric computation
        ref = downsample_for_metrics(ref_png, target_w)
        test = downsample_for_metrics(pipe_png, target_w)
        if test.shape != ref.shape:
            hh = min(ref.shape[0], test.shape[0])
            ww = min(ref.shape[1], test.shape[1])
            ref, test = ref[:hh, :ww], test[:hh, :ww]
        m = compute_visual_metrics(ref, test)
        # 6. evaluate per-metric thresholds
        fails = []
        for key, rule in gate_thresholds.items():
            v = m.get(key)
            if v is None:
                fails.append((key, "missing"))
                continue
            if "max" in rule and v > rule["max"]:
                fails.append((key, f"{v:.4f} > {rule['max']}"))
            if "min" in rule and v < rule["min"]:
                fails.append((key, f"{v:.4f} < {rule['min']}"))
        verdict = "PASS" if not fails else "FAIL"
        row = {
            **m,
            "bayer_psnr_codec": bp_codec,
            "bayer_psnr_final": bp_final,
            "enc_bytes": enc_bytes,
            "enc_ms": enc_ms,
            "ref_crop": str(ref_crop_path),
            "pipeline_crop": str(pipe_crop_path),
            "verdict": verdict,
            "fails": [{"metric": k, "reason": r} for k, r in fails],
        }
        print(f"     LPIPS={m.get('lpips'):.4f}  Y-PSNR={m.get('y_psnr'):.2f}  "
              f"MS-SSIM={m.get('ms_ssim'):.4f}  ΔE={m.get('dE2000_mean'):.2f}  "
              f"=> {verdict}")
        if fails:
            for k, r in fails:
                print(f"        FAIL {k}: {r}")
    return im["id"], row, buf.getvalue()


# --------------------------------------------------------------------- runner


def _cleanup_fullres_pngs(run_dir: Path) -> tuple[int, int]:
    """Delete the inspection-only full-res REF/PIPELINE PNGs from `run_dir`,
    leaving run.json + WORST_*_visual_diff.png + per-image crop PNGs intact.

    A single REF/PIPELINE pair at 50 MP is ~150 MB each; an 8-image run
    leaks ~1.2 GB of intermediate PNGs that the gate doesn't archive. The
    crops and the worst-image visual diff are the durable evidence the
    runner produces — full-res PNGs only matter for ad-hoc inspection
    (which is opt-in via --keep-fullres-pngs or GATE_KEEP_FULLRES=1).

    Matches files of the form `<id>_REF.png` and `<id>_PIPELINE.png` at
    the run_dir root. Crops `<id>_REF_crop_*.png` /
    `<id>_PIPELINE_crop_*.png` are explicitly preserved because their
    filenames contain `_crop_` (which we filter on), and `WORST_*` files
    are preserved because they don't end in `_REF.png` /
    `_PIPELINE.png` (the WORST is `WORST_<id>_visual_diff.png`).

    Returns (files_deleted, bytes_freed)."""
    n = 0
    freed = 0
    for p in run_dir.iterdir():
        if not p.is_file():
            continue
        name = p.name
        # Crops have `_crop_` in the filename — never delete those.
        if "_crop_" in name:
            continue
        # Only target the two specific full-res filenames.
        if name.endswith("_REF.png") or name.endswith("_PIPELINE.png"):
            try:
                sz = p.stat().st_size
                p.unlink()
                n += 1
                freed += sz
            except OSError:
                pass
    return n, freed


def pipeline_run_hash(pipeline_id: str, codec: dict, cnn: dict,
                       dms: dict, image_shas: list[str], gates_sha: str) -> str:
    payload = json.dumps({
        "pipeline_id": pipeline_id,
        "codec_env_canonical": canonical_env({**codec.get("env", {}),
                                              "QUALITY": codec.get("quality")}),
        "cnn_ckpt_sha256": cnn.get("ckpt_sha256", "none"),
        "demosaicer": dms.get("binary", ""),
        "image_shas": sorted(image_shas),
        "gates_sha": gates_sha,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def evaluate_pipeline(pipeline_name: str, keep_fullres: bool = False) -> dict:
    gates = load_json(GATES_PATH)
    test_set = load_json(TEST_SET_PATH)
    registry = load_json(REGISTRY_PATH)
    if pipeline_name not in registry["pipelines"]:
        die(3, f"unknown pipeline: {pipeline_name}. "
               f"Available: {list(registry['pipelines'].keys())}")
    pipe = registry["pipelines"][pipeline_name]
    codec = registry["codecs"][pipe["codec"]]
    cnn = registry["cnns"][pipe["cnn"]]
    dms = registry["demosaicers"][pipe["demosaic"]]
    ship_class = pipe["ship_class"]
    gate_thresholds = gates["ship_classes"][ship_class]["per_image"]

    target_w = test_set["metric_eval_dims"]["width"]
    images = test_set["images"]
    crops = test_set["crops"]

    # Verify source DNGs exist before any work.
    missing = [im for im in images if not Path(im["path"]).exists()]
    if missing:
        die(2, f"source DNG(s) missing: {[m['id'] for m in missing]}")

    # Source SHAs (truncated for stable hash without re-hashing 50MB each run)
    image_shas = []
    for im in images:
        p = Path(im["path"])
        # Stat-based stamp is fine for local dev; CI would use sha256.
        image_shas.append(f"{im['id']}:{p.stat().st_size}:{int(p.stat().st_mtime)}")

    gates_sha = hashlib.sha256(GATES_PATH.read_bytes()).hexdigest()[:16]
    run_hash = pipeline_run_hash(pipeline_name, codec, cnn, dms, image_shas, gates_sha)
    run_dir = RUNS_DIR / f"{run_hash}"
    run_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=f"gate_{run_hash}_"))

    print(f"\n=== pipeline: {pipeline_name}")
    print(f"=== run_hash: {run_hash}  ship_class: {ship_class}")
    print(f"=== run_dir:  {run_dir}")

    results = {
        "pipeline": pipeline_name,
        "ship_class": ship_class,
        "run_hash": run_hash,
        "gates_sha": gates_sha,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "images": {},
    }

    # Per-image work is independent (each image has its own tempdir; the
    # codec/CNN/demosaic/sips/metrics chain only reads the source DNG and
    # writes into run_dir/img_work). Run images in parallel via
    # ProcessPoolExecutor — workers are subprocess-heavy (codec binary,
    # gpr_tools, sips) AND own a per-process PyTorch/LPIPS state, so process
    # parallelism gives the speedup without thread/GIL contention.
    #
    # Set GATE_MAX_WORKERS=1 to force sequential execution (debugging /
    # numerical-diff verification).
    max_workers = int(os.environ.get("GATE_MAX_WORKERS", str(min(4, len(images)))))
    max_workers = max(1, min(max_workers, len(images)))

    image_logs: dict[str, str] = {}
    try:
        if max_workers == 1:
            for im in images:
                im_id, row, log = _process_one_image(
                    im, codec, cnn, dms, gate_thresholds, crops,
                    target_w, str(run_dir), str(workdir),
                )
                results["images"][im_id] = row
                image_logs[im_id] = log
                # Stream log immediately in the sequential path so behavior
                # matches the pre-parallel runner when debugging.
                sys.stdout.write(log)
                sys.stdout.flush()
        else:
            with _cf.ProcessPoolExecutor(max_workers=max_workers) as ex:
                futures = {
                    ex.submit(
                        _process_one_image, im, codec, cnn, dms,
                        gate_thresholds, crops, target_w,
                        str(run_dir), str(workdir),
                    ): im["id"]
                    for im in images
                }
                for fut in _cf.as_completed(futures):
                    im_id, row, log = fut.result()
                    results["images"][im_id] = row
                    image_logs[im_id] = log
            # Emit per-image logs in the original (registry) image order
            # so stdout is deterministic regardless of completion order.
            for im in images:
                log = image_logs.get(im["id"], "")
                if log:
                    sys.stdout.write(log)
            sys.stdout.flush()
            # Reinsert results in registry order so json.dumps writes them
            # in the same order as the sequential runner — keeps run.json
            # byte-identical for any consumer that diffs it textually.
            ordered = {im["id"]: results["images"][im["id"]] for im in images
                       if im["id"] in results["images"]}
            results["images"] = ordered
    finally:
        pass

    # 7. sort worst-first by LPIPS (mandatory)
    ranked = sorted(
        results["images"].items(),
        key=lambda kv: kv[1].get("lpips", 0.0) or 0.0,
        reverse=True,
    )
    results["worst_first"] = [k for k, _ in ranked]
    worst_id, worst_row = ranked[0]

    # 8. build visual-diff for the worst image
    last_best_link = run_dir / "last_best_crop.png"  # placeholder; updated when --update-baseline
    diff_path = run_dir / f"WORST_{worst_id}_visual_diff.png"
    build_visual_diff(
        Path(worst_row["ref_crop"]),
        Path(worst_row["pipeline_crop"]),
        last_best_link if last_best_link.exists() else None,
        diff_path,
        title=f"{pipeline_name[:50]}",
    )
    results["worst_image"] = {
        "id": worst_id,
        "visual_diff_png": str(diff_path),
        "lpips": worst_row.get("lpips"),
    }

    # 9. overall verdict: any image FAIL -> FAIL
    any_fail = any(r["verdict"] == "FAIL" for r in results["images"].values())
    results["verdict"] = "FAIL" if any_fail else "PASS"
    results["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    # 10. write the run log
    (run_dir / "run.json").write_text(json.dumps(results, indent=2, default=str))

    # 10b. clean up the full-res REF/PIPELINE PNGs unless the caller asked
    # us to keep them. These are ~150 MB each (8 per run = ~1.2 GB) and
    # only useful for ad-hoc visual inspection — the crops and the WORST
    # diff are the durable artifacts. We only reach this point with a
    # PASS/FAIL verdict; INDETERMINATE paths exit earlier via die(), and
    # an exception in the per-image work would also bypass this — so on
    # any abnormal exit, everything is preserved for debugging.
    if not keep_fullres:
        deleted, freed = _cleanup_fullres_pngs(run_dir)
        if deleted:
            print(f"\n=== Cleaned up {deleted} full-res PNG(s), "
                  f"freed {freed / (1024*1024):.1f} MB "
                  f"(--keep-fullres-pngs / GATE_KEEP_FULLRES=1 to retain)")

    # 11. print worst-first summary (mandatory format)
    print(f"\n=== VERDICT: {results['verdict']}")
    print(f"=== Worst-first by LPIPS:")
    for img_id in results["worst_first"]:
        row = results["images"][img_id]
        print(f"   {img_id:12s}  LPIPS={row.get('lpips'):.4f}  "
              f"verdict={row['verdict']}")
    print(f"\n=== Visual diff for WORST image written to:")
    print(f"   {diff_path}")
    print(f"\n=== Run log: {run_dir / 'run.json'}")
    return results


# --------------------------------------------------------------------- main


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pipeline", help="Full pipeline name from registry.json")
    p.add_argument("--claim", action="store_true",
                   help="After PASS, prompt for inspection-sentence to append to claims_log.md")
    p.add_argument("--keep-fullres-pngs", action="store_true",
                   help="Keep the full-res REF/PIPELINE PNGs (~150 MB each, ~1.2 GB/run). "
                        "Default is to delete them after the verdict is computed; the run.json, "
                        "WORST_*_visual_diff.png, and per-image crops are always kept. "
                        "GATE_KEEP_FULLRES=1 in the environment has the same effect.")
    args = p.parse_args()

    # Env-var override is OR'd with the flag — either one keeps the PNGs.
    keep_fullres = args.keep_fullres_pngs or os.environ.get("GATE_KEEP_FULLRES", "") not in ("", "0")

    res = evaluate_pipeline(args.pipeline, keep_fullres=keep_fullres)

    if args.claim:
        if res["verdict"] != "PASS":
            print("\n--claim requested but verdict is FAIL. Refusing to log.", file=sys.stderr)
            sys.exit(1)
        if not sys.stdin.isatty():
            print("\n--claim requires interactive stdin for the inspection sentence.",
                  file=sys.stderr)
            sys.exit(2)
        print(f"\nReview the visual diff at: {res['worst_image']['visual_diff_png']}")
        sentence = input("Inspection sentence (>=6 words, must include a concrete noun): ").strip()
        nouns = ["rocks", "sky", "edge", "blockiness", "haze", "noise",
                 "detail", "texture", "shadow", "highlight", "crosshatch",
                 "smooth", "ringing", "color"]
        words = sentence.split()
        if len(words) < 6:
            print("Sentence too short (<6 words). Refusing.", file=sys.stderr)
            sys.exit(2)
        if not any(n in sentence.lower() for n in nouns):
            print(f"Sentence has no concrete noun (one of {nouns}). Refusing.",
                  file=sys.stderr)
            sys.exit(2)
        CLAIMS_LOG.parent.mkdir(exist_ok=True)
        line = (f"- {time.strftime('%Y-%m-%d %H:%M')}  pipeline=`{args.pipeline}`  "
                f"run={res['run_hash']}  worst_lpips={res['worst_image']['lpips']:.4f}  "
                f"worst_image={res['worst_image']['id']}  "
                f"visual_description=\"{sentence}\"\n")
        with open(CLAIMS_LOG, "a") as f:
            f.write(line)
        print(f"Logged claim to {CLAIMS_LOG}")

    sys.exit(0 if res["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
