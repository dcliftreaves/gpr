# Stock decoder argument and allocator boundaries

The public `vc5_decoder_process` entry now rejects absent parameters/input,
missing allocator callbacks, aliased or simultaneous RAW/RGB output descriptors,
short/non-word-aligned/non-VC-5 input, unsupported RGB settings and gain shifts
before allocating or reading the stream. The legacy CLI now explicitly requests
the RAW-only path it writes.

`tests/decoder_bounds.c` checks these rejections with a denying allocator,
then decodes the independent 128×96 stock VC-5 fixture to RAW and 16-bit RGB.
It also fails each allocation in turn and checks the returned error, empty
caller output and zero outstanding tracked allocations: **138 RAW positions and
73 RGB positions** with this fixture. These numbers describe this input and
build, not a fixed count across codec profiles or compiler settings.

The test first reproduced three actual allocator bugs: the first failed
`CreateWavelet` allocation aborted on an assertion; a later failed inverse
scratch allocation wrote through a null pointer; and a failed component array
allocation aborted on another assertion. The decoder now propagates these
out-of-memory errors through wavelet reconstruction, releases partial arrays
and transforms, and checks the final RAW/RGB allocation before returning.
ASan/UBSan testing exercises each failure position and leak detection on Pi 5.

On 2026-10-29, the full Mac Release suite passed **21/21** tests and the full
Pi 5 Release suite passed **19/19**. The selected Pi ASan/UBSan/leak-detection
test passed in **5.01 s**; the same target passed local ASan/UBSan. All four
relocated package profiles passed their independent C/C++ client checks. The
legacy decoder CLI decoded the stock fixture to a 24,576-byte RAW image after
its output-mode correction; a four-byte invalid input now exits with a decode
error instead of asserting that RAW output was produced.

This is an allocator and public-call boundary audit. It does **not** prove
arbitrary malformed VC-5 entropy data is safe, that all legacy SDK error paths
are leak free, or that the full SDK is thread safe. Camera preview separately
validates its strict stock payload structure before entering this decoder.
