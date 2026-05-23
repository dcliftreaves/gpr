# Pi 5 capture hardware requirements

## TL;DR

The encoder kernel hits 25.9 fps in-memory on Pi 5 (Cortex-A76, LL-only-fast mode). Sustained sensor → SD card capture is **storage-bound at ~7 fps** on the stock SD slot. To hit 24 fps sustained at 50 MP × 3.5 MB/frame compressed, you need a storage path that sustains **≥84 MB/s**.

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
| **UHS-II V90 SD card** | 100-200 MB/s | $30-50 | drop-in (Pi 5 SD slot supports UHS-II) | meets the bar |
| **USB 3.0 external SSD** | 400-500 MB/s | $50-100 | USB-A | comfortable headroom |
| **PCIe HAT + NVMe SSD** | 500-800 MB/s | $30 HAT + $50 SSD | HAT install | best, future-proof |
| **Gigabit Ethernet → NFS** | 100-115 MB/s | $0 (existing LAN) | NFS mount | tethered only; meets the bar with margin |
| **2.5 GbE via USB adapter** | ~280 MB/s | $30 | USB ↔ Ethernet | tethered, higher rates than gigabit |

## Recommendation by workflow

- **Pocket camera (untethered)** → UHS-II SD or USB 3.0 SSD
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
