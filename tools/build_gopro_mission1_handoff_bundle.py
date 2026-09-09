#!/usr/bin/env python3
"""Build a compact GoPro Mission 1 handoff bundle.

The bundle is intentionally small: one valid 4K `.gvid` sample, compact
receipts, review media, the quick-validation dry-run receipt, and the docs a
firmware reviewer needs to reproduce or block the camera closure run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from gvid_metadata import read_gvid_frames


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTERNAL = Path("/Volumes/OWC_8TB/gpr_work")
DEFAULT_SAMPLE_GVID = DEFAULT_EXTERNAL / "artifacts/mission1_corrected_q8_local_gvid_120f_20260617/capture.gvid"
DEFAULT_PRODUCER_REPORT = DEFAULT_EXTERNAL / "artifacts/mission1_stream_source_encoder_20260628/run_4096x3072_8f/producer_report.json"
DEFAULT_CLOSURE_ROOT = DEFAULT_EXTERNAL / "artifacts/mission1_camera_closure_run_20260625/current_standin_followup"
DEFAULT_REVIEW_MEDIA = (
    ROOT / "docs/img/readme_showcase.webp",
    ROOT / "docs/img/readme_mission1_native12_100pct.png",
)
DEFAULT_DOCS = (
    ROOT / "README.md",
    ROOT / "docs/GOPRO_MISSION1_QUICK_VALIDATION.md",
    ROOT / "docs/LABS_FIRMWARE_API.md",
    ROOT / "docs/LABS_MISSION1_RUNBOOK.md",
    ROOT / "docs/PRODUCTION_CAPTURE_REQUIREMENTS.md",
    ROOT / "docs/PRODUCTION_CAPTURE_REQUIREMENTS.json",
    ROOT / "docs/RELEASE_ARTIFACTS.md",
    ROOT / "docs/release_evidence_manifest.json",
    ROOT / "tools/run_gopro_mission1_quick_validation.py",
    ROOT / "tools/check_mission1_camera_source_probe.py",
)
DEFAULT_CI_RUN = "https://github.com/dcliftreaves/gpr/actions/runs/0"


def run(cmd: list[str], *, cwd: Path = ROOT, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def git_commit() -> str:
    proc = run(["git", "rev-parse", "HEAD"])
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip()


def copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        raise FileNotFoundError(f"missing bundle input: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_clipped_gvid(src: Path, dst: Path, *, frame_count: int) -> int:
    """Copy the first N complete .gvid frames while fixing the frame-count hint."""
    if frame_count <= 0:
        raise ValueError("--sample-frame-count must be positive")
    frames = read_gvid_frames(src)
    if not frames:
        raise ValueError(f"{src} contains no .gvid frames")
    selected = frames[: min(frame_count, len(frames))]
    dst.parent.mkdir(parents=True, exist_ok=True)
    header = bytearray(src.read_bytes()[:32])
    # Header layout is <IBBHHHIIIII>; frame_count_hint is the final uint32.
    header[28:32] = len(selected).to_bytes(4, "little")
    with src.open("rb") as inp, dst.open("wb") as out:
        out.write(header)
        for frame in selected:
            frame_start = int(frame["payload_offset"]) - 16
            frame_end = int(frame["payload_offset"]) + int(frame["payload_size"])
            inp.seek(frame_start)
            remaining = frame_end - frame_start
            while remaining:
                chunk = inp.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise EOFError(f"{src} ended while clipping frame {frame['frame_index']}")
                out.write(chunk)
                remaining -= len(chunk)
    read_gvid_frames(dst)
    return len(selected)


def validate_sample_decode(sample: Path, decoder: Path) -> None:
    if not decoder.is_file():
        raise FileNotFoundError(f"missing fused decoder for sample validation: {decoder}")
    frames = read_gvid_frames(sample)
    if not frames:
        raise ValueError(f"{sample} contains no frames")
    with tempfile.TemporaryDirectory(prefix="gpr_handoff_decode_") as td:
        root = Path(td)
        payload = root / "frame0.gpr"
        raw = root / "frame0.raw"
        frame = frames[0]
        with sample.open("rb") as inp, payload.open("wb") as out:
            inp.seek(int(frame["payload_offset"]))
            out.write(inp.read(int(frame["payload_size"])))
        proc = run([
            str(decoder),
            str(payload),
            "4096",
            "3072",
            str(raw),
            "4k_raw_1x",
        ])
        if proc.returncode != 0:
            raise RuntimeError(
                "sample .gvid payload failed fused decode validation: "
                + (proc.stderr.strip() or proc.stdout.strip() or f"rc={proc.returncode}")
            )
        expected = 4096 * 3072 * 2
        if raw.stat().st_size != expected:
            raise RuntimeError(f"decoded raw size {raw.stat().st_size} != expected {expected}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_quick_validation_dry_run(args: argparse.Namespace, out: Path) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "tools/run_gopro_mission1_quick_validation.py"),
        "--dry-run",
        "--output-dir",
        "/mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera",
        "--collection-output-dir",
        "/mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera_compact",
        "--repo-root",
        "/mnt/ssd/gpr_work/worktrees/current_goal_sync",
        "--raw",
        args.camera_raw_path,
    ]
    proc = run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"quick validation dry-run failed:\n{proc.stderr}\n{proc.stdout}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"quick validation dry-run emitted invalid JSON: {exc}") from exc
    write_json(out, payload)


def write_readme(args: argparse.Namespace, out: Path) -> None:
    text = f"""# GoPro Mission 1 Handoff Bundle

This bundle is a compact review package for the current GPR Mission 1 prototype.
It is not final camera-production evidence by itself.

## What Is Included

- `samples/mission1_4k_stream_source_8f.gvid`: compact 4096 x 3072 `.gvid` sample for container and optional payload-decode validation.
- `receipts/`: current Pi 5 stand-in closure receipts plus a quick-validation dry-run receipt.
- `review/`: compact visual assets from the repo README.
- `docs/`: the GoPro quick validation guide, firmware ABI, runbook, production capture requirements, release artifact rules, and release evidence manifest.
- `hashes/sha256sums.txt` and `manifest.json`: verifier inputs generated by `tools/build_labs_bundle.py`.

## What This Proves

- The repo has a one-command camera validation path: `python3 tools/run_gopro_mission1_quick_validation.py`.
- The stand-in receipts preserve the active 20 fps Mission 1 floor for 4K Bayer `.gvid` capture and 1024 x 768 preview.
- The `.gvid` sample is real container data, not a wrapped JPEG or wrapped camera `.GPR` payload.

## Product Pillars In This Bundle

- **RAW stills**: represented by the repo README and release evidence manifest; stills remain a separate locked product surface, not the main purpose of this Mission 1 handoff.
- **RAW video MVP**: directly represented by the 4K Bayer `.gvid` sample, stand-in encode/preview receipts, firmware API, and quick-validation command.
- **Premium still/SR**: represented by the release evidence manifest and README status; current models are review evidence, not firmware requirements.
- **RAW video reconstruction**: represented by the release evidence manifest and README status; current 4K cleanup/8K SR paths are approved offline/post baselines, while PSF-aware replacement work remains optional research.

The packaged production capture requirements are the closure contract for
missing real fixtures, darkframes, camera-role receipts, controlled PSF pairs,
and model-promotion receipts.

## What It Does Not Prove

- It does not prove Mission 1 sensor/DMA capture unless `camera_handoff_receipt.json` comes from `target.role=camera`.
- It does not prove Mission 1 rear-display presentation unless `preview_ui_receipt.json` has the UI path executed and visually checked.
- It does not claim the offline 4K cleanup or 8K SR CNN runs on camera hardware.

## Verify

From the source repo:

```bash
python3 tools/verify_labs_bundle.py {out.parent.name}/manifest.json
(cd {out.parent.name} && shasum -a 256 -c hashes/sha256sums.txt)
```

## Camera Closure

On a Mission 1 development target with the camera raw endpoint available:

```bash
python3 tools/run_gopro_mission1_quick_validation.py \\
  --output-dir /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera \\
  --collection-output-dir /mnt/ssd/gpr_work/artifacts/mission1_quick_validation/current_camera_compact \\
  --repo-root /mnt/ssd/gpr_work/worktrees/current_goal_sync \\
  --raw {args.camera_raw_path}
```

The production blocker is closed only when the resulting camera-role receipts
validate and report zero drops at the active 20 fps floor.
"""
    out.write_text(text, encoding="utf-8")


def add_artifact(artifacts: list[str], rel: str, kind: str) -> None:
    artifacts.append(f"{rel}:{kind}")


def build_bundle(args: argparse.Namespace) -> dict[str, Any]:
    bundle_root = args.bundle_root.resolve()
    if bundle_root.exists():
        if not args.force:
            raise FileExistsError(f"bundle root already exists; pass --force to replace: {bundle_root}")
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True)

    artifacts: list[str] = []
    write_readme(args, bundle_root / "README.md")
    add_artifact(artifacts, "README.md", "text")

    sample_dst = bundle_root / "samples/mission1_4k_stream_source_8f.gvid"
    if args.copy_sample_whole:
        copy_file(args.sample_gvid, sample_dst)
    else:
        write_clipped_gvid(args.sample_gvid, sample_dst, frame_count=args.sample_frame_count)
    if args.require_sample_decode or args.fused_decode_cli:
        if not args.fused_decode_cli:
            raise ValueError("--require-sample-decode requires --fused-decode-cli")
        validate_sample_decode(sample_dst, args.fused_decode_cli)
    add_artifact(artifacts, "samples/mission1_4k_stream_source_8f.gvid", "gvid")

    receipt_sources = [
        (args.labs_target_bench, "receipts/labs_target_bench.json"),
        (args.camera_handoff, "receipts/camera_handoff_receipt.json"),
        (args.preview_ui, "receipts/preview_ui_receipt.json"),
        (args.closure_run, "receipts/mission1_camera_closure_run.json"),
    ]
    if args.producer_report:
        receipt_sources.append((args.producer_report, "receipts/source_stream_producer_report.json"))
    for src, rel in receipt_sources:
        copy_file(src, bundle_root / rel)
        add_artifact(artifacts, rel, "json")

    run_quick_validation_dry_run(args, bundle_root / "receipts/quick_validation_dry_run.json")
    add_artifact(artifacts, "receipts/quick_validation_dry_run.json", "json")

    for src in args.review_media:
        rel = f"review/{src.name}"
        copy_file(src, bundle_root / rel)
        add_artifact(artifacts, rel, "media")

    for src in args.doc:
        if src == ROOT / "README.md":
            rel = "docs/REPO_README.md"
        elif src.is_relative_to(ROOT):
            rel = "docs/source/" + str(src.relative_to(ROOT)).replace("/", "__")
        else:
            rel = "docs/" + src.name
        copy_file(src, bundle_root / rel)
        add_artifact(artifacts, rel, "json" if src.suffix == ".json" else "text")

    cmd = [
        sys.executable,
        str(ROOT / "tools/build_labs_bundle.py"),
        str(bundle_root),
        "--repo-commit",
        args.repo_commit,
        "--ci-run",
        args.ci_run,
        "--target-name",
        args.target_name,
        "--target-role",
        args.target_role,
        "--note",
        "GoPro Mission 1 handoff bundle; camera-role sensor/DMA/storage/display receipt remains required for production closure.",
        "--note",
        "Includes compact stand-in receipts, one 4K .gvid sample, quick-validation dry-run receipt, production capture requirements, and firmware-facing docs.",
        "--product-pillars-from",
        str(ROOT / "docs/release_evidence_manifest.json"),
    ]
    for artifact in artifacts:
        cmd.extend(["--artifact", artifact])
    proc = run(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"build_labs_bundle failed:\n{proc.stderr}\n{proc.stdout}")

    verify = run([sys.executable, str(ROOT / "tools/verify_labs_bundle.py"), str(bundle_root / "manifest.json"), "--json"])
    if verify.returncode != 0:
        raise RuntimeError(f"verify_labs_bundle failed:\n{verify.stderr}\n{verify.stdout}")

    return {
        "bundle_root": str(bundle_root),
        "manifest": str(bundle_root / "manifest.json"),
        "artifact_count": len(artifacts) + 1,
        "verification": json.loads(verify.stdout),
    }


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle_root", type=Path)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--repo-commit", default=git_commit())
    ap.add_argument("--ci-run", default=DEFAULT_CI_RUN)
    ap.add_argument("--target-name", default="Pi 5 stand-in")
    ap.add_argument("--target-role", default="stand-in")
    ap.add_argument("--camera-raw-path", default="/dev/mission1/sensor_dma_ring")
    ap.add_argument("--sample-gvid", type=Path, default=DEFAULT_SAMPLE_GVID)
    ap.add_argument("--sample-frame-count", type=int, default=8)
    ap.add_argument("--copy-sample-whole", action="store_true")
    ap.add_argument("--fused-decode-cli", type=Path)
    ap.add_argument("--require-sample-decode", action="store_true")
    ap.add_argument("--producer-report", type=Path, default=DEFAULT_PRODUCER_REPORT)
    ap.add_argument("--labs-target-bench", type=Path, default=DEFAULT_CLOSURE_ROOT / "labs_target_bench.json")
    ap.add_argument("--camera-handoff", type=Path, default=DEFAULT_CLOSURE_ROOT / "camera_handoff_receipt.json")
    ap.add_argument("--preview-ui", type=Path, default=DEFAULT_CLOSURE_ROOT / "preview_ui_receipt.json")
    ap.add_argument("--closure-run", type=Path, default=DEFAULT_CLOSURE_ROOT / "mission1_camera_closure_run.json")
    ap.add_argument("--review-media", type=Path, action="append", default=list(DEFAULT_REVIEW_MEDIA))
    ap.add_argument("--doc", type=Path, action="append", default=list(DEFAULT_DOCS))
    return ap


def main() -> int:
    args = parser().parse_args()
    try:
        result = build_bundle(args)
    except Exception as exc:
        print(f"build_gopro_mission1_handoff_bundle: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
