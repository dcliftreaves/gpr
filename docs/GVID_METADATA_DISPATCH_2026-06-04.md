# GVID Metadata Dispatch

Date: 2026-06-04

This pass turns the raw-clean source metadata sidecar into an operational part
of the `.gvid` workflow.

## What Changed

- `tools/gvid_pack.py` can now take `--metadata <sidecar>`.
- The packer validates the sidecar against the actual packed `.gvid` frame tags.
- Metadata-backed packs stage through a temporary stream first, so a failed
  metadata attach does not leave a final `.gvid` deliverable behind.
- When validation passes, the sidecar is copied beside the stream as
  `<output>.meta.json`, or to `--metadata-output`. The copied JSON normalizes
  its `gvid` field to the attached stream path.
- `tools/cnn/build_codec_raw_clean_dispatch_dashboard.py` can now take
  `--metadata <sidecar>` and select accepted-only vs all-target raw-clean
  models from `gvid_source_metadata.v1`, keyed by `(source_id, crop)`.

The dispatch dashboard still keeps the previous dashboard-oracle mode when no
metadata is supplied. In metadata mode it fails on missing, extra, or duplicate
metadata tiles.

## Full-Gate Metadata Dispatch

Command:

```sh
python3 tools/cnn/build_codec_raw_clean_dispatch_dashboard.py \
  --metadata /Volumes/OWC_8TB/gpr_work/artifacts/gvid_source_metadata_20260604/full_gate.gvid.meta.json \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/dispatch_comparison_w64_metadata
```

Artifacts:

- `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/dispatch_comparison_w64_metadata/codec_raw_clean_dispatch_dashboard.html`
- `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/dispatch_comparison_w64_metadata/codec_raw_clean_dispatch_dashboard.json`

Metrics:

| Candidate | Mean clean RMSE | Accepted mean | Rejected mean |
| --- | ---: | ---: | ---: |
| metadata dispatch | 38.3076 | 26.6221 | 49.9931 |

This matches the earlier oracle dispatch result because the sidecar was built
from the same raw-clean target contract. The important change is that the policy
now consumes the same sidecar that travels with the stream.

## Verification

```sh
python3 -m py_compile \
  tools/gvid_pack.py \
  tools/gvid_metadata.py \
  tools/cnn/build_codec_raw_clean_dispatch_dashboard.py

WORK=/Volumes/OWC_8TB/gpr_work/tmp/gvid_pack_smoke \
  bash tools/test/test_gvid_pack.sh

WORK=/Volumes/OWC_8TB/gpr_work/tmp/gvid_metadata_smoke \
  bash tools/test/test_gvid_metadata.sh
```

All focused checks passed.

Runtime dispatch plan smoke:

`/Volumes/OWC_8TB/gpr_work/artifacts/gvid_runtime_dispatch_20260604/full_gate_synthetic.gvid.dispatch.json`

- synthetic `.gvid`: 4 frames, matching full-gate metadata frame tags;
- dispatch plan: 4 frames, 12 tiles, 6 accepted tiles;
- each plan row carries stream payload offset/size plus per-tile
  `accepted_only_raw_clean` or `all_targets_raw_clean` policy.

## Renderer Handoff Status

The next renderer pass landed in
[`docs/GVID_RENDER_INPUT_2026-06-04.md`](GVID_RENDER_INPUT_2026-06-04.md):
`gpr2prores` accepts `.gvid` directly, unpacks frames under `TMPDIR`, and
validates a `gvid_runtime_dispatch.v1` plan against the actual stream headers
before render. The scripted smoke for that handoff is
`tools/test/test_gpr2prores_gvid_input.sh`.

Per-tile raw-clean model selection inside `GPRPipeline` is still intentionally
not claimed here. The production container claim is the neutral `.gvid` stream,
metadata sidecar validation, direct render input, dispatch-plan validation, and
the documented handoff point for future per-tile model invocation.
