# Labs CI Plan

Last refreshed: 2026-06-15

Labs readiness needs two CI layers: hosted source-level checks and target or
self-hosted media/runtime checks. Hosted CI should not pretend to prove target
capture behavior.

## Hosted CI

Current hosted CI should continue to cover:

- sensitive-content guard and history guard,
- repo artifact hygiene,
- release evidence manifest,
- Labs readiness guard tying the firmware-intake docs, release manifest, and
  CI workflow to the current Pi-proxy / camera-hardware-pending evidence split,
- Labs target receipt guard tying the release manifest to strict Pi receipt
  metrics when external artifacts are mounted,
- production artifact inventory,
- C build on Linux and macOS,
- `.gvid` header and stream validation via `test_video_format`,
- real encoded `.gvid` validation via `test_video_full_chain`,
- Python `.gvid` pack and metadata smokes,
- deterministic Labs bundle manifest/checksum builder smoke,
- simulated Labs target-bench receipt schema and interruption smoke,
- camera-handoff receipt schema smoke for stand-in, blocked camera, and
  invalid promoted-camera cases,
- registry consistency and ship-pipeline receipt audit.

## Target Or Self-Hosted CI

Required for Labs intake before firmware-readiness claims:

| lane | purpose |
|---|---|
| Pi 5 sustained capture | 10 minute stand-in capture, `.gvid` validation, write throughput, memory, temperature, drops |
| Mac/M-series review export | `.gvid` to review MOV/ProRes, timing and memory receipt |
| Artifact bundle verify | download bundle, checksum, validate `.gvid`, validate metadata, inspect receipt schema |
| Interruption recovery | kill capture mid-stream, recover complete frames, reject truncated final frame |

The executable target lane is `.github/workflows/labs-target.yml`. It is
manual-only (`workflow_dispatch`) and requires a self-hosted runner labeled
`self-hosted`, `Linux`, `ARM64`, and `gpr-labs-pi5`. It builds `bench_fused`,
runs `tools/run_labs_target_bench.py` against a caller-supplied raw Bayer file,
writes the compact `labs_target_bench.json` receipt under external storage, and
fails the workflow unless the strict verdict passes. The heavy `.gvid` and frame
payloads stay on the external target drive; GitHub Actions uploads only the JSON
receipt and stdout tail.

## Skip Policy

Hosted CI may skip target-only media tests, but each skip must say why. A skipped
target lane is not a pass for firmware readiness.
