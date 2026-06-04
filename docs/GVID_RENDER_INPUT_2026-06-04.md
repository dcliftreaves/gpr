# GVID Render Input

Date: 2026-06-04

This pass makes `.gvid` a direct `gpr2prores` input. The renderer now
auto-unpacks the neutral stream into a temporary `.gpr` frame directory and
then reuses the existing playback pipeline.

## Behavior

- `.gvid` is accepted as an input format by `tools/gpr2prores/gpr2prores`.
- The unpacker validates:
  - clip magic and version;
  - frame magic;
  - payload truncation;
  - `frame_count_hint`;
  - duplicate frame tags.
- Unpacked frame names preserve stream order:
  `frame_<stream_index>.gpr`.
- `TMPDIR` is honored explicitly, so callers can keep unpack scratch on
  `/Volumes/OWC_8TB/gpr_work/tmp`.
- GPRaw/MOV auto-unpack now uses the same `TMPDIR` helper instead of a
  hard-coded `/tmp` path.
- `--gvid-dispatch <plan.json>` validates a `gvid_runtime_dispatch.v1`
  plan against the frames being rendered and prints per-policy tile counts.
  This is a strict handoff check; per-tile raw-clean model invocation is not
  wired into `GPRPipeline` yet.

## Local Smoke

Input:

`/Volumes/OWC_8TB/gpr_work/artifacts/upresable/halfres/Z8Z_0258.gpr`

Packed into:

`/Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/oneframe.gvid`

Phase-0 proof:

```sh
TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/tmp \
  tools/gpr2prores/gpr2prores \
  --phase0 --no-cnn \
  --gvid-dispatch /Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/oneframe.gvid.dispatch.json \
  --meta-dng /Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng/Z8Z_0258.dng \
  /Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/oneframe.gvid \
  /Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/out.mov
```

Result:

- `.gvid` unpacked under the external `TMPDIR`.
- Dispatch plan validated with one `accepted_only_raw_clean` tile and one
  `all_targets_raw_clean` tile.
- Phase 0 saw a valid FUSED frame:
  `magic=0x44535546`, `w=8280`, `h=5520`, `decimate=2`.

Rendered-output proof:

```sh
TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/tmp \
  tools/gpr2prores/gpr2prores \
  --max-frames 1 --no-cnn \
  --demosaic core-image --out-resolution 2k \
  --gvid-dispatch /Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/oneframe.gvid.dispatch.json \
  --meta-dng /Volumes/OWC_8TB/gpr_work/artifacts/upresable/editable_dng/Z8Z_0258.dng \
  /Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/oneframe.gvid \
  /Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/out_2k.mov
```

Result:

- Output: `/Volumes/OWC_8TB/gpr_work/tmp/gpr2prores_gvid_smoke/out_2k.mov`
- Size: 1.2 MB
- Render: `8280x5520 -> decode 4140x2760 -> ProRes 2048x1364`
- One-frame wall result: `total=0.2s`, effective about `6 fps`
- Per-frame pipeline total: about `95-106 ms` across local smoke runs

Negative proof:

- A `.gvid` patched with duplicate frame tag `0` is rejected with
  `duplicate GVID frame tag 0`.

Scripted local smoke:

```sh
bash tools/test/test_gpr2prores_gvid_input.sh
```

## Remaining Production Handoff

This makes the container renderable and validates the runtime dispatch handoff.
It does not yet apply `gvid_runtime_dispatch.v1` per-tile raw-clean model
selection inside `GPRPipeline`; that remains the next renderer integration
point.
