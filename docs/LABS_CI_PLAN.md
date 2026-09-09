# Labs CI Plan

Last refreshed: 2026-06-25

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
- firmware-facing encoder shim validation via `test_labs_encoder_api`,
- Labs shim target-bench receipt validation via
  `tools/test/test_labs_encoder_bench_cli.sh`,
- real encoded `.gvid` validation via `test_video_full_chain`,
- Python `.gvid` pack and metadata smokes,
- deterministic Labs bundle manifest/checksum builder smoke,
- simulated Labs target-bench receipt schema and interruption smoke,
- camera-handoff receipt schema smoke for stand-in, blocked camera, and
  invalid promoted-camera cases,
- camera preview UI receipt schema smoke for stand-in, blocked camera display,
  and invalid promoted-UI cases,
- camera preview UI receipt builder smoke from target-bench and preview-decode
  receipts,
- Mission 1 camera dispatch input preflight smoke proving camera-role runs
  reject stand-in labels and unset execution flags,
- Mission 1 numbered-list readiness regression covering both the current
  blocked-receipt state and a synthetic production-ready receipt state,
- Mission 1 numbered-list closure plan regression proving the current blockers
  map to concrete replacement receipts, aggregate closure-run validation, and
  final gate,
- Mission 1 camera closure-run validator regression proving the aggregate
  `mission1_camera_closure_run.json` cannot claim production unless both
  firmware handoff and preview UI receipts validate as ready,
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
`labs_encoder_bench_cli`, `fused_decode_cli`, and `gvid_preview_rgb_cli`, writes
a `target_preflight_receipt.json` proving the raw input, output/scratch storage,
optimized bench, public Labs shim, decoder, and preview CLI are present, runs
`tools/run_labs_target_bench.py` against a
caller-supplied raw Bayer file, writes the compact `labs_target_bench.json`
receipt under external storage, converts it to `camera_handoff_receipt.json`,
then runs `tools/run_mission1_camera_closure.py` to generate and validate the
preview decode receipt, `preview_ui_receipt.json`, and aggregate
`mission1_camera_closure_run.json`. The workflow fails unless the strict bench
verdict, handoff receipt, and aggregate closure run all pass their validators.
Dispatch input `bench_binary=bench_fused` is the performance baseline;
`bench_binary=labs_encoder_bench_cli` exercises the firmware-facing public shim
through the same receipt path and should be treated as integration evidence
unless its target receipt also clears the production FPS target.
It also refuses `target_role=camera` dispatches unless sensor/DMA, storage
handoff, UI path, and visual display checks are all explicitly marked executed;
otherwise the run must remain `target_role=stand-in`. That preflight is
implemented by `tools/check_mission1_camera_dispatch_inputs.py` so the same
rule is regression-tested outside the workflow.
The heavy `.gvid` and frame payloads stay on the external target drive; GitHub
Actions uploads only compact JSON receipts and stdout tail.

## Skip Policy

Hosted CI may skip target-only media tests, but each skip must say why. A skipped
target lane is not a pass for firmware readiness.
