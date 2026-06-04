# GVID Source Metadata Sidecar

Date: 2026-06-04

The raw-clean runtime-gate audit showed that decoded `ml2_q3_dec2` input cannot
reliably recover the source-side acceptance labels. The current `.gvid` v1
frame header has no room for per-tile acceptance/noise metadata, and embedding
that data in-stream would be a structural format change. For now, production
work should use a validated companion sidecar while a deliberate `.gvid` v2
metadata chunk is designed.

## Schema

`tools/gvid_metadata.py` defines `gvid_source_metadata.v1`.

The sidecar records:

- frame index and frame tag;
- source frame id/path and ISO;
- per-crop/tile source coordinates;
- source-side raw-clean acceptance;
- reject reasons and noise guardrail metrics.

This is intentionally source metadata. It is computed before or during encode,
not inferred after decode.

## Generated Artifacts

Full gate:

`/Volumes/OWC_8TB/gpr_work/artifacts/gvid_source_metadata_20260604/full_gate.gvid.meta.json`

- 4 frames.
- 12 tiles.
- 6 accepted tiles.

Preview holdout:

`/Volumes/OWC_8TB/gpr_work/artifacts/gvid_source_metadata_20260604/preview_holdout.gvid.meta.json`

- 28 frames.
- 84 tiles.
- 6 accepted tiles.

Both sidecars validate with:

```bash
python3 tools/gvid_metadata.py validate <sidecar>
```

Runtime dispatch plans are generated with:

```bash
python3 tools/gvid_metadata.py runtime-dispatch <sidecar> \
  --gvid <stream.gvid> \
  --output <stream.gvid.dispatch.json>
```

The dispatch plan scans actual `.gvid` frame headers, matches each decoded frame
by `frame_tag`, carries payload offset/size for readers, and emits per-tile
policy values:

- `accepted_only_raw_clean` for accepted source tiles;
- `all_targets_raw_clean` for rejected/no-op source tiles.

## Compatibility

This does not change `.gvid` v1 binary layout. Existing `.gvid` readers can
ignore the sidecar. Decode-time restoration that wants raw-clean dispatch can
load the runtime dispatch plan and select:

- all-target model for rejected/no-op tiles;
- accepted-only high-ISO model for accepted tiles.

If this metadata must become self-contained in the stream, that should be a
`.gvid` v2 design because v1 has only fixed 16-byte frame headers and no
generic metadata chunk.

## Verification

- `python3 -m py_compile tools/gvid_metadata.py`
- Full-gate sidecar generation and validation.
- Preview-holdout sidecar generation and validation.
- `WORK=/Volumes/OWC_8TB/gpr_work/tmp/gvid_metadata_smoke bash tools/test/test_gvid_metadata.sh`
