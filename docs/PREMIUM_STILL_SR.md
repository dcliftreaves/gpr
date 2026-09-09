# Premium Still Super-Resolution

Premium still SR is a separate research workflow that spends additional
desktop processing time on detail, noise behavior, and editing latitude.
It is not a promoted production replacement for the approved offline 4K/8K
raw-video reconstruction.

## Promotion requirements

Evaluate a candidate against the locked still baseline on independent scenes
and the intended camera/resolution range, including 50 MP- and 100 MP-class
sources. Preserve source lineage and avoid train/evaluation scene overlap.

Promotion needs whole-frame raw and rendered comparisons, noise/detail
checks, supported output packaging and metadata, actual editor-openability
and exposure/white-balance latitude review, runtime/memory receipts, model
hashes, and manual visual signoff. Use the existing gate definitions rather
than weakening thresholds to fit a candidate.

A crop win, plausible synthetic high-frequency noise, or a DNG that opens is
not evidence of recovered source signal. Camera-calibration metadata must
carry measured provenance; schema-valid or provisional sidecars alone do
not close the physical calibration requirement.

## Current boundary

Do not infer production approval from archived candidate names or completed
training runs. Model weights and large evaluation sources are external
artifacts; [Reconstruction](RECONSTRUCTION.md) defines their availability
and delivery contract. Optional PSF-conditioned replacements also require
independent promotion evidence.

The experimental queues, candidate results, and machine-specific launch
instructions remain in the
[research and integration archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
[Ship Decision](SHIP_DECISION.md) owns the active product boundary.
