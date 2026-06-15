# Labs Artifact Bundle

Last refreshed: 2026-06-14

This defines the portable review bundle for a Labs prototype intake. Large media
must stay outside git; the repo should carry the manifest, scripts, hashes, and
small receipts needed to verify the bundle on a fresh machine.

## Bundle Layout

```text
gpr_labs_bundle/
  manifest.json
  README.md
  samples/
    half_res_capture.gvid
    half_res_capture.gvid.meta.json
    half_res_capture.gvid.dispatch.json
  review/
    half_res_capture_prores.mov
    dashboard/
  receipts/
    pi5_capture_bench.json
    mac_decode_export_bench.json
    gvid_validate.txt
    ci_run.txt
  hashes/
    sha256sums.txt
```

## Required Manifest Fields

| field | requirement |
|---|---|
| schema | `gpr_labs_bundle.v1` |
| repo_commit | commit that produced or verified the bundle |
| ci_run | GitHub Actions run URL for the commit |
| samples | list of media files with size and SHA-256 |
| receipts | list of bench/validation receipts with size and SHA-256 |
| target | hardware used for capture bench; Pi 5 is allowed only as stand-in |
| notes | explicit gaps, especially if not actual camera hardware |

## Verification Commands

```bash
sha256sum -c hashes/sha256sums.txt
python3 tools/gvid_metadata.py validate \
  samples/half_res_capture.gvid.meta.json \
  --gvid samples/half_res_capture.gvid
python3 tools/gvid_metadata.py runtime-dispatch \
  samples/half_res_capture.gvid.meta.json \
  --gvid samples/half_res_capture.gvid \
  --output "${TMPDIR:-/tmp}/half_res_capture.dispatch.json"
python3 tools/verify_labs_bundle.py manifest.json
```

For repo-local validation, `tools/test/test_labs_bundle_verify.sh` exercises
the bundle verifier with a tiny synthetic `.gvid`. The C stream validator is
exercised by `source/app/test_video_format.c` and
`source/app/test_video_full_chain.c`.

## Current Status

Not complete. The repo has the `.gvid` tools, metadata validation, and CI source
checks. It still needs a portable bundle directory with real sample media,
checksums, target bench receipts, and review outputs copied out of the local
8TB artifact tree.
