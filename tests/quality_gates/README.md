# tests/quality_gates — single source of truth for ship verdicts

## What this is

The only legitimate way to declare a pipeline "ships" or "passes quality"
is `python3 tests/quality_gates/run_gate.py PIPELINE_NAME`. The script
reads `gates.json` and `test_set.json` (both committed, both owned by
the user), runs the pipeline against 4 fixed Z8 50 MP source DNGs,
computes the visual metric stack (LPIPS / MS-SSIM / Y-PSNR / ΔE2000),
and emits a PASS/FAIL verdict per image. **Worst image governs.**
Aggregates are forbidden.

See `CLAUDE.md` at the repo root for the load-bearing rules.

## Files

```
tests/quality_gates/
  gates.json         ship-class thresholds (STILL / VIDEO_FREEZE / PREVIEW)
  test_set.json      4 frozen source DNGs + crop positions + eval dims
  run_gate.py        the runner — only source of truth
  golden/            REF crops (committed, frozen)
  runs/              per-run artifacts, hashed by inputs
```

## Pipeline registry

`pipelines/registry.json` is the only place codec+CNN+demosaicer triples
are named. The full name is the key — `codec=...+cnn=...+demosaic=...`.
Short aliases are forbidden (this is the failure mode the scaffolding
exists to fix).

## Adding a new pipeline

1. Add an entry to `pipelines/registry.json`. All required fields filled.
2. CNN checkpoint goes in `models/` with sha256 in the registry.
3. Document `trained_against_codec` honestly.
4. Run `run_gate.py PIPELINE_NAME` and inspect the worst-image visual
   diff via the Read tool.
5. If PASS, log via `run_gate.py PIPELINE_NAME --claim`.

## Adjusting gates

`gates.json` edits go in isolated PRs with written justification. Don't
loosen a gate to make a failing pipeline pass — that defeats the gate.

## Verified results so far

(Run `run_gate.py` and append to `docs/claims_log.md` to update.)

| pipeline | ship_class | worst LPIPS | verdict |
|---|---|---:|---|
| codec=sl_q3+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools | STILL | 0.009 | PASS |
| codec=ml2_q3+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools | VIDEO_FREEZE | 0.212 | FAIL |
| codec=ml3_q12_l1l2x4_legacy+cnn=bibo1x_ane_l1l2x4+demosaic=sips_via_gpr_tools | VIDEO_FREEZE | 0.290 | FAIL |
