# RAW codec and GVID verification — 2026-11-21

This release consolidates the stock-compatible codec and non-CNN GVID software foundation onto one maintained branch. It includes the native 100 MP path, supported optical metadata, calibrated SDK rendering, strict/recovery readers, bounded capture, ordered-still movie creation and reproducible build/install checks.

## Raspberry Pi 5

Measured on an 8 GB Raspberry Pi 5 Model B, 2.4 GHz under load, `ondemand` governor, Samsung T5 SSD on a 5 Gbit/s UAS connection. No throttling was reported before/after these runs. Tests are RAW fixture replay, not physical sensor acquisition. The 512 MiB reusable workspace is initialized before timed recording.

| Input / quality | Duration | Frames written / requested | Median encode call | Flush-inclusive rate | Result |
|---|---:|---:|---:|---:|---|
| 12 MP RGGB14, Q3, queue 16 | 180 s | 4320 / 4320 | 25.12 ms | 23.996 fps | Qualified |
| 12 MP RGGB14, Q4, queue 16 | 180 s | 3600 / 3600 | 25.84 ms | 19.999 fps | Qualified |
| 50 MP RGGB14, Q3, queue 4 | 180 s | 1800 / 1800 | 73.38 ms | 9.998 fps | Qualified |
| 100 MP RGGB16, Q3, queue 4 | 60 s | 180 / 180 | 155.68 ms | 3.006 fps | Qualified |

The 12/50 MP cases repeat one real GoPro frame each. The 100 MP case cycles three distinct real X2D frames at 11664×8744. Encoding cost depends on the scene: the 100 MP median over those three inputs is not directly comparable with the earlier 240.8 ms mean for repeated copies of only the first frame on the older dependency. Payloads, dimensions, calibration, timestamps and final completion markers were verified.

Peak process RSS was approximately 547 MiB (12 MP Q3), 560 MiB (12 MP Q4), 624 MiB (50 MP) and 1156 MiB (100 MP). This includes preloaded replay inputs and the reserved workspace, not just encoder scratch. The 100 MP case used allocator fallback; it is not a claim of a 512 MiB total-memory camera implementation.

Qualified means every requested frame, zero queue overruns and average durable rate within 1% of target. It does not mean zero per-frame latency misses: those runs reported 6 (12 MP Q3), 41 (12 MP Q4), 16 (50 MP) and 1 (100 MP) misses respectively. The 12 MP and 50 MP cases completed their final flush in about 41 ms and 59 ms. The final 12 MP result includes checking file close and syncing the parent directory as well as file data.

## Keep failed configurations visible

An earlier 12 MP Q3 / 24 fps / queue-4 run passed, but a repeat on the final native frontend rejected one frame. The latter recorded a 165 ms encode-call stall; the four-frame queue was insufficient for that burst. The tested queue-16 configuration completed all frames. This does not establish an upper bound on future OS/storage stalls.

At 30 fps, queue 4 rejected one of 5400 frames; queue 8 rejected 459 frames in a separate run. Their average durable rates were 29.990 and 27.444 fps. Increasing queue depth cannot establish a sustainable rate when service capacity or stalls exceed the available budget. No sustained 30 fps profile is qualified for this drive/setup.

The short SD-card replay from the preliminary audit accepted every submitted 12 MP frame but finished at only about 11.5–12.9 fps when final flushing was included. It is not a qualified 24/30 fps storage profile.

The numeric receipts include both passing and failed runs in [stock-release-20261121/](stock-release-20261121/). Each qualification receipt records its binary/input hashes, conditions and counter accounting. Run the qualifier on the actual intended storage and scenes rather than treating these profiles as device-independent guarantees.

## Correctness and interoperability

- Pi 5: 34 SDK/core/preview CTest tests passed on the integrated native build, including capture lifecycle, buffer ownership, allocation paths, cancellation/write errors, Bayer formats and calibrated export.
- M5: 37 tests passed with native preview, SDK, optional MOV and ProRes enabled. Targeted follow-ups cover the final integrity receipt labels, all JPEG orientations and even dimensions not divisible by eight.
- The stdlib workflow exercises all 12 Bayer/bit-depth combinations plus 128×98 cases in each sample-bit domain, strict corruption/truncation handling, explicit prefix recovery, forced filesystem write failure and exclusive output destinations.
- A 50-still synthetic sequence completes the high-level DNG-to-GPR/GVID workflow. This tests the workflow's frame-count handling, not a real-time 50-frame camera burst.
- Three distinct 100 MP X2D frames were recorded, independently parsed, natively decoded and exported to GPR and DNG. Geometry and typed calibration were checked against their source sidecars.
- All 48 reduced RGB comparisons across six bundled camera samples, four resolutions and 8/16-bit output matched an independently built upstream PR #68 head byte for byte on M5. This is implementation parity, not a paired out-of-camera JPEG color test.
- Synthetic optics tests retain full radial/tangential warp terms, center and flags, baseline tags and JSON reconstruction. Default gain maps stay unchanged; explicit Apple-compatible DNG export adjusts only the intended green samples. Full-SDK embedded thumbnails match the same GPR's later calibrated JPEG render at matching quality.
- Stripped capture-only, preview-only and camera packages built, ran their tests, and passed relocated C/C++ consumer checks after producer removal. The full package also passed native and SDK external clients. A separate downstream `add_subdirectory` build passed.

No ASan/UBSan campaign was added to this pass. Neural model quality/training and target-camera firmware deployment are not release claims.

## Revisions and evidence

The initial consolidated capture runs used `3da206a7`; the calibrated SDK/X2D run used `35c856fe`; the final native frontend and SDK fixes are in `0d65af9c`. `c546f32c` adds accurate integrity scopes and a truly header-only indexing mode. Later commits add boundary regressions, packaging documentation and the release evidence. Documentation-only changes do not alter the recorded binaries; receipts retain their exact binary hashes.

The consolidation incorporates GVID work from `83ffa031`, the published X2D series through `0a194995`, and the stock optimization lineage, without enabling the newer experimental optical-coring, sparse-band or neural branches. Selected upstream rendering work comes from Adeel Abbas's PR #68 at `1a65057d`; see [the upstream review](stock-upstream-review.md).

Source fixtures and generated private full-resolution photos remain local. Only numerical receipts and logs are published here. CI must be checked for the exact master revision; local pass counts are not a claim that unrun hosted jobs passed.
