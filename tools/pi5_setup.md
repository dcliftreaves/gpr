# Pi 5 capture setup — fresh system

End-to-end walkthrough from a clean Raspberry Pi OS install to a Pi 5 that can
run the GPR target-proxy benches. **Wall-clock: ~25 min** (image download +
flash ~10 min, first boot + apt ~5 min, build + bench ~10 min).

Current status: the strict 10 minute Labs Pi proxy receipt is **19.98 fps**
median with 0 drops, valid `.gvid`, and interrupted-tail recovery. That is
proxy evidence for Labs handoff review, not a final Mission 1 hardware claim.
Mission 1 still needs its own 24 fps camera receipt.

## What you need

- A clean boot microSD card
- Prefer USB SSD or NVMe for sustained capture/output tests; fast microSD is
  acceptable only after measuring the exact card
- A Mac or Linux box to flash the card from
- Wi-Fi credentials or an Ethernet cable for the Pi 5
- The Pi 5 itself, power supply, micro-HDMI if no SSH yet

## Step 1 — flash Raspberry Pi OS to the SD card

Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/) if you
don't already have it.

1. Open Raspberry Pi Imager
2. **Choose Device** → Raspberry Pi 5
3. **Choose OS** → Raspberry Pi OS (other) → **Raspberry Pi OS (64-bit) Lite**
   (Bookworm). We pick Lite because the Pi 5 here is a capture box, no GUI
   needed. Saves ~1.5 GB and shaves ~10 s off boot.
4. **Choose Storage** → the SD card. Double-check it's the SD, not your
   internal disk.
5. Click **Next** → **Edit Settings**:
   - **General** tab:
     - Set hostname: `pi5-capture` (or whatever)
     - Set username + password (write these down)
     - Configure wireless LAN: SSID + password + country
     - Set locale + timezone
   - **Services** tab:
     - Enable SSH → use password authentication
       (or paste an SSH public key if you have one)
   - **Options** tab: leave defaults
6. **Save**, then **Yes** to apply, then **Yes** to overwrite the SD.
7. Wait for write + verify.

## Step 2 — first boot

1. Eject the SD, insert into the Pi 5, power on.
2. Wait ~30 s for first boot. The Pi will join your Wi-Fi (or you can
   plug Ethernet).
3. Find its IP: `arp -a | grep pi5-capture` from your Mac, or check your
   router's DHCP table.
4. SSH in:
   ```
   ssh pi5-capture.local      # if mDNS works
   # or
   ssh user@<ip>              # otherwise
   ```

## Step 3 — run the setup script

Pull and run `tools/pi5_setup.sh`. It clones the gpr repo into `~/gpr`,
installs build deps, builds the encoder, runs a storage benchmark, and reports
whether the measured path has enough write bandwidth for the selected bench.

```bash
# Once SSH'd into the Pi 5:
curl -fsSL https://raw.githubusercontent.com/dcliftreaves/gpr/master/tools/pi5_setup.sh \
  | bash
```

Or, if you'd rather inspect it first:

```bash
ssh pi5-capture
git clone --depth 1 https://github.com/dcliftreaves/gpr.git ~/gpr
~/gpr/tools/pi5_setup.sh
```

Expected storage output ends with something like:

```
==> Verdict
    Sustained write speed: 142 MB/s
    Required for 24 fps × 50 MP × 3.5 MB compressed: 84 MB/s

    ✓ ≥84 MB/s — capable of 24 fps × 50 MP × 3.5 MB sustained
```

For the current half-res `.gvid` path, the active storage budget is much lower:
about **1.30 MB/frame**, or **31 MB/s at 24 fps**. Use
`docs/LABS_TARGET_BENCH.md` for the current target receipt schema and
`docs/LABS_MISSION1_RUNBOOK.md` for the final camera-handoff run.

If the measured write speed is unexpectedly low, move output to USB SSD/NVMe,
reseat or replace the card, and rerun the benchmark. Do not assume a card class
label is enough; use the measured sustained-write number.

## Step 4 — encoder smoke test

The setup script left a synthetic 50 MP raw at `/tmp/test_50mp.raw` and
ran a 30-frame in-RAM kernel bench. To verify sustained rate, run a longer
test that exhausts the page cache:

```bash
~/gpr/build/source/app/bench_fused/bench_fused /tmp/test_50mp.raw 8280 5520 500
```

The reported per-frame time times 500 is what you'll actually see end to end.
Compare against:

- 41.7 ms / frame = 24 fps
- 27.8 ms / frame = 36 fps (camera burst limit)

## Next: hook up the sensor

That's outside the scope of this script — the sensor -> DMA -> encoder path
is camera-specific. See `docs/LABS_MISSION1_RUNBOOK.md` for the target camera
receipt and `docs/PI_HARDWARE.md` for historical storage background.
