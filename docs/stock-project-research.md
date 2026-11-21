# Camera integration and grain research notes

These are research leads and evaluation criteria, not dependencies or claims that a new film-grain engine is already shipped. Sources were checked on 2026-11-21. No creator has been contacted.

## Hardware collaboration

The creator is **GxAce / Casey Cavanaugh**. His own site lists the [GX-P1 camera as in development](https://gxace.com/gxp1). The project appears relevant to exploring a deliberately designed photographic experience and a consistent capture-to-render workflow. The public project page does not establish an SDK, sensor integration point or willingness to adopt this codec.

A useful future demonstration would show the same capture as editable RAW, a fast camera preview and a reproducible finished look; document Pi 5 time, memory, size and write bandwidth; and clearly identify which operations could run in camera versus desktop. An engineering pitch should lead with that working example and ask about actual sensor/processor interfaces. No inference about another manufacturer's interest or attribution follows from technical progress alone.

## Grain leads

The remembered video involved measuring scanned **16 mm motion-picture film** and open-source synthesis. Its exact identity remains unconfirmed. The following are relevant candidates or reference implementations, not asserted matches:

- [Newson and colleagues' GPU implementation](https://github.com/alasdairnewson/film_grain_rendering_gpu) and [Realistic Film Grain Rendering](https://www.ipol.im/pub/art/2017/192/): a physical stochastic-grain reference, with resolution-independent rendering. Useful for separating the underlying continuous model from output pixel size.
- [Film Grain Rendering and Parameter Estimation, SIGGRAPH 2023](https://www.siggraph.org/wp-content/uploads/2024/02/ACM-Transactions-on-Graphics-Volume-42-Issue-4.html): the authors describe a faster statistical renderer and parameter estimation from scanned grain. This is a particularly relevant research direction for measurement-driven synthesis; the paper's performance claim is not a benchmark of our implementation.
- [cinegrain2](https://github.com/mr-berndt/cinegrain2): its README reports calibration against real 4K ProRes scans, including 16 mm, using adjacent-pixel autocorrelation, and documents frame-dependent animation and luminance zones. This fits parts of the recollection, but the exact video is unverified. One autocorrelation statistic alone cannot validate all grain structure, luminance behavior or higher-order statistics.
- [grainifier](https://github.com/grainifier/grainifier): profiles real scans with density-conditioned amplitude, noise-power spectrum and skewness. The documented initial profiles are B&W stocks; do not treat those results as verified color motion-picture emulsion models.
- [spektrafilm, formerly agx-emulsion](https://github.com/andreavolpato/spektrafilm): a spectral negative/development/print/scan framework grounded in manufacturer data. A useful reference for the complete process and for keeping film density distinct from scene-linear or display RGB. Its code is not incorporated into this dual-licensed core.

## What to measure before adopting a grain model

Use the least processed scan available, with documented stock, exposure/development, gauge, scanner, sampling pitch, working space and transfer curve. Avoid treating a streaming-video upload as an untouched measurement: resampling, compression, grading and denoising change its statistics.

Measure conditional mean, variance and skewness across density/exposure; the two-dimensional power spectrum and spatial covariance; per-layer/channel correlation; frame-to-frame correlation; and behavior near black, saturation and strong edges. Track physical grain scale across crops and resolution changes. Separate scanner noise and image detail from emulsion texture rather than attributing every high-frequency variation to grain.

Evaluate synthetic video after the intended display transform, playback scaling and delivery codec, in addition to checking the underlying statistics. A model can match variance yet look wrong in motion, or look plausible in one still but produce repeating tiled patterns over time.

For this project, keep the captured signal and supported calibration distinct from a versioned look/grain recipe. A future recipe should specify its domain, model/version, parameter/profile hash, physical scale and deterministic frame/crop seed convention. Statistical re-synthesis cannot recover the exact random noise that was removed during encoding.
