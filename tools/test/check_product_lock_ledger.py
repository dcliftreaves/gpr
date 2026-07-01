#!/usr/bin/env python3
"""Validate that the product lock ledger and scorecard stay aligned."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from build_product_pillar_scorecard import DEFAULT_EXTERNAL_ROOT, build_scorecard  # noqa: E402


LEDGER = ROOT / "docs/PRODUCT_LOCK_LEDGER.md"


def table_first_column(markdown: str, section: str) -> list[str]:
    marker = f"## {section}"
    if marker not in markdown:
        return []
    body = markdown.split(marker, 1)[1]
    if "\n## " in body:
        body = body.split("\n## ", 1)[0]
    values: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [part.strip() for part in line.strip("|").split("|")]
        if not parts or parts[0] in {"path", "gate", "---"} or set(parts[0]) == {"-"}:
            continue
        if parts[0]:
            values.append(parts[0])
    return values


def scorecard_values(scorecard: dict[str, Any], field: str) -> set[str]:
    values: set[str] = set()
    for pillar in scorecard.get("pillars", []):
        for value in pillar.get(field, []):
            values.add(str(value))
    return values


def validate(ledger_path: Path = LEDGER, external_root: Path = DEFAULT_EXTERNAL_ROOT) -> list[str]:
    failures: list[str] = []
    if not ledger_path.exists():
        return [f"{ledger_path} is missing"]
    markdown = ledger_path.read_text(encoding="utf-8")
    locked_paths = set(table_first_column(markdown, "Locked Paths"))
    open_gates = set(table_first_column(markdown, "Open Production Gates"))
    if not locked_paths:
        failures.append("PRODUCT_LOCK_LEDGER.md has no locked paths")
    if not open_gates:
        failures.append("PRODUCT_LOCK_LEDGER.md has no open production gates")

    scorecard = build_scorecard(external_root)
    scorecard_locked = scorecard_values(scorecard, "lock_ledger_paths")
    scorecard_open = scorecard_values(scorecard, "open_production_gates")

    missing_locked = sorted(locked_paths - scorecard_locked)
    extra_locked = sorted(scorecard_locked - locked_paths)
    missing_open = sorted(open_gates - scorecard_open)
    extra_open = sorted(scorecard_open - open_gates)
    if missing_locked:
        failures.append(f"scorecard missing locked ledger paths: {missing_locked}")
    if extra_locked:
        failures.append(f"scorecard has locked paths not in ledger: {extra_locked}")
    if missing_open:
        failures.append(f"scorecard missing open production gates: {missing_open}")
    if extra_open:
        failures.append(f"scorecard has open gates not in ledger: {extra_open}")

    for pillar in scorecard.get("pillars", []):
        if not pillar.get("lock_ledger_paths"):
            failures.append(f"{pillar.get('id')} has no lock_ledger_paths")
        if not pillar.get("production_ready") and not pillar.get("open_production_gates"):
            failures.append(f"{pillar.get('id')} has no open_production_gates")
        if not pillar.get("locked_artifacts"):
            failures.append(f"{pillar.get('id')} has no locked_artifacts")

    return failures


def main() -> int:
    failures = validate()
    if failures:
        print("product lock-ledger check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print("OK - product lock-ledger check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
