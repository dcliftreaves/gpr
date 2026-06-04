# Experiment Archive - 2026-06-04

The production integration branch intentionally excludes generated artifacts,
checkpoint sweeps, and one-off experiment dashboards from `master`.

The full exploratory branch is preserved at:

```text
archive/multilevel-cascade-experiments-20260604
```

That branch keeps the broad investigation history from PR #32, including:

- model checkpoint sweeps under `models/`;
- generated gate run receipts under `tests/quality_gates/runs/`;
- generated dashboard HTML/JSON outputs;
- exploratory CNN scripts for chroma, luma/detail, wavelet, guided-filter,
  Restormer, and hardtail candidate studies;
- session plans and intermediate writeups that were useful during research but
  are not production documentation.

The slim production branch keeps only the code, tests, and curated docs needed
to build, validate, and operate the current GPR/GVID paths. New large media,
dashboards, checkpoints, and scratch artifacts should remain on the external
work drive or a dedicated leaf branch unless they are required by CI or by a
small reproducible fixture.

Current external artifact root:

```text
/Volumes/OWC_8TB/gpr_work/artifacts
```

Current external scratch root:

```text
/Volumes/OWC_8TB/gpr_work/tmp
```
