#!/usr/bin/env bash
# Exercise the documented optional feature branches, not just the full tree.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/gpr-adoption.XXXXXX")
PYTHON_BIN=${PYTHON_BIN:-python3}
cleanup() {
  git -C "$REPO" worktree remove --force "$WORK/source" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT
for feature in stills preview desktop; do
  if [ "$feature" = stills ]; then
    git -C "$REPO" worktree add --detach "$WORK/source" 95d1a2d
  else
    git -C "$REPO" worktree add --detach "$WORK/source" 115414b
    if [ "$feature" = preview ]; then
      commits=(240c527)
    else
      commits=(8e5f724)
    fi
    git -C "$WORK/source" -c user.name='Adoption Test' \
      -c user.email='adoption@example.invalid' cherry-pick "${commits[@]}"
  fi
  # Supply only test drivers from this companion branch, never runtime code.
  mkdir -p "$WORK/source/tools/test" "$WORK/source/tests"
  for driver in test_still_metadata.py test_native_preview.py test_desktop_outputs.py test_bayer_resample.py; do
    cp "$REPO/tools/test/$driver" "$WORK/source/tools/test/"
  done
  cp "$REPO/tests/test_reconstruction_models.py" "$WORK/source/tests/"
  export BUILD_DIR="$WORK/build-$feature"
  export GPR_TOOLS="$BUILD_DIR/source/app/gpr_tools/gpr_tools"
  cmake -S "$WORK/source" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$BUILD_DIR" --parallel "${JOBS:-4}"
  (
    cd "$WORK/source"
    if [ "$feature" = stills ]; then
      "$PYTHON_BIN" tools/test/test_still_metadata.py
    elif [ "$feature" = preview ]; then
      "$PYTHON_BIN" tools/test/test_native_preview.py
    else
      make -C tools/gpraw
      if [ "$(uname -s)" = Darwin ]; then
        make -C tools/gpr2prores GPR_BUILD="$BUILD_DIR"
        "$PYTHON_BIN" tools/test/test_desktop_outputs.py
      else
        "$PYTHON_BIN" tools/test/test_desktop_outputs.py --wrapper-only
      fi
      echo "PASS: independent desktop output adoption"
      git -c user.name='Adoption Test' -c user.email='adoption@example.invalid' \
        cherry-pick cd04508
      cmake -S . -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
      cmake --build "$BUILD_DIR" --parallel "${JOBS:-4}"
      "$PYTHON_BIN" tests/test_reconstruction_models.py
      "$PYTHON_BIN" tools/test/test_bayer_resample.py
      "$PYTHON_BIN" tools/build_camera_noise_runtime_policy.py --help
      "$PYTHON_BIN" tools/cnn/render_gvid_sr_receipt.py --help
      "$PYTHON_BIN" tools/cnn/evaluate_preview_q8_threeway_runtime_fullframe.py --help
    fi
  )
  git -C "$REPO" worktree remove --force "$WORK/source"
  rm -rf "$BUILD_DIR"
  echo "PASS: independent $feature adoption"
done
