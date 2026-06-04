#!/usr/bin/env bash
# Route large local scratch for GPR development to the external drive.
#
# Usage:
#   source tools/dev/external_drive_env.sh
#   tools/dev/external_drive_env.sh python3 tests/quality_gates/run_gate.py ...
#
# Keep the repo for source, registry metadata, and committed run.json receipts.
# Put temp files, model checkpoints, Python/Torch caches, and gate scratch on
# /Volumes/OWC_8TB by default.
set -euo pipefail

ROOT="${GPR_EXTERNAL_ROOT:-/Volumes/OWC_8TB/gpr_work}"

mkdir -p \
  "$ROOT/tmp" \
  "$ROOT/gate_tmp" \
  "$ROOT/checkpoints" \
  "$ROOT/pycache" \
  "$ROOT/torch" \
  "$ROOT/xdg_cache" \
  "$ROOT/matplotlib" \
  /Volumes/OWC_8TB/gpr_work/cnn \
  /Volumes/OWC_8TB/gpr_work/artifacts

export GPR_EXTERNAL_ROOT="$ROOT"
export GPR_CNN_ROOT="${GPR_CNN_ROOT:-/Volumes/OWC_8TB/gpr_work/cnn}"
export GPR_ARTIFACT_ROOT="${GPR_ARTIFACT_ROOT:-/Volumes/OWC_8TB/gpr_work/artifacts}"

# tempfile uses TMPDIR; run_gate.py also honors GATE_TMPDIR explicitly.
export TMPDIR="$ROOT/tmp/"
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
export GATE_TMPDIR="$ROOT/gate_tmp"
export GATE_KEEP_FULLRES="${GATE_KEEP_FULLRES:-0}"

# Training/checkpoint defaults. Override CKPT_DIR per command when the final
# artifact must land in repo-local models/ for registration.
export CKPT_DIR="${CKPT_DIR:-$ROOT/checkpoints}"

# Keep language/runtime caches off the internal disk.
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$ROOT/pycache}"
export TORCH_HOME="${TORCH_HOME:-$ROOT/torch}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$ROOT/xdg_cache}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$ROOT/matplotlib}"

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

cat <<EOF
External-drive GPR environment active:
  GPR_EXTERNAL_ROOT=$GPR_EXTERNAL_ROOT
  TMPDIR=$TMPDIR
  GATE_TMPDIR=$GATE_TMPDIR
  CKPT_DIR=$CKPT_DIR
  GPR_CNN_ROOT=$GPR_CNN_ROOT
  GPR_ARTIFACT_ROOT=$GPR_ARTIFACT_ROOT
EOF
