# Production 100 Percent Work Order

Last refreshed: 2026-07-02

This is the unambiguous work order. Work counts only when it creates or
validates the named receipt. A dashboard, note, training log, or visual review
does not move the project unless it is referenced by that receipt.

## Stop Rule

Continue from the first open local row. Stop only when one of these is true:

1. The row's receipt exists, validates, is linked from the release evidence or
   production artifact docs, and CI is green after push.
2. The row is proven externally blocked, with the blocking condition recorded in
   the row's receipt.
3. CI fails, in which case fixing CI becomes the only active row.

## Ordered Rows

| order | row | status | done means |
|---:|---|---|---|
| 1 | CI and repo hygiene | closed/protect | Latest pushed `master` GitHub Actions run passes; sensitive-content, artifact-hygiene, README, manifest, and product-lock guards pass locally before push. |
| 2 | RAW video reconstruction | closed/protect | Approved 4K cleanup and 8K SR receipts stay locked and green. Do not reopen for PSF research or dashboard cosmetics. |
| 3 | Premium still/SR Gate 14 selector | closed/protect | Gate 14 sidecar reloads, recomputes candidate-only runtime features, verifies source/checkpoint hashes, routes deterministically, and matches intake. |
| 4 | Premium still/SR promotion | open/local | `premium_still_sr_promotion_receipts` proves 50 MP and 100 MP no-REF quality, nonnegative worst rows, editor/openability, timing/memory, checkpoint hashes, exact-sidecar-only noise policy, and production submission validation. |
| 5 | RAW stills noise sidecars | open/sample | Mission 1 and iPhone each have four strict-provenance true darkframes and production-ready camera-noise sidecars. |
| 6 | Mission 1 raw-video camera role | blocked/external | GoPro/Mission 1 firmware owner runs real sensor/DMA or camera ring-buffer source, SD writer, rear display, valid `.gvid`, zero drops, memory, and 120+ sustained frames at the accepted 20+ fps floor. |

## Current First Open Row

The first open local row is **Premium still/SR promotion**.

The next exact receipt is:

```text
/Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_20260702/premium_still_sr_promotion_receipts.json
```

That receipt may say production is still blocked, but it must classify the
blocker. Acceptable blocker classes are:

- `model_promotion_floor_not_met`
- `full_50mp_100mp_gate_missing`
- `worst_row_tail_regression`
- `editor_openability_missing`
- `timing_memory_missing`
- `checkpoint_or_sidecar_drift`
- `noise_policy_not_wired`
- `production_submission_missing_or_failed`
- `external_mission1_camera_role_access`

## Commands For The Current Row

```bash
python3 tools/build_premium_still_sr_promotion_receipts.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_receipts_20260702

python3 tools/check_premium_still_sr_promotion_gate.py \
  --output-dir /Volumes/OWC_8TB/gpr_work/artifacts/premium_still_sr_promotion_gate_current_20260702

python3 tools/test/check_production_capture_requirements.py
python3 tools/test/check_release_evidence_manifest.py
python3 tools/test/check_sensitive_content.py
```

Do not move to Mission/iPhone darkframes until this row has either a production
receipt or a specific machine-readable blocker receipt.
