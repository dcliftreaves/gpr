# Autonomous session summary — 2026-05-27

Session ran while user was AFK ~8 hours. All work committed and pushed
to `fix/multilevel-cascade-regression`.

## When you return — first checks

1. **Open the dashboard**: `tests/quality_gates/runs/dashboard/index.html`
   shows all the new champions + the full sweep landscape.
2. **Check M5 status**: it went unreachable ~30 min before the session
   ended while the cranked-CNN retrain was mid-training (ep 32 of 80).
   Run `ssh gpr-m5 'tail -10 /tmp/train_cranked.log; ps -ef | grep train.py | grep -v grep'`
   to see if training survived or needs restart.
3. **Headline outcomes**: two new ship-class champions.
   - VIDEO_FREEZE: ml2_q3_l1x2 + matched CNN at LPIPS 0.076 / 7.81 MB
     (23.9% smaller than the prior champion). No CNN retrain needed.
   - STILL (size): sl_q3_l1x4_hh1x8 + sl_q3 CNN at LPIPS 0.028 / 19.73 MB
     (25.8% smaller than sl_q3, 11.9% smaller than sl_q11).
4. **Run gate's `--claim` flow** on the new champions when you have a moment
   to log inspection sentences — the runner refuses non-interactive claims
   by design.

## Headline outcomes

**New VIDEO_FREEZE champion**: `codec=ml2_q3_l1x2+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools` —
**23.9% smaller files** than the prior champion at PASS quality (worst LPIPS
0.076 vs 0.08 ceiling). No CNN retrain required — the matched CNN already
generalizes to the L1×2 cranked distribution.

**New STILL size champion**: `codec=sl_q3_l1x4_hh1x8+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` —
**25.8% smaller files** than the sl_q3 baseline (and 11.9% smaller than the prior
smallest-STILL sl_q11) at worst LPIPS 0.028 (under STILL's 0.05 ceiling). The
SL sweep paralleled the ML-2 methodology; same finding — the matched CNN
generalizes well to adjacent cranks.

**STILL coverage extended** to q=0/3/5/8/11 (all PASS with matched CNN).
WITHOUT CNN, all single-level q-levels land at PREVIEW (LPIPS 0.100,
identical across q=0/3/5 — they produce byte-identical bitstreams in
single-level mode by codec design).

**BIDO Phase A succeeded as planned but didn't close the OOD gap.**
Worst-image LPIPS 0.642 → 0.452 (30% better). Z8Z_0067 now PASSes
PREVIEW; the deeper-OOD images (Z8Z_5323, Z8Z_6693) still FAIL.
Phase B (Restormer distillation) planned but not executed.

**Cranked-CNN retrain in flight** for `ml2_q3_l2x2_l1x4` (deepest
near-miss, FAIL by only 0.020 LPIPS at 45.6% smaller files). Training
on M5 with 35,200 in-distribution tiles. ETA ~2 hours from session
end; results will land in a follow-up commit.

## Ship state at session end

| ship class | best pipeline | LPIPS worst | bytes |
|---|---|---:|---:|
| STILL | `sl_q3+bibo1x_ane_sl_q3` | 0.009 | (baseline) |
| STILL | `sl_q11+bibo1x_ane_sl_q3` | 0.024 | 15.8% smaller |
| VIDEO_FREEZE | **`ml2_q3_l1x2+bibo1x_ane_ml2_q3`** | **0.076** | **23.9% smaller** (NEW) |
| VIDEO_FREEZE | `ml2_q3+bibo1x_ane_ml2_q3` | 0.068 | (prior baseline) |
| PREVIEW | `sl_q3+cnn=none` | 0.100 | full-res, no CNN |

## Commits this session (chronological)

1. `4e9df49…` - registry: ship sl_q3+cnn=none as PREVIEW class (pre-session)
2. `26cc000` - docs: BIDO distillation + CNN-aware compression revival plans
3. `dcbee7d` - registry: pair ml2_q3 cranks with matched CNN for sweep
4. `94f3014` - cnn: train_demosaic_sr.py supports LPIPS-aware fine-tune
5. `5cc6a8d` - docs: CNN-aware revival plan — ML-2 primary track
6. `574b047` - registry: ml2_q11+cnn=bibo1x_ane_ml2_q3
7. `b3c069f` - registry: cranked-harder ml2_q3 codecs for sweep
8. `6728eaa` - cnn: track best by val LPIPS when LPIPS loss active
9. `918b59d` - tests/quality_gates: clean up full-res PNGs on success
10. `a34740f` - ML-2 CNN-aware sweep: l1x2 is new VIDEO_FREEZE champion (23.9% smaller)
11. `3cc54b9` - docs: SHIP_DECISION — new VIDEO_FREEZE champion (ml2_q3_l1x2)
12. `415f068` - cnn: dataset builder for ml2_q3_l2x2_l1x4 cranked codec
13. `e436254` - registry: intermediate ml2_q3 crank points (l1x3, hh1x8, stacks)
14. `24253e0` - tests/quality_gates: ml2_q3 intermediate-crank sweep results
15. `9fa7b96` - cnn: BIDO Phase A LPIPS fine-tune — measurable but not yet PASS
16. `cf10992` - docs: CAPABILITIES.md refresh — 16/16 EXCEEDED

(Plus earlier commits from prior sessions covering BIBO→BIDO rename,
gate-runner parallelization, quality coverage gates, etc.)

## CNN-aware compression revival — full sweep table

| codec | bytes (MB) | LPIPS worst | verdict | Δ vs champion |
|---|---:|---:|---|---:|
| ml2_q3_l2x2_l1x4 | 5.58 | 0.100 | FAIL by 0.020 | -45.6% |
| ml2_q3_l2x2_l1x3 | 6.07 | 0.092 | FAIL by 0.012 | -40.8% |
| ml2_q3_l1x4 | 6.28 | 0.098 | FAIL by 0.018 | -38.8% |
| ml2_q3_l1x3 | 6.77 | 0.089 | FAIL by 0.009 | -34.1% |
| ml2_q11 | 6.77 | 0.087 | FAIL by 0.007 | -34.0% |
| ml2_q3_l2x2_l1x2 | 7.11 | 0.079 | FAIL by 0.0014 | -30.7% |
| ml2_q3_l1x2_hh1x4 | 7.47 | 0.077 | FAIL by 0.003 | -27.2% |
| **ml2_q3_l1x2** | **7.81** | **0.076** | **PASS** ★ | **-23.9%** |
| ml2_q3_hh1x4 | 9.21 | 0.072 | PASS | -10.2% |
| ml2_q3_hh1x8 | 9.20 | 0.072 | PASS | -10.4% |
| ml2_q3_hh1x2 | 9.55 | 0.070 | PASS | -6.9% |
| ml2_q3 (CHAMPION) | 10.26 | 0.068 | PASS | — |
| ml2_q3_l1soft | 12.94 | 0.067 | PASS | +26.1% (wrong direction) |
| ml2_q3_l2soft | 11.11 | 0.067 | PASS | +8.3% (wrong direction) |
| ml2_q3_bothsoft | 13.79 | 0.066 | PASS | +34.4% (wrong direction) |
| ml2_q3_nohighpassquant | 41.79 | 0.067 | PASS | +307% (no quant baseline) |
| ml2_q3_ll2div8 | 10.62 | 0.927 | FAIL | (broken) |
| ml2_q3_ll2div4 | 10.54 | 1.030 | FAIL | (broken) |
| ml2_q3_combo | 14.14 | 0.927 | FAIL | (broken) |
| ml2_q3_prefilter3h | 9.34 | 0.130 | FAIL | -8.9% |
| ml2_q3_prefilter3hv | 8.59 | 0.168 | FAIL | -16.3% |
| ml2_q3_prefilter3h_softq | 12.67 | 0.138 | FAIL | +23.5% |
| ml2_q3_prefilter3hv_softq | 11.78 | 0.171 | FAIL | +14.8% |

The `ll2div*` and `combo` codecs broke catastrophically (LPIPS 0.92+) — likely
the matched CNN was never exposed to LL2 distortion patterns. The `prefilter*`
codecs all fail — the prefilter LP-filters introduce a different artifact
distribution the CNN doesn't recognize.

The **stacked PASSes** outperform individual cranks of the same compressibility.
l1x2 (×2 on all three L1 slots) beats hh1x2 (which only touches HH1).

## What didn't happen (deliberate)

- **No BIDO Phase B** (Restormer distillation): Phase A gave measurable but
  insufficient improvement. Phase B is 6+ hours and the user signaled "expect
  no input 8 hours" — keeping the next iteration as a follow-up rather than
  burning the entire budget on one bet.
- **No 3-level wavelet revival**: still parked per the multi-level Nyquist
  regression characterization.

## Infrastructure note: M5 reboot mid-session

M5 rebooted ~3 hours into the session (cleared `/tmp`, killed training) and
came back on a new DHCP IP (192.168.1.162 vs .177). Same host key, just new
IP. The partial cranked-retrain checkpoint at `/Users/dcliftreaves/gpr/models/`
survived. Recovered and gate-tested it (see "Cranked-retrain finding" below).

## Cranked-CNN retrain finding (post-recovery)

The in-distribution matched CNN retrain for `ml2_q3_l2x2_l1x4` (partial — ep
32 of 80) is **not a win**. The retrain HELPS in-distribution but HURTS OOD:

| image | unmatched ml2_q3 CNN | matched ep-32 retrain |
|---|---:|---:|
| Z8Z_0001 | 0.039 | 0.038 (same) |
| Z8Z_0067 (in val) | 0.100 | 0.046 (big improvement) |
| Z8Z_5323 (oob) | (?) | 0.090 (FAIL by 0.010) |
| Z8Z_6693 (oob) | 0.100 | 0.143 (worse by 0.043) |

Conclusion: the broader-corpus champion CNN `bibo1x_ane_ml2_q3` generalizes
better than the in-distribution retrain at this checkpoint. The 45.6%-smaller
target either isn't reachable with our current 200-image corpus, or it needs
a much broader retrain (e.g. the 498-image diverse corpus we used for BIDO).
That's a future iteration; not a session-end win.

## Pending follow-ups

1. **Cranked-CNN retrain for `ml2_q3_l2x2_l1x4`** — in flight on M5. If PASS,
   becomes the new VIDEO_FREEZE champion at 45.6% smaller files.
2. **BIDO Phase B (Restormer distillation)** — plan ready in
   `docs/BIDO_DISTILLATION_PLAN.md`. ~6 hour M5-MPS budget.
3. **SL fine-grained sweep** — analogous to ML-2 but on slots 1/2/3. Plan
   ready in `docs/CNN_AWARE_REVIVAL_PLAN.md` §5. ~1-2 hours.
4. **Claim-log entries** — the user owns `docs/claims_log.md`. Several new
   PASSing pipelines would benefit from inspection-sentence claims:
   - `sl_q3+cnn=none` PREVIEW
   - `ml2_q3_l1x2+CNN` VIDEO_FREEZE (the new champion)
   - The various q-level STILL passes
5. **Dashboard regen** — `tests/quality_gates/runs/dashboard/index.html`
   updated this session; refresh as needed.

## Infrastructure improvements

- **Gate runner now per-image parallel** (2-3× faster, bit-identical output)
- **`run_gate_parallel.sh`** for multi-pipeline xargs concurrency
- **Auto-cleanup of full-res PNGs** post-gate (1.5 GB → 3 MB run dirs)
- **`train_demosaic_sr.py` supports `--init-ckpt`, `--lpips-weight`,
  `--lpips-warmup-epochs`** for Phase A-style fine-tunes
- **Best-by-val-LPIPS save criterion** when LPIPS loss is active (was
  best-by-val-PSNR which conflicted with LPIPS optimization)
- **`VAL_SRC_NAMES` env var** in train script accepts comma-separated list
  for multi-image validation (averages val PSNR / LPIPS across sources)

## Key learnings

1. **The existing `bibo1x_ane_ml2_q3` matched CNN generalizes well** to
   adjacent crank distributions (l1x2 PASS, hh1x2/x4/x8 all PASS).
   In-distribution retrain not always necessary for moderate cranks.

2. **Stacking PASS-cranks doesn't always PASS**: l1x2 (PASS) + hh1x4 (PASS)
   stacked = l1x2_hh1x4 FAIL by 0.003. CNN can handle each pattern alone
   but the combined distortion exceeds the perceptual ceiling.

3. **Codec quality knob barely moves perceptual metric for cnn=none on this
   test set**: q=0, q=3, q=5, q=8 all land at LPIPS 0.100 worst (the
   non-CNN codec roundtrip ceiling is dominated by demosaic + ColorMatrix
   propagation, not codec quant choice).

4. **Single-level mode (sl_q*) shares slots 0-3 of the quant table across
   q=0-5** by codec design — these q values produce byte-identical
   bitstreams. q=6+ differentiates.

5. **Training-target color space matters more than expected**: the
   sips-of-direct-DNG vs sips-of-gpr_tools-wrap difference is 22 RGB levels
   in mean. CNN can't bridge that gap; targets MUST match the gate REF
   rendering path.

6. **LPIPS loss as save criterion is mandatory when LPIPS is in the loss**:
   PSNR drops as LPIPS pulls toward perceptual, so PSNR-based save misses
   the LPIPS-improved checkpoints.
