#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools/cnn/bench_bayer_detail_residual_sidecar_native.py"


def write_fake_native_tool(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import shutil
import sys
from pathlib import Path

cmd = sys.argv[1]
if cmd == "encode":
    codec, clean, sidecar = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    width, height = int(sys.argv[5]), int(sys.argv[6])
    receipt = Path(sys.argv[12])
    sidecar.write_bytes(codec.read_bytes() + b"sidecar")
    receipt.write_text(json.dumps({
        "schema": "gpr.bayer_detail_residual_sidecar_native.v1",
        "cmd": "encode",
        "width": width,
        "height": height,
        "elapsed_ms": float(os.environ.get("BDRS_ENCODE_THREADS", "1")),
        "encode_threads": int(os.environ.get("BDRS_ENCODE_THREADS", "1")),
        "sidecar_bytes": sidecar.stat().st_size,
        "value_count": 1,
        "codec_clean_rmse": 3.0,
        "output_clean_rmse": 0.0
    }))
elif cmd == "decode":
    codec, out = Path(sys.argv[2]), Path(sys.argv[4])
    width, height = int(sys.argv[5]), int(sys.argv[6])
    receipt = Path(sys.argv[8])
    shutil.copyfile(codec, out)
    receipt.write_text(json.dumps({
        "schema": "gpr.bayer_detail_residual_sidecar_native.v1",
        "cmd": "decode",
        "width": width,
        "height": height,
        "elapsed_ms": 2.0,
        "encode_threads": 0,
        "sidecar_bytes": Path(sys.argv[3]).stat().st_size,
        "value_count": 1,
        "codec_clean_rmse": 3.0,
        "output_clean_rmse": 2.0
    }))
else:
    raise SystemExit(2)
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_bench_cli() -> None:
    tmp_parent = os.environ.get("GPR_TMPDIR") or os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(dir=tmp_parent) as td:
        root = Path(td)
        low = root / "low"
        clean = root / "clean"
        low.mkdir()
        clean.mkdir()
        arr = np.full((8, 8), 1000, dtype=np.uint16)
        arr.tofile(low / "A.raw")
        arr.tofile(clean / "A.raw")
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "width12": 8,
                    "height12": 8,
                    "images": [
                        {
                            "image_id": "A",
                            "low_source_raw": str(low / "A.raw"),
                            "low_clean_raw": str(clean / "A.raw"),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        fake_tool = root / "fake_bdrs.py"
        write_fake_native_tool(fake_tool)
        out_dir = root / "bench"
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--manifest",
                str(manifest),
                "--tool",
                str(fake_tool),
                "--out-dir",
                str(out_dir),
                "--repo",
                str(REPO),
                "--threads",
                "1,4",
            ],
            check=True,
            cwd=REPO,
        )
        payload = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        assert payload["schema"] == "gpr.native_bayer_detail_residual_sidecar_thread_sweep.v1"
        assert payload["threads"] == [1, 4]
        assert len(payload["summary_rows"]) == 2
        assert all(row["all_match_baseline_sidecar"] for row in payload["summary_rows"])
        assert not list(out_dir.glob("threads_*/sidecar/*.bdrs"))


if __name__ == "__main__":
    test_bench_cli()
    print("test_bench_bayer_detail_residual_sidecar_native: PASS")
