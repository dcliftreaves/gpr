# Pi 5 SD card swap — runbook + preserved state

Hand-off doc. Pick up whenever. The current Pi keeps working; swap the SD
when convenient.

## Why swap

The current setup runs everything off the SD card (`/dev/mmcblk0p2`, 256 GB).
The USB SSD (`/dev/sda1`, 916 GB at `/mnt/ssd`) is sitting essentially empty
(759 MB used). After swap, the new SD only holds the OS; gpr clone, builds,
test DNGs, gate runs all move to the SSD which is faster and has 4× the
free space.

## Current state (verified 2026-05-29)

| device | mount | size | used | purpose |
|---|---|---|---|---|
| `/dev/mmcblk0p2` | `/` | 231 GB | 4.9 GB | OS + gpr clone + builds (will shrink to 64 GB) |
| `/dev/sda1` | `/mnt/ssd` | 916 GB | 759 MB | empty, ext4 with `noatime` |
| `/dev/mmcblk0p1` | `/boot/firmware` | 505 MB | 75 MB | Pi bootloader/kernel |

Pi clone is at `~/gpr` on commit `3254ab8` of `fix/multilevel-cascade-regression`
with local-modified files that exactly match today's pushed commits
(`79403fb`, `ec1cb2c`, `4fbd0cc`). **The Pi state is fully captured in
origin** — a fresh clone gets you everything plus a cleaner state.

## Preserved artifacts (already pulled)

Saved to `/Volumes/OWC_8TB/pi-pre-wipe-2026-05-29/`:
- `pi_authorized_keys` (101 B) — your ssh pubkey (mostly redundant; Pi
  Imager has a UI for setting ssh keys at flash time)
- `Z8Z_0001.dng`, `Z8Z_0067.dng`, `Z8Z_5323.dng`, `Z8Z_6693.dng` (~190 MB
  total) — the 4 gate test images; saves a re-rsync from the OWC drive
  after the swap

**Not preserved** (recoverable from origin or trivially rebuildable):
- `~/gpr` clone — `git clone` recreates
- `~/gpr/build/` — `cmake .. && make -j4` recreates (~5-10 min)
- `~/gpr-video`, `~/gpr-video-orig` — stale subagent transients; not needed
- `~/z8_bayer.raw` — derived from a DNG via `rawpy`, easy to regenerate
- bashrc / dotfiles — default Pi OS values

## Card recommendation

For the new 64 GB card, target:
- **V30** speed grade minimum (30 MB/s sustained)
- **A2** rating for good random IOPS (helps with directory writes / apt updates)
- **UHS-I** is fine — UHS-II only helps for >50 MB/s sustained which we
  don't need from the SD (capture goes to the SSD)
- Brands I'd trust: Samsung Pro Plus, SanDisk Extreme Pro V30, Kingston Canvas Go Plus
- **Avoid** anything labeled "high endurance" — those are spec'd for
  surveillance constant-write, not burst speed

## Flash + first-boot setup

Use Raspberry Pi Imager from raspberrypi.com:
1. Choose "Raspberry Pi OS Lite (64-bit)" — no GUI needed
2. Click the **gear icon** before flashing. Set:
   - hostname: `gpr-pi`
   - WiFi SSID + password
   - SSH: enable, **paste your pubkey** (this is what was in
     `pi_authorized_keys`; or just paste `~/.ssh/id_ed25519.pub` from
     your Mac)
   - locale
3. Flash. Boot the Pi. It'll come up on the network with ssh ready.

Verify ssh works: `ssh gpr-pi 'uname -a'`. If hostname doesn't resolve,
find the IP in your router and adjust `~/.ssh/config` accordingly (the
memory note `feedback_logarithmic_polling` mentions M5 used `.162` after
DHCP changed — same risk here).

## SSD-first setup commands

Run these in order from your Mac. Total time: ~15 min.

```bash
# 1. Confirm the SSD survived the swap (it should — separate USB device)
ssh gpr-pi 'lsblk | grep sda'    # expect "sda1 ... 931.5G ... part"

# 2. Mount the SSD and persist via fstab
ssh gpr-pi 'sudo mkdir -p /mnt/ssd && sudo mount /dev/sda1 /mnt/ssd'
ssh gpr-pi 'ls /mnt/ssd'         # sanity — should be empty or whatever you had

ssh gpr-pi 'echo "UUID=11b13b2c-aaa4-4656-8476-43df99a94031 /mnt/ssd ext4 defaults,noatime 0 2" | sudo tee -a /etc/fstab'

# 3. Make the workspace on the SSD
ssh gpr-pi 'sudo mkdir -p /mnt/ssd/work && sudo chown -R dcliftreaves:dcliftreaves /mnt/ssd/work'

# 4. Install dependencies
ssh gpr-pi 'sudo apt update && sudo apt install -y build-essential cmake git python3-pip rsync exiftool'

# 5. Clone gpr to the SSD
ssh gpr-pi 'cd /mnt/ssd/work && git clone https://github.com/dcliftreaves/gpr.git'
ssh gpr-pi 'cd /mnt/ssd/work/gpr && git checkout fix/multilevel-cascade-regression'

# 6. Symlink so any tooling that expects ~/gpr still works
ssh gpr-pi 'ln -s /mnt/ssd/work/gpr ~/gpr'

# 7. Build — everything goes to SSD via the symlink
ssh gpr-pi 'cd ~/gpr && mkdir build && cd build && cmake -DCMAKE_BUILD_TYPE=Release .. && make -j4'

# 8. Push test DNGs to the SSD + symlink from $HOME
rsync -avP /Volumes/OWC_8TB/pi-pre-wipe-2026-05-29/Z8Z_*.dng gpr-pi:/mnt/ssd/work/
ssh gpr-pi 'for d in /mnt/ssd/work/Z8Z_*.dng; do ln -sf "$d" ~/; done'

# 9. Smoke test
ssh gpr-pi '~/gpr/build/source/app/gpr_tools/gpr_tools -q 3 -i ~/Z8Z_0067.dng -o /tmp/smoke.gpr && ls -la /tmp/smoke.gpr'
# Expect ~7.8 MB output in well under 1 second
```

## Optional — bind-mount `/tmp` to the SSD

Reduces SD wear during heavy scratch work (rsync staging, ML intermediates).

```bash
ssh gpr-pi 'sudo mkdir -p /mnt/ssd/tmp && sudo chmod 1777 /mnt/ssd/tmp'
ssh gpr-pi 'echo "/mnt/ssd/tmp /tmp none bind 0 0" | sudo tee -a /etc/fstab'
# takes effect on next reboot
```

## Validation checklist after swap

- [ ] `ssh gpr-pi 'uname -a'` works
- [ ] `df -h | grep ssd` shows `/dev/sda1` mounted at `/mnt/ssd`
- [ ] `ls -la ~/gpr` shows a symlink to `/mnt/ssd/work/gpr`
- [ ] `~/gpr/build/source/app/gpr_tools/gpr_tools -q 3 -i ~/Z8Z_0067.dng -o /tmp/smoke.gpr` completes in <1 s
- [ ] Smoke output: `ls -lh /tmp/smoke.gpr` shows ~7.8 MB
- [ ] `cd ~/gpr && git status` shows clean working tree on `fix/multilevel-cascade-regression`
- [ ] `cd ~/gpr && git log --oneline -3` matches current `origin/fix/multilevel-cascade-regression` HEAD

## What this preserves vs the old setup

| was | now |
|---|---|
| gpr clone on SD root | gpr clone on SSD, symlinked into `~/` |
| Build dir on SD root | Build dir on SSD via symlink |
| Test DNGs on SD root | Test DNGs on SSD via symlinks |
| Gate run artifacts on SD | Under `~/gpr/tests/quality_gates/runs/` → SSD |
| SD writes: continuous | SD writes: near-zero in steady state |
| 217 GB free on SD | 60+ GB free on SD (just OS) + 916 GB on SSD |

## Gotchas

1. **The 64 GB SD's `/` partition will need to be expanded** after fresh
   imaging — `sudo raspi-config --expand-rootfs` does this. Imager
   handles it automatically on first boot for most images.
2. **SSD UUID stays the same** across SD swaps — that's why fstab uses
   UUID not `/dev/sda1`. If you ever reformat the SSD, regenerate the
   UUID line via `sudo blkid /dev/sda1` and update fstab.
3. **First `make -j4` on a fresh card uses ~2 GB of compile RAM**. With
   2 GB ZRAM swap (default) plus 4 GB physical, this works but tight.
   Don't run anything else compute-heavy in parallel.
4. **Pi Imager's hostname setting may not propagate to mDNS** on some
   networks — if `ssh gpr-pi` hangs after first boot, find the IP via
   your router's DHCP table and add an explicit `HostName` line in
   `~/.ssh/config`.

## Recovery if something goes wrong

The old 256 GB SD card is your full backup. If the fresh-image setup
fails for any reason, just put the old card back in. You lose nothing.
Recommend keeping the old card untouched for at least 1 week post-swap.

## Pi work this unblocks (next time)

Once the swap is done and the SSD-first layout is verified:
- Re-bench `bench_fused` and `gpr_tools` against the SSD-backed build to
  confirm no regression vs the SD-backed bench (today's `544 ms at q=3`
  and `38.20 ms median for ml2_q3_dec2`).
- More headroom for storing video captures locally during embedded-capture
  testing (currently 24.93 fps × 1.30 MB = 31 MB/s = ~7.5 GB / 4 min clip).
- A future Pi-side CI runner (per `docs/TESTING_METHODOLOGY.md` "open
  gaps") becomes more viable with the SSD for artifacts.
