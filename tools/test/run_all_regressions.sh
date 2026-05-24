#!/usr/bin/env bash
# tools/test/run_all_regressions.sh
#
# Combined entry point for the GPR regression test corpus.
#   1. Legacy 5-case quality corpus  (source/app/test_still_quality_corpus.sh)
#   2. New 15-case quality matrix    (tools/test/test_still_matrix.sh)
#   3. CNN gain regression           (tools/test/test_cnn_regression.py)        — macOS dev box (auto-skips on Linux / missing deps)
#   4. Video pipeline matrix         (tools/test/test_video_pipeline.sh)        — macOS only
#
# Exits 0 iff every step that actually ran passed. Steps that gracefully
# skip (Linux for the macOS-only steps, dev-box-only deps for CNN) are
# treated as PASS for aggregate purposes.
#
# Flags:
#   --fast              (skip the largest-resolution cells in matrix tests)
#   --skip-cnn          (don't run the CNN regression even on macOS dev box)
#   --skip-video        (don't run the video pipeline matrix)
#   --skip-legacy       (don't run the legacy corpus — use when matrix already covers it)
#
# Env knobs are forwarded as-is to children:
#   BUILD_DIR=build-local
#   GTOOLS=...
#   GPR2PRORES=...

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

FAST=0
SKIP_CNN=0
SKIP_VIDEO=0
SKIP_LEGACY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --fast)        FAST=1 ;;
        --skip-cnn)    SKIP_CNN=1 ;;
        --skip-video)  SKIP_VIDEO=1 ;;
        --skip-legacy) SKIP_LEGACY=1 ;;
        -h|--help)
            cat <<EOF
Usage: $0 [--fast] [--skip-cnn] [--skip-video] [--skip-legacy]

  --fast         Skip the largest-resolution cells in the still matrix and
                 the 4k/6k/8k cells in the video pipeline matrix.
  --skip-cnn     Skip the CNN regression (auto-skipped on Linux anyway).
  --skip-video   Skip the gpr2prores video pipeline matrix (macOS-only).
  --skip-legacy  Skip the legacy 5-case still corpus.

Env knobs forwarded to children:
  BUILD_DIR      (default: build)
  GTOOLS         (override gpr_tools path)
  GPR2PRORES     (override gpr2prores path)
EOF
            exit 0 ;;
        *)
            echo "unknown flag: $1" >&2; exit 2 ;;
    esac
    shift
done

export FAST

# Status accumulators.
PASS_STEPS=()
FAIL_STEPS=()
SKIP_STEPS=()

run_step() {
    local label="$1"; shift
    echo
    echo "============================================================"
    echo " $label"
    echo "============================================================"
    "$@"
    local rc=$?
    if [ $rc -eq 0 ]; then
        PASS_STEPS+=("$label")
    else
        FAIL_STEPS+=("$label (exit $rc)")
    fi
}

# 1. Legacy 5-case quality corpus.
if [ "$SKIP_LEGACY" == "1" ]; then
    SKIP_STEPS+=("legacy still-quality corpus")
else
    if [ -x "$REPO_ROOT/source/app/test_still_quality_corpus.sh" ]; then
        run_step "legacy still-quality corpus (5 cases)" \
            "$REPO_ROOT/source/app/test_still_quality_corpus.sh"
    else
        SKIP_STEPS+=("legacy still-quality corpus (script not present)")
    fi
fi

# 2. 15-case quality matrix.
run_step "still matrix (15 cases)" \
    "$REPO_ROOT/tools/test/test_still_matrix.sh"

# 3. CNN regression — auto-skips when deps/checkpoints missing.
if [ "$SKIP_CNN" == "1" ]; then
    SKIP_STEPS+=("CNN regression")
else
    if command -v python3 >/dev/null 2>&1; then
        run_step "CNN regression (9 checkpoints)" \
            python3 "$REPO_ROOT/tools/test/test_cnn_regression.py"
    else
        SKIP_STEPS+=("CNN regression (no python3)")
    fi
fi

# 4. Video pipeline matrix — auto-skips on non-Darwin.
if [ "$SKIP_VIDEO" == "1" ]; then
    SKIP_STEPS+=("video pipeline matrix")
else
    run_step "video pipeline matrix (3 CNN × N res × 2 demosaic)" \
        "$REPO_ROOT/tools/test/test_video_pipeline.sh"
fi

# ---- Summary --------------------------------------------------------------
echo
echo "============================================================"
echo " run_all_regressions: summary"
echo "============================================================"
for s in "${PASS_STEPS[@]:-}";  do [ -n "$s" ] && echo "  PASS  $s"; done
for s in "${SKIP_STEPS[@]:-}";  do [ -n "$s" ] && echo "  SKIP  $s"; done
for s in "${FAIL_STEPS[@]:-}";  do [ -n "$s" ] && echo "  FAIL  $s"; done

if [ "${#FAIL_STEPS[@]}" -gt 0 ]; then
    echo
    echo "==== ${#FAIL_STEPS[@]} step(s) FAILED ===="
    exit 1
fi
echo
echo "==== all ran-steps passed (${#PASS_STEPS[@]} pass / ${#SKIP_STEPS[@]} skip) ===="
exit 0
