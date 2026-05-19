#!/usr/bin/env python3
"""Render source DNG and codec-decoded bayer through the proper DNG pipeline.

Uses rawpy (libraw) to apply white balance, color matrix, gamma, and demosaic
the way Adobe's DNG converter or any standard raw-to-sRGB renderer does.

For the codec-decoded path, we replace the DNG's raw_image array with our
decoded bayer (upsampled 2x to match if it's decimated). This gives an
apples-to-apples comparison: same processing pipeline, different sensor data.
"""
import sys
import array
import numpy as np
import rawpy
from PIL import Image

def upsample_bayer_2x(bayer_bytes, sw, sh, tw, th):
    """Bayer-aware 2x upsample: replicate each 2x2 Bayer cell into 4 copies
    (4x4 in the output), preserving RGGB layout. Visualization-only — quality
    of the upsample doesn't reflect the codec, just lets us reuse the source
    DNG's metadata in the rawpy pipeline."""
    if sw * 2 != tw or sh * 2 != th:
        raise ValueError(f"dims mismatch: {sw}x{sh} -> {tw}x{th}")
    arr = np.frombuffer(bayer_bytes, dtype=np.uint16).reshape(sh, sw)
    sh2, sw2 = sh // 2, sw // 2
    # Reshape into 2x2 Bayer cells: (sh2, sw2, 2, 2)
    cells = arr.reshape(sh2, 2, sw2, 2).transpose(0, 2, 1, 3)
    # Tile each cell 2x2 times → (sh2, sw2, 4, 4) where each 4x4 is 2x2 cell repeated
    tiled = np.tile(cells, (1, 1, 2, 2))  # (sh2, sw2, 4, 4)
    # Reshape back: (sh2, sw2, 4, 4) → (sh2*4, sw2*4)
    out = tiled.transpose(0, 2, 1, 3).reshape(th, tw)
    return out


def render_dng(dng_path, raw_replacement=None, out_path=None, label=""):
    raw = rawpy.imread(dng_path)
    if raw_replacement is not None:
        # raw.raw_image is a view into libraw's buffer. We can write to it.
        ri = raw.raw_image
        if ri.shape != raw_replacement.shape:
            raise ValueError(f"shape mismatch: {ri.shape} vs {raw_replacement.shape}")
        ri[:] = raw_replacement
    rgb = raw.postprocess(
        use_camera_wb=True,        # apply camera's white balance
        no_auto_bright=True,       # don't auto-stretch tones
        output_bps=8,              # 8-bit sRGB output
        gamma=(2.222, 4.5),        # standard Rec.709 / sRGB-ish
        output_color=rawpy.ColorSpace.sRGB,
        demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
    )
    if out_path:
        Image.fromarray(rgb).save(out_path)
        print(f"wrote {out_path}  shape={rgb.shape}  label={label}")
    raw.close()
    return rgb


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dng", required=True, help="source DNG path")
    ap.add_argument("--codec-raw", help="codec-decoded bayer LE u16 (optional)")
    ap.add_argument("--codec-w", type=int, help="codec raw width")
    ap.add_argument("--codec-h", type=int, help="codec raw height")
    ap.add_argument("--out-source", default="source.png")
    ap.add_argument("--out-codec", default="codec.png")
    args = ap.parse_args()

    # Render source DNG as-is for baseline.
    rgb_src = render_dng(args.dng, out_path=args.out_source, label="source")

    if args.codec_raw:
        # Read codec-decoded bayer
        with open(args.codec_raw, "rb") as f:
            buf = f.read()
        decoded = np.frombuffer(buf, dtype=np.uint16).reshape(args.codec_h, args.codec_w)
        print(f"loaded codec raw {args.codec_w}x{args.codec_h}")

        # Get target shape from DNG
        raw_tmp = rawpy.imread(args.dng)
        tgt_h, tgt_w = raw_tmp.raw_image.shape
        raw_tmp.close()
        print(f"target raw shape {tgt_w}x{tgt_h}")

        if (args.codec_w, args.codec_h) != (tgt_w, tgt_h):
            # Upsample Bayer-correctly
            decoded_up = upsample_bayer_2x(decoded.tobytes(), args.codec_w,
                                            args.codec_h, tgt_w, tgt_h)
        else:
            decoded_up = decoded

        rgb_codec = render_dng(args.dng, raw_replacement=decoded_up,
                                out_path=args.out_codec, label="codec")
