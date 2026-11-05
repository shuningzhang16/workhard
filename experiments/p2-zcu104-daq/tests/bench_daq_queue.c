#define _POSIX_C_SOURCE 200809L
#include "queue_host.h"
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

enum { WAIT_ROUNDS = 20, ZERO_WAIT_ROUNDS = 100000 };
static uint64_t clock_ns(clockid_t clock)
{
    struct timespec value;
    assert(clock_gettime(clock, &value) == 0);
    return (uint64_t)value.tv_sec * UINT64_C(1000000000) + (uint64_t)value.tv_nsec;
}
static uint64_t now_ns(void) { return clock_ns(CLOCK_MONOTONIC); }
static void wait_until(uint64_t deadline)
{
    uint64_t now = now_ns();
    if (deadline <= now) return;
    uint64_t delay = deadline - now;
    struct timespec request = {(time_t)(delay / UINT64_C(1000000000)),
                               (long)(delay % UINT64_C(1000000000))};
    while (nanosleep(&request, &request) != 0) assert(errno == EINTR);
}

int main(int argc, char **argv)
{
    uint8_t rtl[QH_CAPTURE_BYTES];
    if (argc != 3 || qh_read_capture(argv[1], rtl) != 0) return 2;
    FILE *trace = fopen(argv[2], "w");
    if (!trace) return 2;
    fputs("capacity,consumer_hold_us,first_epoch_frame,enqueue_ns_from_case_start,release_latency_ns,occupancy_on_publish\n", trace);
    puts("scope,capacity,consumer_hold_us,rtl_replay_epochs,frames,valid_bytes,elapsed_ns,process_cpu_ns,process_cpu_pct,host_frames_per_s,host_valid_bytes_per_s,mean_queue_latency_us,max_queue_latency_us,high_water,full_returns,result");
    const unsigned capacities[] = {1, 3, 8};
    const unsigned delays[] = {0, 200, 1000};
    for (unsigned ci = 0; ci < 3; ++ci) for (unsigned di = 0; di < 3; ++di) {
        uint64_t latency_sum = 0, latency_max = 0, full_returns = 0;
        uint64_t trace_time[12] = {0}, trace_latency[12] = {0};
        unsigned trace_occupancy[12] = {0}, high_water = 0;
        const unsigned rounds = delays[di] == 0 ? ZERO_WAIT_ROUNDS : WAIT_ROUNDS;
        // CPU interval is nested inside the wall interval; both exclude CSV I/O.
        uint64_t begin = now_ns();
        uint64_t cpu_begin = clock_ns(CLOCK_PROCESS_CPUTIME_ID);
        for (unsigned round = 0; round < rounds; ++round) {
            queue_host host;
            daq_session session;
            daq_queue queue;
            qh_setup(&host, &session, &queue, rtl, capacities[ci]);
            uint64_t enqueued[12] = {0}, release_at = 0;
            const dq_packet *borrowed = NULL;
            for (unsigned step = 0; step < 1000; ++step) {
                if (!queue.stopping && queue.produced == 11)
                    assert(dq_request_stop(&queue, 12, 1) == DQ_OK);
                uint64_t before = queue.produced;
                dq_status status = dq_produce(&queue);
                assert(status == DQ_OK || status == DQ_FULL || status == DQ_DONE);
                if (queue.produced != before) {
                    assert(before < 12);
                    enqueued[before] = now_ns();
                    if (round == 0) {
                        trace_time[before] = enqueued[before] - begin;
                        trace_occupancy[before] = queue.count;
                    }
                }
                if (borrowed == NULL && queue.count != 0) {
                    assert(dq_borrow(&queue, &borrowed) == DQ_OK);
                    release_at = now_ns() + (uint64_t)delays[di] * 1000U;
                }
                uint64_t now = now_ns();
                if (borrowed != NULL && now >= release_at) {
                    assert(queue.consumed < 12);
                    assert(memcmp(borrowed->bytes, rtl + queue.consumed * 28, 28) == 0);
                    const uint64_t consumed_index = queue.consumed;
                    assert(dq_release(&queue) == DQ_OK);
                    uint64_t latency = now_ns() - enqueued[consumed_index];
                    latency_sum += latency;
                    if (latency > latency_max) latency_max = latency;
                    if (round == 0) trace_latency[consumed_index] = latency;
                    borrowed = NULL;
                }
                if (queue.status == DQ_DONE && queue.count == 0) break;
                // No spinning while a full queue waits for a slow consumer.
                if (borrowed != NULL && (status == DQ_FULL || queue.status == DQ_DONE))
                    wait_until(release_at);
            }
            assert(queue.status == DQ_DONE && queue.consumed == 12 && queue.count == 0);
            assert(host.submits == 12 && host.syncs == 13);
            full_returns += queue.full_returns;
            if (queue.high_water > high_water) high_water = queue.high_water;
        }
        uint64_t cpu_elapsed = clock_ns(CLOCK_PROCESS_CPUTIME_ID) - cpu_begin;
        uint64_t elapsed = now_ns() - begin;
        const uint64_t frames = (uint64_t)rounds * QH_FRAMES;
        const uint64_t bytes = frames * S2MM_PACKET_BYTES;
        assert(elapsed != 0 && high_water <= capacities[ci]);
        printf("host_callbacks,%u,%u,%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64
               ",%" PRIu64 ",%.3f,%.3f,%.3f,%.3f,%.3f,%u,%" PRIu64 ",PASS\n",
               capacities[ci], delays[di], rounds, frames, bytes, elapsed, cpu_elapsed,
               (double)cpu_elapsed * 100.0 / (double)elapsed,
               (double)frames * 1e9 / (double)elapsed, (double)bytes * 1e9 / (double)elapsed,
               (double)latency_sum / (double)frames / 1000.0, (double)latency_max / 1000.0,
               high_water, full_returns);
        fflush(stdout);
        // Only the first 12-frame epoch is logged; printing is outside timing.
        for (unsigned i = 0; i < 12; ++i)
            fprintf(trace, "%u,%u,%u,%" PRIu64 ",%" PRIu64 ",%u\n", capacities[ci], delays[di], i,
                    trace_time[i], trace_latency[i], trace_occupancy[i]);
    }
    fclose(trace);
    fputs("PASS 9 host callback measurements; 100000 epochs at zero wait, 20 otherwise; process CPU time measured, not board throughput or system CPU load\n", stderr);
    return 0;
}
