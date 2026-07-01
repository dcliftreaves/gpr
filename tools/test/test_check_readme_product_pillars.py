#!/usr/bin/env python3
"""Regression-test README product-pillar framing checks."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/test/check_readme_product_pillars.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("check_readme_product_pillars_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = import_tool()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        readme = tmp / "README.md"
        scorecard = tmp / "PRODUCT_PILLAR_SCORECARD.md"
        docs_dir = tmp / "docs"
        docs_dir.mkdir()
        lock_ledger = docs_dir / "PRODUCT_LOCK_LEDGER.md"

        good = (ROOT / "README.md").read_text(encoding="utf-8")
        readme.write_text(good, encoding="utf-8")
        scorecard.write_text(
            "\n".join(
                (
                    "| Best RAW stills | 90% |",
                    "| GoPro RAW video MVP | 80% |",
                    "| Premium still/SR | 60% |",
                    "| PSF-aware RAW video improvement | 44% |",
                    "The percentages are production-readiness burn-down estimates.",
                    "not regression signals for locked artifacts",
                    "candidate-only patch-dictionary retrieval pass regresses the hard X2D holdout",
                    "Current candidate-only local/full-crop/global-context statistics are not enough for simple CNN or nearest-neighbor transfer",
                    "deeper gated pyramid U-Net",
                    "premium_still_sr_patch_dictionary_x2dholdout_20260630/patch_dictionary_probe.json",
                )
            ),
            encoding="utf-8",
        )
        lock_ledger.write_text(
            "\n".join(
                (
                    "a locked path regresses only when its own committed gate",
                    "## Locked Paths",
                    "Mission 1 4K cleanup",
                    "Mission 1 8K SR",
                    "Mission 1 Pi stand-in raw-video encode",
                    "## Open Production Gates",
                    "Real Mission 1 camera-role raw-video closure",
                    "Premium still-SR promotion",
                    "PSF-aware raw-video replacement",
                )
            ),
            encoding="utf-8",
        )
        failures = module.validate(readme, scorecard)
        if failures:
            print(f"valid README unexpectedly failed: {failures}", file=sys.stderr)
            return 1

        readme.write_text(good.replace("**3. Premium still/SR**", "**3. Offline tooling**"), encoding="utf-8")
        failures = module.validate(readme, scorecard)
        if not failures or not any("Premium still/SR" in failure for failure in failures):
            print(f"missing premium pillar did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

        readme.write_text(good.replace("| Premium still/SR | **60%**", "| Premium still/SR | **95%**"), encoding="utf-8")
        failures = module.validate(readme, scorecard)
        if not failures or not any("Premium still/SR" in failure and "expected 60%" in failure for failure in failures):
            print(f"wrong premium percentage did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

        readme.write_text(
            good
            + "\n/Volumes/OWC_8TB/gpr_work/artifacts/"
            "mission1_8k_sr_with_without_cnn_review_20260630/"
            "mission1_8k_sr_with_without_cnn_contact_review_42f_prores.mov\n",
            encoding="utf-8",
        )
        failures = module.validate(readme, scorecard)
        if not failures or not any("rejected or superseded artifact" in failure for failure in failures):
            print(f"rejected 8K dashboard-video artifact did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

        readme.write_text(
            good
            + "\n/Volumes/OWC_8TB/gpr_work/artifacts/"
            "mission1_8k_continuous_cnn_ab_20260630/"
            "mission42_no_8k_sr_cnn_8k_lanczos_from_4kcnn_42f_20p_prores.mov\n",
            encoding="utf-8",
        )
        failures = module.validate(readme, scorecard)
        if not failures or not any("rejected or superseded artifact" in failure for failure in failures):
            print(f"older no-8K-SR-only artifact did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

        readme.write_text(good, encoding="utf-8")
        scorecard.write_text(
            scorecard.read_text(encoding="utf-8").replace(
                "candidate-only patch-dictionary retrieval pass regresses the hard X2D holdout",
                "candidate-only retrieval was tried",
            ),
            encoding="utf-8",
        )
        failures = module.validate(readme, scorecard)
        if not failures or not any("patch-dictionary" in failure for failure in failures):
            print(f"stale premium still-SR scorecard blocker did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

    print("test_check_readme_product_pillars: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
