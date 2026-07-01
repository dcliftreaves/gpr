#!/usr/bin/env python3
"""Regression-test product lock-ledger alignment checks."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/test/check_product_lock_ledger.py"
LEDGER = ROOT / "docs/PRODUCT_LOCK_LEDGER.md"


def import_tool():
    spec = importlib.util.spec_from_file_location("check_product_lock_ledger_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = import_tool()
    failures = module.validate()
    if failures:
        print(f"current lock ledger unexpectedly failed: {failures}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as td:
        tmp_ledger = Path(td) / "PRODUCT_LOCK_LEDGER.md"
        text = LEDGER.read_text(encoding="utf-8")
        tmp_ledger.write_text(
            text.replace("| Mission 1 8K SR |", "| Mission 1 imaginary lock |"),
            encoding="utf-8",
        )
        failures = module.validate(tmp_ledger)
        if not failures or not any("missing locked ledger paths" in failure for failure in failures):
            print(f"ledger mutation did not trigger missing locked path failure: {failures}", file=sys.stderr)
            return 1

        tmp_ledger.write_text(
            text.replace(
                "| Release packaging and documentation hygiene for the approved offline reconstruction workflow |",
                "| Imaginary open gate |",
            ),
            encoding="utf-8",
        )
        failures = module.validate(tmp_ledger)
        if not failures or not any("missing open production gates" in failure for failure in failures):
            print(f"ledger mutation did not trigger missing open gate failure: {failures}", file=sys.stderr)
            return 1

    print("test_check_product_lock_ledger: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
