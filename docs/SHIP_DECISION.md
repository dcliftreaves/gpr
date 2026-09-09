# Ship Decision

## Approved scope

| Workflow | Decision |
|---|---|
| Raw stills | Legacy VC5 q0 smallest and q3 primary with the matched still CNN; q8 archival without CNN |
| Native 4K raw-video capture | Pi 5 stand-in evidence clears the accepted 20+ fps floor; actual Mission 1 camera production remains open |
| Camera-back preview | Full-frame 1024 x 768 RGB from the same 4096 x 3072 stream; no camera-side CNN |
| Raw-video reconstruction | Approved offline 4K cleanup and 8K SR, with editable DNG/GPR and ProRes review evidence |
| Premium still SR | Separate research; no production promotion inferred from video approval |

The FUSED encoder serves video. The legacy VC5 encoder serves the approved
still tiers. Do not transfer quality claims between encoder families or
between source-resolution, decimated, and reconstructed workflows.

## Audited quality evidence

[claims_log.md](claims_log.md) preserves the machine-written signoffs.
The corresponding `tests/quality_gates/runs/<hash>/run.json` is the receipt;
`tests/quality_gates/gates.json` defines the actual class thresholds.
This cleanup neither reruns quality gates nor changes thresholds or signoffs.

| Existing still signoff | Run hash | Recorded worst LPIPS |
|---|---|---:|
| q0 plus matched still CNN | `54f001717c547574` | 0.0314 |
| q3 plus matched still CNN | `b44fa841c05c9bff` | 0.0155 |
| q8 without CNN | `9837b797660627aa` | 0.0035 |

These are bounded test-set results, not universal quality guarantees.
VIDEO_FREEZE and historical UPRESABLE signoffs remain in the same ledger.
The latter gates editable raw using Bayer PSNR; its recorded rendered LPIPS
is not a finished-render approval. Historical desktop full-resolution
VIDEO_FREEZE results do not establish embedded capture throughput.

## Promotion and release rules

The approved raw-video reconstruction baseline is frozen. Reopen it when a
locked gate, receipt, artifact hash, CI guard, or manual review fails, or when
a replacement already beats the baseline with equivalent quality, timing,
memory, packaging, review, and hash evidence. Optional PSF/blur modeling is
future research, not a requirement for the approved baseline.

Premium still SR needs its own detail, noise, metadata, and editor-latitude
evidence. A synthetic noise texture, crop-only win, or output file that opens
does not establish restored source detail or editing latitude.

A camera-ready claim additionally requires actual sensor/DMA, storage, and
display execution at the accepted floor with zero drops, a valid stream,
and recovery proof. [Video Status](VIDEO_STATUS.md) records the narrower
stand-in evidence; [Release Artifacts](RELEASE_ARTIFACTS.md) defines delivery.

Detailed older matrices and decisions remain in the
[archive](https://github.com/dcliftreaves/gpr/tree/archive/research-and-integration-2026-09-09),
pinned at [`3d675ef`](https://github.com/dcliftreaves/gpr/tree/3d675ef).
