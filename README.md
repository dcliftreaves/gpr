# Early GPR Codec Prototype Archive

Historical source snapshot from the standalone `decr-gpror` workspace,
preserved on September 9, 2026. This is not the supported product branch and
is not intended to be merged into it.

The prototype explored 16-bit Bayer support, quality presets, ARM NEON
acceleration, entropy decoding, and DNG metadata round trips. Several of these
ideas have since been incorporated into the current
[GPR fork](https://github.com/dcliftreaves/gpr).

## Preserved

- The complete working source tree and CMake build definition, including all
  14 locally modified source files.
- Small synthetic Bayer generation, patch extraction, and difference scripts
  in `tools/`.
- The previously untracked [quality analysis](docs/quality-analysis.md).
  Its measurements and interpretations are historical and unvalidated here;
  they are not current product claims or quality gates.
- Original license and attribution files.

The original local repository had no remote. Its two commits were
`9c831e9` (16-bit support and NEON) and `d5d69bc` (entropy decoding and metadata),
both dated February 11, 2026. This snapshot includes the subsequent uncommitted
working changes; those old commit IDs describe provenance, not reachable
commits in this source-only archive.

Photos, generated RAW/GPR outputs, compiled binaries, environments, caches,
and the old binary-heavy Git object database are deliberately excluded.
The original working directory is not required to inspect this branch.

## Historical Build

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
```

This archive has not been requalified for current compilers, platforms, or
camera firmware. Use the product branch for supported builds and tests.
