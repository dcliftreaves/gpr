# Contributing

Start with the [production build and test guide](docs/stock-production.md). Keep the non-CNN capture path independently buildable. Optional desktop tools and research models should have explicit dependencies and fallbacks.

For codec optimizations, preserve historical VC-5 fixtures and compare fast/reference payloads byte for byte. Check Bayer phase, word/packed domain, padded or unaligned rows, allocator failure and format boundaries. Report Raspberry Pi 5 measurements with source revision, scene/input hash, quality, workspace, warmup and timing boundaries. M5 results are useful for development, but do not predict a camera's performance.

For capture/container changes, test ownership, backpressure, write failures, cancellation, completion and interrupted-file recovery. Separate encode time, buffered throughput, flush-inclusive recording rate and per-frame deadlines. Keep failed configurations in the evidence rather than removing them from a summary.

For rendering/calibration changes, document which quantities are preserved and which are deliberately transformed. An implementation match to a reference renderer is not proof of an exact camera-JPEG match. Use paired captures when making that claim, and test neutral/color behavior, clipping, spatial corrections, orientation and bit-depth agreement. Include a small synthetic regression for the failure the change addresses.

For learned reconstruction or grain work, describe the model/profile identity, working domain, physical assumptions, training/evaluation split and temporal behavior. Keep source capture and derived interpretation distinguishable. Do not call statistical grain synthesis exact noise recovery. See [the project direction](VISION.md) and [research notes](docs/stock-project-research.md).

Credit upstream authors and link the exact PR/revision when importing work. Explain adaptations and intentionally excluded changes. Keep new commits focused on behavior a reviewer can assess; keep experimental evidence clearly labeled. Use redistributable fixtures or synthetic data, and do not commit private photographs or access credentials.

This guide covers this fork. Contributions sent to `gopro/gpr` follow that project's separate review and CLA requirements.
