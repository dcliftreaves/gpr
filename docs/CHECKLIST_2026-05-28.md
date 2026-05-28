# Working checklist — 2026-05-28

Everything we discussed, organized for execution. Items in priority order
within each section.

## (1) Codify stills vs video — APPROVED — **DONE** (commits 541134c, ecf9822)

- [x] Add `use_for` field to every codec entry in `pipelines/registry.json`
- [x] Mark FUSED single-level codecs as `deprecated`
- [x] Mark legacy `gpr_tools_q3` and `gpr_tools_legacy` as `still`
- [x] Mark `ml2_q3*` codecs as `video`, `ml3_*` and experimental sweep
      codecs as `experiment`
- [x] Update SHIP_DECISION.md to show two cleanly separated modes
- [x] Add a registry consistency check
      (`tests/quality_gates/check_registry_consistency.py`)
- [x] Drop the FUSED single-level *pipelines* from SHIP_DECISION
- [x] Wire the consistency check into CI

## (2) Stills q-level table — **DONE**

Built and shipped 2026-05-28. See `STILLS_PI5_TIMING.md` and
`FULL_PIPELINE_MATRIX.md`. Key finding: q=8 codec-alone PASSes STILL
without CNN; the matched-q3 CNN generalizes down to q=0; codec saturates
above q=6. Three-tier ship possible (q=0/q=3/q=8) spanning 3.4× storage.

- [x] q=8 gate-tested; PASSes STILL without CNN (LPIPS 0.0035, archival
      alternate added to ship matrix)
- [x] Matched-CNN retrain confirmed to generalize across q=0..3
- [x] Pi 5 encode timing at q=0/3/5/8 captured (in STILLS_PI5_TIMING.md)
- [x] Full table compiled with codec MB × end-to-end LPIPS × MS-SSIM ×
      Y-PSNR × Pi 5 ms

## (3) Legacy encoder perf work — **DONE** (3 commits 2026-05-28)

Three Pi 5 perf passes landed today:

- [x] Pass 1 (commit 79403fb): skip redundant DNG metadata pre-parse —
      38% off baseline (1577 → 966 ms at q=3 on Z8Z_0067)
- [x] Pass 2 (commit ec1cb2c): parallel DNG tile read on POSIX +
      `qDNGThreadSafe` Linux bugfix — 43% off that, 65% off original
      baseline (966 → 544 ms at q=3). Bitstream-identical, 10/10
      deterministic.
- [x] Profile harness (commit 4fbd0cc): GPR_PI_PROFILE-gated phase
      timing in main_c.c + gpr.cpp for future perf passes
- [-] Pass 3 (in-flight subagent, branch `worktree-agent-a5350dea*`):
      FFTW/FFmpeg-style cache-line alignment of VC5 encoder hot path
      (`vc5_encoder/encoder.c`, `vc5_common/wavelet.c`, `image.c`)
- [-] Video-path Pi 5 profiling (in-flight subagent, branch
      `worktree-agent-abe488be*`): profile FUSED encoder, find biggest
      parallelizable chunk

Net so far on Z8Z_0067 q=3: 1577 → 544 ms (**2.89×**). Mac 819 → 212 ms
(**3.86×**).

## (4) Methodology / testing audit — partial done

- [x] Document three test layers explicitly
      (`docs/TESTING_METHODOLOGY.md`)
- [x] Add registry consistency check to CI
- [ ] `test_capabilities.py`: add CNN-corrected rows for the legacy
      stills ship (Layer 1+2 unified)
- [ ] Add per-pipeline gate-run reference to SHIP_DECISION (run-hash per row)
- [ ] CI: add the perceptual gate as a CI cell for the ship pipelines, not
      just test_capabilities (needs MPS-capable macOS runner)
- [ ] Verify every shipping pipeline has at least one passing gate run
      checked into `tests/quality_gates/runs/`
- [ ] Consider splitting `test_capabilities.py` into `test_stills.py` and
      `test_video.py` to mirror the codified split

## (5) Video side — status documented

- [x] Document the two video paths and which one ships for what
      (`docs/VIDEO_STATUS.md`)
- [x] Confirmed full-res VIDEO_FREEZE ship is desktop-only
      (Pi 5 ~0.5 fps full-res, not 24-capable)
- [x] Confirmed Pi capture path is half-res ml2_q3_dec2 (24.93 fps)
      but the restoration CNN doesn't yet PASS PREVIEW

Open follow-ups:
- [ ] BIDO Phase B (Restormer-teacher distillation) — close the
      embedded-preview gap. ~6 hours on M5.
- [ ] Try the legacy-encoder methodology for video too (legacy gpr_tools
      at q=3, matched ML-2-style CNN). Could be smaller per-frame than
      FUSED ml2_q3. ~3 hours.

## (6) Operator-only (Claude can't do)

- [ ] `run_gate.py <pipeline> --claim` for the new STILL primary
      (`gpr_tools_q3+matched CNN`) — type the inspection sentence
- [ ] Same for the VIDEO_FREEZE primary (`ml2_q3_l1x2+matched CNN`)
- [ ] Same for the post-threshold-bump alternates (`ml2_q3_l2x2_l1x2`,
      `ml2_q3_l1x2_hh1x4`)

## (7) Open follow-ups, lower priority

- [ ] Cranked-CNN retrain for `ml2_q3_l2x2_l1x4` with broader corpus
      (this session's partial training hurt OOD)
- [ ] Higher-quality STILL alternate via legacy q=5 + CNN
- [ ] Refresh `docs/CAPABILITIES.md` with the new codec/CNN ship matrix

## Decisions waiting on user

- (a) Drop FUSED single-level pipelines entirely (delete codec entries)
      vs keep as `deprecated`? — current plan is keep as `deprecated`
- (b) Push the STILL gate further? Worst LPIPS 0.0155 leaves a lot of
      headroom under the 0.05 ceiling. Could go to legacy q=1 or q=2
      for another ~20-30% size reduction.
- (c) Refresh `CAPABILITIES.md` to reflect the new ship state (legacy +
      CNN), or kill it in favor of the perceptual gate as source of truth?
