# Local Fixture Compatibility

This project keeps real camera fixtures outside Git under
`/Volumes/OWC_8TB/gpr_work/artifacts/fixtures`. CI uses synthetic fixtures, but
the workstation compatibility audit uses these files to catch real-world DNG/GPR
ingest regressions.

Run the audit with:

```bash
export GPR_EXTERNAL_ROOT=/Volumes/OWC_8TB/gpr_work
export GPR_ARTIFACT_ROOT=/Volumes/OWC_8TB/gpr_work/artifacts
GPR_TOOLS=./build-local/source/app/gpr_tools/gpr_tools \
  tools/test/test_real_fixture_compatibility.sh
```

## Canonical Fixtures

| Camera/input | Path | SHA-256 | Purpose |
| --- | --- | --- | --- |
| Nikon Z8 CFA DNG | `/Volumes/OWC_8TB/gpr_work/artifacts/fixtures/barn_sky_dngs/Z8Z_1349.dng` | `8fa53603100ed55076e13f7bacc87d8b32a56c363c2963f3b3121cce0a0a6930` | Stable 45MP Bayer DNG fixture for still/GPR roundtrip and Z8 compatibility. |
| Hasselblad X2D Adobe DNG | `/Volumes/OWC_8TB/gpr_work/artifacts/fixtures/x2d_dngs/2024_April_X2D_1742.dng` | `1fd421393bec2bdf9dbbdf72e22a8fbc27fbb1389e5d3557fa967b2c855e0c1c` | Stable 100MP-class Bayer DNG fixture for large-sensor compatibility. |
| iPhone 16 Pro Max Linear Raw DNG | `/Volumes/OWC_8TB/gpr_work/artifacts/fixtures/iphone_linear_raw/IMG_9270_iPhone16ProMax_LinearRaw.DNG` | `9826845edd2a8a2cd742ecf5e45a2907676f980f4fa39ac2998a49bf1b906ea4` | Negative fixture: must be rejected because it is not a single-plane CFA Bayer input. |

The Mission 1 fixtures remain in the photo library because the full local audit
needs both source `.GPR` and Adobe-converted DNG pairs:

| Camera/input | Default path | Purpose |
| --- | --- | --- |
| Mission 1 50MP DNG | `/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P/RawPics/DNG/GP017504.dng` | 50MP still/roundtrip compatibility. |
| Mission 1 12MP DNG | `/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P/RawPics/DNG/GP017602.dng` | Native 12MP Mission path compatibility. |
| Mission 1 50MP GPR | `/Volumes/Photos/DavidsPics/gopro_raw/2026-06__GoProM1P/RawPics/GP017504.GPR` | Camera `.GPR` decode compatibility. |

## Latest Receipt

Current local audit receipt:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/real_fixture_compatibility/receipt_20260628T060625Z.txt
```

Summary: 8 pass, 0 skip.

| Check | Fixture family | Current result |
| --- | --- | --- |
| Mission 1 50MP DNG roundtrip | Mission 1 | PASS |
| Mission 1 12MP DNG roundtrip | Mission 1 | PASS |
| Mission 1 50MP GPR roundtrip | Mission 1 | PASS |
| Z8 50MP DNG roundtrip | Nikon Z8 | PASS |
| X2D 100MP DNG roundtrip | Hasselblad X2D | PASS |
| iPhone CFA DNG roundtrip | iPhone | PASS |
| iPhone metadata roundtrip | iPhone | PASS |
| iPhone Linear Raw rejection | iPhone | PASS |

Current real Bayer phase discovery:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_20260630_rawpy/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_targeted_2000_20260630/index.html
/Volumes/OWC_8TB/gpr_work/artifacts/bayer_phase_fixture_discovery_broad_dng_gpr_3000_20260630/index.html
```

Summary: the broader local scan parsed 74 normal 2x2 Bayer DNG fixtures: 70
RGGB and 4 Mission 1 GBRG. The targeted GoPro/Mission/Hassel/iPhone raw scan
then parsed 2,000 local raw files as normal Bayer: 1,892 GBRG and 108 RGGB.
The newer targeted GoPro/Mission DNG/GPR scan parses 3,000 local files as
normal Bayer: 2,892 GBRG and 108 RGGB. GRBG and BGGR remain covered by
synthetic still conformance, but they still need real camera fixtures before
broad real-camera alternate-phase support should be claimed.

## Cleanup Boundary

Do not delete the canonical fixture paths above. Bulky experiment directories in
`/Volumes/OWC_8TB/gpr_work/artifacts` may be deleted only when they are not
referenced by repo docs/tests/manifests and their outputs are superseded by the
current release artifacts.
