# Security Policy

## Reporting a vulnerability

If you believe you have found a security vulnerability in GPR, **please
do not open a public GitHub issue.** Instead, use one of the following
private channels:

- **Preferred: GitHub Security Advisory.** From the repository's
  Security tab, choose "Report a vulnerability". GitHub will create a
  private advisory shared only with the maintainers and the reporter.
- **Email backup.** If you cannot use GitHub Security Advisories, email
  the maintainers privately (contact via the addresses listed in
  `AUTHORS.md`). Use a subject line that begins with `[GPR SECURITY]`.

Please include:

- A description of the vulnerability and the impact you believe it has.
- Steps to reproduce, ideally with a minimal sample input file or a
  failing test invocation.
- The git commit / release tag you reproduced against.
- Your name and affiliation if you would like to be credited in the
  advisory, or a note that you wish to remain anonymous.

We will acknowledge receipt within 5 business days and provide an
initial assessment within 10 business days.

## Disclosure timeline

We follow a **90-day coordinated-disclosure policy**:

1. We confirm the report and reproduce the issue.
2. We develop a fix on a private branch and validate it against the
   reporter's test case.
3. We coordinate a public disclosure date with the reporter, normally
   within 90 days of the original report. If the issue is being
   actively exploited or requires a longer fix window, we will discuss
   adjusting the date.
4. We publish the fix, the advisory, and credit the reporter (unless
   they have asked to remain anonymous).

Reporters who follow this policy and refrain from public disclosure
until the coordinated date will be credited in the advisory and the
release notes.

## Scope

The components below are in scope. Reports of vulnerabilities in any
of these are welcome.

- **Decoder code paths** under `source/lib/vc5_decoder/`,
  `source/lib/gpr_sdk/`, and the standalone `vc5_decoder_app`. These
  consume **untrusted input**: a GPR / VC-5 / GVID bitstream that may
  have been crafted by an attacker. Memory-safety issues, infinite
  loops, integer overflows that can be reached from a malformed
  bitstream, and out-of-bounds reads/writes during decode are in
  scope.
- **Container parsing** in `source/lib/vc5_encoder/gpr_video_format.h`
  / `gpr_video_format.c` and any code that reads `'GVID'` / `'FRM\0'`
  headers from untrusted bytes.
- **DNG container parsing** under `source/lib/dng_sdk/` and the XMP /
  expat code paths that handle metadata from potentially-untrusted
  files.
- **gpr_tools** and the sample applications as command-line tools
  given untrusted file inputs.

## Out of scope

- **Encoder code paths** under `source/lib/vc5_encoder/` (including
  `fused_encode.c`, `gpr_video.c`, and the NEON / ARM64 assembly
  paths). The encoder operates on **trusted input** — raw Bayer
  pixels supplied by a camera or trusted upstream component. We do
  not consider crashes or memory-safety issues triggered by pixel
  values that a calibrated sensor would not produce to be
  vulnerabilities. We do welcome reports of issues that could be
  reached via the public API surface from untrusted code in the
  same process — for example, integer overflow on user-supplied
  width / height parameters — but the threat model is much narrower
  than for the decoder.
- **Patent or licensing claims.** See `PATENTS.md` and
  `docs/raw-video-landscape.md` for the patent posture. Patent
  notifications should be sent through the normal contact addresses,
  not through the security channel.
- **Build-system or test-harness bugs** that do not affect produced
  binaries.

## Supported versions

| Version | Status | Security fixes |
|---|---|---|
| 2.0.x (current) | Active | Yes |
| 1.0.x | Maintenance | Critical only, until 2027-01-01 |
| < 1.0 | Unsupported | No |

Security fixes for 2.0.x are released as patch versions (2.0.1, 2.0.2, …)
on the default branch. Critical fixes for 1.0.x are backported when the
issue applies to the older stills-only codebase.

## Past advisories

None at this time. Once advisories exist, they will be linked from this
section and from `CHANGELOG.md`.
