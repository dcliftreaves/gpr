# CNN-aware fine-grained compression — revival plan (ML-2 primary, SL secondary)

**Author:** planning pass, 2026-05-27 (extended same day with ML-2 primary track)
**Status:** plan only — no code changes proposed in this doc

> **2026-05-28 update — SL track is obsolete.** The "Secondary: SL" track
> below targeted STILL via FUSED single-level (`sl_q3`). On 2026-05-28
> stills moved to the legacy CineForm VC5 encoder (`gpr_tools`) per
> `SHIP_DECISION.md`; the FUSED single-level codecs are now
> `use_for: deprecated` in the registry. The ML-2 (PRIMARY) track is
> still active for VIDEO_FREEZE. Disregard the SL parts of this plan.

**Companion docs (read first):**

- [docs/REGRESSION_2026-05-25.md](REGRESSION_2026-05-25.md) — what changed about multi-level (cascade fix, 2-level restored)
- [docs/methodology_cnn_aware_quant.md](methodology_cnn_aware_quant.md) — the AccelIR-style methodology (figures stale, walk-back at top of doc; now's the time to re-run cleanly)
- [docs/quant_calibration_findings.md](quant_calibration_findings.md) — per-subband sweep data (multi-level; stale)
- [pipelines/registry.json](../pipelines/registry.json) — existing experimental codec entries showing `GPR_QUANT_OVERRIDE` syntax

## 0. Two-track summary

The project has two CNN-aware compression tracks. Both follow the same
methodology (per-subband quant sweep → stacking → CNN retrain) and the
same architecture (`F_ane_no_sr`, BIBO_1x, w=16, AAon). They differ in
**which codec they sit on top of** and **what ship class they target**.

| Track | Codec | Ship class | LPIPS ceiling | Current champion | Champion mean bytes | Sweep slots |
|---|---|---|---|---|---|---|
| **PRIMARY: ML-2** | `ml2_q3` (2-level wavelet) | VIDEO_FREEZE | 0.08 | `codec=ml2_q3+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools` (run `5e0b4c751d7a26eb`) | **10.26 MB** | 4,5,6 (LH2/HL2/HH2) + 7,8,9 (LH1/HL1/HH1) — **six knobs** |
| Secondary: SL | `sl_q3` (single-level) | STILL | 0.05 | `codec=sl_q11+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` (run `0b6114e53fd0e04d`) | 22.4 MB | 1,2,3 (LH/HL/HH) — three knobs |

### Why ML-2 is primary

1. **More knobs.** Six highpass slots vs three. The per-subband sweep
   has 2× the search space and 2× the chances of finding a low-LPIPS-cost,
   high-bits-saved knob.
2. **More LPIPS headroom.** VIDEO_FREEZE allows LPIPS ≤ 0.08. The
   matched-CNN champion is at worst-image LPIPS 0.068 (Z8Z_6693). Tight
   (0.012 headroom for any new cranking degradation) but workable. STILL
   gates at 0.05 and the current SL champion (`sl_q11+CNN`) is at LPIPS
   0.024 — STILL has 0.026 headroom in absolute terms but the metric is
   harder to predict in that regime.
3. **Video bytes >> stills bytes.** A 20% file-size win on the 10.26 MB
   ML-2 champion saves ~2 MB per frame. At 24 fps that is ~3 GB/min
   saved. A 20% win on `sl_q11+CNN` saves ~4 MB per still. Cumulative
   gain per shot from video is two orders of magnitude bigger.
4. **Infrastructure is more developed on ML-2.** Eleven `ml2_q3_*`
   experimental codec entries already exist in `pipelines/registry.json`
   (some gate-tested), the matched CNN `bibo1x_ane_ml2_q3` is trained
   and shipped, the methodology paper's slot map (4..9) is for ML-2,
   and historical retrained CNNs (`bibo1x_ane_hh1x4`, `bibo1x_ane_l1l2x4`)
   live in `models/`.
5. **Methodology paper's per-subband table was ML-2 (multi-level)**, but
   measured under the pre-cascade-fix 10 dB regression. The fix landed
   (`project_2level_wavelet_restored.md`); re-measurement on the clean
   ML-2 path is the obvious next step.

### Why SL is secondary, not abandoned

The methodology proven on ML-2 ports directly to SL — slots 1/2/3 are
the same axis (LH/HL/HH highpass), just at L1 only. SL's LPIPS budget
is tighter (champion at 0.024 vs ceiling 0.05 = 0.026 headroom), but it
serves a fundamentally different ship class (STILL = printable, no
motion-masking allowance) that we should still try to improve.

## 1. Baselines we are trying to beat

### 1.1 ML-2 champion (primary target)

From `tests/quality_gates/runs/5e0b4c751d7a26eb/run.json`:

| Image | LPIPS | Y-PSNR | MS-SSIM | dE2000 | enc bytes |
|---|---:|---:|---:|---:|---:|
| Z8Z_6693 (worst) | **0.0683** | 36.71 | 0.9746 | 1.284 | 17.38 MB |
| Z8Z_5323 | 0.0426 | 39.26 | 0.9839 | 1.006 | 13.57 MB |
| Z8Z_0067 | 0.0414 | 50.40 | 0.9974 | 0.546 | 4.09 MB |
| Z8Z_0001 | 0.0230 | 43.07 | 0.9963 | 0.992 | 6.00 MB |
| **Mean** | — | — | — | — | **10.26 MB** |

PASS at VIDEO_FREEZE. Worst-image LPIPS is 0.068 against a 0.08 ceiling
— **0.012 LPIPS of headroom to spend on additional cranking**.

The lower-bound mean to beat is 10.26 MB. To call something a meaningful
ship win, target ≥ 10% smaller (≤ 9.2 MB mean) AND VIDEO_FREEZE PASS.

### 1.2 SL champion (secondary target)

From `tests/quality_gates/runs/`:

| Pipeline | Run hash | Worst image | Worst LPIPS | Mean bytes | Verdict |
|---|---|---|---:|---:|---|
| `codec=sl_q3+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` | `7c4a529562b0f588` | Z8Z_0067 | 0.0086 | 26.6 MB | PASS |
| `codec=sl_q11+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` | `0b6114e53fd0e04d` | Z8Z_0067 | 0.0237 | 22.4 MB | PASS |

`sl_q11+CNN` is the SL bar. 15.8% smaller than `sl_q3+CNN`.

## 2. ML-2 slot map (primary track)

For `FUSED_MULTI_LEVEL=1` + `FUSED_WAVELET_LEVELS=2` + `GPR_INCLUDE_LL=1`,
the encoder reads slots 0..9 of `quality_tables[quality]`. Slot mapping
per `source/lib/vc5_encoder/fused_encode.c` lines 3242-3420 and 3987-3995:

| Slot | Subband | `q=3` default | `q=11` value | Notes |
|---|---|---:|---:|---|
| 0 | LL (× LL2_EXTRA_DIVISOR=16 in ML-2) | 1 | 1 | `qt[0] * ll2_extra` = 16 effective |
| 1 | (unused in ML-2 — used by ML-3 for L3) | 24 | 48 | — |
| 2 | (unused in ML-2 — used by ML-3 for L3) | 24 | 48 | — |
| 3 | (unused in ML-2 — used by ML-3 for L3) | 12 | 48 | — |
| **4** | **LH2** (vertical edges, L2) | **24** | **48** (2×) | sweep candidate |
| **5** | **HL2** (horizontal edges, L2) | **24** | **48** (2×) | sweep candidate |
| **6** | **HH2** (diagonal, L2) | **12** | **24** (2×) | sweep candidate |
| **7** | **LH1** (vertical edges, L1) | **96** | **192** (2×) | sweep candidate |
| **8** | **HL1** (horizontal edges, L1) | **96** | **192** (2×) | sweep candidate |
| **9** | **HH1** (diagonal, L1) | **144** | **576** (4×) | sweep candidate |

The `GPR_QUANT_OVERRIDE` env (parsed by `apply_quant_override` at
`fused_encode.c:260`) takes `"slot:value,slot:value"` pairs; we'll use
slots **4, 5, 6, 7, 8, 9** for the ML-2 sweep.

Note: q=11 is already a 2× crank across slots 4/5/6/7/8 and a 4× crank
on slot 9. The sweep below explores **beyond** q=11 on those slots, and
also tests softer cranking (some slots back off from q=11) to find the
LPIPS sweet spot.

## 3. The (stale) per-subband data we are re-measuring

`docs/methodology_cnn_aware_quant.md` §4.3 reported a per-subband sweep
on the multi-level codec, with the now-known 10 dB regression sitting
under the bayer-PSNR. The L1L2x4 and HH1x4 retrained CNNs were trained
against multi-level outputs that included the regression.

**Critical**: the historical CNNs `bibo1x_ane_hh1x4` and
`bibo1x_ane_l1l2x4` are calibrated to a broken upstream distribution.
Per `tests/quality_gates/runs/`:

- `codec=ml2_q3+cnn=bibo1x_ane_hh1x4` worst LPIPS = 0.1996 (FAIL)
- `codec=ml2_q3+cnn=bibo1x_ane_l1l2x4` worst LPIPS = 0.3137 (FAIL)

Both substantially worse than the matched `bibo1x_ane_ml2_q3` at 0.068.
They don't transfer cleanly to clean ML-2. We keep them in `models/`
per CLAUDE.md ("historical good results — do not delete in cleanup")
but we do not plan to use them as the ship CNN.

## 4. Primary track: ML-2 fine-grained sweep plan

### 4.1 Sweep grid

For each L1 and L2 highpass slot, sweep multipliers **{2×, 4×, 8×, 16×}**
on top of the `ml2_q3` default. (Reference cell = `ml2_q3` defaults, no
override.) The slot/multiplier ↔ `GPR_QUANT_OVERRIDE` string mapping:

| Friendly name | Slot | q=3 default | 2× | 4× | 8× | 16× |
|---|---:|---:|---|---|---|---|
| LH2 | 4 | 24 | `"4:48"` | `"4:96"` | `"4:192"` | `"4:384"` |
| HL2 | 5 | 24 | `"5:48"` | `"5:96"` | `"5:192"` | `"5:384"` |
| HH2 | 6 | 12 | `"6:24"` | `"6:48"` | `"6:96"` | `"6:192"` |
| LH1 | 7 | 96 | `"7:192"` | `"7:384"` | `"7:768"` | `"7:1536"` |
| HL1 | 8 | 96 | `"8:192"` | `"8:384"` | `"8:768"` | `"8:1536"` |
| HH1 | 9 | 144 | `"9:288"` | `"9:576"` | `"9:1152"` | `"9:2304"` |

24 sweep cells × 4 gate images = 96 encode/decode/render runs per pass.
(Slot 9 16× = 2304 may exceed rANS class-15 range; that is itself
diagnostic — let the gate runner tell us.)

### 4.2 Existing ML-2 codec entries that overlap the sweep grid

Several `ml2_q3_*` codec entries in `pipelines/registry.json` already
encode points in this sweep (with `cnn=none` — they are codec-only
diagnostic runs, not CNN-corrected). Existing gate-tested points:

| Existing codec id | `GPR_QUANT_OVERRIDE` | Where it sits on the sweep | Existing run verdict |
|---|---|---|---|
| `ml2_q3_l1soft` | `7:48,8:48,9:72` | softer-than-default L1 (0.5× HH1) | FAIL no CNN, LPIPS 0.23 |
| `ml2_q3_l2soft` | `4:12,5:12,6:6` | softer-than-default L2 (0.5×) | FAIL no CNN, LPIPS 0.23 |
| `ml2_q3_bothsoft` | `4:12,5:12,6:6,7:48,8:48,9:72` | L1+L2 softer | FAIL no CNN, LPIPS 0.23 |
| `ml2_q3_nohighpassquant` | `4:1,5:1,6:1,7:1,8:1,9:1` | upper bound (no quant) | FAIL no CNN, LPIPS 0.22 (this is the codec-only ceiling, ~42 MB) |
| `ml2_q3_combo` | `4:12,5:12,6:6,7:48,8:48,9:72` + `FUSED_LL2_DIVISOR=8` | L1+L2 softer + LL2 fidelity | FAIL no CNN, LPIPS 0.92 (LL2 too aggressive somewhere) |
| `ml2_q11` (q=11 preset) | bake-in `4:48,5:48,6:24,7:192,8:192,9:576` | 2/2/2/2/2/4× | FAIL `cnn=bibo1x_ane_sl_q3` (mismatched CNN; not retested with matched CNN) |
| `ml2_q3_prefilter3h_softq` | `4:12,5:12,6:6,7:48,8:48,9:72` + `FUSED_L2_PREFILTER=3` | L1+L2 softer + horiz prefilter | FAIL no CNN, LPIPS 0.24 |

**Reading these**: every existing entry was gated with `cnn=none` and
fails by ~0.2 LPIPS — meaning the codec-only path is far above the
0.08 VIDEO_FREEZE ceiling, but ALL of these had the CNN absorb that
gap when paired with `bibo1x_ane_ml2_q3` (the matched CNN brings ML-2
defaults from raw codec LPIPS to 0.068).

**Action**: the sweep above must be run **with the matched CNN
`bibo1x_ane_ml2_q3` enabled**, not `cnn=none`. The existing codec-only
runs are background — informative about codec-only behaviour but not
ship-relevant. Don't repeat them with `cnn=none`; the CNN-corrected
question is the unanswered one.

### 4.3 Cranking direction: harder, not softer

The existing `*soft*` codec entries explored softening L1 and L2 (testing
whether the matched CNN cleared the gate at *finer* quant). The new sweep
direction is the opposite: **crank harder** at each subband than q=11
already does. The hypothesis we're testing:

> The matched CNN `bibo1x_ane_ml2_q3` has 0.012 LPIPS of headroom at
> the VIDEO_FREEZE gate. Per-subband cranking of slots {4..9} above
> `ml2_q3` defaults can save bits cheap; the CNN, having been trained
> against `ml2_q3` defaults, will partially absorb the additional
> degradation. Find the per-slot multiplier where bit-savings × CNN-absorption
> is favourable, then stack.

### 4.4 Metrics collected per cell

For each (slot, multiplier, image), via `run_gate.py`:

1. **Encoded bytes** (mean and per-image) vs `ml2_q3` reference.
2. **Y-PSNR**, **MS-SSIM**, **LPIPS**, **ΔE2000** vs the gate's REF
   rendering — both with `cnn=bibo1x_ane_ml2_q3` and without (`cnn=none`).
   The CNN-on number is what gates; the CNN-off number documents what
   the bare decode looks like.
3. **Worst image first** (CLAUDE.md "Aggregates are not allowed").

The runner already does (1) and (2)+(3). Item 2's `cnn=none` half is
diagnostic — only run it for the top three candidate slots (not every
cell) to keep the sweep tractable.

### 4.5 Headroom call-outs — likely-bust cells

The champion's Z8Z_6693 sits at LPIPS 0.0683. Cells likely to bust the
0.08 ceiling on a 50 MP high-detail image like Z8Z_6693, based on the
methodology paper's prior per-subband sweep (with appropriate skepticism
because it was on the broken codec):

- **HH1 16× (`9:2304`)** — almost certainly busts. Slot 9 already
  cranked 4× in q=11; an additional 4× on top is aggressive territory.
  Include in the sweep as the ceiling-test (we want to see *where* it
  breaks).
- **LH1 8× / 16×** and **HL1 8× / 16×** — the methodology paper had
  CNN gain falling to +2.4 dB at 4× on a noisier codec; double that
  crank likely busts. Predict FAIL at 16× for both.
- **HH2 16×** — only diagonal L2; the diagonal subband has historically
  been the cheapest to crank but ML-2 L2 already operates near Nyquist
  per `project_multilevel_regression.md`. Expect aliasing if the
  diagonal energy is real.
- **LH2 / HL2 cranked aggressively** — these are the Nyquist-sensitive
  L2 subbands. Pair these sweep points with the `prefilter3hv` codec
  variant (see §4.7) to test whether anti-aliasing buys headroom.

The full sweep is still worth running — gating where each knob breaks
is the answer.

### 4.6 Stacked patterns

After the single-knob sweep, identify per-slot multipliers at which the
matched CNN keeps worst-image LPIPS ≤ 0.06 (allowing some headroom for
stacking compounding) and per-knob bit savings ≥ 4%. Stack those into a
single `GPR_QUANT_OVERRIDE`.

Re-derived "L1L2x4 pattern in clean ML-2 slot terms": the original
ML-3-era `ml3_q12_l1l2x4_legacy` codec uses
`4:48,5:48,6:24,7:384,8:384,9:576`. That's L2 highpass at 2× over q=3
defaults and L1 highpass at 4× over q=3 (HH1 at 4× same as q=11). In
ML-2 slot terms this is identical (slots 4..9 mean the same thing in
ML-2 and ML-3). A clean-ML-2 version of this pattern:

- `ml2_q3_l1l2x4`: `4:48,5:48,6:24,7:384,8:384,9:576` (L2 highpass 2×,
  L1 highpass 4×, HH1 4×). Beyond q=11 only on slots 7, 8.

Candidate stacked codec entries to register (Phase A — with matched CNN):

| Candidate codec id | `GPR_QUANT_OVERRIDE` | Rationale |
|---|---|---|
| `ml2_q3_l1x4` | `7:384,8:384,9:576` | L1-only crank, no L2 change. Compare vs q=11 (which also touches L2 at 2×). |
| `ml2_q3_l2x4` | `4:96,5:96,6:48` | L2-only crank, no L1 change. Tests if L2 has independent savings the matched CNN can absorb. |
| `ml2_q3_l1l2x4` | `4:48,5:48,6:24,7:384,8:384,9:576` | Clean re-derivation of the historical L1L2x4 pattern. |
| `ml2_q3_l1l2x4_hh16` | `4:48,5:48,6:24,7:384,8:384,9:2304` | Aggressive — HH1 16× over q=3, stacked. |
| `ml2_q3_winners` | (TBD from §4.4 sweep top picks) | Built from the per-knob winners. |

### 4.7 Prefilter risk mitigation

`project_multilevel_regression.md` flagged Nyquist aliasing as
intrinsic to multi-level wavelets. ML-2 attenuates this vs ML-3 but
does not eliminate it. The `ml2_q3_prefilter3h*` codec entries
(`FUSED_L2_PREFILTER=3` or `33`) apply a 3-tap LP prefilter to LL1
before the L2 cascade.

**Predict**: when cranking L2 highpass aggressively (slots 4, 5, 6),
the prefilter buys back enough quality margin to allow a more
aggressive L2 crank than would otherwise pass.

Include in the sweep:

| Candidate codec id | `GPR_QUANT_OVERRIDE` + prefilter | Rationale |
|---|---|---|
| `ml2_q3_l2x4_prefilter` | `4:96,5:96,6:48` + `FUSED_L2_PREFILTER=3` | L2 4× crank with horizontal prefilter |
| `ml2_q3_l2x8_prefilter_hv` | `4:192,5:192,6:96` + `FUSED_L2_PREFILTER=33` | L2 8× crank with H+V prefilter — only with prefilter |
| `ml2_q3_winners_prefilter` | (sweep winners) + `FUSED_L2_PREFILTER=3` | The recommended stacked ship candidate, if §4.6 winners exceed L2 cranking thresholds |

### 4.8 Gate-pass condition for the primary track

A candidate **wins** if BOTH:

1. `run_gate.py codec=<candidate>+cnn=<chosen_cnn>+demosaic=sips_via_gpr_tools`
   returns PASS for ship_class VIDEO_FREEZE.
2. Mean encoded bytes < champion's 10.26 MB AND ideally ≤ 9.2 MB (≥10%
   gain — call out smaller wins but don't promote them to ship).

Per CLAUDE.md the per-image worst-case governs (1); the mean is only
for the file-size comparison (2).

### 4.9 CNN retrain — historical first, then fresh

The historical retrained CNNs `bibo1x_ane_hh1x4` and `bibo1x_ane_l1l2x4`
were trained against multi-level outputs that included the pre-fix
10 dB cascade regression. Two paths:

**Path (a): Cheap sanity check first.** Run the two historical CNNs
against the cleanest matched cranked codec — e.g.
`codec=ml2_q3_l1l2x4+cnn=bibo1x_ane_l1l2x4+demosaic=sips_via_gpr_tools`.
The hypothesis-falsifying outcome is the CNN actually transfers anyway
because the codec-output statistics are similar enough. Existing data
suggests this is unlikely (the historical CNNs fail on plain `ml2_q3`
at LPIPS 0.2-0.3) but it's a one-gate-run experiment and worth knowing.

**Path (b): Retrain `bibo1x_ane_ml2_q3` against each Phase A cranked
candidate**. The training distribution shifts; the architecture stays
`F_ane_no_sr`. Use the matched ML-2 retrain recipe (already in
`pipelines/registry.json`):

- **Architecture**: `F_ane_no_sr` (BIBO_1x, w=16, AAon, residual_scale=0.01).
- **Training data**: pairs of (cranked-codec output, source bayer) from
  the same 200 barn_sky + 298 diverse NEFs used to train
  `bibo2x_ane_ml2_q3_dec2_diverse`. Filter out 4 gate images. Build via
  a new `tools/cnn/build_tiles_<cranked_codec_id>.py` patterned on
  `tools/cnn/build_tiles_ml2_q3.py`.
- **Loss**: L1 + MS-SSIM (weight 0.3), matching `bibo1x_ane_ml2_q3_msssim`.
  MS-SSIM matters because it's the second-strictest VIDEO_FREEZE metric.
- **Optimizer**: AdamW lr=5e-4, cold start.
- **Schedule**: 80 epochs M5 MPS, ~2 h per retrain.
- **Validation**: 4 held-out diverse images (NOT the 4 gate images).
- **Budget**: AT MOST 3 retrains for the primary track. Spend on the
  most promising stacked candidate, the most ambitious one, and one
  fallback (see §4.10).

### 4.10 Retrain decision tree

After the Phase A (matched-CNN, no retrain) sweep:

1. **Candidate PASSes VIDEO_FREEZE AND mean bytes < 9.2 MB**: stop.
   Run the ship-claim preflight and propose as new champion. No
   retrain needed.
2. **Candidate worst LPIPS in (0.08, 0.12) range**: retrain candidate.
   Plausible the matched CNN's training distribution is the gap.
3. **Candidate worst LPIPS > 0.12**: probably too aggressive. Back
   off the crank rather than retrain.

Retrain budget order:

a. Best stacked candidate just over the line (LPIPS 0.08–0.10) — most
   likely to be unlocked by a matching CNN.
b. Most-ambitious candidate (e.g. `ml2_q3_l1l2x4_hh16` if it lands in
   the 0.10–0.12 band).
c. Held in reserve.

## 5. Secondary track: SL fine-grained sweep plan

The SL track is the prior single-level revival plan (preserved below for
completeness). Execute only after the ML-2 track produces a result —
its methodology informs which knobs are worth sweeping on SL, and the
M5 retrain budget is shared.

### 5.1 SL slot map

For `GPR_INCLUDE_LL=1` (no `FUSED_MULTI_LEVEL`), the encoder reads
slots 0..3 of `quality_tables[quality]`:

| Slot | Subband (SL) | `q=3` default | `q=11` value |
|---|---|---:|---:|
| 0 | LL (×16 internal via `q_ll1_base *= 16`) | 1 | 1 |
| 1 | LH | 24 | 48 (2×) |
| 2 | HL | 24 | 48 (2×) |
| 3 | HH | 12 | 48 (4×) |

Slots 4..9 are ignored in single-level mode.

### 5.2 SL sweep grid

Same multiplier scheme {2×, 4×, 8×, 16×} on slots 1, 2, 3. 12 cells × 4
images. Tighter LPIPS budget (0.05 STILL ceiling, champion at 0.024 =
0.026 headroom) means more cells likely bust.

### 5.3 SL stacked candidates

Re-derive in single-level slot terms:

- `sl_q3_lhhl_x2_hh_x4`: `1:48,2:48,3:48` — equivalent to current
  `sl_q11` written explicitly.
- `sl_q3_lhhl_x2_hh_x8`: `1:48,2:48,3:96` — crank HH harder vs `sl_q11`.
- `sl_q3_lhhl_x4_hh_x8`: `1:96,2:96,3:96` — analogue of historical L1L2×4.
- `sl_q3_lhhl_x4_hh_x16`: `1:96,2:96,3:192` — aggressive.
- `sl_q3_hh1x8`: `3:96` — most promising single-knob (HH is cheapest
  to crank in low-detail regions; HH champion already at 4×).

### 5.4 SL gate-pass condition

STILL gate (lpips ≤ 0.05, ms_ssim ≥ 0.99, y_psnr ≥ 35, dE2000 ≤ 1.5)
AND mean bytes < `sl_q11+CNN`'s 22.4 MB. Target ≥ 5% smaller (≤ 21.3 MB).

### 5.5 SL CNN retrain

Same architecture (`F_ane_no_sr`, BIBO_1x). New CNN id e.g.
`bibo1x_ane_sl_q3_hh1x8`. Training data = diverse corpus minus 4 gate
images, paired against the new cranked codec output. Budget: 0–2
retrains for SL (after ML-2 has consumed up to 3).

## 6. Shared CNN architecture decisions

Both tracks use:

- **Architecture**: `F_ane_no_sr` (BIBO_1x, width=16, AAon, residual
  output). No super-res — input and output are 4-channel half-res bayer
  at the codec's native resolution. (Super-res CNNs `bibo2x_*` are
  out-of-scope for both tracks: the ML-2 dec2 super-res path is its
  own pipeline.)
- **Loss**: L1 + MS-SSIM (weight 0.3). The MS-SSIM term protected
  Z8Z_6693 from going below 0.97 in the matched-CNN training.
- **Optimizer**: AdamW lr=5e-4, cold start (no warm-start from prior
  cranked-codec CNNs — the multi-level retrains showed cold-start
  generalises better when the input distribution shifted).
- **Schedule**: 80 epochs M5 MPS, ~2 h per retrain.
- **Tile gen**: gate-aligned, source bayer + cranked-codec output via
  the actual encoder/decoder binary. Pattern from
  `tools/cnn/build_tiles_ml2_q3.py` and
  `tools/cnn/build_tiles_dmsr_gate_aligned.py`.
- **Validation**: 4 held-out diverse images, never the gate images.
- **Naming**: per `feedback_cnn_naming.md`,
  `BayInBayOut_1x_AAon_w16_<distribution>.pt`. E.g.
  `BayInBayOut_1x_AAon_w16_ANE_ML2_q3_l1l2x4.pt`.

The only thing that differs between an ML-2 CNN retrain and an SL CNN
retrain is the training-data pairing — the codec used to generate the
cranked output. The training script (`tools/cnn/train.py`) and tile
builder are reused; only the codec invocation differs.

## 7. Cross-track sequencing

Recommended order:

1. **ML-2 single-knob sweep** (§4.1) — 24 cells, 4 images each. Phase A
   (matched CNN, no retrain).
2. **ML-2 worst-image visual-diff review** of top three candidates per
   §4.5. Skip-or-proceed gate.
3. **ML-2 stacked candidates** (§4.6) — 4–6 stacked sweeps.
4. **ML-2 prefilter pairing** (§4.7) — re-run the most aggressive L2
   stacked candidate with `FUSED_L2_PREFILTER`.
5. **ML-2 CNN retrain** (≤3) per §4.10.
6. **ML-2 ship-claim preflight** if a winner exists.
7. **SL single-knob sweep** (§5.2) — 12 cells, only if ML-2 is in good
   shape and retrain budget is left.
8. **SL stacked + retrain** (§5.3, §5.5).
9. **SL ship-claim preflight**.

Each completed sweep round produces a candidate. Gate-test before
stacking; one CNN retrain per significant operating point.

## 8. Risks specific to ML-2

### 8.1 Multi-level Nyquist aliasing

Per `project_multilevel_regression.md` memory, the original multi-level
regression had two root causes: (1) Nyquist aliasing through the
cascade, (2) double-rounding in `horizontal_filter`. Cause (2) was the
specific cascade bug that the cascade-fix addressed; cause (1) — Nyquist
— is intrinsic to multi-level wavelets and reduced (not eliminated) by
moving from ML-3 to ML-2 (per `project_2level_wavelet_restored.md`).

**Implication**: cranking slots 4, 5 (LH2, HL2) — the L2 axis-aligned
subbands — risks reintroducing aliasing the cascade-fix didn't address,
because aggressive quantisation of L2 highpass effectively *adds*
high-frequency noise back to LL1 in the inverse pass.

**Mitigation**: include `FUSED_L2_PREFILTER=3` and `FUSED_L2_PREFILTER=33`
in the sweep paired with the most aggressive L2 cranks. The prefilter
attenuates content near L2 Nyquist before the L2 forward, so when
inverse cascade reintroduces high-frequency content from quant noise,
the underlying signal isn't where it would constructively interfere.

### 8.2 L2 vs L1 — CNN doesn't see L2 directly

The CNN operates on the decoded bayer output, after the inverse cascade
has folded L2 back through L1. The CNN cannot distinguish "L2 quant
noise" from "L1 quant noise" in its input. The matched CNN
`bibo1x_ane_ml2_q3` was trained on the natural L2:L1 distortion ratio
of the q=3 default. Cranking L2 substantially changes that ratio —
the CNN may not absorb L2 noise as effectively as it absorbs L1 noise.

**Implication**: per-knob "CNN absorption" for L2 slots (4, 5, 6) is
expected to be lower than for L1 slots (7, 8, 9). The retrain step
(§4.9) is more important for L2-cranked candidates than for L1-cranked
candidates.

### 8.3 LL2 divisor risk (already known)

`ml2_q3_ll2div4` (FAIL LPIPS 0.98) and `ml2_q3_combo` (FAIL LPIPS 0.92)
demonstrate that aggressively reducing the LL2 internal divisor below
8 risks rANS class-15 overflow on some content. **Do not touch
`FUSED_LL2_DIVISOR` as part of this sweep.** All sweep cells keep LL2
at the default ×16.

### 8.4 LPIPS-only-near-ceiling regime

The champion at LPIPS 0.068 has 0.012 headroom. LPIPS in this regime
moves in jumps from individual feature-detector responses, not smoothly
with bit-rate. Risk: a small bit-rate saving might land on a steep
piece of the LPIPS curve and cost more LPIPS than the savings justify.

**Mitigation**: the worst-image visual-diff PNG MUST be opened
(CLAUDE.md hard rule). The Z8Z_6693 image specifically is the one
sitting on the LPIPS bubble; that image is what the eye must check.

### 8.5 The "champion" itself could be near a regression boundary

The matched CNN at LPIPS 0.068 cleared VIDEO_FREEZE only after the
ms_ssim threshold was loosened from 0.98 to 0.97 on 2026-05-26 (see
`gates.json` $change_log). Z8Z_6693 sits at MS-SSIM 0.9746 — already
below the original 0.98. Any new cranked candidate must clear the
current 0.97 bar; the bar moving in a future PR is out of scope here
(CLAUDE.md "Never edit gates.json in the same PR as code that you're
trying to make pass").

### 8.6 Embedded path is unaffected

Per `project_deployment_targets_split.md`, embedded (Pi 5, in-camera)
ships codec only (no CNN). The cranked ML-2 codec output is *larger
in perceptible artifact* for no-CNN consumers than `ml2_q3` defaults.
The embedded path stays on `ml2_q3` (no override). This work targets
the *desktop video-freeze* class, which has CNN + desktop CPU/GPU.

## 9. Expected outcomes — primary track

### 9.1 Best case

`ml2_q3_l1l2x4 + bibo1x_ane_ml2_q3` (already trained matched CNN)
PASSes VIDEO_FREEZE at ~8 MB mean (22% smaller than the 10.26 MB
champion). No retrain needed. Just registry edits + gate run + claim.

A more conservative best-case: one of the single-knob 8× cranks
(probably HH1 at `9:1152`) passes with the matched CNN at ~9 MB mean
(12% smaller). One retrain on the stacked candidate unlocks another 5%.

### 9.2 Pessimistic outcome

All single-knob crank candidates ≥ 4× bust VIDEO_FREEZE on Z8Z_6693
worst-image LPIPS. Stacked candidates are worse than single-knob. Three
retrains spend ~6 h M5 and close only some of the gap. Final result:
the q=11 preset's L2 cranking is approximately the right operating
point for ML-2 (it's already the matched-CNN training distribution),
and the headroom past q=11 isn't claimable without architecture changes.

We learn:

- The fine-grained per-subband sweep on ML-2 doesn't extend beyond
  q=11. The matched CNN is near its capacity at the current operating
  point.
- ML-2 file-size headroom is exhausted at the current ship CNN
  architecture. Either accept the 10.26 MB mean as the ship floor, or
  invest in CNN architecture (wider, deeper, attention) before another
  cranked-quant push.
- Methodology is clean for future work.

### 9.3 Honest middle case

A single-knob HH1 8× crank gets to worst-image LPIPS 0.072 (within
gate) at ~9.1 MB mean (11% smaller). One retrain brings worst LPIPS
to 0.055 and confirms the operating point. Stacked candidates with L2
are worse; we ship single-knob HH1×8 (over q=11's HH1×4 = slot 9 = 576)
at ~9 MB mean, ~12% smaller than current champion.

### 9.4 SL track outcome (informed by ML-2 result)

If ML-2 ships a 10–15% win, SL is likely to show smaller gains because
of the tighter LPIPS budget. Realistic expectation for SL: 0–5%
additional file-size win over `sl_q11+CNN`, or a NULL result with the
inspection sentence explaining why.

## 10. Execution checklist — ML-2 track (detailed)

Each step ends with a sanity-check gate. If the gate fails, stop and
diagnose before proceeding.

### Step 1 — confirm baseline

```bash
python3 tests/quality_gates/run_gate.py \
    codec=ml2_q3+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools
```

**Sanity gate**: PASS verdict, mean encoded bytes = 10.26 MB, worst
image Z8Z_6693 at LPIPS ~0.068. (If cached, this is one minute.)

### Step 2 — register Phase A single-knob codecs

Edit `pipelines/registry.json` to add the 24 single-knob codec entries
listed in §4.1 (4 multipliers × 6 slots), naming pattern
`ml2_q3_{lh|hl|hh}{1|2}x{2|4|8|16}`. For each, also add the matching
pipeline entry
`codec=<codec_id>+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools`
with `ship_class: VIDEO_FREEZE`.

**Sanity gate**: `python3 tests/quality_gates/run_gate.py
codec=ml2_q3_hh1x2+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools`
runs to completion (regardless of verdict). Run hash written. If the
runner barfs on registry parsing, fix before doing the sweep.

### Step 3 — run Phase A single-knob sweep

```bash
for slot_name in lh2x2 lh2x4 lh2x8 lh2x16 \
                 hl2x2 hl2x4 hl2x8 hl2x16 \
                 hh2x2 hh2x4 hh2x8 hh2x16 \
                 lh1x2 lh1x4 lh1x8 lh1x16 \
                 hl1x2 hl1x4 hl1x8 hl1x16 \
                 hh1x2 hh1x4 hh1x8 hh1x16; do
  python3 tests/quality_gates/run_gate.py \
    "codec=ml2_q3_${slot_name}+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools"
done
```

24 gate runs. Each ~2 min CNN-on with cached intermediates.

**Sanity gate**: all 24 produce `run.json`; per-image LPIPS values are
monotonic in multiplier within each slot (LPIPS at 16× > LPIPS at 8× >
LPIPS at 4× > LPIPS at 2×). Non-monotonic = override parsing bug.

### Step 4 — build per-knob results table

Aggregate the 24 runs into a CSV:

```
codec_id  worst_image  worst_lpips  worst_y_psnr  worst_ms_ssim  worst_dE  mean_bytes  delta_vs_ml2_q3 (%)
```

Sorted by mean_bytes ascending (smallest first), with PASS/FAIL flagged.

Identify:

- **Single-knob winners**: worst LPIPS ≤ 0.08 AND mean_bytes < 10.26 MB.
- **Near-misses**: worst LPIPS in (0.08, 0.12) — Phase B retrain
  candidates.

**Sanity gate**: open WORST visual-diff PNG (Read tool) for the top
two PASS candidates AND the worst near-miss. Verify the metric ranking
matches the eye. If not, document the disagreement and treat the metric
as suspect for that image.

### Step 5 — register Phase A stacked candidates

From per-knob winners (§4.6), build 4–6 stacked codec entries:

- `ml2_q3_l1x4`, `ml2_q3_l2x4`, `ml2_q3_l1l2x4`, `ml2_q3_l1l2x4_hh16`,
  `ml2_q3_winners` (built from sweep winners).

### Step 6 — run Phase A stacked sweep

Gate-run each stacked candidate against the matched CNN. **If any
PASSes VIDEO_FREEZE AND mean bytes ≤ 9.2 MB**: stop sweep, skip to
step 9.

**Sanity gate**: stacked LPIPS should be ≥ max(single-knob LPIPS at
those multipliers). If stacked is somehow lower, suspicion of error in
the gate runner.

### Step 7 — Phase A prefilter pairing

For the most aggressive stacked L2-cranking candidate from §4.6:

```bash
# Build matching prefilter codec
python3 tests/quality_gates/run_gate.py \
    codec=ml2_q3_winners_prefilter+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools
```

**Sanity gate**: does the prefilter help (smaller LPIPS, only mildly
larger file)? If LPIPS is smaller AND file size penalty < 5%, prefilter
is in the ship candidate. If the LPIPS effect is < 0.005, prefilter
isn't load-bearing — drop it from the ship candidate.

### Step 8 — Phase B retrain decision

If no Phase A candidate cleared the win condition, pick up to 3 retrain
candidates per §4.10. For each:

a. Build tiles via a new `tools/cnn/build_tiles_<codec_id>.py` patterned
   on `tools/cnn/build_tiles_ml2_q3.py`. Source = diverse corpus minus
   the 4 gate images.
b. Train per §6 — 80 epochs M5 MPS (~2 h).
c. Register CNN id e.g. `bibo1x_ane_ml2_q3_l1l2x4`, copy checkpoint to
   `models/`, record sha256 in registry.
d. Register pipeline
   `codec=<codec>+cnn=<new_cnn>+demosaic=sips_via_gpr_tools`.
e. `python3 tests/quality_gates/run_gate.py <new_pipeline>`.

**Sanity gate per retrain**: validation PSNR during training > codec-only
bayer PSNR by ≥ +2 dB on val images. If not, training didn't help; do
not bother running the gate.

### Step 9 — ship-claim preflight (per CLAUDE.md)

If a winner exists:

a. Read the WORST visual-diff PNG with the Read tool (CLAUDE.md hard
   rule).
b. `python3 tests/quality_gates/run_gate.py <winner_pipeline> --claim`
   with a ≥6-word inspection sentence containing a concrete noun (e.g.
   "Z8Z_6693 rocks remain detailed across the cranked HH1 boundary").
c. The entry appends to `docs/claims_log.md`.
d. Propose docs update + registry promotion in a separate PR. Do NOT
   amend `gates.json` or `test_set.json` in that PR.

### Step 10 — SL track

The SL track follows the same procedure with slots 1, 2, 3 on
`codec=sl_q3` (no `FUSED_MULTI_LEVEL`), gating against STILL, and
beating `sl_q11+CNN`'s 22.4 MB mean. See §5 for the per-slot
multiplier table. Reuse the same retrain pipeline; budget is what's
left after ML-2.

### Step 11 — gates.json / test_set.json discipline

Per CLAUDE.md: **no edits** to either file in any PR landing this work.
If Z8Z_6693 fails on every candidate, the gate hasn't moved — Z8Z_6693
remains in the gate.

## 11. Wall-clock estimate (M5 MPS)

### 11.1 ML-2 track

| Step | Wall clock | Notes |
|---|---|---|
| 1 — confirm baseline | 5 min | cached |
| 2 — registry edits (24 single-knob + 4 stacked + 2 prefilter pipelines) | 30 min | JSON edits, careful |
| 3 — Phase A single-knob sweep (24 runs × 4 images, CNN on) | ~90 min | each gate ~2 min CNN-on with caching |
| 4 — per-knob table + visual-diff review | 45 min | image opens, table building |
| 5 — register stacked codecs | 15 min | 4–6 entries |
| 6 — Phase A stacked sweep | 15 min | up to 6 gate runs |
| 7 — Phase A prefilter pairing | 15 min | 2 gate runs |
| 8 — Phase B retrains (worst case 3) | ~6 h | 2 h per retrain on M5 |
| 9 — ship-claim preflight | 30 min | claim log entry, PR draft |

**ML-2 track total**: 3–4 h if no retrain needed; ~10 h if all 3
retrains exercised. Roughly **half a working day to a long working
day on M5**, of which ~6 h is unattended training.

### 11.2 SL track

| Step | Wall clock |
|---|---|
| SL single-knob sweep (12 runs × 4 images) | ~45 min |
| Phase A stacked + visual-diff review | 1 h |
| Phase B retrains (0–2) | 0–4 h |
| Ship-claim | 30 min |

**SL track total**: 2 h if no retrain; ~6 h with 2 retrains.

### 11.3 Combined

**4–18 h, two tracks**. Realistic mid-case: ~12 h (8 h ML-2, 4 h SL,
some retraining on both). Mostly unattended.

## 12. Out-of-scope (do not let scope creep here)

- Any work on ML-3. Documented Nyquist regression; not shipping.
- Modifying `quality_tables[3]` defaults — both SL and ML default
  shipping behaviour must be unchanged.
- Editing `tests/quality_gates/gates.json` or `test_set.json`. Hard
  rule per CLAUDE.md.
- New CNN architecture variants. We only swap training distribution;
  architecture stays `F_ane_no_sr`. (BIBO_2x super-res is its own
  track, not part of this plan.)
- Joint demosaic+super-res CNNs (`F_ane_dm_sr`). Out of scope.
- `FUSED_LL2_DIVISOR` changes. Known rANS overflow risk per §8.3.
- Embedded / Pi 5 deployment of the cranked codec. Desktop video
  freeze only.

## 13. Open questions for the human

1. **Which gate image is the binding constraint?** Z8Z_6693 is the
   matched-CNN champion's worst-image at LPIPS 0.068. If we expect to
   gain 10–20% file size while *not* making Z8Z_6693 worse, that's
   tight. If Z8Z_6693 is in some sense "exceptional" — e.g.
   high-frequency man-made content — the sweep result might tell us
   that the gate's binding constraint isn't representative of typical
   video freeze frames. Worth knowing before declaring failure.
2. **q=11 retraining provenance.** The `bibo1x_ane_ml2_q3` matched CNN
   was trained against `ml2_q3` defaults. Did training include any
   `q=11`-cranked tiles? If so, the matched CNN has wider distribution
   coverage than just q=3 defaults and the sweep may surprise upward.
   If not (cold q=3 only), it explains why q=11 codec + matched-CNN
   has not yet been gate-tested.
3. **Should `ml2_q11+cnn=bibo1x_ane_ml2_q3` be the very first sweep
   point?** It's already in the registry (q=11 preset). One gate run
   answers the question: does q=11 + matched-CNN beat q=3 + matched-CNN
   without any custom override? If yes, that's a free Phase A win before
   the sweep starts. If no, the sweep is starting from a known position.
4. **CNN retrain corpus.** Reuse the same 200 + 298 = 498 diverse DNGs
   that trained `bibo2x_ane_ml2_q3_dec2_diverse`? Or curate a new
   subset weighted toward Z8 50 MP since that's the gate? Either is
   defensible; the diverse corpus is the more conservative choice.

## 14. Infrastructure gaps (none blocking, two to flag)

The infrastructure for executing the ML-2 track is essentially
complete:

- `apply_quant_override` parses `GPR_QUANT_OVERRIDE` for both encoder
  and decoder.
- `tests/quality_gates/run_gate.py` evaluates VIDEO_FREEZE candidates
  end-to-end.
- `pipelines/registry.json` accepts new codec entries via plain JSON
  edits.
- `tools/cnn/train.py` + `tools/cnn/build_tiles_ml2_q3.py` cover the
  retrain pipeline.
- Matched CNN `bibo1x_ane_ml2_q3` is trained and registered.

Two flags:

1. **Per-codec tile builder duplication**. Each new cranked codec needs
   its own `tools/cnn/build_tiles_<codec_id>.py`. A more general
   `build_tiles_from_codec.py <codec_id>` script (looking up the codec
   env from the registry and invoking the binary) would save 10 lines
   per retrain — not blocking, just cleanup.
2. **`run_gate.py --claim` inspection sentence is hand-typed.** For
   the ML-2 winner, the inspection sentence will reference a specific
   crop of Z8Z_6693 (the worst-image binding constraint). Operator
   discipline, not tooling — but worth noting that the claim is on the
   operator, not the runner.

## 15. Table of contents

- §0 — Two-track summary, why ML-2 is primary
- §1 — Baselines (ML-2 and SL champions)
- §2 — ML-2 slot map
- §3 — Stale per-subband data — what's being re-measured
- §4 — **Primary track: ML-2 fine-grained sweep**
  - §4.1 Sweep grid
  - §4.2 Existing ML-2 codec entries that overlap
  - §4.3 Cranking direction
  - §4.4 Metrics
  - §4.5 Headroom call-outs
  - §4.6 Stacked patterns + L1L2x4 re-derivation
  - §4.7 Prefilter risk mitigation
  - §4.8 Gate-pass condition
  - §4.9 CNN retrain — historical first, then fresh
  - §4.10 Retrain decision tree
- §5 — **Secondary track: SL fine-grained sweep**
- §6 — Shared CNN architecture decisions
- §7 — Cross-track sequencing
- §8 — Risks specific to ML-2
- §9 — Expected outcomes
- §10 — Execution checklist (ML-2 detailed; SL as pointer)
- §11 — Wall-clock estimate
- §12 — Out-of-scope
- §13 — Open questions for the human
- §14 — Infrastructure gaps
