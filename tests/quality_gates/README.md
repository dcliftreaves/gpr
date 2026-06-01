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
  preview_holdout_set.json
                     28-image informational PREVIEW breadth set
  run_gate.py        the runner — only source of truth
  summarize_preview_holdout.py
                     worst/p95/median/per-stratum summary for holdout receipts
  check_registry_consistency.py
                     registry/schema/artifact metadata check
  audit_ship_pipelines.py
                     verifies ship-* roles have committed PASS receipts
  audit_production_readiness.py
                     output-family readiness checklist
  dashboard.py       quality-gate run index
  build_ops_dashboard.py
                     size/timing/FPS/storage/chroma operations dashboard
  diagnose_chroma_signal.py
                     Lab/YCbCr chroma drift diagnostic for gate runs
  golden/            REF crops (committed, frozen)
  runs/              per-run artifacts, hashed by inputs
```

## Pipeline registry

`pipelines/registry.json` is the only place codec+CNN+demosaicer triples
are named. The full name is the key — `codec=...+cnn=...+demosaic=...`.
Short aliases are forbidden (this is the failure mode the scaffolding
exists to fix).

Before claiming a production pipeline, run:

```
python3 tests/quality_gates/check_registry_consistency.py --strict-artifacts
python3 tests/quality_gates/audit_ship_pipelines.py
```

CI runs the same checker without `--strict-artifacts` so structural registry
breakage fails fast while known historical artifact gaps stay visible as
warnings. Strict mode is the release cleanup list: missing checkpoints,
unresolved checkpoint hashes, and unresolved training provenance must be
fixed or deliberately removed from the registry before a ship claim.

`audit_ship_pipelines.py` ignores untracked local runs by default. It only
counts committed `run.json` receipts, so a fresh checkout can verify every
`ship-*` role. Release preparation should also run:

```
python3 tests/quality_gates/audit_ship_pipelines.py --strict
```

Strict ship audit additionally requires the current `gates.json` hash and a
matching `docs/claims_log.md` receipt.

For a broader stills/video/container/UPRESABLE/Pi-target checklist, run:

```
python3 tests/quality_gates/audit_production_readiness.py
```

It exits 0 by default so it can be used during burn-down. Use `--strict` when
the readiness matrix is expected to be completely green.

## Dashboards and diagnostics

The dashboards are generated artifacts under `tests/quality_gates/runs/dashboard/`.
Regenerate them from committed run logs instead of hand-editing HTML.

```
python3 tests/quality_gates/dashboard.py
python3 tests/quality_gates/build_ops_dashboard.py
python3 tests/quality_gates/diagnose_chroma_signal.py RUN_HASH [RUN_HASH...]
```

`dashboard.py` is the gate-result index. `build_ops_dashboard.py` is the
operations matrix: encoded size, bpp, compression ratio, encode/decode timing,
FPS, Pi-to-Mac transfer throughput, UPRESABLE artifact accounting, and chroma
diagnostics. `diagnose_chroma_signal.py` is for root-causing color failures; it
reports Lab lightness/chroma error, a/b bias and correlation, hue error, and
chroma high-frequency retention for one or more quality-gate runs.

## PREVIEW holdout eval

`preview_holdout_set.json` is a broader 28-image informational set for ranking
PREVIEW candidates after the frozen four-image gate has exposed a blocker. It
does not replace `test_set.json`, and `run_gate.py --claim` is refused for any
alternate manifest.

Run a candidate on the holdout:

```
python3 tests/quality_gates/run_gate.py PIPELINE_NAME \
  --test-set tests/quality_gates/preview_holdout_set.json
```

Summarize one or more holdout receipts:

```
python3 tests/quality_gates/summarize_preview_holdout.py RUN_HASH [RUN_HASH...]
```

The summary reports worst image, LPIPS/dE p95 tails, MS-SSIM/Y-PSNR p05 tails,
medians, and per-stratum failures. Use it to compare candidate breadth, not to
average away a frozen-gate failure.

## Adding a new pipeline

1. Add an entry to `pipelines/registry.json`. All required fields filled.
2. CNN checkpoint goes in `models/` with sha256 in the registry.
3. Document `trained_against_codec` honestly.
4. Run `check_registry_consistency.py --strict-artifacts`.
5. Run `run_gate.py PIPELINE_NAME` and inspect the worst-image visual
   diff via the Read tool.
6. If PASS, log via `run_gate.py PIPELINE_NAME --claim`.

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
