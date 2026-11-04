#include "simple_s2mm.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

enum { FRAMES = 12, CAPTURE_BYTES = FRAMES * S2MM_PACKET_BYTES, POLL_LIMIT = 3 };
typedef enum { UNKNOWN, QUIESCENT, CPU, PREPARED, ACTIVE, COMPLETE } phase;
typedef enum { NONE, LENGTH, DMA_ERROR, NEVER_DONE, CORRUPT, SUBMIT_FAIL } fault;
typedef struct {
    const uint8_t *capture;
    _Alignas(4) uint8_t cpu[S2MM_PACKET_BYTES];
    uint8_t staged[S2MM_PACKET_BYTES];
    phase phase;
    fault fault;
    unsigned packet, fault_packet, polls, completion_poll, reset_polls;
    unsigned submits, to_cpu, to_device;
    size_t actual;
    bool reset_fail;
    char trace[256];
    size_t trace_size;
} host;
static int cases, failures, checks_failed;

#define CHECK(expression) do { if (!(expression)) { \
    fprintf(stderr, "check failed at line %d: %s\n", __LINE__, #expression); \
    checks_failed++; } } while (0)

static void event(host *h, char symbol)
{
    assert(h->trace_size + 1 < sizeof(h->trace));
    h->trace[h->trace_size++] = symbol;
    h->trace[h->trace_size] = '\0';
}

static int reset_epoch(void *context, unsigned limit)
{
    host *h = context;
    event(h, 'R');
    h->reset_polls = h->reset_fail ? limit : 1;
    if (h->reset_fail) return -1;
    h->phase = QUIESCENT;
    h->packet = 0;
    return 0;
}

static void for_device(void *context)
{
    host *h = context;
    event(h, 'D');
    assert(h->phase == CPU);
    h->to_device++;
    /* The CPU view stays poisoned until the completion sync callback. */
    memset(h->cpu, 0xa5, sizeof(h->cpu));
    h->phase = PREPARED;
}

static void for_cpu(void *context)
{
    host *h = context;
    event(h, 'C');
    assert(h->phase == QUIESCENT || h->phase == COMPLETE);
    if (h->phase == COMPLETE) memcpy(h->cpu, h->staged, sizeof(h->cpu));
    h->to_cpu++;
    h->phase = CPU;
}

static int submit(void *context, size_t bytes)
{
    host *h = context;
    event(h, 'S');
    assert(h->phase == PREPARED && bytes == S2MM_PACKET_BYTES);
    h->submits++;
    h->polls = 0;
    h->phase = ACTIVE;
    return h->fault == SUBMIT_FAIL && h->packet == h->fault_packet ? -1 : 0;
}

static s2mm_event poll_once(void *context)
{
    host *h = context;
    event(h, 'P');
    assert(h->phase == ACTIVE);
    h->polls++;
    bool inject = h->packet == h->fault_packet;
    if (h->polls < h->completion_poll || (inject && h->fault == NEVER_DONE))
        return (s2mm_event){0};
    if (inject && h->fault == DMA_ERROR)
        return (s2mm_event){.done = true, .error = true, .actual_bytes = 28,
                            .raw_status = 0x4052};
    assert(h->packet < FRAMES);
    memcpy(h->staged, h->capture + h->packet * S2MM_PACKET_BYTES, sizeof(h->staged));
    if (inject && h->fault == CORRUPT) h->staged[2 * 4] ^= 1;
    h->phase = COMPLETE;
    h->packet++;
    return (s2mm_event){.done = true,
        .actual_bytes = inject && h->fault == LENGTH ? h->actual : S2MM_PACKET_BYTES,
        .raw_status = 0x1002};
}

static const s2mm_ops ops = {reset_epoch, for_device, for_cpu, submit, poll_once};

static void setup(host *h, simple_s2mm *rx, const uint8_t *capture)
{
    *h = (host){.capture = capture, .completion_poll = 2, .fault_packet = 2,
                .actual = S2MM_PACKET_BYTES};
    CHECK(s2mm_init(rx, &ops, h, h->cpu, sizeof(h->cpu), POLL_LIMIT) == S2MM_NEEDS_RESTART);
    CHECK(s2mm_receive_frame(rx) == S2MM_NEEDS_RESTART && h->trace_size == 0);
    CHECK(s2mm_restart(rx) == S2MM_OK);
    CHECK(strcmp(h->trace, "RC") == 0 && rx->owner == S2MM_CPU);
}

static void receive_all(simple_s2mm *rx)
{
    for (unsigned i = 0; i < FRAMES && rx->status == S2MM_OK; ++i)
        s2mm_receive_frame(rx);
    s2mm_finish(rx, FRAMES);
}

static void sticky(host *h, simple_s2mm *rx)
{
    size_t events = h->trace_size;
    s2mm_status first = rx->status;
    s2mm_event evidence = rx->last_event;
    uint64_t words = rx->validator.accepted_words;
    unsigned polls = rx->last_polls;
    CHECK(s2mm_receive_frame(rx) == first);
    CHECK(s2mm_finish(rx, FRAMES) == first);
    CHECK(h->trace_size == events && rx->validator.accepted_words == words);
    CHECK(rx->last_polls == polls && rx->last_event.raw_status == evidence.raw_status &&
          rx->last_event.actual_bytes == evidence.actual_bytes);
}

static void record(const char *name, const char *origin, host *h, simple_s2mm *rx,
                   s2mm_status expected, uint64_t words, s2mm_owner owner)
{
    CHECK(rx->status == expected && rx->validator.accepted_words == words);
    CHECK(rx->owner == owner);
    sticky(h, rx);
    bool pass = checks_failed == 0;
    printf("%s,%s,%s,%s,%" PRIu64 ",%s,%u,%zu,%08" PRIx32 ",%s,%s\n",
        name, origin, s2mm_status_name(expected), s2mm_status_name(rx->status),
        rx->validator.accepted_words, owner == S2MM_CPU ? "CPU" : "DEVICE",
        rx->last_polls, rx->last_event.actual_bytes, rx->last_event.raw_status,
        h->trace, pass ? "PASS" : "FAIL");
    cases++;
    if (!pass) failures++;
    checks_failed = 0;
}

int main(int argc, char **argv)
{
    uint8_t capture[CAPTURE_BYTES + 1];
    if (argc != 2) return 2;
    FILE *input = fopen(argv[1], "rb");
    if (input == NULL) { perror(argv[1]); return 2; }
    size_t size = fread(capture, 1, sizeof(capture), input);
    int read_error = ferror(input);
    fclose(input);
    if (read_error || size != CAPTURE_BYTES) return 2;
    host h;
    simple_s2mm rx;
    puts("case,origin,expected,actual,accepted_words,owner,last_polls,actual_bytes,raw_status_hex,call_trace,result");

    setup(&h, &rx, capture);
    receive_all(&rx);
    char expected_trace[80] = "RC";
    for (unsigned i = 0; i < FRAMES; ++i) strcat(expected_trace, "DSPPC");
    CHECK(strcmp(h.trace, expected_trace) == 0);
    CHECK(h.submits == 12 && h.to_device == 12 && h.to_cpu == 13);
    CHECK(rx.validator.complete_frames == 12 && rx.validator.expected_frame == 12);
    record("twelve_packets", "RTL_payload_host_status", &h, &rx, S2MM_DONE, 84, S2MM_CPU);

    setup(&h, &rx, capture);
    h.completion_poll = POLL_LIMIT;
    receive_all(&rx);
    CHECK(rx.last_polls == POLL_LIMIT && h.submits == 12);
    record("complete_on_last_poll", "RTL_payload_host_status", &h, &rx, S2MM_DONE, 84, S2MM_CPU);

    const size_t bad_lengths[] = {0, 24, 32};
    const char *length_names[] = {"zero_length", "short_packet", "over_capacity_report"};
    for (unsigned i = 0; i < 3; ++i) {
        setup(&h, &rx, capture);
        h.fault = LENGTH;
        h.actual = bad_lengths[i];
        receive_all(&rx);
        CHECK(h.submits == 3 && h.to_cpu == 3 && h.to_device == 3);
        CHECK(rx.last_event.actual_bytes == bad_lengths[i]);
        CHECK(strcmp(h.trace, "RCDSPPCDSPPCDSPP") == 0);
        record(length_names[i], "RTL_payload_injected_length", &h, &rx,
               S2MM_BAD_LENGTH, 14, S2MM_DEVICE);
    }

    setup(&h, &rx, capture);
    h.fault = DMA_ERROR;
    receive_all(&rx);
    CHECK(rx.last_event.done && rx.last_event.error && h.to_cpu == 3);
    CHECK(rx.last_event.raw_status == 0x4052);
    record("error_over_completion", "RTL_prefix_injected_error", &h, &rx,
           S2MM_DMA_ERROR, 14, S2MM_DEVICE);

    setup(&h, &rx, capture);
    h.fault = NEVER_DONE;
    receive_all(&rx);
    CHECK(h.polls == POLL_LIMIT && h.to_cpu == 3 && h.submits == 3);
    CHECK(strcmp(h.trace, "RCDSPPCDSPPCDSPPP") == 0);
    record("timeout", "RTL_prefix_injected_pending", &h, &rx, S2MM_TIMEOUT, 14, S2MM_DEVICE);

    h.reset_fail = true;
    size_t old_events = h.trace_size;
    CHECK(s2mm_restart(&rx) == S2MM_TIMEOUT && rx.restart_failed);
    CHECK(h.trace_size == old_events + 1 && h.trace[h.trace_size - 1] == 'R');
    CHECK(h.reset_polls == POLL_LIMIT && h.to_cpu == 3 && rx.last_polls == POLL_LIMIT);
    record("failed_restart_preserves_error", "RTL_prefix_injected_reset_failure", &h, &rx,
           S2MM_TIMEOUT, 14, S2MM_DEVICE);

    h.reset_fail = false;
    h.fault = NONE;
    old_events = h.trace_size;
    CHECK(s2mm_restart(&rx) == S2MM_OK && !rx.restart_failed);
    CHECK(strcmp(h.trace + old_events, "RC") == 0 && rx.validator.accepted_words == 0);
    receive_all(&rx);
    CHECK(h.packet == FRAMES && rx.validator.complete_frames == FRAMES);
    record("explicit_restart_then_twelve_packets", "RTL_replay_new_epoch", &h, &rx,
           S2MM_DONE, 84, S2MM_CPU);

    setup(&h, &rx, capture);
    h.fault = CORRUPT;
    receive_all(&rx);
    CHECK(rx.validator.status == FV_WORD_INDEX && rx.validator.expected_word == 0x20002);
    CHECK(rx.validator.observed_word == 0x20003 && h.to_cpu == 4 && h.submits == 3);
    record("validator_error", "RTL_payload_one_byte_mutation", &h, &rx,
           S2MM_BAD_FRAME, 16, S2MM_CPU);

    setup(&h, &rx, capture);
    h.fault = SUBMIT_FAIL;
    receive_all(&rx);
    CHECK(h.to_cpu == 3 && rx.last_polls == 0 && h.submits == 3);
    record("submit_failure", "RTL_prefix_injected_submit_failure", &h, &rx,
           S2MM_SUBMIT_ERROR, 14, S2MM_DEVICE);

    setup(&h, &rx, capture);
    CHECK(s2mm_receive_frame(&rx) == S2MM_OK);
    CHECK(s2mm_finish(&rx, FRAMES) == S2MM_BAD_FRAME);
    CHECK(rx.validator.status == FV_TRUNCATED);
    record("early_finish", "RTL_payload_host_status", &h, &rx, S2MM_BAD_FRAME, 7, S2MM_CPU);

    setup(&h, &rx, capture);
    h.reset_fail = true;
    CHECK(s2mm_restart(&rx) == S2MM_RESTART_ERROR && rx.restart_failed);
    CHECK(h.to_cpu == 1);
    record("restart_failure_without_prior_error", "injected_reset_failure", &h, &rx,
           S2MM_RESTART_ERROR, 0, S2MM_DEVICE);

    fprintf(stderr, "cases=%d failures=%d; host control flow only, not DMA/cache simulation\n", cases, failures);
    return failures ? 1 : 0;
}
