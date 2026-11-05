#ifndef DAQ_QUEUE_H
#define DAQ_QUEUE_H

#include "daq_session.h"

enum { DAQ_QUEUE_MAX_PACKETS = 8 };
typedef enum {
    DQ_OK, DQ_FULL, DQ_EMPTY, DQ_BORROWED, DQ_PENDING,
    DQ_DONE, DQ_NEEDS_RESTART, DQ_BAD_CONFIG, DQ_RECEIVE_ERROR, DQ_STOP_LIMIT
} dq_status;
typedef struct { uint8_t bytes[S2MM_PACKET_BYTES]; } dq_packet;
typedef struct {
    daq_session *session;
    dq_packet packets[DAQ_QUEUE_MAX_PACKETS];
    unsigned capacity, head, count, high_water;
    bool borrowed, stopping;
    unsigned drain_limit, drained;
    uint64_t requested_frames, produced, consumed, full_returns;
    dq_status status;
} daq_queue;

/* Cooperative single caller; not an ISR/thread-safe ring. The session and its
 * fixed DMA work buffer belong exclusively to this queue while it is in use.
 * Only completed, CPU-synchronized and validated 28-byte packets are copied
 * into this CPU-only ring. Ring slots are NOT DMA targets and need no DMA sync.
 * Capacity is 1..8; no allocation, no overwrite or implicit discard.
 */
dq_status dq_init(daq_queue *queue, daq_session *session, unsigned capacity);
dq_status dq_restart(daq_queue *queue); // Requires all published packets released.
dq_status dq_produce(daq_queue *queue); // FULL: no register/cache/DMA callback.
dq_status dq_request_stop(daq_queue *queue, uint64_t requested_frames, unsigned max_drain);
/* Borrow the oldest packet; keep its pointer only until release. One consumer
 * loan at a time. Valid queued packets remain readable after producer errors.
 */
dq_status dq_borrow(daq_queue *queue, const dq_packet **packet);
dq_status dq_release(daq_queue *queue);
const char *dq_status_name(dq_status status);

#endif
