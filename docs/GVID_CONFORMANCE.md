# GVID Conformance

Last refreshed: 2026-06-26

This document defines the `.gvid` conformance surface independently from the
codec-quality gates. The container must be robust even when the payload codec,
CNN, or review renderer changes.

## V1 Wire Contract

| record | size | contract |
|---|---:|---|
| clip header | 32 bytes | little-endian magic `GVID`, version `1`, known flags only, valid pixel format, valid quality, nonzero dimensions, nonzero fps, optional frame-count hint |
| frame header | 16 bytes | little-endian magic `FRM`, nonzero payload size, monotonic `uint64_t` frame tag |
| payload | variable | complete frame payload; v1 conformance does not inspect codec internals |

Strict validation must reject:

- bad clip magic or unsupported version,
- unknown flag bits,
- nonzero reserved fields,
- zero dimensions or zero fps,
- target-bitrate flag mismatch,
- unsupported pixel format or quality,
- truncated clip header,
- truncated frame header,
- truncated frame payload,
- zero-frame streams,
- zero-size frame payloads,
- duplicate or out-of-order frame tags,
- frame-count hint mismatches.

Interrupted-file recovery is valid only when EOF lands after a complete frame
payload. EOF inside a frame header or payload is corruption, not a recoverable
tail.

## Test Layers

| layer | command | purpose |
|---|---|---|
| Python v1 validator | `python3 tools/test/test_gvid_conformance.py` | builds tiny valid and malformed `.gvid` fixtures and verifies accept/reject behavior without project dependencies |
| Labs bundle verifier | `python3 tools/verify_labs_bundle.py <bundle>/manifest.json` | verifies release/Labs bundles, checks hashes, and validates included `.gvid` samples |
| C stream tests | `build/source/app/test_video_format` and related C tests | exercises the C reader/writer contract used by firmware-facing paths |
| Metadata dispatch | `bash tools/test/test_gvid_metadata.sh` | validates `.gvid` metadata sidecars and runtime dispatch checks |
| ProRes review path | `bash tools/test/test_gpr2prores_gvid_input.sh` | proves `.gvid` inputs are accepted by the review/export path and malformed streams fail clearly |
| Codec bitstream conformance | `tests/conformance/` | pins FUSED payload bytes for synthetic raw inputs; this is payload stability, not container conformance |

## Promotion Rule

A `.gvid` change is production-safe only when the container conformance tests,
metadata tests, bundle verifier, C stream tests, and review-path tests still
pass. Intentional wire-format changes require a version bump and a migration
note in `docs/format-spec-v2.md`.

