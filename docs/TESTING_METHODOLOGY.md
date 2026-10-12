# Testing Methodology

Use the test appropriate to the claim. Passing container validation, codec
regression, a rendered quality gate, or a hardware timing test establishes
different facts.

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| `tools/test/test_gvid_conformance.py` and C stream tests | Container accept/reject and recovery behavior | Payload quality or camera integration |
| `tests/conformance/` | Manual historical bitstream comparison; currently mismatches | A passing release gate or universal perceptual quality |
| `tools/test/test_capabilities.py` | Declared codec cells and regression limits | Every end-to-end workflow or sensor |
| `tests/quality_gates/run_gate.py` | The selected pipeline/class on its specified corpus | Other codecs, models, cameras, or output objectives |
| Target capture/preview receipts | Throughput, memory, drops, storage, and identity on that setup | Camera readiness when the target is a stand-in |
| Release bundle verification | Hashes, inventory, and included stream validity | Fresh hardware execution or new quality measurements |

## Quality signoffs

Read `tests/quality_gates/gates.json` for thresholds and
`pipelines/registry.json` for exact pipeline identities.
[claims_log.md](claims_log.md) contains audited machine-written signoffs;
each must resolve to its matching `runs/<hash>/run.json`.
Do not hand-edit measurements or infer a new pass from prose.

Compare the entire stated pipeline, including codec, model, preprocessing,
demosaic, metadata, and render settings. Report worst-image behavior where
the gate requires it. Bayer PSNR evaluates editable raw reconstruction;
LPIPS and rendered metrics describe a particular render. Neither alone
establishes editing latitude or physical sensor-noise fidelity.

## Timing and reproduction

Record source commit, build configuration, input identity, dimensions, format,
quality/profile, hardware, storage/flush policy, frame count, and output hashes.
Separate end-to-end wall timing from kernel or loop timing. Best-of-three
single-image results are not sustained capture rates.

Full model-backed quality checks require external fixtures/weights and the
appropriate backend hardware. Missing prerequisites are a skip or blocker,
not a pass. Hosted CI cannot substitute for an actual camera-role
sensor/DMA, storage, and display receipt.

[Stills Pi 5 Timing](STILLS_PI5_TIMING.md) and [Video Status](VIDEO_STATUS.md)
summarize existing measurements. [GVID Conformance](GVID_CONFORMANCE.md)
lists focused container checks; [Labs Firmware API](LABS_FIRMWARE_API.md)
defines hardware evidence.
