#!/bin/bash
# post_w32_1x_pipeline.sh — run after F_ane_w32_no_sr (heavy still-recovery)
# training completes on M5.
#
# Pulls the checkpoint, extracts BN-folded Metal weights, runs eval_all_arch.py
# for the rendered Y-PSNR number, and writes a summary to /tmp/w32_1x_results.txt.
#
# Notes:
#   - F_ane_w32 has width=32; SuperResMetal's loader currently hardcodes
#     width=16, so we can't yet run this through gpr2prores. Eval is via
#     the PyTorch path only (which works for any width).
#   - Compare against F_ane (w=16) 1× = +0.91 dB rendered.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
RESULT_FILE=/tmp/w32_1x_results.txt
CKPT_NAME=BayInBayOut_1x_AAon_w32_ANE.pt
M5_CKPT=/Users/dcliftreaves/dering_proto_v2/checkpoints/$CKPT_NAME
LOCAL_CKPT=/Users/dcliftreaves/dering_proto_v2/checkpoints/$CKPT_NAME
WEIGHTS_DIR=/tmp/F_ane_w32_1x_weights
PY=/Users/dcliftreaves/anaconda3/envs/py3_10/bin/python3

echo "post_w32_1x_pipeline starting: $(date)" | tee $RESULT_FILE
echo "================================================" | tee -a $RESULT_FILE

echo "" | tee -a $RESULT_FILE
echo "[1/4] copying checkpoint from M5 ..." | tee -a $RESULT_FILE
scp gpr-m5:$M5_CKPT $LOCAL_CKPT 2>&1 | tail -3 | tee -a $RESULT_FILE
ls -l $LOCAL_CKPT | tee -a $RESULT_FILE

echo "" | tee -a $RESULT_FILE
echo "[2/4] training log tail (last best, final epoch) ..." | tee -a $RESULT_FILE
ssh gpr-m5 'grep -E "SAVED|ep  80/80|early stop|best" /tmp/train_F_ane_w32_1x.log | tail -10' | tee -a $RESULT_FILE

echo "" | tee -a $RESULT_FILE
echo "[3/4] extract BN-folded Metal weights ..." | tee -a $RESULT_FILE
cd $HERE
$PY extract_F_ane_weights.py --ckpt $LOCAL_CKPT --out $WEIGHTS_DIR --dw-kernel 3 2>&1 | tail -5 | tee -a $RESULT_FILE

echo "" | tee -a $RESULT_FILE
echo "[4/4] PyTorch rendered Y-PSNR via eval_all_arch.py ..." | tee -a $RESULT_FILE

# Add the w32 1× entry to eval_all_arch.py if not already there
$PY <<'PYEOF' | tee -a $RESULT_FILE
import os, sys
eval_script = "/Users/dcliftreaves/dering_proto_v2/eval_all_arch.py"
with open(eval_script) as f:
    contents = f.read()
if "BayInBayOut_1x_AAon_w32_ANE.pt" not in contents:
    print("Adding F_ane_w32 1× entry to eval_all_arch.py …")
    contents = contents.replace(
        '("BayInBayOut_2x_AAon_w32_ANE.pt", None, "F_ane_w32 (heavy)", "F_ane wider (BN+SiLU)", True),',
        '("BayInBayOut_2x_AAon_w32_ANE.pt", None, "F_ane_w32 (heavy)", "F_ane wider (BN+SiLU)", True),\n        ("BayInBayOut_1x_AAon_w32_ANE.pt", None, "F_ane_w32 1× (heavy still-recovery)", "Heavy 1× for still artifact recovery", False),'
    )
    with open(eval_script, "w") as f:
        f.write(contents)
    print("  patched.")
else:
    print("Already present in eval_all_arch.py.")
PYEOF

KMP_DUPLICATE_LIB_OK=TRUE $PY /Users/dcliftreaves/dering_proto_v2/eval_all_arch.py 2>&1 | \
    grep -E "F_ane_w32 1×|F_ane_w32 \(|F_ane \(w=16|F_ane_no_sr|codec baseline|F_ane LK7 1×" | tee -a $RESULT_FILE

echo "" | tee -a $RESULT_FILE
echo "================================================" | tee -a $RESULT_FILE
echo "post_w32_1x_pipeline done: $(date)" | tee -a $RESULT_FILE
echo ""
echo "==== KEY NUMBERS ===="
echo "Compare F_ane_w32 1× to F_ane_no_sr (w=16) 1× = +0.91 dB rendered"
echo "Higher gain means heavy model recovers more compressed detail in still-image mode"
