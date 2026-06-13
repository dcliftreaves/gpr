#!/usr/bin/env python3
"""Train a runtime-shaped no-REF PREVIEW RGB refiner.

Unlike train_display_rgb_direct_nonref.py, this trainer fixes source policy
before training and does not provide sample-index, crop-key, or winner-derived
conditioning. REF is the supervised target and metric reference only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lpips
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageFilter
from pytorch_msssim import ms_ssim


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from evaluate_preview_runtime_policy import build_input, build_samples, load_rgb, sha256_file, summarize, write_html  # noqa: E402
from evaluate_preview_scene_routed import route_from_sidecar  # noqa: E402
from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import build_rgb_refiner, grad_loss, pass_preview  # noqa: E402


DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
ARCHITECTURES = [
    "direct",
    "dilated_context",
    "lowfreq_spatial",
    "lowfreq_spatial_strong",
    "coord_field",
    "lowfreq_spatial_residual",
    "midfreq_spatial_residual",
    "midfreq_spatial_residual_strong",
    "midfreq_spatial_residual_xstrong",
    "context_unet",
    "context_unet_generator",
]


@dataclass(frozen=True)
class ReceiptSample:
    image_id: str
    crop: str
    ref_path: Path
    source_path: Path
    source_label: str
    cluster: int | None = None
    tile_xywh: tuple[int, int, int, int] | None = None
    source_render_size: tuple[int, int] | None = None
    source_global_stats: dict[str, float] | None = None
    context_path: Path | None = None
    intersects_crops: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssembledCropGroup:
    image_id: str
    crop: str
    sample_indices: tuple[int, ...]
    paste_xywh: tuple[tuple[int, int, int, int], ...]
    crop_xywh: tuple[int, int, int, int]
    canvas_size: tuple[int, int]


def build_receipt_samples(args: argparse.Namespace) -> list[ReceiptSample]:
    sidecar = json.loads(args.router_sidecar.read_text()) if args.router_sidecar else None
    wanted_clusters = {int(c) for c in args.include_cluster}
    wanted_intersects = {str(c) for c in args.include_intersect_crop}
    out: list[ReceiptSample] = []
    for receipt_path in args.sample_receipt or []:
        receipt = json.loads(receipt_path.read_text())
        for row in receipt.get("rows") or []:
            if args.image_id and str(row.get("image_id")) not in set(args.image_id):
                continue
            intersects_crops = tuple(str(v) for v in row.get("intersects_crops", []))
            if wanted_intersects and not wanted_intersects.intersection(intersects_crops):
                continue
            source_path = Path(str(row.get("source_png_resolved") or row.get("source_png") or ""))
            ref_path = Path(str(row.get("ref_png") or ""))
            context_path = Path(str(row.get("context_png") or "")) if row.get("context_png") else None
            if not source_path.exists() or not ref_path.exists():
                continue
            if context_path is not None and not context_path.exists():
                context_path = None
            cluster = int(row["cluster"]) if row.get("cluster") is not None else None
            if sidecar is not None:
                cluster, _route = route_from_sidecar(source_path, sidecar)
            if wanted_clusters and cluster not in wanted_clusters:
                continue
            tile_xywh = tuple(int(v) for v in row["tile_xywh"]) if row.get("tile_xywh") else None
            source_render_size = tuple(int(v) for v in row["source_render_size"]) if row.get("source_render_size") else None
            if tile_xywh is None and isinstance(row.get("source_render"), dict):
                crop_box = row["source_render"].get("crop_box_render")
                if crop_box:
                    x0, y0, x1, y1 = [int(v) for v in crop_box]
                    tile_xywh = (x0, y0, x1 - x0, y1 - y0)
            if source_render_size is None and isinstance(row.get("source_render"), dict):
                render_size = row["source_render"].get("render_size")
                if render_size:
                    source_render_size = tuple(int(v) for v in render_size)
            out.append(
                ReceiptSample(
                    image_id=str(row["image_id"]),
                    crop=str(row["crop"]),
                    ref_path=ref_path,
                    source_path=source_path,
                    source_label=str(row.get("source_label", "receipt:source")),
                    cluster=cluster,
                    tile_xywh=tile_xywh,
                    source_render_size=source_render_size,
                    source_global_stats={k: float(v) for k, v in row["source_global_stats"].items()} if row.get("source_global_stats") else None,
                    context_path=context_path,
                    intersects_crops=intersects_crops,
                )
            )
    if not out:
        raise RuntimeError("sample receipts produced no training samples")
    return out


def scaled_box(crop: dict[str, int], sensor_dims: list[int], render_size: tuple[int, int]) -> tuple[int, int, int, int]:
    sensor_w, sensor_h = int(sensor_dims[0]), int(sensor_dims[1])
    render_w, render_h = int(render_size[0]), int(render_size[1])
    x0 = int(round(int(crop["x"]) * render_w / sensor_w))
    y0 = int(round(int(crop["y"]) * render_h / sensor_h))
    x1 = int(round((int(crop["x"]) + int(crop["w"])) * render_w / sensor_w))
    y1 = int(round((int(crop["y"]) + int(crop["h"])) * render_h / sensor_h))
    x0 = min(max(0, x0), render_w - 1)
    y0 = min(max(0, y0), render_h - 1)
    x1 = min(max(x0 + 1, x1), render_w)
    y1 = min(max(y0 + 1, y1), render_h)
    return x0, y0, x1, y1


def build_assembled_crop_groups(samples: list[Any], args: argparse.Namespace) -> list[AssembledCropGroup]:
    if args.assembled_crop_weight <= 0.0 or args.assembled_manifest is None:
        return []
    manifest = json.loads(args.assembled_manifest.read_text())
    images = {str(image["id"]): image for image in manifest.get("images", [])}
    crops = {
        str(name): crop
        for name, crop in manifest.get("crops", {}).items()
        if not str(name).startswith("$")
    }
    focus = set(args.assembled_focus_crop)
    groups: list[AssembledCropGroup] = []
    for image_id, image in images.items():
        image_indices = [idx for idx, sample in enumerate(samples) if sample.image_id == image_id]
        if not image_indices:
            continue
        render_size = samples[image_indices[0]].source_render_size
        if render_size is None:
            continue
        for crop_name, crop in crops.items():
            if focus and crop_name not in focus:
                continue
            selected = [
                idx
                for idx in image_indices
                if crop_name in getattr(samples[idx], "intersects_crops", ())
                and getattr(samples[idx], "tile_xywh", None) is not None
            ]
            if not selected:
                continue
            boxes = [samples[idx].tile_xywh for idx in selected]
            if any(box is None for box in boxes):
                continue
            boxes_i = [(int(x), int(y), int(w), int(h)) for x, y, w, h in boxes if x is not None]
            min_x = min(x for x, _y, _w, _h in boxes_i)
            min_y = min(y for _x, y, _w, _h in boxes_i)
            max_x = max(x + w for x, _y, w, _h in boxes_i)
            max_y = max(y + h for _x, y, _w, h in boxes_i)
            crop_box = scaled_box(crop, image["sensor_dims"], render_size)
            if not (min_x <= crop_box[0] < crop_box[2] <= max_x and min_y <= crop_box[1] < crop_box[3] <= max_y):
                continue
            groups.append(
                AssembledCropGroup(
                    image_id=image_id,
                    crop=crop_name,
                    sample_indices=tuple(selected),
                    paste_xywh=tuple((x - min_x, y - min_y, w, h) for x, y, w, h in boxes_i),
                    crop_xywh=(crop_box[0] - min_x, crop_box[1] - min_y, crop_box[2] - crop_box[0], crop_box[3] - crop_box[1]),
                    canvas_size=(max_x - min_x, max_y - min_y),
                )
            )
    return groups


def source_frequency_planes(source_rgb: np.ndarray, mode: str, blur_radius: float) -> list[np.ndarray]:
    if mode == "none":
        return []
    if mode != "low_high":
        raise ValueError(f"unsupported source frequency plane mode {mode!r}")
    source = source_rgb.astype(np.float32) / 255.0
    low_rgb = np.asarray(
        Image.fromarray(source_rgb).filter(ImageFilter.GaussianBlur(radius=float(blur_radius))),
        dtype=np.float32,
    ) / 255.0
    high_rgb = source - low_rgb
    return [
        np.transpose(low_rgb, (2, 0, 1)).astype(np.float32),
        np.transpose(high_rgb, (2, 0, 1)).astype(np.float32),
    ]


def build_input_for_sample(
    source_rgb: np.ndarray,
    conditioning: str,
    coordinate_mode: str,
    sample: ReceiptSample,
    source_frequency_mode: str = "none",
    source_frequency_blur: float = 2.0,
) -> torch.Tensor:
    if coordinate_mode == "local" and conditioning != "global_color_stats" and source_frequency_mode == "none":
        return build_input(source_rgb, conditioning)
    if coordinate_mode not in {"global_tile", "zero_coord"}:
        if coordinate_mode != "local" or conditioning != "global_color_stats":
            raise ValueError(f"unsupported coordinate mode {coordinate_mode!r}")
    height, width = source_rgb.shape[:2]
    if sample.tile_xywh is None or sample.source_render_size is None or coordinate_mode == "local":
        yy, xx = np.meshgrid(
            np.linspace(0, 1, height, dtype=np.float32),
            np.linspace(0, 1, width, dtype=np.float32),
            indexing="ij",
        )
    elif coordinate_mode == "zero_coord":
        yy = np.zeros((height, width), dtype=np.float32)
        xx = np.zeros((height, width), dtype=np.float32)
    else:
        x0, y0, _tile_w, _tile_h = sample.tile_xywh
        full_w, full_h = sample.source_render_size
        yy, xx = np.meshgrid(
            (np.arange(height, dtype=np.float32) + float(y0)) / max(1.0, float(full_h - 1)),
            (np.arange(width, dtype=np.float32) + float(x0)) / max(1.0, float(full_w - 1)),
            indexing="ij",
        )
    source = np.transpose(source_rgb.astype(np.float32) / 255.0, (2, 0, 1))
    key_planes = np.zeros((4, height, width), dtype=np.float32)
    if conditioning == "zero":
        pass
    elif conditioning == "content_stats":
        gray = source.mean(axis=0)
        key_planes[0].fill(float(gray.mean()))
        key_planes[1].fill(float(gray.std()))
        key_planes[2].fill(float(np.percentile(gray, 95) - np.percentile(gray, 5)))
    elif conditioning == "color_stats":
        gray = source.mean(axis=0)
        key_planes[0].fill(float(source[0].mean()))
        key_planes[1].fill(float(source[1].mean()))
        key_planes[2].fill(float(source[2].mean()))
        key_planes[3].fill(float(gray.std()))
    elif conditioning == "global_color_stats":
        stats = sample.source_global_stats
        if stats is None:
            gray = source.mean(axis=0)
            stats = {
                "r_mean": float(source[0].mean()),
                "g_mean": float(source[1].mean()),
                "b_mean": float(source[2].mean()),
                "gray_std": float(gray.std()),
            }
        key_planes[0].fill(float(stats["r_mean"]))
        key_planes[1].fill(float(stats["g_mean"]))
        key_planes[2].fill(float(stats["b_mean"]))
        key_planes[3].fill(float(stats["gray_std"]))
    else:
        raise ValueError(f"unsupported conditioning {conditioning!r}")
    planes = [source, np.stack([xx, yy], axis=0), key_planes]
    planes.extend(source_frequency_planes(source_rgb, source_frequency_mode, source_frequency_blur))
    if getattr(sample, "context_path", None) is not None:
        context = load_rgb(sample.context_path)
        if context.shape[:2] != source_rgb.shape[:2]:
            context = np.asarray(
                Image.fromarray(context).resize((source_rgb.shape[1], source_rgb.shape[0]), Image.Resampling.BILINEAR),
                dtype=np.uint8,
            )
        planes.append(np.transpose(context.astype(np.float32) / 255.0, (2, 0, 1)))
    arr = np.concatenate(planes, axis=0)
    return torch.from_numpy(arr[None].copy()).to(DEVICE).contiguous()


def build_tensors(args: argparse.Namespace) -> tuple[list[Any], torch.Tensor, torch.Tensor]:
    samples = build_receipt_samples(args) if args.sample_receipt else build_samples(args)
    if args.cluster_audit is not None:
        audit = json.loads(args.cluster_audit.read_text())
        wanted_clusters = {int(c) for c in args.include_cluster}
        wanted_rows = {
            (row["image_id"], row["crop"])
            for row in audit.get("rows", [])
            if int(row.get("cluster", -1)) in wanted_clusters
        }
        samples = [s for s in samples if (s.image_id, s.crop) in wanted_rows]
        if not samples:
            raise RuntimeError(f"cluster filter {sorted(wanted_clusters)} produced no samples")
    xs: list[torch.Tensor] = []
    ys: list[np.ndarray] = []
    for sample in samples:
        source = load_rgb(sample.source_path)
        ref = load_rgb(sample.ref_path)
        xs.append(
            build_input_for_sample(
                source,
                args.conditioning,
                args.coordinate_mode,
                sample,
                args.source_frequency_planes,
                args.source_frequency_blur,
            ).cpu()[0]
        )
        ys.append(np.transpose(ref.astype(np.float32) / 255.0, (2, 0, 1)))
    return samples, torch.stack(xs).contiguous(), torch.from_numpy(np.stack(ys).copy()).contiguous()


def charbonnier(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    diff = (pred - target).contiguous()
    return torch.sqrt(diff * diff + 1e-6).mean()


def center_crop_tensor(x: torch.Tensor, size: int) -> torch.Tensor:
    if size <= 0:
        return x
    height, width = x.shape[-2:]
    if size > height or size > width:
        raise ValueError(f"center crop {size} exceeds tensor shape {tuple(x.shape)}")
    y0 = (height - size) // 2
    x0 = (width - size) // 2
    return x[..., y0:y0 + size, x0:x0 + size].contiguous()


def center_crop_array(x: np.ndarray, size: int) -> np.ndarray:
    if size <= 0:
        return x
    height, width = x.shape[:2]
    if size > height or size > width:
        raise ValueError(f"center crop {size} exceeds array shape {x.shape}")
    y0 = (height - size) // 2
    x0 = (width - size) // 2
    return x[y0:y0 + size, x0:x0 + size].copy()


def lowfreq_color_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    pred_mean = pred.mean(dim=(2, 3))
    target_mean = target.mean(dim=(2, 3))
    pred_std = pred.std(dim=(2, 3), unbiased=False)
    target_std = target.std(dim=(2, 3), unbiased=False)
    pooled_pred = F.interpolate(pred, size=(64, 64), mode="area")
    pooled_target = F.interpolate(target, size=(64, 64), mode="area")
    return (
        (pred_mean - target_mean).abs().mean()
        + 0.5 * (pred_std - target_std).abs().mean()
        + (pooled_pred - pooled_target).abs().mean()
    )


def gate_luma_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    weights = pred.new_tensor([0.2126, 0.7152, 0.0722]).view(1, 3, 1, 1)
    pred_y = (pred * weights).sum(dim=1, keepdim=True)
    target_y = (target * weights).sum(dim=1, keepdim=True)
    return (
        charbonnier(pred_y, target_y)
        + charbonnier(
            F.interpolate(pred_y, size=(64, 64), mode="area"),
            F.interpolate(target_y, size=(64, 64), mode="area"),
        )
    )


def opponent_color_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    pred_rg = pred[:, 0:1] - pred[:, 1:2]
    pred_by = pred[:, 2:3] - 0.5 * (pred[:, 0:1] + pred[:, 1:2])
    target_rg = target[:, 0:1] - target[:, 1:2]
    target_by = target[:, 2:3] - 0.5 * (target[:, 0:1] + target[:, 1:2])
    pred_opp = torch.cat([pred_rg, pred_by], dim=1)
    target_opp = torch.cat([target_rg, target_by], dim=1)
    return (
        charbonnier(pred_opp, target_opp)
        + charbonnier(
            F.interpolate(pred_opp, size=(64, 64), mode="area"),
            F.interpolate(target_opp, size=(64, 64), mode="area"),
        )
    )


def rgb_to_lab(rgb: torch.Tensor) -> torch.Tensor:
    rgb = torch.clamp(rgb, 0.0, 1.0)
    linear = torch.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055).pow(2.4))
    r, g, b = linear[:, 0:1], linear[:, 1:2], linear[:, 2:3]
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883
    xyz = torch.cat([x, y, z], dim=1)
    eps = 0.008856
    f = torch.where(xyz > eps, torch.clamp(xyz, min=1e-8).pow(1.0 / 3.0), xyz / 0.12841854934601665 + 0.14081893333333334)
    fx, fy, fz = f[:, 0:1], f[:, 1:2], f[:, 2:3]
    l = (116.0 * fy - 16.0) / 100.0
    a = (500.0 * (fx - fy)) / 100.0
    b_lab = (200.0 * (fy - fz)) / 100.0
    return torch.cat([l, a, b_lab], dim=1)


def lab_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    pred_lab = rgb_to_lab(pred)
    target_lab = rgb_to_lab(target)
    return (
        charbonnier(pred_lab, target_lab)
        + charbonnier(
            F.interpolate(pred_lab, size=(64, 64), mode="area"),
            F.interpolate(target_lab, size=(64, 64), mode="area"),
        )
    )


def gaussian_kernel1d(sigma: float, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
    sigma = max(0.25, float(sigma))
    radius = max(1, int(round(3.0 * sigma)))
    x = torch.arange(-radius, radius + 1, device=device, dtype=dtype)
    kernel = torch.exp(-(x * x) / (2.0 * sigma * sigma))
    return kernel / kernel.sum()


def gaussian_blur(rgb: torch.Tensor, sigma: float) -> torch.Tensor:
    if sigma <= 0.0:
        return rgb
    kernel = gaussian_kernel1d(sigma, rgb.device, rgb.dtype)
    channels = int(rgb.shape[1])
    pad = int(kernel.numel() // 2)
    ky = kernel.view(1, 1, -1, 1).repeat(channels, 1, 1, 1)
    kx = kernel.view(1, 1, 1, -1).repeat(channels, 1, 1, 1)
    blurred = F.conv2d(F.pad(rgb, (0, 0, pad, pad), mode="reflect"), ky, groups=channels)
    blurred = F.conv2d(F.pad(blurred, (pad, pad, 0, 0), mode="reflect"), kx, groups=channels)
    return blurred


def midfreq_residual_loss(pred: torch.Tensor, target: torch.Tensor, source: torch.Tensor, sigma: float) -> torch.Tensor:
    pred_residual = pred - source
    target_residual = target - source
    return charbonnier(gaussian_blur(pred_residual, sigma), gaussian_blur(target_residual, sigma))


def source_preservation_loss(pred: torch.Tensor, source: torch.Tensor) -> torch.Tensor:
    return charbonnier(pred, source)


def source_lowfreq_preservation_loss(pred: torch.Tensor, source: torch.Tensor, sigma: float) -> torch.Tensor:
    return charbonnier(gaussian_blur(pred, sigma), gaussian_blur(source, sigma))


def sample_weight(sample: ReceiptSample, args: argparse.Namespace) -> float:
    weight = 1.0
    for crop in args.focus_intersect_crop:
        if crop in sample.intersects_crops:
            weight *= args.focus_weight
    for pattern in args.focus_crop:
        if pattern in sample.crop:
            weight *= args.focus_weight
    return float(weight)


def load_initial_state(model: torch.nn.Module, checkpoint: Path) -> str:
    init = torch.load(str(checkpoint), map_location="cpu", weights_only=False)
    state = init["state_dict"]
    try:
        model.load_state_dict(state)
        return "full"
    except RuntimeError:
        pass
    local = getattr(model, "local", None)
    base = getattr(model, "base", None)
    if base is not None:
        try:
            base.load_state_dict(state)
            return "base_full_state"
        except RuntimeError:
            pass
    if local is None:
        raise RuntimeError(f"cannot initialize {type(model).__name__} from {checkpoint}")
    try:
        local.load_state_dict(state)
        return "local_full_state"
    except RuntimeError:
        local_state = {
            key.removeprefix("local."): value
            for key, value in state.items()
            if key.startswith("local.")
        }
        if not local_state:
            raise
        local.load_state_dict(local_state)
        return "local_prefixed_state"


def assemble_group_crop(pred_tiles: torch.Tensor, target_tiles: torch.Tensor, group: AssembledCropGroup) -> tuple[torch.Tensor, torch.Tensor]:
    canvas_w, canvas_h = group.canvas_size
    pred_canvas = pred_tiles.new_zeros((3, canvas_h, canvas_w))
    target_canvas = target_tiles.new_zeros((3, canvas_h, canvas_w))
    for row, (x0, y0, width, height) in enumerate(group.paste_xywh):
        pred_canvas[:, y0:y0 + height, x0:x0 + width] = pred_tiles[row, :, :height, :width]
        target_canvas[:, y0:y0 + height, x0:x0 + width] = target_tiles[row, :, :height, :width]
    cx, cy, cw, ch = group.crop_xywh
    pred_crop = pred_canvas[:, cy:cy + ch, cx:cx + cw].unsqueeze(0)
    target_crop = target_canvas[:, cy:cy + ch, cx:cx + cw].unsqueeze(0)
    if pred_crop.shape[-2:] != (512, 512):
        pred_crop = F.interpolate(pred_crop, size=(512, 512), mode="bilinear", align_corners=False)
        target_crop = F.interpolate(target_crop, size=(512, 512), mode="bilinear", align_corners=False)
    return pred_crop.contiguous(), target_crop.contiguous()


def assembled_crop_loss(
    *,
    model: torch.nn.Module,
    xt: torch.Tensor,
    yt: torch.Tensor,
    groups: list[AssembledCropGroup],
    args: argparse.Namespace,
    lpips_net: torch.nn.Module | None,
    step: int,
) -> tuple[torch.Tensor, dict[str, float]]:
    if not groups or args.assembled_crop_weight <= 0.0:
        zero = xt.new_tensor(0.0)
        return zero, {"assembled": 0.0, "assembled_luma": 0.0, "assembled_lab": 0.0, "assembled_midfreq": 0.0}
    count = min(max(1, int(args.assembled_crop_count)), len(groups))
    if count >= len(groups):
        selected = groups
    else:
        start = (step - 1) % len(groups)
        selected = [groups[(start + offset) % len(groups)] for offset in range(count)]
    losses = []
    luma_values = []
    lab_values = []
    mid_values = []
    for group in selected:
        idx = torch.tensor(group.sample_indices, dtype=torch.long, device=xt.device)
        input_tiles = xt.index_select(0, idx)
        pred_tiles = model(input_tiles).contiguous()
        target_tiles = yt.index_select(0, idx).contiguous()
        source_tiles = input_tiles[:, :3].contiguous()
        pred_crop, target_crop = assemble_group_crop(pred_tiles, target_tiles, group)
        source_crop, _source_target = assemble_group_crop(source_tiles, target_tiles, group)
        l1 = charbonnier(pred_crop, target_crop)
        lms = 1.0 - ms_ssim(pred_crop, target_crop, data_range=1.0, win_size=7) if args.assembled_ms_weight > 0.0 else pred_crop.new_tensor(0.0)
        llp = lpips_net(pred_crop * 2 - 1, target_crop * 2 - 1).mean() if lpips_net is not None and args.assembled_lpips_weight > 0.0 else pred_crop.new_tensor(0.0)
        ly = gate_luma_loss(pred_crop, target_crop)
        llab = lab_loss(pred_crop, target_crop)
        lmid = midfreq_residual_loss(pred_crop, target_crop, source_crop, args.assembled_midfreq_blur_sigma)
        loss = (
            l1
            + args.assembled_ms_weight * lms
            + args.assembled_lpips_weight * llp
            + args.assembled_y_weight * ly
            + args.assembled_lab_weight * llab
            + args.assembled_midfreq_weight * lmid
        )
        losses.append(loss)
        luma_values.append(float(ly.detach().cpu()))
        lab_values.append(float(llab.detach().cpu()))
        mid_values.append(float(lmid.detach().cpu()))
    merged = torch.stack(losses).mean()
    return args.assembled_crop_weight * merged, {
        "assembled": float(merged.detach().cpu()),
        "assembled_luma": float(sum(luma_values) / len(luma_values)),
        "assembled_lab": float(sum(lab_values) / len(lab_values)),
        "assembled_midfreq": float(sum(mid_values) / len(mid_values)),
    }


def eval_score(
    *,
    model: torch.nn.Module,
    xb: torch.Tensor,
    yb: torch.Tensor,
    xt: torch.Tensor,
    yt: torch.Tensor,
    assembled_groups: list[AssembledCropGroup],
    args: argparse.Namespace,
    lpips_net: torch.nn.Module | None,
    step: int,
) -> tuple[float, dict[str, float]]:
    with torch.no_grad():
        pred_eval = model(xb).contiguous()
        score_center_size = args.metric_center_size or args.loss_center_size
        pred_metric = center_crop_tensor(pred_eval, score_center_size)
        yb_metric = center_crop_tensor(yb, score_center_size)
        xb_metric = center_crop_tensor(xb, score_center_size)
        l1_eval = (pred_metric - yb_metric).abs().mean().item()
        ms_eval = ms_ssim(pred_metric, yb_metric, data_range=1.0, win_size=7).item() if args.ms_weight > 0.0 else 0.0
        lp_eval = lpips_net(pred_metric * 2 - 1, yb_metric * 2 - 1).mean().item() if lpips_net is not None else 0.0
        y_eval = gate_luma_loss(pred_metric, yb_metric).item()
        opp_eval = opponent_color_loss(pred_metric, yb_metric).item()
        lab_eval = lab_loss(pred_metric, yb_metric).item()
        mid_eval = midfreq_residual_loss(pred_metric, yb_metric, xb_metric[:, :3], args.midfreq_blur_sigma).item()
        _asm_eval_loss, asm_eval_stats = assembled_crop_loss(
            model=model,
            xt=xt,
            yt=yt,
            groups=assembled_groups,
            args=args,
            lpips_net=lpips_net,
            step=step,
        )
    score = (
        l1_eval
        + 0.1 * (1.0 - ms_eval)
        + 0.2 * lp_eval
        + args.score_y_weight * y_eval
        + args.score_opponent_weight * opp_eval
        + args.score_lab_weight * lab_eval
        + args.score_midfreq_weight * mid_eval
        + args.score_assembled_weight * asm_eval_stats["assembled"]
    )
    return score, {
        "l1": l1_eval,
        "ms": ms_eval,
        "lp": lp_eval,
        "y": y_eval,
        "opp": opp_eval,
        "lab": lab_eval,
        "midfreq": mid_eval,
        **asm_eval_stats,
    }


def train(args: argparse.Namespace) -> dict[str, Any]:
    samples, x, y = build_tensors(args)
    assembled_groups = build_assembled_crop_groups(samples, args)
    if args.assembled_crop_weight > 0.0 and not assembled_groups:
        raise RuntimeError("assembled crop loss was requested, but no assembled crop groups were built")
    xt = x.to(DEVICE).contiguous()
    yt = y.to(DEVICE).contiguous()
    sample_count = int(xt.shape[0])
    in_channels = int(xt.shape[1])
    model = build_rgb_refiner(
        args.architecture,
        width=args.width,
        in_channels=in_channels,
        residual_scale=args.residual_scale,
    ).to(DEVICE)
    init_load_mode = None
    if args.init_checkpoint is not None:
        init_load_mode = load_initial_state(model, args.init_checkpoint)
    if args.freeze_base:
        base = getattr(model, "base", None)
        if base is None:
            raise RuntimeError("--freeze-base requires a model with a base submodule")
        for param in base.parameters():
            param.requires_grad_(False)
    trainable_params = [param for param in model.parameters() if param.requires_grad]
    if not trainable_params:
        raise RuntimeError("no trainable parameters remain")
    opt = torch.optim.AdamW(trainable_params, lr=args.lr, weight_decay=args.weight_decay)
    needs_lpips = args.lpips_weight > 0.0 or (args.assembled_crop_weight > 0.0 and args.assembled_lpips_weight > 0.0)
    lpips_net = lpips.LPIPS(net="alex").to(DEVICE).eval() if needs_lpips else None
    if lpips_net is not None:
        for param in lpips_net.parameters():
            param.requires_grad_(False)
    sample_weights = torch.tensor([sample_weight(sample, args) for sample in samples], dtype=torch.float32, device=DEVICE)
    weighted_sampling = bool(args.focus_intersect_crop or args.focus_crop)

    if sample_count <= int(args.initial_score_max_samples):
        best, initial_stats = eval_score(
            model=model,
            xb=xt,
            yb=yt,
            xt=xt,
            yt=yt,
            assembled_groups=assembled_groups,
            args=args,
            lpips_net=lpips_net,
            step=0,
        )
        best_state: dict[str, torch.Tensor] | None = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        print(
            f"initial score={best:.6f} l1={initial_stats['l1']:.5f} ms={initial_stats['ms']:.5f} "
            f"lp={initial_stats['lp']:.4f} y={initial_stats['y']:.5f} "
            f"asm={initial_stats['assembled']:.5f} asm_y={initial_stats['assembled_luma']:.5f} "
            f"asm_mid={initial_stats['assembled_midfreq']:.5f}",
            flush=True,
        )
    else:
        best = float("inf")
        best_state = None
    t0 = time.time()
    for step in range(1, args.steps + 1):
        if args.batch_size and args.batch_size < sample_count:
            if weighted_sampling:
                idx = torch.multinomial(sample_weights, args.batch_size, replacement=True)
            else:
                idx = torch.randint(0, sample_count, (args.batch_size,), device=DEVICE)
            xb = xt.index_select(0, idx)
            yb = yt.index_select(0, idx)
        else:
            xb = xt
            yb = yt
        pred = model(xb).contiguous()
        pred_loss = center_crop_tensor(pred, args.loss_center_size)
        yb_loss = center_crop_tensor(yb, args.loss_center_size)
        xb_loss = center_crop_tensor(xb, args.loss_center_size)
        l1 = charbonnier(pred_loss, yb_loss)
        lms = 1.0 - ms_ssim(pred_loss, yb_loss, data_range=1.0, win_size=7) if args.ms_weight > 0.0 else pred.new_tensor(0.0)
        lg = grad_loss(pred_loss, yb_loss)
        llp = lpips_net(pred * 2 - 1, yb * 2 - 1).mean() if lpips_net is not None else pred.new_tensor(0.0)
        if lpips_net is not None and args.loss_center_size > 0:
            llp = lpips_net(pred_loss * 2 - 1, yb_loss * 2 - 1).mean()
        lcolor = lowfreq_color_loss(pred_loss, yb_loss)
        ly = gate_luma_loss(pred_loss, yb_loss)
        lopp = opponent_color_loss(pred_loss, yb_loss)
        llab = lab_loss(pred_loss, yb_loss)
        lmid = midfreq_residual_loss(pred_loss, yb_loss, xb_loss[:, :3], args.midfreq_blur_sigma)
        lsource = source_preservation_loss(pred_loss, xb_loss[:, :3])
        lsource_lf = source_lowfreq_preservation_loss(pred_loss, xb_loss[:, :3], args.source_lowfreq_blur_sigma)
        loss = (
            l1
            + args.grad_weight * lg
            + args.ms_weight * lms
            + args.lpips_weight * llp
            + args.color_weight * lcolor
            + args.y_weight * ly
            + args.opponent_weight * lopp
            + args.lab_weight * llab
            + args.midfreq_weight * lmid
            + args.source_weight * lsource
            + args.source_lowfreq_weight * lsource_lf
        )
        lasm, asm_stats = assembled_crop_loss(
            model=model,
            xt=xt,
            yt=yt,
            groups=assembled_groups,
            args=args,
            lpips_net=lpips_net,
            step=step,
        )
        loss = loss + lasm
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step == 1 or step % args.log_every == 0 or step == args.steps:
            score, stats = eval_score(
                model=model,
                xb=xb,
                yb=yb,
                xt=xt,
                yt=yt,
                assembled_groups=assembled_groups,
                args=args,
                lpips_net=lpips_net,
                step=step,
            )
            if score < best:
                best = score
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            print(
                f"step {step}/{args.steps} loss={loss.item():.6f} "
                f"l1={stats['l1']:.5f} ms={stats['ms']:.5f} lp={stats['lp']:.4f} "
                f"color={lcolor.item():.5f} y={stats['y']:.5f} opp={stats['opp']:.5f} lab={stats['lab']:.5f} "
                f"mid={stats['midfreq']:.5f} "
                f"src={lsource.item():.5f} src_lf={lsource_lf.item():.5f} "
                f"asm={stats['assembled']:.5f} asm_y={stats['assembled_luma']:.5f} asm_mid={stats['assembled_midfreq']:.5f} "
                f"best={best:.6f} t={time.time() - t0:.1f}s",
                flush=True,
            )
    if best_state is None:
        raise RuntimeError("training did not produce a checkpoint")

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "kind": "preview_runtime_refiner",
            "architecture": args.architecture,
            "state_dict": best_state,
            "width": args.width,
            "in_channels": in_channels,
            "residual_scale": args.residual_scale,
            "init_checkpoint": str(args.init_checkpoint) if args.init_checkpoint else None,
            "init_load_mode": init_load_mode,
            "freeze_base": args.freeze_base,
            "initial_score_max_samples": args.initial_score_max_samples,
            "steps": args.steps,
            "batch_size": args.batch_size,
            "best_score": best,
            "source_policy": args.policy,
            "conditioning": args.conditioning,
            "coordinate_mode": args.coordinate_mode,
            "color_weight": args.color_weight,
            "y_weight": args.y_weight,
            "opponent_weight": args.opponent_weight,
            "lab_weight": args.lab_weight,
            "midfreq_weight": args.midfreq_weight,
            "midfreq_blur_sigma": args.midfreq_blur_sigma,
            "source_weight": args.source_weight,
            "source_lowfreq_weight": args.source_lowfreq_weight,
            "source_lowfreq_blur_sigma": args.source_lowfreq_blur_sigma,
            "source_frequency_planes": args.source_frequency_planes,
            "source_frequency_blur": args.source_frequency_blur,
            "score_y_weight": args.score_y_weight,
            "score_opponent_weight": args.score_opponent_weight,
            "score_lab_weight": args.score_lab_weight,
            "score_midfreq_weight": args.score_midfreq_weight,
            "score_assembled_weight": args.score_assembled_weight,
            "focus_intersect_crop": args.focus_intersect_crop,
            "focus_crop": args.focus_crop,
            "focus_weight": args.focus_weight,
            "loss_center_size": args.loss_center_size,
            "metric_center_size": args.metric_center_size,
            "assembled_crop_weight": args.assembled_crop_weight,
            "assembled_manifest": str(args.assembled_manifest) if args.assembled_manifest else None,
            "assembled_focus_crop": args.assembled_focus_crop,
            "assembled_crop_count": args.assembled_crop_count,
            "assembled_ms_weight": args.assembled_ms_weight,
            "assembled_lpips_weight": args.assembled_lpips_weight,
            "assembled_y_weight": args.assembled_y_weight,
            "assembled_lab_weight": args.assembled_lab_weight,
            "assembled_midfreq_weight": args.assembled_midfreq_weight,
            "assembled_midfreq_blur_sigma": args.assembled_midfreq_blur_sigma,
            "assembled_groups": [
                {
                    "image_id": group.image_id,
                    "crop": group.crop,
                    "sample_indices": list(group.sample_indices),
                    "canvas_size": list(group.canvas_size),
                    "crop_xywh": list(group.crop_xywh),
                }
                for group in assembled_groups
            ],
            "forbidden_inputs": ["winner JSON", "sample index", "crop identity key planes"],
            "render_input_features": {
                "source_frequency_planes": args.source_frequency_planes,
                "source_frequency_blur": args.source_frequency_blur,
            },
            "samples": [
                {
                    "image_id": s.image_id,
                    "crop": s.crop,
                    "source_label": s.source_label,
                    "cluster": getattr(s, "cluster", None),
                    "has_context_rgb": getattr(s, "context_path", None) is not None,
                    "intersects_crops": list(getattr(s, "intersects_crops", ())),
                    "sample_weight": sample_weight(s, args),
                }
                for s in samples
            ],
        },
        args.checkpoint,
    )
    return {
        "checkpoint": str(args.checkpoint),
        "checkpoint_sha256": sha256_file(args.checkpoint),
        "best_score": best,
        "samples": samples,
    }


def evaluate(args: argparse.Namespace, training: dict[str, Any]) -> dict[str, Any]:
    ckpt = torch.load(str(args.checkpoint), map_location="cpu", weights_only=False)
    model = build_rgb_refiner(
        str(ckpt.get("architecture", "direct")),
        width=int(ckpt.get("width", args.width)),
        in_channels=int(ckpt.get("in_channels", 9)),
        residual_scale=float(ckpt.get("residual_scale", 0.5)),
    ).to(DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    samples = training.get("samples")
    if not samples:
        samples = build_receipt_samples(args) if args.sample_receipt else build_samples(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    frequency_mode = str(ckpt.get("source_frequency_planes", args.source_frequency_planes))
    frequency_blur = float(ckpt.get("source_frequency_blur", args.source_frequency_blur))
    with torch.no_grad():
        for sample in samples:
            source = load_rgb(sample.source_path)
            ref = load_rgb(sample.ref_path)
            pred = model(
                build_input_for_sample(
                    source,
                    args.conditioning,
                    args.coordinate_mode,
                    sample,
                    frequency_mode,
                    frequency_blur,
                )
            ).detach().cpu().numpy()[0]
            rgb = np.clip(np.transpose(pred, (1, 2, 0)) * 255, 0, 255).astype(np.uint8)
            metric_rgb = center_crop_array(rgb, args.metric_center_size)
            metric_ref = center_crop_array(ref, args.metric_center_size)
            png = args.output_dir / f"{sample.image_id}_{sample.crop}_{args.policy}_{args.conditioning}_runtime_refiner.png"
            Image.fromarray(metric_rgb if args.metric_center_size > 0 else rgb).save(png)
            metrics = compute_visual_metrics(metric_ref, metric_rgb)
            metrics["preview_pass"] = pass_preview(metrics)
            rows.append({
                "image_id": sample.image_id,
                "crop": sample.crop,
                "source_label": sample.source_label,
                "png": png.name,
                **metrics,
            })
            print(
                f"EVAL {sample.image_id} {sample.crop} {'PASS' if metrics['preview_pass'] else 'FAIL'} "
                f"lp={metrics['lpips']:.4f} ms={metrics['ms_ssim']:.4f} "
                f"y={metrics['y_psnr']:.2f} de={metrics['dE2000_mean']:.2f}",
                flush=True,
            )
    payload = {
        "schema": "preview_runtime_refiner_train_receipt.v1",
        "summary": {"preview_runtime_policy": summarize(rows)},
        "runtime_contract": {
            "source_policy": args.policy,
            "conditioning": args.conditioning,
            "coordinate_mode": args.coordinate_mode,
            "loss_center_size": args.loss_center_size,
            "metric_center_size": args.metric_center_size,
            "forbidden_inputs": ["REF image content", "REF HF/LF fields", "winner JSON", "sample index", "crop identity key planes"],
            "render_inputs": ["source RGB frame/crop", "normalized pixel coordinates", "checkpoint"],
            "source_frequency_planes": frequency_mode,
            "source_frequency_blur": frequency_blur,
            "input_channels": int(ckpt.get("in_channels", 9)),
            "device": str(DEVICE),
        },
        "training": {k: v for k, v in training.items() if k != "samples"},
        "rows": rows,
    }
    args.dashboard_json.write_text(json.dumps(payload, indent=2))
    write_html(payload | {"checkpoint_sha256": training["checkpoint_sha256"], "timing": {"model_ms_per_crop_median": 0.0}, "memory": {"max_rss_mb": 0.0}}, args.dashboard_html)
    print(json.dumps(payload["summary"]["preview_runtime_policy"], indent=2), flush=True)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, action="append", default=[
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/upresable_preview_probe_20260606/crops"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_learned_atlas_20260606"),
        Path("/Volumes/OWC_8TB/gpr_work/artifacts/display_rgb_refiner_20260606"),
    ])
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--init-checkpoint", type=Path)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--dashboard-json", type=Path, required=True)
    ap.add_argument("--dashboard-html", type=Path, required=True)
    ap.add_argument("--policy", choices=["runtime_priority_v1", "fixed_upresable", "fixed_learned_atlas"], default="runtime_priority_v1")
    ap.add_argument("--conditioning", choices=["zero", "content_stats", "color_stats", "global_color_stats"], default="zero")
    ap.add_argument("--coordinate-mode", choices=["local", "global_tile", "zero_coord"], default="local")
    ap.add_argument("--image-id", action="append")
    ap.add_argument("--cluster-audit", type=Path)
    ap.add_argument("--sample-receipt", type=Path, action="append")
    ap.add_argument("--router-sidecar", type=Path)
    ap.add_argument("--include-cluster", type=int, action="append", default=[])
    ap.add_argument("--include-intersect-crop", action="append", default=[], help="Train only receipt rows whose intersects_crops contains this crop name.")
    ap.add_argument("--focus-intersect-crop", action="append", default=[], help="Oversample receipt rows whose intersects_crops contains this crop name.")
    ap.add_argument("--focus-crop", action="append", default=[], help="Oversample receipt rows whose crop id contains this substring.")
    ap.add_argument("--focus-weight", type=float, default=4.0)
    ap.add_argument("--loss-center-size", type=int, default=0, help="If set, train ordinary per-sample losses on the centered square only.")
    ap.add_argument("--metric-center-size", type=int, default=0, help="If set, evaluate metrics and dashboard PNGs on the centered square only.")
    ap.add_argument("--assembled-crop-weight", type=float, default=0.0, help="Add differentiable loss on manifest crops assembled from predicted receipt tiles.")
    ap.add_argument("--assembled-manifest", type=Path, default=REPO / "tests/quality_gates/preview_holdout_set.json")
    ap.add_argument("--assembled-focus-crop", action="append", default=[], help="Limit assembled-crop loss to this manifest crop name.")
    ap.add_argument("--assembled-crop-count", type=int, default=1, help="Number of assembled crop groups to score per step.")
    ap.add_argument("--assembled-ms-weight", type=float, default=0.20)
    ap.add_argument("--assembled-lpips-weight", type=float, default=0.10)
    ap.add_argument("--assembled-y-weight", type=float, default=4.0)
    ap.add_argument("--assembled-lab-weight", type=float, default=2.0)
    ap.add_argument("--assembled-midfreq-weight", type=float, default=0.0, help="Weight for assembled crop blurred residual supervision.")
    ap.add_argument("--assembled-midfreq-blur-sigma", type=float, default=1.0)
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--batch-size", type=int, default=0, help="Use stochastic mini-batches when positive; default keeps legacy full-batch training.")
    ap.add_argument("--architecture", choices=ARCHITECTURES, default="direct")
    ap.add_argument("--width", type=int, default=40)
    ap.add_argument("--residual-scale", type=float, default=0.5)
    ap.add_argument("--lr", type=float, default=8e-4)
    ap.add_argument("--weight-decay", type=float, default=1e-5)
    ap.add_argument("--freeze-base", action="store_true", help="Freeze a residual wrapper's base model and train only the added correction branch.")
    ap.add_argument("--grad-weight", type=float, default=0.08)
    ap.add_argument("--ms-weight", type=float, default=0.40)
    ap.add_argument("--lpips-weight", type=float, default=0.25)
    ap.add_argument("--color-weight", type=float, default=0.0)
    ap.add_argument("--y-weight", type=float, default=0.0)
    ap.add_argument("--opponent-weight", type=float, default=0.0)
    ap.add_argument("--lab-weight", type=float, default=0.0)
    ap.add_argument("--midfreq-weight", type=float, default=0.0, help="Weight for blurred residual supervision against source-to-target residual.")
    ap.add_argument("--midfreq-blur-sigma", type=float, default=1.0, help="Gaussian sigma for mid-frequency residual supervision.")
    ap.add_argument("--source-weight", type=float, default=0.0, help="Penalize changing the source RGB; useful for no-op-biased post refiners.")
    ap.add_argument("--source-lowfreq-weight", type=float, default=0.0, help="Penalize changing blurred source RGB; useful for low-frequency no-op bias.")
    ap.add_argument("--source-lowfreq-blur-sigma", type=float, default=2.0)
    ap.add_argument("--source-frequency-planes", choices=["none", "low_high"], default="none", help="Append source-derived frequency planes to runtime inputs.")
    ap.add_argument("--source-frequency-blur", type=float, default=2.0, help="Blur radius for source-derived low/high input planes.")
    ap.add_argument("--score-y-weight", type=float, default=0.0)
    ap.add_argument("--score-opponent-weight", type=float, default=0.0)
    ap.add_argument("--score-lab-weight", type=float, default=0.0)
    ap.add_argument("--score-midfreq-weight", type=float, default=0.0)
    ap.add_argument("--score-assembled-weight", type=float, default=0.0)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--initial-score-max-samples", type=int, default=64)
    ap.add_argument("--eval-only", action="store_true")
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    args.dashboard_html.parent.mkdir(parents=True, exist_ok=True)
    if args.eval_only:
        training = {"checkpoint": str(args.checkpoint), "checkpoint_sha256": sha256_file(args.checkpoint)}
    else:
        training = train(args)
    evaluate(args, training)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
