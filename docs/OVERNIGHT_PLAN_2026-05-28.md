# Overnight test queue — 2026-05-28 night

Reviewed `docs/RESEARCH_VSR_AND_ANE.md`, `docs/shadow_highlight_recovery_research.md`,
`project_cnn_deblock_superres.md`. Three concrete tests queued for overnight
execution; one already dispatched.

## Already in flight

- **w24 BIDO capacity test** (M5, PID via `pgrep`) — Task #4. ETA ~02:00.
  Architecture-capacity hypothesis test for the embedded PREVIEW gap.
- **Restormer-as-decoder + BIBO_1x w24 matched retrain** (subagent `a157baa4`).
  Tests the "heavy desktop decoder enables more aggressive cranking" thesis.

Both are running. Don't duplicate; gate them through the literature.

## Hypothesis ranking by EV

From the three research docs, the highest-EV un-tried experiments are:

### T1 — BIBO retrain WITH the 78-DNG OOD corpus (highest EV)

The 78 same-session DNGs at `/Volumes/OWC_8TB/gpr_work/cnn/ood_dngs_2025-04-20/`
are converted but **never used in any training**. Per `BIDO_DISTILLATION_PLAN.md`
§8: *"adding representative texture (hair, saturated regions) is the next
move — a data acquisition project, not a CNN architecture project."* We did
the data acquisition today; now use it.

Plan:
1. Build a new dataset for `ml2_q3_dec2` that adds the 78 OOD DNGs to the
   existing diverse_dngs + barnsky corpus.
2. Train BIDO_4x w16 (the production size) from scratch on the expanded
   corpus, msL1 + LPIPS γ=0.10 (Phase A recipe).
3. Gate-test against the 4-image gate. If PASSes PREVIEW, the corpus-axis
   hypothesis is confirmed and we have a viable embedded preview ship.

Predicted outcome from research (BIDO plan §8 with corpus rather than
arch): worst-image LPIPS 0.20-0.30 — moves the needle from 0.45 (current
FAIL) toward PREVIEW (0.15 ceiling) but probably doesn't quite clear.

### T2 — μ-law / log-domain L1 retrain

The SIGGRAPH Asia 2024 finding (Hanji et al., arxiv 2312.03640) is
literally a free 2-9 dB on RAW restoration: train L1 on PU21- or μ-law-
encoded pixels instead of linear. Our codec already applies a log curve
on encode but the CNN trains on **re-linearized** output. We're throwing
away the perceptual encoding before the loss.

Plan:
1. Patch `tools/cnn/train.py` to add `--loss-domain {linear,mu_law,pu21}`.
   The μ-law function τ(H) = log(1+μH)/log(1+μ) with μ≈5000 is cheap and
   differentiable; no LUT.
2. Retrain the matched BIBO_1x against `ml2_q3` (the standard codec)
   with `--loss-domain mu_law` and same hparams as the current matched
   CNN.
3. Gate-test. If worst LPIPS drops below the current 0.068, μ-law wins
   and becomes the default loss for all future retrains.

Predicted outcome: 0.5-1.5 dB Y-PSNR gain (less dramatic than the
literature's 2-9 dB because our problem is less shadow/highlight-skewed
than HDR restoration). Most likely improvement on Z8Z_6693 (the worst
image) since hair grain spans both tone tails.

### T3 — Dynamic focal L1 (|residual|^α weighting)

OHEM/focal-regression literature (Shrivastava 2016, focal frequency loss
2021): per-pixel weight `|y_pred - y_target|^α` with stop-grad. Equivalent
to OHEM but adaptive every step. Lower-EV than T2 because:
- T2 changes the **domain** of the loss; T3 changes the **emphasis** within
  the same domain.
- Most gains stack with T2 (could do `μ-law + focal`).

Skip unless T1 and T2 have completed.

### T4 — Per-tile weighted sampling on bright-hard edges (LOW priority)

`project_cnn_deblock_superres` memo confirms this delivered +3 dB on
Z8 ISO64 last time. Worth doing for any cranked retrain in the future
but the data-loader change is invasive — skip overnight, do as a future
session.

## Execution order

1. T1 (BIDO with OOD corpus, M5) — start when w24 training finishes
   (~02:00). 70-90 min training + 2 min gate.
2. T2 (μ-law L1 retrain, M3 Max) — can start anytime, M3 Max GPU
   currently free. 70-90 min training + 2 min gate.

T1 + T2 can run in parallel since they're on different hosts. Both
complete by morning.

## Constraints (CLAUDE.md)

- `gates.json` / `test_set.json` OFF-LIMITS
- No debug code in commits
- Per-image worst-case governs
- Open worst-image diff via Read tool for every PASS, write concrete-noun observation
- Don't run `--claim` (interactive, operator-only)
- Push to `origin/fix/multilevel-cascade-regression` after each test
- Co-author trailer required

## Stop conditions

- If any test PASSes its target gate → promote, commit, push, log run hash
- If a test FAILs → document with per-image LPIPS table, do NOT lower thresholds
- If MPS OOM or hard error → log it, move on to the next test
- If wall budget exceeded → finalize whatever produced a result, queue the rest for the morning
