#!/usr/bin/env python3
"""Regression-test the high-level goal contract guard."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/test/check_high_level_goal_contract.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("check_high_level_goal_contract_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = import_tool()
    failures = module.validate()
    if failures:
        print(f"current high-level goal contract unexpectedly failed: {failures}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        paths = {}
        for label in module.DOC_TOKENS:
            source = module.path_for(label)
            target = tmp / label.replace("/", "__")
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            paths[label] = target

        paths["docs/BIG_EFFORTS_STATUS.md"].write_text(
            paths["docs/BIG_EFFORTS_STATUS.md"].read_text(encoding="utf-8").replace(
                "Raw video reconstruction improvement",
                "Raw video improvement",
            ),
            encoding="utf-8",
        )
        failures = module.validate(paths)
        if not failures or not any("Raw video reconstruction improvement" in failure for failure in failures):
            print(f"missing raw-video reconstruction effort did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

        paths["docs/BIG_EFFORTS_STATUS.md"].write_text(
            module.path_for("docs/BIG_EFFORTS_STATUS.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        paths["docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md"].write_text(
            paths["docs/HIGH_LEVEL_GOAL_EXECUTION_PLAN.md"].read_text(encoding="utf-8").replace(
                "Offline premium still improvement has a dedicated still-SR gate",
                "Offline premium still improvement has a review path",
            ),
            encoding="utf-8",
        )
        failures = module.validate(paths)
        if not failures or not any("dedicated still-SR gate" in failure for failure in failures):
            print(f"missing still-SR gate did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

    print("test_check_high_level_goal_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
