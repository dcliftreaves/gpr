"""CNN super-res/dering regression test.

Walks every F-family checkpoint, runs codec-bayer → CNN → rawpy AHD render,
computes brightness-matched masked-middle Y-PSNR against the source DNG
render, and asserts the gain over the codec baseline matches the locked
per-checkpoint number within ±0.1 dB.

Methodology mirrors eval_all_arch.py in the external dering workspace
exactly. Same model loaders, same inference scaling (RESIDUAL_SCALE=0.01),
same rawpy postprocess flags, same psnr() mask (dark<10, bright<250).
This is the production eval reduced to an assertable form.

Expected per-checkpoint gains (locked from clean 2026-05-24 run; see the
eval_all_arch_results.json in dering_proto_v2/):

  codec baseline                       31.059 dB
  F_ane (w=16) 2×                      +5.51 dB
  F_ane_no_sr (w=16) 1×                +0.91 dB
  F_ane LK7 1×                         +0.70 dB
  F_ane_w8 self-KD 1×                  +0.71 dB
  F_ane_w32 2× (heavy)                 +6.23 dB
  F_ane_w8 heavy-KD 2×                 +3.32 dB
  F_ane LK7 2×                         +5.84 dB
  F_ane_w32 1× (heavy still-recovery)  +1.375 dB

Skips gracefully when torch / rawpy / cv2 / dering_proto_v2/ are missing
(Linux CI will skip; macOS dev box will run).
"""
import os
import sys
from pathlib import Path

# ---- Dependency probe: import everything, skip cleanly if any fail. ----

MISSING = []
try:
    import numpy as np
except ImportError as e:
    MISSING.append(f"numpy ({e})")
try:
    import torch
    import torch.nn.functional as F
except ImportError as e:
    MISSING.append(f"torch ({e})")
try:
    import rawpy
except ImportError as e:
    MISSING.append(f"rawpy ({e})")
try:
    import cv2
except ImportError as e:
    MISSING.append(f"cv2/opencv-python ({e})")

REPO = Path(__file__).resolve().parents[2]
EXTERNAL_ROOT = Path(os.environ.get("GPR_EXTERNAL_ROOT", "/Volumes/OWC_8TB/gpr_work"))
DERING_DIR = str(Path(os.environ.get(
    "GPR_DERING_DIR", EXTERNAL_ROOT / "external" / "dering_proto_v2")))
CKPT_DIR = str(Path(os.environ.get("GPR_CHECKPOINT_ROOT", EXTERNAL_ROOT / "checkpoints")))
REF_DNG = str(Path(os.environ.get(
    "GPR_CNN_REF_DNG", REPO / "data/test_sets/entropy_matrix/Z8_ISO64.DNG")))
CODEC_RAW = str(Path(os.environ.get(
    "GPR_CNN_CODEC_RAW", EXTERNAL_ROOT / "external/dering_proto_v2/pairs/Z8_ISO64_codec.raw")))

if not MISSING and not os.path.isdir(CKPT_DIR):
    MISSING.append(f"checkpoints directory not present: {CKPT_DIR}")
if not MISSING and not os.path.exists(REF_DNG):
    MISSING.append(f"reference DNG not present: {REF_DNG}")
if not MISSING and not os.path.exists(CODEC_RAW):
    MISSING.append(f"codec bayer not present: {CODEC_RAW}")

if MISSING:
    print("SKIP — CNN regression test prerequisites not available:")
    for m in MISSING:
        print(f"  - {m}")
    print("This test is macOS-development-host only and is allowed to skip.")
    sys.exit(0)

# ---- Real test starts here ----

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, DERING_DIR)
# Optional reconstructed-legacy-model dir; tolerated if missing.
sys.path.insert(0, str(EXTERNAL_ROOT / "tmp" / "cnn_sweep"))

DEVICE = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
RAW_NORM = 16383.0
RESIDUAL_SCALE = 0.01
TOLERANCE_DB = float(os.environ.get("CNN_REGRESSION_TOLERANCE_DB", "0.1"))

# ---- helpers (verbatim from eval_all_arch.py) ----

def bayer_bicubic_2x(b):
    R = b[0::2, 0::2]; G1 = b[0::2, 1::2]; G2 = b[1::2, 0::2]; B = b[1::2, 1::2]
    sh, sw = R.shape
    o = np.empty((sh * 4, sw * 4), dtype=np.uint16)
    for plane, dst in zip([R, G1, G2, B], [(0, 0), (0, 1), (1, 0), (1, 1)]):
        up = cv2.resize(plane, (sw * 2, sh * 2), cv2.INTER_CUBIC).astype(np.uint16)
        o[dst[0]::2, dst[1]::2] = up
    return o


def render_rawpy(bayer):
    raw = rawpy.imread(REF_DNG)
    raw.raw_image[:] = bayer
    rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=16,
                          gamma=(2.222, 4.5), output_color=rawpy.ColorSpace.sRGB,
                          demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD)
    raw.close()
    return rgb


def Y_of(im):
    return 0.299 * im[..., 0] + 0.587 * im[..., 1] + 0.114 * im[..., 2]


def psnr_masked(ref, test, dark=10, bright=250):
    rs = (ref / 256.0).astype(np.float32)
    ts = (test / 256.0).astype(np.float32)
    ry = Y_of(rs); ty = Y_of(ts)
    mask = (ry > dark) & (ry < bright)
    mse = ((ry[mask] - ty[mask]) ** 2).mean()
    return 20 * np.log10(255.0 / np.sqrt(max(mse, 1e-12)))


def brightness_match(rgb, ref):
    rm = np.array([ref[..., c].mean() for c in range(3)])
    o = rgb.astype(np.float32)
    for c in range(3):
        o[..., c] = np.clip(o[..., c] + (rm[c] - o[..., c].mean()), 0, 65535)
    return o.astype(np.uint16)


# ---- model loaders ----

def load_F_ane_or_kd(ckpt_path):
    from model_F_ane import build as build_ane, build_lk
    try:
        from model_F_ane_kd import build as build_kd
        kd_known = True
    except ImportError:
        kd_known = False

    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    variant = ck.get("variant", "F_ane")
    sd = ck["backbone_state"]

    if variant.startswith("F_ane_w8") or variant.startswith("F_ane_l2"):
        if not kd_known:
            raise RuntimeError("kd model module not available")
        m = build_kd(variant)
    elif any(("dw.weight" in k and sd[k].shape[-1] == 7) for k in sd):
        kernel_sz = None
        for k in sd:
            if "encoders.0.0.dw.weight" in k:
                kernel_sz = sd[k].shape[-1]
                break
        m = build_lk(variant, dw_kernel=kernel_sz)
    else:
        m = build_ane(variant)

    m.load_state_dict(sd)
    m.to(DEVICE).eval()
    n_params = sum(p.numel() for p in m.parameters() if p.requires_grad)
    return m, m.sr, n_params


def load_F_legacy(ckpt_path, variant_hint=None):
    try:
        from models import build as build_legacy
    except ImportError:
        return None, None, None
    ck = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    variant = variant_hint or ck.get("variant", "F")
    sd = ck.get("backbone_state") or ck.get("model")
    if variant == "F_no_sr":
        m = build_legacy("F_no_sr")
    else:
        m = build_legacy("F")
    m.load_state_dict(sd)
    m.to(DEVICE).eval()
    n_params = sum(p.numel() for p in m.parameters() if p.requires_grad)
    return m, m.sr, n_params


# ---- inference ----

def run_inference(model, codec, sr2x):
    R = codec[0::2, 0::2]; G1 = codec[0::2, 1::2]
    G2 = codec[1::2, 0::2]; B = codec[1::2, 1::2]
    pl = np.stack([R, G1, G2, B], 0).astype(np.float32) / RAW_NORM
    x = torch.from_numpy(pl).unsqueeze(0).to(DEVICE)
    H, W = x.shape[-2:]
    pad_h = (16 - H % 16) % 16
    pad_w = (16 - W % 16) % 16
    if pad_h or pad_w:
        x = F.pad(x, (0, pad_w, 0, pad_h), mode='reflect')

    with torch.no_grad():
        if sr2x:
            baseline = F.interpolate(x, scale_factor=2, mode="bicubic", align_corners=False)
            y = (baseline + RESIDUAL_SCALE * model(x)).clamp(0, 1)
            Hc, Wc = 2 * H, 2 * W
        else:
            y = (x + RESIDUAL_SCALE * model(x)).clamp(0, 1)
            Hc, Wc = H, W
    y = y[..., :Hc, :Wc]
    yn = y.squeeze(0).cpu().numpy()

    if sr2x:
        out = np.empty((2 * codec.shape[0], 2 * codec.shape[1]), dtype=np.uint16)
    else:
        out = np.empty(codec.shape, dtype=np.uint16)
    out[0::2, 0::2] = np.clip(yn[0] * RAW_NORM, 0, 16383).astype(np.uint16)
    out[0::2, 1::2] = np.clip(yn[1] * RAW_NORM, 0, 16383).astype(np.uint16)
    out[1::2, 0::2] = np.clip(yn[2] * RAW_NORM, 0, 16383).astype(np.uint16)
    out[1::2, 1::2] = np.clip(yn[3] * RAW_NORM, 0, 16383).astype(np.uint16)

    if not sr2x:
        out = bayer_bicubic_2x(out)
    return out


# ---- per-checkpoint expected gains (from clean eval_all_arch_results.json) ----
#
# Format: (ckpt_filename, legacy_hint_or_None, display_name, sr2x_expected,
#          expected_gain_db, kind)
#
# Gains are over the codec baseline (rawpy-AHD of bicubic-upscaled codec
# bayer). The brief specifies these locked numbers; we treat them as ground
# truth and assert |measured_gain - expected_gain| <= TOLERANCE_DB.
EXPECTED = [
    ("BayInBayOut_2x_AAon_w16_ANE.pt",      None, "F_ane (w=16) 2×",                     True,  5.51,  "F_ane BN+SiLU"),
    ("BayInBayOut_1x_AAon_w16_ANE.pt",      None, "F_ane_no_sr (w=16) 1×",               False, 0.91,  "F_ane BN+SiLU 1×"),
    ("BayInBayOut_1x_AAon_w16_ANE_LK7.pt",  None, "F_ane LK7 1×",                        False, 0.70,  "Large kernel 7×7, 1× output"),
    ("BayInBayOut_1x_AAon_w8_ANE_KD.pt",    None, "F_ane_w8 self-KD 1×",                 False, 0.71,  "KD self-distill 1×"),
    ("BayInBayOut_2x_AAon_w32_ANE.pt",      None, "F_ane_w32 2× (heavy)",                True,  6.23,  "F_ane wider"),
    ("BayInBayOut_2x_AAon_w8_HEAVY_KD.pt",  None, "F_ane_w8 heavy-KD 2×",                True,  3.32,  "KD heavy teacher → tiny"),
    ("BayInBayOut_2x_AAon_w16_ANE_LK7.pt",  None, "F_ane LK7 2×",                        True,  5.84,  "Large kernel 7×7"),
    ("BayInBayOut_1x_AAon_w32_ANE.pt",      None, "F_ane_w32 1× (heavy still-recovery)", False, 1.375, "Heavy 1× for still artifact recovery"),
]
EXPECTED_BASELINE_DB = 31.06  # codec baseline target


def main():
    print(f"==== test_cnn_regression: {__import__('datetime').datetime.now().isoformat(timespec='seconds')} ====")
    print(f"Device       : {DEVICE.type}")
    print(f"Tolerance    : ±{TOLERANCE_DB:.2f} dB on per-checkpoint gain")
    print()

    codec = np.fromfile(CODEC_RAW, dtype=np.uint16).reshape(2760, 4140)
    raw = rawpy.imread(REF_DNG)
    src = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=16,
                          gamma=(2.222, 4.5), output_color=rawpy.ColorSpace.sRGB,
                          demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD)
    raw.close()

    codec_8k = bayer_bicubic_2x(codec)
    codec_rgb = render_rawpy(codec_8k)
    codec_bm = brightness_match(codec_rgb, src)
    p_codec = psnr_masked(src, codec_bm)

    base_diff = p_codec - EXPECTED_BASELINE_DB
    base_status = "PASS" if abs(base_diff) <= TOLERANCE_DB else "FAIL"
    print(f"  {base_status}  {'codec baseline':40s}  measured={p_codec:6.3f} dB  "
          f"expected={EXPECTED_BASELINE_DB:5.2f}  diff={base_diff:+.3f}")

    fails = 0 if base_status == "PASS" else 1

    for fname, legacy_hint, name, sr2x_expected, expected_gain, kind in EXPECTED:
        path = os.path.join(CKPT_DIR, fname)
        if not os.path.exists(path):
            print(f"  SKIP  {name:40s}  ({fname} not present)")
            continue
        try:
            if legacy_hint is not None:
                model, sr2x, _ = load_F_legacy(path, variant_hint=legacy_hint)
                if model is None:
                    print(f"  SKIP  {name:40s}  (legacy model module not available)")
                    continue
            else:
                model, sr2x, _ = load_F_ane_or_kd(path)
            if sr2x != sr2x_expected:
                print(f"  FAIL  {name:40s}  sr mismatch (got {sr2x}, expected {sr2x_expected})")
                fails += 1
                continue
            out_bayer = run_inference(model, codec, sr2x)
            rgb = render_rawpy(out_bayer)
            measured = psnr_masked(src, brightness_match(rgb, src))
            gain = measured - p_codec
            diff = gain - expected_gain
            ok = abs(diff) <= TOLERANCE_DB
            status = "PASS" if ok else "FAIL"
            print(f"  {status}  {name:40s}  measured={measured:6.3f} dB  "
                  f"gain={gain:+.3f}  expected_gain={expected_gain:+.3f}  diff={diff:+.3f}")
            if not ok:
                fails += 1
            del model
            if DEVICE.type == "mps":
                torch.mps.empty_cache()
        except Exception as e:
            print(f"  FAIL  {name:40s}  exception: {e}")
            fails += 1

    print()
    print(f"==== {fails} failure(s) ====")
    sys.exit(fails)


if __name__ == "__main__":
    main()
