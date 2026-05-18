#!/usr/bin/env bash
# Pi 5 / Cortex-A76 benchmark harness for the fused encoder.
#
# Run on the Pi after building. Expects a 50 MP raw at $RAW (defaults to
# /tmp/Z8_textured.raw with 8280x5520) and a built /tmp/bench_clean binary
# linked against the current branch's libvc5_encoder.a.
#
# Outputs one block of stats per (single|multi) × (legacy|ring) config.
#
# Usage:
#   ./pi_benchmark.sh                            # uses defaults
#   RAW=/path/to.raw W=8280 H=5520 N=30 ./pi_benchmark.sh
#
# To produce /tmp/bench_clean on the Pi after scp'ing this repo:
#   cmake -B build -DCMAKE_BUILD_TYPE=Release
#   cmake --build build -j$(nproc)
#   clang -O3 -DNDEBUG -I source/lib/vc5_encoder \
#     tools/bench_clean.c \
#     build/source/lib/vc5_encoder/libvc5_encoder.a \
#     build/source/lib/vc5_common/libvc5_common.a \
#     build/source/lib/common/libcommon.a \
#     -lm -lpthread -o /tmp/bench_clean

set -u

RAW="${RAW:-/tmp/Z8_textured.raw}"
W="${W:-8280}"
H="${H:-5520}"
N="${N:-30}"
BENCH="${BENCH:-/tmp/bench_clean}"

if [ ! -x "$BENCH" ]; then
    echo "ERROR: $BENCH not found or not executable" >&2
    exit 1
fi
if [ ! -r "$RAW" ]; then
    echo "ERROR: $RAW not readable" >&2
    exit 1
fi

# Pin governor to 'performance' if writable — Pi 5 defaults to 'ondemand'
# which scales clocks down between frames, adding jitter on short bursts.
if [ -w /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]; then
    echo "Setting governor=performance on all cores"
    for c in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        echo performance | sudo tee "$c" > /dev/null 2>&1 || \
        echo performance > "$c" 2>/dev/null || true
    done
fi

run() {
    local label="$1"; shift
    echo "=== $label ==="
    env "$@" "$BENCH" "$RAW" "$W" "$H" "$N" > /dev/null 2>&1 | true  # eat stdout (frame list)
    env "$@" "$BENCH" "$RAW" "$W" "$H" "$N" 2>&1 > /dev/null         # show stats (stderr)
    echo
}

echo "Pi 5 fused-encoder benchmark (raw=$RAW  ${W}x${H}  n=$N)"
echo "Branch: $(git -C "$(dirname "$0")/.." rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")"
echo "HEAD:   $(git -C "$(dirname "$0")/.." log -1 --oneline 2>/dev/null || echo "unknown")"
echo

run "single-level  legacy unpack"   FUSED_MULTI_LEVEL=0 FUSED_PRODUCER_UNPACK=0
run "single-level  ring unpack"     FUSED_MULTI_LEVEL=0 FUSED_PRODUCER_UNPACK=1
run "multi-level   legacy unpack"   FUSED_MULTI_LEVEL=1 FUSED_PRODUCER_UNPACK=0
run "multi-level   ring unpack"     FUSED_MULTI_LEVEL=1 FUSED_PRODUCER_UNPACK=1

echo "24 fps target = 41.7 ms/frame.  Lower is better."
