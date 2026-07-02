#!/usr/bin/env python3
"""Regression test for the premium still-SR gate receipt skeleton."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "tools/build_premium_still_sr_gate_receipt.py"
CHECKER = ROOT / "tools/check_product_pillar_receipts.py"


def temp_root() -> Path:
    if os.environ.get("GPR_TMPDIR"):
        root = Path(os.environ["GPR_TMPDIR"])
    elif Path("/Volumes/OWC_8TB/gpr_work/tmp").exists():
        root = Path("/Volumes/OWC_8TB/gpr_work/tmp")
    else:
        root = Path(tempfile.gettempdir())
    root.mkdir(parents=True, exist_ok=True)
    return root


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="gpr_still_sr_gate_", dir=temp_root()) as tmp:
        out_dir = Path(tmp) / "still_sr"
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(out_dir),
                "--camera-count",
                "2",
                "--fifty-mp-or-larger-count",
                "1",
                "--hundred-mp-or-larger-count",
                "1",
                "--cfa-phase",
                "RGGB",
                "--cfa-phase",
                "GBRG",
            ],
            check=True,
        )
        receipt = out_dir / "premium_still_sr_gate_receipt.json"
        subprocess.run([sys.executable, str(CHECKER), str(receipt)], check=True)

        payload = json.loads(receipt.read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.premium_still_sr_gate.v1"
        assert payload["production_ready"] is False
        assert payload["fixture_summary"]["hundred_mp_or_larger_count"] == 1
        assert payload["runtime_policy"]["runtime_inputs"] == ["candidate_raw", "camera_metadata"]
        assert payload["runtime_policy"]["no_ref_runtime"] is False
        assert payload["promotion_metrics"]["full_frame_gate_50mp_row_count"] == 0
        assert payload["performance"]["render_seconds_per_100mp_frame"] == 0.0
        assert payload["noise_policy"]["exact_sidecars_only"] is False
        assert payload["candidate"]["checkpoint_sha256"]
        for ref in payload["outputs"].values():
            assert Path(ref["path"]).exists()
            assert len(ref["sha256"]) == 64

        bad = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(Path(tmp) / "bad"),
                "--production-ready",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert bad.returncode == 2, bad
        assert "--production-ready requires --real-artifacts" in bad.stderr

        real_missing_paths = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(Path(tmp) / "real_missing_paths"),
                "--real-artifacts",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert real_missing_paths.returncode == 2, real_missing_paths
        assert "--real-artifacts requires --editable-dng" in real_missing_paths.stderr

        real_root = Path(tmp) / "real_inputs"
        real_root.mkdir()
        editable_dng = real_root / "candidate.dng"
        editable_gpr = real_root / "candidate.gpr"
        review_media = real_root / "candidate.tiff"
        dashboard = real_root / "dashboard.html"
        editable_dng.write_bytes(b"editable dng fixture\n")
        editable_gpr.write_bytes(b"editable gpr fixture\n")
        review_media.write_bytes(b"review media fixture\n")
        dashboard.write_text("<!doctype html><title>dashboard</title>\n", encoding="utf-8")

        prod_out = Path(tmp) / "production"
        subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(prod_out),
                "--real-artifacts",
                "--editable-dng",
                str(editable_dng),
                "--editable-gpr",
                str(editable_gpr),
                "--review-media",
                str(review_media),
                "--dashboard-artifact",
                str(dashboard),
                "--pipeline-id",
                "premium_still_sr_candidate_fixture",
                "--checkpoint-sha256",
                "c" * 64,
                "--camera-count",
                "2",
                "--fifty-mp-or-larger-count",
                "1",
                "--hundred-mp-or-larger-count",
                "1",
                "--cfa-phase",
                "RGGB",
                "--cfa-phase",
                "GBRG",
                "--passed-gate",
                "--no-ref-runtime",
                "--forbidden-source-content-absent",
                "--full-frame-gate-50mp-passed",
                "--full-frame-gate-100mp-passed",
                "--full-frame-gate-50mp-row-count",
                "3",
                "--full-frame-gate-100mp-row-count",
                "3",
                "--median-mae-reduction-pct-50mp",
                "16.0",
                "--median-mae-reduction-pct-100mp",
                "15.5",
                "--worst-row-mae-reduction-pct-50mp",
                "0.1",
                "--worst-row-mae-reduction-pct-100mp",
                "0.0",
                "--editor-latitude-passed",
                "--beats-current-baseline",
                "--render-seconds-per-50mp-frame",
                "12.0",
                "--render-seconds-per-100mp-frame",
                "28.0",
                "--peak-rss-gb",
                "9.5",
                "--raw-noise-signal-audit-passed",
                "--noise-policy-exact-sidecars-only",
                "--noise-policy-forbids-source-residual-noise",
                "--production-ready",
            ],
            check=True,
        )
        prod_receipt = prod_out / "premium_still_sr_gate_receipt.json"
        subprocess.run([sys.executable, str(CHECKER), str(prod_receipt)], check=True)
        prod_payload = json.loads(prod_receipt.read_text(encoding="utf-8"))
        assert prod_payload["production_ready"] is True
        assert prod_payload["outputs"]["editable_dng"]["path"] == str(editable_dng)
        assert prod_payload["runtime_policy"]["no_ref_runtime"] is True
        assert prod_payload["promotion_metrics"]["median_mae_reduction_pct_100mp"] == 15.5

        forbidden_runtime = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--out-dir",
                str(Path(tmp) / "forbidden_runtime"),
                "--real-artifacts",
                "--editable-dng",
                str(editable_dng),
                "--editable-gpr",
                str(editable_gpr),
                "--review-media",
                str(review_media),
                "--dashboard-artifact",
                str(dashboard),
                "--checkpoint-sha256",
                "c" * 64,
                "--camera-count",
                "2",
                "--fifty-mp-or-larger-count",
                "1",
                "--hundred-mp-or-larger-count",
                "1",
                "--runtime-input",
                "Source_Raw",
                "--runtime-input",
                "JPG-target",
                "--passed-gate",
                "--no-ref-runtime",
                "--forbidden-source-content-absent",
                "--full-frame-gate-50mp-passed",
                "--full-frame-gate-100mp-passed",
                "--full-frame-gate-50mp-row-count",
                "3",
                "--full-frame-gate-100mp-row-count",
                "3",
                "--median-mae-reduction-pct-50mp",
                "16.0",
                "--median-mae-reduction-pct-100mp",
                "15.5",
                "--worst-row-mae-reduction-pct-50mp",
                "0.1",
                "--worst-row-mae-reduction-pct-100mp",
                "0.0",
                "--editor-latitude-passed",
                "--beats-current-baseline",
                "--render-seconds-per-50mp-frame",
                "12.0",
                "--render-seconds-per-100mp-frame",
                "28.0",
                "--peak-rss-gb",
                "9.5",
                "--raw-noise-signal-audit-passed",
                "--noise-policy-exact-sidecars-only",
                "--noise-policy-forbids-source-residual-noise",
                "--production-ready",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert forbidden_runtime.returncode == 2, forbidden_runtime
        assert "forbidden production input(s): JPG-target, Source_Raw" in forbidden_runtime.stderr

    print("test_build_premium_still_sr_gate_receipt: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
