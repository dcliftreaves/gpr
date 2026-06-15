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
| target.name | hardware used for capture bench; Pi 5 is allowed only as stand-in |
| notes | non-empty explicit gaps, especially if not actual camera hardware |
| artifacts | single list of files with `path`, `kind`, `size_bytes`, and `sha256` |

The verifier requires the `artifacts` list to include at least one
`samples/*.gvid` artifact, one `samples/` artifact, one `receipts/` artifact,
one `review/` or `dashboard` artifact, and `hashes/sha256sums.txt`.

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
the bundle verifier with a tiny synthetic `.gvid`, including checksum mismatch,
bad GitHub Actions run URL, missing `target.name`, missing `notes`, missing
receipt coverage, and zero-frame `.gvid` rejection. The C stream validator is
exercised by `source/app/test_video_format.c` and
`source/app/test_video_full_chain.c`, including malformed headers, truncated
frame headers/payloads, frame-count hint mismatches, duplicate or out-of-order
frame tags, oversized payloads, and zero-frame streams.

## Current Bundle

Current stand-in bundle:

`/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json`

Verification:

```bash
python3 tools/verify_labs_bundle.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json
```

Contents:

- UPRESABLE `.gvid` sample;
- MOV compatibility wrapper;
- ProRes review MOV;
- Pi 5 120-frame stand-in timing receipt;
- preview review dashboard;
- checksums and CI/run receipt.

This bundle is enough for source/media review. It is **not** final
camera-firmware evidence because the target bench receipt is a 120-frame Pi 5
stand-in run, not a 10 minute camera-firmware capture.
