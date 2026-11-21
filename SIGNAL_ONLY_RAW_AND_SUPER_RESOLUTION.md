# Reproducible signal RAW and bounded super-resolution experiment

This branch provides an **offline desktop experiment**: calibrated RGGB14 input
→ optional host denoising → stock VC-5 GPR → a separate decoder process → editable
DNG, with analytical or frozen neural reconstruction and optional generated grain.

The shipped 388,500-parameter checkpoint loads, but its training-source split is
not recorded. Evaluation is exploratory: no held-out-scene quality approval,
Phocus/HNCS matching, camera deployment, sustained capture rate or neural
accelerator compatibility is established by this workflow.

## Build and test

macOS/Linux, CMake >=3.12 and a C/C++ compiler are required. Host ML dependencies
are optional for the codec and installed only for this experiment:

```sh
python3 -m venv outputs/signal-env
. outputs/signal-env/bin/activate
python -m pip install -r requirements-signal.txt
cmake -S . -B outputs/signal-build -DCMAKE_BUILD_TYPE=Release \
  -DGPR_BUILD_SDK=OFF -DGPR_BUILD_STILL_APPS=OFF \
  -DGPR_BUILD_SIGNAL_TESTS=ON -DPython3_EXECUTABLE="$(which python)"
cmake --build outputs/signal-build --target vc5_encoder_app vc5_decoder_app -j 4
ctest --test-dir outputs/signal-build -R signal_raw --output-on-failure
```

These tests generate their own small inputs, load the shipped checkpoint, and
exercise the actual codec. They verify bounded floating output, exact integer
cell sums, globally aligned tiling, empty-bin noise estimates, independent and
frame-varying grain, crop-equivalent random samples, metadata and a new decoder
process with the original image hidden. No external images or training are needed. A small known-clean synthetic input
can also be generated for the comparison command:

```sh
python tests/signal_raw_test.py --write-fixture outputs/signal-fixture
```

Use its `source.dng` as input and `clean.dng` with `--clean-reference`. These are
synthetic correctness/behavior fixtures, not evidence of camera-scene quality.

The previous `python -m unittest tests/stock_*` invocation was not a valid test of
the larger model: those historical suites have other native dependencies and
missing runtime components on this branch. The portable entry above supersedes
that claim. `tools/verify_50mp_gopro_full_frame.py` evaluates the older F_ane/W96
models and is not evidence for the newly shipped larger checkpoint.

## Compare one image

Supply a calibrated, aligned **RGGB14 DNG or GPR**. A DNG containing previously
decoded GPR samples does not become lossless sensor ground truth by repackaging.
This model's count normalization is not suitable for arbitrary RGGB16/X2D input.

```sh
python tools/signal_raw.py compare /path/to/source.dng --output outputs/comparison \
  --encoder outputs/signal-build/source/app/vc5_encoder_app/vc5_encoder_app \
  --decoder outputs/signal-build/source/app/vc5_decoder_app/vc5_decoder_app \
  --qualities 0 1 2 3 4 5 --device cpu
```

On a supported Apple GPU, explicitly select `--device mps`. `--tile 256` can reduce
halo overhead; larger tiles increase memory. CPU is the portable default.

Open `outputs/comparison/report.html` for fixed-curve grayscale RAW previews and
DNG links. `measurements.csv` contains size, timing, memory and quality columns;
`comparison.json` retains detailed per-case checks and reference qualifications.
Outputs remain local and existing output directories/files are refused.

Each quality preset produces three actual GPR files and five decoded views:

| Encoded input | Decoder output |
| --- | --- |
| Full-resolution stock control | Native VC-5 decode |
| Full-resolution host-denoised input | Native VC-5 decode |
| Simulated half-resolution denoised input | Bounded analytical 2x, frozen neural 2x, and neural 2x with generated grain |

The smaller input is synthesized with a same-color linear box average before
encoding. It is **not asserted equal to physical sensor binning or VC-5 LL1**.
The neural and analytical views use the same actual codec-decoded low-resolution
samples, rather than an uncompressed simulation supplied directly to the model.

PSNR, bias, shadow/highlight error, detail/faint-gradient error and a simple
square-root tone proxy are measured against the input samples. These scores do
not establish that denoising recovers clean signal. If an independently obtained,
aligned clean target is available, add `--clean-reference /path/to/clean.dng`;
its scores are reported separately and its provenance remains operator supplied.
Do not tune on these images and subsequently describe them as held-out results.

File bytes include calibration and experimental metadata. Native encode timing
includes process startup and I/O; preparation (profiling/filtering) is separate.
Decoder timing includes model loading, reconstruction and DNG writing. RSS is
whole-process residency, including Torch. MPS driver memory is sampled at tile
boundaries and is not a certified GPU peak. None of these is an on-camera rate.

## Encode, close and reopen independently

```sh
python tools/signal_raw.py encode /path/to/source.dng --output outputs/signal.gpr \
  --mode simulated_sr --quality 3 \
  --encoder outputs/signal-build/source/app/vc5_encoder_app/vc5_encoder_app \
  --decoder outputs/signal-build/source/app/vc5_decoder_app/vc5_decoder_app
python tools/signal_raw.py decode outputs/signal.gpr --output outputs/restored.dng \
  --decoder outputs/signal-build/source/app/vc5_decoder_app/vc5_decoder_app
```

The decoder needs the GPR, codec executable and, only for `--neural`, the hash-bound
checkpoint. It does not need the original image or a noise-profile sidecar.
Bounded analytical reconstruction is the default. `--neural` explicitly opts
into the frozen neural checkpoint; it can regress on new inputs. `--grain-strength 1` enables
Gaussian texture and `--frame-index N` varies innovations for a sequence.
`--checkpoint` permits relocating the same checkpoint; a different hash is rejected.

## What is stored and conserved

Experimental TIFF tag **65000**, prefixed `gpr.signal_raw.v1`, contains the mode,
noise estimate, seed, checkpoint identity, VC-5 payload digest and, for SR, original
full-resolution calibration. Unknown tag owners/collisions are rejected.

Each **32-value float16 sigma LUT occupies 64 bytes**. Its intensity positions
are a fixed uniform 0..16383 grid. SR simulation also estimates a separate LUT
in the averaged pre-encode domain, rather than assuming that noise covariance
or sigma survives downsampling unchanged; storing both sigma arrays costs 128 bytes. The JSON envelope, format information, hashes,
seed and full-resolution calibration cost additional bytes, all reported. This is
an experimental metadata contract, not a registered production GPR extension;
third-party tools may discard it. The codec payload is stock VC-5. The control uses this branch's native codec
with extra optical/coring modes disabled, rather than claiming its code is
identical to the pristine upstream encoder.

The profiler is an intensity-binned green-difference MAD approximation. Texture,
Bayer-site displacement and compression can contaminate it; it does not uniquely
identify photon/read noise or replace dark/flat calibration. The existing HQS/PSF prototype is not enabled in this default benchmark; measured
lens PSF calibration remains a prerequisite. The host filter is
explicitly separate from the existing fixed-threshold C coring modes, which are
not silently enabled by shell environment variables during comparison.

The SR output is corrected for range and cell mean together. Integer samples use
balanced rounding, and every group of four same-color output samples sums to
exactly four times the **decoded** low sample. This guarantee applies before
grain and before any subsequent lossy re-encoding; it does not recover the
uncompressed source measurement. Tile origins respect the pooling grid and use
at least 64 low-plane pixels of halo. The nominal old 138-pixel context label is
not an independently measured effective receptive-field guarantee.

Generated grain uses independent Bayer-site Gaussian innovations, a stored seed,
frame index and absolute sample coordinates. It is reproducible across crops and
varies across frames. It does **not** restore discarded original noise, establish
an exact sensor covariance, or implement a measured OLPF. Its clipping and integer
rounding can change output cell means. Grain is off by default.

## Evidence and next hardware gate

Sanitized measurements and test results are in
[docs/signal-raw-validation.json](docs/signal-raw-validation.json). Images, decoded
DNGs and source metadata remain operator-local. Earlier visual-guide figures and
old PSNR tables are historical illustrations, not receipts from this workflow.

Before camera work or larger models: establish a calibrated source/reference
protocol, recover training-split provenance or retrain with recorded splits,
measure matched-size rate/quality curves on new scenes, calibrate actual noise/PSF
behavior, and measure full-frame latency/memory on the intended hardware. The
current larger model requires roughly 1.2 trillion convolution MACs per 50 MP
output before tile overlap, profiling or optics; its parameter count alone is not a runtime budget.
