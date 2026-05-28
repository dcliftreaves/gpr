"""Ship pipeline audit — every pipeline tagged ship-* in the registry
should have a passing recent gate run. Run on demand to catch drift.

Usage:
  python3 tests/quality_gates/audit_ship_pipelines.py

Exit codes:
  0  every ship pipeline has a passing gate run
  1  one or more ship pipelines is missing a passing run or has a FAIL
"""
from __future__ import annotations
import json
import os
import glob
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REG = json.loads((REPO / "pipelines/registry.json").read_text())
RUNS_DIR = REPO / "tests/quality_gates/runs"


def latest_run(pipeline_name: str):
    best = None
    best_mt = -1
    for f in glob.glob(str(RUNS_DIR / "*/run.json")):
        try:
            d = json.loads(open(f).read())
            if d.get("pipeline") != pipeline_name:
                continue
            mt = os.path.getmtime(f)
            if mt > best_mt:
                best_mt = mt
                best = (f, d)
        except Exception:
            pass
    return best


def main() -> int:
    ship_pipelines = []
    for pn, p in REG.get("pipelines", {}).items():
        if not isinstance(p, dict):
            continue
        role = p.get("$role", "")
        if role.startswith("ship-"):
            ship_pipelines.append((pn, p))

    print(f"=== Ship pipeline audit ({len(ship_pipelines)} ship-tagged pipelines) ===")
    print()
    any_problem = False
    for pn, p in ship_pipelines:
        r = latest_run(pn)
        role = p.get("$role", "?")
        sc = p.get("ship_class", "?")
        if r is None:
            print(f"  NO RUN  [{sc:13}] {role}")
            print(f"          {pn}")
            any_problem = True
            continue
        v = r[1].get("verdict", "?")
        imgs = r[1].get("images", {})
        worst_lp = max((im.get("lpips", 0) or 0 for im in imgs.values()), default=0)
        bytes_list = [im.get("enc_bytes", 0) for im in imgs.values()]
        mean_mb = sum(bytes_list) / len(bytes_list) / 1e6 if bytes_list else 0
        rh = os.path.basename(os.path.dirname(r[0]))[:16]
        marker = "  " if v == "PASS" else "✗ "
        print(f"  {marker}{v}  [{sc:13}] LPIPS {worst_lp:.4f}  {mean_mb:5.2f} MB  {role}")
        print(f"          run={rh}  pipeline={pn}")
        if v != "PASS":
            any_problem = True
    print()
    if any_problem:
        print("FAIL — one or more ship pipelines lacks a passing gate run")
        return 1
    print("OK — every ship pipeline has a passing gate run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
