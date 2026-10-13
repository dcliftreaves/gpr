# Review and Adoption

Review aid only, not product status or a final merge topology. The contribution
was split into two reviews on this fork:

- `review/product-runtime`, based on GoPro `446c736`: SDK, recording,
  preview, desktop reconstruction, examples, and usage documentation.
- `review/product-validation`, based on the production branch: tests,
  fixtures, diagnostics, quality gates, and hardware validation tooling.

Review and merge production first. Then retarget the validation PR to the
same integration branch; its diff should continue to contain only validation.
Confirm the current PR base and diff before merging; branch tips and commit
maps may change during cleanup.

## Production Features

| Commit | Feature | Prerequisites |
|---|---|---|
| `95d1a2d` | High-bit-depth stills and metadata | GoPro baseline |
| `b979441` | Fused Bayer codec | Stills/shared codec |
| `115414b` | GVID framing and recording | Fused codec |
| `db0ddb8` | Bounded capture API | Codec + GVID |
| `240c527` | Native preview | Codec + GVID; no capture API |
| `8e5f724` | ProRes and MOV wrappers | Codec + GVID; no camera components |
| `cd04508` | Restoration and reconstruction | Codec + GVID; desktop tools for ProRes |
| Integration layer (inspect current tip) | Packaging, examples, and visual overview | Full suite |

For example, preview without the capture API:

```sh
git switch -c preview-only 446c736
git cherry-pick 95d1a2d b979441 115414b 240c527
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
```

From the validation branch, `bash tools/test/test_feature_adoption.sh`
builds stills alone, preview without capture, and desktop tools without either
camera component, then adds reconstruction. Historical desktop and model
drivers are pinned to the archive revision matching those checkpoints;
current interoperability and inference tests run separately on the full tree.
Test drivers are copied into
disposable production worktrees; no runtime implementation is copied from
the testing branch. Temporary data stays under `TMPDIR`.

The commit map above identifies the original split, not a claim that its
hashes describe a future rewritten series. Check the adoption driver's pinned
revisions before using it to evaluate a new series.
See [Testing Methodology](TESTING_METHODOLOGY.md) for the distinction
between synthetic tests, trained-model gates, and actual hardware evidence.

The unsplit review remains at `archive/review/human-feature-series` (`1553708`), and
older experiments remain on `archive/research-and-integration-2026-09-09`.

## Feature Cohesion

The pre-cleanup tree is preserved at
`archive/before-feature-cohesion-2026-10-13` (`a956fcd`).

| Area | Current disposition | Verification boundary |
|---|---|---|
| Still SDK, metadata and high-bit-depth Bayer | Production | Synthetic roundtrips and metadata tests; camera corpus is separate |
| Fused codec, GVID, capture and native preview | Production | Native, container and source-simulator tests; no Mission 1 firmware claim |
| Selected restoration and SR | Production inference helpers separated from training/benchmark names | Synthetic model contracts do not replace approved checkpoint gates |
| MOV and ProRes | Production; portable reader shared by both frontends | Cross-frontend payload tests and macOS rendering |
| FFmpeg decoder | Retained optional integration pinned to FFmpeg n8.0 | Fresh Bayer encode, MOV wrap, native-vs-FFmpeg decode, image/ProRes export and malformed headers |
| Standalone CoreML polish API | Archived; no selected model or production caller | Removed rather than implying its availability test exercised inference |
| Minimal fast TIFF still writer | Archived; the retired switch warns and uses the SDK writer | SDK readback regression; separate fast decoder retained |
| Detail-residual sidecar experiment | Validation only | Not part of selected GVID or reconstruction formats |

`tools/test/audit_feature_coverage.py` inventories changed source against exact
commits. LinuxRelease collects native and Python execution coverage in the
existing CI job and uploads `coverage/feature-coverage.json`. Static caller
references are hints, not execution evidence. Uninstrumented backends remain
UNKNOWN; zero coverage is a reason to investigate, not automatic permission to
delete a public API. Instrumented timings are not performance receipts.
