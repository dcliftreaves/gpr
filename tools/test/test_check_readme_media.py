#!/usr/bin/env python3
"""Regression-test README media freshness checks."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/test/check_readme_media.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("check_readme_media_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = import_tool()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        clean_svg = tmp / "clean.svg"
        clean_svg.write_text(
            "<svg><text>Mission native12 .gvid 20.50 fps wall</text></svg>\n",
            encoding="utf-8",
        )
        failures: list[str] = []
        module.validate_claim_freshness(clean_svg, "clean.svg", failures)
        if failures:
            print(f"clean SVG unexpectedly failed: {failures}", file=sys.stderr)
            return 1

        stale_svg = tmp / "stale.svg"
        stale_svg.write_text(
            "<svg><text>latest strict run: 19.98 fps</text></svg>\n",
            encoding="utf-8",
        )
        failures = []
        module.validate_claim_freshness(stale_svg, "stale.svg", failures)
        if not failures or "latest strict run: 19.98 fps" not in failures[0]:
            print(f"stale SVG did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

        stale_md = tmp / "README.md"
        stale_md.write_text("Preview capture\n", encoding="utf-8")
        failures = []
        old_readme = module.README
        module.README = stale_md
        module.validate_claim_freshness(stale_md, "README.md", failures)
        module.README = old_readme
        if not failures or "Preview capture" not in failures[0]:
            print(f"stale README did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

    print("test_check_readme_media: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
