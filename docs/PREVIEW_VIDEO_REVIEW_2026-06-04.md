# Preview video review state - 2026-06-04

## Current conclusion

The only Pi 5 raw-video encoder path proven to sustain 24 fps is:

```
codec=ml2_q3_dec2
```

That path encodes decimated Bayer payloads for later desktop decode and
reconstruction. The production raw-video container should be `.gvid`, which
wraps the per-frame FUSED `.gpr` payloads with clip-level fps, dimensions,
pixel format, quality, and bitrate metadata. The MOV/GPRaw wrappers remain
export and compatibility options, not the primary neutral deliverable.

The SOTA-v2 preview renders reviewed on 2026-06-04 are display/review
outputs from this class of decoded half-res capture. They are not the raw
video format themselves.

## Review bundle

Generated artifacts live outside the git repo to avoid committing large video
files:

```
/Volumes/OWC_8TB/gpr_work/artifacts/preview_review_20260604/
```

Dashboard:

```
/Volumes/OWC_8TB/gpr_work/artifacts/preview_review_20260604/preview_review_dashboard.html
```

ProRes review outputs:

| File | Frames | Duration | Format | Purpose |
|---|---:|---:|---|---|
| `barnsky_codec_only_120f_4k_prores_hq.mov` | 120 | 5.0 s | 3840x2160 ProRes 422 HQ | decoded codec-only preview |
| `barnsky_sota_v2_120f_4k_prores_hq.mov` | 120 | 5.0 s | 3840x2160 ProRes 422 HQ | SOTA-v2 display reconstruction |
| `barnsky_codec_vs_sota_v2_120f_3840x1080_prores_hq.mov` | 120 | 5.0 s | 3840x1080 ProRes 422 HQ | side-by-side review, codec-only left and SOTA-v2 right |
| `upresable_720f_4k_prores_hq.mov` | 720 | 30.0 s | 3840x2160 ProRes 422 HQ | UPRESABLE reference path timelapse |

The refreshed SOTA-v2 render was generated in 114.5 s for 120 frames:

```
0.95 sec/frame, including decode + codec path + sips + MPS CNN + ProRes encode
```

## Reproduction

The committed preview scripts default to the consolidated external work area,
but allow explicit path overrides:

```bash
python3 tools/cnn/preview_timelapse_fast.py \
  --n-frames 120 \
  --workers 4 \
  --src-dir /Volumes/OWC_8TB/gpr_work/barnsky_full_dngs \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/preview_timelapse

python3 tools/cnn/preview_timelapse_fast_sota.py \
  --n-frames 120 \
  --workers 4 \
  --src-dir /Volumes/OWC_8TB/gpr_work/barnsky_full_dngs \
  --out-dir /Volumes/OWC_8TB/gpr_work/artifacts/preview_timelapse
```

Both scripts render 16-bit TIFF intermediates, center-crop the 3:2 source
render to 16:9 UHD without geometric stretch, and pipe `rgb48le` into
`ffmpeg` for 10-bit ProRes 422 HQ output. `--eight-bit` exists only as a
legacy diagnostic path because it can introduce sky banding.

## Quality state

This 2026-06-04 review bundle predates the q8 three-way PREVIEW candidate. It
remains the latest committed ProRes/video-review media bundle, but it is no
longer the latest PREVIEW quality evidence. The current no-REF full-frame
offline/review production path is `preview_q8_threeway_runtime_fullframe_v1`:
84/84 on the 28-image holdout, worst LPIPS 0.1178, MS-SSIM 0.9548, Y-PSNR
30.87, and dE2000 2.64. That path is offline/review only at 13.65 s/image
(0.073 fps).

Relevant gate runs:

| Run | Pipeline role | Verdict | Z8Z_6693 LPIPS | Z8Z_6693 MS-SSIM | Z8Z_6693 dE2000 |
|---|---|---|---:|---:|---:|
| `5e7b79b5678fdf62` | passing SL q3 preview baseline | PASS | 0.1003 | 0.9580 | 1.7116 |
| `b3b767e5d4d2f717` | best learned LPIPS candidate | FAIL | 0.1511 | 0.9422 | 2.0169 |
| `824275e674aa8e9f` | best learned MS-SSIM candidate | FAIL | 0.2270 | 0.9472 | 2.5781 |
| `9d6dba741fdb6972` | larger-context Y candidate | FAIL | 0.1986 | 0.9438 | 3.1754 |

## Raw-video output decisions

Use this product split:

| Output | Role |
|---|---|
| `.gvid` | primary raw video deliverable for 24 fps capture |
| `.gpraw` / MOV `GPRr` | metadata-rich interchange/export wrapper |
| MOV `GPR1` | older `gpr2prores` compatibility wrapper |
| directory of `.gpr` frames | intermediate/debug handoff |
| editable DNG sequence | offline raw-editor handoff |
| ProRes 422 HQ MOV | rendered review/export, not raw |
| H.264/H.265 MP4 | browser/proxy review, not raw |

`gpr2prores` now accepts `.gvid` directly. It auto-unpacks the stream to a
temporary `.gpr` frame directory and reuses the existing playback renderer.
Set `TMPDIR=/Volumes/OWC_8TB/gpr_work/tmp` before invoking it to keep unpack
scratch on the external work drive.

## Next production risk

The remaining video production risk is not the container or 24 fps encode
path. It is quality beyond codec-only for live/camera-back PREVIEW: the q8
route is quality-valid for offline/review output but is far below live frame
rate. Noise separation remains relevant for future CNN training, but it is not
the current blocker for the registered offline/review PREVIEW path.
