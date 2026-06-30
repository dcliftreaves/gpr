#!/usr/bin/env bash
# tools/test/run_all_regressions.sh
#
# Combined entry point for the GPR regression test corpus.
#   1. Legacy 5-case quality corpus  (source/app/test_still_quality_corpus.sh)
#   2. New 15-case quality matrix    (tools/test/test_still_matrix.sh)
#   3. CNN gain regression           (tools/test/test_cnn_regression.py)        — macOS dev box (auto-skips on Linux / missing deps)
#   4. Video pipeline matrix         (tools/test/test_video_pipeline.sh)        — macOS only
#   5. CI-safe release/readiness guards
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
#   --skip-release      (don't run CI-safe release/readiness guards)
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
SKIP_RELEASE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --fast)        FAST=1 ;;
        --skip-cnn)    SKIP_CNN=1 ;;
        --skip-video)  SKIP_VIDEO=1 ;;
        --skip-legacy) SKIP_LEGACY=1 ;;
        --skip-release) SKIP_RELEASE=1 ;;
        -h|--help)
            cat <<EOF
Usage: $0 [--fast] [--skip-cnn] [--skip-video] [--skip-legacy] [--skip-release]

  --fast         Skip the largest-resolution cells in the still matrix and
                 the 4k/6k/8k cells in the video pipeline matrix.
  --skip-cnn     Skip the CNN regression (auto-skipped on Linux anyway).
  --skip-video   Skip the gpr2prores video pipeline matrix (macOS-only).
  --skip-legacy  Skip the legacy 5-case still corpus.
  --skip-release Skip CI-safe release/readiness guards.

Env knobs forwarded to children:
  BUILD_DIR      (default: build, auto-falls back to build-local when present)
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

if [ -z "${BUILD_DIR:-}" ]; then
    if [ -x "$REPO_ROOT/build/source/app/gpr_tools/gpr_tools" ]; then
        export BUILD_DIR="$REPO_ROOT/build"
    elif [ -x "$REPO_ROOT/build-local/source/app/gpr_tools/gpr_tools" ]; then
        export BUILD_DIR="$REPO_ROOT/build-local"
    else
        export BUILD_DIR="build"
    fi
fi

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

python_has_modules() {
    python3 - "$@" <<'PY' >/dev/null 2>&1
import importlib.util
import sys
missing = [name for name in sys.argv[1:] if importlib.util.find_spec(name) is None]
sys.exit(1 if missing else 0)
PY
}

# 1. Legacy 5-case quality corpus.
if [ "$SKIP_LEGACY" == "1" ]; then
    SKIP_STEPS+=("legacy still-quality corpus")
else
    if ! python_has_modules numpy rawpy; then
        SKIP_STEPS+=("legacy still-quality corpus (missing numpy/rawpy)")
    elif [ -x "$REPO_ROOT/source/app/test_still_quality_corpus.sh" ]; then
        run_step "legacy still-quality corpus (5 cases)" \
            "$REPO_ROOT/source/app/test_still_quality_corpus.sh"
    else
        SKIP_STEPS+=("legacy still-quality corpus (script not present)")
    fi
fi

# 2. 15-case quality matrix.
if ! python_has_modules numpy rawpy; then
    SKIP_STEPS+=("still matrix (missing numpy/rawpy)")
else
    run_step "still matrix (15 cases)" \
        "$REPO_ROOT/tools/test/test_still_matrix.sh"
fi

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
elif ! python_has_modules numpy; then
    SKIP_STEPS+=("video pipeline matrix (missing numpy)")
else
    run_step "video pipeline matrix (3 CNN × N res × 2 demosaic)" \
        "$REPO_ROOT/tools/test/test_video_pipeline.sh"
fi

# 5. CI-safe release/readiness guards.
if [ "$SKIP_RELEASE" == "1" ]; then
    SKIP_STEPS+=("release/readiness guards")
else
    if command -v python3 >/dev/null 2>&1; then
        run_step "release/readiness guards" \
            bash -c "cd '$REPO_ROOT' && \
                python3 tools/test/check_sensitive_content.py && \
                python3 tools/test/check_repo_artifact_hygiene.py && \
                python3 tools/test/check_readme_media.py && \
                python3 tools/test/test_check_readme_media.py && \
                python3 tools/test/check_readme_product_pillars.py && \
                python3 tools/test/test_check_readme_product_pillars.py && \
                python3 tools/test/check_high_level_goal_contract.py && \
                python3 tools/test/test_check_high_level_goal_contract.py && \
                python3 tools/test/test_product_pillar_receipts.py && \
                python3 tools/test/test_build_camera_noise_calibration.py && \
                python3 tools/test/test_convert_darkframe_calibration_to_noise_sidecars.py && \
                python3 tools/test/test_build_camera_noise_coverage_audit.py && \
                python3 tools/test/test_build_darkframe_candidate_audit.py && \
                python3 tools/test/test_build_bayer_phase_fixture_inventory.py && \
                python3 tools/test/test_build_stills_fixture_gap_plan.py && \
                python3 tools/test/test_extract_raw_bayer_u16.py && \
                python3 tools/test/test_build_stills_capture_request.py && \
                python3 tools/test/test_build_premium_still_sr_gate_receipt.py && \
                python3 tools/test/test_build_premium_still_sr_readiness.py && \
                python3 tools/test/test_build_100mp_still_visual_audit.py && \
                python3 tools/test/test_build_premium_still_sr_fixture_manifest.py && \
                python3 tools/test/test_build_premium_still_sr_pairs.py && \
                python3 tools/test/test_build_premium_still_sr_candidate_dashboard.py && \
                python3 tools/test/test_build_premium_still_sr_visual_review.py && \
                python3 tools/test/test_build_premium_still_sr_router_plan.py && \
                python3 tools/test/test_build_premium_still_sr_degraded_candidate_raw.py && \
                python3 tools/test/test_build_premium_still_sr_hf_residual_targets.py && \
                python3 tools/test/test_audit_premium_still_sr_noise_clean_sweep.py && \
                python3 tools/test/test_audit_premium_still_sr_raw_cfa_residual.py && \
                python3 tools/test/test_build_premium_still_sr_raw_cfa_residual_targets.py && \
                python3 tools/test/test_train_premium_still_sr_raw_cfa_residual.py && \
                python3 tools/test/test_merge_premium_still_sr_hf_residual_targets.py && \
                python3 tools/test/test_analyze_premium_still_sr_hf_residual_bands.py && \
                python3 tools/test/test_train_premium_still_sr_hf_residual.py && \
                python3 tools/test/test_build_premium_still_sr_experiment_scoreboard.py && \
                python3 tools/test/test_build_premium_still_sr_blocker_audit.py && \
                python3 tools/test/test_build_premium_still_sr_target_expansion_plan.py && \
                python3 tools/test/test_build_premium_still_sr_expanded_hf_targets_from_plan.py && \
                python3 tools/test/test_build_bayer_resize_psf_receipt.py && \
                python3 tools/test/test_build_bayer_resize_psf_from_pairs.py && \
                python3 tools/test/test_build_mission1_native_psf_pair_inventory.py && \
                python3 tools/test/test_build_mission1_native_psf_measurement_plan.py && \
                python3 tools/test/test_build_mission1_native_psf_measurement.py && \
                python3 tools/test/test_build_raw_video_sr_candidate_scoreboard.py && \
                python3 tools/test/test_build_raw_video_psf_audit.py && \
                python3 tools/test/test_build_raw_video_psf_gap_plan.py && \
                python3 tools/test/test_build_raw_video_psf_capture_request.py && \
                python3 tools/test/test_build_product_pillar_scorecard.py && \
                python3 tools/test/test_build_product_burndown.py && \
                python3 tools/test/check_product_burndown_contract.py && \
                python3 tools/test/test_check_product_burndown_contract.py && \
                python3 tools/test/check_product_lock_ledger.py && \
                python3 tools/test/test_check_product_lock_ledger.py && \
                python3 tools/test/check_release_evidence_manifest.py && \
                python3 tools/test/check_labs_readiness.py && \
                python3 tools/test/test_mission1_numbered_list_readiness.py && \
                python3 tools/test/test_mission1_numbered_list_closure_plan.py && \
                python3 tools/test/test_mission1_8k_sr_production_promotion.py && \
                python3 tools/test/test_build_mission1_8k_sr_visual_review.py && \
                python3 tools/test/test_build_cnn_product_scorecard.py && \
                python3 tools/test/test_mission1_camera_dispatch_inputs.py && \
                python3 tools/test/test_mission1_camera_closure_package.py && \
                python3 tools/test/test_mission1_camera_hardware_audit.py && \
                python3 tools/test/test_mission1_camera_source_probe.py && \
                python3 tools/test/test_run_gopro_mission1_quick_validation.py && \
                python3 tools/test/test_build_gopro_mission1_handoff_bundle.py && \
                python3 tools/test/test_build_gopro_mission1_intake_audit.py && \
                python3 tools/test/test_mission1_camera_target_preflight.py && \
                python3 tools/test/test_collect_mission1_target_closure.py && \
                python3 tools/test/test_run_mission1_target_closure_package.py && \
                python3 tools/test/test_run_mission1_remote_closure_package.py && \
                python3 tools/test/test_run_mission1_camera_closure.py && \
                python3 tools/test/test_mission1_camera_closure_run.py && \
                python3 tools/test/test_verify_release_manifest_artifacts.py && \
                if [ -d \"\${GPR_ARTIFACT_ROOT:-\${GPR_EXTERNAL_ROOT:-/Volumes/OWC_8TB/gpr_work}/artifacts}\" ]; then \
                    python3 tools/verify_release_manifest_artifacts.py --strict --summary; \
                else \
                    python3 tools/verify_release_manifest_artifacts.py --summary; \
                fi && \
                bash tools/test/test_labs_camera_handoff_receipt.sh && \
                bash tools/test/test_labs_encoder_bench_cli.sh"
    else
        SKIP_STEPS+=("release/readiness guards (no python3)")
    fi
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
