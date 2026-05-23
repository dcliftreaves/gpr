"""Validate that hybrid backend produces output close to MPSGraph baseline.

Decodes the same 3-frame .mov clips made with --cnn-backend mpsgraph vs metal
and computes per-frame max/mean abs difference.

Usage:
  python3 validate_hybrid_vs_mpsgraph.py /tmp/mpsgraph_test.mov /tmp/hybrid_test.mov
"""
import sys, subprocess, os, json
import numpy as np

mov_a = sys.argv[1]
mov_b = sys.argv[2]
print(f"compare: {mov_a}  vs  {mov_b}")

def decode_mov_to_raw(mov):
    """Use ffmpeg to decode mov to raw YUV/RGB; we'll grab the Y channel."""
    # Use ffmpeg to dump raw frames (each frame as 16-bit big endian RGB).
    out = f"/tmp/_decode_{os.path.basename(mov)}.raw"
    cmd = ["ffmpeg", "-y", "-i", mov,
           "-pix_fmt", "rgb48le",
           "-f", "rawvideo", out]
    subprocess.run(cmd, capture_output=True, check=True)
    # Get dims from ffprobe.
    p = subprocess.run(["ffprobe", "-loglevel", "error",
                        "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,nb_frames",
                        "-of", "json", mov], capture_output=True, text=True)
    info = json.loads(p.stdout)["streams"][0]
    w = int(info["width"]); h = int(info["height"])
    n = int(info["nb_frames"])
    data = np.fromfile(out, dtype=np.uint16)
    # Each frame: w*h*3 uint16
    expected = n * w * h * 3
    if data.size != expected:
        print(f"WARN: size {data.size} != expected {expected} (n={n}, w={w}, h={h})")
        n = data.size // (w * h * 3)
    data = data.reshape(n, h, w, 3)
    return data

a = decode_mov_to_raw(mov_a)
b = decode_mov_to_raw(mov_b)

print(f"  a shape={a.shape}  b shape={b.shape}")
n = min(a.shape[0], b.shape[0])
if a.shape != b.shape:
    print(f"WARN: shapes differ, taking first {n} frames")
a = a[:n]; b = b[:n]

# Normalize to [0, 1] for fp16-units-like comparison.
a_f = a.astype(np.float32) / 65535.0
b_f = b.astype(np.float32) / 65535.0
diff = np.abs(a_f - b_f)
print(f"\n=== {n} frames, RGB 16-bit ===")
print(f"  max abs diff (normalized [0,1]): {diff.max():.5f}")
print(f"  mean abs diff: {diff.mean():.6f}")
print(f"  >0.01 fraction: {(diff > 0.01).mean()*100:.3f}%")
print(f"  >0.05 fraction: {(diff > 0.05).mean()*100:.3f}%")
# fp16 epsilon ~ 0.00098; max abs diff < 0.01 is comfortable
print(f"\n  {'PASS' if diff.max() < 0.01 else ('OK-ish' if diff.max() < 0.05 else 'FAIL')}: max diff < 0.01 (target)")
