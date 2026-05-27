# CNN-aware fine-grained compression — revival plan on the SHIPPING single-level codec

**Author:** planning pass, 2026-05-27
**Status:** plan only — no code changes proposed in this doc
**Companion docs (read first):**

- [docs/REGRESSION_2026-05-25.md](REGRESSION_2026-05-25.md) — why the prior numbers are invalid
- [docs/methodology_cnn_aware_quant.md](methodology_cnn_aware_quant.md) — the AccelIR-style methodology (sound; figures need re-measurement)
- [docs/quant_calibration_findings.md](quant_calibration_findings.md) — per-subband sweep data (multi-level; stale)
- [pipelines/registry.json](../pipelines/registry.json) — existing experimental codec entries showing `GPR_QUANT_OVERRIDE` syntax

## 0. One-line goal

Replace `codec=sl_q11+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools`
(current STILL champion: PASS at worst LPIPS 0.024, ~24% smaller files
than `sl_q3+CNN` baseline) with a fine-grained per-subband cranked
single-level pipeline at **smaller files AND no worse LPIPS** worst-case.

## 1. Baselines we are trying to beat

From `tests/quality_gates/runs/`:

| Pipeline | Worst image | Worst LPIPS | Worst Y-PSNR | Avg encoded bytes | Verdict |
|---|---|---|---|---|---|
| `codec=sl_q3+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` (run `7c4a529562b0f588`) | Z8Z_0067 | 0.0086 | 44.69 (Z8Z_6693) | 26.6 MB | PASS |
| `codec=sl_q11+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools` (run `0b6114e53fd0e04d`) | Z8Z_0067 | 0.0237 | 43.33 (Z8Z_6693) | 22.4 MB | PASS |

`sl_q11` is **15.8% smaller** than `sl_q3` (not the 24% in the prompt;
the registry shows similar magnitudes and the prompt may be rounding to
a broader baseline). Either way, `sl_q11+CNN` is the bar.

Headroom on every metric is large vs STILL gate (`lpips ≤ 0.05`,
`ms_ssim ≥ 0.99`, `y_psnr ≥ 35`, `dE2000 ≤ 1.5`). The CNN is doing a
lot of heavy lifting — we have room to crank harder.

## 2. Architectural background — single-level slot map

For the single-level codec (`GPR_INCLUDE_LL=1`, no `FUSED_MULTI_LEVEL`),
the encoder reads slots 0..3 of `quality_tables[quality]` in
`source/lib/vc5_encoder/fused_encode.c:228` (and the mirror in
`source/lib/vc5_decoder/fused_decode.c`):

| Slot | Subband (single-level) | `q=3` default | `q=11` value | Notes |
|---|---|---|---|---|
| 0 | LL | 1 | 1 | `GPR_INCLUDE_LL=1` multiplies this by 16 internally (`q_ll1_base *= 16` at fused_encode.c:3993) |
| 1 | LH (vertical edges) | 24 | 48 | 2× crank in `q=11` |
| 2 | HL (horizontal edges) | 24 | 48 | 2× crank in `q=11` |
| 3 | HH (diagonal) | 12 | 48 | **4× crank in `q=11`** — heaviest |

Slots 4..9 are multi-level only and ignored in single-level (encoder
only walks 4 slots: `int divs[4] = { q_ll1_base, qt[q_lh1], qt[q_hl1], qt[q_hh1] }`).

The `GPR_QUANT_OVERRIDE` env (parsed identically by encoder
`apply_quant_override` at `fused_encode.c:260` and the decoder) takes
`"slot:value,slot:value"` pairs; we'll use slots **1, 2, 3** for the
single-level sweep.

## 3. The (stale) per-subband data we are re-measuring

`docs/quant_calibration_findings.md` and §4.1 of methodology paper
reported on **multi-level** outputs. Per the regression doc, the
multi-level cascade introduced ~10 dB of visual loss that didn't show
in bayer-PSNR. Specifically the multi-level vs single-level "amazing
sl_q3+CNN" delta:

- Multi-level barn_sky CNN gain: +0.3 to +4.6 dB
- Single-level barn_sky CNN gain: +4.21 to +17.49 dB

So the CNN already does much better against single-level distortion
than it did against multi-level distortion (per `REGRESSION_2026-05-25.md`
final section). The per-subband CNN-gain table needs to be re-measured
in this environment; we should expect the gains to be **higher**, not
lower, because the CNN's existing training distribution overlaps
single-level cleanly.

## 4. Calibration sweep plan (per-subband, single-level)

### 4.1 Sweep grid

For each axis-aligned subband {LH, HL, HH} at the level-1 wavelet, sweep
multipliers {1× (ref), 2×, 4×, 8×, 16×}. The slot/multiplier ↔
`GPR_QUANT_OVERRIDE` string mapping:

| Friendly name | Slot | Default (q=3) | 1× | 2× | 4× | 8× | 16× |
|---|---|---|---|---|---|---|---|
| LH | 1 | 24 | (skip — ref) | `"1:48"` | `"1:96"` | `"1:192"` | `"1:384"` |
| HL | 2 | 24 | (skip — ref) | `"2:48"` | `"2:96"` | `"2:192"` | `"2:384"` |
| HH | 3 | 12 | (skip — ref) | `"3:24"` | `"3:48"` | `"3:96"` | `"3:192"` |

Reference encode = `sl_q3` defaults (no override).

15 sweep cells × 4 gate images = 60 encode/decode/render runs per pass.

### 4.2 Metrics collected per cell

For each (slot, multiplier, image):

1. **File size** vs `sl_q3` reference (per-image and mean).
2. **Bayer-PSNR codec-only** (no CNN) vs source DNG's bayer plane.
3. **Y-PSNR**, **MS-SSIM**, **LPIPS**, **ΔE2000** after sips render
   (no CNN) vs the gate's REF rendering of the source.
4. **Y-PSNR, MS-SSIM, LPIPS, ΔE2000** with `bibo1x_ane_sl_q3` CNN
   applied to the decoded bayer, then sips-rendered.

Items 3 and 4 are what gate uses. Item 2 is keep-honest (any bayer-PSNR
fall that LPIPS doesn't reflect is the regression mode we're guarding
against).

### 4.3 Why these multipliers

- 1× is the baseline (already in `sl_q3`).
- 2× is the existing `sl_q11` setting for slots 1/2; we should match
  this somewhere.
- 4× is the existing `sl_q11` setting for slot 3.
- 8× and 16× are the fine-grained exploration — what happens beyond
  q=11's per-subband cranks?

### 4.4 Existing harness

`tools/test/quant_calibration.py` already implements `--mode per-subband`
in `--encoder-mode single-ll`. Per the methodology paper §2.5, the
command is:

```
python3 tools/test/quant_calibration.py --mode per-subband \
    --corpus /Volumes/OWC_8TB/gate_dngs_4 \
    --slots 1,2,3 --multipliers 1.0,2.0,4.0,8.0,16.0 \
    --encoder-mode single-ll --with-cnn \
    --cnn-ckpt-pt models/BayInBayOut_1x_AAon_w16_ANE.pt \
    --out-dir /Volumes/OWC_8TB/gpr_artifacts/quant_calibration_singlelevel_2026-05-27
```

Note this harness operates at half-res (decimate=2) by design — it was
the multi-level investigation path. **Critical adaptation needed**: re-run
with `decimate=0` (full-res) and gate-aligned source bayer / target render
path, OR fall back to running the actual ship-gate per candidate (slower
but more honest). Recommend the latter — see §7.

## 5. Pipeline registry plan

### 5.1 New codecs

Add the following codec entries to `pipelines/registry.json` — single-level,
quality=3 base, with `GPR_QUANT_OVERRIDE` per subband and multiplier.
Naming convention follows existing `ml2_q3_l1soft` / `ml2_q3_l2soft`
style but with `sl_` prefix and explicit subband+multiplier:

| Codec id | `GPR_QUANT_OVERRIDE` | Notes |
|---|---|---|
| `sl_q3_lh1x2` | `1:48` | LH 2× |
| `sl_q3_lh1x4` | `1:96` | LH 4× |
| `sl_q3_lh1x8` | `1:192` | LH 8× |
| `sl_q3_hl1x2` | `2:48` | HL 2× |
| `sl_q3_hl1x4` | `2:96` | HL 4× |
| `sl_q3_hl1x8` | `2:192` | HL 8× |
| `sl_q3_hh1x2` | `3:24` | HH 2× |
| `sl_q3_hh1x4` | `3:48` | HH 4× — same as `sl_q11`'s HH crank |
| `sl_q3_hh1x8` | `3:96` | HH 8× — **most promising single knob** |
| `sl_q3_hh1x16` | `3:192` | HH 16× — exploration ceiling |

Stacked candidates (from prior work, single-level slot map):

| Codec id | `GPR_QUANT_OVERRIDE` | Notes |
|---|---|---|
| `sl_q3_lhhl_x2_hh_x4` | `1:48,2:48,3:48` | Equivalent to `sl_q11` per §3, written explicitly |
| `sl_q3_lhhl_x2_hh_x8` | `1:48,2:48,3:96` | Crank HH harder vs `sl_q11` |
| `sl_q3_lhhl_x4_hh_x8` | `1:96,2:96,3:96` | "AccelIR stack" — analogue of the old L1L2x4 pattern |
| `sl_q3_lhhl_x4_hh_x16` | `1:96,2:96,3:192` | Aggressive ship target |

All entries share:
```json
"binary": "build-local/bin/test_fused_roundtrip",
"env": {
  "GPR_INCLUDE_LL": "1",
  "GPR_QUANT_OVERRIDE": "<as above>"
},
"quality": 3
```

### 5.2 New pipelines

For each candidate codec, the pipeline name is
`codec=<codec_id>+cnn=<cnn_id>+demosaic=sips_via_gpr_tools`. Phase A
re-uses the shipped CNN; Phase B is post-retrain.

**Phase A** (existing CNN, no retrain):
- `codec=sl_q3_hh1x4+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools`
- `codec=sl_q3_hh1x8+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools`
- `codec=sl_q3_lhhl_x2_hh_x8+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools`
- `codec=sl_q3_lhhl_x4_hh_x8+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools`

All declared `ship_class: STILL` (we want them to clear the STILL gate
or fail with worst-image evidence).

**Phase B** (after at most 3 retrains):
- New CNN id e.g. `bibo1x_ane_sl_q3_hh1x8` (trained against
  `sl_q3_hh1x8` codec) — paired with the matching codec.

## 6. Retrain decision tree

### 6.1 Does the existing CNN handle the new distribution?

Decision rule from Phase A sweep results, per candidate codec:

1. If candidate **clears STILL gate with the existing CNN** AND is smaller
   than `sl_q11+CNN`: **ship as the new STILL champion. No retrain
   needed.**
2. If candidate **fails STILL but worst LPIPS < 0.10**: Phase B — retrain
   the CNN against the new codec's distribution.
3. If candidate fails STILL with worst LPIPS ≥ 0.10: probably too
   aggressive for retrain to fix without a stronger architecture.
   Either back off the crank or admit defeat on that knob.

### 6.2 Retrain recipe (if needed)

Mirror the recipe in `pipelines/registry.json` `bibo1x_ane_ml2_q3` and
the existing tile-builders (`tools/cnn/build_tiles_dmsr_gate_aligned.py`):

- **Architecture**: `F_ane_no_sr` (= BIBO_1x, w=16, AAon). Input and
  output are 4-channel bayer; no super-res. Matches `bibo1x_ane_sl_q3`.
  No new architecture variant needed; only the training distribution
  changes.
- **Training data**: pairs of (cranked-codec output, source bayer) at
  tile granularity. Reuse the same source DNGs that built
  `bibo2x_ane_ml2_q3_dec2_diverse` — 200 barn_sky + 298 diverse NEFs
  from `/Volumes/OWC_8TB/gpr_cnn/diverse_dngs/` and
  `/Volumes/OWC_8TB/barnsky_full_dngs/`. **Filter out the 4 gate images**
  before tiling. Build via a new
  `tools/cnn/build_tiles_sl_q3_<variant>.py` patterned on
  `build_tiles_ml2_q3.py`.
- **Loss**: same loss schedule as `bibo1x_ane_ml2_q3_msssim` —
  L1 + MSSSIM_LOSS_WEIGHT=0.3. (MS-SSIM term matters because that's
  the second-strictest gate metric after LPIPS.)
- **Optimizer**: AdamW lr=5e-4, cold start (no warm-start from
  `bibo1x_ane_sl_q3`; the multi-level retrains showed cold-start
  generalises better when the input distribution shifted).
- **Schedule**: 80 epochs M5 MPS, ~90 s/epoch on a 200-DNG corpus →
  ~2 h per retrain. Plan for AT MOST 3 retrains. Strict early-stop:
  best epoch checkpoint, no warm continuation.
- **Validation**: 4 held-out images from the diverse corpus (NOT the
  4 gate images — preserve test-set integrity). Pick by characteristic
  to span the gate set: one hard-detail, one smooth-gradient, one
  high-detail-studio, one mixed-contrast.
- **Tile gen reference**: use `tools/cnn/build_tiles_dmsr_gate_aligned.py`
  as the template for gate-aligned target generation (it goes
  bayer → gpr_tools-wrap → sips render to match the gate's REF).

### 6.3 Retrain budget — at most 3

Spend the 3-retrain budget on the *best* Phase A candidate, the *most
ambitious* one we want to ship, and one fallback. Concretely:

1. Best Phase A candidate that *just* failed STILL (e.g.
   `sl_q3_hh1x8` if Phase A shows worst LPIPS ≈ 0.06–0.10).
2. The stacked candidate `sl_q3_lhhl_x4_hh_x8` if Phase A shows it as
   a possible big win.
3. Held in reserve for whatever the Phase A sweep flags as worth
   another shot.

## 7. Stack-and-test

After step 4 (per-subband sweep with existing CNN), step 5 is the
combined-knob test:

1. From the per-subband Phase A results, pick the multipliers per
   subband at which `LPIPS_with_CNN ≤ 0.04` (gives gate headroom) and
   file-size savings per knob is ≥ 4%.
2. Build the stacked `GPR_QUANT_OVERRIDE` from those multipliers and
   register a codec entry per §5.1.
3. Run the gate against the stacked codec + existing CNN.
4. If it PASSes STILL, you're done — log claim with the worst-image
   inspection sentence and propose as the new STILL champion.
5. If it FAILs STILL but worst LPIPS < 0.08, retrain (Phase B).
6. The stacked test answers an open question from `methodology_cnn_aware_quant.md`
   §8: do the per-subband gains stack, or does the CNN saturate?

## 8. Gate verification — pass condition

A candidate **wins** if both are true:

1. `run_gate.py codec=<candidate>+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools`
   returns PASS for ship_class STILL.
2. Mean encoded bytes (across the 4 gate images) is **strictly less
   than** the `sl_q11+CNN` mean of 22.4 MB.

(Mean is acceptable for the file-size comparison because file size is
not a quality verdict; the per-image worst-case rule from CLAUDE.md
applies to *quality* not bytes.)

For a borderline winner (file size only 1–2% smaller), don't ship —
the gain isn't worth the disruption. Target ≥ 5% smaller than
`sl_q11+CNN`, i.e. ≤ 21.3 MB mean.

## 9. Risk assessment

### 9.1 Bayer-PSNR misled us — could it again?

The multi-level walk-back was caused by bayer-PSNR not catching the
cross-hatch artifacts that LPIPS / MS-SSIM did. We're now collecting
LPIPS, MS-SSIM, Y-PSNR, ΔE2000 on the sips-rendered output. **This is
a different metric stack** — the multi-level regression would have
been caught by this stack. Risk remains that a new artifact category
emerges that none of these four metrics catch; mitigation is the
mandatory visual-diff read in CLAUDE.md (open the WORST visual-diff
PNG before claiming ship).

### 9.2 CNN saturation

The methodology paper §8 notes: "the +5.6 / +4.4 / +4.2 dB gains were
measured independently. Whether they stack or the retrained CNN
saturates at ~5 dB total is unmeasured." On the *single-level* codec
this stacking question hasn't been answered at all. Possible outcomes:

- Gains stack roughly linearly → big wins.
- CNN saturates at one knob → only one subband can be cranked, others
  give diminishing returns.
- Stacking *hurts* — the cross-band correlation in errors that the CNN
  was trained on breaks at extreme cranks.

The way we learn which is by running step 7's stacked-codec test, not
by speculation. Plan accordingly: don't pre-commit to a stacked-CNN
retrain until the stacked codec result is in.

### 9.3 LPIPS doesn't move with file size

`q=3` vs `q=8` worst LPIPS is 0.0086 vs ~0.01 (huge file-size delta,
tiny LPIPS delta). This is the "you can't measure what you're saving
in LPIPS at this end of the curve" regime — every metric we care about
is sub-gate by a wide margin. **Implication**: even huge file savings
might land at "PASS but I can't show you why I'm proud of it." That's
fine for the production ship decision — what matters is that the file
size went down AND every per-image LPIPS stayed under 0.05. The
inspection sentence will need to lean on the file-size delta as the
visible win.

### 9.4 The methodology itself may be flawed

The multi-level walk-back demonstrated that an entire research program
was built on a metric that hid a real regression. The replacement metric
stack (Y-PSNR + MS-SSIM + LPIPS + ΔE2000 on sips-rendered RGB) is the
honest fix, but we should remain alert for any one image where
file-size savings come with metric movement that the human eye
disagrees with on the visual diff. **Mitigation**: at each pass/fail
verdict, the worst-image visual-diff PNG MUST be opened (CLAUDE.md
ship-claim preflight); if the eye disagrees with the metric, treat
as FAIL and document.

### 9.5 The CNN is paired with a moving target

If we retrain the CNN against `sl_q3_hh1x8`, that CNN can no longer be
the production CNN for plain `sl_q3` content unless we cross-validate
it. The cleanest split: ship the retrained CNN with the cranked codec
as a paired bundle (matching the existing `trained_against_codec`
discipline in `pipelines/registry.json`). The current production CNN
(`bibo1x_ane_sl_q3`) keeps pairing with `sl_q3` and `sl_q11`.

### 9.6 Pi 5 / embedded budget

Per `feedback_honest_capture_bench.md`, the embedded path is bandwidth-
limited (~6.88 fps sensor → SD on Pi 5). Smaller still files help the
microSD wear-life. This work is desktop-class still ship; embedded ships
no CNN (per `project_deployment_targets_split.md`). The cranked codec
output is *bigger* for non-CNN consumers than `sl_q3` because the bit
savings come from the CNN absorbing distortion the bare decode shows.
For non-CNN users we still ship `sl_q3` defaults. **Do not change the
default quants in `quality_tables[3]`** as part of this work.

## 10. Step-by-step execution checklist

Each step ends with a sanity-check gate. If the gate fails, stop and
diagnose before proceeding.

### Step 1 — confirm baseline numbers

```bash
# Re-confirm baselines (cheap if run dirs already exist)
python3 tests/quality_gates/run_gate.py codec=sl_q3+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools
python3 tests/quality_gates/run_gate.py codec=sl_q11+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools
```

**Sanity gate**: both PASS, sl_q11 mean encoded bytes < sl_q3 mean.
Record the exact baseline numbers in a scratchpad — do not regress them.

### Step 2 — register Phase A codec entries

Edit `pipelines/registry.json` to add the 10 single-knob and 4 stacked
`sl_q3_*` codecs from §5.1, and the matching Phase A pipelines from §5.2.
(This is a registry edit only; no source changes.)

**Sanity gate**: `python3 tests/quality_gates/run_gate.py
codec=sl_q3_hh1x2+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools`
runs to completion (even if FAIL). Run hash written to
`tests/quality_gates/runs/`. If the runner barfs on registry parsing,
fix and re-try before doing the full sweep.

### Step 3 — run Phase A single-knob sweep

For each of the 10 single-knob pipelines, run the gate:

```bash
for codec in sl_q3_lh1x2 sl_q3_lh1x4 sl_q3_lh1x8 \
             sl_q3_hl1x2 sl_q3_hl1x4 sl_q3_hl1x8 \
             sl_q3_hh1x2 sl_q3_hh1x4 sl_q3_hh1x8 sl_q3_hh1x16; do
  python3 tests/quality_gates/run_gate.py \
    "codec=${codec}+cnn=bibo1x_ane_sl_q3+demosaic=sips_via_gpr_tools"
done
```

**Sanity gate**: all 10 produce run.json with no errors. Per-image LPIPS
values look monotonic in multiplier — if `sl_q3_hh1x16` somehow has
lower worst LPIPS than `sl_q3_hh1x4`, something is wrong with override
parsing.

### Step 4 — build per-knob results table

Aggregate the 10 runs into a table (sortable in a tmp Markdown or CSV):

```
codec_id  worst_lpips  worst_y_psnr  mean_bytes  delta_vs_sl_q3 (%)
```

worst-image is the lead per CLAUDE.md. Identify:

- Single-knob *winners* (LPIPS_worst ≤ 0.05 AND mean_bytes <
  22.4 MB) — these PASS STILL and beat `sl_q11+CNN`.
- *Near-misses* (LPIPS_worst ≤ 0.08, fails STILL but on the edge) —
  candidates for retrain (Phase B).

**Sanity gate**: open WORST visual-diff PNG for at least the top two
candidates and the worst FAIL. Verify the metric ranking matches the
eye.

### Step 5 — Phase A stacked test

Build the stacked codec from the per-knob winners (the multipliers per
slot at which STILL passed). Register, run gate. **If this PASSes
STILL AND beats `sl_q11+CNN` mean bytes**: stop and propose as the
new champion. Skip to step 8.

**Sanity gate**: stacked LPIPS_worst < any single-knob LPIPS_worst at
the same per-slot multipliers would be suspicious — expect stacked ≥
max(single-knob).

### Step 6 — Phase B retrain decision

If step 5 PASSes but with little file-size gain, OR step 5 fails STILL
but with worst LPIPS < 0.08, retrain. Pick at most 3 candidates per §6.3.

For each retrain candidate:

a. Build tiles via a new `tools/cnn/build_tiles_<codec_id>.py`
   patterned on `build_tiles_ml2_q3.py` + `build_tiles_dmsr_gate_aligned.py`.
   Source = diverse corpus minus the 4 gate images.
b. Train per §6.2 — 80 epochs M5 MPS, ~2 h.
c. Register CNN id e.g. `bibo1x_ane_sl_q3_hh1x8`, copy checkpoint to
   `models/`, record sha256 in registry.
d. Register pipeline `codec=<codec>+cnn=<new_cnn>+demosaic=sips_via_gpr_tools`.
e. `python3 tests/quality_gates/run_gate.py <new_pipeline>`.

**Sanity gate per retrain**: val PSNR during training > codec-only
bayer PSNR by at least +2 dB on val images. If not, training did not
help; do not bother running the gate.

### Step 7 — Phase B gate verification

For each retrained pipeline, evaluate against the §8 win condition.
Stop on first winner.

### Step 8 — ship-claim preflight

If a winner exists:

a. Read the WORST visual-diff PNG with the Read tool (CLAUDE.md hard rule).
b. `python3 tests/quality_gates/run_gate.py <winner_pipeline> --claim`
   with a ≥6-word inspection sentence containing a concrete noun.
c. The entry appends to `docs/claims_log.md`.
d. Propose docs update + registry promotion in a separate PR.

### Step 9 — gate.json / test_set.json discipline

Per CLAUDE.md "Hard-rules about gates.json and test_set.json":
**no edits** to either file in any PR landing this work. If a candidate
fails on Z8Z_6693 specifically, that failure IS the answer, not a
prompt to remove Z8Z_6693 from the test set.

## 11. Expected outcome

### 11.1 Best case

`sl_q3_hh1x8 + bibo1x_ane_sl_q3` already PASSes STILL with mean bytes
~18 MB (file size scaling roughly linearly with HH crank above what
`sl_q11` already does, with the CNN trained on a closely-related
distribution and absorbing the extra error). 30–35% smaller than the
current STILL ship. Best case: a no-retrain win, just registry +
gate-run + claim.

A more conservative best-case: the stacked Phase A candidate
(`sl_q3_lhhl_x4_hh_x8 + bibo1x_ane_sl_q3`) PASSes STILL at ~19 MB
mean — 15% smaller than `sl_q11+CNN`, 30% smaller than `sl_q3+CNN`.

### 11.2 Most pessimistic outcome

Phase A reveals that all single-knob cranks past 4× hit a CNN
saturation point — LPIPS worst lands at 0.06–0.10 for HH×8/16, and
the stacked test makes it strictly worse (LPIPS 0.12+). Phase B
retrains (3 attempts) close some of the gap but never bring a stacked
crank below the gate, AND no single-knob crank beats `sl_q11+CNN`
significantly enough to ship. We learn:

- The fine-grained sweep doesn't extend beyond `sl_q11`'s settings.
- `sl_q11+CNN` remains the STILL champion.
- We have a clean methodology and reproducible numbers for future work
  (e.g. when an architecture change to the CNN unlocks more headroom).

In the pessimistic case, file 1-3 new gate.json *informational-only*
metric ideas (e.g. file-size budget per ship_class, NOT a gate
threshold) and re-park this until the CNN architecture changes.

### 11.3 The honest middle case

`sl_q3_hh1x8` Phase A is borderline (worst LPIPS 0.05–0.07 — at or just
above STILL). One retrain (≈ 2 h M5) brings it under 0.04 and we ship
it at ~19 MB mean (15% smaller than `sl_q11+CNN`). Stacked variants
don't add over the single-knob retrain. Net: a small but real ship
win, methodology preserved for the next iteration.

## 12. Wall-clock estimate (M5 MPS)

Per-step rough timing:

| Step | Wall clock | Notes |
|---|---|---|
| 1 — confirm baselines | 5 min | 2 gate runs cached |
| 2 — registry edits | 10 min | text edits |
| 3 — Phase A single-knob (10 runs × 4 images) | ~60 min | each gate is ~2 min; CNN inference is the bottleneck |
| 4 — Phase A table + visual-diff review | 30 min | image opens, table building |
| 5 — Phase A stacked test | 10 min | one gate run |
| 6 — Phase B retrains (worst case 3) | ~6 h | 2 h per retrain on M5; can pipeline 1-2 if dataset prep is parallel |
| 7 — Phase B gate verification | 30 min | up to 3 gate runs |
| 8 — ship-claim + docs PR | 30 min | claim log entry, PR draft |

**Total wall clock**: 1–2 h if no retrain needed; ~9 h if all 3
retrains are exercised. Roughly **half a working day to a full working
day on the M5**, of which ~6 h is unattended training.

## 13. Out-of-scope (do not let scope creep here)

- Any work on multi-level codec (`ml2_*` / `ml3_*`). Separate track.
- Modifying the `quality_tables[3]` defaults. Single-level `q=3` must
  remain the no-CNN default per `project_deployment_targets_split.md`.
- Editing `tests/quality_gates/gates.json` or `test_set.json`. Hard
  rule per CLAUDE.md.
- New CNN architecture variants. We only swap training distribution;
  architecture stays `F_ane_no_sr`.
- Embedded / Pi 5 deployment of the cranked codec. Desktop STILL only.
- Demosaic-domain experiments (e.g. F_ane_dm_sr for stills). Out of
  scope; we want a clean per-subband result first.

## 14. Open questions for the human

1. Should `sl_q11` itself be re-registered with explicit
   `GPR_QUANT_OVERRIDE` (rather than `FUSED_QUALITY=11`) so the
   "single-level cranked" knob lineup is regular? This would make the
   `quality_tables[11]` entry effectively a convenience preset rather
   than load-bearing. Mild refactor; not blocking.
2. The "24% smaller files" headline in the prompt vs the 15.8% observed
   in `runs/0b6114e53fd0e04d/run.json` — which baseline does that
   compare against? If it's mean encoded bytes vs the `sl_q3` REF
   stored in the gate (which uses a different encoder than `sl_q3`
   FUSED), we may be measuring two different things. Worth resolving
   before declaring the new win in percentage terms.
3. Naming: do we like `sl_q3_hh1x8` or would the user prefer
   `sl_q3_crankhh8` / `sl_q3_v_hh8` / something else? Names go in the
   registry forever (no rename in same PR as artifact run, per
   `pipelines/registry.json` `$rules`).
