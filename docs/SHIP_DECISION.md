# Ship-decision artifact — CNN-aware quant + retrained CNN

> **⚠ 2026-05-25 evening update — much of this doc is wrong.** All the
> empirical numbers below were measured on the FUSED multi-level path,
> which has been since shown to have a ~10 dB visual-quality regression
> vs single-level (see `docs/REGRESSION_2026-05-25.md`). The "22%
> savings" figure for q=12 was buying broken reconstruction. Re-measured
> on single-level, the equivalent crank pattern saves ~16%, and the CNN
> trained on multi-level outputs is not directly applicable. **Do not
> ship any of the recommendations below until the multi-level cascade
> bug is fixed (task #172).** Read REGRESSION_2026-05-25.md first.

## TL;DR (ORIGINAL — see warning above)

We have empirical evidence that **a retrained BIBO_1x CNN + cranked
default quants** ships 5-22% smaller files at the same CNN-corrected
quality. This doc lays out the three options for shipping it, the
specific changes each requires, and the trade-offs.

Pre-release exploration framing applies (see
`memory/project_strategic_framing.md`): we're building a contribution
candidate for GoPro's OSS codec, not deploying commercially.

## What's already shipped (this session)

The infrastructure to ship q=11 is fully in place:

- Encoder + decoder accept q=11 (PR #21)
- `quality_tables[11]` = `{1, 24, 24, 12, 24, 24, 12, 192, 192, 576}`
  (multi-level L1 cranked ×2/×2/×4)
- Retrained CNN trained on the cranked distribution; checkpoint at
  `/Users/dcliftreaves/dering_proto_v2/checkpoints/BayInBayOut_1x_AAon_w16_ANE_HH1x4.pt`
- Calibration harness + diverse-corpus eval CSV
- Methodology writeup in `docs/methodology_cnn_aware_quant.md`

What's NOT shipped yet:

- The retrained checkpoint itself (not in the gpr repo)
- The change to make q=11 (or cranked quants) the default
- Any q=12+ preset that combines L1 + L2 cranking

## Empirical data summary

### Single-knob savings (single-frame Z8 50 MP, retrained CNN)

| Crank | bits saved (multi-level) | retrained CNN gain |
|---|---|---|
| L1 ×2 (= q=11 shipped) | 4.7% | (see L1 lines below) |
| L1 ×4 only | 6.7% | LH1 +4.03, HL1 +3.71, HH1 +4.79 dB |
| L2 ×2 added | jumps to ~22% combined | LH2 +1.93, HL2 +1.98, HH2 +2.65 dB |
| L2 ×4 added | 26.2% | (proportionally smaller gain at ×4) |
| L3 cranks | +1-2% only | LH3/HL3 ~0 dB, HH3 +1.5 dB |

### Stacked savings (the real ship signal)

| Config | KB/frame | % saved vs default | CNN absorbs distortion? |
|---|---|---|---|
| default (q=3) | 408 | — | n/a |
| L1 ×2 (= shipped q=11) | 389 | 4.7% | yes (retrained gain ~+4 dB) |
| L1 ×4 | 381 | 6.7% | yes (retrained gain ~+4 dB) |
| **L1 ×4 + L2 ×2** | **318** | **22.0%** | partially (retrained on L1 only) |
| L1 ×4 + L2 ×4 | 301 | 26.2% | partially |
| L1 ×4 + L2 ×4 + L3 ×2 | 294 | 28.0% | unclear (L3 not absorbed) |

L2 cranks unlock the bulk of bit savings. The current retrained CNN
WAS trained only on L1 cranks but the multi-level sweep showed it
ALSO closes ~2 dB on L2 distortion — suggesting some generalization.
A CNN explicitly retrained on L1+L2 cranks would do better.

### Pi 5 capture budget at each config (24 fps × 50 MP)

| Config | Frame size | Bandwidth | microSD UHS-I headroom |
|---|---|---|---|
| default | 408 KB | 9.8 MB/s | 7.3× |
| q=11 | 389 KB | 9.3 MB/s | 7.7× |
| L1+L2 ×2 | 318 KB | 7.6 MB/s | 9.4× |
| L1+L2 ×4 | 301 KB | 7.2 MB/s | 10.0× |

All configs fit comfortably on every consumer-class storage tier (UHS-I
microSD sustained = 71.7 MB/s per Pi 5 re-validation today).

### Sustained playback fps (M3 Max + retrained CNN, est.)

All configs land at the same ~26 fps × UHD because the CNN at ~35 ms
is the binding constraint, not the codec. Smaller files don't gain
playback fps; they just reduce storage cost.

## Three ship options

### Option A — Ship q=11 as documented + bundle retrained CNN

**What changes**:
1. Add the retrained checkpoint `BayInBayOut_1x_AAon_w16_ANE_HH1x4.pt`
   to `/Volumes/OWC_8TB/gpr_artifacts/weights/F_ane_1x_weights_metal/`
   as the new default (or rename existing + ship as v2)
2. Update `tools/test/make_gpraw_fixture.sh` to default to q=11 instead
   of letting `bench_fused` use its hardcoded q=3
3. Update `test_capabilities.py` CNN cells to use the retrained ckpt
4. Update `docs/quant_calibration_findings.md` shipping recommendation

**Effect on users**:
- ~5% smaller fixture files
- Same playback fps (CNN-bound)
- CNN-corrected quality matches or slightly exceeds previous default
  on diverse content (per retrained sweep: HH1 4× CNN gain went from
  +0.53 → +5.61 dB, net effect ≈ 0 dB CNN-corrected vs default)

**Effort**: ~2-3 hours of code + tests + verification.
**Risk**: Low — q=11 already shipped and tested; this is just changing
which preset is the default in the fixture pipeline.

### Option B — Add q=12 (L1+L2 cranks) AND ship Option A

**What changes**: everything in Option A plus:
1. Add `quality_tables[12]` to the three quality_table mirrors with
   `{1, 24, 24, 12, 48, 48, 24, 192, 192, 576}` (or `{..., 96, 96, 48,
   192, 192, 576}` for the more-aggressive variant)
2. Bump `VC5_ENCODER_QUALITY_SETTING_COUNT` to 13
3. Add a `VC5_ENCODER_QUALITY_SETTING_CNN_AWARE_AGGRESSIVE` enum entry
4. Retrain BIBO_1x on L1+L2 cranked data (~90 min M5 training)
5. Add q=12 capability cell and CNN cell to test_capabilities

**Effect on users**:
- 22% smaller fixture files
- Same playback fps
- CNN-corrected quality likely within ±1 dB of default with the
  L1+L2-retrained CNN (current retrained CNN closes ~2 dB on L2 alone
  per multi-level sweep, but unvalidated on combined cranks)

**Effort**: ~4-6 hours including the retraining cycle.
**Risk**: Medium — need the L1+L2-retrained CNN to validate, and the
combined-knob CNN-corrected PSNR isn't measured yet on diverse content.

### Option C — Hold both, document only

**What changes**: nothing in the repo. Optionally update
`docs/quant_calibration_findings.md` with the stacked-crank data table.

**Effect on users**: nothing.
**Effort**: ~30 min (doc only).
**Risk**: Zero. Useful if GoPro wants to absorb the findings + design
the production preset themselves.

## My recommendation (when asked)

For a **pre-release exploration aimed at GoPro contribution**: Option C.

Reasoning:
- We are NOT a product. Shipping defaults to actual users isn't the
  goal; demonstrating capability is.
- The methodology + measurements are the contribution. GoPro can pick
  the operating point that matches their product targets.
- Option A or B risks committing to defaults that GoPro then has to
  un-pick. Better to document and let them choose.

For a **product**: Option B. The 22% file size reduction is the
headline number worth shipping; the 5% from q=11 alone is marginal.

For **continued exploration only**: keep going with the M5 retraining
queue. Train a CNN on the L1+L2 cranked distribution. Once that
checkpoint exists, the combined-knob CNN-corrected PSNR sweep validates
the 22% claim. Then Option B becomes data-supported.

## Decision questions for the user

1. Is the current q=11 ship state (shipped preset, retrained ckpt
   exists but not bundled) acceptable as the "snapshot" for GoPro
   handoff?
2. Should we invest the next 2-4 hours in a L1+L2 retrained CNN +
   q=12 preset to take the headline number from 5% → 22%?
3. Are there content classes we haven't tested (portraits, low-light,
   motion blur) that would change the recommendation?
4. Should the retrained checkpoint live in the gpr repo (vs.
   dering_proto_v2/) so it's bundled with the codec spec contribution?
