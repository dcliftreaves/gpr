# CLAUDE.md — load-bearing instructions for Claude in this repo

These rules override default behavior. They exist because Claude has, in
this codebase, repeatedly:

1. Declared visual results "shippable" without looking at the image
2. Picked LPIPS/PSNR thresholds and then hidden behind them
3. Aggregated metrics across images to dilute a clear failure on one
4. Renamed pipelines so the codec+CNN pairing was lost
5. Re-derived prior conclusions instead of reading the prior conclusion
6. Marked tasks "complete" on partial wins

Each section below closes one of those holes.

## Ship-claim preflight (BLOCKING)

Before saying any pipeline "ships", "is complete", "is good", "passes",
"works", or similar language about visual quality:

1. Run `python3 tests/quality_gates/run_gate.py <pipeline-name>`.
   `<pipeline-name>` must be a full key from `pipelines/registry.json`.
   Ad-hoc shorthand like `ML2_q3_CNN` is not a pipeline name.
2. Read the worst-image visual-diff PNG via the **Read tool**. Not just
   look at metrics. Open the image. The path is in the gate output.
3. If the gate returned PASS, you may use ship language. If FAIL, you
   must not. INDETERMINATE = FAIL for this purpose.
4. To log the claim, run `run_gate.py <pipeline-name> --claim` and
   provide a 6+ word inspection sentence with a concrete noun. The
   runner appends it to `docs/claims_log.md`.

Anything you cite as evidence of ship-worthiness must be either (a) a
run-hash from `tests/quality_gates/runs/`, or (b) a `claims_log.md`
entry. Prose memory of "I tested this earlier and it looked good"
doesn't count.

## Hard-rules about gates.json and test_set.json

- **Never edit `tests/quality_gates/gates.json` in the same PR/commit
  as code that you're trying to make pass.** Threshold changes go in
  isolated PRs with written justification.
- **Never edit `tests/quality_gates/test_set.json` to remove an image
  because a pipeline fails on it.** Failing the gate IS the answer.
- The user owns those two files. Propose changes; don't make them
  silently.

## Pipeline names are full triples

Every pipeline reference uses the full registry name:

```
codec=<codec_id>+cnn=<cnn_id>+demosaic=<demosaic_id>
```

When writing tables, headers, captions, or commits, use this name in
full at least once per artifact. You may use a 16-char run-hash as a
shorter handle, but never invent your own short alias.

## Before declaring a task complete, check the prior state

- If a task says "fix X", grep the repo for prior attempts at X first.
  Read those before writing new code.
- If a task references a prior session's investigation (e.g. multi-level
  cascade fix, CNN distribution mismatch), open the prior session
  summary doc in `docs/` and read it before acting.
- "I forgot we already tested this" is the failure mode this rule
  exists to prevent.

## Aggregates are not allowed as a quality verdict

Per-image worst-case governs. Reports that say "mean LPIPS = 0.12 borderline"
are forbidden as ship-verdicts. The gate runner enforces this:
its output and `run.json` are sorted worst-first by LPIPS, and the
worst image is the headline.

If you find yourself reaching for an aggregate in chat to summarize
quality, lead with the worst image instead:

```
Z8Z_0001 (worst) LPIPS=0.231 — FAIL VIDEO_FREEZE gate (≤0.08)
Z8Z_0067         LPIPS=0.045 — PASS
```

## When sending images to the user

Use `SendUserFile` only after you have used the **Read tool** on the
image yourself in the same turn. The next message you send must include
a 6+ word description of what you observed, with a concrete noun.

This applies to dashboards too: if the dashboard embeds images you
haven't opened, open at least the worst-image crop before sending.

## When a CNN is involved

- Every CNN checkpoint must have a `trained_against_codec` field in
  the registry. If it doesn't, you don't know what it's paired with.
- A CNN's gain only counts when paired with the codec it was trained
  against. Cross-pairings (e.g. SL-trained CNN on ML-2 codec output)
  are *experiments*, not ship candidates.
- The `bibo1x_ane_l1l2x4` and `bibo1x_ane_hh1x4` checkpoints live in
  `models/` with codec pairings documented. Do not delete them in
  "cleanup" passes — they are the historical good results.

## Memory is for stable knowledge, not gate verdicts

- Pipeline test results live in `tests/quality_gates/runs/`, not memory.
- "Ships" claims live in `docs/claims_log.md`, not memory.
- Memory is for *patterns I keep doing wrong* (like this file) and
  *project context that doesn't change quickly* (strategic framing,
  who owns what, why a constraint exists). Not state.

## When in doubt

Read `docs/REGRESSION_2026-05-25.md`, `docs/SESSION_SUMMARY_2026-05-25_evening.md`,
and `pipelines/registry.json`. Then re-read this file.
