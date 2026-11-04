#include "simple_s2mm.h"

s2mm_status s2mm_init(simple_s2mm *rx, const s2mm_ops *ops, void *context,
                      const void *cpu_buffer, size_t capacity, unsigned poll_limit)
{
    if (rx == NULL) return S2MM_BAD_CONFIG;
    *rx = (simple_s2mm){.status = S2MM_BAD_CONFIG, .owner = S2MM_DEVICE};
    if (ops == NULL || ops->restart == NULL || ops->for_device == NULL ||
        ops->for_cpu == NULL || ops->submit == NULL || ops->poll == NULL ||
        cpu_buffer == NULL || capacity < S2MM_PACKET_BYTES || poll_limit == 0)
        return rx->status;
    rx->ops = *ops;
    rx->context = context;
    rx->cpu_buffer = cpu_buffer;
    rx->poll_limit = poll_limit;
    rx->status = S2MM_NEEDS_RESTART;
    return rx->status;
}

s2mm_status s2mm_restart(simple_s2mm *rx)
{
    if (rx == NULL) return S2MM_BAD_CONFIG;
    if (rx->status == S2MM_BAD_CONFIG) return rx->status;
    /* A failed reset must not permit reuse, even if CPU owned the old payload. */
    rx->owner = S2MM_DEVICE;
    if (rx->ops.restart(rx->context, rx->poll_limit) != 0) {
        rx->restart_failed = true;
        if (rx->status == S2MM_OK || rx->status == S2MM_DONE ||
            rx->status == S2MM_NEEDS_RESTART) rx->status = S2MM_RESTART_ERROR;
        return rx->status;       /* Preserve the first failure and its evidence. */
    }
    rx->ops.for_cpu(rx->context);
    rx->owner = S2MM_CPU;
    fv_reset(&rx->validator, S2MM_FRAME_WORDS, 0);
    rx->last_event = (s2mm_event){0};
    rx->last_polls = 0;
    rx->restart_failed = false;
    rx->status = S2MM_OK;
    return rx->status;
}

s2mm_status s2mm_receive_frame(simple_s2mm *rx)
{
    if (rx == NULL) return S2MM_BAD_CONFIG;
    if (rx->status != S2MM_OK) return rx->status;
    rx->last_event = (s2mm_event){0};
    rx->last_polls = 0;
    rx->ops.for_device(rx->context);
    rx->owner = S2MM_DEVICE;
    if (rx->ops.submit(rx->context, S2MM_PACKET_BYTES) != 0) {
        rx->status = S2MM_SUBMIT_ERROR;
        return rx->status;
    }
    for (unsigned i = 0; i < rx->poll_limit; ++i) {
        rx->last_event = rx->ops.poll(rx->context);
        rx->last_polls++;
        if (rx->last_event.error) {
            rx->status = S2MM_DMA_ERROR;
            return rx->status;
        }
        if (rx->last_event.done) {
            if (rx->last_event.actual_bytes != S2MM_PACKET_BYTES) {
                rx->status = S2MM_BAD_LENGTH;
                return rx->status;   /* Do not sync/read an invalid payload. */
            }
            rx->ops.for_cpu(rx->context);
            rx->owner = S2MM_CPU;
            if (fv_feed(&rx->validator, rx->cpu_buffer,
                        rx->last_event.actual_bytes) != FV_OK)
                rx->status = S2MM_BAD_FRAME;
            return rx->status;
        }
    }
    rx->status = S2MM_TIMEOUT;
    return rx->status;           /* No automatic reset, requeue or buffer access. */
}

s2mm_status s2mm_finish(simple_s2mm *rx, uint64_t requested_frames)
{
    if (rx == NULL) return S2MM_BAD_CONFIG;
    if (rx->status != S2MM_OK) return rx->status;
    rx->status = fv_finish(&rx->validator, requested_frames) == FV_OK
                 ? S2MM_DONE : S2MM_BAD_FRAME;
    return rx->status;
}

const char *s2mm_status_name(s2mm_status status)
{
    switch (status) {
    case S2MM_OK: return "OK";
    case S2MM_DONE: return "DONE";
    case S2MM_NEEDS_RESTART: return "NEEDS_RESTART";
    case S2MM_BAD_CONFIG: return "BAD_CONFIG";
    case S2MM_SUBMIT_ERROR: return "SUBMIT_ERROR";
    case S2MM_DMA_ERROR: return "DMA_ERROR";
    case S2MM_TIMEOUT: return "TIMEOUT";
    case S2MM_BAD_LENGTH: return "BAD_LENGTH";
    case S2MM_BAD_FRAME: return "BAD_FRAME";
    case S2MM_RESTART_ERROR: return "RESTART_ERROR";
    default: return "UNKNOWN";
    }
}
