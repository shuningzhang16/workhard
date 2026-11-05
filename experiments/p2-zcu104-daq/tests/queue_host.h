#ifndef QUEUE_HOST_H
#define QUEUE_HOST_H

#include "daq_queue.h"

enum { QH_CAPTURE_BYTES = 336, QH_FRAMES = 12 };
typedef enum { QH_NONE, QH_DMA_ERROR, QH_TIMEOUT, QH_SHORT, QH_LONG, QH_CORRUPT, QH_SUBMIT } qh_fault;
typedef struct {
    const uint8_t *rtl;
    uint8_t cpu[28], staged[28];
    unsigned packet, fault_packet, calls, prepares, submits, polls, syncs;
    bool running, stopping, armed, prepared, completed, reset_fail;
    qh_fault fault;
} queue_host;

int qh_read_capture(const char *path, uint8_t *bytes);
void qh_setup(queue_host *h, daq_session *s, daq_queue *q, const uint8_t *rtl, unsigned capacity);
void qh_consume_one(daq_queue *q, const uint8_t *rtl);

#endif
