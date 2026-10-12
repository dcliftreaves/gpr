# Review and Adoption

This contribution is a feature series above GoPro's `446c736` baseline.
Read the commits in order, or select the dependencies for the workflow you
need. The previous development history remains on
`archive/research-and-integration-2026-09-09`; it is not part of this series.

| Commit | Feature | Prerequisites |
|---|---|---|
| `9084a22` | High-bit-depth stills and camera metadata | GoPro baseline |
| `559f9b1` | Reusable fused Bayer codec | Stills/shared codec |
| `e479bdf` | GVID framing and metadata | Fused codec |
| `96e6f1c` | Bounded capture API and simulated source | Codec + GVID |
| `5a93986` | Full-frame native preview | Codec + GVID; no capture API |
| `2a8dec5` | Desktop ProRes and MOV wrappers | Codec + GVID; no capture API or preview |
| `096cbd4` | Optional restoration and reconstruction | Codec + GVID; desktop tools for ProRes |
| Final integration commit | Examples, delivery tools, complete CI, and visual overview | Full suite |

Each feature carries its tests and documentation. Native capture and preview
do not depend on CNN weights. Desktop rendering works with `--no-cnn`;
trained restoration additionally requires the matching external model package.

## Select a Subset

For example, on a new branch based on `446c736`:

```sh
# Stills only:
git cherry-pick 9084a22

# Or, on a separate clean baseline branch: codec + GVID + preview, no capture API.
git cherry-pick 9084a22 559f9b1 e479bdf 5a93986
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
ctest --test-dir build --output-on-failure
BUILD_DIR="$PWD/build" python3 tools/test/test_native_preview.py
```

Do not combine both example cherry-pick sequences on the same branch. The
Python still tests need NumPy, RawPy, and tifffile; the native preview test
uses only the Python standard library and the compiled tools. Desktop
dependencies and smoke tests are in [Renderer Usage](../tools/gpr2prores/USAGE.md).

`bash tools/test/test_feature_adoption.sh` builds and tests preview without the
capture API, then desktop rendering/reconstruction without capture or preview.
It uses disposable worktrees under `TMPDIR`; macOS CI also runs this check.

## What Validation Means

CI checks intermediate builds and synthetic behavior. Pi comparisons use the
same decoded Mission 1 Bayer inputs, codec settings, and reference build;
encoded payload, decoded Bayer, and preview RGB hashes detect changes that a
timing result alone would miss. The helper scripts in `tools/test/compare_*_checkpoints.py`
keep temporary outputs under the configured scratch directory and produce
machine-readable results.

Buffered write throughput, final filesystem flush, and display presentation
are different measurements. The current Pi card is not a verified Lexar
SILVER PLUS, and Pi results do not establish Mission 1 firmware readiness.
Likewise, synthetic model shape/reload tests do not repeat the archived
trained-model quality gates. See [Reconstruction](RECONSTRUCTION.md) for
model availability and [Camera Evaluation](GOPRO_MISSION1_QUICK_VALIDATION.md)
for the hardware handoff.
