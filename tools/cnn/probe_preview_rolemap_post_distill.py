#!/usr/bin/env python3
"""Distill arbitrary-tiled PREVIEW crops toward exact no-REF crops with role maps.

This is a diagnostic for the full-frame PREVIEW blocker. Training target is the
exact no-REF crop output, not REF. REF is used only for scoring.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from pytorch_msssim import ms_ssim


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/test"))
sys.path.insert(0, str(REPO / "tools/cnn"))

from metrics import compute_visual_metrics  # noqa: E402
from train_display_rgb_direct_nonref import build_rgb_refiner, grad_loss, pass_preview  # noqa: E402


DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def tensor_rgb(rgb: np.ndarray) -> torch.Tensor:
    arr = np.transpose(rgb.astype(np.float32) / 255.0, (2, 0, 1))
    return torch.from_numpy(arr.copy())


def role_name(row: dict[str, Any], tile: dict[str, Any]) -> str:
    return str(tile.get("role") or tile.get("checkpoint_role") or "unknown")


def rect_intersection_xyxy(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def build_role_planes(row: dict[str, Any], role_to_idx: dict[str, int], height: int, width: int) -> np.ndarray:
    crop_box = tuple(int(v) for v in row["source_crop_box_render"])
    crop_x0, crop_y0, crop_x1, crop_y1 = crop_box
    crop_w = max(1, crop_x1 - crop_x0)
    crop_h = max(1, crop_y1 - crop_y0)
    planes = np.zeros((len(role_to_idx), height, width), dtype=np.float32)
    tiles = ((row.get("tiled_intersections") or {}).get("tiles") or [])
    for tile in tiles:
        xywh = tile.get("written_xywh") or tile.get("xywh")
        if not xywh:
            continue
        tx, ty, tw, th = [int(v) for v in xywh]
        inter = rect_intersection_xyxy(crop_box, (tx, ty, tx + tw, ty + th))
        if inter is None:
            continue
        ix0, iy0, ix1, iy1 = inter
        px0 = int(round((ix0 - crop_x0) * width / crop_w))
        px1 = int(round((ix1 - crop_x0) * width / crop_w))
        py0 = int(round((iy0 - crop_y0) * height / crop_h))
        py1 = int(round((iy1 - crop_y0) * height / crop_h))
        px0, px1 = max(0, px0), min(width, px1)
        py0, py1 = max(0, py0), min(height, py1)
        if px1 <= px0 or py1 <= py0:
            continue
        planes[role_to_idx[role_name(row, tile)], py0:py1, px0:px1] = 1.0
    if planes.size and not np.any(planes):
        roles = (row.get("tiled_intersections") or {}).get("roles") or {}
        if roles:
            best_role = max(roles.items(), key=lambda item: float(item[1]))[0]
            planes[role_to_idx[str(best_role)], :, :] = 1.0
    return planes


def build_input(tiled_rgb: np.ndarray, role_planes: np.ndarray) -> torch.Tensor:
    height, width = tiled_rgb.shape[:2]
    yy, xx = np.meshgrid(
        np.linspace(0.0, 1.0, height, dtype=np.float32),
        np.linspace(0.0, 1.0, width, dtype=np.float32),
        indexing="ij",
    )
    planes = [
        np.transpose(tiled_rgb.astype(np.float32) / 255.0, (2, 0, 1)),
        np.stack([xx, yy], axis=0),
        role_planes,
    ]
    return torch.from_numpy(np.concatenate(planes, axis=0).copy())


def collect_roles(rows: list[dict[str, Any]]) -> dict[str, int]:
    roles: set[str] = set()
    for row in rows:
        for tile in ((row.get("tiled_intersections") or {}).get("tiles") or []):
            roles.add(role_name(row, tile))
        roles.update(str(role) for role in ((row.get("tiled_intersections") or {}).get("roles") or {}).keys())
    return {role: idx for idx, role in enumerate(sorted(roles))}


def selected_rows(payload: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    rows = list(payload.get("rows") or [])
    if mode == "all":
        return rows
    if mode == "exact_pass_tiled_fail":
        return [
            row
            for row in rows
            if bool((row.get("exact_metrics") or {}).get("preview_pass"))
            and not bool((row.get("tiled_metrics") or {}).get("preview_pass"))
        ]
    if mode == "mixed_exact_pass_tiled_fail":
        return [
            row
            for row in rows
            if bool((row.get("exact_metrics") or {}).get("preview_pass"))
            and not bool((row.get("tiled_metrics") or {}).get("preview_pass"))
            and int((row.get("tiled_intersections") or {}).get("role_count") or 0) > 1
        ]
    raise ValueError(f"unsupported row selection {mode!r}")


def center_crop_tensor(x: torch.Tensor, size: int) -> torch.Tensor:
    if size <= 0:
        return x
    height, width = x.shape[-2:]
    y0 = max(0, (height - size) // 2)
    x0 = max(0, (width - size) // 2)
    return x[..., y0:y0 + size, x0:x0 + size].contiguous()


def charbonnier(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    diff = pred - target
    return torch.sqrt(diff * diff + 1e-6).mean()


def luma_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    w = pred.new_tensor([0.2126, 0.7152, 0.0722]).view(1, 3, 1, 1)
    pred_y = (pred * w).sum(dim=1, keepdim=True)
    target_y = (target * w).sum(dim=1, keepdim=True)
    return charbonnier(pred_y, target_y)


def train_model(args: argparse.Namespace, x: torch.Tensor, y: torch.Tensor) -> tuple[torch.nn.Module, dict[str, Any]]:
    model = build_rgb_refiner(
        "direct",
        width=int(args.width),
        in_channels=int(x.shape[1]),
        residual_scale=float(args.residual_scale),
    ).to(DEVICE)
    xt = x.to(DEVICE).contiguous()
    yt = y.to(DEVICE).contiguous()
    opt = torch.optim.AdamW(model.parameters(), lr=float(args.lr), weight_decay=float(args.weight_decay))
    best = float("inf")
    best_state: dict[str, torch.Tensor] | None = None
    t0 = time.time()
    for step in range(1, int(args.steps) + 1):
        pred = model(xt).contiguous()
        pred_loss = center_crop_tensor(pred, int(args.loss_center_size))
        yt_loss = center_crop_tensor(yt, int(args.loss_center_size))
        l1 = charbonnier(pred_loss, yt_loss)
        ly = luma_loss(pred_loss, yt_loss)
        lg = grad_loss(pred_loss, yt_loss)
        lms = 1.0 - ms_ssim(pred_loss, yt_loss, data_range=1.0, win_size=7) if float(args.ms_weight) > 0.0 else pred.new_tensor(0.0)
        loss = l1 + float(args.y_weight) * ly + float(args.grad_weight) * lg + float(args.ms_weight) * lms
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        score = float(loss.detach().cpu())
        if score < best:
            best = score
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if step == 1 or step % int(args.log_every) == 0 or step == int(args.steps):
            print(
                f"step {step}/{args.steps} loss={score:.6f} l1={float(l1.detach().cpu()):.5f} "
                f"y={float(ly.detach().cpu()):.5f} grad={float(lg.detach().cpu()):.5f} "
                f"ms={float(lms.detach().cpu()):.5f} best={best:.6f} t={time.time() - t0:.1f}s",
                flush=True,
            )
    if best_state is None:
        raise RuntimeError("training produced no state")
    model.load_state_dict(best_state)
    return model, {"best_loss": best, "train_seconds": time.time() - t0}


def metric_row(ref: np.ndarray, rgb: np.ndarray) -> dict[str, Any]:
    metrics = compute_visual_metrics(ref, rgb)
    metrics["preview_pass"] = pass_preview(metrics)
    return metrics


def summarize(rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    subset = [row[prefix] for row in rows]
    count = len(subset)
    pass_count = sum(1 for row in subset if row["preview_pass"])
    out: dict[str, Any] = {
        "count": count,
        "pass_count": pass_count,
        "pass_rate": pass_count / count if count else 0.0,
    }
    for metric in ("lpips", "ms_ssim", "y_psnr", "dE2000_mean"):
        values = [float(row[metric]) for row in subset]
        if not values:
            out[f"worst_{metric}"] = None
        elif metric in {"lpips", "dE2000_mean"}:
            out[f"worst_{metric}"] = max(values)
        else:
            out[f"worst_{metric}"] = min(values)
    return out


def write_html(path: Path, payload: dict[str, Any]) -> None:
    def fmt(value: Any) -> str:
        if isinstance(value, float):
            if math.isinf(value):
                return "inf"
            return f"{value:.4f}"
        return html.escape(str(value))

    rows_html = []
    for row in payload["rows"]:
        rows_html.append(
            "<tr>"
            f"<td>{html.escape(row['image_id'])}<br>{html.escape(row['crop'])}</td>"
            f"<td>{html.escape(str(row['mixed_tiled_roles']))}<br>{html.escape(json.dumps(row['tiled_roles'], sort_keys=True))}</td>"
            f"<td><img src='{html.escape(row['assets']['tiled'])}'><br>tiled</td>"
            f"<td><img src='{html.escape(row['assets']['exact'])}'><br>exact teacher</td>"
            f"<td><img src='{html.escape(row['assets']['output'])}'><br>role-map output</td>"
            f"<td>{'PASS' if row['tiled_ref_metrics']['preview_pass'] else 'FAIL'}<br>"
            f"LPIPS {fmt(row['tiled_ref_metrics']['lpips'])}<br>dE {fmt(row['tiled_ref_metrics']['dE2000_mean'])}</td>"
            f"<td>{'PASS' if row['output_ref_metrics']['preview_pass'] else 'FAIL'}<br>"
            f"LPIPS {fmt(row['output_ref_metrics']['lpips'])}<br>MS {fmt(row['output_ref_metrics']['ms_ssim'])}<br>"
            f"Y {fmt(row['output_ref_metrics']['y_psnr'])}<br>dE {fmt(row['output_ref_metrics']['dE2000_mean'])}</td>"
            f"<td>{'PASS' if row['output_teacher_metrics']['preview_pass'] else 'FAIL'}<br>"
            f"LPIPS {fmt(row['output_teacher_metrics']['lpips'])}<br>MS {fmt(row['output_teacher_metrics']['ms_ssim'])}<br>"
            f"Y {fmt(row['output_teacher_metrics']['y_psnr'])}<br>dE {fmt(row['output_teacher_metrics']['dE2000_mean'])}</td>"
            "</tr>"
        )
    doc = """<!doctype html>
<meta charset="utf-8">
<title>PREVIEW Role-Map Post Distill</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:24px;color:#1f2933}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border:1px solid #ccd5df;padding:6px;vertical-align:top}
th{background:#edf2f7}
img{width:192px;height:192px;object-fit:contain;background:#111}
pre{background:#f4f7fa;padding:12px}
</style>
<h1>PREVIEW Role-Map Post Distill</h1>
<p>Training target is exact no-REF crop output. REF is scoring-only.</p>
<h2>Summary</h2>
<pre>""" + html.escape(json.dumps(payload["summary"], indent=2)) + """</pre>
<table>
<thead><tr><th>Row</th><th>Runtime Roles</th><th>Tiled</th><th>Exact</th><th>Output</th><th>Tiled vs REF</th><th>Output vs REF</th><th>Output vs Teacher</th></tr></thead>
<tbody>""" + "".join(rows_html) + """</tbody></table>"""
    path.write_text(doc)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contract-audit", type=Path, required=True)
    ap.add_argument("--row-selection", choices=["all", "exact_pass_tiled_fail", "mixed_exact_pass_tiled_fail"], default="exact_pass_tiled_fail")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--output-html", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=600)
    ap.add_argument("--width", type=int, default=48)
    ap.add_argument("--residual-scale", type=float, default=0.5)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--loss-center-size", type=int, default=0)
    ap.add_argument("--y-weight", type=float, default=2.0)
    ap.add_argument("--grad-weight", type=float, default=0.10)
    ap.add_argument("--ms-weight", type=float, default=0.10)
    ap.add_argument("--log-every", type=int, default=100)
    args = ap.parse_args()

    payload = json.loads(args.contract_audit.read_text())
    rows = selected_rows(payload, args.row_selection)
    if not rows:
        raise RuntimeError(f"row selection {args.row_selection!r} produced no rows")
    role_to_idx = collect_roles(rows)
    base_dir = args.contract_audit.parent
    xs: list[torch.Tensor] = []
    ys: list[torch.Tensor] = []
    loaded: list[dict[str, Any]] = []
    for row in rows:
        assets = row.get("assets") or {}
        tiled = load_rgb(base_dir / assets["tiled"])
        exact = load_rgb(base_dir / assets["exact"])
        ref = load_rgb(base_dir / assets["ref"])
        role_planes = build_role_planes(row, role_to_idx, tiled.shape[0], tiled.shape[1])
        xs.append(build_input(tiled, role_planes))
        ys.append(tensor_rgb(exact))
        loaded.append({"row": row, "tiled": tiled, "exact": exact, "ref": ref})
    x = torch.stack(xs).contiguous()
    y = torch.stack(ys).contiguous()
    model, train_summary = train_model(args, x, y)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "kind": "preview_rolemap_post_distill",
            "architecture": "direct",
            "state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "width": int(args.width),
            "in_channels": int(x.shape[1]),
            "residual_scale": float(args.residual_scale),
            "role_to_idx": role_to_idx,
            "row_selection": args.row_selection,
            "training_target": "exact no-REF crop output",
            "forbidden_render_inputs": ["REF image content", "REF HF/LF fields", "winner JSON", "sample index", "crop identity key planes"],
        },
        args.checkpoint,
    )

    result_rows: list[dict[str, Any]] = []
    with torch.no_grad():
        pred = model(x.to(DEVICE)).detach().cpu().numpy()
    for idx, item in enumerate(loaded):
        row = item["row"]
        out_rgb = np.clip(np.transpose(pred[idx], (1, 2, 0)) * 255.0, 0, 255).astype(np.uint8)
        name = f"{row['image_id']}_{row['crop']}_rolemap_post.png"
        Image.fromarray(out_rgb).save(args.output_dir / name)
        result_rows.append(
            {
                "image_id": row["image_id"],
                "crop": row["crop"],
                "mixed_tiled_roles": int((row.get("tiled_intersections") or {}).get("role_count") or 0) > 1,
                "tiled_roles": (row.get("tiled_intersections") or {}).get("roles") or {},
                "assets": {
                    "tiled": str((base_dir / row["assets"]["tiled"]).resolve()),
                    "exact": str((base_dir / row["assets"]["exact"]).resolve()),
                    "output": name,
                },
                "tiled_ref_metrics": metric_row(item["ref"], item["tiled"]),
                "exact_ref_metrics": metric_row(item["ref"], item["exact"]),
                "output_ref_metrics": metric_row(item["ref"], out_rgb),
                "output_teacher_metrics": metric_row(item["exact"], out_rgb),
            }
        )
        print(
            f"EVAL {row['image_id']} {row['crop']} "
            f"out_ref={'PASS' if result_rows[-1]['output_ref_metrics']['preview_pass'] else 'FAIL'} "
            f"lp={result_rows[-1]['output_ref_metrics']['lpips']:.4f} "
            f"de={result_rows[-1]['output_ref_metrics']['dE2000_mean']:.2f}",
            flush=True,
        )

    out_payload = {
        "schema": "preview_rolemap_post_distill.v1",
        "contract_audit": str(args.contract_audit),
        "row_selection": args.row_selection,
        "role_to_idx": role_to_idx,
        "device": str(DEVICE),
        "checkpoint": str(args.checkpoint),
        "training": train_summary,
        "runtime_contract": {
            "training_target": "exact no-REF crop output",
            "ref_usage": "scoring_only",
            "render_inputs": ["arbitrary tiled RGB crop", "runtime tile role planes", "normalized pixel coordinates"],
            "forbidden_inputs": ["REF image content", "REF HF/LF fields", "winner JSON", "sample index", "crop identity key planes"],
        },
        "summary": {
            "tiled_ref": summarize(result_rows, "tiled_ref_metrics"),
            "exact_ref": summarize(result_rows, "exact_ref_metrics"),
            "output_ref": summarize(result_rows, "output_ref_metrics"),
            "output_teacher": summarize(result_rows, "output_teacher_metrics"),
        },
        "rows": result_rows,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(out_payload, indent=2) + "\n")
    write_html(args.output_html, out_payload)
    print(json.dumps(out_payload["summary"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
