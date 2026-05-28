"""Precompute Restormer (real_denoising.pth) teacher targets per tile.

Input  : tiles_ml2_q3_dec2_dmsr_gate.npz on M5
         (codec_R/G1/G2/B uint16 128x128, tgt_rgb uint8 512x512x3, ...)
Output : tiles_ml2_q3_dec2_dmsr_gate_distill.npz with ALL existing fields
         plus tgt_rgb_teacher uint8 (N, 512, 512, 3).

INPUT-MODE TRADEOFF (must read before changing):
- BIDO_DISTILLATION_PLAN.md §3 says feed Restormer the *codec-degraded*
  bilinear-demosaiced -> bicubic 2x RGB (i.e. the same distribution the
  student sees), so the teacher output is a plausible upper bound.
- However: Restormer real_denoising was trained on natural sRGB
  (tone-curve-applied) images and our codec path produces linear-raw
  near-darkroom RGB. Feeding raw-linear codec output is OOD for
  Restormer and produces ~3x darker output than the gate target
  (verified dry-run: out_u8 6/28 vs tgt_rgb 19/68). With L1 in
  msL1(pred, tgt_teacher) that color drift would actively pull the
  student AWAY from the gate color space.
- Pragmatic choice (default): run Restormer on tgt_rgb (the clean
  sips-rendered gate target) so the teacher is IN distribution for
  Restormer and IN the gate color space. This makes the teacher a
  light denoise+enhance of the gate target — a slightly-cleaner
  ground truth that adds a perceptual pull. The student is so far from
  tgt_rgb in LPIPS (~0.45 worst) that an upper-bound target is fine.
- Honesty flag: --input-mode codec-degraded reverts to the plan's
  literal wording. Default is --input-mode tgt-rgb.

Resume-friendly: writes a progress sidecar
  tiles_ml2_q3_dec2_dmsr_gate_distill.progress.npy
holding the cumulative count of completed tiles. The teacher field is built
chunk-by-chunk into a uint8 memmap so we never need to hold all of it in RAM.

Sanity-PNG dump: writes 3 teacher tiles to /tmp/teacher_sample_*.png for
the visual gate per plan section 11.
"""
from __future__ import annotations
import os, time, argparse, importlib.util
import numpy as np
import torch
import torch.nn.functional as F

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

RESTORMER_REPO = os.path.expanduser("~/external/Restormer")
CKPT = os.path.expanduser(
    "~/external/Restormer/Denoising/pretrained_models/pretrained_models/real_denoising.pth")
IN_NPZ  = os.path.expanduser("~/gpr_data/tiles_ml2_q3_dec2_dmsr_gate.npz")
OUT_NPZ = os.path.expanduser("~/gpr_data/tiles_ml2_q3_dec2_dmsr_gate_distill.npz")
TEACHER_MEMMAP = os.path.expanduser("~/gpr_data/tgt_rgb_teacher.memmap.uint8")
PROGRESS_PATH  = os.path.expanduser(
    "~/gpr_data/tiles_ml2_q3_dec2_dmsr_gate_distill.progress.npy")
SAMPLE_DIR = "/tmp"

BATCH = 4
RAW_NORM = 16383.0


def load_restormer(device):
    spec = importlib.util.spec_from_file_location(
        "restormer_arch",
        os.path.join(RESTORMER_REPO, "basicsr/models/archs/restormer_arch.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    m = mod.Restormer(LayerNorm_type="BiasFree")
    sd = torch.load(CKPT, map_location="cpu")
    m.load_state_dict(sd.get("params", sd))
    m.eval(); m.to(device)
    return m


def _build_kernels(device, dtype):
    k_rb = torch.tensor([[1, 2, 1], [2, 4, 2], [1, 2, 1]],
                        dtype=dtype, device=device) / 4.0
    k_g = torch.tensor([[0, 1, 0], [1, 4, 1], [0, 1, 0]],
                       dtype=dtype, device=device) / 4.0
    return k_rb.view(1, 1, 3, 3), k_g.view(1, 1, 3, 3)


def bayer4_to_rgb(planes: torch.Tensor) -> torch.Tensor:
    """(B, 4, H, W) -> (B, 3, 2H, 2W) bilinear RGB.
    Layout: planes[:,0]=R at (0,0), planes[:,1]=G1 at (0,1),
            planes[:,2]=G2 at (1,0), planes[:,3]=B at (1,1).
    Matches train_demosaic_sr.py:bayer_4plane_to_rgb.
    """
    B, _, H, W = planes.shape
    bayer = torch.zeros((B, 1, 2 * H, 2 * W), device=planes.device, dtype=planes.dtype)
    bayer[:, 0, 0::2, 0::2] = planes[:, 0]
    bayer[:, 0, 0::2, 1::2] = planes[:, 1]
    bayer[:, 0, 1::2, 0::2] = planes[:, 2]
    bayer[:, 0, 1::2, 1::2] = planes[:, 3]
    mR  = torch.zeros_like(bayer); mR[:, :, 0::2, 0::2] = 1
    mG1 = torch.zeros_like(bayer); mG1[:, :, 0::2, 1::2] = 1
    mG2 = torch.zeros_like(bayer); mG2[:, :, 1::2, 0::2] = 1
    mB  = torch.zeros_like(bayer); mB[:, :, 1::2, 1::2] = 1
    sR = bayer * mR; sG = bayer * (mG1 + mG2); sB = bayer * mB
    k_rb, k_g = _build_kernels(planes.device, planes.dtype)
    R  = F.conv2d(sR, k_rb, padding=1)
    G  = F.conv2d(sG, k_g,  padding=1)
    Bc = F.conv2d(sB, k_rb, padding=1)
    return torch.cat([R, G, Bc], dim=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-mode", choices=["tgt-rgb", "codec-degraded"],
                    default="tgt-rgb",
                    help="What to feed Restormer. tgt-rgb (default): the "
                         "clean sips-rendered gate target. codec-degraded: "
                         "bilinear-demosaiced + bicubic-2x codec output "
                         "(plan §3 literal wording; produces dark "
                         "linear-raw teacher output).")
    ap.add_argument("--stride", type=int, default=1,
                    help="Process every Nth tile (e.g. --stride 4 = ~4980 of "
                         "19920). Output NPZ contains only the kept tiles "
                         "(all fields subsampled identically). Use when "
                         "teacher precompute is the bottleneck.")
    args = ap.parse_args()

    t_start = time.time()
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"[teacher-precompute] device={device}  input-mode={args.input_mode}",
          flush=True)

    print(f"[teacher-precompute] loading Restormer from {CKPT}", flush=True)
    model = load_restormer(device)
    nparams = sum(p.numel() for p in model.parameters())
    print(f"[teacher-precompute] Restormer params: {nparams:,}", flush=True)

    print(f"[teacher-precompute] mmapping NPZ: {IN_NPZ}", flush=True)
    npz = np.load(IN_NPZ, mmap_mode="r", allow_pickle=True)
    n_full = npz["codec_R"].shape[0]
    stride = max(1, args.stride)
    # Stride-subsample keeps tiles 0, stride, 2*stride, ...
    keep_indices = np.arange(0, n_full, stride, dtype=np.int64)
    n_tiles = len(keep_indices)
    print(f"[teacher-precompute] n_full={n_full} stride={stride} "
          f"n_tiles_kept={n_tiles}", flush=True)

    teacher_shape = (n_tiles, 512, 512, 3)
    teacher_bytes = int(np.prod(teacher_shape))
    if os.path.exists(TEACHER_MEMMAP):
        sz = os.path.getsize(TEACHER_MEMMAP)
        if sz != teacher_bytes:
            print(f"[teacher-precompute] memmap size mismatch ({sz} vs "
                  f"{teacher_bytes}); recreating", flush=True)
            os.remove(TEACHER_MEMMAP)
            if os.path.exists(PROGRESS_PATH):
                os.remove(PROGRESS_PATH)
    teacher = np.memmap(TEACHER_MEMMAP, dtype=np.uint8,
                        mode="r+" if os.path.exists(TEACHER_MEMMAP) else "w+",
                        shape=teacher_shape)

    if os.path.exists(PROGRESS_PATH):
        completed = int(np.load(PROGRESS_PATH))
        print(f"[teacher-precompute] resume from tile {completed}", flush=True)
    else:
        completed = 0
    if completed > n_tiles:
        completed = n_tiles

    if completed == n_tiles:
        print("[teacher-precompute] tile pass already complete; "
              "proceeding to NPZ assembly", flush=True)

    anchor = completed
    t_loop = time.time()
    samples_dumped = False
    last_log = completed

    while completed < n_tiles:
        i0 = completed
        i1 = min(i0 + BATCH, n_tiles)
        # Map subset indices [i0:i1] back to full-NPZ indices for the slice
        src_idx = keep_indices[i0:i1]
        # Fancy indexing on memmap is fine for small batches
        if args.input_mode == "tgt-rgb":
            tgt_np = np.asarray(npz["tgt_rgb"][src_idx]).astype(np.float32) / 255.0
            rgb512 = torch.from_numpy(np.transpose(tgt_np, (0, 3, 1, 2))).to(device)
        else:
            planes_np = np.stack([
                np.asarray(npz["codec_R"][src_idx]),
                np.asarray(npz["codec_G1"][src_idx]),
                np.asarray(npz["codec_G2"][src_idx]),
                np.asarray(npz["codec_B"][src_idx]),
            ], axis=1).astype(np.float32) / RAW_NORM
            planes = torch.from_numpy(planes_np).to(device)
            with torch.no_grad():
                rgb256 = bayer4_to_rgb(planes).clamp(0, 1)
                rgb512 = F.interpolate(rgb256, scale_factor=2,
                                       mode="bicubic",
                                       align_corners=False).clamp(0, 1)

        with torch.no_grad():
            out = model(rgb512).clamp(0, 1)
        if device.type == "mps":
            torch.mps.synchronize()
        out_np = out.cpu().numpy()
        out_np = np.transpose(out_np, (0, 2, 3, 1))
        out_u8 = np.clip(out_np * 255.0 + 0.5, 0, 255).astype(np.uint8)
        teacher[i0:i1] = out_u8
        completed = i1

        if completed - last_log >= 100 or completed == n_tiles:
            teacher.flush()
            np.save(PROGRESS_PATH, np.int64(completed))
            done_since_anchor = max(completed - anchor, 1)
            elapsed = time.time() - t_loop
            per_tile = elapsed / done_since_anchor
            eta_min = (n_tiles - completed) * per_tile / 60.0
            print(f"[teacher-precompute] {completed}/{n_tiles} "
                  f"({100.0*completed/n_tiles:5.1f}%) "
                  f"avg {per_tile*1000:.0f} ms/tile  eta {eta_min:.1f} min",
                  flush=True)
            last_log = completed

        if not samples_dumped and completed >= 3:
            try:
                from PIL import Image
                for k in range(3):
                    Image.fromarray(np.asarray(teacher[k])).save(
                        os.path.join(SAMPLE_DIR, f"teacher_sample_{k}.png"))
                print(f"[teacher-precompute] dumped 3 sample PNGs to "
                      f"{SAMPLE_DIR}/teacher_sample_*.png", flush=True)
                samples_dumped = True
            except Exception as e:
                print(f"[teacher-precompute] sample dump skipped: {e}", flush=True)
                samples_dumped = True  # don't retry forever

    teacher.flush()
    np.save(PROGRESS_PATH, np.int64(completed))
    print(f"[teacher-precompute] all {n_tiles} tiles done in "
          f"{time.time()-t_start:.1f}s", flush=True)

    print(f"[teacher-precompute] assembling NPZ -> {OUT_NPZ}", flush=True)
    # Build a full-size (n_full) teacher array, copying tgt_rgb for non-computed
    # tiles + a parallel uint8 mask (1 = teacher valid, 0 = fallback to tgt_rgb).
    # This lets the trainer use the full NPZ and apply the β loss term only on
    # the stride-subsampled subset (so the student trains on all 19920 tiles
    # with extra signal on ~4980 of them).
    print(f"[teacher-precompute] assembling full-size teacher array "
          f"(n_full={n_full})", flush=True)
    teacher_full = np.empty((n_full, 512, 512, 3), dtype=np.uint8)
    teacher_mask = np.zeros((n_full,), dtype=np.uint8)
    # Stream-copy tgt_rgb in chunks to fall back when teacher unavailable.
    chunk = 256
    for i in range(0, n_full, chunk):
        j = min(i + chunk, n_full)
        teacher_full[i:j] = np.asarray(npz["tgt_rgb"][i:j])
    # Overwrite kept indices with computed teacher tiles
    for k, src_i in enumerate(keep_indices):
        teacher_full[int(src_i)] = teacher[k]
        teacher_mask[int(src_i)] = 1
    np.savez(
        OUT_NPZ,
        codec_R=np.asarray(npz["codec_R"]),
        codec_G1=np.asarray(npz["codec_G1"]),
        codec_G2=np.asarray(npz["codec_G2"]),
        codec_B=np.asarray(npz["codec_B"]),
        src=np.asarray(npz["src"]),
        src_lookup_names=np.asarray(npz["src_lookup_names"]),
        tgt_rgb=np.asarray(npz["tgt_rgb"]),
        tgt_rgb_teacher=teacher_full,
        tgt_rgb_teacher_mask=teacher_mask,
    )
    print(f"[teacher-precompute] DONE. wall={time.time()-t_start:.1f}s",
          flush=True)


if __name__ == "__main__":
    main()
