# High-Level Goal Closure Matrix

Last refreshed: 2026-07-02

This is the shortest completion audit for the active high-level goal. It maps
the four product efforts to the evidence that would make each effort done, the
evidence already locked, and the exact work that can still move the goal.

Use this page before starting another long run. If the proposed work does not
close one of the open gates below or protect one of the locked proofs, it is
research or polish, not production closure.

## Current Completion

| effort | current completion | locked proof | still open |
|---|---:|---|---|
| Raw stills for 50 MP / 100 MP cameras | 92% | 50 MP q0/q3/q8 still tiers, X2D 100MP roundtrip, 12/14/16-bit normal Bayer support, and real RGGB/GBRG/GRBG/BGGR fixture coverage. | Mission 1 and iPhone strict-provenance darkframe sidecars before broad nonzero noise addback is claimed. |
| GoPro RAW video MVP | 80% | Pi 5 stand-in 4096 x 3072 Bayer `.gvid` encode and 1024 x 768 preview decode above the accepted 20+ fps floor, plus `.gvid` validation and Labs handoff tooling. | Actual Mission 1 camera-role receipts for sensor/DMA or ring-buffer input, SD writer, rear display, zero drops, valid `.gvid`, timing, memory, and storage. |
| Premium still/SR | 60% | Still-SR datasets, raw-CFA targets, routed specialists, editor-openability receipts, promotion tooling, and 93 runtime-safe experiment receipts. | A no-REF 50 MP / 100 MP candidate that beats the current still baseline and clears the promotion gate. Current best older runtime-safe recovery is 4.03% MAE / 3.75% RMSE against the 15% / 15% floor; the newest t64 Restormer pair receipts also fail the joint X2D/Z8 holdout gate. |
| Raw video reconstruction / PSF-aware improvement | 100% for the approved current workflow | Approved 4K cleanup and 8K SR baselines with `.gvid`, editable DNG/GPR, standalone ProRes A/B review media, objective review, manual signoff, registry, and release receipts. | No release blocker. Controlled high/low PSF pairs and PSF-conditioned models are optional replacement research until they beat the locked baseline with the same receipt surface. |

## What Would Make The Whole Goal Complete

The full goal is complete only when every row below has direct evidence. A
green CI run is necessary, but it is not sufficient if the evidence below is
missing.

| closure requirement | proving evidence |
|---|---|
| Raw stills are production-ready for the intended 50 MP / 100 MP normal-Bayer surface. | `docs/SHIP_DECISION.md`, `docs/CAPABILITIES.md`, still matrix/capability CI, X2D 100MP visual audit, real normal-Bayer fixture scans, and no new open phase/bit-depth gaps. |
| Camera-noise-aware still compression/addback is safe to claim beyond X2D/Z8. | Mission 1 and iPhone `gpr.camera_noise_calibration.v1` sidecars built from same-camera, same-ISO, no-scene-signal darkframe stacks with source hashes; raw-noise/signal audit passing. |
| GoPro raw-video MVP is firmware-ready. | Mission 1 camera-role closure package from real sensor/DMA or camera ring-buffer source, real SD writer, real rear-display path, zero drops, valid `.gvid`, timing, memory, and storage receipts. |
| Premium still/SR is promoted. | Candidate-only runtime inputs, no REF/source/JPEG image content at render time, 50 MP and 100 MP full-frame rows, positive median MAE/RMSE recovery, nonnegative worst-row recovery, editor-latitude review, editable DNG/GPR receipts, timing, memory, checkpoint/config hashes, and exact-sidecar-only noise policy. |
| Raw-video reconstruction remains shipped. | Locked 4K cleanup and 8K SR gates, hashes, `.gvid`, editable raw, ProRes review, objective review, manual signoff, registry, release manifest, and CI continue to pass. |
| PSF/blur work is correctly scoped. | `docs/BAYER_RESIZE_PSF.md`, PSF audits, and capture requests stay in optional research unless a replacement beats the locked 4K/8K baselines and emits the same production receipt set. |
| Public docs are honest and useful. | README, docs index, product scorecard, lock ledger, burn-down, release manifest, and this matrix agree on locked paths, open gates, percentages, and non-claims. |

## Next Work By Type

| work type | next useful action | why it moves the goal |
|---|---|---|
| Local model work | Run only premium still-SR candidates that follow `docs/PREMIUM_STILL_SR_FIRST_HOUR.md` and can be rejected early against the 50 MP / 100 MP no-REF promotion contract. | Premium still/SR is the largest local algorithmic gap; video SR is already locked for the approved current workflow. |
| Local docs/release work | Keep README, `docs/PRODUCT_PILLAR_SCORECARD.md`, `docs/PRODUCT_LOCK_LEDGER.md`, and `docs/PRODUCTION_CAPTURE_REQUIREMENTS.md` aligned with the current evidence. | Prevents approved work from being reopened and prevents diagnostic still-SR work from being overclaimed. |
| Sample acquisition | Fill Mission 1 and iPhone darkframe provenance manifests, then build validated camera-noise sidecars. | This closes the remaining raw-stills noise/addback claim beyond X2D/Z8. |
| Hardware integration | Have a GoPro/Labs engineer run `docs/GOPRO_LABS_FIRST_HOUR.md` and `docs/GOPRO_MISSION1_QUICK_VALIDATION.md` on actual Mission 1 hardware. | This is the only evidence that can convert the raw-video MVP from Pi stand-in to firmware-ready. |
| Optional research | Collect controlled Mission 1 high/low Bayer pairs and rerun PSF measurement only as replacement research. | Useful for a future PSF-conditioned model, but not needed to ship the approved current raw-video reconstruction path. |

## Non-Claims

| not claimed | reason |
|---|---|
| Mission 1 firmware is production-ready today. | Current camera evidence is Pi stand-in plus handoff tooling; actual camera-role receipts are still missing. |
| Mission 1 or iPhone can use nonzero production noise addback today. | They lack validated same-camera, same-ISO darkframe sidecars with strict source provenance. |
| Premium still/SR is a shipping quality claim today. | The promotion scoreboard has zero promotable rows and the best runtime-safe recovery is below the promotion floor. |
| PSF-conditioned video/SR is required for the current release. | The approved 4K cleanup and 8K SR path is locked; PSF work is replacement research until it beats that path. |

## Source Of Truth

| topic | document |
|---|---|
| Current percentages and long-form status | [`BIG_EFFORTS_STATUS.md`](BIG_EFFORTS_STATUS.md) |
| Execution order and no-infinite-SR rule | [`HIGH_LEVEL_GOAL_EXECUTION_PLAN.md`](HIGH_LEVEL_GOAL_EXECUTION_PLAN.md) |
| Locked paths versus open gates | [`PRODUCT_LOCK_LEDGER.md`](PRODUCT_LOCK_LEDGER.md) |
| Machine-checkable scorecard | [`PRODUCT_PILLAR_SCORECARD.md`](PRODUCT_PILLAR_SCORECARD.md) |
| Production requirements | [`PRODUCTION_CAPTURE_REQUIREMENTS.md`](PRODUCTION_CAPTURE_REQUIREMENTS.md) and [`PRODUCTION_CAPTURE_REQUIREMENTS.json`](PRODUCTION_CAPTURE_REQUIREMENTS.json) |
| GoPro/Labs first-hour handoff | [`GOPRO_LABS_FIRST_HOUR.md`](GOPRO_LABS_FIRST_HOUR.md) |
| Premium still-SR first-hour promotion | [`PREMIUM_STILL_SR_FIRST_HOUR.md`](PREMIUM_STILL_SR_FIRST_HOUR.md) |
| Raw-stills noise first-hour checklist | [`RAW_STILLS_NOISE_FIRST_HOUR.md`](RAW_STILLS_NOISE_FIRST_HOUR.md) |
