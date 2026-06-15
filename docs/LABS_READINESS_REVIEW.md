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
| Portable stand-in bundle | `/Volumes/OWC_8TB/gpr_work/artifacts/labs_bundle_20260614_upresable_v1/manifest.json` verifies with `tools/verify_labs_bundle.py` |
| Current overview | README is media-focused; detailed proof lives in docs |

## Not Ready Yet

| area | missing evidence |
|---|---|
| Firmware capture integration | sensor/DMA handoff and memory ownership have not been executed on target |
| Sustained target run | no committed 10 minute target-style receipt for fps, storage, thermal, memory, drops |
| Final target artifact bundle | stand-in bundle exists; final bundle still needs 10 minute target receipt and camera-firmware evidence |
| Recovery proof | partial-file recovery policy is specified but target interruption receipt is missing |

## Current Risk

The main risk is not whether `.gvid` can represent the media. The risk is
whether target firmware can feed, encode, write, recover, and validate the
stream under real storage, thermal, power, and memory constraints.

## Next Work

1. Run the Pi 5 sustained capture bench as explicit 10 minute stand-in evidence.
2. Replace or supplement the stand-in bundle with final target-capture receipts.
3. Add target/self-hosted CI jobs or documented manual receipts for media
   behavior hosted CI cannot exercise.
4. Re-run the readiness review with target bundle hashes and bench receipts attached.
