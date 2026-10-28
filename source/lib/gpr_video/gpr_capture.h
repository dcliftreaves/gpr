/* SPDX-License-Identifier: Apache-2.0 OR MIT */
#ifndef GPR_CAPTURE_H
#define GPR_CAPTURE_H
#include "gpr_gvid.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef struct gpr_capture gpr_capture;
enum {
    GPR_CAPTURE_OK = 0, GPR_CAPTURE_INVALID = -1,
    GPR_CAPTURE_BUSY = -2, GPR_CAPTURE_CLOSED = -3,
    GPR_CAPTURE_CANCELLED = -4, GPR_CAPTURE_CODEC = -5,
    GPR_CAPTURE_WRITER = -6, GPR_CAPTURE_NOMEM = -7
};
typedef struct {
    gpr_gvid_config video; /* Capture requires width/height >=48, in addition to framing limits. */
    uint32_t stride_bytes;
    uint32_t max_inflight; /* 1..16, counts raw+encoding+encoded+writing together. */
    size_t workspace_bytes; /* 0: malloc; otherwise first-touched reusable arena. */
    const void *metadata;
    size_t metadata_size;
} gpr_capture_config;
typedef void (*gpr_capture_release_fn)(void *user);
typedef struct {
    const void *data;
    size_t size_bytes;
    uint64_t index, timestamp_ns;
    const void *metadata;
    size_t metadata_size;
    /* Optional input lease: packed rows only. On success the caller retains
     * the buffer unchanged until release(user) runs exactly once on the codec
     * thread, including cancellation/error. On rejection ownership stays with
     * the caller and release is NOT called. Metadata is always copied.
     * Release may call get_stats, but not submit/flush/finish/destroy.
     */
    gpr_capture_release_fn release;
    void *release_user;
} gpr_capture_frame;
typedef struct {
    uint64_t index, timestamp_ns, payload_bytes, encode_ns, write_ns;
} gpr_capture_completion;
/* Writer/completion run on the storage thread, outside internal locks.
 * Write returns 0 only after accepting ALL bytes; bytes expire on return.
 * Callbacks may call get_stats, but must not call submit/flush/finish/destroy.
 * Cancellation cannot interrupt a blocked application callback.
 */
typedef int (*gpr_capture_write_fn)(void *user, const uint8_t *bytes, size_t size);
typedef void (*gpr_capture_complete_fn)(void *user, const gpr_capture_completion *frame);
typedef struct {
    gpr_capture_write_fn write;
    gpr_capture_complete_fn complete;
    void *user;
} gpr_capture_callbacks;
typedef struct {
    uint64_t submitted, encoded, written, discarded, payload_bytes;
    uint64_t inflight, inflight_high_water, encode_ns, write_ns, submit_wait_ns;
    uint64_t workspace_peak_bytes, workspace_fallback_peak_bytes;
    int error;
} gpr_capture_stats;

int gpr_capture_create(const gpr_capture_config *cfg, const gpr_capture_callbacks *callbacks,
                       gpr_capture **out);
/* Thread-safe; submissions serialize in frame-index order. Input and metadata
 * are COPIED before success returns unless an input lease is supplied; copied
 * input includes repacking padded rows. Index is
 * contiguous from 0, timestamps strictly increase. Failed submits consume no
 * index. timeout_ms=0 is nonblocking; UINT32_MAX waits without a deadline.
 * Input is unpacked native-endian uint16 within the declared sample range.
 * Sensor/capture threads choose whether to wait, retry or record an overrun.
 */
int gpr_capture_submit(gpr_capture *capture, const gpr_capture_frame *frame, uint32_t timeout_ms);
/* Drain accepted work. Caller owns filesystem durability. Flush allows later
 * submissions; finish closes submission, drains, writes END3 and waits until
 * both workers stop. No callback occurs after finish returns, even on error.
 */
int gpr_capture_flush(gpr_capture *capture);
int gpr_capture_finish(gpr_capture *capture);
void gpr_capture_cancel(gpr_capture *capture);
void gpr_capture_destroy(gpr_capture *capture);
int gpr_capture_get_stats(gpr_capture *capture, gpr_capture_stats *out);
#ifdef __cplusplus
}
#endif
#endif
