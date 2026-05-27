#!/usr/bin/env python3
"""Gate-runner specialized for the gpr_tools production path.

The main run_gate.py invokes a codec binary with a raw-bayer interface
(matches test_fused_roundtrip). The gpr_tools production path is
DNG → GPR → DNG — different interface, and the encoder needs the source
DNG's metadata to produce a roundtrippable file. This runner threads the
source DNG path through directly.

Emits a run.json in the same schema as run_gate.py's runs, so the
dashboard picks it up automatically.

Usage:
  python3 tests/quality_gates/run_gate_gpr_tools.py
"""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
import tifffile
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
GATES_PATH = REPO / "tests/quality_gates/gates.json"
TEST_SET_PATH = REPO / "tests/quality_gates/test_set.json"
RUNS_DIR = REPO / "tests/quality_gates/runs"
GTOOLS = REPO / "build-local/source/app/gpr_tools/gpr_tools"

sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics, bayer_psnr  # noqa: E402


PIPELINE_NAME = "codec=gpr_tools_legacy+cnn=none+demosaic=sips_via_gpr_tools"
SHIP_CLASS = "STILL"


def downsample_for_metrics(png_path: Path, target_w: int) -> np.ndarray:
    img = Image.open(png_path).convert("RGB")
    W, H = img.size
    if W > target_w:
        scale = target_w / W
        img = img.resize((target_w, int(H * scale)), Image.LANCZOS)
    return np.array(img)


def crop_at(png_path: Path, crop: dict, out_path: Path) -> None:
    img = Image.open(png_path).convert("RGB")
    W, H = img.size
    x = max(0, min(crop["x"], W - crop["w"]))
    y = max(0, min(crop["y"], H - crop["h"]))
    img.crop((x, y, x + crop["w"], y + crop["h"])).save(out_path)


def build_visual_diff(ref_crop: Path, test_crop: Path, out_path: Path, title: str) -> None:
    from PIL import ImageDraw
    parts = [Image.open(ref_crop).convert("RGB"), Image.open(test_crop).convert("RGB")]
    cw = max(p.width for p in parts); ch = max(p.height for p in parts)
    pad = 8
    diff = Image.new("RGB", (cw * 2 + pad * 3, ch + pad * 2 + 24), (24, 24, 24))
    for i, p in enumerate(parts):
        diff.paste(p, (pad + i * (cw + pad), pad))
    d = ImageDraw.Draw(diff)
    for i, lbl in enumerate(["REF", "PIPELINE"]):
        d.text((pad + i * (cw + pad) + 4, ch + pad + 4), f"{lbl}  {title}", fill=(220, 220, 220))
    diff.save(out_path)


def main():
    gates = json.loads(GATES_PATH.read_text())
    test_set = json.loads(TEST_SET_PATH.read_text())
    gate_rules = gates["ship_classes"][SHIP_CLASS]["per_image"]
    target_w = test_set["metric_eval_dims"]["width"]
    crops = test_set["crops"]

    # Stable run hash from inputs
    image_shas = []
    for im in test_set["images"]:
        p = Path(im["path"])
        image_shas.append(f"{im['id']}:{p.stat().st_size}:{int(p.stat().st_mtime)}")
    gates_sha = hashlib.sha256(GATES_PATH.read_bytes()).hexdigest()[:16]
    payload = json.dumps({"pipeline_id": PIPELINE_NAME, "image_shas": sorted(image_shas),
                         "gates_sha": gates_sha}, sort_keys=True)
    run_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    run_dir = RUNS_DIR / run_hash
    run_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=f"gate_gprtools_{run_hash}_"))

    print(f"\n=== pipeline: {PIPELINE_NAME}")
    print(f"=== run_hash: {run_hash}  ship_class: {SHIP_CLASS}")
    print(f"=== run_dir:  {run_dir}\n")

    results = {
        "pipeline": PIPELINE_NAME, "ship_class": SHIP_CLASS, "run_hash": run_hash,
        "gates_sha": gates_sha, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "images": {},
    }

    for im in test_set["images"]:
        src = Path(im["path"])
        base = im["id"]
        gpr = workdir / f"{base}.gpr"
        dec_dng = workdir / f"{base}_dec.dng"
        src_png = run_dir / f"{base}_REF.png"
        pipe_png = run_dir / f"{base}_PIPELINE.png"

        t0 = time.time()
        subprocess.run([str(GTOOLS), "-i", str(src), "-o", str(gpr)],
                       check=True, capture_output=True)
        enc_ms = (time.time() - t0) * 1000
        enc_bytes = gpr.stat().st_size

        subprocess.run([str(GTOOLS), "-i", str(gpr), "-o", str(dec_dng)],
                       check=True, capture_output=True)
        subprocess.run(["sips", "-s", "format", "png", str(src), "--out", str(src_png)],
                       check=True, capture_output=True)
        subprocess.run(["sips", "-s", "format", "png", str(dec_dng), "--out", str(pipe_png)],
                       check=True, capture_output=True)

        ref_crop = run_dir / f"{base}_REF_crop_A_detail.png"
        pipe_crop = run_dir / f"{base}_PIPELINE_crop_A_detail.png"
        crop_at(src_png, crops["A_detail"], ref_crop)
        crop_at(pipe_png, crops["A_detail"], pipe_crop)

        ref = downsample_for_metrics(src_png, target_w)
        test = downsample_for_metrics(pipe_png, target_w)
        hh = min(ref.shape[0], test.shape[0]); ww = min(ref.shape[1], test.shape[1])
        m = compute_visual_metrics(ref[:hh, :ww], test[:hh, :ww])

        # Bayer-PSNR
        with tifffile.TiffFile(str(src)) as tf:
            src_bayer = tf.pages[0].pages[0].asarray()
        with tifffile.TiffFile(str(dec_dng)) as tf:
            dec_bayer = tf.pages[0].asarray()
        bp_codec = bayer_psnr(src_bayer, dec_bayer) if src_bayer.shape == dec_bayer.shape else None

        fails = []
        for k, rule in gate_rules.items():
            v = m.get(k)
            if v is None:
                fails.append((k, "missing")); continue
            if "max" in rule and v > rule["max"]:
                fails.append((k, f"{v:.4f} > {rule['max']}"))
            if "min" in rule and v < rule["min"]:
                fails.append((k, f"{v:.4f} < {rule['min']}"))
        verdict = "PASS" if not fails else "FAIL"
        results["images"][base] = {
            **m, "bayer_psnr_codec": bp_codec, "bayer_psnr_final": bp_codec,
            "enc_bytes": enc_bytes, "enc_ms": enc_ms,
            "ref_crop": str(ref_crop), "pipeline_crop": str(pipe_crop),
            "verdict": verdict, "fails": [{"metric": k, "reason": r} for k, r in fails],
        }
        print(f"  {base:<12s} LPIPS={m.get('lpips'):.4f} Y-PSNR={m.get('y_psnr'):.2f} "
              f"MS-SSIM={m.get('ms_ssim'):.4f} ΔE={m.get('dE2000_mean'):.2f} => {verdict}")
        for k, r in fails:
            print(f"     FAIL {k}: {r}")

    ranked = sorted(results["images"].items(),
                    key=lambda kv: kv[1].get("lpips", 0.0) or 0.0, reverse=True)
    results["worst_first"] = [k for k, _ in ranked]
    worst_id, worst_row = ranked[0]
    diff_path = run_dir / f"WORST_{worst_id}_visual_diff.png"
    build_visual_diff(Path(worst_row["ref_crop"]), Path(worst_row["pipeline_crop"]),
                      diff_path, title=PIPELINE_NAME[:50])
    results["worst_image"] = {"id": worst_id, "visual_diff_png": str(diff_path),
                              "lpips": worst_row.get("lpips")}
    results["verdict"] = "FAIL" if any(r["verdict"] == "FAIL" for r in results["images"].values()) else "PASS"
    results["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    (run_dir / "run.json").write_text(json.dumps(results, indent=2, default=str))
    print(f"\n=== VERDICT: {results['verdict']}")
    print(f"=== Worst-first by LPIPS:")
    for img_id in results["worst_first"]:
        r = results["images"][img_id]
        print(f"   {img_id:12s}  LPIPS={r.get('lpips'):.4f}  verdict={r['verdict']}")
    print(f"\n=== Visual diff: {diff_path}")
    print(f"=== Run log:     {run_dir / 'run.json'}")
    sys.exit(0 if results["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
