# Labs Readiness Review

Last refreshed: 2026-06-14

## Decision

Go for Labs prototype exploration of half-res `.gvid` raw capture plus desktop
review/export.

No-go for direct firmware merge until target hardware integration and sustained
capture evidence exist.

## Ready Now

| area | evidence |
|---|---|
| Media shape | `.gvid` clip/frame format, Python packer, metadata sidecars |
| Desktop review path | `gpr2prores` accepts `.gvid` and validates runtime dispatch |
| Source-level safety | hosted CI validates headers, streams, release evidence, registry consistency |
| Format hardening | C reader rejects malformed v1 headers and whole-stream corruption |
| Current overview | README is media-focused; detailed proof lives in docs |

## Not Ready Yet

| area | missing evidence |
|---|---|
| Firmware capture integration | sensor/DMA handoff and memory ownership have not been executed on target |
| Sustained target run | no committed 10 minute target-style receipt for fps, storage, thermal, memory, drops |
| Portable artifact bundle | bundle manifest, sample media, checksums, and review outputs still need packaging |
| Recovery proof | partial-file recovery policy is specified but target interruption receipt is missing |

## Current Risk

The main risk is not whether `.gvid` can represent the media. The risk is
whether target firmware can feed, encode, write, recover, and validate the
stream under real storage, thermal, power, and memory constraints.

## Next Work

1. Produce the portable Labs artifact bundle.
2. Run the Pi 5 sustained capture bench as explicit stand-in evidence.
3. Add target/self-hosted CI jobs or documented manual receipts for media
   behavior hosted CI cannot exercise.
4. Re-run the readiness review with bundle hashes and bench receipts attached.
