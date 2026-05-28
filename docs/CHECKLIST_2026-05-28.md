# Working checklist — 2026-05-28

Everything we discussed, organized for execution. Items in priority order
within each section.

## (1) Codify stills vs video — APPROVED

- [ ] Add `use_for` field to every codec entry in `pipelines/registry.json`:
      `still` | `video` | `experiment` | `deprecated`
- [ ] Mark FUSED single-level codecs (`sl_q3`, `sl_q11`, `sl_q3_l1x4_hh1x8`,
      `sl_q3_hh1x{2,4,8}`, `sl_q3_l1x{2,3,4}`) as `deprecated` (keep entries so
      existing run.json files resolve, but they don't appear in ship table)
- [ ] Mark legacy `gpr_tools_q3` as `still`
- [ ] Mark `ml2_q3*` and `sl_q3_dec2*` and `ml3_*` as `video` or `experiment`
- [ ] Update SHIP_DECISION.md to show only two cleanly separated modes
- [ ] Add a registry consistency check (warn when still codec paired with
      video CNN or vice-versa)
- [ ] Drop the FUSED single-level *pipelines* from SHIP_DECISION (keep
      codec entries in registry)

## (2) Stills q-level table — APPROVED

For the user-facing trade-off table on legacy gpr_tools encoder:

- [ ] Build training pairs for legacy q=8 (Filmscan-5, highest quality preset)
- [ ] Train matched CNN at q=8 on M5 (~90 min)
- [ ] Gate-test `codec=gpr_tools_q8+cnn=bibo1x_ane_gpr_tools_q8+demosaic=sips_via_gpr_tools`
- [ ] Pi 5 encode timing at q=0/3/5/8 on real DNG (~10 min/q × 4 = 40 min)
- [ ] Compile the final table: q × bytes × LPIPS × Y-PSNR × Pi5 ms × MS-SSIM

Optional follow-ups in this track:
- [ ] q=5 matched CNN retrain (~2 hr more)
- [ ] q=1 / q=2 matched CNN retrain (push the smallest end)

## (3) Legacy encoder perf work — IN FLIGHT (subagent)

- [-] Profile current encoder on the 4 gate images
- [-] Memory alignment audit
- [-] NEON intrinsics where scalar today
- [-] Cache-friendly tiling
- [-] Multi-threading on color-plane / row-stripe boundaries
- [-] Verify bitstream byte-identical after every change
- [-] Report speedup achieved

## (4) Methodology / testing audit

- [ ] `test_capabilities.py`: currently benchmarks legacy encoder bare; add
      a CNN-corrected row that actually exercises the ship pipeline
- [ ] Add per-pipeline gate-run reference to SHIP_DECISION (run-hash per row)
- [ ] CI: add the perceptual gate as a CI cell for the ship pipelines, not
      just test_capabilities
- [ ] Verify every shipping pipeline has at least one passing gate run
      checked into `tests/quality_gates/runs/`
- [ ] Consider splitting `test_capabilities.py` into `test_stills.py` and
      `test_video.py` to mirror the codified split

## (5) Video side

Honest status check first:
- [ ] Confirm the full-res VIDEO_FREEZE ship `ml2_q3_l1x2+CNN` is intended
      for desktop post-processing, not embedded capture (24 fps on Pi 5
      not achievable at full-res)
- [ ] Confirm the Pi-capture path is `ml2_q3_dec2` (half-res), captures at
      24.93 fps median — but the restoration CNN (BIDO_4x) doesn't yet
      PASS PREVIEW gate

Possible next steps:
- [ ] BIDO Phase B (Restormer-teacher distillation) — close the
      embedded-preview gap. ~6 hours on M5. Plan in `docs/BIDO_DISTILLATION_PLAN.md`.
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
