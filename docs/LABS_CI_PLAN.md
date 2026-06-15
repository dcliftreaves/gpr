# Labs CI Plan

Last refreshed: 2026-06-14

Labs readiness needs two CI layers: hosted source-level checks and target or
self-hosted media/runtime checks. Hosted CI should not pretend to prove target
capture behavior.

## Hosted CI

Current hosted CI should continue to cover:

- sensitive-content guard and history guard,
- repo artifact hygiene,
- release evidence manifest,
- production artifact inventory,
- C build on Linux and macOS,
- `.gvid` header and stream validation via `test_video_format`,
- real encoded `.gvid` validation via `test_video_full_chain`,
- Python `.gvid` pack and metadata smokes,
- simulated Labs target-bench receipt schema and interruption smoke,
- registry consistency and ship-pipeline receipt audit.

## Target Or Self-Hosted CI

Required for Labs intake before firmware-readiness claims:

| lane | purpose |
|---|---|
| Pi 5 sustained capture | 10 minute stand-in capture, `.gvid` validation, write throughput, memory, temperature, drops |
| Mac/M-series review export | `.gvid` to review MOV/ProRes, timing and memory receipt |
| Artifact bundle verify | download bundle, checksum, validate `.gvid`, validate metadata, inspect receipt schema |
| Interruption recovery | kill capture mid-stream, recover complete frames, reject truncated final frame |

## Skip Policy

Hosted CI may skip target-only media tests, but each skip must say why. A skipped
target lane is not a pass for firmware readiness.
