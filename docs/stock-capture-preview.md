# Capture with bounded asynchronous calibrated preview

`gpr_preview_queue.h` connects recording to a caller-supplied RGB sink. The
recorder offers an already-written stock VC-5 payload with its immutable source
plan, frame index and capture timestamp. The queue copies compressed bytes
before returning and retains the plan. RAW leases and writer-owned compressed
buffers may then expire normally.

There is one active frame and one latest pending frame. A newer offer replaces
pending preview work. It cannot interrupt rendering or a sink callback already
in progress. Offers do not wait for the renderer/sink; a short mutex covers
the bounded payload copy and bookkeeping. Preview still competes with capture
for CPU and memory bandwidth.

## Library ownership and failures

- Create reserves two compressed buffers and one RGB buffer within configured
  capacities (each 1..128 MiB). Decoder scratch and retained calibration plans
  have separate memory costs. The application controls its number of plans.
- An accepted offer owns its copy and plan reference. Indices/timestamps must
  strictly increase; gaps are allowed. Rejected offers acquire no ownership.
  `plan_retain` shares ownership; `plan_destroy` releases one reference.
- The sink runs on the preview thread outside queue locks. RGB is borrowed
  until callback return. The sink may query statistics but must not call offer,
  finish or destroy. Its context must live through finish/destroy.
- Callback failure/exception latches `GPR_PREVIEW_CALLBACK`; decoder errors
  propagate. Pending work is discarded; later offers return the latched error.
  Applications decide whether this also ends recording.
- Finish closes offers, drains the latest image and waits for callbacks.
  Concurrent finish callers are supported. Cancel closes/discards pending work;
  active work/callbacks may still finish. Destroy cancels, waits and joins, and
  must be serialized against all callers.
- Once drained, `offered == rendered + discarded`; replacements are a subset
  of discarded images. Inflight is at most two. Rendered means sink acceptance,
  without a claim that a physical screen presented the image.

`background=1` requests lower worker priority: Linux thread nice at least 10,
macOS utility QoS or Windows below-normal priority. It never raises an already
lower priority and does not change encoder priority. Statistics distinguish
requested/applied settings; unsupported/rejected requests report applied zero.
No realtime privileges are required.

## Capture frontend

Build `gpr_capture_app` with both capture and preview. Supply one prepared pure
`.gprp` profile per RAW source in input order:

```sh
build-runtime/gpr_capture_app \
  --input a.raw --input b.raw \
  --source-metadata a.json --source-metadata b.json \
  --preview-profile a.gprp --preview-profile b.gprp \
  --preview-every 3 --quality 3 --frames 900 --paced --leased \
  --output new-recording.gvid
```

Use the [host preparer](stock-calibrated-preview.md) or equivalent source
parameters. Pure profiles are reusable for their RAW/calibration pair. Offline
`.gprp.bind` files bind an existing recording and are not loaded for a new
capture. The caller supplies matching calibration. Changing camera WB/matrices
currently requires another plan; these two-fixed-source tests do not establish
rapid dynamic-calibration preparation cost.

The frontend keeps the original source/profile association after overruns.
Its sink computes RGB CRCs in memory, with frame identity, geometry and render,
capture-to-sink and overlap measurements. There is no physical display backend.
Background priority is the default; `--preview-foreground` enables comparison.
`--preview-delay-ms`/`--preview-fail-after` simulate a slow/failing sink.

Sink failure stops preview offers while recording continues through END3 and
fsync. The frontend prints the complete capture summary, then exits nonzero to
report preview failure. Preview events/summary precede the existing final
capture summary. Durable capture FPS includes fsync; remaining preview drain
and setup/precomputation time are reported separately.

## Pi 5 measurements

Two alternating supplied 4096x3072 RGGB14 sources, their individual calibration,
stock Q3, leased inputs, four capture slots, 192 MiB workspace, nominal 30 fps
paced replay and USB SSD. Each sustained run attempts 900 frames over 30 seconds
with final fsync. This is one matched run sequence, not a statistical overhead
estimate. Preview requests occur every third accepted frame.

| Preview | Recorded / attempted | Buffered / durable fps | Encode median ms | Late completions | Preview count / median render ms |
|---|---:|---:|---:|---:|---:|
| Disabled | 888 / 900 | 29.60 / 28.44 | 28.46 | 413 | — |
| 512x384, background | 875 / 900 | 29.16 / 28.13 | 33.05 | 871 | 292 / 54.42 |
| 256x192, background | 890 / 900 | 29.67 / 28.65 | 30.67 | 528 | 297 / 3.87 |

All requested previews rendered. The smaller preview has much lower processing
cost. Differences in accepted counts include scheduling/storage variability;
they do not establish a capture speed benefit from enabling preview.
Capture-to-sink p95 was 196.52/138.33 ms at 512x384/256x192. Peak RSS was about
510.7/534.8/521.7 MB; final flush took 1.23/1.10/1.07 seconds. Late completion
means write completion more than one nominal frame period after actual submit;
nominal sensor scheduling jitter is not separately measured.

An earlier 120-attempt comparison accepted 120 frames with background preview
and 114 foreground. Background rendering took longer (36.81 vs 28.52 ms median)
while yielding CPU to capture, but still had 71 late completions. The sustained
runs supersede any inference of reliable 30 fps from that short experiment.

Neither baseline nor combined runs establish reliable live 30 fps. Both Pi HDMI
connectors were disconnected. Sensor capture, physical presentation, microSD,
CNN inference and full thermal qualification remain unverified. The governor
was performance at an observed 2.4 GHz. An environment snapshot had a historical
soft-temperature-limit flag and no current throttle flags; per-frame frequency
and temperature were not recorded throughout the runs.

## Verification

The queue test gates callbacks to prove replacement, copied payload/retained
plan lifetime, concurrent finish, cancellation, capacity rejection and sticky
sink/decoder errors. Combined tests record copied/leased inputs, force overruns
and sink failure, verify complete recordings and compare all delivered pixels
against offline playback using each recorded frame's actual calibration.
Installed C/C++ clients create/drain a queue and verify delivery after releasing
the caller's plan reference.

Real-source receipts are in `stock-capture-preview-receipts/`. Verification
checks complete CRC/END3 framing, every accepted payload, exact source
calibration and every preview's timestamp, source, payload CRC and offline RGB
CRC. Separate Q3 encodes use the earlier upstream stock build, identified by
probe/library hashes. Sanitizer/package receipts state exact scope/revisions.
