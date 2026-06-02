# Training corpus expansion — closing the OOD PREVIEW gap

**Status:** PLAN + first batch landed (2026-05-28). Hand-off doc for future
retrain runs. Companion to `docs/BIDO_DISTILLATION_PLAN.md` §8.

## Why this exists

Phase B distillation FAILed PREVIEW gate at worst LPIPS 0.4919 (Z8Z_6693, hair/skin
session content). Plan §8's contingency clause applies: `worst LPIPS > 0.30 → the
325K-param architecture cannot represent the texture distribution`. Both Phase A
(LPIPS fine-tune) and Phase B (Restormer distillation) confirmed that **loss
engineering alone won't close the gap on out-of-distribution content** the model
has never seen.

The fix is data, not architecture. The current training corpus has 0 source DNGs
from the 2025-04-20 session (hair/skin portraits, sub-mm subject detail, complex
specular highlights). Z8Z_6693 lives there. The model has nothing to learn from.

## What's in scope

This doc covers DATA selection and conversion for the next training run. It does
NOT cover the training itself (that's a separate session triggered when a fresh
training is dispatched).

## Inventory found

`/Volumes/photos/DavidsPics/2025/` has **7,164 NEFs** across 26 dated sessions in
2025 alone. Gate test images traced to specific sessions:

| Gate image | Session(s) where the .NEF exists | Content class |
|---|---|---|
| Z8Z_0067 | 2025-07-25 or 2025-09-02 (filename collision) | smooth-gradient (skin/sky) — IN domain |
| Z8Z_0001 | 2025-07-25, 2025-07-26, or 2025-09-01 (collision) | high-frequency texture |
| Z8Z_5323 | 2025-01-30 | high-saturation texture |
| **Z8Z_6693** | **2025-04-20** | **hair/skin OOD — gate WORST** |

## Selected first batch — same-session as the gate worst

The **2025-04-20 session has 78 NEFs total** (Z8Z_6693.NEF through Z8Z_6770.NEF).
Same-session = same lighting + same subject + same lens + same content
distribution as the gate worst image. Highest expected ΔLPIPS-per-DNG of any
batch we can construct.

Converted and staged via Adobe DNG Converter at:

```
/Volumes/OWC_8TB/gpr_work/cnn/ood_dngs_2025-04-20/
```

(78 DNGs, ~4 GB total. Adobe DNG Converter `-c` for compressed.)

## Recommended next batches (NOT YET CONVERTED)

To complete the texture-coverage gap, additionally sample from these sessions:

| Session | NEF range | Why include |
|---|---|---|
| 2025-01-30 | Z8Z_5323..5537 (215 NEFs) | Z8Z_5323 distribution (saturation textures) |
| 2025-07-25 | Z8Z_0001..0767 (767 NEFs) | Z8Z_0067 / Z8Z_0001 collision-set context |
| 2025-09-01 | Z8Z_0001..0065 | Z8Z_0001 collision-set context |

Total candidate budget: **78 (done) + ~100 (recommended sampling)** = ~180 source
DNGs added on top of the existing ~498 (barnsky + diverse). The training cost
scales linearly; the corpus would be ~36% larger.

## Conversion command (Adobe DNG Converter CLI)

```
/Applications/Adobe\ DNG\ Converter.app/Contents/MacOS/Adobe\ DNG\ Converter \
    -c -d <out_dir> <input_file_or_glob>
```

- `-c` = compressed DNG (default; smaller files)
- `-d` = output directory
- Conversion rate ~1-2 s/file on Mac M3 Max

## Why NEF doesn't work directly

The existing `tools/cnn/build_dataset_*.py` pipelines call `test_fused_roundtrip`
which reads via the Adobe DNG SDK. That SDK CAN read NEF in principle, but the
GPR build pipeline writes its codec-roundtrip output back into the DNG container,
which requires a DNG-shaped input first. Easier to pre-convert than to bend the
build pipeline.

Also: `rawpy.imread()` on Z8 NEFs fails with `LibRawFileUnsupportedError` on the
current `rawpy` version. Adobe DNG Converter is the load-bearing tool.

## Wiring the new DNGs into a training run

When a future session retrains BIDO (or a sibling CNN) against this expanded
corpus:

1. Edit `tools/cnn/build_dataset_<codec>.py` to add the new DNG dir:
   ```python
   DNG_DIRS = [
       "/Volumes/OWC_8TB/gpr_work/barnsky_full_dngs",
       "/Volumes/OWC_8TB/gpr_work/cnn/diverse_dngs",
       "/Volumes/OWC_8TB/gpr_work/cnn/ood_dngs_2025-04-20",   # ← new
   ]
   ```
2. Rebuild the codec-pair set + tile NPZ.
3. Retrain from scratch (do NOT init from Phase A's checkpoint — that converged
   to the wrong distribution).
4. Gate per `BIDO_DISTILLATION_PLAN.md` §7.16.

## What this is NOT

- It is not a substitute for the cranked-CNN retrain on the broader corpus —
  that's tracked separately as task #5.
- It is not the higher-capacity (w24/w32) architecture test — that's task #4.
- It is not a guarantee Phase B will pass with the new data. The actual EV
  test is the gate run after retraining. If still > 0.30 worst LPIPS, the next
  hypothesis is architecture, then ensembling, then conceding the path.

## TODO once the running #4 + #5 subagents finish

- Run a fresh BIDO_4x training using `ood_dngs_2025-04-20` + existing corpus.
- Compare gate verdict against Phase B's FAIL baseline (worst LPIPS 0.4919).
- If passes PREVIEW → log via `--claim` and ship.
- If still fails → escalate to corpus + architecture jointly.
