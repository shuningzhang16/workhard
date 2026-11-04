#ifndef SIMPLE_S2MM_H
#define SIMPLE_S2MM_H

#include "frame_validator.h"
#include <stdbool.h>

enum { S2MM_FRAME_WORDS = 7, S2MM_PACKET_BYTES = 28 };
typedef enum {
    S2MM_OK, S2MM_DONE, S2MM_NEEDS_RESTART, S2MM_BAD_CONFIG,
    S2MM_SUBMIT_ERROR, S2MM_DMA_ERROR, S2MM_TIMEOUT,
    S2MM_BAD_LENGTH, S2MM_BAD_FRAME, S2MM_RESTART_ERROR
} s2mm_status;
typedef enum { S2MM_CPU, S2MM_DEVICE } s2mm_owner;

typedef struct {
    bool done;                 /* Current submission completed; no further writes. */
    bool error;                /* Takes precedence over done. */
    size_t actual_bytes;       /* Only valid for a successful completion. */
    uint32_t raw_status;
} s2mm_event;

/* Single caller, one preallocated/mapped buffer, no background callback threads.
 * Every callback must return in bounded time. No callback may silently retry.
 * restart: reset/quiesce DMA AND reset source/FIFO to frame 0; 0 means confirmed.
 * It must use at most poll_limit reset-status polls. Failure may leave DMA active.
 * for_device/for_cpu: platform cache/ownership operations over the whole isolated
 * allocation. Only for_cpu exposes completed bytes to the CPU.
 * submit: exactly 28 bytes, 0 on accepted; clear stale completion before starting.
 * poll: observe current request once; no implicit cache access or recovery.
 * CPU pointer and DMA address are distinct; the platform context owns mapping.
 */
typedef struct {
    int (*restart)(void *context, unsigned poll_limit);
    void (*for_device)(void *context);
    void (*for_cpu)(void *context);
    int (*submit)(void *context, size_t bytes);
    s2mm_event (*poll)(void *context);
} s2mm_ops;

typedef struct {
    s2mm_ops ops;
    void *context;
    const uint8_t *cpu_buffer;
    unsigned poll_limit;
    s2mm_status status;
    s2mm_owner owner;
    frame_validator validator;
    s2mm_event last_event;
    unsigned last_polls;
    bool restart_failed;
} simple_s2mm;

/* Initialize once, before use. Never reinitialize a live receiver to clear an
 * error. The buffer must remain allocated/mapped even after timeout or failure.
 * No I/O here; explicit restart is required before the first packet.
 */
s2mm_status s2mm_init(simple_s2mm *rx, const s2mm_ops *ops, void *context,
                      const void *cpu_buffer, size_t capacity, unsigned poll_limit);
s2mm_status s2mm_restart(simple_s2mm *rx);
s2mm_status s2mm_receive_frame(simple_s2mm *rx);
s2mm_status s2mm_finish(simple_s2mm *rx, uint64_t requested_frames);
const char *s2mm_status_name(s2mm_status status);

#endif
