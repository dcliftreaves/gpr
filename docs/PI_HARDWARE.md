# Pi 5 capture hardware requirements

Historical note: this page records the older full-res/LL-only storage planning
bench. The current half-res `.gvid` capture path is tracked in
`VIDEO_STATUS.md`, `LABS_TARGET_BENCH.md`, and
`RAW_RESOLUTION_TARGETS_2026-06-14.md`, where the active budget is
1.30 MB/frame and about 31 MB/s at 24 fps. Keep this page as storage
background, not as the current `.gvid` ship budget.

## TL;DR

For this historical full-res planning case, the encoder kernel hit 25.9 fps
in-memory on Pi 5 (Cortex-A76, LL-only-fast mode), while sustained writes to
the tested stock SD setup reached only about 7 fps. To sustain 24 fps at
50 MP × 3.5 MB/frame compressed, a measured storage path of **>=84 MB/s** is
required. The current half-res `.gvid` Labs path has a lower storage budget;
its active blocker/evidence is tracked in the Labs target docs.

## Measured numbers (Pi 5, 8 GB)

| Test | fps |
|---|---|
| Encoder kernel only (in-RAM bayer → GPR bytes in RAM) | **25.9 fps** |
| End-to-end **100 frames** burst (page-cache absorbed) | 21.3 fps |
| End-to-end **500 frames** sustained (page cache full) | **6.88 fps** |
| SD card sustained write (dd, fdatasync) | 18-33 MB/s |
| Required for 24 fps × 3.5 MB | **84 MB/s** |

## Storage path options

| Path | Sustained write | Cost | Setup | Notes |
|---|---|---|---|---|
| **Stock SD slot, generic V30 card** | 25-40 MB/s | $10-20 | drop-in | what's there today; **insufficient** |
| **Fast measured microSD** | card-dependent | $20-80 | drop-in | acceptable only if the exact card sustains the required write rate |
| **USB 3.0 external SSD** | 400-500 MB/s | $50-100 | USB-A | comfortable headroom |
| **PCIe HAT + NVMe SSD** | 500-800 MB/s | $30 HAT + $50 SSD | HAT install | best, future-proof |
| **Gigabit Ethernet → NFS** | 100-115 MB/s | $0 (existing LAN) | NFS mount | tethered only; meets the bar with margin |
| **2.5 GbE via USB adapter** | ~280 MB/s | $30 | USB ↔ Ethernet | tethered, higher rates than gigabit |

## Recommendation by workflow

- **Pocket camera (untethered)** → measured-fast microSD, USB 3.0 SSD, or NVMe
- **Studio rig (tethered to workstation)** → Gigabit Ethernet + NFS, or USB SSD
- **Maximum throughput rig** → PCIe HAT + NVMe

## RAM-buffer fallback (current hardware)

Pi 5 has 8 GB RAM; `/dev/shm` (tmpfs) defaults to 4 GB. At 3.5 MB/frame that buffers **~1100 frames = 47 seconds of 24 fps capture**. Useful for short bursts that can be flushed to SD afterward.

Workflow:
1. Capture to `/dev/shm/clip/`
2. Stop recording
3. Move files to SD card (~5 sec of recording flushes in ~12 sec at 33 MB/s)
4. Resume

Not suitable for long takes; pad SD writes between bursts.

## Reproducing the bench

```bash
# Pi 5
cc -O3 -mcpu=native tools/test/save_test.c -o /tmp/save_test

# Sustained sensor-style test: 500 frames at 3.5 MB each
mkdir /tmp/cap_test
/tmp/save_test 500 0 /tmp/cap_test  # 500 individual writes
rm -rf /tmp/cap_test
/tmp/save_test 500 1 /tmp/cap_test  # 1 file with appends (container-like)
```

The `save_test.c` source is the synthetic bench used to characterize the SD card without needing a real encoder. Source-level wall clock vs encoder kernel time isolates the I/O from the compute.
