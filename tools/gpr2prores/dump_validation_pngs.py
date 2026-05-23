"""Dump sanity PNGs from the validation Bayer dumps (demosaic via simple bilinear)."""
import numpy as np
from PIL import Image

W, H = 8280, 5520

for name, path in [("coreml", "/tmp/bayer_coreml.raw"), ("metal", "/tmp/bayer_metal.raw")]:
    bayer = np.fromfile(path, dtype=np.uint16).reshape(H, W)
    # very crude downsample by 2 then 2-tap bayer-to-RGB just for visual sanity
    R = bayer[0::2, 0::2].astype(np.float32)
    G1 = bayer[0::2, 1::2].astype(np.float32)
    G2 = bayer[1::2, 0::2].astype(np.float32)
    B = bayer[1::2, 1::2].astype(np.float32)
    G = (G1 + G2) * 0.5
    rgb = np.stack([R, G, B], axis=-1)
    # crude tone: gamma 2.2, scale by 4x
    rgb = np.clip(rgb / 16383.0 * 4.0, 0, 1) ** (1/2.2)
    rgb8 = (rgb * 255).astype(np.uint8)
    # downsample 2x by stride
    small = rgb8[::4, ::4]
    Image.fromarray(small).save(f"/tmp/validate_{name}.png")
    print(f"  wrote /tmp/validate_{name}.png  {small.shape}")
