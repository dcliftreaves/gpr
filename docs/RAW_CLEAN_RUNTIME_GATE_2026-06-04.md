# Raw Clean Runtime Gate Audit

Date: 2026-06-04

This pass tests whether the raw clean/addback dispatch label can be recovered
from decoded `ml2_q3_dec2` codec input at restore time. It cannot, at least not
with the current source-raw acceptance contract applied directly to
decoded/upsampled codec crops.

Artifacts:

- Full-gate runtime gate dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/runtime_gate_w64/codec_raw_clean_runtime_gate.html`
- Full-gate runtime gate JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_train_20260604/runtime_gate_w64/codec_raw_clean_runtime_gate.json`
- Preview-holdout codec pairs:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_preview_holdout_20260604/ml2_q3_dec2_raw_clean_pairs_preview_holdout.npz`
- Preview-holdout runtime gate dashboard:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_preview_holdout_20260604/runtime_gate/codec_raw_clean_runtime_gate.html`
- Preview-holdout runtime gate JSON:
  `/Volumes/OWC_8TB/gpr_work/artifacts/codec_raw_clean_pairs_preview_holdout_20260604/runtime_gate/codec_raw_clean_runtime_gate.json`

## Method

`tools/cnn/evaluate_codec_raw_clean_runtime_gate.py`:

1. Loads codec-input raw clean pairs.
2. Upsamples decoded half-res `ml2_q3_dec2` Bayer planes to target resolution.
3. Recomputes the same residual contract used by the source-raw clean target
   builder.
4. Compares runtime acceptance against the sidecar/source-raw acceptance label.

This is an intentionally strict test: it asks whether the existing source-raw
acceptance logic can be reused after codec decode without a new classifier or
metadata path.

## Results

Full frozen gate:

| Rows | Matches | TP | TN | FP | FN |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 12 | 6 | 0 | 6 | 0 | 6 |

Preview holdout:

| Rows | Matches | TP | TN | FP | FN |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 84 | 77 | 0 | 77 | 1 | 6 |

The failure is asymmetric:

- negatives are mostly preserved;
- every sidecar-accepted positive becomes a runtime false negative;
- the decoded/upsampled codec input has high same-plane lag on accepted
  high-ISO crops, so the source-raw contract rejects it.

Full-gate accepted false negatives:

| Image | Crop | ISO | Runtime reasons | Runtime lag | Runtime edge ratio |
| --- | --- | ---: | --- | ---: | ---: |
| `Z8Z_5323` | `A_detail` | 5000 | `lag` | 0.571 | 0.890 |
| `Z8Z_5323` | `B_center` | 5000 | `lag` | 0.553 | 0.882 |
| `Z8Z_5323` | `C_lowerleft` | 5000 | `lag, edge_ratio` | 0.592 | 1.176 |
| `Z8Z_6693` | `A_detail` | 9000 | `lag, edge_ratio` | 0.543 | 1.290 |
| `Z8Z_6693` | `B_center` | 9000 | `lag` | 0.568 | 0.985 |
| `Z8Z_6693` | `C_lowerleft` | 9000 | `lag, edge_ratio` | 0.583 | 1.057 |

Preview-holdout accepted false negatives show the same lag failure on the
accepted ISO 500, 4000, and 25600 crops.

## Production Implication

The oracle dispatch from `docs/CODEC_RAW_CLEAN_DISPATCH_2026-06-04.md` should
not be implemented by recomputing the current acceptance contract after decode.
The decoded path has codec/interpolation structure that makes the contract too
conservative for the exact high-ISO cases where noise removal is useful.

The next production design should compute acceptance/noise-level metadata on
the source raw path before or during encode, then carry that metadata through
the `.gvid` frame/tile stream. Decode-time restoration can then use:

- source-side acceptance/noise metadata for dispatch;
- all-target model on no-op/unsafe tiles;
- accepted-only high-ISO model on accepted noise-removal tiles;
- exact residual addback for visual equivalence scoring during validation;
- synthetic noise addback only after it is separately validated.
