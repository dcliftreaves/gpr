#!/usr/bin/env python3
"""Inspect experimental stock-VC5 GVID, extract frames, or run offline 1x Bayer CNN.

This profile is deliberately distinct from the fork's fused-codec GVID v1.
CNN architecture code and trained weights are supplied explicitly by the caller.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import time

CLIP = struct.Struct("<4sHH4sIIIII4sII20s")
FRAME = struct.Struct("<4sIQQQ")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_header(f):
    data = f.read(CLIP.size)
    if len(data) != CLIP.size:
        raise ValueError("truncated clip header")
    magic, version, size, codec, w, h, num, den, q, bayer, bits, fs, reserved = CLIP.unpack(data)
    if (magic, version, size, codec, bayer, bits, fs, reserved) != (
            b"GVID", 2, 64, b"VC5\0", b"RGGB", 14, 32, bytes(20)):
        raise ValueError("unsupported GVID profile (requires experimental v2 stock VC-5)")
    if not (0 < w <= 8192 and 0 < h <= 6144 and w % 8 == h % 8 == 0
            and 0 < num <= 240 and den == 1 and 0 <= q <= 5):
        raise ValueError("invalid clip dimensions, frame rate or quality")
    return dict(width=w, height=h, fps_num=num, fps_den=den, quality=q,
                bayer="RGGB", sample_bits=bits, codec="stock_vc5", version=version)


def frames(f, header):
    index = 0
    file_end = f.seek(0, 2)
    f.seek(CLIP.size)
    while True:
        data = f.read(FRAME.size)
        if not data:
            if not index:
                raise ValueError("empty clip")
            return
        if len(data) != FRAME.size:
            raise ValueError("truncated frame header")
        magic, size, number, pts, length = FRAME.unpack(data)
        if magic != b"FRM2" or size != 32 or number != index:
            raise ValueError("invalid frame header or sequence")
        if pts != number * 1_000_000_000 // header["fps_num"]:
            raise ValueError("invalid frame timestamp")
        if not 0 < length <= header["width"] * header["height"] * 8:
            raise ValueError("invalid payload length")
        if length > file_end - f.tell():
            raise ValueError("truncated payload")
        payload = f.read(length)
        yield number, pts, payload
        index += 1


def load_cnn(root, checkpoint, device):
    import torch
    # Local caller-selected model package; no automatic weights download.
    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if "backbone_state" in ckpt:
        if ckpt.get("variant") not in ("F_ane_no_sr", "bibo_1x") or ckpt.get("raw_norm") != 16383.0:
            raise ValueError("requires a 1x BIBO checkpoint normalized by 16383")
        module_path, entry = root / "model.py", "build"
    elif "config" in ckpt and "model" in ckpt:
        module_path, entry = root / "train_bayer_rgb_target_cleanup.py", "make_model"
    else:
        raise ValueError("unsupported CNN checkpoint schema")
    spec = importlib.util.spec_from_file_location("stock_video_external_cnn", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if entry == "build":
        backbone = module.build(ckpt["variant"])
        backbone.load_state_dict(ckpt["backbone_state"], strict=True)
        scale = float(ckpt["residual_scale"])
        if not 0 < scale <= 1:
            raise ValueError("invalid checkpoint residual scale")

        class Residual(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = backbone

            def forward(self, x):
                return (x + scale * self.backbone(x)).clamp(0, 1)

        model = Residual()
    else:
        model = module.make_model(dict(ckpt["config"]))
        model.load_state_dict(ckpt["model"], strict=True)
    return model.to(device).eval(), dict(
        checkpoint_sha256=sha256(checkpoint), architecture_sha256=sha256(module_path),
        checkpoint_schema=entry, device=str(device), quality_status="unvalidated_for_stock_video")


def restore(raw, width, height, model, device, tile, halo):
    import numpy as np
    import torch
    import torch.nn.functional as functional
    image = np.fromfile(raw, dtype="<u2").reshape(height, width)
    planes = np.stack([image[0::2, 0::2], image[0::2, 1::2],
                       image[1::2, 0::2], image[1::2, 1::2]])
    out = np.empty_like(planes)
    started = time.perf_counter()
    with torch.inference_mode():
        # Nonoverlapping output cores with context halos; padding respects the
        # three-level BIBO U-Net's spatial multiple of 8. Each output written once.
        for y in range(0, height // 2, tile):
            for x in range(0, width // 2, tile):
                y1, x1 = min(y + tile, height // 2), min(x + tile, width // 2)
                ya, xa = max(0, y - halo), max(0, x - halo)
                yb, xb = min(height // 2, y1 + halo), min(width // 2, x1 + halo)
                patch = torch.from_numpy(planes[:, ya:yb, xa:xb].astype(np.float32) / 16383.0)[None].to(device)
                ph, pw = patch.shape[-2:]
                patch = functional.pad(patch, (0, (-pw) % 8, 0, (-ph) % 8), mode="replicate")
                pred = model(patch)
                if pred.shape != patch.shape or not torch.isfinite(pred).all().item():
                    raise ValueError("CNN must return finite same-size 4-plane Bayer data")
                core = pred[0, :, y-ya:y1-ya, x-xa:x1-xa].cpu().numpy()
                out[:, y:y1, x:x1] = np.clip(core * 16383.0 + .5, 0, 16383).astype("<u2")
    restored = np.empty_like(image)
    restored[0::2, 0::2], restored[0::2, 1::2] = out[0], out[1]
    restored[1::2, 0::2], restored[1::2, 1::2] = out[2], out[3]
    return restored, time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "extract", "restore"))
    parser.add_argument("clip", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--decoder", type=Path, help="stock_video executable")
    parser.add_argument("--limit", type=int, default=0, help="0 exports all; inspection always validates all")
    parser.add_argument("--cnn-root", type=Path, help="external fork tools/cnn directory")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--reference-raw", type=Path, action="append",
                        help="optional reference replay RAWs in input order, for distortion measurements")
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
    parser.add_argument("--tile", type=int, default=256, help="output core size in Bayer-plane pixels")
    parser.add_argument("--halo", type=int, default=64, help="context on each side of the output core")
    args = parser.parse_args()
    if args.limit < 0 or args.tile < 8 or args.tile % 8 or args.halo < 0 or args.halo % 8:
        parser.error("invalid frame limit, tile or halo (spatial sizes must be multiples of 8)")
    if args.action != "inspect" and args.out_dir is None:
        parser.error("--out-dir is required")
    if args.action == "restore" and not all((args.decoder, args.cnn_root, args.checkpoint)):
        parser.error("restore requires --decoder, --cnn-root and --checkpoint")
    if args.reference_raw and (not args.decoder or args.action == "inspect"):
        parser.error("reference measurements require extraction/restore with --decoder")
    model, model_info = None, None
    if args.action == "restore":
        import torch
        device = torch.device(args.device)
        model, model_info = load_cnn(args.cnn_root, args.checkpoint, device)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=False)
    with args.clip.open("rb") as f:
        header = read_header(f)
        report = dict(schema="gpr.stock_video.inspect.v1", clip_sha256=sha256(args.clip),
                      header=header, frames=[], cnn=model_info)
        for index, pts, payload in frames(f, header):
            row = dict(index=index, pts_ns=pts, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())
            if args.action != "inspect" and (not args.limit or index < args.limit):
                vc5 = args.out_dir / f"{index:06d}.vc5"
                vc5.write_bytes(payload)
                if args.decoder:
                    raw = vc5.with_suffix(".raw")
                    subprocess.run([str(args.decoder.resolve()), "--decode", str(vc5), "--output", str(raw),
                                    "--width", str(header["width"]), "--height", str(header["height"])], check=True)
                    if raw.stat().st_size != header["width"] * header["height"] * 2:
                        raise ValueError("decoded RAW size mismatch")
                    row["raw_sha256"] = sha256(raw)
                    restored = None
                    if model is not None:
                        restored, elapsed = restore(raw, header["width"], header["height"],
                                                    model, device, args.tile, args.halo)
                        path = vc5.with_suffix(".cnn.raw")
                        restored.tofile(path)
                        row.update(cnn_s=elapsed, cnn_sha256=sha256(path))
                    if args.reference_raw:
                        import numpy as np
                        ref_path = args.reference_raw[index % len(args.reference_raw)]
                        ref = np.fromfile(ref_path, dtype="<u2").reshape(header["height"], header["width"]).astype(np.float64)
                        def psnr(image):
                            mse = float(np.mean((image.astype(np.float64) - ref) ** 2))
                            return float(10 * np.log10(16383.0 ** 2 / mse)) if mse else None
                        row.update(reference_sha256=sha256(ref_path),
                                   stock_psnr_db=psnr(np.fromfile(raw, dtype="<u2").reshape(ref.shape)))
                        if restored is not None:
                            row["cnn_psnr_db"] = psnr(restored)
            report["frames"].append(row)
    report["frame_count"] = len(report["frames"])
    report["required_MBps"] = sum(row["bytes"]+32 for row in report["frames"]) / report["frame_count"] * header["fps_num"] / 1e6
    result = json.dumps(report, indent=2) + "\n"
    if args.out_dir:
        (args.out_dir / "receipt.json").write_text(result)
    print(result, end="")


if __name__ == "__main__":
    main()
