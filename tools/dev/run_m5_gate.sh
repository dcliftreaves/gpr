#!/usr/bin/env bash
# Run a frozen quality gate on the M5 using copied source DNGs.
#
# This keeps the local workstation out of the heavy path. The gate still uses
# tests/quality_gates/test_set.json; only source DNG paths are remapped at
# runtime so crop positions, metric dimensions, thresholds, and run identity
# stay tied to the frozen manifest.
#
# Required M5 layout:
#   $M5_GPR_REPO          clean or staged repo checkout
#   $M5_GATE_DNG_DIR      contains Z8Z_0001.dng, Z8Z_0067.dng, Z8Z_5323.dng, Z8Z_6693.dng
#   $M5_GATE_TMPDIR       scratch directory on the M5 data volume
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 PIPELINE [run_gate.py args...]" >&2
  exit 3
fi

M5_HOST="${M5_HOST:-gpr-m5}"
M5_GPR_REPO="${M5_GPR_REPO:-/Users/dcliftreaves/gpr_codex_gate}"
M5_GATE_DNG_DIR="${M5_GATE_DNG_DIR:-/Users/dcliftreaves/gpr_data/gate_dngs}"
M5_GATE_TMPDIR="${M5_GATE_TMPDIR:-/Users/dcliftreaves/gpr_data/gate_tmp}"
GATE_MAX_WORKERS="${GATE_MAX_WORKERS:-1}"
GATE_MIN_FREE_GB="${GATE_MIN_FREE_GB:-25}"
GATE_KEEP_FULLRES="${GATE_KEEP_FULLRES:-0}"

SOURCE_MAP="/Volumes/OWC_8TB/gpr_work/artifacts/visual_compare_20260525/source_dngs=$M5_GATE_DNG_DIR;/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs=$M5_GATE_DNG_DIR"

printf 'M5 gate target:\n' >&2
printf '  host=%s\n  repo=%s\n  dngs=%s\n  tmp=%s\n  workers=%s\n' \
  "$M5_HOST" "$M5_GPR_REPO" "$M5_GATE_DNG_DIR" "$M5_GATE_TMPDIR" "$GATE_MAX_WORKERS" >&2

quoted_args=()
for arg in "$@"; do
  quoted_args+=("$(printf '%q' "$arg")")
done

ssh "$M5_HOST" "
  set -e
  cd $(printf '%q' "$M5_GPR_REPO")
  mkdir -p $(printf '%q' "$M5_GATE_TMPDIR")
  GATE_SOURCE_PATH_MAP=$(printf '%q' "$SOURCE_MAP") \
  GATE_TMPDIR=$(printf '%q' "$M5_GATE_TMPDIR") \
  GATE_MAX_WORKERS=$(printf '%q' "$GATE_MAX_WORKERS") \
  GATE_MIN_FREE_GB=$(printf '%q' "$GATE_MIN_FREE_GB") \
  GATE_KEEP_FULLRES=$(printf '%q' "$GATE_KEEP_FULLRES") \
  python3 tests/quality_gates/run_gate.py ${quoted_args[*]}
"
