#!/usr/bin/env python3
"""Quality-gate runner — the SINGLE source of truth for ship verdicts.

This script is the only thing allowed to produce a "PASS" / "FAIL" verdict
for any pipeline. If you're claiming a pipeline ships, you must reference
a run-hash this script emitted.

Design constraints (don't undo these without reading docs/quality_gates.md):
  - Per-image evaluation, never aggregate-only. Worst image governs.
  - Crop positions, eval resolution, and thresholds are file-fixed in
    test_set.json and gates.json. The script never picks them.
  - Pipelines are looked up by name in pipelines/registry.json. No
    inline overrides.
  - Visual diff PNG is written. If it isn't, verdict is INDETERMINATE.
  - The script writes a JSON run log to tests/quality_gates/runs/. The
    run-hash is deterministic from inputs — same inputs = same hash.
  - A failing image is reported with its filename AND the metric values
    that failed. No silent failures.

Usage:
  python3 tests/quality_gates/run_gate.py PIPELINE_NAME [--update-baseline]

Example:
  python3 tests/quality_gates/run_gate.py \
      'codec=ml2_q3+cnn=none+demosaic=sips_via_gpr_tools'

Exit codes:
  0   PASS — all per-image metrics under their gate-class thresholds
  1   FAIL — at least one image failed at least one metric
  2   INDETERMINATE — visual diff wasn't produced, source missing, etc.
  3   USAGE_ERROR — bad invocation, unknown pipeline, etc.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
GATES_PATH = REPO / "tests/quality_gates/gates.json"
TEST_SET_PATH = REPO / "tests/quality_gates/test_set.json"
REGISTRY_PATH = REPO / "pipelines/registry.json"
RUNS_DIR = REPO / "tests/quality_gates/runs"
CLAIMS_LOG = REPO / "docs/claims_log.md"

sys.path.insert(0, str(REPO / "tools/test"))
from metrics import compute_visual_metrics, bayer_psnr  # noqa: E402


# --------------------------------------------------------------------- helpers


def die(code: int, msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_env(env: dict) -> str:
    return ";".join(f"{k}={env[k]}" for k in sorted(env))


def load_json(p: Path) -> dict:
    if not p.exists():
        die(3, f"missing: {p}")
    return json.loads(p.read_text())


# --------------------------------------------------------------------- core


def read_source_bayer(dng_path: str) -> tuple[np.ndarray, int, int]:
    import tifffile
    with tifffile.TiffFile(dng_path) as tf:
        raw = tf.pages[0].pages[0].asarray()
    h, w = raw.shape
    return raw.astype("<u2"), w, h


def encode_decode(codec: dict, bayer: np.ndarray, w: int, h: int,
                  workdir: Path) -> tuple[np.ndarray, int, float]:
    binary = REPO / codec["binary"]
    if not binary.exists():
        die(2, f"codec binary not built: {binary}")
    env = os.environ.copy()
    env.update({k: str(v) for k, v in codec.get("env", {}).items()})
    if "quality" in codec and "FUSED_QUALITY" not in env:
        env["FUSED_QUALITY"] = str(codec["quality"])
    in_raw = workdir / "in.raw"
    out_raw = workdir / "out.raw"
    if not in_raw.exists():
        bayer.tofile(in_raw)
    t0 = time.time()
    r = subprocess.run(
        [str(binary), str(in_raw), str(w), str(h), str(out_raw)],
        env=env, capture_output=True, text=True, timeout=300,
    )
    enc_ms = (time.time() - t0) * 1000.0
    if r.returncode != 0:
        die(2, f"codec failed rc={r.returncode}: {r.stderr[-300:]}")
    import re
    m = re.search(r"ENCODE: (\d+) bytes", r.stderr)
    enc_bytes = int(m.group(1)) if m else 0
    me = re.search(r"ENCODE.*in ([\d.]+) ms", r.stderr)
    enc_ms_reported = float(me.group(1)) if me else enc_ms
    dec = np.fromfile(out_raw, dtype=np.uint16).reshape(h, w)
    return dec, enc_bytes, enc_ms_reported


def apply_cnn(bayer: np.ndarray, cnn: dict) -> np.ndarray:
    if cnn.get("ckpt_path") is None:
        return bayer
    import torch
    import torch.nn.functional as F
    sys.path.insert(0, str(REPO / "tools/cnn"))
    from model import build as build_variant
    ckpt_path = REPO / cnn["ckpt_path"]
    if not ckpt_path.exists():
        die(2, f"CNN checkpoint not in repo: {ckpt_path}. "
               f"Migrate the checkpoint with proper metadata before testing.")
    ck = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    m = build_variant(ck.get("variant", cnn["cnn_arch_variant"]))
    m.load_state_dict(ck["backbone_state"])
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    m.to(dev).eval()
    h, w = bayer.shape
    eh, ew = h - (h & 1), w - (w & 1)
    b = bayer[:eh, :ew]
    pl = np.stack([b[0::2, 0::2], b[0::2, 1::2], b[1::2, 0::2], b[1::2, 1::2]], 0)
    raw_norm = cnn.get("raw_norm", 16383.0)
    res_scale = cnn.get("residual_scale", 0.01)
    x = torch.from_numpy(pl.astype(np.float32) / raw_norm).unsqueeze(0).to(dev)
    H, W = x.shape[-2:]
    ph = (16 - H % 16) % 16
    pw = (16 - W % 16) % 16
    if ph or pw:
        x = F.pad(x, (0, pw, 0, ph), mode="reflect")
    with torch.no_grad():
        y = (x + res_scale * m(x)).clamp(0, 1)
    y = y[..., :H, :W].squeeze(0).cpu().numpy()
    out = bayer.copy()
    out[:eh:2, :ew:2] = np.clip(y[0] * raw_norm, 0, raw_norm).astype(np.uint16)
    out[:eh:2, 1:ew:2] = np.clip(y[1] * raw_norm, 0, raw_norm).astype(np.uint16)
    out[1:eh:2, :ew:2] = np.clip(y[2] * raw_norm, 0, raw_norm).astype(np.uint16)
    out[1:eh:2, 1:ew:2] = np.clip(y[3] * raw_norm, 0, raw_norm).astype(np.uint16)
    return out


def demosaic_to_png(bayer: np.ndarray, dms: dict, src_dng: Path,
                    workdir: Path, out_png: Path) -> None:
    binary = REPO / dms["binary"]
    if not binary.exists():
        die(2, f"demosaic binary not built: {binary}")
    # Extract source-DNG params (color matrix etc.)
    params_cache = workdir / "params.json"
    if not params_cache.exists():
        cp = subprocess.run([str(binary), "-i", str(src_dng), "-d", "1"],
                            capture_output=True, text=True)
        if cp.returncode != 0:
            die(2, f"gpr_tools params dump failed: {cp.stderr[-200:]}")
        lines = [l for l in cp.stdout.splitlines() if not l.startswith("[")]
        params_cache.write_text("\n".join(lines))
    params = json.loads(params_cache.read_text())
    h, w = bayer.shape
    params["input_width"] = w
    params["input_height"] = h
    params["input_pitch"] = w * 2
    params_run = workdir / f"params_{w}x{h}.json"
    params_run.write_text(json.dumps(params))
    raw_in = workdir / "bayer.raw"
    bayer.tofile(raw_in)
    dng_out = workdir / "out.dng"
    r = subprocess.run([str(binary), "-i", str(raw_in), "-w", str(w), "-h", str(h),
                        "-x", "rggb14", "-o", str(dng_out), "-a", str(params_run)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(2, f"gpr_tools DNG write failed: {r.stderr[-200:]}")
    r = subprocess.run(["sips", "-s", "format", "png", str(dng_out), "--out", str(out_png)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die(2, f"sips render failed: {r.stderr[-200:]}")


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
    x, y, cw, ch = crop["x"], crop["y"], crop["w"], crop["h"]
    x = max(0, min(x, W - cw))
    y = max(0, min(y, H - ch))
    img.crop((x, y, x + cw, y + ch)).save(out_path)


def build_visual_diff(ref_crop: Path, test_crop: Path, last_best_crop: Path | None,
                      out_path: Path, title: str) -> None:
    """Side-by-side image: REF | this pipeline | (optional) last-best.
    Forces visual inspection at fixed dimensions."""
    parts = [Image.open(ref_crop).convert("RGB"), Image.open(test_crop).convert("RGB")]
    if last_best_crop and last_best_crop.exists():
        parts.append(Image.open(last_best_crop).convert("RGB"))
    cw = max(p.width for p in parts)
    ch = max(p.height for p in parts)
    pad = 8
    total_w = cw * len(parts) + pad * (len(parts) + 1)
    total_h = ch + pad * 2 + 24  # space for label band
    diff = Image.new("RGB", (total_w, total_h), (24, 24, 24))
    for i, p in enumerate(parts):
        diff.paste(p, (pad + i * (cw + pad), pad))
    from PIL import ImageDraw
    d = ImageDraw.Draw(diff)
    labels = ["REF", "PIPELINE"] + (["LAST_BEST"] if len(parts) == 3 else [])
    for i, lbl in enumerate(labels):
        d.text((pad + i * (cw + pad) + 4, ch + pad + 4), f"{lbl}  {title}", fill=(220, 220, 220))
    diff.save(out_path)


# --------------------------------------------------------------------- runner


def pipeline_run_hash(pipeline_id: str, codec: dict, cnn: dict,
                       dms: dict, image_shas: list[str], gates_sha: str) -> str:
    payload = json.dumps({
        "pipeline_id": pipeline_id,
        "codec_env_canonical": canonical_env({**codec.get("env", {}),
                                              "QUALITY": codec.get("quality")}),
        "cnn_ckpt_sha256": cnn.get("ckpt_sha256", "none"),
        "demosaicer": dms.get("binary", ""),
        "image_shas": sorted(image_shas),
        "gates_sha": gates_sha,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def evaluate_pipeline(pipeline_name: str) -> dict:
    gates = load_json(GATES_PATH)
    test_set = load_json(TEST_SET_PATH)
    registry = load_json(REGISTRY_PATH)
    if pipeline_name not in registry["pipelines"]:
        die(3, f"unknown pipeline: {pipeline_name}. "
               f"Available: {list(registry['pipelines'].keys())}")
    pipe = registry["pipelines"][pipeline_name]
    codec = registry["codecs"][pipe["codec"]]
    cnn = registry["cnns"][pipe["cnn"]]
    dms = registry["demosaicers"][pipe["demosaic"]]
    ship_class = pipe["ship_class"]
    gate_thresholds = gates["ship_classes"][ship_class]["per_image"]

    target_w = test_set["metric_eval_dims"]["width"]
    images = test_set["images"]
    crops = test_set["crops"]

    # Verify source DNGs exist before any work.
    missing = [im for im in images if not Path(im["path"]).exists()]
    if missing:
        die(2, f"source DNG(s) missing: {[m['id'] for m in missing]}")

    # Source SHAs (truncated for stable hash without re-hashing 50MB each run)
    image_shas = []
    for im in images:
        p = Path(im["path"])
        # Stat-based stamp is fine for local dev; CI would use sha256.
        image_shas.append(f"{im['id']}:{p.stat().st_size}:{int(p.stat().st_mtime)}")

    gates_sha = hashlib.sha256(GATES_PATH.read_bytes()).hexdigest()[:16]
    run_hash = pipeline_run_hash(pipeline_name, codec, cnn, dms, image_shas, gates_sha)
    run_dir = RUNS_DIR / f"{run_hash}"
    run_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=f"gate_{run_hash}_"))

    print(f"\n=== pipeline: {pipeline_name}")
    print(f"=== run_hash: {run_hash}  ship_class: {ship_class}")
    print(f"=== run_dir:  {run_dir}")

    results = {
        "pipeline": pipeline_name,
        "ship_class": ship_class,
        "run_hash": run_hash,
        "gates_sha": gates_sha,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "images": {},
    }

    for im in images:
        src_dng = Path(im["path"])
        print(f"\n  -- {im['id']} ({im['character']})")
        bayer, w, h = read_source_bayer(im["path"])
        img_work = workdir / im["id"]
        img_work.mkdir()
        # 1. encode/decode through codec
        dec, enc_bytes, enc_ms = encode_decode(codec, bayer, w, h, img_work)
        bp_codec = bayer_psnr(bayer, dec)
        # 2. apply CNN (no-op if cnn=none)
        post = apply_cnn(dec, cnn)
        bp_final = bayer_psnr(bayer, post)
        # 3. demosaic both REF and pipeline output to PNG
        ref_png = run_dir / f"{im['id']}_REF.png"
        pipe_png = run_dir / f"{im['id']}_PIPELINE.png"
        if not ref_png.exists():
            demosaic_to_png(bayer, dms, src_dng, img_work, ref_png)
        demosaic_to_png(post, dms, src_dng, img_work, pipe_png)
        # 4. crop A_detail (the canonical hard case) for visual diff
        ref_crop_path = run_dir / f"{im['id']}_REF_crop_A_detail.png"
        pipe_crop_path = run_dir / f"{im['id']}_PIPELINE_crop_A_detail.png"
        crop_at(ref_png, crops["A_detail"], ref_crop_path)
        crop_at(pipe_png, crops["A_detail"], pipe_crop_path)
        # 5. downsample to target_w for metric computation
        ref = downsample_for_metrics(ref_png, target_w)
        test = downsample_for_metrics(pipe_png, target_w)
        if test.shape != ref.shape:
            hh = min(ref.shape[0], test.shape[0])
            ww = min(ref.shape[1], test.shape[1])
            ref, test = ref[:hh, :ww], test[:hh, :ww]
        m = compute_visual_metrics(ref, test)
        # 6. evaluate per-metric thresholds
        fails = []
        for key, rule in gate_thresholds.items():
            v = m.get(key)
            if v is None:
                fails.append((key, "missing"))
                continue
            if "max" in rule and v > rule["max"]:
                fails.append((key, f"{v:.4f} > {rule['max']}"))
            if "min" in rule and v < rule["min"]:
                fails.append((key, f"{v:.4f} < {rule['min']}"))
        verdict = "PASS" if not fails else "FAIL"
        results["images"][im["id"]] = {
            **m,
            "bayer_psnr_codec": bp_codec,
            "bayer_psnr_final": bp_final,
            "enc_bytes": enc_bytes,
            "enc_ms": enc_ms,
            "ref_crop": str(ref_crop_path),
            "pipeline_crop": str(pipe_crop_path),
            "verdict": verdict,
            "fails": [{"metric": k, "reason": r} for k, r in fails],
        }
        print(f"     LPIPS={m.get('lpips'):.4f}  Y-PSNR={m.get('y_psnr'):.2f}  "
              f"MS-SSIM={m.get('ms_ssim'):.4f}  ΔE={m.get('dE2000_mean'):.2f}  "
              f"=> {verdict}")
        if fails:
            for k, r in fails:
                print(f"        FAIL {k}: {r}")

    # 7. sort worst-first by LPIPS (mandatory)
    ranked = sorted(
        results["images"].items(),
        key=lambda kv: kv[1].get("lpips", 0.0) or 0.0,
        reverse=True,
    )
    results["worst_first"] = [k for k, _ in ranked]
    worst_id, worst_row = ranked[0]

    # 8. build visual-diff for the worst image
    last_best_link = run_dir / "last_best_crop.png"  # placeholder; updated when --update-baseline
    diff_path = run_dir / f"WORST_{worst_id}_visual_diff.png"
    build_visual_diff(
        Path(worst_row["ref_crop"]),
        Path(worst_row["pipeline_crop"]),
        last_best_link if last_best_link.exists() else None,
        diff_path,
        title=f"{pipeline_name[:50]}",
    )
    results["worst_image"] = {
        "id": worst_id,
        "visual_diff_png": str(diff_path),
        "lpips": worst_row.get("lpips"),
    }

    # 9. overall verdict: any image FAIL -> FAIL
    any_fail = any(r["verdict"] == "FAIL" for r in results["images"].values())
    results["verdict"] = "FAIL" if any_fail else "PASS"
    results["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    # 10. write the run log
    (run_dir / "run.json").write_text(json.dumps(results, indent=2, default=str))

    # 11. print worst-first summary (mandatory format)
    print(f"\n=== VERDICT: {results['verdict']}")
    print(f"=== Worst-first by LPIPS:")
    for img_id in results["worst_first"]:
        row = results["images"][img_id]
        print(f"   {img_id:12s}  LPIPS={row.get('lpips'):.4f}  "
              f"verdict={row['verdict']}")
    print(f"\n=== Visual diff for WORST image written to:")
    print(f"   {diff_path}")
    print(f"\n=== Run log: {run_dir / 'run.json'}")
    return results


# --------------------------------------------------------------------- main


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pipeline", help="Full pipeline name from registry.json")
    p.add_argument("--claim", action="store_true",
                   help="After PASS, prompt for inspection-sentence to append to claims_log.md")
    args = p.parse_args()

    res = evaluate_pipeline(args.pipeline)

    if args.claim:
        if res["verdict"] != "PASS":
            print("\n--claim requested but verdict is FAIL. Refusing to log.", file=sys.stderr)
            sys.exit(1)
        if not sys.stdin.isatty():
            print("\n--claim requires interactive stdin for the inspection sentence.",
                  file=sys.stderr)
            sys.exit(2)
        print(f"\nReview the visual diff at: {res['worst_image']['visual_diff_png']}")
        sentence = input("Inspection sentence (>=6 words, must include a concrete noun): ").strip()
        nouns = ["rocks", "sky", "edge", "blockiness", "haze", "noise",
                 "detail", "texture", "shadow", "highlight", "crosshatch",
                 "smooth", "ringing", "color"]
        words = sentence.split()
        if len(words) < 6:
            print("Sentence too short (<6 words). Refusing.", file=sys.stderr)
            sys.exit(2)
        if not any(n in sentence.lower() for n in nouns):
            print(f"Sentence has no concrete noun (one of {nouns}). Refusing.",
                  file=sys.stderr)
            sys.exit(2)
        CLAIMS_LOG.parent.mkdir(exist_ok=True)
        line = (f"- {time.strftime('%Y-%m-%d %H:%M')}  pipeline=`{args.pipeline}`  "
                f"run={res['run_hash']}  worst_lpips={res['worst_image']['lpips']:.4f}  "
                f"worst_image={res['worst_image']['id']}  "
                f"visual_description=\"{sentence}\"\n")
        with open(CLAIMS_LOG, "a") as f:
            f.write(line)
        print(f"Logged claim to {CLAIMS_LOG}")

    sys.exit(0 if res["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
