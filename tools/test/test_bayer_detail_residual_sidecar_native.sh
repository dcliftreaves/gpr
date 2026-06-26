#!/usr/bin/env bash
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TOOL=${BAYER_DETAIL_RESIDUAL_SIDECAR:-"$REPO/build-local/bin/bayer_detail_residual_sidecar"}
PYTHON_BIN=${PYTHON_BIN:-python3}
WORK=${WORK:-"${GPR_TMPDIR:-${TMPDIR:-/tmp}}/bayer_detail_residual_sidecar_native"}

cleanup() {
  local status=$?
  if [ "$status" -eq 0 ] && [ "${GPR_KEEP_TEST_ARTIFACTS:-0}" != "1" ]; then
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT

if [ ! -x "$TOOL" ]; then
  echo "test_bayer_detail_residual_sidecar_native: SKIP missing tool: $TOOL"
  exit 0
fi

rm -rf "$WORK"
mkdir -p "$WORK"

"$PYTHON_BIN" - "$WORK/codec.raw" "$WORK/clean.raw" <<'PY'
import sys
import numpy as np

codec = np.full((32, 32), 1000, dtype=np.uint16)
clean = codec.copy()
clean[0::4, 0::4] += 12
codec.tofile(sys.argv[1])
clean.tofile(sys.argv[2])
PY

"$TOOL" encode "$WORK/codec.raw" "$WORK/clean.raw" "$WORK/residual.bdrs" \
  32 32 1 2 1 2 65535 "$WORK/encode.json" > "$WORK/encode.log"
BDRS_ENCODE_THREADS=4 "$TOOL" encode "$WORK/codec.raw" "$WORK/clean.raw" "$WORK/residual_t4.bdrs" \
  32 32 1 2 1 2 65535 "$WORK/encode_t4.json" > "$WORK/encode_t4.log"
cmp -s "$WORK/residual.bdrs" "$WORK/residual_t4.bdrs"
BDRS_COMPACT=1 "$TOOL" encode "$WORK/codec.raw" "$WORK/clean.raw" "$WORK/residual_compact.bdrs" \
  32 32 1 2 1 2 65535 "$WORK/encode_compact.json" > "$WORK/encode_compact.log"
BDRS_COMPACT=1 BDRS_ENCODE_THREADS=4 "$TOOL" encode "$WORK/codec.raw" "$WORK/clean.raw" "$WORK/residual_compact_t4.bdrs" \
  32 32 1 2 1 2 65535 "$WORK/encode_compact_t4.json" > "$WORK/encode_compact_t4.log"
cmp -s "$WORK/residual_compact.bdrs" "$WORK/residual_compact_t4.bdrs"
"$TOOL" decode "$WORK/codec.raw" "$WORK/residual.bdrs" "$WORK/out.raw" \
  32 32 "$WORK/clean.raw" "$WORK/decode.json" > "$WORK/decode.log"
"$TOOL" decode "$WORK/codec.raw" "$WORK/residual_compact.bdrs" "$WORK/out_compact.raw" \
  32 32 "$WORK/clean.raw" "$WORK/decode_compact.json" > "$WORK/decode_compact.log"

test -s "$WORK/residual.bdrs"
test -s "$WORK/residual_compact.bdrs"
test -s "$WORK/out.raw"
cmp -s "$WORK/out.raw" "$WORK/out_compact.raw"

"$PYTHON_BIN" - "$WORK/decode.json" "$WORK/decode_compact.json" "$WORK/codec.raw" "$WORK/out.raw" <<'PY'
import json
import sys
import numpy as np
from pathlib import Path

receipt = json.loads(Path(sys.argv[1]).read_text())
compact = json.loads(Path(sys.argv[2]).read_text())
assert receipt["schema"] == "gpr.bayer_detail_residual_sidecar_native.v1"
assert receipt["sidecar_format"] == "bitmap_i16"
assert compact["sidecar_format"] == "compact_varint_qstep"
assert compact["sidecar_bytes"] < receipt["sidecar_bytes"]
assert receipt["output_clean_rmse"] < receipt["codec_clean_rmse"]
assert abs(compact["output_clean_rmse"] - receipt["output_clean_rmse"]) < 1e-9
codec = np.fromfile(sys.argv[3], dtype="<u2")
out = np.fromfile(sys.argv[4], dtype="<u2")
assert not np.array_equal(codec, out)
PY

"$PYTHON_BIN" - "$WORK/encode.json" "$WORK/encode_t4.json" "$WORK/encode_compact.json" "$WORK/encode_compact_t4.json" <<'PY'
import json
import sys
from pathlib import Path

single = json.loads(Path(sys.argv[1]).read_text())
threaded = json.loads(Path(sys.argv[2]).read_text())
compact = json.loads(Path(sys.argv[3]).read_text())
compact_threaded = json.loads(Path(sys.argv[4]).read_text())
assert single["encode_threads"] == 1
assert threaded["encode_threads"] == 4
assert compact_threaded["encode_threads"] == 4
assert single["value_count"] == threaded["value_count"]
assert single["sidecar_bytes"] == threaded["sidecar_bytes"]
assert compact["value_count"] == single["value_count"]
assert compact["sidecar_format"] == "compact_varint_qstep"
assert compact_threaded["sidecar_format"] == "compact_varint_qstep"
assert compact_threaded["value_count"] == compact["value_count"]
assert compact_threaded["sidecar_bytes"] == compact["sidecar_bytes"]
assert compact["value_payload_bytes"] < single["value_payload_bytes"]
PY

echo "test_bayer_detail_residual_sidecar_native: PASS"
