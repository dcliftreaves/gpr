# Review and Adoption

The contribution is split into two reviews on this fork:

- `review/product-runtime`, based on GoPro `446c736`: SDK, recording,
  preview, desktop reconstruction, examples, and usage documentation.
- `review/product-validation`, based on the production branch: tests,
  fixtures, diagnostics, quality gates, and hardware validation tooling.

Review and merge production first. Then retarget the validation PR to the
same integration branch; its diff should continue to contain only validation.
Neither PR targets GoPro's repository or changes this fork's `master` merely
by merging into the frozen review baseline.

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
| Final production commit | Packaging, examples, and visual overview | Full suite |

For example, preview without the capture API:

```sh
git switch -c preview-only 446c736
git cherry-pick 95d1a2d b979441 115414b 240c527
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
```

From the validation branch, `bash tools/test/test_feature_adoption.sh`
builds stills alone, preview without capture, and desktop tools without either
camera component, then adds reconstruction. Test drivers are copied into
disposable production worktrees; no runtime implementation is copied from
the testing branch. Temporary data stays under `TMPDIR`.

The eight validation commits correspond to the same eight original feature
groups. Complete CTest wiring and CI are collected in their final integration
commit. See [Testing Methodology](TESTING_METHODOLOGY.md) for the distinction
between synthetic tests, trained-model gates, and actual hardware evidence.

The unsplit review remains at `review/human-feature-series` (`1553708`), and
older experiments remain on `archive/research-and-integration-2026-09-09`.
