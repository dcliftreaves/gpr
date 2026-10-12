#!/usr/bin/env bash
# Build the decoder fuzzer in two variants:
#   /tmp/fuzz_decoder              — libFuzzer + AddressSanitizer (needs Clang)
#   /tmp/fuzz_decoder_standalone   — plain driver, runs anywhere
#
# Prerequisite: an in-tree build of the libs, i.e.
#   cmake -S . -B build && cmake --build build -j
# so that source/lib/*/lib*.a exist.
#
# Usage:
#   ./build.sh              # build both
#   ./build.sh fuzzer       # libFuzzer only
#   ./build.sh standalone   # standalone only

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
BUILD_LIB="$REPO/build/source/lib"

INCS=(
  "-I$REPO/source/lib/vc5_common"
  "-I$REPO/source/lib/vc5_encoder"
  "-I$REPO/source/lib/vc5_decoder"
  "-I$REPO/source/lib/common/public"
  "-I$REPO/source/lib/common/private"
)

LIBS=(
  "-L$BUILD_LIB/vc5_decoder" "-lvc5_decoder"
  "-L$BUILD_LIB/vc5_encoder" "-lvc5_encoder"
  "-L$BUILD_LIB/vc5_common"  "-lvc5_common"
  "-L$BUILD_LIB/common"      "-lcommon"
  "-lm" "-lpthread"
)

target="${1:-both}"

build_fuzzer() {
  echo ">>> Building libFuzzer variant -> /tmp/fuzz_decoder"
  # On macOS:
  #   - Apple's Xcode Clang doesn't ship libclang_rt.fuzzer_osx.a (so we
  #     can't use it for fuzzer builds).
  #   - Homebrew Clang DOES ship the fuzzer runtime, but it was built
  #     against Homebrew's own libc++ (not the system one). If the linker
  #     picks the system libc++ we get "std::__1::__hash_memory" undefined
  #     symbol errors. So we explicitly point libc++ at the Homebrew
  #     install when we detect one.
  local CXX_LIB_FLAGS=()
  if [[ "$(uname -s)" == "Darwin" ]]; then
    local BREW_LLVM=""
    if command -v brew >/dev/null 2>&1; then
      BREW_LLVM="$(brew --prefix llvm 2>/dev/null || true)"
    fi
    if [[ -n "$BREW_LLVM" && -d "$BREW_LLVM/lib/c++" ]]; then
      CXX_LIB_FLAGS=(
        "-L$BREW_LLVM/lib/c++"
        "-Wl,-rpath,$BREW_LLVM/lib/c++"
        "-lc++"
      )
    fi
  fi
  clang -O1 -g -fsanitize=fuzzer,address -fno-omit-frame-pointer \
    "${INCS[@]}" \
    "$HERE/main.c" \
    "${LIBS[@]}" \
    "${CXX_LIB_FLAGS[@]}" \
    -o /tmp/fuzz_decoder
  echo "    ok: /tmp/fuzz_decoder"
}

build_standalone() {
  echo ">>> Building standalone variant -> /tmp/fuzz_decoder_standalone"
  clang -O2 -g \
    "${INCS[@]}" \
    "$HERE/main.c" "$HERE/standalone.c" \
    "${LIBS[@]}" \
    -o /tmp/fuzz_decoder_standalone
  echo "    ok: /tmp/fuzz_decoder_standalone"
}

case "$target" in
  fuzzer)     build_fuzzer ;;
  standalone) build_standalone ;;
  both)
    # libFuzzer build is best-effort: skip with a warning if this Clang lacks it.
    if clang -fsanitize=fuzzer -x c -E /dev/null >/dev/null 2>&1; then
      build_fuzzer
    else
      echo ">>> Skipping libFuzzer variant: this Clang doesn't support -fsanitize=fuzzer."
    fi
    build_standalone
    ;;
  *)
    echo "usage: $0 [fuzzer|standalone|both]" >&2
    exit 2
    ;;
esac
