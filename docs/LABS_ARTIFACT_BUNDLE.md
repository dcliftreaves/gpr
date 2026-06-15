# Labs Artifact Bundle

Last refreshed: 2026-06-15

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
(cd /path/to/gpr_labs_bundle && sha256sum -c hashes/sha256sums.txt)
python3 tools/gvid_metadata.py validate \
  samples/half_res_capture.gvid.meta.json \
  --gvid samples/half_res_capture.gvid
python3 tools/gvid_metadata.py runtime-dispatch \
  samples/half_res_capture.gvid.meta.json \
  --gvid samples/half_res_capture.gvid \
  --output "${TMPDIR:-/tmp}/half_res_capture.dispatch.json"
python3 tools/verify_labs_bundle.py manifest.json
```

Build or refresh a bundle manifest from explicit bundle-relative files:

```bash
python3 tools/build_labs_bundle.py /path/to/gpr_labs_bundle \
  --repo-commit "$(git rev-parse HEAD)" \
  --ci-run "https://github.com/dcliftreaves/gpr/actions/runs/<run-id>" \
  --target-name "Pi 5 stand-in" \
  --target-role "stand-in" \
  --note "Pi 5 proxy evidence; actual Mission 1 24 fps receipt pending" \
  --artifact samples/half_res_capture.gvid:gvid \
  --artifact samples/half_res_capture.gvid.meta.json:json \
  --artifact review/preview_review_dashboard.html:dashboard \
  --artifact receipts/pi5_capture_bench.json:json
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

Current source/media stand-in bundle:

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

Current target-proxy bundle:

`/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/manifest.json`

Verification:

```bash
python3 tools/verify_labs_bundle.py \
  /Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/manifest.json
```

Primary target-proxy receipt:

`/Volumes/OWC_8TB/gpr_work/artifacts/labs_target_bench_pi5_20260615_0dd6660/labs_target_bench.json`

Normalized camera-handoff receipt:

`/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260615_pi_proxy_v1/receipts/pi5_proxy_camera_handoff_receipt.json`

This receipt validates 14,400 frames, 0 drops, `.gvid`, and interrupted-tail
recovery at 19.98 fps median. It is acceptable as a conservative Pi 5 proxy for
continuing Labs integration, but it must be replaced or supplemented by an
actual Mission 1 24 fps hardware receipt before firmware readiness is claimed.
