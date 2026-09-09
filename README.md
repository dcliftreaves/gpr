# GPR

[![CI](https://img.shields.io/github/actions/workflow/status/dcliftreaves/gpr/ci.yml?branch=master&label=CI&style=flat-square)](https://github.com/dcliftreaves/gpr/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20OR%20MIT-blue?style=flat-square)](#license)

**8-bit JPEG size. 16-bit RAW quality.**

Compact RAW photos. RAW video you can edit. More detail when you get home.
This fork extends GoPro's GPR SDK from still photography into a complete Bayer
capture and desktop reconstruction workflow.

![Raw Bayer timelapse decoded through the GPR preview path](docs/img/readme_z8_timelapse_1024.webp)

## Small Files. Room To Edit.

GPR began with a useful idea: keep the flexibility of RAW without carrying huge
files everywhere. This fork builds on it with faster compression, 14-bit and
16-bit Bayer support, and optional CNN restoration. Choose a smaller file for
everyday shooting or a higher-quality tier for a demanding edit; the sensor
data stays available in either case.

![Three STILL tiers, fine-detail crop](docs/img/still_three_tiers.png)

The tested 50 MP still tiers average **9.80 MB**, **15.05 MB**, and **27.17 MB**.
The two smaller tiers pair compression with desktop restoration; the largest
uses no CNN. The workflow also supports X2D 100 MP DNG roundtrips and the four
standard Bayer layouts: RGGB, GBRG, GRBG, and BGGR. File size and fidelity depend
on the scene and selected settings.

## RAW In Motion

The next step was to make that same idea continuous. Fresh 4K Bayer frames are
compressed into `.gvid`, an independently decodable RAW video stream. A native
preview path reads that stream and displays the full frame, so capture and
playback share the same recording. No CNN is needed on the camera side.

![Mission native12 100 percent crop sheet](docs/img/readme_mission1_native12_100pct.png)

The Pi 5 evaluation path records **4096 x 3072 Bayer at 20+ fps** and previews
the same stream at **1024 x 768 above 20 fps**. These are Pi 5 measurements;
Mission 1 firmware integration still needs testing on the camera's sensor,
storage, and display interfaces.

![Native 12MP encode speed evidence](docs/img/readme_native12_fps_plot.svg)

## More Detail In Post

Capture has a deadline. Reconstruction can take its time. On the Mac, optional
CNNs restore 4K detail or reconstruct an 8K output from the recorded Bayer data.
The approved video models support editable RAW workflows and ProRes rendering,
letting you choose the source format or a ready-to-edit movie for the next step.

![Mission native12 2x SR contact sheet](docs/img/readme_mission1_2x_sr_contact.png)

The 4K cleanup and 8K video SR paths have passed their recorded review gates.
**Premium still/SR** is a separate, slower research effort for 50 MP and 100 MP
photography; a broadly improved replacement model has not yet passed its gate.
The existing still-restoration and video models remain available independently.

![CNN and SR improvement plot](docs/img/readme_cnn_sr_plot.svg)

## One RAW Source

Record once, then choose the output you need: a compact editable still, camera
preview, restored 4K, or reconstructed 8K. White balance and rendering happen
downstream of the Bayer recording, and ProRes is an output of that RAW workflow.

![GPR still and video pipeline flow](docs/img/readme_pipeline_flow.svg)

| Workflow | Output |
|---|---|
| RAW stills | Editable GPR/DNG, with optional desktop restoration |
| RAW video capture | 4K Bayer `.gvid` |
| Camera preview | Full-frame 1024 x 768 RGB from the same `.gvid` |
| Desktop reconstruction | 4K cleanup or 8K SR, editable Bayer and ProRes |

## Try It

Build the SDK and command-line tools:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
```

The [getting-started guide](docs/GETTING_STARTED.md) covers conversion and video
workflows. GoPro engineers can start with the
[camera evaluation guide](docs/GOPRO_MISSION1_QUICK_VALIDATION.md).

For measurements, model availability, limitations, and the development history,
see [technical details and evidence](docs/PRODUCT_DETAILS.md).

## License

Dual licensed under Apache-2.0 or MIT. See [LICENSE.txt](LICENSE.txt).
Product names belong to their respective owners; this fork is an independent
extension of the GoPro SDK.
