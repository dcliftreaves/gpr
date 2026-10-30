# Stock UPRESABLE workflow

`stock_upres.py` recreates the applicable timelapse, regression and combined
orchestration from the original feature branch using the stock encoder.
It requires an explicit 2x checkpoint and two explicit stock presets. It does
not select, download or approve weights. Python NumPy, tifffile and Torch are
optional workflow dependencies; native capture does not depend on them.

For each ordered input, the workflow checks the source calibration and count
domain, independently checks lossless DNG pixels against SDK decoding, averages
2x2 samples at each Bayer site to simulate half-resolution capture, encodes and
decodes that capture through stock VC-5, runs the selected 2x CNN, and encodes a
full-resolution stock GPR. The model loads once per invocation. A camera GPR
replay can instead be declared explicitly; it is not sensor ground truth.

```sh
python tools/stock_upres.py --mode both \
  --input frame001.dng --input frame002.dng \
  --reference held-out.dng --reference-kind lossless_sensor_dng \
  --checkpoint selected-2x.pt --sdk build-runtime/source/app/gpr_tools/gpr_tools \
  --capture-quality 3 --output-quality 5 --bridge build-mov/gpr_mov \
  --output-dir new-run --dng-export
```

`timelapse` requires ordered `--input` paths and the native MOV bridge;
`regression` requires `--reference` paths. `both` runs both lists. Outputs are
placed in a new directory, with per-frame stock encoding/decoding receipts and
a `run.json` manifest. A failed run retains completed work, records the error,
and keeps `complete` false. Existing output directories are refused.

The primary timelapse outputs are `timelapse.gvid` and `timelapse.mov`.
`stock_sequence.py` copies each full-resolution GPR payload without another
encode, preserving per-frame typed calibration. A matching stock encoding
receipt is required for each input to bind the advertised preset, count domain,
metadata and payload. GVID framing, CRCs and END3 are verified before publication;
the MOV wrapper independently verifies exact GVID recovery. Timestamps are
explicitly synthetic, at the requested `--fps-num`/`--fps-den` rate.

`--dng-export` keeps both `model-output.dng` (exact CNN counts) and
`decoded-full.dng` (decoded final GPR counts). These can differ because stock
GPR re-encoding is lossy. Regression reports compare bicubic, model output and
final GPR output against the same reference, including active-area, detail,
shadow, highlight and per-site errors. Re-encoding loss is reported separately.
Every report retains `quality_approval: false`; passing a workflow test does
not approve a model or a visual size/quality tier.

Optional calibrated deep ProRes uses the existing macOS renderer and encoder:

```sh
# Add to a timelapse/both invocation:
--prores --prores-decoder build-runtime/source/app/stock_video/stock_video \
  --prores-renderer build-runtime/gpr_render \
  --prores-encoder build-runtime/gpr_prores --prores-probe /path/to/ffprobe
```

That export renders the final GPR-derived frames without a second CNN pass.
It remains a distinct calibrated rendering path rather than a Bayer master.

Current scope requires RGGB14, source dimensions divisible by four, and at
least 96x96. Simulation rejects nonempty stage-1/2 opcodes, black-level delta
arrays and unrepresentable spatial calibration; opaque XMP is omitted with
accounting. Timelapse additionally requires full dimensions divisible by eight
and at most 8192x6144. The original 8280-wide Nikon still references can be
evaluated in regression mode but cannot be silently cropped into this video
profile. Native CoreML/Metal, physical sensor capture, temporal model approval
and automatic checkpoint selection remain separate work.

Validation: `tests/stock_sequence_test.py` checks exact payloads/calibration,
rational timestamps, native MOV round-trip and mismatched receipt/geometry
rejection. `tests/stock_upres_test.py` exercises all three modes with a
deterministic zero-residual 2x checkpoint, verifies bicubic equivalence, source
identity, DNG calibration, final payload identity, non-overwrite and failed-run
accounting. Mac additionally exercises calibrated ProRes. Revision-bound
receipts are in `stock-upres-receipts/`; these are synthetic functional tests,
not real-scene quality or 12 MP throughput evidence.
