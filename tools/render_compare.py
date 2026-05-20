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
import cv2
from PIL import Image

def upsample_bayer_2x(bayer_bytes, sw, sh, tw, th):
    """Bayer-aware 2x upsample. Deinterleaves the source Bayer into 4 color
    planes (R, G1, G2, B) at half-resolution, bicubic-upsamples each plane
    by 2x independently, then reinterleaves into a 2x-sized Bayer pattern.

    Bicubic-per-plane avoids the cross-color smearing that a naive bicubic
    on the Bayer mosaic would produce (which would mix R into G samples
    etc.). The previous nearest-neighbor 2x tile produced visible 2-pixel
    block artifacts at native zoom; bicubic-per-plane is the right
    smooth-upsample for visualization since rawpy still wants a valid
    Bayer mosaic to demosaic.

    Visualization-only — the codec actually outputs at (sh, sw); upscaling
    to (th, tw) lets us reuse the source DNG's WB/color matrix pipeline,
    but it does NOT add detail the codec discarded."""
    if sw * 2 != tw or sh * 2 != th:
        raise ValueError(f"dims mismatch: {sw}x{sh} -> {tw}x{th}")
    arr = np.frombuffer(bayer_bytes, dtype=np.uint16).reshape(sh, sw)
    # Deinterleave into 4 planes at (sh/2, sw/2). For RGGB:
    #   plane R  = arr[0::2, 0::2]
    #   plane G1 = arr[0::2, 1::2]
    #   plane G2 = arr[1::2, 0::2]
    #   plane B  = arr[1::2, 1::2]
    planes = [
        arr[0::2, 0::2],
        arr[0::2, 1::2],
        arr[1::2, 0::2],
        arr[1::2, 1::2],
    ]
    # Bicubic-upsample each plane from (sh/2, sw/2) to (sh, sw). cv2.resize
    # takes (width, height) and is uint16-native with INTER_CUBIC.
    target_w, target_h = sw, sh   # each upsampled plane is the size of one
                                   # cell-grid in the target Bayer (tw/2, th/2),
                                   # which equals (sw, sh) since tw=2sw, th=2sh.
    up = [cv2.resize(p, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
          for p in planes]
    # Reinterleave into the target Bayer (th, tw).
    out = np.empty((th, tw), dtype=np.uint16)
    out[0::2, 0::2] = up[0]
    out[0::2, 1::2] = up[1]
    out[1::2, 0::2] = up[2]
    out[1::2, 1::2] = up[3]
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
    ap.add_argument("--codec-shift-rows", type=int, default=6,
                    help="rows to roll codec Bayer DOWN before rendering, to "
                         "align with source. 0 = off. Default 6 source rows = "
                         "3 codec-output pixels at 4K = compensates the "
                         "encoder's 'fast row-skip' top-aligned 2x2 decimation "
                         "(fused_encode.c:1153-1170). Even integers only (must "
                         "preserve Bayer parity).")
    args = ap.parse_args()
    assert args.codec_shift_rows % 2 == 0, "shift must be even to preserve Bayer parity"

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
            decoded_up = decoded.copy()

        # Encoder alignment compensation. The fused encoder's default
        # "fast row-skip" path (fused_encode.c, GPR_DECIMATE_AA=0) samples the
        # TOP row pair of each 4-row block and skips the bottom pair. That
        # produces a top-aligned 2x2 decimation rather than a centered one,
        # leaving codec output spatially offset relative to the source by
        # ~3 codec pixels at 4K dims = ~6 source-Bayer rows. Compensate by
        # rolling the upsampled Bayer DOWN by that many rows (even, to keep
        # Bayer parity intact). Set --codec-shift-rows=0 to disable.
        if args.codec_shift_rows != 0:
            decoded_up = np.roll(decoded_up, shift=args.codec_shift_rows, axis=0)
            print(f"applied codec_shift_rows = {args.codec_shift_rows} "
                  f"(compensates encoder fast-row-skip alignment)")

        rgb_codec = render_dng(args.dng, raw_replacement=decoded_up,
                                out_path=args.out_codec, label="codec")
