/*
 * rans_decode_arm64.S — ARM64 assembly rANS Pass 1 decode
 *
 * Full rANS state update + renorm + token extraction in assembly.
 * Eliminates compiler register allocation inefficiency by dedicating
 * callee-saved registers to hot state:
 *
 *   w19-w22: rANS states[0-3]
 *   x23: decode_info base
 *   x24: rANS byte pointer
 *   x25: resid data pointer + byte_pos (computed)
 *   w26: resid bit_pos
 *   x27: runs output pointer
 *   x28: values output pointer
 *
 * int rans_pass1_asm(
 *   x0 = decode_info base
 *   x1 = rptr (in), updated on stack on return
 *   w2 = token_count
 *   x3 = runs output
 *   x4 = values output
 *   x5 = resid_data
 *   w6 = resid_size
 *   x7 = state_io (uint32_t[4], read initial states, write final)
 *   [sp+0] = resid_byte_bit (uint64_t* — packed: lo32=byte_pos, hi32=bit_pos)
 * )
 * Returns: pair_count in w0, or -1 on error
 */

#ifdef __aarch64__

.text
.globl _rans_pass1_asm
.p2align 4

_rans_pass1_asm:
    /* Stub — return -1 for C fallback */
    mov w0, #-1
    ret

#endif
