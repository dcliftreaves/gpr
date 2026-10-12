"""Ship pipeline audit.

Every pipeline tagged ship-* in the registry should have production evidence.
Most ship pipelines must have a committed passing gate run for their exact
pipeline id. External-receipt-only pipelines are allowed only when the registry
declares the external receipt, dashboard, runtime entrypoint, and production
scope explicitly. Strict mode additionally requires normal gate runs to use the
current gates.json and to have a claims_log.md receipt.

Usage:
  python3 tests/quality_gates/audit_ship_pipelines.py
  python3 tests/quality_gates/audit_ship_pipelines.py --strict

Exit codes:
  0  every ship pipeline has a passing gate run
  1  one or more ship pipelines is missing a passing run or has a FAIL
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REG = json.loads((REPO / "pipelines/registry.json").read_text())
RUNS_DIR = REPO / "tests/quality_gates/runs"
GATES_PATH = REPO / "tests/quality_gates/gates.json"
CLAIMS_LOG = REPO / "docs/claims_log.md"


def current_gates_sha() -> str:
    return hashlib.sha256(GATES_PATH.read_bytes()).hexdigest()[:16]


def parse_time(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def git_tracked_run_jsons() -> set[Path]:
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "tests/quality_gates/runs/*/run.json"],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return set()
    return {REPO / line.strip() for line in out.splitlines() if line.strip()}


def run_json_paths(include_untracked: bool) -> list[Path]:
    if include_untracked:
        return sorted(RUNS_DIR.glob("*/run.json"))
    tracked = git_tracked_run_jsons()
    return sorted(path for path in tracked if path.exists())


def load_claims() -> set[tuple[str, str]]:
    if not CLAIMS_LOG.exists():
        return set()
    claims = set()
    pat = re.compile(r"pipeline=`([^`]+)`\s+run=([0-9a-f]{16})")
    for line in CLAIMS_LOG.read_text(errors="ignore").splitlines():
        m = pat.search(line)
        if m:
            claims.add((m.group(1), m.group(2)))
    return claims


def latest_run(pipeline_name: str, include_untracked: bool):
    best = None
    best_time = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    for f in run_json_paths(include_untracked):
        try:
            d = json.loads(f.read_text())
            if d.get("pipeline") != pipeline_name:
                continue
            run_time = parse_time(d.get("finished_at"))
            if best is None or run_time > best_time or (
                run_time == best_time and f.parent.name > best[0].parent.name
            ):
                best_time = run_time
                best = (f, d)
        except Exception:
            pass
    return best


def worst_lpips(run: dict) -> float:
    imgs = run.get("images") or {}
    return max((im.get("lpips", 0) or 0 for im in imgs.values()), default=0.0)


def mean_mb(run: dict) -> float:
    imgs = run.get("images") or {}
    bytes_list = [im.get("enc_bytes", 0) for im in imgs.values()]
    return sum(bytes_list) / len(bytes_list) / 1e6 if bytes_list else 0.0


def image_verdicts_ok(run: dict) -> bool:
    imgs = run.get("images") or {}
    return bool(imgs) and all(im.get("verdict") == "PASS" for im in imgs.values())


def git_tracked_file(path: Path) -> bool:
    try:
        subprocess.check_output(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(REPO))],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def external_receipt_checks(pipeline: dict) -> tuple[bool, list[str], dict]:
    cnn_name = str(pipeline.get("cnn", ""))
    cnn = ((REG.get("cnns") or {}).get(cnn_name, {}) or {})
    checks: list[str] = []
    details = {
        "cnn": cnn_name,
        "holdout_receipt": str(cnn.get("holdout_receipt", "")),
        "dashboard": str(cnn.get("dashboard", "")),
        "runtime_entrypoint": str(cnn.get("runtime_entrypoint", "")),
    }
    pipeline_doc_l = str(pipeline.get("$doc", "")).lower()
    cnn_doc_l = str(cnn.get("$doc", "")).lower()
    entrypoint = details["runtime_entrypoint"]

    if not cnn.get("external_receipt_only"):
        checks.append("cnn is not marked external_receipt_only")
    if not details["holdout_receipt"]:
        checks.append("missing holdout_receipt")
    if not details["dashboard"]:
        checks.append("missing dashboard")
    if not entrypoint:
        checks.append("missing runtime_entrypoint")
    elif not git_tracked_file(REPO / entrypoint):
        checks.append(f"runtime_entrypoint is not tracked ({entrypoint})")
    if "external-receipt" not in pipeline_doc_l:
        checks.append("pipeline doc does not say external-receipt")
    if "production path" not in pipeline_doc_l:
        checks.append("pipeline doc does not say production path")
    if "not live/camera-back preview" not in pipeline_doc_l:
        checks.append("pipeline doc does not define live/camera-back boundary")
    if "external-receipt" not in cnn_doc_l:
        checks.append("cnn doc does not say external-receipt")
    if "production path" not in cnn_doc_l:
        checks.append("cnn doc does not say production path")

    return not checks, checks, details


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--include-untracked",
        action="store_true",
        help="include local untracked run.json files; off by default for production audits",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="also require current gates_sha and a claims_log.md receipt",
    )
    args = ap.parse_args()

    gates_sha = current_gates_sha()
    claims = load_claims()
    ship_pipelines = []
    for pn, p in REG.get("pipelines", {}).items():
        if not isinstance(p, dict):
            continue
        role = p.get("$role", "")
        if role.startswith("ship-"):
            ship_pipelines.append((pn, p))

    print(f"=== Ship pipeline audit ({len(ship_pipelines)} ship-tagged pipelines) ===")
    print(f"include_untracked: {args.include_untracked}")
    print(f"strict: {args.strict}")
    print(f"current_gates_sha: {gates_sha}")
    print()
    any_problem = False
    for pn, p in ship_pipelines:
        r = latest_run(pn, args.include_untracked)
        role = p.get("$role", "?")
        sc = p.get("ship_class", "?")
        if r is None:
            external_ok, external_problems, details = external_receipt_checks(p)
            if external_ok:
                print(f"  PASS [{sc:13}] external receipt  {role}")
                print(f"       pipeline={pn}")
                print(f"       receipt={details['holdout_receipt']}")
                print(f"       dashboard={details['dashboard']}")
                continue
            print(f"  FAIL no committed run [{sc:13}] {role}")
            print(f"          {pn}")
            for check in external_problems:
                print(f"       - {check}")
            any_problem = True
            continue

        run_path, run = r
        run_hash = run_path.parent.name[:16]
        checks = []
        if run.get("run_hash") != run_hash:
            checks.append(f"run_hash field mismatch ({run.get('run_hash')} != {run_hash})")
        if run.get("ship_class") != sc:
            checks.append(f"ship_class mismatch ({run.get('ship_class')} != {sc})")
        if run.get("verdict") != "PASS":
            checks.append(f"verdict is {run.get('verdict')}")
        if not image_verdicts_ok(run):
            checks.append("one or more image verdicts are not PASS")
        if args.strict and run.get("gates_sha") != gates_sha:
            checks.append(f"stale gates_sha ({run.get('gates_sha')} != {gates_sha})")
        if args.strict and (pn, run_hash) not in claims:
            checks.append("missing claims_log.md receipt")

        status = "PASS" if not checks else "FAIL"
        print(f"  {status} [{sc:13}] LPIPS {worst_lpips(run):.4f}  {mean_mb(run):5.2f} MB  {role}")
        print(f"       run={run_hash}  gates={run.get('gates_sha')}  pipeline={pn}")
        for check in checks:
            print(f"       - {check}")
        if checks:
            any_problem = True

    print()
    if any_problem:
        print("FAIL - one or more ship pipelines lacks a production-valid gate receipt")
        return 1
    print("OK - every ship pipeline has a production-valid gate receipt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
