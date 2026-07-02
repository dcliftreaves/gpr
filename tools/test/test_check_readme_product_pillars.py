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
        img_dir = docs_dir / "img"
        img_dir.mkdir()
        lock_ledger = docs_dir / "PRODUCT_LOCK_LEDGER.md"
        status_matrix = img_dir / "readme_status_matrix.svg"

        good = (ROOT / "README.md").read_text(encoding="utf-8")
        readme.write_text(good, encoding="utf-8")
        scorecard.write_text(
            "\n".join(
                (
                    "| Best RAW stills | 92% |",
                    "| GoPro RAW video MVP | 80% |",
                    "| Premium still/SR | 60% |",
                    "| RAW video reconstruction improvement | 100% |",
                    "PSF-conditioned replacement training are preserved as optional research evidence",
                    "separate Research Parking Lot for PSF/SR follow-ups",
                    "excluded from production action counts and readiness percentages",
                    "psf_gradient_focus_from_detail_s400_fw6_gw12_s300",
                    "mission1_native12_8k_sr_coord_detail_psf_focus_step0075_v1",
                    "Mission gradient median +0.253",
                    "The percentages are production-readiness burn-down estimates.",
                    "not regression signals for locked artifacts",
                    "deduplicated raw-supervision NPZ collapses it to 117 unique scene/crop raw-domain rows with zero raw conflicts",
                    "same-scene candidate-signal and frequency-filter probes regress",
                    "Current candidate-only local/full-crop/global-context/masked-context statistics are not enough",
                    "deeper gated pyramid U-Net",
                    "premium_still_sr_patch_dictionary_x2dholdout_20260630/patch_dictionary_probe.json",
                    "95 runtime-safe rendered-HF, raw-CFA residual, clean-signal, and clean-source pair training receipts",
                    "newest clean-source Restormer pair rows remain far below promotion",
                    "zero promotable rows",
                    "4.03 percent held-out MAE recovery and 3.75 percent held-out RMSE recovery",
                    "15 percent / 15 percent promotion threshold",
                    "full 12k-step X2D scene-holdout window-attention teacher run",
                    "-0.030 percent MAE",
                    "-0.098 percent RMSE",
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
        status_matrix.write_text(
            "\n".join(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg">',
                    "<title>GPR four-pillar production readiness</title>",
                    "<text>RAW stills</text>",
                    "<text>92%</text>",
                    "<text>GoPro RAW video MVP</text>",
                    "<text>80%</text>",
                    "<text>Premium still/SR</text>",
                    "<text>60%</text>",
                    "<text>Video reconstruction</text>",
                    "<text>100%</text>",
                    "<text>PSF / blur modeling is parked, not blocking the release.</text>",
                    "<text>Controlled high/low Mission 1 pairs</text>",
                    "<text>same .gvid, editable raw, ProRes, dashboard, timing, memory, and hash receipts</text>",
                    "</svg>",
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

        readme.write_text(good, encoding="utf-8")
        status_matrix.write_text(status_matrix.read_text(encoding="utf-8").replace("<text>60%</text>", "<text>95%</text>"), encoding="utf-8")
        failures = module.validate(readme, scorecard)
        if not failures or not any("readme_status_matrix.svg" in failure and "Premium still/SR" in failure for failure in failures):
            print(f"wrong SVG premium percentage did not trigger expected failure: {failures}", file=sys.stderr)
            return 1
        status_matrix.write_text(status_matrix.read_text(encoding="utf-8").replace("<text>95%</text>", "<text>60%</text>"), encoding="utf-8")

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
                "same-scene candidate-signal and frequency-filter probes regress",
                "some candidate probes were tried",
            ),
            encoding="utf-8",
        )
        failures = module.validate(readme, scorecard)
        if not failures or not any("frequency-filter" in failure for failure in failures):
            print(f"stale premium still-SR scorecard blocker did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

        scorecard.write_text(
            (ROOT / "docs/PRODUCT_PILLAR_SCORECARD.md").read_text(encoding="utf-8").replace(
                "95 runtime-safe rendered-HF, raw-CFA residual, clean-signal, and",
                "many runtime-safe rendered-HF, raw-CFA residual, clean-signal, and",
            ),
            encoding="utf-8",
        )
        failures = module.validate(readme, scorecard)
        if not failures or not any("95 runtime-safe" in failure for failure in failures):
            print(f"stale premium still-SR scoreboard count did not trigger expected failure: {failures}", file=sys.stderr)
            return 1

    print("test_check_readme_product_pillars: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
