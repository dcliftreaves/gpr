# RAW as a camera system

A photograph begins with a lens, a sensor and a photographer's intent. The file should carry enough knowledge of those things to remain useful as processing improves.

This project develops GPR stills and GVID video around that principle: fast, editable Bayer capture; explicit optical and sensor calibration; and reproducible rendering that leaves room for both measured reconstruction and artistic choices. We build on GoPro's GPR/VC-5 work and credit the contributors whose improvements we adopt.

## What we preserve

Capture must keep its geometry, sample domain, exposure, timing and supported calibration. A full lens warp is more useful than two coefficients that happen to describe one camera. Black level, white balance, color matrices, shading and baseline exposure must survive conversion rather than being replaced by convenient defaults.

Compression is an explicit tradeoff. The stock VC-5 path is lossy, including its companding. We measure size, speed and image error together; no preset is universally the best compression for every scene. Exporting another DNG does not make a lossy capture lossless.

## Camera knowledge should earn its place

Knowing the sensor, lens, aperture, readout and noise statistics can improve compression, preview, reconstruction and power use. Profiles should identify the measured hardware and operating conditions, explain their assumptions and carry versions and hashes. Unsupported calibration should remain visible to applications rather than silently turning into an invented profile.

The current foundation retains typed camera metadata, bounded capture and calibrated output. More detailed sensor/readout profiles, per-lens optical models and matched preview-to-final rendering are development goals, not claims of implemented camera firmware.

## AI should respect the measurement

We want AI-assisted RAW workflows whose models are anchored in optics and sensor behavior, with a usable analytical path when a model is unavailable. Model identity, training scope, reconstruction settings and geometric changes should be explicit. Evaluation must include unseen scenes and cameras, color and exposure consistency, edges, texture and temporal behavior—not only an average score on training-like crops.

The released non-CNN capture path does not require weights or a neural runtime. Existing experimental reconstruction branches remain separate until their image-quality and deployment requirements are met. A learned reconstruction is a derived interpretation of the capture, not newly measured sensor detail.

## Grain and look are part of photography

Sensor noise and photographic film grain are different processes. A camera-noise model may depend on signal, channel, gain, temperature and spatial correlation. A film-grain model may depend on emulsion, exposure, development, physical grain size, scanning and the display transform. Neither is adequately described by one generic noise-strength slider.

The intended workflow lets a photographer retain captured texture or choose a documented rendering recipe. Synthetic grain should have reproducible seeds, a physical scale, a defined working domain and sensible behavior across crops, image sizes and video frames. Removing stochastic noise and generating a statistically similar realization is not exact reversibility; exact recovery requires retaining the missing information.

Research directions include measured conditional variance, noise-power spectra, channel correlation, higher-order statistics and temporal independence. See [the research notes](docs/stock-project-research.md) for starting points. These are design criteria for future work, not a claim that the stock codec now implements a film emulator.

## Optionality that survives time

A file should remain decodable without a particular cloud service or model download. Bayer data, calibration and capture timing belong to the recording. A display look, grain recipe or learned reconstruction should be identifiable and reproducible without replacing that recording.

The practical finish line is a camera engineer who can integrate a bounded encoder, a photographer who can recover editable frames, and a developer who can reproduce the result from a clean checkout. Performance claims use Raspberry Pi 5 as the current embedded reference and must state storage, quality, scene and measurement boundaries. Camera-specific behavior still needs camera-specific measurements.
