#include "daq_session.h"

static int read_register(daq_session *s, unsigned offset, uint32_t *value)
{
    if (s->registers.read(s->context, offset, value) == 0) return 0;
    s->register_failed = true;
    return -1;
}
static int write_register(daq_session *s, unsigned offset, uint32_t value)
{
    if (s->registers.write(s->context, offset, value) == 0) return 0;
    s->register_failed = true;
    return -1;
}
static int reset_epoch(void *context, unsigned limit)
{
    daq_session *s = context;
    if (s->dma_ops.restart(s->context, limit) != 0) return -1;
    for (unsigned i = 0; i < limit; ++i) {
        if (read_register(s, DAQ_STATUS, &s->last_control_status) != 0) return -1;
        if ((s->last_control_status & 3U) == 0) {
            /* Explicit source epoch reset, while confirmed stopped. */
            return write_register(s, DAQ_COMMAND, 1);
        }
    }
    return -1;
}
static void for_device(void *context)
{
    daq_session *s = context;
    s->dma_ops.for_device(s->context);
}
static void for_cpu(void *context)
{
    daq_session *s = context;
    s->dma_ops.for_cpu(s->context);
}
static int submit(void *context, size_t bytes)
{
    daq_session *s = context;
    if (s->dma_ops.submit(s->context, bytes) != 0) return -1;
    if (s->start_pending) {
        // The DMA's stream reset may remain asserted until the channel starts.
        // Arm DMA first, observe reset release through the live control bus.
        for (unsigned i = 0; i < s->receiver.poll_limit; ++i) {
            if (read_register(s, DAQ_STATUS, &s->last_control_status) != 0) return -1;
            if ((s->last_control_status & 4U) == 0) {
                if (write_register(s, DAQ_CONTROL, 1) != 0) return -1;
                s->start_pending = false;
                return 0;
            }
        }
        s->register_failed = true;
        return -1;
    }
    return 0;
}
static s2mm_event poll_once(void *context)
{
    daq_session *s = context;
    return s->dma_ops.poll(s->context);
}
static const s2mm_ops bridge = {reset_epoch, for_device, for_cpu, submit, poll_once};

daq_status daq_init(daq_session *s, const s2mm_ops *dma, const daq_register_ops *registers,
                    void *context, const void *buffer, size_t capacity, unsigned poll_limit)
{
    if (s == NULL) return DAQ_CONFIG_ERROR;
    *s = (daq_session){.status = DAQ_CONFIG_ERROR};
    if (dma == NULL || registers == NULL || registers->read == NULL || registers->write == NULL ||
        dma->restart == NULL || dma->for_device == NULL || dma->for_cpu == NULL ||
        dma->submit == NULL || dma->poll == NULL) return s->status;
    s->dma_ops = *dma;
    s->registers = *registers;
    s->context = context;
    if (s2mm_init(&s->receiver, &bridge, s, buffer, capacity, poll_limit) != S2MM_NEEDS_RESTART)
        return s->status;
    s->status = DAQ_NEEDS_RESTART;
    return s->status;
}

daq_status daq_restart(daq_session *s)
{
    if (s == NULL) return DAQ_CONFIG_ERROR;
    if (s->status == DAQ_CONFIG_ERROR) return s->status;
    daq_status previous = s->status;
    s->register_failed = false;
    if (s2mm_restart(&s->receiver) != S2MM_OK) {
        if (previous < DAQ_CONFIG_ERROR)
            s->status = s->register_failed ? DAQ_REGISTER_ERROR : DAQ_RECEIVE_ERROR;
        return s->status;           /* Existing session/receiver errors remain latched. */
    }
    s->start_pending = true;
    s->last_frames = 0;
    s->drained = 0;
    s->status = DAQ_OK;
    return s->status;
}

daq_status daq_receive(daq_session *s)
{
    if (s == NULL) return DAQ_CONFIG_ERROR;
    if (s->status != DAQ_OK) return s->status;
    if (s2mm_receive_frame(&s->receiver) != S2MM_OK)
        s->status = s->register_failed ? DAQ_REGISTER_ERROR : DAQ_RECEIVE_ERROR;
    return s->status;
}

daq_status daq_request_stop(daq_session *s)
{
    if (s == NULL) return DAQ_CONFIG_ERROR;
    if (s->status != DAQ_OK) return s->status;
    if (write_register(s, DAQ_CONTROL, 0) != 0) return s->status = DAQ_REGISTER_ERROR;
    s->start_pending = false;      /* A drain submission must never cancel STOP. */
    s->drained = 0;
    return s->status;
}

daq_status daq_check_stop(daq_session *s, uint64_t requested_frames)
{
    if (s == NULL) return DAQ_CONFIG_ERROR;
    if (s->status != DAQ_OK) return s->status;
    if (read_register(s, DAQ_STATUS, &s->last_control_status) != 0 ||
        read_register(s, DAQ_FRAMES, &s->last_frames) != 0)
        return s->status = DAQ_REGISTER_ERROR;
    uint64_t complete = s->receiver.validator.complete_frames;
    if (s->last_control_status == 0) {
        if (s->last_frames < complete) return s->status = DAQ_COUNT_ERROR;
        if (s->last_frames == complete) {
            s->status = s2mm_finish(&s->receiver, requested_frames) == S2MM_DONE
                        ? DAQ_DONE : DAQ_RECEIVE_ERROR;
        }
    }
    return s->status;
}

daq_status daq_stop(daq_session *s, uint64_t requested_frames, unsigned max_drain)
{
    if (daq_request_stop(s) != DAQ_OK) return s == NULL ? DAQ_CONFIG_ERROR : s->status;
    for (;;) {
        if (daq_check_stop(s, requested_frames) != DAQ_OK) return s->status;
        if (s->drained == max_drain) return s->status = DAQ_STOP_LIMIT;
        if (daq_receive(s) != DAQ_OK) return s->status;
        s->drained++;
    }
}

const char *daq_status_name(daq_status status)
{
    switch (status) {
    case DAQ_OK: return "OK";
    case DAQ_DONE: return "DONE";
    case DAQ_NEEDS_RESTART: return "NEEDS_RESTART";
    case DAQ_CONFIG_ERROR: return "CONFIG_ERROR";
    case DAQ_REGISTER_ERROR: return "REGISTER_ERROR";
    case DAQ_RECEIVE_ERROR: return "RECEIVE_ERROR";
    case DAQ_STOP_LIMIT: return "STOP_LIMIT";
    case DAQ_COUNT_ERROR: return "COUNT_ERROR";
    default: return "UNKNOWN";
    }
}
