# 2026-05-25 — exploration progress

End-of-day roll-up for the autonomous exploration session. **All technical
work was done in service of the project framing in
`memory/project_strategic_framing.md`**: pre-release contribution to
GoPro's open-source codec, Apple Silicon-first, open-source non-commercial
through 2028+.

## Shipped (master, this session)

| PR | Subject | Net effect |
|---|---|---|
| #10 | Half-res FUSED topology in playback decode | 3.6 → 26.89 fps × UHD with CNN |
| #11 | Multi-level FUSED honors decimate=2 | 11× smaller bitstreams |
| #13 | Per-subband quant calibration harness | Quantitative framework |
| #14 | q=5 capability cell (the actual quality peak) | Locked the empirical peak |
| #15 | `make_gpraw_fixture` defaults to multi-level | Production fixture path |
| #16 | Encoder L3 highpass quant floor | Fixed q=7/8 on highlights content |
| #17 | CNN-PSNR + sustained-fps regressions in CI | Locked the playback win |
| #18 | bench_fused GPR_BENCH_WRITE_ALL flag | Honest sustained-write benchmarks |
| #19 | Retrained-CNN findings doc | Methodology documented |
| #20 | Encoder per-band quant floor (slots 1-9) | Fixed q=7/8 on dark content |
| #21 | **q=11 CNN-aware preset + ENV_VAR_CLEANUP.md** | New shipping preset + future-cleanup map |
| #22 | q=11 capability cell | Locked q=11 in the regression matrix |
| #23 | docs/methodology_cnn_aware_quant.md | AccelIR-style methodology writeup |
| #24 | docs/session_2026-05-25_progress.md (this doc) | End-of-day roll-up |
| #25 | docs/SHIP_DECISION.md | Three-option decision artifact |
| #26 | **docs/SPEC.md** | **Formal bitstream format documentation (5707 words, 898 lines)** |

16 PRs merged. 0 reverts. CI green on every merged change.

## Major documentation artifacts produced

- `docs/quant_calibration_findings.md` — empirical rate-distortion data
- `docs/methodology_cnn_aware_quant.md` — AccelIR-style methodology writeup
- `docs/SPEC.md` — formal bitstream format specification (the GoPro
  contribution artifact). Headlines: FUSED_HEADER is 48 bytes (not 52);
  rANS class-15 ceiling is 2047 (not 1023 — that's the VLC limit);
  12-bit input uses 14-bit log curve internally; multi-level
  bitstream-slot-order vs quant-table-index-order divergence is
  documented in two tables.
- `docs/SHIP_DECISION.md` — three ship options with empirical data
- `docs/ENV_VAR_CLEANUP.md` — durable env-var inventory + future
  cleanup plan
- `docs/session_2026-05-25_progress.md` — this doc

## Key empirical findings

### Pipeline performance (M3 Max Release, 24-frame Z8 50 MP × UHD)

| Config | KB/frame | decode ms | total ms | sustained fps |
|---|---|---|---|---|
| pre-PR #10 (full-res, decimate=0) | 14 000 | 266 | 942 | 3.62 |
| single-level + LL + dec=2 (PR #10 default) | 4 522 | 9 | 138 | 26.89 |
| multi-level + dec=2 (new default per PR #15) | 386 | 26 | 141 | 26.24 |

**Net**: 12× smaller bitstream at essentially the same sustained fps.
The 4-deep pipeline hides multi-level's slightly slower decode.

### Pi 5 capture re-validation (PR-less, doc-only verification)

Multi-level + decimate=2 at 24 fps × 50 MP requires only **6.8 MB/s**
sustained write bandwidth. USB 3 SSD: 47× headroom. **microSD UHS-I:
9.7× headroom**. The "needs UHS-II V90 or USB SSD" deployment caveat
is obsolete. Any consumer-class storage handles this.

### CNN-aware quant calibration (the AccelIR-style result)

The existing `BIBO_1x_AAon_w16_ANE.pt` was trained on LL-only-fast
pairs and never saw highpass quant distortion. Retraining on cranked-
quant pairs unlocks the architecture:

| Subband | mult | bits saved (single-ll) | un-retrained CNN gain | retrained CNN gain |
|---|---|---|---|---|
| LH1 | 4× | 8.0% | +2.48 dB | **+4.40 dB** |
| HL1 | 4× | 7.0% | +2.43 dB | **+4.22 dB** |
| HH1 | 4× | 9.7% | +0.53 dB | **+5.61 dB** |

The retrained checkpoint lives at
`/Users/dcliftreaves/dering_proto_v2/checkpoints/BayInBayOut_1x_AAon_w16_ANE_HH1x4.pt`.

### Stacked-crank savings (today's NEW finding, not yet in a PR)

On the multi-level path with single-frame Z8Z_1330.dng:

| Crank config | Frame size | % saved |
|---|---|---|
| default (q=3) | 408 KB | — |
| L1 ×2 (= q=11 shipped) | 389 KB | 4.7% |
| L1 ×4 | 381 KB | 6.7% |
| **L1 ×4 + L2 ×2** | **318 KB** | **22.0%** |
| L1 ×4 + L2 ×4 | 301 KB | 26.2% |
| L1 ×4 + L2 ×4 + L3 ×2 | 294 KB | 28.0% |

**Headline**: L2 cranking is where the real bit savings live on
multi-level. q=11 (L1-only) gets 5%; q=12 with L2 added would get 22%.

The retrained BIBO_1x already partially absorbs L2 distortion
(+1.93-2.65 dB CNN gain on L2 slots per the multi-level sweep). For
shipping q=12 confidently, a retrained CNN trained on L1+L2 cranked
data would be even better; current retrained CNN is L1-only.

### q-preset regression on real content (#159 + #162)

Two encoder bugs that together cost ~7-10 dB on real photographic
content at q=7/q=8:

1. **L3 highpass coefficient clamping** (#159 PR #16) — VLC magnitude
   table is 1024 entries; small quants on highlights-heavy content
   produced post-quant magnitudes >1023 and got silently clamped to 1023.
   Floor slots 1/2/3 at 8.

2. **L2 + L3 floors** (#162 PR #20) — same class of bug in slots 1, 2,
   5 (LH3, HL3, HL2) on dark content. Per-band floor table
   `{0,14,14,8,1,11,1,1,1,1}` replaces the flat-8 loop.

q-preset PSNR is now monotone-improving on both highlights-heavy and
dark content. Filed task #166 for q=12 candidate using the L1+L2
stack-crank data above.

## Strategic context (memory)

- **`memory/project_strategic_framing.md`** captures the pre-release
  contribution-to-GoPro framing. All decisions during the session
  used this as the prioritization axis.
- **`memory/feedback_logarithmic_polling.md`** — learned the hard way
  that subagents have to be polled on a 30s/1m/2m/4m/8m/16m/30m
  schedule via SSH+tail/ps/gh, NOT by reading the JSONL transcript.
- **`docs/ENV_VAR_CLEANUP.md`** (in repo) — durable map of every
  `GPR_*`/`FUSED_*` env var with proposed disposition for the
  eventual spec contribution. Most env vars are still load-bearing for
  ongoing calibration; the doc makes the eventual cleanup mechanical.

## In flight when this was written

- M5 BIBO_2x retraining (cranked HH1 + super-res variant) — ep 8/80,
  +2.65 dB, ~75 min remaining
- SPEC.md authoring subagent — bitstream format documentation
- Perf profiling subagent — find the next bottleneck after CNN at 35 ms

Each is independent of the others and of master. Logarithmic-polled.

## Decision points pending user review

1. **Ship q=11 retrained CNN as the production default?**
   - Pro: clean ~5% bit savings, no quality regression, methodology
     validated and documented
   - Con: only 5% savings on multi-level. The L1+L2 stack gets 22% but
     needs a q=12 preset + retraining

2. **Add q=12 (L1+L2 cranked) preset?**
   - Pro: 22% file size reduction
   - Con: needs a new CNN retraining cycle (~90 min on M5) to validate
     CNN-corrected quality

3. **Encoder env-var cleanup pass** (per `docs/ENV_VAR_CLEANUP.md`) —
   not yet, but the prep work is done. Half-day refactor when ready.

4. **Spec contribution to GoPro** — gated on (1)-(3) landing and a
   formal SPEC.md (in flight).

## Tasks closed today
✅ #155-#157, **#158**, **#159**, #160, #161, #162, #163, #164, **#165**, **#142**

## Tasks remaining
- 🔄 #166 (q=12 candidate) — pending; data above is the substrate
- 🔄 BIBO_2x retraining subagent finishing
- 🔄 SPEC.md authoring subagent
- 🔄 Perf profiling subagent
