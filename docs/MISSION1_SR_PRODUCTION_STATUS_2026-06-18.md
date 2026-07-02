# Mission 1 SR Production Status - 2026-06-18

Historical note. This file records the 2026-06-18 12MP-to-8K Bayer SR
iteration state and is kept for traceability only.

It is no longer the current shipping decision. The current release boundary is:
Mission 1 4K cleanup and Mission 1 8K SR are approved offline/post product
paths, while PSF/blur-conditioned replacements remain optional research. Use
[`PRODUCT_LOCK_LEDGER.md`](PRODUCT_LOCK_LEDGER.md),
[`PRODUCT_PILLAR_SCORECARD.md`](PRODUCT_PILLAR_SCORECARD.md), and
[`CNN_PRODUCT_SCORECARD_2026-06-29.md`](CNN_PRODUCT_SCORECARD_2026-06-29.md)
as the current source of truth. Do not read the rejected checkpoints below as a
regression of the locked 4K/8K reconstruction path.

## Current Best Evidence

- Best global/cross-camera checkpoint remains `mixed_step1600`.
  - Selection: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_interp_mixed_hard_20260618/selection.json`
  - Decision: `reject_do_not_register`
  - Reason: no Z8 regression, but Mission key8 still has three hard failures:
    - `GP017346`: MAE and gradient below floor
    - `GP017349`: RMSE lift just below floor
    - `GP017600`: gradient below floor

- Fastest Mission-specialized 39/42 checkpoint from this pass is the width96 adapter continuation.
  - Checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_adapter_remined_continue_20260618/adapter96_continue_w96_d6_rs03_gw14_lap02_3000.pt`
  - Mission all-42 dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_adapter_remined_continue_20260618/adapter96_continue_mission_all42_fullframe/index.html`
  - Mission all-42 result: 39/42 pass, 92.86%.
  - Median MPS full-frame throughput with write: 1.301 fps.
  - Remaining Mission failures:
    - `GP017346`: MAE 17.974, gradient 5.066
    - `GP017349`: RMSE 29.358
    - `GP017600`: gradient 7.127

- The adapter checkpoint is not a global checkpoint.
  - Z8 holdout dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_adapter_remined_continue_20260618/adapter96_continue_z8_holdout5_fullframe/index.html`
  - Z8 guardrail regresses versus balanced/mixed:
    - balanced rmse_min 44.589, psnr_min 54.138
    - mixed rmse_min 45.274, psnr_min 54.244
    - adapter rmse_min 40.754, psnr_min 53.517

- Best current Mission-specialized metric candidate is the broad preclean+aux early-stop checkpoint at step 200.
  - Checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/eval_checkpoints/preclean_aux_broad_recovery_w96_d6_rs03_gw08_lap01_aux05_1600_step000200.pt`
  - Temporary review pipeline: `codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_preclean_aux_broad_step0200_v1+demosaic=sips_via_gpr_tools`
  - Decision: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/preclean_aux_broad_step0200_decision_vs_adapter.json`
  - Mission all-42 dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/preclean_aux_broad_step0200_mission_all42_fullframe/index.html`
  - Z8 holdout dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/preclean_aux_broad_step0200_z8_holdout5_fullframe/index.html`
  - Mission all-42 result: 39/42 pass, 92.86%.
  - Median MPS full-frame throughput with write: 1.123 fps.
  - It beats the adapter on the conservative paired Mission/Z8 promotion-review comparison:
    - Mission rmse_min delta: +0.0759
    - Mission rmse_median delta: +0.2330
    - Mission psnr14_min delta: +0.0729 dB
    - Z8 rmse_min delta: +0.2764
    - Z8 psnr14_min delta: +0.0427 dB
  - It is not production-ready yet because the same three Mission rows still fail absolute floors:
    - `GP017346`: gradient 5.131
    - `GP017349`: RMSE 29.434
    - `GP017600`: gradient 7.173
  - Runtime receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_gvid_to_8k_sr_preclean_step0200_multiframe_20260618/receipt.json`
    - 3-frame `.gvid` decode + SR write median: 0.9168 s/frame, 1.091 fps.
    - Peak RSS: 1204 MB.
  - Packaging receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_gvid_to_8k_sr_preclean_step0200_packaging_q3_20260618/packaging_receipt.json`
    - q3 editable GPR readback: 53.74 dB PSNR14.
    - Generic DNG roundtrip: byte-identical raw.
    - GPR-to-DNG opens at 8192x6144.
    - Two-frame ProRes review reports 24/1 fps.

## Experiments Rejected In This Pass

- Edge-head CNN from `mixed_step1600`.
  - Artifact root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_edge_head_20260618`
  - Rejected because it added a Mission failure and did not improve the selector rank.

- Mixed-to-hard checkpoint interpolation.
  - Artifact root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_interp_mixed_hard_20260618`
  - Alpha 0.75 improved some Mission detail margins, but still failed Mission and regressed Z8.

- Residual-scale 0.5 retarget.
  - Artifact root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_guarded_current_adapt_20260618/rs05_blockers_fullframe`
  - Rejected because it worsened MAE/gradient on blocker rows.

- CFA-plane unsharp postfilter.
  - Artifact root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_postfilter_probe_20260618`
  - Rejected because positive sharpening worsened gradient error. Mild smoothing helped gradient slightly but not enough and hurt RMSE.

- `GP017346` specialist continuation.
  - Artifact root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_specialist_probe_20260618`
  - Rejected because it did not move `GP017346` full-frame metrics versus phase 2.

- Current-failure resblock capacity probe.
  - Hard-tile corpus: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_hardtiles_phase2_failures_20260618/phase2_failure_hardtiles_current_contract_t233_w128.npz`
  - Probe root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_resblock_hardtiles_phase2_failures_20260618`
  - Rejected before full-frame eval: hard-tile RMSE lift was only 0.159%.
  - Cause: non-strict resblock init did not map the useful lowres-pixelshuffle weights (`head`, `body`, and `tail` were missing; old `net.*` tensors were unexpected).

## Capacity Probes That Moved The Gate

- Function-preserving width expansion was added to `tools/cnn/train_mission1_sr.py`.
  - Regression test: `tools/test/test_train_mission1_sr_expand.py`
  - This fixed the earlier failure mode where architecture probes started near bilinear instead of inheriting the useful checkpoint.

- Width64 current-failure hard-tile training improved Mission all-42 from 38/42 to 39/42.
  - Dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_wide_lowres_hardtiles_20260618/wide64_mission_all42_fullframe/index.html`
  - Remaining failures after width64: `GP017346`, `GP017349`, `GP017600`.
  - Median MPS full-frame throughput with write: 2.458 fps.

- Re-mining hard tiles from the current widened model and adding a zero-initialized adapter branch improved margins but not pass count.
  - Re-mined corpus: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_hardtiles_wide_failures_20260618/wide_continue_failure_hardtiles_current_contract_t233_w128.npz`
  - Adapter dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_adapter_remined_continue_20260618/adapter96_continue_mission_all42_fullframe/index.html`
  - Improvements versus width64 hard:
    - `GP017346`: MAE 17.316 -> 17.974, gradient 4.578 -> 5.066
    - `GP017349`: RMSE 29.042 -> 29.358
    - `GP017600`: gradient 6.797 -> 7.127

- A low-res preclean branch with auxiliary clean-low supervision confirmed the codec-artifact direction, but is not the current best candidate.
  - Checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_20260618/preclean_aux_from_preclean_w96_d6_rs03_gw14_lap02_aux10_2400.pt`
  - Dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_20260618/preclean_aux_mission_all42_fullframe/index.html`
  - Result: 38/42 pass, 90.48%.
  - It improved the targeted remaining rows versus adapter-only:
    - `GP017346`: MAE 17.974 -> 18.110, gradient 5.066 -> 5.173
    - `GP017349`: RMSE 29.358 -> 29.428
    - `GP017600`: gradient 7.127 -> 7.216
  - It regressed `GP017347` back below the gradient floor and reduced throughput to 1.122 fps, so it is rejected as a production candidate.

- Broad preclean+aux recovery from the first preclean checkpoint produced a better early-stop candidate but the final checkpoint was rejected.
  - Artifact root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618`
  - Final checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/preclean_aux_broad_recovery_w96_d6_rs03_gw08_lap01_aux05_1600.pt`
  - Final dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/preclean_aux_broad_mission_all42_fullframe/index.html`
  - Final result: 38/42 pass, with `GP017347` regressed below the gradient floor.
  - Early-stop scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/blocker_earlystop_scan`
  - Step 200 recovered `GP017347` and slightly improved the three persistent hard rows, so it is the current promotion-review candidate.

## Current Read

The current lowres-pixelshuffle family can reach a strong Mission-specialized result, and function-preserving width/context expansion moves the hard rows. However, the same direction now shows diminishing returns: `GP017349` and `GP017600` are close but still below floor, while `GP017346` remains far below the gradient floor even with width96, context adapter, and a low-res preclean branch.

A clean-low diagnostic changed the read. The same adapter checkpoint clears all three remaining failures when the input is the clean synthetic 12MP Bayer rather than the current codec-degraded `t233` decode:

- Diagnostic dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_clean_vs_codec_low_20260618/adapter96_clean_low_failures_fullframe/index.html`
- Codec-low failures:
  - `GP017346`: MAE 17.974, gradient 5.066
  - `GP017349`: RMSE 29.358
  - `GP017600`: gradient 7.127
- Clean-low results:
  - `GP017346`: RMSE 62.914, MAE 29.399, gradient 11.890
  - `GP017349`: RMSE 35.730, MAE 31.298, gradient 15.599
  - `GP017600`: RMSE 63.544, MAE 33.941, gradient 14.337

The low-frame clean-vs-codec deltas are small in raw counts but large enough to break SR:

- `t233` low-frame RMSE versus clean low:
  - `GP017346`: 4.577 counts
  - `GP017349`: 5.659 counts
  - `GP017600`: 2.858 counts
- Alternate codec profile probe with the same adapter did not solve this:
  - `t236_ch2lh3`, `t356_ch2lh3`, and `t468_ch2lh4` all performed worse than current `t233` on the remaining failures.
  - Probe root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_profile_adapter_probe_20260618`

That points away from a pure 12MP-to-50MP information limit. The next blocker is codec-decode artifact sensitivity in the SR input. Remaining likely causes:

- the SR model needs an explicit low-res codec cleanup/preclean stage,
- the codec profile needs an SR-aware reconstruction constraint,
- or training needs to include an auxiliary clean-low restoration objective before the 8K target.

## Recommended Next Step

The step-200 broad preclean checkpoint is registered as a temporary review pipeline and now has runtime plus packaging receipts, but not for a production claim. The next production step is to run the full production audit for that exact pipeline and keep attacking the remaining absolute floor failures.

The full production-readiness audit now passes with this evidence set, but that
does not make the SR checkpoint production-ready. The audit records the SR
state as offline/review evidence and keeps the absolute hard-row failures
visible.

Follow-up hard96 continuation from the step-200 checkpoint is rejected:

- Probe root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_hard96_preclean_continuation_20260618`
- Decision receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_hard96_preclean_continuation_20260618/hard96_preclean_continuation_decision.json`
- Decision SHA-256: `c7181e00915e58e51376d74bc660552b19ecad51d871218aab3235ab80d61fb7`
- Method:
  - Re-rendered the three step-200 failure rows with retained raw output.
  - Mined 480 hard 96px low-res tiles, balanced across `GP017346`, `GP017349`, and `GP017600`.
  - Merged those tiles with the broad Mission42+Z8 current-contract corpus.
  - Continued from the step-200 preclean checkpoint with stronger gradient/laplacian/clean-low auxiliary weights.
- Result:
  - Tile eval improved locally, but all saved checkpoints regressed at least one full-frame blocker versus the step-200 guardrail.
  - Best checkpoint by minimum guardrail delta was step 100, still worse by 0.783 points on the blocker set.
  - Step 700 was best on tile eval but full-frame regressed:
    - `GP017346` gradient: `5.131 -> 4.305`
    - `GP017349` RMSE: `29.434 -> 28.897`
    - `GP017600` gradient: `7.173 -> 6.564`

Deterministic codec-side cleanup was also probed:

- Tool: `tools/cnn/apply_bayer_detail_shrink_raw.py`
- Regression test: `tools/test/test_apply_bayer_detail_shrink_raw.py`
- Probe root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_shrink_cleanup_20260618`
- Decision receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_shrink_cleanup_20260618/detail_shrink_t1_g100_decision.json`
- Decision SHA-256: `c4d70816d27aca05e409d199aa1d208c369ff82b27bad562979b426fa946d04a`
- Best small sweep setting: per-CFA-plane 3x3 binomial residual soft-threshold with threshold `1`, gain `1.0`.
- Result versus the step-200 preclean guardrail:
  - Mission all-42 worst RMSE lift: `29.434 -> 29.559`
  - Mission all-42 worst MAE lift: `18.052 -> 18.988`
  - Mission all-42 worst gradient lift: `5.131 -> 5.599`
  - Z8 holdout worst RMSE/MAE/gradient all moved slightly up, while worst PSNR moved slightly down by `0.003 dB`.
  - Targeted hard rows improved, but the same rows remain below the production floors, so the cleanup is rejected for registration.
- Inference: tiny deterministic residual shrink is directionally useful for current T233 codec artifacts, but the effect is too small. A learned or context-aware cleanup stage should include the Z8 guardrail in the objective and be judged on full-frame metrics, not tile loss.

A standalone learned low-res cleanup stage was then tested:

- Tool: `tools/cnn/train_bayer_low_cleanup.py`
- Probe root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_learned_low_cleanup_20260618`
- Checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_learned_low_cleanup_20260618/learned_low_cleanup_mission42_z8train19_w32_d4_rs03_gw02_step0800.pt`
- Decision receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_learned_low_cleanup_20260618/learned_low_cleanup_step0800_decision.json`
- Decision SHA-256: `443c9e00442f447126258f3954a39d86059c66fd66bc522cc08ce201a74c08b4`
- Method:
  - Train codec-low to clean-low directly on Mission42 plus Z8 train19.
  - Hold out `Z8Z_1349` through `Z8Z_1353`.
  - Focus sampling on `GP017346`, `GP017349`, and `GP017600`.
  - Apply the cleanup before the current best step-200 preclean SR checkpoint.
- Result:
  - Tile-level low-clean RMSE improved only about 1.26% on the held-out Z8 cleanup objective.
  - Stacked cleanup+SR regressed the targeted Mission hard rows versus the step-200 guardrail:
    - `GP017346` gradient: `5.131 -> 5.065`
    - `GP017349` RMSE: `29.434 -> 29.408`
    - `GP017600` gradient: `7.173 -> 7.092`
  - Z8 full-frame floors also regressed slightly.
- Inference: optimizing low-clean reconstruction separately is not the right objective. It can remove or shift detail that the SR checkpoint needs. The next useful path is an end-to-end cleanup+SR objective judged by full-frame blocker metrics, or a codec/reconstruction change that reduces the artifact before the SR stack sees it.

Larger-context end-to-end preclean+SR training was tested after the standalone cleanup rejection:

- Probe root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_context192_endtoend_20260618`
- Decision receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_context192_endtoend_20260618/context192_endtoend_decision.json`
- Decision SHA-256: `5cccdf2b86905819f97c90674c6cff931439020e366648183facd14a4b00b35e`
- Method:
  - Built a bounded 192px low-tile current-T233 corpus from `GP017346`, `GP017349`, `GP017600`, and Z8 train frames `Z8Z_1344` through `Z8Z_1348`.
  - Continued from the step-200 preclean checkpoint with the preclean+SR stack trained end to end.
  - Scanned saved checkpoints on the actual Mission hard full-frame rows.
- Result:
  - Tile eval improved, but no checkpoint beat the step-200 full-frame guardrail.
  - Best checkpoint by minimum guardrail delta was step 600, still below the guardrail by `0.737` points on the blocker set.
  - Step 600 blocker metrics:
    - `GP017346` gradient: `5.131 -> 4.394`
    - `GP017349` RMSE: `29.434 -> 29.257`
    - `GP017600` gradient: `7.173 -> 6.665`
- Inference: larger local context alone does not solve the full-frame detail-placement blocker. The next useful path is full-frame/whole-image objective selection, codec-side reconstruction changes, or a model trained with explicit full-frame blocker loss rather than random/context tile loss.

Scoped finetuning from the step-200 checkpoint was tested next, specifically to check whether the current checkpoint can be nudged without damaging the learned full-frame mapping:

- Code change: `tools/cnn/train_mission1_sr.py` now supports `--trainable-scope all|adapter_only|preclean_only|adapter_and_preclean`.
- Regression test: `tools/test/test_train_mission1_sr_expand.py::test_trainable_scope_freezes_preclean_adapter_trunk`.
- Gate scanner: `tools/cnn/scan_mission1_sr_fullframe_checkpoints.py`
- Scanner regression test: `tools/test/test_scan_mission1_sr_fullframe_checkpoints.py`
- Decision receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_scoped_adapter_finetune_20260618/scoped_finetune_decision.json`
- Decision SHA-256: `be7f443cbb1ca60114e1ee10223a75e47b4d96050c9ead86de0cb1909a64dfad`
- Canonical full-frame checkpoint scan:
  - `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_checkpoint_scan_20260618/checkpoint_scan_decision.json`
  - TSV: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_checkpoint_scan_20260618/checkpoint_scan.tsv`
- Method:
  - Regenerated the hard-row baseline from the untouched step-200 checkpoint.
  - Built a detail-shrunk training-input NPZ as a negative-control probe.
  - Ran full-weight, ultra-low-LR, hard-loss, and adapter/preclean-only finetunes.
  - Scanned saved checkpoints on the actual `GP017346`, `GP017349`, and `GP017600` full-frame rows.
- Result:
  - The untouched step-200 seed remained the best finetune-family checkpoint:
    - hard-row RMSE minimum: `29.434`
    - hard-row MAE minimum: `18.052`
    - hard-row gradient minimum: `5.131`
  - Detail-shrink before SR improved all three hard rows but still missed production floors:
    - hard-row RMSE minimum: `29.559`
    - hard-row MAE minimum: `18.988`
    - hard-row gradient minimum: `5.600`
  - Every learned finetune variant regressed the full-frame blocker set, even when the SR trunk was frozen and only adapter/preclean branches were trainable.
- Full-frame scanner result:
  - `seed_step0` is best ranked.
  - `stability_step20`, `stability_step100`, `stability_step200`, `scoped_step50`, `scoped_step200`, and `scoped_step400` all regress the hard-row minima versus the seed.
  - The scanner decision is `reject_do_not_register`.
- Inference: the blocker is now narrowed to full-frame/tile-objective mismatch and checkpoint sensitivity. Training-tile holdout metrics can improve while full-frame Mission hard rows collapse, so the next SR training loop must select checkpoints by full-frame gate rows or a gate-aligned proxy, not by random tile loss alone.

A full Mission42 codec-sensitivity pass was added to separate "largest low-res
codec residual" from "low-res residual that breaks SR":

- Tool: `tools/cnn/analyze_mission1_sr_codec_sensitivity.py`
- Regression test: `tools/test/test_analyze_mission1_sr_codec_sensitivity.py`
- Hard-row dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitivity_20260619/hard3_step0200/index.html`
- Mission42 dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitivity_20260619/mission42_step0200/index.html`
- Mission42 summary: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitivity_20260619/mission42_step0200/mission1_sr_codec_sensitivity.json`
- Result:
  - The three SR failures are not the rows with the largest low-res codec error.
  - Failing-row median low-res RMSE is `4.577` counts; passing-row median is `6.776` counts.
  - Failing-row median high-frequency residual RMSE is `3.458` counts; passing-row median is `4.657` counts.
  - Gate pressure correlation is weak/negative against overall low-res RMSE (`-0.199`), p99 abs error (`-0.303`), low-res gradient MAE (`-0.285`), and high-frequency residual RMSE (`-0.190`).
  - `GP017346` and `GP017349` are red-plane/high-frequency sensitive; `GP017600` is green-plane/high-frequency sensitive.
- Inference: codec residual magnitude alone is not a sufficient selector or loss. Passing rows tolerate larger low-res residuals, while the hard rows fail when smaller codec errors land on content/phase structures the SR model depends on. The next viable SR pass needs a content/phase-aware cleanup or an SR objective selected directly by full-frame gate pressure, not a standalone low-clean reconstruction loss.

The first gate-pressure/content-aware tile-mining pass was then run:

- Miner update: `tools/cnn/mine_mission1_sr_hard_tiles.py` can now optionally weight hard tiles by full-frame gate pressure and local codec-low-vs-clean-low residual on the failure-sensitive CFA plane.
- Regression test: `tools/test/test_mine_mission1_sr_hard_tiles.py`
- Tile manifest: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/gate_codec_sensitive_hard3_w96_s48_top192.json`
  - SHA-256: `5d5ba7355699490440be39d5666aec22b08c09a26306bd8f70fd869adc4573fd`
  - 576 selected tiles, balanced across `GP017346`, `GP017349`, and `GP017600`.
  - Focus planes match the sensitivity pass: red for `GP017346`/`GP017349`, green1 for `GP017600`.
- Pair corpus: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/gate_codec_sensitive_hard3_current_t233_w96.npz`
  - SHA-256: `c803d8f62cbc440157de13ba41e29561dc422b003cece05c1b46e2831ebf69eb`
  - Sidecar SHA-256: `ea95659968e31953bc63b1ca74123edcd032a8975085959f515964ce61dd070e`
  - Contract: `current_t233`, `gaussian_area`, manifest-only, low tile 96.
- Probe checkpoint family:
  - Root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619`
  - Final checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/codec_sensitive_step0200_probe_w96_d6_rs03_gw08_lap01_aux05_0800.pt`
  - Full-frame scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/checkpoint_scan_0800_hard3/checkpoint_scan_decision.json`
  - Scan SHA-256: `9c2549a87484a61796f0c6cd598b7d2abbf0efd4cfe27805f074e678c669c7d8`
- Result:
  - Decision: `reject_do_not_register`.
  - Best checkpoint: `step000600`.
  - Best hard-row minima versus seed:
    - RMSE lift: `29.433839 -> 29.438082`
    - MAE lift: `18.051824 -> 18.066467`
    - gradient lift: `5.130740 -> 5.138557`
    - PSNR14 lift: `53.545878 -> 53.546397`
  - All three hard rows still fail the production floors:
    - `GP017346`: MAE and gradient remain below floor.
    - `GP017349`: RMSE remains below floor.
    - `GP017600`: gradient remains below floor.
- Inference: gate/codec-sensitive mining is directionally better than the seed and does not show the severe collapse seen in earlier finetunes, but the magnitude is far too small. The next pass should not simply train longer on the same small adapter/preclean objective; it needs a stronger full-frame selected objective, larger context/capacity at the sensitive CFA plane, or a codec reconstruction change that preserves the structures the SR model uses.

Follow-up all-scope and plane-weighted codec-sensitive probes were also rejected:

- All-scope probe:
  - Checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/codec_sensitive_allscope_lr3e5_w96_d6_rs03_gw10_lap02_aux05_0800.pt`
  - Full-frame scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/checkpoint_scan_allscope_lr3e5_hard3/checkpoint_scan_decision.json`
  - Scan SHA-256: `d67bd43c30238a9ecc47690125aafc57d08943a6886098188364f6c97a070f4e`
  - Decision: `reject_do_not_register`.
  - Best checkpoint: `step000800`.
  - Best hard-row minima versus seed:
    - RMSE: `29.433839 -> 29.421411`
    - MAE: `18.051824 -> 18.189182`
    - gradient: `5.130740 -> 5.248777`
    - PSNR14: `53.545878 -> 53.544346`
  - Remaining failures:
    - `GP017346`: MAE `18.189` and gradient `5.249` remain below floor.
    - `GP017349`: RMSE `29.421` remains below floor.
    - `GP017600`: gradient `7.345` remains below floor.
- Seed/all-scope interpolation:
  - Full-frame scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/checkpoint_scan_interp_allscope_hard3/checkpoint_scan_decision.json`
  - Scan SHA-256: `de35be430bb555a22934fb454710f2c0e1cd9ad378ef180924a31763162872c1`
  - Decision: `reject_do_not_register`.
  - Interpolation did not improve on the all-scope step-800 checkpoint.
- Plane-weighted loss support:
  - Code change: `tools/cnn/train_mission1_sr.py` now supports `--plane-weights r,g1,g2,b`.
  - Regression test: `tools/test/test_train_mission1_sr_expand.py::test_plane_weighted_loss_preserves_uniform_behavior`.
  - Probe checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/codec_sensitive_planewt_rg_w96_d6_rs03_gw10_lap02_aux05_0800.pt`
  - Full-frame scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/checkpoint_scan_planewt_rg_hard3/checkpoint_scan_decision.json`
  - Scan SHA-256: `50d0576d62e3d8b48fbb1e0cb411773400e6d6082aa267e79277a06963c4746c`
  - Decision: `reject_do_not_register`.
  - Best checkpoint: `step000800`.
  - Best hard-row minima versus seed:
    - RMSE: `29.433839 -> 29.451149`
    - MAE: `18.051824 -> 18.136843`
    - gradient: `5.130740 -> 5.171261`
    - PSNR14: `53.545878 -> 53.548006`
  - Remaining failures:
    - `GP017346`: MAE `18.137` and gradient `5.171` remain below floor.
    - `GP017349`: RMSE `29.451` remains below floor.
    - `GP017600`: gradient `7.251` remains below floor.
- Inference: plane-aware loss helps balance the `GP017349` red-plane failure better than the all-scope run, but it gives back too much `GP017346`/`GP017600` gradient improvement. The limiting issue is no longer "find any crop with codec residual"; the hard rows need a gate-aligned full-frame objective or codec reconstruction change that preserves phase-sensitive structures before SR.

A follow-up gradient-focused plane-weighted probe was rejected after this:

- Probe checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/codec_sensitive_planewt_gradfocus_w96_d6_rs03_gw14_lap02_aux03_1000.pt`
- Full-frame scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_codec_sensitive_hardtiles_20260619/checkpoint_scan_planewt_gradfocus_hard3/checkpoint_scan_decision.json`
- Scan SHA-256: `6ba592e0d4233fb6025d9b1885c8dbe46a6264bc426155a49715969369e2cf67`
- Method:
  - Continued from the step-200 preclean checkpoint.
  - Trained all parameters with stronger gradient loss (`1.4`), laplacian loss (`0.2`), lower clean-low auxiliary weight (`0.03`), and plane weights `2.5,1.8,1.4,1.0`.
  - Oversampled `GP017346` and `GP017600` by `1.8x` to target the gradient-floor blockers.
  - Selected by the same full-frame `GP017346`, `GP017349`, and `GP017600` scan, not by tile loss.
- Result:
  - Decision: `reject_do_not_register`.
  - Best checkpoint: `step001000`.
  - Best hard-row minima versus seed:
    - RMSE: `29.433839 -> 29.274878`
    - MAE: `18.051824 -> 18.305578`
    - gradient: `5.130740 -> 5.373025`
    - PSNR14: `53.545878 -> 53.526331`
  - Remaining failures:
    - `GP017346`: MAE `18.306` and gradient `5.373` remain below floor.
    - `GP017349`: RMSE `29.275` remains below floor.
    - `GP017600`: gradient `7.461` remains below floor.
- Inference: targeted gradient pressure can raise `GP017346`/`GP017600` detail margins, but the tradeoff worsens `GP017349` RMSE and PSNR. This confirms that the current small hard-tile corpus plus scalar loss weights is not enough; the next useful attempt should change the supervision shape, not only the weights. Candidate directions are full-frame/blocker-row loss, a phase-aware codec reconstruction constraint, or a larger-context model whose checkpoint is selected exclusively by the full-frame hard rows and Z8 guardrail.

A full-frame coverage-shaped corpus was then tested to reduce the crop-local
objective mismatch:

- Coverage manifest tool: `tools/cnn/build_mission1_sr_coverage_manifest.py`
- Regression test: `tools/test/test_build_mission1_sr_coverage_manifest.py`
- Coverage manifest: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/hard3_coverage_grid_w96_s192_plus48.json`
  - SHA-256: `cea3dfc14d8ef1a7381832a48805f966c4a3fa9bf72a259128021277c9e052b6`
  - 448 tiles over `GP017346`, `GP017349`, and `GP017600`.
  - Each image gets deterministic full-frame coverage grid tiles plus up to 48 non-overlapping codec-sensitive hard tiles.
- Pair corpus: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/hard3_coverage_current_t233_w96.npz`
  - SHA-256: `1d45a34650d4cca89c526876eafa155e1eea29b652f14974561a9ff50ac19f6a`
  - Sidecar SHA-256: `f808e99e36649e3e0abf1f409f0da3d7d79159ce050fcfac6afd43db36201060`
  - Contract: current T233 codec decode, `gaussian_area` CFA-preserving low source, manifest-only, low tile 96.
- Probe checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/coverage_grad_w96_d6_rs03_gw10_lap02_aux03_0800.pt`
- Full-frame scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/checkpoint_scan_coverage_grad_hard3/checkpoint_scan_decision.json`
  - SHA-256: `65c49ee1b3b4405304c1365bc3aa875f98ec1842874caea3431acb264e132e46`
  - Decision: `reject_do_not_register`.
  - Best checkpoint: `step000800`.
  - Best hard-row minima versus seed:
    - RMSE: `29.433839 -> 29.389743`
    - MAE: `18.051824 -> 18.220574`
    - gradient: `5.130740 -> 5.247044`
    - PSNR14: `53.545878 -> 53.540449`
  - Remaining failures:
    - `GP017346`: MAE `18.221` and gradient `5.247` remain below floor.
    - `GP017349`: RMSE `29.390` remains below floor.
    - `GP017600`: gradient `7.307` remains below floor.
- Inference: full-frame coverage is less destructive than pure hard-crop tuning and improves the seed on MAE/gradient, but the change is still too small and still trades off RMSE/PSNR. The next SR pass should move beyond tile-wise supervision entirely, either by adding a true full-frame/blocker-row loss term, changing the codec reconstruction objective that feeds SR, or using a larger-context model selected by full-frame hard rows plus Z8 guardrails.

A coordinate-channel full-frame coverage probe was added next:

- Architecture support: `coord_preclean_adapter_pixelshuffle` in `tools/cnn/train_mission1_sr.py`
  - Adds absolute low-frame XY coordinate channels to the SR trunk.
  - Keeps the 4-channel precleaner unchanged.
  - Initializes from `preclean_adapter_pixelshuffle` by preserving all existing weights and zero-initializing the new coordinate input weights, so step 1 starts as the known checkpoint function.
- Runtime support: `tools/cnn/bench_mission1_sr_8k.py`
  - Appends matching absolute coordinate channels per tile during full-frame render.
  - Receipt records the coordinate architecture cost.
- Regression test: `tools/test/test_train_mission1_sr_expand.py::test_preclean_to_coord_preclean_preserves_source_output`
- Probe checkpoint: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/coord_coverage_w96_d6_rs03_gw10_lap02_aux03_0800.pt`
- Full-frame scan: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/checkpoint_scan_coord_coverage_hard3/checkpoint_scan_decision.json`
  - SHA-256: `78106c43fc3f4b2d0f7a3001a90389c8c8f20c31cc920adca7cee6e3143086e5`
  - Decision: `reject_do_not_register`.
  - Best checkpoint: `step000800`.
  - Best hard-row minima versus seed:
    - RMSE: `29.433839 -> 29.397754`
    - MAE: `18.051824 -> 18.223522`
    - gradient: `5.130740 -> 5.263829`
    - PSNR14: `53.545878 -> 53.541435`
  - Remaining failures:
    - `GP017346`: MAE `18.224` and gradient `5.264` remain below floor.
    - `GP017349`: RMSE `29.398` remains below floor.
    - `GP017600`: gradient `7.302` remains below floor.
- Inference: absolute coordinates are wired correctly and move the hard-row gradient slightly more than the non-coordinate coverage run, but the gain is still far below the production floor. Position awareness alone is not the missing capability. The next useful experiment is a true full-frame/blocker-row optimization loop or a codec reconstruction objective that directly preserves the phase-sensitive low-frame structures before SR.

The coordinate coverage checkpoint was then continued through a full-coverage
gate-driven wrapper instead of another hard-row-only scan:

- Planner tool: `tools/cnn/plan_mission1_sr_gate_iteration.py`
  - Regression test: `tools/test/test_plan_mission1_sr_gate_iteration.py`
  - Plan receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_gate_iteration_actual_20260619/coord_coverage_next_plan.json`
  - The planner classified the current pressure as gradient-dominated:
    - normalized gradient pressure: `0.429333`
    - normalized MAE pressure: `0.088824`
    - normalized RMSE pressure: `0.020075`
  - Focus rows: `GP017346`, `GP017349`, and `GP017600`.
- Guarded experiment root: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_gate_iteration_actual_20260619/coord_gate_iteration`
  - Summary receipt: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_gate_iteration_actual_20260619/coord_gate_iteration/guarded_experiment_summary.json`
  - Decision: `no_candidate_promoted`.
  - Candidate count: `6` (`step000001`, `step000200`, `step000400`, `step000600`, `step000800`, and the saved best tile-eval checkpoint).
- Method:
  - Continued from the coordinate coverage `step000800` checkpoint.
  - Used `coord_preclean_adapter_pixelshuffle`, width `96`, depth `6`, residual scale `0.3`.
  - Used gradient weight `14.0`, laplacian weight `0.2`, low-clean auxiliary weight `0.03`, plane weights `1.6,1.4,1.2,1.0`, and `adapter_and_preclean` trainable scope.
  - Trained against the coverage corpus with clean-low sidecars.
  - Evaluated every checkpoint against the full 8-image Mission guardrail and the full 5-image regenerated-Z8 guardrail, not just the three blocker rows.
- Code fix found by this run:
  - `tools/cnn/train_mission1_sr.py` now supports same-architecture continuation from a `coord_preclean_adapter_pixelshuffle` checkpoint.
  - Regression test: `tools/test/test_train_mission1_sr_expand.py::test_coord_preclean_continuation_loads_same_architecture`
- Best observed tradeoff:
  - `step000400` had the least-bad Mission worst-row delta versus guardrail-light:
    - Mission RMSE min: `29.405491`
    - Mission gradient min: `5.268771`
    - Mission PSNR14 min: `46.256062`
    - Mission RMSE-min delta versus guardrail-light: `-7.978438`
    - Z8 RMSE-min delta versus guardrail-light: `+1.844695`
  - `step000800` did not improve the blocker:
    - Mission RMSE min: `29.403436`
    - Mission gradient min: `5.262874`
    - Mission RMSE-min delta versus guardrail-light: `-7.980494`
    - Z8 RMSE-min delta versus guardrail-light: `+1.828802`
- Inference: the full-coverage gate loop is now reproducible, but this recipe
  still cannot beat the registered/light Mission guardrail on worst rows.
  The Z8 guardrail is protected or improved, while Mission rows
  `GP017349`, `GP017350`, `GP017351`, and `GP017604` remain worse than
  guardrail-light. More continuation with the same coordinate/preclean tile
  objective is not a production path. The next useful SR work must change the
  objective or source reconstruction: full-frame/blocker-row differentiable
  loss, a phase-aware codec reconstruction constraint, or a larger-context
  model selected exclusively by full-frame Mission+Z8 receipts.

The next diagnostic pass checked whether the codec-decoded low frame preserves
same-color Bayer detail phase before SR:

- Phase reconstruction tool: `tools/cnn/analyze_mission1_sr_phase_reconstruction.py`
  - Regression test: `tools/test/test_analyze_mission1_sr_phase_reconstruction.py`
  - Metrics: per-CFA-plane detail residual RMSE/MAE, normalized detail
    correlation, significant-detail sign mismatch, flip-energy percentage, and
    a combined phase-error score.
- Authoritative Mission exact-low receipt:
  - `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_reconstruction_20260619/mission_holdout8_step400_exactlow/mission1_sr_phase_reconstruction.json`
  - Dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_reconstruction_20260619/mission_holdout8_step400_exactlow/index.html`
  - Sidecar: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_reconstruction_20260619/mission_holdout8_step400_exactlow/mission_holdout8_exact_phase_sidecar.json`
  - Decision: `codec_phase_mixed_signal`.
  - Reason: failing rows have worse low-frame phase scores, but not worse
    detail residual amplitude.
  - Failing rows versus passing rows:
    - phase-error median: `15.006337` versus `13.518941`
    - detail-RMSE median: `5.049777` versus `5.334394`
    - sign-mismatch median: `11.187041%` versus `11.103938%`
    - gate-pressure correlation with phase score: `0.125733`
    - gate-pressure correlation with detail RMSE: `-0.331601`
  - Worst Mission gate rows:
    - `GP017346`: gate pressure `4.518926`, phase score `15.663020`, worst plane `r`
    - `GP017600`: gate pressure `0.701419`, phase score `14.349653`, worst plane `r`
    - `GP017349`: gate pressure `0.594509`, phase score `16.161256`, worst plane `r`
- Z8 holdout receipt:
  - `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_reconstruction_20260619/z8_holdout5_step400/mission1_sr_phase_reconstruction.json`
  - Dashboard: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_reconstruction_20260619/z8_holdout5_step400/index.html`
  - Decision: `no_passing_rows_for_contrast` under the absolute Mission floors,
    because the Z8 guardrail is judged against baseline deltas rather than the
    Mission absolute gradient floor.
- Non-authoritative caution:
  - `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_reconstruction_20260619/mission_holdout8_step400/mission1_sr_phase_reconstruction.json`
    used an older pair sidecar whose lows did not match the step-400 full-frame
    evaluation lows. Keep it as a path-mismatch caution, not as the Mission
    phase conclusion.
- Inference: the evidence now points to a red-plane phase-preservation problem
  on the Mission hard rows, but not a generic low-clean amplitude problem.
  The next SR experiment should not be another broad cleanup or scalar tile-loss
  continuation. It should target same-color red-plane phase preservation before
  or inside SR, then select only by the full Mission+Z8 gate receipts.

That follow-up scalar phase-loss probe was run and rejected:

- Trainer update: `tools/cnn/train_mission1_sr.py` now supports
  `--detail-phase-weight` and `--detail-phase-threshold`.
  - Regression test: `tools/test/test_train_mission1_sr_expand.py::test_detail_phase_loss_weights_same_color_planes`
  - Guarded-runner pass-through: `tools/cnn/run_mission1_sr_guarded_experiment.py`
  - Planner pass-through: `tools/cnn/plan_mission1_sr_gate_iteration.py`
- Plan receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_loss_probe_20260619/red_phase_next_plan.json`
- Guarded experiment root:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_loss_probe_20260619/red_phase_guarded`
- Guarded summary:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_loss_probe_20260619/red_phase_guarded/guarded_experiment_summary.json`
- Method:
  - Continued from the coordinate coverage `step000800` checkpoint.
  - Used `coord_preclean_adapter_pixelshuffle`, width `96`, depth `6`,
    residual scale `0.3`.
  - Added same-color binomial-detail phase loss with weight `0.5` and
    significant-detail threshold `2.0` raw counts.
  - Used red-heavy plane weights `2.5,1.4,1.2,1.0`, gradient weight `14.0`,
    laplacian weight `0.2`, low-clean auxiliary weight `0.03`, and
    `adapter_and_preclean` trainable scope.
  - Evaluated saved checkpoints against the full 8-image Mission guardrail and
    5-image regenerated-Z8 guardrail.
- Result:
  - Decision: `no_candidate_promoted`.
  - Candidate count: `6`.
  - Best observed Mission RMSE-min delta versus guardrail-light was still
    negative:
    - `step000400`: Mission RMSE-min delta `-7.978212`, Z8 RMSE-min delta
      `+1.844347`.
    - `step000600`: Mission RMSE-min delta `-7.978704`, Z8 RMSE-min delta
      `+1.843905`.
    - `step000800`: Mission RMSE-min delta `-7.979079`, Z8 RMSE-min delta
      `+1.832120`.
  - The tile-best checkpoint was the step-1 function and also rejected.
  - The run kept artifacts bounded: `56M` total and no retained `*_sr.raw`
    intermediates.
- Inference: red-plane scalar phase loss is wired and reproducible, but it is
  not enough to change the Mission blocker. It preserves/improves the Z8
  guardrail relative to guardrail-light, while the same Mission worst-row RMSE
  and gradient failures remain. The next useful pass should not be stronger
  scalar weighting on the same tile corpus. It needs a different source
  reconstruction or objective shape: a codec-side phase-preserving
  reconstruction constraint, a differentiable full-frame/blocker-row loss, or a
  larger-context model selected only by full-frame Mission+Z8 receipts.

The next source-reconstruction oracle narrowed that conclusion further:

- Oracle tool: `tools/cnn/apply_bayer_phase_oracle_raw.py`
  - Regression test: `tools/test/test_apply_bayer_phase_oracle_raw.py`
  - Schema: `gpr.bayer_phase_oracle_raw.v1`
  - This is not a production transform. It uses clean-low references to answer
    which low-frame information is missing before SR.
- Artifact root:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_oracle_probe_20260619`
- Inputs:
  - Pair sidecar:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/hard3_coverage_current_t233_w96.npz.json`
  - SR checkpoint:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_preclean_aux_broad_recovery_20260618/eval_checkpoints/preclean_aux_broad_recovery_w96_d6_rs03_gw08_lap01_aux05_1600_step000200.pt`
  - Hard rows: `GP017346`, `GP017349`, and `GP017600`
- Evaluated oracle modes:
  - `clean`: full clean 12MP low input.
  - `codec_lf_clean_detail`: codec low-frequency plus clean same-color detail
    above a threshold.
  - `codec_lf_clean_phase_codec_mag`: codec low-frequency plus clean detail
    sign/phase with codec detail magnitude.
- Receipts:
  - Full clean low:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_oracle_probe_20260619/clean/preclean_step0200_hard3_fullframe/summary.json`
  - Codec LF plus clean detail:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_oracle_probe_20260619/codec_lf_clean_detail/preclean_step0200_hard3_fullframe/summary.json`
  - Codec LF plus clean phase with codec magnitude:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_phase_oracle_probe_20260619/codec_lf_clean_phase_codec_mag/preclean_step0200_hard3_fullframe/summary.json`
- Key result:
  - Full clean low clears the hard rows.
  - Codec LF plus clean same-color detail also clears the hard rows:
    - `GP017346`: RMSE improvement `62.36%`, MAE improvement `24.32%`,
      gradient-MAE improvement `9.00%`, model PSNR14 `60.34 dB`.
    - `GP017349`: RMSE improvement `35.21%`, MAE improvement `30.50%`,
      gradient-MAE improvement `15.15%`, model PSNR14 `54.38 dB`.
    - `GP017600`: RMSE improvement `63.34%`, MAE improvement `29.19%`,
      gradient-MAE improvement `11.61%`, model PSNR14 `60.25 dB`.
  - Codec LF plus clean phase/sign but codec magnitude improves the rows, but
    does not clear all floors:
    - `GP017346`: MAE improvement only `18.98%`, gradient-MAE improvement
      only `5.69%`.
    - `GP017600`: gradient-MAE improvement `7.84%`, just below the floor.
- Inference: the blocker is not solved by sign/phase preservation alone. The
  production path needs to preserve or reconstruct same-color Bayer detail
  amplitude/content in the 12MP low source before the 8K SR model consumes it.
  The next pass should train or optimize an allowed low-source reconstruction
  stage against this detail-content target, then select only by full-frame
  Mission+Z8 receipts.

That production-valid low-source cleanup pass was attempted and rejected:

- Trainer update: `tools/cnn/train_bayer_low_cleanup.py` now supports an
  opt-in same-color Bayer detail-content loss:
  - `--detail-weight`
  - `--detail-threshold`
  - `--detail-plane-weights`
  - Regression test: `tools/test/test_train_bayer_low_cleanup.py`
- Probe root:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_content_cleanup_probe_20260619`
- Broad detail-cleanup checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_content_cleanup_probe_20260619/detail_content_cleanup_w48_d5_rs08_gw02_dw25_focus3_step0600.pt`
  - Datasets: Mission all-42 plus Z8 train19.
  - Focus rows: `GP017346`, `GP017349`, `GP017600`.
  - Low-clean tile RMSE improvement: `2.71%`.
  - Apply timing on MPS 12MP lows: roughly `0.26-0.28 s/frame`, so the Python
    cleanup is offline-only unless compiled or fused.
  - SR full-frame receipt:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_content_cleanup_probe_20260619/preclean_step0200_cleanup_hard3_fullframe/summary.json`
  - SR result:
    - `GP017346`: RMSE improvement `59.28%`, MAE improvement `17.97%`,
      gradient-MAE improvement `5.10%`, model PSNR14 `59.61 dB`.
    - `GP017349`: RMSE improvement `29.40%`, MAE improvement `24.45%`,
      gradient-MAE improvement `11.13%`, model PSNR14 `53.54 dB`.
    - `GP017600`: RMSE improvement `61.09%`, MAE improvement `21.89%`,
      gradient-MAE improvement `7.13%`, model PSNR14 `59.71 dB`.
- Hard-row overfit diagnostic checkpoint:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_content_cleanup_probe_20260619/detail_content_cleanup_hard3_overfit_w64_d6_rs20_gw02_dw80_step1200.pt`
  - Datasets: only `GP017346`, `GP017349`, `GP017600`.
  - Low-clean tile RMSE improvement after direct hard-row training: `7.27%`.
  - SR full-frame receipt:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_content_cleanup_probe_20260619/preclean_step0200_cleanup_hardfit_hard3_fullframe/summary.json`
  - SR result:
    - `GP017346`: RMSE improvement `59.11%`, MAE improvement `17.94%`,
      gradient-MAE improvement `5.25%`, model PSNR14 `59.58 dB`.
    - `GP017349`: RMSE improvement `28.76%`, MAE improvement `23.85%`,
      gradient-MAE improvement `10.79%`, model PSNR14 `53.46 dB`.
    - `GP017600`: RMSE improvement `60.64%`, MAE improvement `21.75%`,
      gradient-MAE improvement `7.22%`, model PSNR14 `59.61 dB`.
- Decision: reject both cleanup candidates for registration. They improve the
  low-source and SR rows, but do not approach the oracle result and still miss
  the hard-row MAE/gradient floors. Even direct hard-row overfit fails to
  recover enough same-color detail content, so the current small residual
  cleanup architecture/loss is not the missing production path.
- Updated inference: the oracle fix likely requires either a deeper/larger
  source-reconstruction model trained end-to-end through the SR gate, or a codec
  reconstruction change that preserves the relevant same-color detail before the
  learned SR stack. More standalone low-clean tile-loss training is not a good
  next step.

An end-to-end preclean detail-supervision pass was then wired and rejected:

- Trainer update: `tools/cnn/train_mission1_sr.py` now supports low-clean
  same-color detail supervision on the preclean branch:
  - `--low-clean-detail-aux-weight`
  - `--low-clean-detail-threshold`
  - Guarded runner pass-through:
    `tools/cnn/run_mission1_sr_guarded_experiment.py`
  - Gate-iteration planner pass-through:
    `tools/cnn/plan_mission1_sr_gate_iteration.py`
  - Regression tests:
    `tools/test/test_run_mission1_sr_guarded_experiment.py` and
    `tools/test/test_plan_mission1_sr_gate_iteration.py`
- Guarded experiment root:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_lowclean_detail_aux_probe_20260619/detail_aux_guarded`
- Guarded summary:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_lowclean_detail_aux_probe_20260619/detail_aux_guarded/guarded_experiment_summary.json`
- Method:
  - Continued from the coordinate coverage `step000800` checkpoint.
  - Used `coord_preclean_adapter_pixelshuffle`, width `96`, depth `6`,
    residual scale `0.3`.
  - Used gradient weight `14.0`, laplacian weight `0.2`, high-res detail-phase
    weight `0.25`, low-clean auxiliary weight `0.03`, and low-clean detail
    auxiliary weight `0.15`.
  - Evaluated saved checkpoints against the 8-image Mission guardrail and
    5-image regenerated-Z8 guardrail.
- Result:
  - Decision: `no_candidate_promoted`.
  - Candidate count: `4`.
  - All candidates were rejected:
    - `step000001`: Mission RMSE-min delta `-7.984706`, Mission PSNR14-min
      delta `-1.763226`, Z8 RMSE-min delta `+1.849099`.
    - `step000200`: Mission RMSE-min delta `-7.979650`, Mission PSNR14-min
      delta `-1.763748`, Z8 RMSE-min delta `+1.847014`.
    - `step000400`: Mission RMSE-min delta `-7.978665`, Mission PSNR14-min
      delta `-1.764037`, Z8 RMSE-min delta `+1.848701`.
    - final/best checkpoint: same decision as `step000001`.
  - The run kept artifacts bounded: `37M` total and no retained `*_sr.raw`
    intermediates.
- Inference: adding detail supervision to the existing preclean branch does not
  close the Mission worst rows. It protects or improves the Z8 guardrail, but
  the Mission failure is effectively unchanged from prior scalar phase/detail
  continuations. The next useful pass should stop tweaking this branch and
  instead change representation or capacity: a larger/deeper source
  reconstruction model trained through the SR gate, a full-frame/blocker-row
  objective, or a codec-side reconstruction change that preserves the oracle
  same-color detail before SR.

The next capacity check added a deeper low-source preclean branch and was also
rejected:

- Architecture update: `coord_deep_preclean_adapter_pixelshuffle` in
  `tools/cnn/train_mission1_sr.py`
  - Keeps the existing coordinate preclean adapter SR trunk names intact.
  - Adds a zero-initialized `preclean_extra` branch with dilated low-res
    convolutions, so initialization from `coord_preclean_adapter_pixelshuffle`
    starts as the known function.
  - Regression tests:
    `tools/test/test_train_mission1_sr_expand.py::test_coord_deep_preclean_loads_coord_preclean_function`
    and
    `tools/test/test_train_mission1_sr_expand.py::test_trainable_scope_includes_deep_preclean_extra`
  - Runtime cost is recorded by `tools/cnn/bench_mission1_sr_8k.py`.
- Guarded experiment root:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_deep_preclean_probe_20260619/deep_preclean_guarded`
- Guarded summary:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_deep_preclean_probe_20260619/deep_preclean_guarded/guarded_experiment_summary.json`
- Method:
  - Continued from the coordinate coverage `step000800` checkpoint.
  - Used `coord_deep_preclean_adapter_pixelshuffle`, width `96`, depth `6`,
    residual scale `0.3`.
  - Used gradient weight `14.0`, laplacian weight `0.2`,
    high-res detail-phase weight `0.25`, low-clean auxiliary weight `0.03`,
    low-clean detail auxiliary weight `0.15`, plane weights
    `2.0,1.4,1.2,1.0`, and `adapter_and_preclean` trainable scope.
  - Evaluated saved checkpoints against the 8-image Mission guardrail and
    5-image regenerated-Z8 guardrail.
- Result:
  - Decision: `no_candidate_promoted`.
  - Candidate count: `4`.
  - All candidates were rejected:
    - `step000001`: Mission RMSE-min delta `-7.984956`, Mission PSNR14-min
      delta `-1.763276`, Z8 RMSE-min delta `+1.849705`.
    - `step000200`: Mission RMSE-min delta `-7.979282`, Mission PSNR14-min
      delta `-1.764116`, Z8 RMSE-min delta `+1.848138`.
    - `step000400`: Mission RMSE-min delta `-7.978821`, Mission PSNR14-min
      delta `-1.763785`, Z8 RMSE-min delta `+1.844372`.
    - final/best checkpoint: same decision as `step000001`.
  - Median Mission MPS full-frame throughput with write was about
    `0.749 fps`; regenerated-Z8 throughput was about `0.978 fps`.
  - Cost estimate:
    - Mission 4096x3072 low to 8192x6144 output:
      `3.294 TMAC/frame`.
    - Z8 4140x2760 low to 8280x5520 output:
      `2.991 TMAC/frame`.
  - The run kept artifacts bounded: `44M` total and no retained `*_sr.raw`
    intermediates.
- Inference: simply adding deeper preclean capacity to the same low-clean/detail
  objective is not the production path. It slightly improves the Z8 guardrail,
  but leaves the Mission hard-row deltas effectively unchanged and makes
  throughput worse. The next SR pass should pivot to a source representation or
  codec reconstruction change that preserves same-color detail content before
  SR, or to a true full-frame/blocker-row differentiable objective. More
  preclean-branch depth on the current tile objective is ruled out.

A codec-side detail-residual side-channel oracle was then added and produced a
stronger production direction:

- Tool: `tools/cnn/apply_bayer_detail_residual_oracle_raw.py`
  - Regression test: `tools/test/test_apply_bayer_detail_residual_oracle_raw.py`
  - Schema: `gpr.bayer_detail_residual_oracle_raw.v1`
  - This is not a runtime transform. It uses clean-low references to estimate
    same-color detail residual information the encoder could preserve before
    quantization/dead-zone loss.
- Prototype packer: `tools/cnn/pack_bayer_detail_residual_sidecar.py`
  - Regression test: `tools/test/test_pack_bayer_detail_residual_sidecar.py`
  - Schema: `gpr.bayer_detail_residual_sidecar.v1`
  - Encode uses source/clean low to build a compressed residual sidecar; decode
    uses only codec low plus the sidecar.
- Budget analyzer: `tools/cnn/analyze_bayer_detail_residual_budget.py`
  - Regression test: `tools/test/test_analyze_bayer_detail_residual_budget.py`
  - Schema: `gpr.bayer_detail_residual_budget.v1`
  - Computes reconstruction and compressed-size estimates across broad corpora
    without writing decoded low raws.
- Probe root:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_sidecar_probe_20260619`
- Mission hard-row sweep:
  - Exact-ish residual: `q1_t0_all`
  - Quantized sparse residual: `q2_t1_all`
  - More aggressive sensitive-plane residual: `q4_t2_sensitive`
- Best production-shaped diagnostic so far: `q2_t1_all`
  - Receipt:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_sidecar_probe_20260619/q2_t1_all/detail_residual_oracle.json`
  - Mission hard-row SR receipt:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_sidecar_probe_20260619/q2_t1_all/preclean_step0200_hard3_fullframe/summary.json`
  - Z8 holdout SR receipt:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_sidecar_probe_20260619/q2_t1_all_z8/preclean_step0200_z8_fullframe/summary.json`
- Mission hard-row result with `q2_t1_all`:
  - `GP017346`: RMSE improvement `62.34%`, MAE improvement `24.21%`,
    gradient-MAE improvement `8.90%`, model PSNR14 `60.33 dB`.
  - `GP017349`: RMSE improvement `35.18%`, MAE improvement `30.47%`,
    gradient-MAE improvement `15.12%`, model PSNR14 `54.37 dB`.
  - `GP017600`: RMSE improvement `63.32%`, MAE improvement `29.08%`,
    gradient-MAE improvement `11.47%`, model PSNR14 `60.25 dB`.
  - These match the oracle-clearing direction while using quantized residuals,
    not full clean lows.
- Z8 regenerated holdout with the same `q2_t1_all` residual:
  - RMSE-improvement minimum improved from `25.77%` guardrail-light to
    `34.31%`.
  - MAE-improvement minimum improved from `6.16%` to `8.25%`.
  - Gradient-improvement minimum improved from `1.68%` to `2.31%`.
  - PSNR14 minimum improved from `51.26 dB` to `52.44 dB`.
- Side-channel size estimate:
  - Mission hard rows, `q2_t1_all`: mean nonzero sample rate `36.97%`;
    sparse estimate mean `19.77 MB/frame`; bitmap estimate mean
    `7.39 MB/frame`; zlib bitmap+values proxy mean `3.57 MB/frame`,
    max `5.71 MB/frame`.
  - Z8 holdout, `q2_t1_all`: mean nonzero sample rate `21.03%`;
    sparse estimate mean `11.72 MB/frame`; bitmap estimate mean
    `5.93 MB/frame`; zlib bitmap+values proxy mean `2.13 MB/frame`,
    max `2.13 MB/frame`.
  - The zlib proxy is still not a final bitstream design, but it shows the
    residual is compressible enough to justify an encoder/decoder prototype.
- Sidecar prototype receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_sidecar_probe_20260619/q2_t1_all_sidecar_proto/summary.json`
  - Decoded lows are byte-identical to the already-scored `q2_t1_all` oracle
    lows.
  - Mission hard-row mean sidecar size: `3.58 MB/frame`.
  - Per-row sidecar sizes:
    - `GP017346`: `2.34 MB`
    - `GP017349`: `5.71 MB`
    - `GP017600`: `2.68 MB`
  - Python decode mean: `0.097 s/frame`.
  - This decode timing is not production code; it proves the data path and
    gives a first performance ceiling for a C/native implementation.
- Native sidecar prototype receipt:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_probe_20260619/summary.json`
  - Tool: `source/app/bayer_detail_residual_sidecar.c`
  - Regression test: `tools/test/test_bayer_detail_residual_sidecar_native.sh`
  - Native decode is byte-identical to the Python `q2_t1_all` oracle lows on
    all three hard Mission rows.
  - The current tool includes a fused encode-detail pass so the encoder walks
    each 3x3 Bayer-plane neighborhood once for clean/detail-residual terms
    instead of running separate clean and codec blur passes, plus a direct
    interior-pixel Bayer-plane path that avoids reflection/index overhead away
    from borders.
  - Mission hard-row mean uncompressed native sidecar size:
    `10.37 MiB/frame`.
  - Mean encode time: `106.54 ms/frame`; mean decode time:
    `26.96 ms/frame`.
  - Mean RMSE reduction versus current T233 low source: `49.06%`; minimum
    hard-row reduction: `39.82%`; mean PSNR14 lift: `5.93 dB`.
  - Per-row native results:
    - `GP017346`: `6.93 MiB`, encode `94.48 ms`, decode `23.29 ms`,
      RMSE reduction `52.77%`, PSNR14 lift `6.52 dB`.
    - `GP017349`: `16.14 MiB`, encode `128.94 ms`, decode `33.71 ms`,
      RMSE reduction `54.60%`, PSNR14 lift `6.86 dB`.
    - `GP017600`: `8.05 MiB`, encode `96.21 ms`, decode `23.88 ms`,
      RMSE reduction `39.82%`, PSNR14 lift `4.41 dB`.
  - This is still not a production bitstream. The current native file stores
    an uncompressed bitmap plus int16 values; the Python zlib proxy above is
    the better first-order size estimate. The production version needs
    entropy coding and a much faster encode-side implementation before
    Pi/Mission 1 capture timing claims. At the current timing it is better
    treated as a quality oracle/offline reconstruction direction than as a
    live 20-24 fps capture path.
- Native sidecar thread sweep:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_threads_20260619/summary.json`
  - Reproducer:
    `tools/cnn/bench_bayer_detail_residual_sidecar_native.py --manifest /Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_fullframe_coverage_manifest_20260619/hard3_coverage_current_t233_w96.npz.json --tool build-local/bin/bayer_detail_residual_sidecar --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_threads_20260619 --repo . --threads 1,2,4,8`
  - `BDRS_ENCODE_THREADS` is opt-in; default encode behavior remains
    single-threaded.
  - The threaded path writes quantized residuals into a dense temporary buffer
    and compacts in deterministic sample order, so emitted sidecars are
    byte-identical to the single-thread path on the hard Mission rows.
  - Mean encode timing on the three 4096x3072 hard rows:
    - 1 thread: `149.92 ms/frame`
    - 2 threads: `99.52 ms/frame`
    - 4 threads: `64.48 ms/frame`
    - 8 threads: `45.51 ms/frame`
  - Mean decode timing remains about `25.5-28.6 ms/frame`.
  - Interpretation: parallelism is directionally useful, but even the
    Pi-relevant 4-thread result is still above a 20-24 fps live capture
    budget. The sidecar can be kept as an offline/review or future
    bitstream-reconstruction direction; it should not be folded into the live
    Mission 1 capture claim without further algorithmic compression and
    encoder-side reductions.
- Native compact sidecar sweep:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_compact_20260619/summary.json`
  - Tool mode: set `BDRS_COMPACT=1` to emit `compact_varint_qstep` sidecars.
  - The compact format keeps the same deterministic bitmap and quantized
    residual samples, but stores residual units with signed zigzag varints.
  - Regression coverage now verifies that compact and uncompressed sidecars
    decode to byte-identical lows on the native smoke case.
  - Mission hard-row mean compact sidecar size: `5.94 MiB/frame`, versus the
    prior uncompressed native mean of `10.37 MiB/frame`.
  - Mean value payload size: `4.44 MiB/frame`.
  - 4-thread compact encode mean: `66.79 ms/frame`; decode mean:
    `27.17 ms/frame`.
  - Sidecars remain byte-stable across the checked thread counts, and the
    receipt retained no `.bdrs` or decoded `.raw` payloads.
  - Interpretation: this is a real move toward a production-shaped residual
    bitstream cost, but it still does not meet live Mission 1 timing. The next
    implementation target is reducing encoder cost and integrating the compact
    residual stream with the actual codec/reconstruction path.
- Native direct threaded compact sidecar sweep:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_compact_direct_20260619/summary.json`
  - Tool mode: `BDRS_COMPACT=1 BDRS_ENCODE_THREADS=4`.
  - The threaded compact path emits per-row-chunk varint payloads directly,
    then concatenates them in deterministic CFA-plane and row-chunk order. This
    avoids the dense temporary `int16_t` residual image used by the older
    threaded compact path.
  - Regression coverage verifies that the 4-thread compact sidecar is
    byte-identical to the single-thread compact sidecar on the native smoke
    fixture.
  - Mission hard-row mean compact sidecar size is unchanged at
    `5.94 MiB/frame`; mean value payload remains `4.44 MiB/frame`.
  - 4-thread direct compact encode mean: `46.74 ms/frame`; decode mean:
    `27.02 ms/frame`.
  - This improves the previous 4-thread compact mean of `66.79 ms/frame`, but
    remains above the strict 24 fps frame budget of `41.67 ms`. It should not
    be folded into the live Mission 1 capture claim without further algorithmic
    compression or encoder-side reductions.
- Strict-24 encode hot-path follow-up:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_encode_rejection_summary_20260619/summary.json`
  - Same-session baseline repeat on `GP017602`, 120 frames: `44.515 ms`
    median, `22.46 fps` median, `21.89 fps` wall.
  - Rejected rANS reverse-write candidate: `46.345 ms` median, `21.58 fps`
    median, `20.99 fps` wall. This regressed both median and wall timing.
  - Rejected profile-guided/code-layout candidate: `44.515 ms` median,
    `22.46 fps` median, `21.92 fps` wall. This was neutral versus baseline and
    does not close the strict 24 fps gap.
  - Inference: small code-layout and reverse-buffer changes are not enough.
    The next 24 fps attempt needs algorithmic encode-work reduction or real
    pipeline overlap, not another simple compiler/layout probe.
- Broad no-output budget receipts:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_budget_broad_20260619`
  - Mission all-42 current-contract T233:
    `mission_all42_q2_t1_all_budget.json`
    - `42` images.
    - bitmap+values zlib sidecar mean `4.49 MB/frame`, median
      `4.69 MB/frame`, p95 `5.80 MB/frame`, max `6.22 MB/frame`.
    - nonzero sample rate mean `46.55%`, p95 `61.96%`.
    - low-source RMSE reduction mean `54.58%`.
    - worst sidecar row: `GP017457`, `6.22 MB`.
    - worst output-clean RMSE row: `GP017507`, `5.236` counts.
  - Z8 all-24 current-contract T233:
    `z8_all24_q2_t1_all_budget.json`
    - `24` images.
    - bitmap+values zlib sidecar mean `2.12 MB/frame`, median
      `2.13 MB/frame`, p95 `2.14 MB/frame`, max `2.14 MB/frame`.
    - nonzero sample rate mean `20.98%`, p95 `21.17%`.
    - low-source RMSE reduction mean `38.34%`.
    - worst sidecar row: `Z8Z_1346`, `2.14 MB`.
    - worst output-clean RMSE row: `Z8Z_1345`, `2.025` counts.
  - Stale-path caution: the older
    `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_z8_sr_all24_current_t233_20260618/z8_all24_sr_pairs_current_t233_gaussian_area_96t_w96.npz.json`
    points at decoded lows that are no longer present. Use the current-contract
    Z8 root above for broad residual-budget evidence.
- Focused residual Pareto sweep:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_pareto_20260619/pareto_summary.json`
  - Summary SHA-256:
    `1a9cf3e12b731f4b19d6183424ac186d48158732f16b71164b0b1f619d9c22f5`.
  - Scope: no-output sweep over Mission focus rows `GP017346`, `GP017349`,
    `GP017600`, `GP017604`, `GP017457`, `GP017507`, `GP017350`,
    `GP017351`, plus regenerated-Z8 holdout rows `Z8Z_1349` through
    `Z8Z_1353`.
  - `q2_t1_all` remains the strongest quality budget in this sweep:
    Mission focus mean sidecar `4.448 MB/frame`, mean low-source RMSE
    reduction `52.961%`; Z8 holdout mean sidecar `2.128 MB/frame`, mean
    low-source RMSE reduction `38.393%`.
  - `q3_t1_all` is the best conservative quality/size point in the Python
    budget sweep: Mission focus mean
    sidecar drops to `3.545 MB/frame` while mean RMSE reduction remains
    `52.142%`; Z8 holdout mean sidecar drops to `1.704 MB/frame` while mean
    RMSE reduction remains `37.612%`.
  - `q4_t2_all` is smaller (`2.907 MB/frame` Mission focus,
    `1.378 MB/frame` Z8 holdout) but loses more recovery. `q6_t3_all` and
    `q4_t2_r_g1_g2` cut size further but lose too much signal for the next
    production prototype.
  - Interpretation before native timing: keep `q2_t1_all` as the quality
    oracle, use `q3_t1_all` as the conservative size point, and test
    `q4_t2_all` as the aggressive-size fallback only after SR full-frame gates
    are rerun.
- Native q3/q4 direct compact sidecar receipts:
  - q3/t1 receipt:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_q3t1_direct_20260619/summary.json`
    - SHA-256:
      `61f9f2e4e373f707c864d61a205ef467913ddb6c9bfb769eb7000bf0ac5f1223`.
    - 4-thread direct compact encode mean `51.143 ms/frame`, median
      `44.437 ms/frame`, max `65.814 ms/frame`.
    - Mean compact sidecar size `5.158 MiB/frame`; decode mean
      `25.800 ms/frame`.
  - q4/t2 receipt:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_native_sidecar_q4t2_direct_20260619/summary.json`
    - SHA-256:
      `62fc817a3fc13eaa728683857758391e6b8306717c3b4fcdeacc1c83e656803c`.
    - 4-thread direct compact encode mean `41.867 ms/frame`, median
      `38.113 ms/frame`, max `50.580 ms/frame`.
    - Mean compact sidecar size `4.467 MiB/frame`; decode mean
      `22.615 ms/frame`.
  - Interpretation: q4/t2 is now the best implementation candidate for a
    detail-residual reconstruction stream. It is near the standalone 24 fps
    encode budget on these hard rows, but it is still additive to the main raw
    codec and has max-frame misses, so it remains offline/future-bitstream
    evidence until integrated with the codec path and timed end to end.
- q3/q4 SR hard-row gate:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q3q4_sr_gate_20260619/summary.json`
  - Summary SHA-256:
    `5e1ecb4125bcd7c2b6f8fcb11a8b97794b02192400e7b395e762cb1b47c2c408`.
  - q3/t1 hard3 SR summary:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q3q4_sr_gate_20260619/q3_t1_all/preclean_step0200_hard3_fullframe/summary.json`
    with SHA-256
    `3f7089e810e47584f733bb16faa63bf5b267ad1846a537e8745c36cf18972c70`.
    It clears the focused hard rows with RMSE lift min `35.116%`, MAE lift min
    `23.786%`, gradient lift min `8.570%`, and PSNR14 min `54.363 dB`.
  - q4/t2 hard3 SR summary:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q3q4_sr_gate_20260619/q4_t2_all/preclean_step0200_hard3_fullframe/summary.json`
    with SHA-256
    `181c388491ff9073d34ce1bf838e73955272db101b63873c3928cceb21c38b8f`.
    It also clears the focused hard rows with RMSE lift min `35.019%`, MAE lift
    min `23.122%`, gradient lift min `8.080%`, and PSNR14 min `54.350 dB`.
  - Generated 8K `*_sr.raw` intermediates were deleted after scoring. The
    artifact root is `147M`, mostly retained reconstructed 12MP lows and
    dashboard/contact-sheet evidence.
  - Interpretation: q4/t2 gives the best current speed/size/quality tradeoff
    for the sidecar reconstruction direction on the focused hard rows.
- q4/t2 broad Mission42 and Z8 all24 SR gate:
  `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/summary.json`
  - Summary SHA-256:
    `3edc2ea7a7f00ab1d03f5ad2c7de8eb8b66e4b3ef7fc1e228f4d65d21d29065d`.
  - Mission42 summary:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/mission42_q4_t2_all/preclean_step0200_fullframe/summary.json`
    with SHA-256
    `a4630414fc3b4fa42a612ce9c8078e2ecdf42a46b418e6eb0de706ddb0ac59d8`.
    Across 42 full frames, q4/t2 plus the step-200 SR checkpoint records mean
    RMSE lift `54.443%`, mean MAE lift `43.074%`, mean gradient-MAE lift
    `22.299%`, and mean PSNR14 `52.420 dB`. Worst rows remain positive:
    RMSE lift min `35.019%`, MAE lift min `23.122%`, gradient lift min
    `8.080%`.
  - Z8 all24 summary:
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/z8_all24_q4_t2_all/preclean_step0200_fullframe/summary.json`
    with SHA-256
    `cf98bbbaba5d63df14646ca7981a7c74441a90e6c5c1161f80075ad91542d493`.
    Across 24 full frames, q4/t2 records mean RMSE lift `42.588%`, mean MAE
    lift `8.394%`, mean gradient-MAE lift `2.477%`, and mean PSNR14
    `53.890 dB`. The Z8 result is strong for amplitude/PSNR recovery but weak
    for edge/detail placement, with gradient lift min only `2.414%`.
  - Z8 high targets were regenerated from the DNG sidecar into
    `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_residual_q4t2_broad_gate_20260619/z8_all24_high_target_raw/manifest.json`
    with SHA-256
    `e954a8dc589bc3010ca0a2d5b9d141915d7f0de69df9f6c1212ecdb4d1d20162`.
  - Generated 8K `*_sr.raw` intermediates were deleted after scoring; the
    broad artifact root is `3.6G`, mostly retained Z8 high-target raws plus
    contact sheets and JSON receipts.
  - Interpretation: q4/t2 is now the best sidecar implementation candidate,
    but the broad Z8 all24 result shows it is still not a complete
    texture-placement solution. Next work is a fused codec-side
    implementation/timing pass plus a larger-context or sidecar-aware SR loss
    that raises Z8/Mission detail placement without giving up the Mission42
    reconstruction gains.
- Inference: the limiting information is now much more specifically located.
  A quantized same-color detail residual preserved by the encoder can recover
  the Mission blockers and improve Z8, while more CNN preclean depth could not.
  The next production experiment should move from oracle to implementation:
  add an encoder/decoder-side residual detail stream or equivalent
  phase/detail-preserving reconstruction mode, entropy-code its true cost, and
  rerun the Mission/Z8 SR gates plus Pi timing. The CNN should consume the
  reconstructed low source; it should not be expected to invent this lost
  detail from the current T233 low raw alone.

Before claiming production readiness, run one codec-aware SR probe that can change the `GP017346` failure mode:

1. Build a current-contract hard-tile corpus centered on the four remaining all-42 failures, especially `GP017346`.
   - Done for this pass: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_hardtiles_phase2_failures_20260618/phase2_failure_hardtiles_w128_s64_top192.json`
   - Re-mined from the current widened model: `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_hardtiles_wide_failures_20260618/wide_continue_failure_hardtiles_w128_s48_top256.json`
2. Stop doing plain low-LR continuations on the same tile objective; they improve too slowly and the 1600-step broad recovery regressed `GP017347`.
3. Next viable probes:
   - train against a full-frame/context-aware objective instead of crop-mined hard tiles,
   - revise the codec profile with an SR-aware low-frame error objective,
   - or add a deterministic codec-side cleanup/preclean transform before SR and prove it improves the hard rows without hurting Z8.
   - The first hard-tile-only preclean+aux probe moved the intended rows but overfit/regressed `GP017347`.
   - The broad preclean+aux step-200 checkpoint is the best metric candidate so far, but it still does not clear `GP017346`, `GP017349`, or `GP017600`.
   - The hard96 crop-mined continuation is rejected because crop/tile improvement diverged from full-frame blocker metrics.
   - The deterministic detail-shrink cleanup is rejected because the improvement is too small to clear the hard rows.
   - The standalone learned cleanup is rejected because low-clean tile improvement regressed full-frame SR blocker metrics.
   - The detail-content learned cleanup is rejected because both broad training
     and direct hard-row overfit improved the rows but still missed the
     hard-row MAE/gradient floors.
   - The preclean low-clean detail-aux continuation is rejected because it
     improved Z8 but left Mission worst-row deltas essentially unchanged.
   - The deeper preclean capacity probe is rejected because it improved Z8 but
     left Mission worst-row deltas essentially unchanged while reducing
     throughput.
  - The detail-residual side-channel oracle is the first current pass that
    recovers all three Mission blockers and improves Z8; next work should turn
    that side-channel idea into a measured encoder/decoder path.
   - Feeding detail-restored low raws directly into the existing registered
     SR checkpoint was tested on hard rows `GP017346`, `GP017349`, `GP017600`,
     and `GP017604`:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_restored_hardrows_eval_20260619/delta_summary.json`.
     The detail residual cut low-source RMSE from `5.10` to `2.42` counts
     mean, but SR quality regressed versus the plain current-codec baseline:
     mean RMSE-lift delta `-2.10` percentage points and mean PSNR delta
     `-0.90 dB`. This confirms the current CNN is distribution-coupled to the
     plain T233 low raws; detail-preserved lows need a retrained or fine-tuned
     SR model before they can be judged as a production candidate.
   - A retargeted Mission all-42 training pair set was built with the same
     targets but detail-restored inputs for hard rows `GP017346`, `GP017349`,
     `GP017600`, and `GP017604`:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_retarget_pairs_20260619/mission_all42_t233_detail_restored_hard4_inputs_w96.npz`.
     It contains `4032` tiles, with `384` retargeted hard-row tiles.
   - A 400-step fine-tune from the registered w48/d6 checkpoint confirms the
     direction is plausible but not production-ready:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_retarget_finetune_20260619/decision.json`.
     Step 400 improves mean RMSE-lift by `+3.66` points versus the old
     checkpoint on detail-restored lows, but only `+1.55` points versus the
     plain-current registered baseline and still has a worst-row delta of
     `-3.62` points. Do not promote it; continue with a longer guarded
     Mission+Z8 retargeted training pass or a residual-sidecar-aware objective.
   - A longer guarded Mission+Z8 retarget pass was run from the registered
     w48/d6 checkpoint:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_retarget_mixed_finetune_20260619/detail_retarget_mixed_decision.json`.
     It built a mixed Mission42+Z8 pair set with `6336` tiles, including `384`
     retargeted Mission hard-row tiles, then evaluated steps 400/800/1200/1600
     full-frame on Mission detail-restored hard rows and Z8 holdout.
   - The best continuation point is step 1200, but it is rejected for
     promotion. On detail-restored Mission hard rows it improves mean RMSE-lift
     by `+3.52` points versus the registered checkpoint on the same
     detail-restored inputs. However, on normal current-codec Mission lows it
     regresses mean RMSE-lift by `-2.71` points versus the registered checkpoint
     across the eight-image Mission holdout, and on Z8 it regresses mean
     RMSE-lift by `-8.76` points and mean PSNR by `-1.88 dB`.
   - Conclusion for the next pass: do not replace the shared registered SR
     checkpoint with this fine-tune. Continue with either a deterministic
     detail-sidecar specialist selected by runtime metadata, or a multi-domain
     loss that explicitly preserves the normal current-codec Mission and Z8
     manifolds while improving detail-restored Mission inputs.
   - A focused detail-sidecar specialist continuation was then run from the
     mixed step-1200 checkpoint:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_sidecar_specialist_20260619/detail_sidecar_specialist_decision.json`.
     This intentionally treats detail-restored inputs as a separate runtime
     path instead of replacing the shared registered checkpoint.
   - The best specialist checkpoint is step 600. It improves the
     detail-restored hard-row median RMSE-lift to `51.23%`, with all four hard
     rows positive and `GP017604` improving from `75.41` to `68.96` RMSE
     counts versus the mixed step-1200 checkpoint. However, it still does not
     beat the registered normal-input baseline on `GP017349` or `GP017604`, so
     it is not production-ready.
   - A lower-LR continuation from the step-600 specialist did not fix the
     remaining rows. The next sidecar-specialist attempt should mine hard tiles
     specifically from `GP017349` and `GP017604` and train an adapter/head while
     preserving the shared trunk, instead of continuing whole-trunk fine-tunes.
   - Adapter-only continuations were tested next:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_sidecar_adapter_from_specialist_20260619/detail_sidecar_adapter_decision.json`.
     Expanding the registered checkpoint into an adapter model and training
     only the adapter branch was effectively unchanged. Expanding the best
     sidecar-specialist trunk and training only the adapter branch gave tiny
     gains, but still trailed the registered normal-input baseline on
     `GP017349` and `GP017604`.
   - A hard-tile adapter pass then mined `320` full-frame failure tiles from
     `GP017349` and `GP017604`, built a focused detail-low pair corpus, and
     trained only the adapter branch:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_detail_sidecar_hardtile_adapter_20260619/hardtile_adapter_decision.json`.
     This improved `GP017604` modestly (`68.96` to `68.42` RMSE counts versus
     the best specialist), but `GP017349` remained effectively unchanged
     (`31.57` to `31.56` RMSE counts), and later checkpoints started trading
     off against `GP017346`.
   - Current narrowed blocker: `GP017349` is not responding to whole-trunk
     fine-tune, adapter-only fine-tune, or mined hard-tile adapter training.
     Before more CNN training, run a `GP017349` diagnostic that decomposes the
     mined-tile error into LF, gradient, CFA plane, and phase terms. The issue
     now looks more like a target/content or loss-feature mismatch than generic
     model capacity.
   - That `GP017349` decomposition was run:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_gp017349_error_decomposition_20260619/gp017349_error_decomposition_summary.json`.
     It compared the registered checkpoint, sidecar specialist,
     adapter-from-specialist, and hard-tile adapter against the same
     detail-restored low input and 50MP target.
   - Result: the sidecar specialist improves LF RMSE from `11.09` to `9.23`
     counts and total RMSE from `33.20` to `31.57` counts, but the remaining
     error is stable green-plane detail. `g1` detail RMSE stays near `31.8`
     counts and `g2` near `31.7` counts across the specialist, adapter, and
     hard-tile adapter. Detail correlation only moves from about `0.526` to
     `0.536`.
   - A green-plane-weighted hard-tile adapter probe was also rejected:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_gp017349_green_plane_adapter_20260619/green_step1200_gp017349_decomposition.json`.
     Emphasizing `g1/g2` in the loss did not reduce the green detail error;
     step 1200 still reports `g1` detail RMSE around `31.81` counts.
   - The deterministic `GP017349` green-plane phase/alignment oracle was run:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_gp017349_green_phase_oracle_20260619/gp017349_green_phase_oracle_decision.json`.
     Same-color green-detail +/- one-pixel shifts, `g1/g2` swap, and
     green-detail averaging all regressed versus identity; identity remains the
     best non-oracle variant with green-detail RMSE `31.77` counts.
   - Target-detail oracles do move the row: target-sign/model-magnitude green
     detail improves green-detail RMSE by `15.73%`, target-green-detail
     improves it by `83.35%`, and full target green planes reduce it to zero.
     This rules out a simple deterministic high-frame green-plane phase offset
     and points to missing/wrong green-detail signal prediction under the
     current target/loss/model contract.
   - Next experiment should train a green-detail signal model instead of another
     phase/swap probe: either a supervised green-detail residual head selected
     for the detail-sidecar runtime path, or a multi-output loss that predicts
     LF and green detail separately while preserving Mission normal-current and
     Z8 guardrails.
   - A zero-initialized `green_detail_adapter_pixelshuffle` branch was added and
     trained green-detail-only from the hard-tile adapter:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_green_detail_adapter_20260619/green_detail_adapter_decision.json`.
     The branch is function-preserving at initialization and is useful tooling,
     but the checkpoint is rejected for promotion.
   - Full-frame result: the green-detail branch improves `GP017604` to `66.22`
     RMSE counts at step 1200, but `GP017349` remains stuck around `31.56`
     counts with the best row at step 600. The hard-tile training gain does not
     generalize to the full-frame `GP017349` blocker, so the next pass needs
     full-frame/blocker-aware supervision or a larger-context green-detail
     target rather than another hard-tile-only continuation.
   - A broader Mission+Z8 green-detail-only pass was also rejected:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_green_detail_broad_adapter_20260619/green_detail_broad_adapter_decision.json`.
     It moves `GP017349` only marginally (`31.56` to `31.562` best observed
     RMSE counts in this pass) and loses the hard-tile pass's `GP017604`
     improvement, landing back around `68.42` RMSE counts. This rules out
     random broad-tile green-detail loss as the missing ingredient.
   - A 192px low-tile large-context `GP017349` corpus was mined from the actual
     full-frame model-vs-target miss and retargeted to detail-restored lows:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_gp017349_large_context_20260619/gp017349_large_context_decision.json`.
     This is the first non-oracle pass that materially moves `GP017349`
     full-frame: adapter+green continuation reaches `31.23` RMSE counts from
     the `31.56` hard-tile-adapter baseline.
   - It is still rejected for promotion. The same step-1800 specialist regresses
     the other hard rows when used as a shared model: `GP017346` rises to
     `30.19` RMSE counts and `GP017604` to `70.17`. The step-900 checkpoint is
     less severe but still not balanced, with `GP017349` at `31.47`,
     `GP017346` at `24.09`, and `GP017604` at `68.72`.
   - Next SR pass should build a mixed 192px large-context hard-row corpus mined
     from `GP017346`, `GP017349`, `GP017600`, and `GP017604`, then select by
     hard4 full-frame aggregate instead of optimizing a GP017349-only specialist.
   - That mixed 192px large-context hard4 pass was run and rejected for
     promotion:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_mixed_large_context_hard4_20260619/mixed_large_context_alpha010_decision.json`.
     It trained a mixed hard4 checkpoint and interpolated the balanced step
     `10%` toward the `GP017349` specialist. On the detail-restored/sidecar
     low distribution, the alpha-0.10 candidate improves the hard4 rows versus
     the prior hard-tile adapter baseline:
     `GP017346` RMSE `19.82 -> 19.23`, `GP017349` `31.56 -> 31.56`
     tiny improvement, `GP017600` `16.28 -> 16.27`, and `GP017604`
     `68.42 -> 68.02`.
   - The same alpha-0.10 candidate also beats the regenerated registered Z8
     baseline on all five Z8 holdout frames, with median RMSE-lift `31.29%`
     versus `27.36%` and minimum PSNR14 `51.60 dB` versus `51.16 dB`.
     However, it remains materially behind the stronger all24 Z8 guardrail
     (`41.67%` median RMSE-lift and `54.09 dB` minimum PSNR14), so it is
     useful evidence but not a production checkpoint.
   - A normal current-codec hard4 check closes the production-path question:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_mixed_large_context_hard4_20260619/interp_a100_normal_current_hard4_fullframe/summary.json`.
     On those normal lows, alpha-0.10 regresses every shared hard row versus
     all24: `GP017346` RMSE `20.44 -> 22.06`, `GP017349` `30.37 -> 32.28`,
     `GP017600` `17.14 -> 19.48`, and `GP017604` `66.11 -> 74.70`.
   - Current SR read: large-context hard-row supervision can move the
     detail-restored/sidecar distribution, but it should not replace or route
     into the normal current-codec production low path. Keep all24 as the
     normal-low baseline. The next pass is either a deterministic routed
     sidecar specialist with a guardrail that chooses all24 for normal lows, or
     a shared model trained with explicit all24/Z8 preservation loss and no
     normal-current hard-row regression.
   - The context192 end-to-end continuation is rejected because larger local context improved tile eval but still regressed the full-frame blocker set.
   - Scoped adapter/preclean finetuning is rejected because it still collapsed the full-frame hard rows after updates; freezing the trunk did not fix the tile/full-frame objective mismatch.
   - A q4/t2 sidecar-aware broad continuation was run from the preclean
     step-200 checkpoint using Mission42 plus Z8 all24 training pairs retargeted
     to q4/t2 detail-residual lows:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/guarded_experiment_summary.json`.
     The merged training pair set is
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/mission42_z8_all24_q4t2_inputs_w96.npz`
     with sha256
     `d6976cbf92729b78eeff7bf0c6b0f79e550c7d895bd64a7db21a61a0e9526d62`.
   - The selected checkpoint is
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_q4t2_sidecar_aware_train_20260619/sidecar_aware_preclean_step0200_continue_s400/q4t2_sidecar_aware_preclean_continue_s400.pt`
     with sha256
     `a16579f2aacd6edbadc3931ab112a3ff52566bd4f8a6245c95b246b16af98bb5`.
     Its training receipt hash is
     `9b20c909e5a48f376933a81a9de26cf21223b05d20ec7f8f46b541d9a907018b`;
     the final decision receipt hash is
     `660f22cf85c392b9e43d7ce5f525fa5f4450f51905f3629934ee48a18f1d850b`.
   - Decision result:
     `promote_for_registry_review`, not production. Compared with the previous
     q4/t2 preclean step-200 broad gate, the final candidate improves Mission
     PSNR14 floor by `0.6300 dB`, Mission RMSE median by `2.9622` points,
     Mission RMSE floor by `1.3811` points, Z8 all24 PSNR14 floor by
     `0.2667 dB`, and Z8 all24 RMSE floor by `1.7409` points. The final
     Mission42 summary hash is
     `7a0c23293336fc52e246aed4f3cff5aee26f787c97a724239c2fdb282fd1330d`;
     the final Z8 all24 summary hash is
     `a18e5c14a9d5c96727d86fa492e5c06ae19b4a4123c84438345c7b66e233174a`.
   - Production boundary: this is the best current sidecar-aware 8K SR
     registry-review candidate, but it is still an offline/upscale candidate.
     It is registered behind temporary pipeline id
     `codec=mission1_native12_t233+cnn=mission1_native12_8k_sr_q4t2_sidecar_aware_s400_v1+demosaic=sips_via_gpr_tools`
     with `production_scope=offline_review_only`.
   - The registry-driven `.gvid` receipt was refreshed from the known-good
     120-frame native12 capture
     `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_corrected_q8_local_gvid_120f_20260617/capture.gvid`
     because the older small `mission1_native12.gvid` fixture no longer matches
     the successful decode payload size. The three-frame q4/t2 sidecar-aware
     receipt is
     `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_multiframe_20260619/receipt.json`
     with sha256
     `b79cac5b1ad12bdeeddac0bb4b53bc806b45c5822fb6ac6fe1267f5d4a6501d1`.
     It records 120 source frames, 8,765,001-byte frame payloads, median
     decode+SR+write `0.8581 s/frame` (`1.165 fps`), and peak RSS
     `1204.4 MB` on MPS. This is offline only.
   - The retained-render receipt is
     `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_packaging_20260619/receipt.json`
     with sha256
     `9bd45a49a13b344498907f7c0532a120fff2944382a9659bd1db9870f39d2e57`.
     The q3 editable/review packaging receipt is
     `/Volumes/OWC_8TB/gpr_work/artifacts/mission1_native12_gvid_to_8k_sr_q4t2_sidecar_aware_packaging_q3_20260619/packaging_receipt.json`
     with sha256
     `eab82ddaa985e2ce6f1667ee5ad025f60a87fc8ee4d4e83504a3121e5975c8f8`.
     It writes a 27.6 MB SDK-wrapped editable GPR, converts it back to DNG
     openable as `8192x6144`, and emits 2048x1536 ProRes review MOVs. Editable
     GPR readback PSNR14 is `52.95 dB`.
   - Remaining boundary: the candidate has one paired Mission regression versus
     the previous q4/t2 candidate: `GP017346` moves backward by `0.7933` RMSE
     counts and `0.1803 dB` PSNR, even though the broad Mission floors improve.
     It also needs a full production audit refresh if it is to replace the
     current offline candidate. Do not promote it as a live/camera path.
   - A checkpoint interpolation probe between the previous q4/t2 step-200
     candidate and the sidecar-aware step-400 candidate was run:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_q4t2_sidecar_aware_interp_probe_20260619/interpolation_decision_summary.json`
     with sha256
     `8b6972e2cb4dfecb05c0c89229e029c1647a06276c7937da3f9fae497c01b8da`.
     Decision: `reject_interpolations_keep_step400_as_review_candidate`.
     Alpha `0.25`, `0.50`, and `0.75` were tested against the Mission hard4
     set and the Z8 all24 holdout. Lower alpha preserves more `GP017346`
     gradient margin, while higher alpha improves the broader Z8/Mission
     metrics. None resolves the hard-row issue or beats step-400 on the broad
     holdout floors, so linear checkpoint blending is not the next production
     path.
   - A machine-readable production gap report now freezes this boundary:
     `/Volumes/OWC_8TB/gpr_work/artifacts/current_goal_sr_production_gap_report_20260619/summary.json`
     with sha256
     `f1fbd618a812183667e7c69fbe1d083bf384e45eccc4411f9823fa237c8f17b9`.
     It classifies the q4/t2 sidecar-aware candidate as
     `offline_registry_review_not_production`. Packaging is passing, but the
     remaining blockers are live timing (`1.165 fps` decode+SR+write),
     `GP017346` paired RMSE/PSNR regression, Mission metadata transplant not
     refreshed for this checkpoint, native12 strict-24 capture still open, and
     rejected checkpoint interpolation. The next SR work should therefore
     target a full-frame/blocker-aware objective or a routed normal-low versus
     q4/t2-sidecar policy, not more scalar checkpoint blending.
4. Evaluate:
   - Mission all-42 full-frame gate,
   - Z8 holdout,
   - router feasibility if the wider expert is Mission-only.

Until that passes, the 8K SR path should stay experimental. The 12MP native raw-video path and stills path are separate and should not be blocked by this SR checkpoint.
