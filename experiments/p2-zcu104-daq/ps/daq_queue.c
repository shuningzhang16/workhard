#include "daq_queue.h"
#include <string.h>

dq_status dq_init(daq_queue *q, daq_session *session, unsigned capacity)
{
    if (q == NULL) return DQ_BAD_CONFIG;
    *q = (daq_queue){.status = DQ_BAD_CONFIG};
    if (session == NULL || capacity == 0 || capacity > DAQ_QUEUE_MAX_PACKETS)
        return q->status;
    q->session = session;
    q->capacity = capacity;
    q->status = DQ_NEEDS_RESTART;
    return q->status;
}

dq_status dq_restart(daq_queue *q)
{
    if (q == NULL) return DQ_BAD_CONFIG;
    if (q->status == DQ_BAD_CONFIG) return q->status;
    if (q->count != 0 || q->borrowed) return DQ_PENDING;
    if (daq_restart(q->session) != DAQ_OK) {
        if (q->status != DQ_STOP_LIMIT) q->status = DQ_RECEIVE_ERROR;
        return q->status;
    }
    q->head = 0;
    q->high_water = 0;
    q->produced = q->consumed = q->full_returns = 0;
    q->drain_limit = q->drained = 0;
    q->requested_frames = 0;
    q->stopping = false;
    q->status = DQ_OK;
    return q->status;
}

dq_status dq_produce(daq_queue *q)
{
    if (q == NULL) return DQ_BAD_CONFIG;
    if (q->status != DQ_OK) return q->status;
    if (q->count == q->capacity) {
        q->full_returns++;
        return DQ_FULL;
    }
    if (q->stopping) {
        daq_status state = daq_check_stop(q->session, q->requested_frames);
        if (state == DAQ_DONE) return q->status = DQ_DONE;
        if (state != DAQ_OK) return q->status = DQ_RECEIVE_ERROR;
        if (q->drained == q->drain_limit) return q->status = DQ_STOP_LIMIT;
    }
    if (daq_receive(q->session) != DAQ_OK) return q->status = DQ_RECEIVE_ERROR;
    unsigned tail = (q->head + q->count) % q->capacity;
    memcpy(q->packets[tail].bytes, q->session->receiver.cpu_buffer, S2MM_PACKET_BYTES);
    q->count++;
    q->produced++;
    if (q->count > q->high_water) q->high_water = q->count;
    if (q->stopping) q->drained++;
    return DQ_OK;
}

dq_status dq_request_stop(daq_queue *q, uint64_t requested_frames, unsigned max_drain)
{
    if (q == NULL) return DQ_BAD_CONFIG;
    if (q->status != DQ_OK) return q->status;
    if (q->stopping) return DQ_PENDING;
    if (daq_request_stop(q->session) != DAQ_OK) return q->status = DQ_RECEIVE_ERROR;
    q->stopping = true;
    q->requested_frames = requested_frames;
    q->drain_limit = max_drain;
    q->drained = 0;
    return DQ_OK;
}

dq_status dq_borrow(daq_queue *q, const dq_packet **packet)
{
    if (q == NULL || packet == NULL || q->status == DQ_BAD_CONFIG) return DQ_BAD_CONFIG;
    *packet = NULL;
    if (q->borrowed) return DQ_BORROWED;
    if (q->count == 0) return DQ_EMPTY;
    q->borrowed = true;
    *packet = &q->packets[q->head];
    return DQ_OK;
}

dq_status dq_release(daq_queue *q)
{
    if (q == NULL || q->status == DQ_BAD_CONFIG) return DQ_BAD_CONFIG;
    if (!q->borrowed) return DQ_EMPTY;
    q->borrowed = false;
    q->head = (q->head + 1) % q->capacity;
    q->count--;
    q->consumed++;
    return DQ_OK;
}

const char *dq_status_name(dq_status status)
{
    switch (status) {
    case DQ_OK: return "OK";
    case DQ_FULL: return "FULL";
    case DQ_EMPTY: return "EMPTY";
    case DQ_BORROWED: return "BORROWED";
    case DQ_PENDING: return "PENDING";
    case DQ_DONE: return "DONE";
    case DQ_NEEDS_RESTART: return "NEEDS_RESTART";
    case DQ_BAD_CONFIG: return "BAD_CONFIG";
    case DQ_RECEIVE_ERROR: return "RECEIVE_ERROR";
    case DQ_STOP_LIMIT: return "STOP_LIMIT";
    default: return "UNKNOWN";
    }
}
