#!/usr/bin/env bash
# Smoke-test the Mission 1 4K cleanup production-signoff receipt schema.
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
WORK=${WORK:-$GPR_TMPDIR/mission1_4k_cleanup_signoff_smoke}
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

"$PYTHON_BIN" - "$WORK" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
base = {
    "schema": "gpr.mission1_4k_cleanup_production_signoff.v1",
    "candidate": {
        "pipeline_id": "mission1_native12_4k_cleanup_rgb_cfa_w40_v1",
        "checkpoint_sha256": "a" * 64,
        "visual_signoff_sha256": "b" * 64,
        "contact_sheet_sha256": "c" * 64,
    },
    "objective_visual_signoff": {
        "verdict": "objective_visual_metrics_pass_manual_signoff_required",
        "all_checks_passed": True,
        "check_count": 7,
    },
    "raw_domain_guard": {
        "path": "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_raw_guard/summary.json",
        "sha256": "d" * 64,
        "kind": "high_res_cfa_target",
        "target": "high-resolution-derived CFA raw target",
        "source_schema": "gpr.bayer_rgb_cfa_target_dashboard.v1",
        "row_count": 42,
        "thresholds": {
            "min_rmse_improvement_pct": 0.0,
            "min_mae_improvement_pct": 0.0,
            "min_psnr_delta_db": 0.0,
        },
        "metrics": {
            "rmse_improvement_pct": {"n": 42, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
            "mae_improvement_pct": {"n": 42, "min": 1.0, "median": 2.0, "mean": 2.0, "max": 3.0},
            "psnr_delta_db": {"n": 42, "min": 0.1, "median": 0.2, "mean": 0.2, "max": 0.3},
        },
        "source_metric_names": {
            "rmse_improvement_pct": "cfa_raw_rmse_improvement_pct",
            "mae_improvement_pct": "cfa_raw_mae_improvement_pct",
            "psnr_delta_db": "cfa_raw_psnr_delta_db",
        },
        "passed": True,
    },
    "diagnostics": {
        "legacy_clean_low_raw_guard": {
            "production_blocking": False,
            "note": "diagnostic",
        }
    },
    "reviewer": {
        "name": "synthetic reviewer",
        "role": "project-owner",
        "reviewed_at_utc": "2026-06-25T00:00:00Z",
    },
    "review": {
        "visual_checked": True,
        "contact_sheet_path": "artifacts/mission1_4k_cleanup_visual_signoff_20260625/visual_signoff_contact_sheet.jpg",
        "dashboard_paths": [
            "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_rgb_cfa_target_gate_wb_review/index.html",
            "artifacts/current_goal_bayer_rgb_target_cleanup_20260625/train_w40_d5_rs015_gamma2_grad1_raw2_bayer2/mission42_4k_cnn_tone_audit_20260625/index.html",
        ],
        "blocking_issues": [],
    },
    "verdict": {
        "production_ready": True,
        "accepted_role": "production",
        "no_blocking_visual_issues": True,
    },
}
(root / "production_ok.json").write_text(json.dumps(base, indent=2), encoding="utf-8")

blocked = json.loads(json.dumps(base))
blocked["review"]["visual_checked"] = False
blocked["review"]["blocking_issues"] = ["project-owner visual signoff not complete"]
blocked["verdict"] = {
    "production_ready": False,
    "accepted_role": "blocked",
    "no_blocking_visual_issues": False,
}
blocked["blocker"] = {"cause": "manual_visual_signoff_missing"}
(root / "blocked_ok.json").write_text(json.dumps(blocked, indent=2), encoding="utf-8")

bad = json.loads(json.dumps(base))
bad["review"]["blocking_issues"] = ["visible artifact"]
(root / "bad_production_with_issue.json").write_text(json.dumps(bad, indent=2), encoding="utf-8")

bad_no_blocker = json.loads(json.dumps(blocked))
del bad_no_blocker["blocker"]
(root / "bad_blocked_without_cause.json").write_text(json.dumps(bad_no_blocker, indent=2), encoding="utf-8")

bad_raw_guard = json.loads(json.dumps(base))
bad_raw_guard["raw_domain_guard"]["passed"] = False
(root / "bad_production_raw_guard.json").write_text(json.dumps(bad_raw_guard, indent=2), encoding="utf-8")
PY

"$PYTHON_BIN" "$REPO/tools/check_mission1_4k_cleanup_signoff_receipt.py" "$WORK/production_ok.json"
"$PYTHON_BIN" "$REPO/tools/check_mission1_4k_cleanup_signoff_receipt.py" "$WORK/blocked_ok.json"

if "$PYTHON_BIN" "$REPO/tools/check_mission1_4k_cleanup_signoff_receipt.py" "$WORK/bad_production_with_issue.json" > "$WORK/bad.log" 2>&1; then
  echo "test_mission1_4k_cleanup_signoff_receipt: expected production issue receipt to fail" >&2
  exit 1
fi
grep -q "blocking_issues" "$WORK/bad.log"

if "$PYTHON_BIN" "$REPO/tools/check_mission1_4k_cleanup_signoff_receipt.py" "$WORK/bad_blocked_without_cause.json" > "$WORK/bad_cause.log" 2>&1; then
  echo "test_mission1_4k_cleanup_signoff_receipt: expected blocked receipt without cause to fail" >&2
  exit 1
fi
grep -q "blocker.cause" "$WORK/bad_cause.log"

if "$PYTHON_BIN" "$REPO/tools/check_mission1_4k_cleanup_signoff_receipt.py" "$WORK/bad_production_raw_guard.json" > "$WORK/bad_raw_guard.log" 2>&1; then
  echo "test_mission1_4k_cleanup_signoff_receipt: expected production receipt with failing raw guard to fail" >&2
  exit 1
fi
grep -q "raw_domain_guard.passed" "$WORK/bad_raw_guard.log"

echo "test_mission1_4k_cleanup_signoff_receipt: PASS"
