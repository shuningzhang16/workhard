#include "daq_session.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    const uint8_t *rtl;
    uint8_t cpu[28], staged[28];
    unsigned packet, prepares, submits, syncs, starts, stops, calls;
    bool running, stopping, armed, complete;
    bool start_fail, dma_error, reset_fail, count_bad;
    unsigned reset_reads;
    bool status_stuck, stream_reset_held;
} host;

static int reset(void *p, unsigned limit)
{
    host *h = p;
    assert(limit == 3);
    h->calls++;
    if (h->reset_fail) return -1;
    h->packet = 0; h->running = false; h->stopping = false;
    h->armed = false; h->complete = false; h->reset_reads = 0;
    return 0;
}
static void device(void *p)
{
    host *h = p;
    assert(!h->armed);
    h->calls++; h->prepares++;
    memset(h->cpu, 0xa5, sizeof(h->cpu));
}
static void cpu(void *p)
{
    host *h = p;
    assert(!h->armed);
    h->calls++; h->syncs++;
    if (h->complete) memcpy(h->cpu, h->staged, sizeof(h->cpu));
}
static int submit(void *p, size_t bytes)
{
    host *h = p;
    assert(bytes == 28 && !h->armed);
    h->calls++; h->submits++; h->armed = true; h->complete = false;
    return 0;
}
static s2mm_event poll(void *p)
{
    host *h = p;
    h->calls++;
    assert(h->armed && h->running && h->packet < 12);
    if (h->dma_error) return (s2mm_event){.error = true, .raw_status = 0x4040};
    memcpy(h->staged, h->rtl + h->packet * 28, 28);
    h->packet++; h->armed = false; h->complete = true;
    if (h->stopping) h->running = false;
    return (s2mm_event){.done = true, .actual_bytes = 28, .raw_status = 0x1002};
}
static int read_reg(void *p, unsigned offset, uint32_t *value)
{
    host *h = p;
    h->calls++;
    if (offset == DAQ_STATUS) {
        h->reset_reads++;
        *value = h->status_stuck ? 1 : (h->stream_reset_held && h->armed ? 4 :
                                      (h->running ? (h->stopping ? 3U : 1U) : 0));
    } else if (offset == DAQ_FRAMES) {
        *value = h->count_bad ? 0 : h->packet;
    } else assert(0);
    return 0;
}
static int write_reg(void *p, unsigned offset, uint32_t value)
{
    host *h = p;
    h->calls++;
    if (offset == DAQ_COMMAND) {
        assert(value == 1 && !h->running && !h->armed);
        h->packet = 0;
    } else if (offset == DAQ_CONTROL && value == 1) {
        assert(h->armed);              /* Real ordering assertion: DMA before START. */
        if (h->start_fail) return -1;
        h->starts++; h->running = true;
    } else if (offset == DAQ_CONTROL && value == 0) {
        h->stops++; h->stopping = true;
    } else assert(0);
    return 0;
}
static const s2mm_ops dma_ops = {reset, device, cpu, submit, poll};
static const daq_register_ops reg_ops = {read_reg, write_reg};
static int cases;

static void setup(host *h, daq_session *s, const uint8_t *rtl)
{
    *h = (host){.rtl = rtl};
    assert(daq_init(s, &dma_ops, &reg_ops, h, h->cpu, sizeof(h->cpu), 3) == DAQ_NEEDS_RESTART);
    assert(daq_restart(s) == DAQ_OK);
    assert(h->calls == 4 && h->syncs == 1); // reset, status, command, CPU ownership
}
static void record(const char *name, host *h, daq_session *s, daq_status expected)
{
    assert(s->status == expected);
    unsigned calls = h->calls;
    assert(daq_receive(s) == expected && daq_stop(s, 12, 1) == expected);
    assert(h->calls == calls);           /* Sticky error / terminal state. */
    printf("%s,%s,%s,%" PRIu64 ",%u,%u,%u,%u,%u,%s,PASS\n", name,
           daq_status_name(s->status), s2mm_status_name(s->receiver.status),
           s->receiver.validator.complete_frames, s->drained, h->starts, h->stops,
           h->submits, h->syncs, s->receiver.owner == S2MM_CPU ? "CPU" : "DEVICE");
    cases++;
}
int main(int argc, char **argv)
{
    uint8_t rtl[337];
    if (argc != 2) return 2;
    FILE *input = fopen(argv[1], "rb");
    if (!input) return 2;
    size_t size = fread(rtl, 1, sizeof(rtl), input);
    int error = ferror(input);
    fclose(input);
    if (size != 336 || error) return 2;
    host h;
    daq_session s;
    puts("case,session,receiver,frames,drained,starts,stops,submits,cpu_syncs,owner,result");

    setup(&h, &s, rtl);
    for (unsigned i = 0; i < 11; ++i) assert(daq_receive(&s) == DAQ_OK);
    assert(daq_stop(&s, 12, 1) == DAQ_DONE);
    assert(s.drained == 1 && h.starts == 1 && h.submits == 12 && h.syncs == 13);
    record("start_arm_order_stop_drain", &h, &s, DAQ_DONE);

    assert(daq_restart(&s) == DAQ_OK && s.receiver.validator.accepted_words == 0);
    for (unsigned i = 0; i < 11; ++i) assert(daq_receive(&s) == DAQ_OK);
    assert(daq_stop(&s, 12, 1) == DAQ_DONE && h.starts == 2);
    record("explicit_restart_new_epoch", &h, &s, DAQ_DONE);

    setup(&h, &s, rtl);
    assert(daq_receive(&s) == DAQ_OK);
    assert(daq_stop(&s, 2, 0) == DAQ_STOP_LIMIT && h.submits == 1);
    record("bounded_stop_drain", &h, &s, DAQ_STOP_LIMIT);

    setup(&h, &s, rtl);
    h.start_fail = true;
    assert(daq_receive(&s) == DAQ_REGISTER_ERROR && s.receiver.owner == S2MM_DEVICE);
    assert(s.receiver.status == S2MM_SUBMIT_ERROR && h.syncs == 1);
    record("start_write_failure_after_arm", &h, &s, DAQ_REGISTER_ERROR);

    setup(&h, &s, rtl);
    h.dma_error = true;
    assert(daq_receive(&s) == DAQ_RECEIVE_ERROR);
    assert(s.receiver.status == S2MM_DMA_ERROR && h.syncs == 1);
    h.reset_fail = true;
    assert(daq_restart(&s) == DAQ_RECEIVE_ERROR && s.receiver.status == S2MM_DMA_ERROR);
    assert(s.receiver.restart_failed && h.syncs == 1);
    record("dma_error_failed_restart_latched", &h, &s, DAQ_RECEIVE_ERROR);

    setup(&h, &s, rtl);
    assert(daq_receive(&s) == DAQ_OK);
    h.count_bad = true;
    assert(daq_stop(&s, 2, 1) == DAQ_COUNT_ERROR);
    record("hardware_frame_count_mismatch", &h, &s, DAQ_COUNT_ERROR);

    setup(&h, &s, rtl);
    assert(daq_receive(&s) == DAQ_OK);
    assert(daq_stop(&s, 1, 1) == DAQ_RECEIVE_ERROR);
    assert(s.receiver.validator.status == FV_FRAME_COUNT);
    record("original_target_not_adjusted", &h, &s, DAQ_RECEIVE_ERROR);

    setup(&h, &s, rtl);
    h.status_stuck = true;
    assert(daq_restart(&s) == DAQ_RECEIVE_ERROR && h.reset_reads == 3 && h.syncs == 1);
    record("wrapper_not_stopped_after_reset", &h, &s, DAQ_RECEIVE_ERROR);

    setup(&h, &s, rtl);
    h.stream_reset_held = true;
    unsigned previous_reads = h.reset_reads;
    assert(daq_receive(&s) == DAQ_REGISTER_ERROR && h.starts == 0 && h.armed);
    assert(h.reset_reads == previous_reads + 3 && h.syncs == 1);
    record("stream_reset_not_released_after_arm", &h, &s, DAQ_REGISTER_ERROR);

    fprintf(stderr, "PASS %d session cases; injected status, real RTL payload; no hardware/cache proof\n", cases);
    return 0;
}
