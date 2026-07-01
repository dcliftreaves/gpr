#!/usr/bin/env python3
"""Regression test for the darkframe provenance review packet builder."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/build_darkframe_provenance_review_packet.py"


def import_tool():
    spec = importlib.util.spec_from_file_location("build_darkframe_provenance_review_packet", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = import_tool()
    with tempfile.TemporaryDirectory(prefix="gpr_darkframe_packet_") as td:
        root = Path(td)
        cand0 = root / "mission0.dng"
        cand1 = root / "mission1.dng"
        cand0.write_bytes(b"mission-darkframe-candidate-0")
        cand1.write_bytes(b"mission-darkframe-candidate-1")
        capture = {
            "schema": "gpr.stills_capture_request.v1",
            "requests": [
                {
                    "id": "mission1_lowest_lift_darkframe_topup",
                    "requirement_id": "mission1_darkframe_stack",
                    "sample_type": "matching_darkframe_topup",
                    "camera": "GoPro Mission 1",
                    "existing_group": "GoPro|MISSION 1|ISO232|RGGB",
                    "existing_candidate_count": 2,
                    "minimum_count": 2,
                    "candidate_paths": [cand0.as_posix(), cand1.as_posix()],
                }
            ],
        }
        packet = module.build_packet(capture, root / "capture_request.json")
        assert packet["schema"] == "gpr.darkframe_provenance_review_packet.v1"
        assert packet["production_ready"] is False
        assert packet["summary"]["review_group_count"] == 1
        assert packet["summary"]["candidate_source_count"] == 2
        assert packet["summary"]["minimum_additional_darkframes_needed"] == 2
        assert packet["summary"]["requirements_still_needing_capture"] == ["mission1_darkframe_stack"]
        group = packet["groups"][0]
        assert group["production_ready"] is False
        assert group["source_provenance_manifest_ready"] is False
        assert group["candidates"][0]["original_sha256"] == module.sha256_file(cand0)
        assert group["provenance_manifest_template"]["schema"] == "gpr.darkframe_source_provenance_manifest.v1"
        assert group["provenance_manifest_template"]["frames"][0]["no_scene_signal"].startswith("<set true")
        html = module.render_html(packet)
        assert "Darkframe Provenance Review Packet" in html
        assert "GoPro Mission 1" in html

        out = root / "out"
        capture_path = root / "capture_request.json"
        capture_path.write_text(json.dumps(capture), encoding="utf-8")
        proc_args = type("Args", (), {"capture_request": capture_path, "output_dir": out})
        data = module.build_packet(module.load_json(proc_args.capture_request), proc_args.capture_request)
        out.mkdir()
        (out / "darkframe_provenance_review_packet.json").write_text(json.dumps(data), encoding="utf-8")
        assert (out / "darkframe_provenance_review_packet.json").is_file()
    print("test_build_darkframe_provenance_review_packet: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
