#!/usr/bin/env bash
# bench_pi_to_mac_upresable.sh — sustained Pi capture → USB transfer → Mac
# super-res-and-package UPRESABLE pipeline. Three stages timed independently,
# bottleneck identified. Output to logs + external-drive report.
#
# Stages (all on the 4 gate-image DNGs, cycled N times):
#   A. Pi encodes halfres .gpr via ml2_q3_dec2 → /mnt/ssd/work/bench_pi2mac/
#   B. rsync over USB-tethered SSH from Pi → Mac /Volumes/OWC_8TB/.../bench
#   C. Mac decodes + BIBO_2x super-res + encodes full-res .gpr
#   D. gvid_pack full-res .gpr sequence → .gvid (primary deliverable)
#   E. gpr_mov_tool pack full-res .gpr sequence → GPR1 MOV (compatibility)
#
# Per-frame DNG wrap is NOT in the perf path; it's a one-time correctness
# export and lives in upresable_pipeline.py --dng-export.
#
# End-to-end sustained throughput = min(A_fps, B_fps, C_fps).
# Latency for one frame to traverse all three stages is reported separately.
#
# Usage:
#   bash tools/test/bench_pi_to_mac_upresable.sh [N_FRAMES]
#   default N_FRAMES=120 (5 sec at 24 fps)

set -euo pipefail

N="${1:-120}"
PI="${PI:-gpr-pi}"
SRC_DNGS=(Z8Z_0001.dng Z8Z_0067.dng Z8Z_5323.dng Z8Z_6693.dng)

GPR_ROOT="${GPR_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
GPR_EXTERNAL_ROOT="${GPR_EXTERNAL_ROOT:-/Volumes/OWC_8TB/gpr_work}"
GPR_ARTIFACT_ROOT="${GPR_ARTIFACT_ROOT:-$GPR_EXTERNAL_ROOT/artifacts}"
GPR_MODEL_ROOT="${GPR_MODEL_ROOT:-$GPR_EXTERNAL_ROOT/models}"
TMPDIR="${TMPDIR:-$GPR_EXTERNAL_ROOT/tmp}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

MAC_OUT="${MAC_OUT:-$GPR_ARTIFACT_ROOT/upresable/pi_mac_bench}"
PI_OUT="${PI_OUT:-/mnt/ssd/work/bench_pi2mac}"
LOG=$MAC_OUT/run.log
REPORT="${REPORT:-$TMPDIR/pi_mac_bench_report.txt}"

mkdir -p "$MAC_OUT" "$TMPDIR"
rm -f "$LOG"
exec > >(tee -a "$LOG") 2>&1

echo "=== bench_pi_to_mac_upresable — $N frames ==="
echo "  Pi:        $PI"
echo "  Pi out:    $PI_OUT"
echo "  Mac out:   $MAC_OUT"
echo "  source:    cycling ${#SRC_DNGS[@]} DNGs (${SRC_DNGS[*]})"
echo

# --- Stage A: prep raws on Mac → push to Pi → encode in a loop ---
echo "--- Stage A.0: extract bayer planes on Mac (one-time) ---"
RAW_DIR=$MAC_OUT/raws
mkdir -p "$RAW_DIR"
for name in Z8Z_0001 Z8Z_0067 Z8Z_5323 Z8Z_6693; do
  if [ ! -f "$RAW_DIR/$name.raw" ]; then
    DNG="$GPR_EXTERNAL_ROOT/barnsky_full_dngs/$name.dng"
    [ -f "$DNG" ] || DNG="$GPR_ARTIFACT_ROOT/visual_compare_20260525/source_dngs/$name.dng"
    DNG_PATH="$DNG" RAW_PATH="$RAW_DIR/$name.raw" \
    "$PYTHON_BIN" -c "
import os, tifffile, numpy as np
with tifffile.TiffFile(os.environ['DNG_PATH']) as tf:
    bayer = None
    for p in tf.pages:
        for sp in (p.pages or []):
            if len(sp.shape) == 2 and sp.shape[0] > 1000:
                bayer = sp.asarray().astype('<u2'); break
        if bayer is not None: break
bayer.tofile(os.environ['RAW_PATH'])
print(f'wrote {os.environ[\"RAW_PATH\"]} shape={bayer.shape}')
"
  fi
done
echo "  raws ready: $(ls $RAW_DIR/*.raw | wc -l) files"

echo "--- Stage A.1: push raws to Pi (one-time) ---"
ssh "$PI" "mkdir -p /mnt/ssd/work/raws"
rsync -a "$RAW_DIR/" "$PI:/mnt/ssd/work/raws/"

echo "--- Stage A.2: Pi encode loop (ml2_q3_dec2) ---"
ssh "$PI" "rm -rf $PI_OUT && mkdir -p $PI_OUT"
A_T0=$(date +%s.%N)
ssh "$PI" "bash -s" <<PIEOF
set -euo pipefail
BIN=/mnt/ssd/work/gpr/build/bin/test_fused_roundtrip
SRC=(Z8Z_0001 Z8Z_0067 Z8Z_5323 Z8Z_6693)
T_PI_START=\$(date +%s.%N)
for i in \$(seq 0 \$(( $N - 1 ))); do
  idx=\$(( i % 4 ))
  name=\${SRC[\$idx]}
  out=$PI_OUT/frame_\$(printf "%05d" \$i).gpr
  GPR_INCLUDE_LL=1 FUSED_MULTI_LEVEL=1 FUSED_WAVELET_LEVELS=2 \
    GPR_COL_DECIMATE=2 GPR_ROW_DECIMATE=2 FUSED_QUALITY=3 \
    GPR_SAVE_ENC_TO=\$out GPR_SKIP_DECODE=1 \
    \$BIN /mnt/ssd/work/raws/\${name}.raw 8280 5520 >/dev/null 2>&1 || \
      { echo "Pi encode failed on \$i (\$name)"; exit 1; }
done
T_PI_END=\$(date +%s.%N)
T_PI=\$(awk "BEGIN {print \$T_PI_END - \$T_PI_START}")
echo "PI_ENCODE_TIME_SEC=\$T_PI"
echo "PI_FRAME_COUNT=$N"
du -sb $PI_OUT | awk '{print "PI_TOTAL_BYTES="\$1}'
PIEOF
A_T1=$(date +%s.%N)
A_DUR=$(echo "$A_T1 - $A_T0" | bc -l)
A_FPS=$(echo "$N / $A_DUR" | bc -l)
echo "  Stage A: ${A_DUR}s for $N frames → $(printf '%.2f' $A_FPS) fps (incl. SSH overhead)"
echo

# --- Stage B: rsync ---
echo "--- Stage B: rsync Pi → Mac ---"
B_T0=$(date +%s.%N)
rsync -a --info=stats2 "$PI:$PI_OUT/" "$MAC_OUT/halfres_gpr/" > "$TMPDIR/rsync_stats.txt"
B_T1=$(date +%s.%N)
B_DUR=$(echo "$B_T1 - $B_T0" | bc -l)
B_FPS=$(echo "$N / $B_DUR" | bc -l)
TOTAL_BYTES=$(du -sk "$MAC_OUT/halfres_gpr/" | awk '{print $1}')
MBS=$(echo "scale=2; $TOTAL_BYTES / 1024 / $B_DUR" | bc -l)
echo "  Stage B: ${B_DUR}s for $N frames ($((TOTAL_BYTES/1024)) MB) → $(printf '%.2f' $B_FPS) fps, ${MBS} MB/s"
echo

# --- Stage C: Mac upresable processing ---
echo "--- Stage C: Mac BIBO_2x + DNG wrap + .gpr encode ---"
# Move the rsynced GPRs into a structure upresable_pipeline.py expects,
# then run in a one-off mode that processes existing GPRs (we don't have
# a CLI flag for that yet, so we use a small inline Python harness).
C_T0=$(date +%s.%N)
PYTHONPATH="$GPR_ROOT/tools/cnn" \
"$PYTHON_BIN" - <<PYEOF
import sys, time, os, subprocess
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, '$GPR_ROOT/tools/cnn')
import importlib.util
spec = importlib.util.spec_from_file_location("up", "$GPR_ROOT/tools/cnn/upresable_pipeline.py")
up = importlib.util.module_from_spec(spec); spec.loader.exec_module(up)

GPRS = sorted(Path("$MAC_OUT/halfres_gpr").glob("*.gpr"))
print(f"  found {len(GPRS)} halfres GPRs to process", flush=True)

device = torch.device('mps')
ckpt = os.environ.get(
    'GPR_BIBO2X_CKPT',
    '$GPR_MODEL_ROOT/BayInBayOut_2x_AAon_w16_ANE_ML2_q3_dec2_diverse.pt')
ck = torch.load(ckpt, map_location='cpu', weights_only=False)
from model import build
variant = ck.get('variant', 'F_ane')
m = build(variant).to(device)
state = ck['backbone_state'] if 'backbone_state' in ck else (ck['model'] if 'model' in ck else ck)
m.load_state_dict(state, strict=True)
m.eval()

OUT = Path("$MAC_OUT/processed"); OUT.mkdir(exist_ok=True)
work = Path("$MAC_OUT/work"); work.mkdir(exist_ok=True)
fullres_dir = OUT / "fullres"; fullres_dir.mkdir(exist_ok=True)

src_names = ['Z8Z_0001','Z8Z_0067','Z8Z_5323','Z8Z_6693']

def read_fused_gpr_to_bayer(gpr_path):
    raw_out = work / (gpr_path.stem + ".raw")
    cmd = ['$GPR_ROOT/build-local/bin/fused_decode_cli',
           str(gpr_path), '8280', '5520', str(raw_out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f'fused_decode_cli failed: {r.stderr[-200:]}')
    nbytes = raw_out.stat().st_size
    for w, h in ((4140, 2760), (8280, 5520)):
        if nbytes == w * h * 2:
            arr = np.fromfile(raw_out, dtype=np.uint16).reshape(h, w)
            return arr
    raise RuntimeError(f'unexpected raw size {nbytes}')

def encode_fullres_gpr(bayer_full, out_path, idx):
    """Bayer → FUSED .gpr (full-res). Uses test_fused_roundtrip with
    GPR_SAVE_ENC_TO + GPR_SKIP_DECODE so we get just the encoded bitstream."""
    raw_in = work / f"full_in_{idx}.raw"
    bayer_full.tofile(raw_in)
    bin_path = '$GPR_ROOT/build-local/bin/test_fused_roundtrip'
    env = os.environ.copy()
    env.update({
        'GPR_INCLUDE_LL': '1', 'FUSED_MULTI_LEVEL': '1',
        'FUSED_WAVELET_LEVELS': '2', 'FUSED_QUALITY': '3',
        'GPR_SAVE_ENC_TO': str(out_path), 'GPR_SKIP_DECODE': '1',
    })
    r = subprocess.run([bin_path, str(raw_in), str(bayer_full.shape[1]),
                       str(bayer_full.shape[0])], env=env, capture_output=True)
    raw_in.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f'full-res encode failed: {r.stderr[-200:]}')

n = len(GPRS)
t0 = time.time()
cnn_ms = []
encode_ms = []
total_ms = []
for i, gpr in enumerate(GPRS):
    t_frame = time.time()
    half_bayer = read_fused_gpr_to_bayer(gpr)
    t_cnn0 = time.time()
    full_bayer = up.run_bibo2x_mps(m, half_bayer, device, res_scale=0.01)
    cnn_ms.append((time.time() - t_cnn0) * 1000.0)
    t_enc0 = time.time()
    encode_fullres_gpr(full_bayer, fullres_dir / f"frame_{i:05d}.gpr", i)
    encode_ms.append((time.time() - t_enc0) * 1000.0)
    total_ms.append((time.time() - t_frame) * 1000.0)
    if (i + 1) % 10 == 0 or i + 1 == n:
        rate = (i + 1) / (time.time() - t0)
        print(f"    {i+1}/{n}  rate={rate:.2f} f/s  cnn_med={np.median(cnn_ms):.0f}ms "
              f"enc_med={np.median(encode_ms):.0f}ms", flush=True)

elapsed = time.time() - t0
fps = n / elapsed
print(f"MAC_PROCESS_SEC={elapsed:.2f}")
print(f"MAC_FPS={fps:.3f}")
print(f"MAC_CNN_MS_MEDIAN={float(np.median(cnn_ms)):.1f}")
print(f"MAC_DECODE_PLUS_CNN_MS_MEDIAN={float(np.median(total_ms)):.1f}")
PYEOF
C_T1=$(date +%s.%N)
C_DUR=$(echo "$C_T1 - $C_T0" | bc -l)
C_FPS=$(echo "$N / $C_DUR" | bc -l)
echo "  Stage C: ${C_DUR}s for $N frames → $(printf '%.2f' $C_FPS) fps"
echo

# --- Stage D: pack primary .gvid ---
echo "--- Stage D: pack full-res .gpr → .gvid ---"
GVID=$MAC_OUT/processed/upresable.gvid
D_T0=$(date +%s.%N)
"$PYTHON_BIN" "$GPR_ROOT/tools/gvid_pack.py" \
  "$MAC_OUT/processed/fullres" "$GVID" \
  --width 8280 --height 5520 --fps 24 --quality 3 --pixel-format 4
D_T1=$(date +%s.%N)
D_DUR=$(echo "$D_T1 - $D_T0" | bc -l)
D_FPS=$(echo "$N / $D_DUR" | bc -l)
GVID_MB=$(ls -la "$GVID" | awk '{print $5 / 1024 / 1024}')
echo "  Stage D: ${D_DUR}s for $N frames → $(printf '%.2f' $D_FPS) fps  (.gvid size: $(printf '%.1f' $GVID_MB) MB)"
echo

# --- Stage E: pack MOV compatibility wrapper ---
echo "--- Stage E: pack full-res .gpr → GPR1 MOV compatibility wrapper ---"
MOV_COMPAT=$MAC_OUT/processed/upresable.gpr1.mov
E_T0=$(date +%s.%N)
"$GPR_ROOT/tools/gpr2prores/gpr_mov_tool" pack \
  "$MAC_OUT/processed/fullres" "$MOV_COMPAT" --fps 24 2>&1 | tail -2
E_T1=$(date +%s.%N)
E_DUR=$(echo "$E_T1 - $E_T0" | bc -l)
E_FPS=$(echo "$N / $E_DUR" | bc -l)
MOV_MB=$(ls -la "$MOV_COMPAT" | awk '{print $5 / 1024 / 1024}')
echo "  Stage E: ${E_DUR}s for $N frames → $(printf '%.2f' $E_FPS) fps  (MOV wrapper size: $(printf '%.1f' $MOV_MB) MB)"
echo

# --- Report ---
echo "=== Report ==="
{
  echo "bench_pi_to_mac_upresable — $(date)"
  echo "frames: $N"
  echo "deliverable: .gvid ($(printf '%.1f' $GVID_MB) MB)"
  echo "compatibility: GPR1 MOV ($(printf '%.1f' $MOV_MB) MB)"
  echo ""
  printf "%-40s %12s %12s %12s\n" "stage" "duration_s" "fps" "MB/s"
  printf "%-40s %12s %12s %12s\n" "----" "----------" "---" "----"
  printf "%-40s %12.2f %12.2f %12s\n" "A. Pi encode (ml2_q3_dec2)" "$A_DUR" "$A_FPS" "-"
  printf "%-40s %12.2f %12.2f %12.2f\n" "B. rsync Pi → Mac (USB)" "$B_DUR" "$B_FPS" "$MBS"
  printf "%-40s %12.2f %12.2f %12s\n" "C. Mac decode + BIBO_2x + encode" "$C_DUR" "$C_FPS" "-"
  printf "%-40s %12.2f %12.2f %12s\n" "D. gvid_pack → .gvid" "$D_DUR" "$D_FPS" "-"
  printf "%-40s %12.2f %12.2f %12s\n" "E. gpr_mov_tool pack → GPR1 MOV" "$E_DUR" "$E_FPS" "-"
  echo ""
  printf "Bottleneck: "
  python3 -c "
fps = [$A_FPS, $B_FPS, $C_FPS, $D_FPS]
stages = ['A: Pi encode', 'B: USB rsync', 'C: Mac decode+CNN+encode', 'D: .gvid pack']
m = min(fps); i = fps.index(m)
print(f'{stages[i]} at {m:.2f} fps')
print(f'Primary .gvid sustained throughput = min(A,B,C,D) = {m:.2f} fps')
print(f'MOV compatibility pack = {float("$E_FPS"):.2f} fps')
"
} | tee "$REPORT"
echo
echo "Full log: $LOG"
echo "Report:   $REPORT"
