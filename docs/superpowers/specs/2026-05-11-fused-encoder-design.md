# Fused Encoder Design — Stage B1

## Summary

Replace the 4-stage serial encoder pipeline (unpack → wavelet → tokenize → rANS) with a 2-pass fused design that eliminates 44MB of intermediate memory and fuses frequency counting into the wavelet output path.

## Pass 1: Fused Unpack→Wavelet→Quantize→FreqCount
- Streams raw Bayer through log curve → horizontal filter → 6-row buffer → vertical filter + quantize
- Counts ANS symbol frequencies inline as coefficients are produced
- Eliminates 4 component arrays (44MB for Z8 45MP)

## Pass 2: rANS Encode
- Re-scans quantized band data to regenerate tokens
- Uses pre-counted frequencies from Pass 1
- Identical rANS algorithm, just skips the frequency counting

## Target: GoPro ARM (Cortex-A78), Mac ARM64 as testbed
## Approach: C first, then ARM64 assembly port

## Files
- `source/lib/vc5_encoder/fused_encode.c` — C implementation
- `source/lib/vc5_encoder/fused_encode.h` — Public API
- `source/lib/vc5_encoder/fused_encode_arm64.S` — Assembly (future)
