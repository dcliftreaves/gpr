#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
scratch="${RUNNER_TEMP:?Set RUNNER_TEMP}/gpr-coverage"
out="${GPR_TEST_ARTIFACT_DIR:?Set GPR_TEST_ARTIFACT_DIR}/coverage"
mkdir -p "$out"
unset COVERAGE_PROCESS_START
export COVERAGE_FILE="$scratch/python/.coverage"
python3 -m coverage combine "$scratch/python"
python3 -m coverage json -o "$out/python.json"
python3 -m gcovr --root "$root" --object-directory "${BUILD_DIR:?Set BUILD_DIR}" \
    --gcov-ignore-errors=source_not_found --json "$out/native.json" \
    "${BUILD_DIR}" "$scratch"
runtime=$(git rev-parse "${GPR_RUNTIME_REF:-origin/review/product-runtime}")
python3 tools/test/audit_feature_coverage.py --base 446c736a38fb14f51343605c0780d347dc602f89 \
    --head "$runtime" --test-ref HEAD --python-json "$out/python.json" \
    --gcov-json "$out/native.json" --output "$out/feature-coverage.json"
python3 - "$out/feature-coverage.json" "${GITHUB_STEP_SUMMARY:-/dev/stdout}" <<'PY'
import collections
import json
import sys
from pathlib import Path
report = json.loads(Path(sys.argv[1]).read_text())
states = collections.Counter(row['execution']['status'] for row in report['files'])
measured = sum(row['changed_line_coverage']['measured_lines'] for row in report['files'])
executed = sum(row['changed_line_coverage']['executed_lines'] for row in report['files'])
with open(sys.argv[2], 'a', encoding='utf-8') as out:
    out.write('\n### Instrumented Linux feature coverage\n')
    out.write(f"Runtime commit: `{report['refs']['head']}`; validation: `{report['refs']['tests']}`.\n\n")
    out.write(f"Files: {dict(states)}. Changed executable lines: {executed}/{measured}.\n\n")
    out.write('Uninstrumented platforms/backends remain UNKNOWN. Execution is not an assertion or trained-model quality pass. Instrumented timings are not performance receipts.\n')
PY
