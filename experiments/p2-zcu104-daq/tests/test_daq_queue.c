#include "queue_host.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static unsigned cases;
static void record(const char *name, queue_host *h, daq_queue *q, dq_status expected)
{
    assert(q->status == expected);
    assert(q->produced == q->consumed + q->count && q->high_water <= q->capacity);
    if (expected != DQ_OK) {
        unsigned calls = h->calls;
        assert(dq_produce(q) == expected && h->calls == calls);
    }
    printf("%s,%s,%s,%u,%" PRIu64 ",%" PRIu64 ",%u,%u,%" PRIu64 ",%u,%u,%s,PASS\n",
        name, dq_status_name(q->status), s2mm_status_name(q->session->receiver.status),
        q->capacity, q->produced, q->consumed, q->count, q->high_water, q->full_returns,
        h->submits, h->syncs, q->session->receiver.owner == S2MM_CPU ? "CPU" : "DEVICE");
    fflush(stdout);
    cases++;
}
static void run_capture(daq_queue *q, const uint8_t *rtl)
{
    while (q->produced < 11) {
        dq_status status = dq_produce(q);
        if (status == DQ_FULL) qh_consume_one(q, rtl);
        else assert(status == DQ_OK);
    }
    assert(dq_request_stop(q, 12, 1) == DQ_OK);
    for (unsigned step = 0; step < 30 && q->status == DQ_OK; ++step) {
        dq_status status = dq_produce(q);
        if (status == DQ_FULL) qh_consume_one(q, rtl);
        else assert(status == DQ_OK || status == DQ_DONE);
    }
    assert(q->status == DQ_DONE && q->drained == 1);
    while (q->count) qh_consume_one(q, rtl);
    assert(q->produced == 12 && q->consumed == 12);
}

int main(int argc, char **argv)
{
    uint8_t rtl[QH_CAPTURE_BYTES];
    if (argc != 2 || qh_read_capture(argv[1], rtl) != 0) return 2;
    queue_host h;
    daq_session s;
    daq_queue q;
    puts("case,queue,receiver,capacity,produced,consumed,pending,high_water,full_returns,submits,cpu_syncs,dma_buffer_owner,result");
    const unsigned capacities[] = {1, 3, 8};
    const char *capacity_names[] = {"capacity_1_wrap", "capacity_3_wrap", "capacity_8_wrap"};
    for (unsigned i = 0; i < 3; ++i) {
        qh_setup(&h, &s, &q, rtl, capacities[i]);
        run_capture(&q, rtl);
        assert(q.high_water == capacities[i] && h.submits == 12 && h.syncs == 13);
        record(capacity_names[i], &h, &q, DQ_DONE);
    }

    qh_setup(&h, &s, &q, rtl, 3);
    const dq_packet *held, *unused;
    assert(dq_borrow(&q, &unused) == DQ_EMPTY);
    assert(dq_produce(&q) == DQ_OK && dq_borrow(&q, &held) == DQ_OK);
    assert(dq_produce(&q) == DQ_OK && dq_produce(&q) == DQ_OK);
    unsigned calls = h.calls;
    for (unsigned i = 0; i < 3; ++i) assert(dq_produce(&q) == DQ_FULL);
    assert(dq_restart(&q) == DQ_PENDING && dq_borrow(&q, &unused) == DQ_BORROWED);
    assert(h.calls == calls && memcmp(held->bytes, rtl, 28) == 0);
    assert(dq_release(&q) == DQ_OK && dq_release(&q) == DQ_EMPTY);
    assert(dq_produce(&q) == DQ_OK); // Freed head is reused only after release.
    while (q.count) qh_consume_one(&q, rtl);
    assert(dq_request_stop(&q, 5, 1) == DQ_OK && dq_produce(&q) == DQ_OK);
    assert(dq_produce(&q) == DQ_DONE);
    qh_consume_one(&q, rtl);
    record("borrowed_slot_never_overwritten", &h, &q, DQ_DONE);

    qh_setup(&h, &s, &q, rtl, 3);
    for (unsigned i = 0; i < 3; ++i) assert(dq_produce(&q) == DQ_OK);
    assert(dq_request_stop(&q, 4, 1) == DQ_OK);
    calls = h.calls;
    assert(dq_produce(&q) == DQ_FULL && h.calls == calls && q.drained == 0);
    qh_consume_one(&q, rtl);
    assert(dq_produce(&q) == DQ_OK && q.count == 3);
    qh_consume_one(&q, rtl);
    assert(dq_produce(&q) == DQ_DONE);
    while (q.count) qh_consume_one(&q, rtl);
    assert(q.produced == 4 && q.consumed == 4);
    record("full_queue_stop_drains_without_loss", &h, &q, DQ_DONE);

    const qh_fault faults[] = {QH_DMA_ERROR, QH_TIMEOUT, QH_SHORT, QH_LONG, QH_CORRUPT, QH_SUBMIT};
    const s2mm_status errors[] = {S2MM_DMA_ERROR, S2MM_TIMEOUT, S2MM_BAD_LENGTH,
                                 S2MM_BAD_LENGTH, S2MM_BAD_FRAME, S2MM_SUBMIT_ERROR};
    const char *names[] = {"dma_error_keeps_valid_prefix", "timeout_keeps_valid_prefix",
        "short_packet_not_published", "over_length_report_not_published",
        "corrupt_packet_not_published", "submit_error_not_published"};
    for (unsigned i = 0; i < 6; ++i) {
        qh_setup(&h, &s, &q, rtl, 3);
        h.fault = faults[i];
        assert(dq_produce(&q) == DQ_OK && dq_produce(&q) == DQ_OK);
        assert(dq_produce(&q) == DQ_RECEIVE_ERROR && s.receiver.status == errors[i]);
        assert(q.produced == 2 && q.count == 2);
        if (faults[i] == QH_TIMEOUT) assert(s.receiver.last_polls == 3);
        assert(h.syncs == (faults[i] == QH_CORRUPT ? 4U : 3U));
        calls = h.calls;
        assert(dq_restart(&q) == DQ_PENDING && h.calls == calls);
        record(names[i], &h, &q, DQ_RECEIVE_ERROR);
        // Already-published CPU packets remain consumable after DMA failure.
        while (q.count) qh_consume_one(&q, rtl);
    }

    h.reset_fail = true;
    unsigned syncs = h.syncs;
    assert(dq_restart(&q) == DQ_RECEIVE_ERROR && h.syncs == syncs);
    assert(s.receiver.status == S2MM_SUBMIT_ERROR && s.receiver.restart_failed);
    h.reset_fail = false; h.fault = QH_NONE;
    assert(dq_restart(&q) == DQ_OK && q.produced == 0 && q.consumed == 0);
    run_capture(&q, rtl);
    record("failed_restart_then_explicit_recovery", &h, &q, DQ_DONE);

    qh_setup(&h, &s, &q, rtl, 3);
    assert(dq_produce(&q) == DQ_OK && dq_request_stop(&q, 2, 0) == DQ_OK);
    assert(dq_produce(&q) == DQ_STOP_LIMIT && h.submits == 1 && q.count == 1);
    qh_consume_one(&q, rtl);
    record("stop_drain_limit_preserves_packet", &h, &q, DQ_STOP_LIMIT);
    fprintf(stderr, "PASS %u bounded-queue cases; real RTL payload, injected host status\n", cases);
    return 0;
}
