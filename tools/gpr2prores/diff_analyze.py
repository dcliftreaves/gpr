"""Where exactly do the Metal vs CoreML bayer outputs differ?"""
import numpy as np
import os
import tempfile
from pathlib import Path
W, H = 8280, 5520
def default_external_root() -> Path:
    mounted = Path("/Volumes/OWC_8TB/gpr_work")
    if mounted.exists():
        return mounted
    return Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "gpr_work"


TMPDIR = Path(os.environ.get(
    "TMPDIR", Path(os.environ.get("GPR_EXTERNAL_ROOT", default_external_root())) / "tmp"))
a = np.fromfile(TMPDIR / "bayer_coreml.raw", dtype=np.uint16).reshape(H, W)
b = np.fromfile(TMPDIR / "bayer_metal.raw", dtype=np.uint16).reshape(H, W)
diff = np.abs(a.astype(np.int32) - b.astype(np.int32))

# Where are the worst diffs?
idx = np.unravel_index(np.argmax(diff), diff.shape)
print(f"max diff {diff.max()} at row={idx[0]} col={idx[1]}")
print(f"  CoreML pixel = {a[idx[0], idx[1]]}, Metal pixel = {b[idx[0], idx[1]]}")
print(f"  near edge?  row in [0, {H-1}], col in [0, {W-1}]")

# 2D heatmap of diff in 64x64 blocks
import sys
H_blocks = H // 64
W_blocks = W // 64
block = diff[:H_blocks*64, :W_blocks*64].reshape(H_blocks, 64, W_blocks, 64).mean(axis=(1, 3))
print(f"\nblock mean diff stats: min={block.min():.2f}  median={np.median(block):.2f}  max={block.max():.2f}")
print(f"top-left  block diff: {block[:5, :5].round(1)}")
print(f"top-right block diff: {block[:5, -5:].round(1)}")
print(f"bot-left  block diff: {block[-5:, :5].round(1)}")
print(f"bot-right block diff: {block[-5:, -5:].round(1)}")
print(f"center   block diff: {block[H_blocks//2-3:H_blocks//2+3, W_blocks//2-3:W_blocks//2+3].round(1)}")

# Show distribution of differences
print(f"\nfull diff distribution:")
for pct in [50, 75, 90, 95, 99, 99.9, 99.99, 100]:
    print(f"  p{pct}: {np.percentile(diff, pct):.0f}")
