/* Controlled callbacks only: no AXI DMA/register/cache hardware model. */
#include "queue_host.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int reset(void *context, unsigned limit)
{
    queue_host *h = context;
    assert(limit == 3);
    h->calls++;
    if (h->reset_fail) return -1;
    h->packet = 0;
    h->running = h->stopping = h->armed = h->prepared = h->completed = false;
    return 0;
}
static void for_device(void *context)
{
    queue_host *h = context;
    assert(!h->armed && !h->prepared);
    h->calls++; h->prepares++;
    memset(h->cpu, 0xa5, sizeof(h->cpu));
    h->prepared = true;
    h->completed = false;
}
static void for_cpu(void *context)
{
    queue_host *h = context;
    assert(!h->armed && !h->prepared);
    h->calls++; h->syncs++;
    if (h->completed) memcpy(h->cpu, h->staged, sizeof(h->cpu));
}
static int submit(void *context, size_t bytes)
{
    queue_host *h = context;
    assert(bytes == 28 && h->prepared && !h->armed);
    h->calls++; h->submits++;
    h->prepared = false; h->armed = true;
    return h->fault == QH_SUBMIT && h->packet == h->fault_packet ? -1 : 0;
}
static s2mm_event poll(void *context)
{
    queue_host *h = context;
    assert(h->armed && h->running && h->packet < QH_FRAMES);
    h->calls++; h->polls++;
    bool inject = h->packet == h->fault_packet;
    if (inject && h->fault == QH_DMA_ERROR)
        return (s2mm_event){.error = true, .raw_status = 0x4040};
    if (inject && h->fault == QH_TIMEOUT) return (s2mm_event){0};
    memcpy(h->staged, h->rtl + h->packet * 28, 28);
    if (inject && h->fault == QH_CORRUPT) h->staged[8] ^= 1;
    h->packet++; h->armed = false; h->completed = true;
    if (h->stopping) h->running = false;
    return (s2mm_event){.done = true, .raw_status = 0x1002,
        .actual_bytes = inject && h->fault == QH_SHORT ? 24 :
                       inject && h->fault == QH_LONG ? 32 : 28};
}
static int read_reg(void *context, unsigned offset, uint32_t *value)
{
    queue_host *h = context;
    h->calls++;
    if (offset == DAQ_STATUS) *value = h->running ? (h->stopping ? 3U : 1U) : 0;
    else if (offset == DAQ_FRAMES) *value = h->packet;
    else assert(0);
    return 0;
}
static int write_reg(void *context, unsigned offset, uint32_t value)
{
    queue_host *h = context;
    h->calls++;
    if (offset == DAQ_COMMAND) {
        assert(value == 1 && !h->running && !h->armed);
        h->packet = 0;
    } else if (offset == DAQ_CONTROL && value == 1) {
        assert(h->armed);
        h->running = true;
    } else if (offset == DAQ_CONTROL && value == 0) h->stopping = true;
    else assert(0);
    return 0;
}
static const s2mm_ops dma_ops = {reset, for_device, for_cpu, submit, poll};
static const daq_register_ops reg_ops = {read_reg, write_reg};

int qh_read_capture(const char *path, uint8_t *bytes)
{
    FILE *input = fopen(path, "rb");
    if (input == NULL) return -1;
    size_t count = fread(bytes, 1, QH_CAPTURE_BYTES, input);
    int extra = fgetc(input);
    int error = ferror(input);
    fclose(input);
    return count == QH_CAPTURE_BYTES && extra == EOF && !error ? 0 : -1;
}
void qh_setup(queue_host *h, daq_session *s, daq_queue *q, const uint8_t *rtl, unsigned capacity)
{
    *h = (queue_host){.rtl = rtl, .fault_packet = 2};
    assert(daq_init(s, &dma_ops, &reg_ops, h, h->cpu, sizeof(h->cpu), 3) == DAQ_NEEDS_RESTART);
    assert(dq_init(q, s, capacity) == DQ_NEEDS_RESTART);
    assert(dq_restart(q) == DQ_OK);
}
void qh_consume_one(daq_queue *q, const uint8_t *rtl)
{
    const dq_packet *packet;
    assert(dq_borrow(q, &packet) == DQ_OK);
    assert(q->consumed < QH_FRAMES);
    assert(memcmp(packet->bytes, rtl + q->consumed * 28, 28) == 0);
    assert(dq_release(q) == DQ_OK);
}
