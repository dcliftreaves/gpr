# Autonomous run 2026-05-25 — what happened while you were away

> **⚠ Evening update (same day):** the morning run's "headline" results
> were measured against a broken codec path (FUSED multi-level has a
> ~10 dB visual-quality regression vs single-level). Read
> `docs/REGRESSION_2026-05-25.md` for the corrected picture.
> Specifically: the +5.6 dB CNN gain (PR #19), the +7.80 dB L1+L2 number
> (in-flight when this doc was written), and the 22% file-size savings
> from q=12 are all numbers measured on multi-level. On single-level
> the equivalent cranks give 8.8% (HH×4) to 26.2% (LH/HL/HH ×8).
> The retrained CNN checkpoints were trained on multi-level outputs
> and won't help (may hurt) on single-level codec output.

Read-this-first artifact. Single doc that ties together everything that
shipped, what's pending, and what decisions are waiting on you.

Length budget: 5 minutes to read. Pointer-only — every claim links to
the underlying artifact.

## Headline

**14 PRs merged** to master in an 8-hour autonomous session. 0 reverts,
0 broken CI on master. Codec quality at q≥6 fixed on both content
classes (highlights + dark). CNN-aware quant methodology proven with
+5.6 dB CNN gain unlock on the retrained checkpoint. Full bitstream
spec written (5707 words). Pi 5 storage budget cleared — any consumer
microSD now handles 24 fps × 50 MP capture.

## Where to start reading (in priority order)

1. **`docs/SHIP_DECISION.md`** — the decision-ready artifact. Three
   ship options laid out against today's data. Tells you the explicit
   choice points awaiting your call.

2. **`docs/session_2026-05-25_progress.md`** — full session log: every
   PR, every empirical finding, the stacked-knob 22% file size win.

3. **`docs/SPEC.md`** — the formal bitstream format spec (5707 words,
   898 lines). This is the contribution-ready artifact for GoPro.

4. **`docs/methodology_cnn_aware_quant.md`** — the AccelIR-style
   methodology writeup, paper-style, 2070 words.

5. **`docs/perf_findings_20260525.md`** — Apple Silicon profile pass.
   Bottom line: CNN at w=16 is at the GPU compute floor on M1 Pro.
   No surgical optimization possible without arch change.

6. **`docs/quant_calibration_findings.md`** — empirical rate-distortion
   data. The methodology doc cites this.

7. **`docs/ENV_VAR_CLEANUP.md`** — durable env-var inventory + future
   cleanup plan. Most env vars are still load-bearing; this is the
   future plan when we're ready to lock the spec.

## Today's PRs (chronological)

| PR | Subject | Why it matters |
|---|---|---|
| #16 | Encoder L3 highpass quant floor | q=7/8 fix on highlights-heavy content |
| #17 | CNN-PSNR + sustained-fps regressions in CI | Locked the 26 fps × UHD win |
| #18 | bench_fused GPR_BENCH_WRITE_ALL | Honest sustained-write benchmarks |
| #19 | Retrained-CNN findings doc | +5.6 dB CNN gain documented |
| #20 | Encoder per-band quant floor (slots 1-9) | q=7/8 fix on dark content (the second bug) |
| #21 | **q=11 CNN-aware preset + ENV_VAR_CLEANUP.md** | New shipping preset |
| #22 | q=11 capability cell | Regression locks |
| #23 | docs/methodology_cnn_aware_quant.md | Methodology writeup |
| #24 | docs/session_2026-05-25_progress.md | Roll-up doc |
| #25 | docs/SHIP_DECISION.md | Decision artifact |
| #26 | **docs/SPEC.md** | Formal bitstream spec |
| #27 | perf: profile playback pipeline | CNN is GPU compute-bound (no 5% win without arch change) |
| #28 | docs roll-up update | Adds SPEC.md to the roll-up |

## Decisions waiting on you

### 1. Ship q=11 retrained CNN as production default?

- **Yes (Option A in SHIP_DECISION.md)**: 5% smaller files, no quality
  regression, well-validated. ~2-3 hours of code + tests.
- **No (Option C)**: keep current behavior, contribute the methodology
  and let GoPro pick the operating point. My recommendation per the
  pre-release-contribution framing.

### 2. Build out q=12 (L1+L2 cranks)?

The stacked-crank table in SHIP_DECISION.md shows L1+L2 ×2 = **22%
file savings** (vs 5% for q=11 alone). To ship q=12 confidently,
needs a CNN retrained on L1+L2 cranked data. **Already in flight** —
see "In flight when you read this" below.

### 3. Replace the BIBO_1x checkpoint in the production weights dir
   with the HH1×4 retrained version?

The retrained ckpt is at
`/Users/dcliftreaves/dering_proto_v2/checkpoints/BayInBayOut_1x_AAon_w16_ANE_HH1x4.pt`.
The shipping path uses
`/Volumes/OWC_8TB/gpr_work/artifacts/weights/F_ane_1x_weights_metal/` —
which still has the LL-only-fast-trained baseline. Swapping in the
retrained ckpt: 30 min of work, would change the production CNN
behavior. Not done autonomously because it's a behavioral change
worth your eyes.

## In flight when you read this

Two M5 training jobs are queued:

1. **BIBO_2x retraining** — analog of HH1×4 retraining for the
   super-res variant. ep ~22/80 last poll. ETA: ~65 min from this
   doc commit. Will produce
   `BayInBayOut_2x_AAon_w16_ANE_HH1x4.pt`.

2. **L1+L2 retraining (queued)** — subagent is waiting for #1 to
   finish, then will train a third checkpoint on combined L1+L2
   cranks. ETA: another ~90 min after #1 finishes. Validates the
   q=12 hypothesis (22% file size savings).

Both end-state results will land as PRs or task updates once they
return. Logarithmic polling continues in background.

## Tasks state at end of session

```
✅ #155-#157  Half-res topology + decode + CNN at codec-dim
✅ #158       CNN-aware per-subband quant calibration (M5 retraining)
✅ #159       q=5→q=7/8 highlights regression (PR #16)
✅ #160       CNN-corrected PSNR regression cells (PR #17)
✅ #161       Sustained-fps regression test (PR #17)
✅ #162       Dark-content q=7/8 regression (PR #20)
✅ #163       Pi 5 capture re-validation (storage budget cleared)
✅ #164       bench_fused write-all flag (PR #18)
✅ #165       q=11 CNN-aware preset (PR #21)
✅ #142       BarnAndSky render with final config
🔄 #166       q=12 candidate — data collected, awaits validation
```

## Memory updated this session

- `memory/project_strategic_framing.md` — pre-release contribution
  framing locked in (open-source non-commercial through 2028+, Apple
  Silicon-first, OEM-implementable spec is the goal)
- `memory/feedback_logarithmic_polling.md` — poll long-running
  processes via SSH+tail/ps/gh on 30s/1m/2m/4m/8m/16m/30m schedule;
  NEVER read the JSONL transcript
- `memory/feedback_honest_capture_bench.md` — updated with Pi 5
  multi-level + decimate=2 storage budget (the old "needs UHS-II V90"
  caveat is obsolete)

## Code state

Master is at `df2b773` (or wherever it is after the in-flight subagents
finish committing). `test_still_matrix.sh` 15/15 PASS, `test_capabilities`
13/13 EXCEEDED (12 still cells + the new q=11 cell, plus 3 CNN cells),
CI green on macOS + Ubuntu Debug + Release.

No outstanding lint, no broken builds, no failed tests.

## What I didn't do (and you might want me to)

- Did not change the production default CNN checkpoint. The retrained
  one lives in `dering_proto_v2/` not in the repo's weights dir.
- Did not change `make_gpraw_fixture.sh` to default to q=11. The
  multi-level + dec=2 default from PR #15 still uses bench_fused's
  hardcoded q=3.
- Did not push the q=12 preset with L1+L2 cranks. The data supports
  it but a dedicated retrained CNN should validate it first (in flight).
- Did not start writing a paper draft on the AccelIR-style raw-Bayer
  methodology. The methodology doc is the substrate; turning that into
  a publication is a separate, multi-day effort.

## Suggested next moves when you're back

1. Read SHIP_DECISION.md first. Pick A/B/C.
2. If A or B, I can do the actual ship in ~2-3 hours (or ~4-6 with
   the L1+L2 retraining if B).
3. Check the in-flight M5 retraining results.
4. Decide whether to start the env-var cleanup pass (per
   docs/ENV_VAR_CLEANUP.md). I'd defer this until the codec is
   feature-complete for your spec contribution.

That's it. Standing by.
