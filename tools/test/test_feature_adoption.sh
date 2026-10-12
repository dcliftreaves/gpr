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
for feature in preview desktop; do
  git -C "$REPO" worktree add --detach "$WORK/source" e479bdf
  if [ "$feature" = preview ]; then
    commits=(5a93986)
  else
    commits=(2a8dec5)
  fi
  git -C "$WORK/source" -c user.name='Adoption Test' \
    -c user.email='adoption@example.invalid' cherry-pick "${commits[@]}"
  export BUILD_DIR="$WORK/build-$feature"
  cmake -S "$WORK/source" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$BUILD_DIR" --parallel "${JOBS:-4}"
  ctest --test-dir "$BUILD_DIR" --output-on-failure
  (
    cd "$WORK/source"
    if [ "$feature" = preview ]; then
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
        cherry-pick 096cbd4
      cmake -S . -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
      cmake --build "$BUILD_DIR" --parallel "${JOBS:-4}"
      "$PYTHON_BIN" tests/test_reconstruction_models.py
      "$PYTHON_BIN" tools/test/test_bayer_resample.py
      "$PYTHON_BIN" tools/test/test_raw_resolution_targets.py
    fi
  )
  git -C "$REPO" worktree remove --force "$WORK/source"
  rm -rf "$BUILD_DIR"
  echo "PASS: independent $feature adoption"
done
