#!/usr/bin/env bash
# Smoke-test the Mission 1 4K cleanup signoff receipt builder.
set -euo pipefail

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [ -z "${GPR_EXTERNAL_ROOT:-}" ]; then
  if [ -d /Volumes/OWC_8TB/gpr_work ]; then
    GPR_EXTERNAL_ROOT="/Volumes/OWC_8TB/gpr_work"
  else
    GPR_EXTERNAL_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/gpr_work"
  fi
fi
GPR_TMPDIR="${GPR_TMPDIR:-$GPR_EXTERNAL_ROOT/tmp}"
WORK=${WORK:-$GPR_TMPDIR/mission1_4k_cleanup_signoff_builder_smoke}
PYTHON_BIN="${PYTHON_BIN:-python3}"

cleanup() {
  local status=$?
  if [ "$status" -eq 0 ] && [ "${GPR_KEEP_TEST_ARTIFACTS:-0}" != "1" ]; then
    rm -rf "$WORK"
  fi
}
trap cleanup EXIT

rm -rf "$WORK"
mkdir -p "$WORK"

checkpoint="$WORK/checkpoint.pt"
visual="$WORK/visual_signoff.json"
contact="$WORK/contact.jpg"
raw_guard="$WORK/raw_guard_summary.json"
printf 'checkpoint' > "$checkpoint"
printf 'contact-sheet' > "$contact"
"$PYTHON_BIN" - "$visual" <<'PY'
import json
import sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "schema": "gpr.mission1_4k_cleanup_visual_signoff.v1",
    "verdict": "objective_visual_metrics_pass_manual_signoff_required",
    "checks": [
        {"name": "a", "passed": True, "detail": "ok"},
        {"name": "b", "passed": True, "detail": "ok"},
    ],
}, indent=2), encoding="utf-8")
PY
"$PYTHON_BIN" - "$raw_guard" <<'PY'
import json
import sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "schema": "gpr.bayer_low_cleanup_dashboard.v1",
    "summary": {
        "count": 2,
        "rmse_improvement_pct": {"n": 2, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
        "mae_improvement_pct": {"n": 2, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
        "psnr_delta_db": {"n": 2, "min": 0.1, "median": 0.2, "mean": 0.2, "max": 0.3},
        "cfa_raw_rmse_improvement_pct": {"n": 2, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
        "cfa_raw_mae_improvement_pct": {"n": 2, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
        "cfa_raw_psnr_delta_db": {"n": 2, "min": 0.1, "median": 0.2, "mean": 0.2, "max": 0.3},
    },
}, indent=2), encoding="utf-8")
PY

"$PYTHON_BIN" "$REPO/tools/build_mission1_4k_cleanup_signoff_receipt.py" \
  --external-root "$WORK" \
  --checkpoint "$checkpoint" \
  --visual-signoff "$visual" \
  --contact-sheet "$contact" \
  --raw-guard-summary "$raw_guard" \
  --dashboard-path "$WORK/dashboard_a.html" \
  --output "$WORK/blocked.json" \
  --reviewer-name "synthetic reviewer" \
  --reviewed-at-utc "2026-06-25T00:00:00Z" \
  --blocking-issue "project-owner visual signoff not complete" \
  --blocker-cause "manual_visual_signoff_missing"
"$PYTHON_BIN" "$REPO/tools/check_mission1_4k_cleanup_signoff_receipt.py" "$WORK/blocked.json"

"$PYTHON_BIN" "$REPO/tools/build_mission1_4k_cleanup_signoff_receipt.py" \
  --external-root "$WORK" \
  --checkpoint "$checkpoint" \
  --visual-signoff "$visual" \
  --contact-sheet "$contact" \
  --raw-guard-summary "$raw_guard" \
  --dashboard-path "$WORK/dashboard_a.html" \
  --output "$WORK/production.json" \
  --reviewer-name "synthetic reviewer" \
  --reviewed-at-utc "2026-06-25T00:00:00Z" \
  --visual-checked \
  --production-ready
"$PYTHON_BIN" "$REPO/tools/check_mission1_4k_cleanup_signoff_receipt.py" "$WORK/production.json"

if "$PYTHON_BIN" "$REPO/tools/build_mission1_4k_cleanup_signoff_receipt.py" \
  --external-root "$WORK" \
  --checkpoint "$checkpoint" \
  --visual-signoff "$visual" \
  --contact-sheet "$contact" \
  --raw-guard-summary "$raw_guard" \
  --dashboard-path "$WORK/dashboard_a.html" \
  --output "$WORK/bad.json" \
  --reviewer-name "synthetic reviewer" \
  --reviewed-at-utc "2026-06-25T00:00:00Z" \
  --visual-checked \
  --production-ready \
  --blocking-issue "visible artifact" > "$WORK/bad.log" 2>&1; then
  echo "test_build_mission1_4k_cleanup_signoff_receipt: expected production with blocking issue to fail" >&2
  exit 1
fi
grep -q -- "--production-ready cannot be combined" "$WORK/bad.log"

"$PYTHON_BIN" - "$raw_guard" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["summary"]["rmse_improvement_pct"]["min"] = -1.0
data["summary"]["cfa_raw_rmse_improvement_pct"]["min"] = -1.0
path.write_text(json.dumps(data, indent=2), encoding="utf-8")
PY
if "$PYTHON_BIN" "$REPO/tools/build_mission1_4k_cleanup_signoff_receipt.py" \
  --external-root "$WORK" \
  --checkpoint "$checkpoint" \
  --visual-signoff "$visual" \
  --contact-sheet "$contact" \
  --raw-guard-summary "$raw_guard" \
  --dashboard-path "$WORK/dashboard_a.html" \
  --output "$WORK/bad_raw_guard.json" \
  --reviewer-name "synthetic reviewer" \
  --reviewed-at-utc "2026-06-25T00:00:00Z" \
  --visual-checked \
  --production-ready > "$WORK/bad_raw_guard.log" 2>&1; then
  echo "test_build_mission1_4k_cleanup_signoff_receipt: expected production with failing raw guard to fail" >&2
  exit 1
fi
grep -q "raw-domain guard" "$WORK/bad_raw_guard.log"

echo "test_build_mission1_4k_cleanup_signoff_receipt: PASS"
