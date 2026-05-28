"""Assemble the final distillation NPZ from the in-progress teacher memmap.

Reads:
  - tiles_ml2_q3_dec2_dmsr_gate.npz   (source NPZ, 19920 tiles)
  - tgt_rgb_teacher.memmap.uint8       (computed teacher tiles for the stride
                                        subset, written by
                                        build_teacher_targets_restormer.py)
  - tiles_ml2_q3_dec2_dmsr_gate_distill.progress.npy   (completed count)

Writes:
  - tiles_ml2_q3_dec2_dmsr_gate_distill.npz with all 19920 tiles AND:
      tgt_rgb_teacher        : (19920, 512, 512, 3) uint8
                               (= tgt_rgb on positions not in the stride
                                  subset, = computed Restormer output on
                                  positions in it)
      tgt_rgb_teacher_mask   : (19920,) uint8 (1 where computed, 0 fallback)

Use this when the teacher precompute used an older script that wrote a
subset-only NPZ but you want a full-size NPZ with a mask so training can
use ALL tiles (with the β loss applied only on the stride-subsampled
subset). Idempotent — safe to rerun.
"""
from __future__ import annotations
import os
import numpy as np

IN_NPZ = os.path.expanduser("~/gpr_data/tiles_ml2_q3_dec2_dmsr_gate.npz")
OUT_NPZ = os.path.expanduser("~/gpr_data/tiles_ml2_q3_dec2_dmsr_gate_distill.npz")
TEACHER_MEMMAP = os.path.expanduser("~/gpr_data/tgt_rgb_teacher.memmap.uint8")
PROGRESS_PATH = os.path.expanduser(
    "~/gpr_data/tiles_ml2_q3_dec2_dmsr_gate_distill.progress.npy")

STRIDE = 4  # must match build_teacher_targets_restormer.py invocation


def main():
    print(f"[assemble] loading source NPZ {IN_NPZ}", flush=True)
    npz = np.load(IN_NPZ, mmap_mode="r", allow_pickle=True)
    n_full = npz["codec_R"].shape[0]
    keep_indices = np.arange(0, n_full, STRIDE, dtype=np.int64)
    n_stride = len(keep_indices)
    print(f"[assemble] n_full={n_full} stride={STRIDE} n_stride={n_stride}",
          flush=True)

    if not os.path.exists(PROGRESS_PATH):
        raise FileNotFoundError(f"progress file missing: {PROGRESS_PATH}")
    completed = int(np.load(PROGRESS_PATH))
    print(f"[assemble] completed stride-tile count: {completed}/{n_stride}",
          flush=True)
    if completed < n_stride:
        print(f"[assemble] WARNING: teacher precompute incomplete; only "
              f"{completed} tiles will have valid teacher targets", flush=True)

    teacher_shape = (n_stride, 512, 512, 3)
    teacher_mm = np.memmap(TEACHER_MEMMAP, dtype=np.uint8, mode="r",
                           shape=teacher_shape)

    print(f"[assemble] building full-size teacher_full (uint8)", flush=True)
    teacher_full = np.empty((n_full, 512, 512, 3), dtype=np.uint8)
    teacher_mask = np.zeros((n_full,), dtype=np.uint8)
    chunk = 256
    for i in range(0, n_full, chunk):
        j = min(i + chunk, n_full)
        teacher_full[i:j] = np.asarray(npz["tgt_rgb"][i:j])
    for k in range(completed):
        src_i = int(keep_indices[k])
        teacher_full[src_i] = teacher_mm[k]
        teacher_mask[src_i] = 1
    print(f"[assemble] valid teacher tiles: {int(teacher_mask.sum())}",
          flush=True)

    print(f"[assemble] writing {OUT_NPZ}", flush=True)
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
    sz = os.path.getsize(OUT_NPZ) / (1024**3)
    print(f"[assemble] done. NPZ size: {sz:.1f} GB", flush=True)


if __name__ == "__main__":
    main()
