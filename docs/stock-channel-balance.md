# Encoder channel balance diagnostic

A private instrumented build of `40aa476` measures each channel's combined
forward-transform/incremental-entropy wall and thread CPU time. Channel 0 is
usually the critical worker in the unrestricted replay. This is evidence for
investigating finer-grained work distribution, not an implemented speedup or
a passing recording deadline result. Production source is unchanged.

## Method and correctness

The existing `GPR_PROFILE` channel print is bypassed by the direct-band return
used in capture, so it cannot measure this path as written. The private patch
records start/finish and `CLOCK_THREAD_CPUTIME_ID` before that return. The
parent prints four records only after all joins, avoiding concurrent worker
logging. Thread start offsets include dispatch and private stream setup;
reported worker CPU excludes that setup. The combined worker interval includes
both wavelet transform and incremental entropy coding and final band flushes.

Two separate 120-frame runs exercise the frozen alternating 12 MP inputs with
the production capture/preview options, first unrestricted and then with the
existing opt-in channel affinity. A third run samples user cycles at 199 Hz.
All three runs independently verify 120 payloads and 120 calibrated previews,
source metadata and the end marker. The private build's five registered preview
tests pass. These instrumented short runs do not replace production Release,
package or sustained acceptance evidence.

## Observations

| Channel | Unrestricted median CPU ms | Unrestricted median wall ms | Last to finish, of 120 |
|---|---:|---:|---:|
| 0 | 28.741 | 28.887 | 99 |
| 1 | 24.366 | 24.490 | 7 |
| 2 | 24.472 | 24.631 | 13 |
| 3 | 23.836 | 24.475 | 1 |

Median start offsets are 0.056–0.068 ms. The median time between the final
worker completion and completed joins is 0.015 ms. These measurements do not
justify treating thread creation/join overhead as the primary explanation of
the roughly four-ms pooled channel imbalance.

Pinning does not consistently resolve that imbalance: channel 0 finishes last
in 62/120 frames, with 27.839 ms median CPU and 29.097 ms wall time. Other
workers finish last more often. Input-specific results differ: source 0 still
has about 29.4 ms of channel-0 CPU versus about 24.6–25.1 ms on other channels;
source 1 is more balanced when pinned. Pooled medians must not be interpreted
as a fixed per-frame saving or an affinity recommendation.

The separate process-wide sampled profile has no lost samples and attributes
26.82% to `EncodeHighpassIncremental.constprop.1`, 15.68% to the assembly unpack
kernel, 11.81% to `ForwardWaveletTransform`, 10.18% to wavelet display rows,
8.16% to inverse spatial reconstruction and 5.68% to horizontal filtering.
This includes setup and preview and does not attribute individual symbols to
channel 0. The annotated entropy assembly is retained for further inspection.

## Next architectural investigation

Measure channel/stage-specific entropy cost before changing scheduling. The
current direct-band worker interleaves filtering and entropy coding and gives
one whole channel to each worker. If channel 0's excess is concentrated in
entropy, bounded band/row jobs might let workers that finish other channels
help it. Any such design must preserve row ordering, pending zero-run state,
private output ownership, bounded scratch and exact historical payloads. It
must then beat matched full-capture controls; aggregate sample percentages
alone do not establish that this scheduling change is worthwhile.

[Diagnostic protocol](stock-channel-balance-receipts/diagnostic/protocol.json),
[verified results](stock-channel-balance-receipts/diagnostic/receipt.json),
[per-source breakdown](stock-channel-balance-receipts/source-breakdown.json),
[sampled protocol](stock-channel-balance-receipts/sampled/protocol.json),
[sampled verification](stock-channel-balance-receipts/sampled/receipt.json) and
[hot-symbol report](stock-channel-balance-receipts/sampled/report.txt)
retain the scope and identities. Apply `diagnostic.patch` to `40aa476`, build
with the commands in `build-commands.json`, and adapt external paths in `diagnose.py`
and `profile.py` to reproduce. Raw samples and media remain under
`/Volumes/OWC_8TB/gpr_work/artifacts/stock_channel_balance_20261030` and the
matching Pi directory. The private patch is not included in production.
