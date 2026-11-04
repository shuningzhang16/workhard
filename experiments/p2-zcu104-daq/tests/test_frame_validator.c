#include "frame_validator.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

enum { FRAME_WORDS = 7, FRAMES = 12, CAPTURE_BYTES = FRAME_WORDS * FRAMES * 4 };
static int failures = 0, cases = 0;

static fv_status feed_batches(frame_validator *state, const uint8_t *data, size_t size, int fragmented)
{
    const size_t batch_words[] = {1, 5, 2, 11, 3};
    size_t offset = 0, batch = 0;
    while (offset < size) {
        size_t count = fragmented ? batch_words[batch++ % 5] * 4 : size;
        if (count > size - offset) count = size - offset;
        fv_status status = fv_feed(state, data + offset, count);
        if (status != FV_OK) return status;
        offset += count;
    }
    return state->status;
}

static void record(const char *name, const char *origin, fv_status expected,
                   uint64_t expected_accepted, const frame_validator *state, int extra_check)
{
    int pass = state->status == expected && state->accepted_words == expected_accepted && extra_check;
    cases++;
    if (!pass) failures++;
    printf("%s,%s,%s,%s,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%08" PRIx32 ",%08" PRIx32 ",%s\n",
           name, origin, fv_status_name(expected), fv_status_name(state->status),
           expected_accepted, state->accepted_words, state->complete_frames,
           state->expected_word, state->observed_word, pass ? "PASS" : "FAIL");
}

static void check(const char *name, const char *origin, const uint8_t *data, size_t size,
                  uint16_t first_frame, uint64_t requested, int fragmented,
                  fv_status expected, uint64_t accepted)
{
    frame_validator state;
    fv_reset(&state, FRAME_WORDS, first_frame);
    feed_batches(&state, data, size, fragmented);
    fv_finish(&state, requested);
    record(name, origin, expected, accepted, &state, 1);
}

static void put_word(uint8_t *data, uint32_t word)
{
    data[0] = (uint8_t)word;
    data[1] = (uint8_t)(word >> 8);
    data[2] = (uint8_t)(word >> 16);
    data[3] = (uint8_t)(word >> 24);
}

int main(int argc, char **argv)
{
    uint8_t original[CAPTURE_BYTES + 1], changed[CAPTURE_BYTES + 28];
    if (argc != 2) {
        fprintf(stderr, "Usage: test_frame_validator complete_rtl_capture.bin\n");
        return 2;
    }
    FILE *input = fopen(argv[1], "rb");
    if (input == NULL) { perror(argv[1]); return 2; }
    size_t size = fread(original, 1, sizeof(original), input);
    int read_error = ferror(input);
    fclose(input);
    if (read_error || size != CAPTURE_BYTES) {
        fprintf(stderr, "Expected exactly %d bytes of complete RTL capture\n", CAPTURE_BYTES);
        return 2;
    }
    printf("case,origin,expected_status,actual_status,expected_accepted_words,accepted_words,complete_frames,expected_word_hex,observed_word_hex,result\n");
    check("rtl_single_batch", "RTL", original, size, 0, FRAMES, 0, FV_OK, 84);
    check("rtl_mid_frame_batches", "RTL", original, size, 0, FRAMES, 1, FV_OK, 84);

    memcpy(changed, original, 10 * 4);
    memcpy(changed + 10 * 4, original + 11 * 4, size - 11 * 4);
    check("missing_word", "RTL_mutation", changed, size - 4, 0, FRAMES, 1, FV_WORD_INDEX, 10);

    memcpy(changed, original, 11 * 4);
    memcpy(changed + 11 * 4, original + 10 * 4, size - 10 * 4);
    check("duplicate_word", "RTL_mutation", changed, size + 4, 0, FRAMES, 1, FV_WORD_INDEX, 11);

    memcpy(changed, original, size);
    changed[9 * 4] = 5;
    check("bad_word_index", "RTL_mutation", changed, size, 0, FRAMES, 1, FV_WORD_INDEX, 9);

    memcpy(changed, original, 14 * 4);
    memcpy(changed + 14 * 4, original + 21 * 4, size - 21 * 4);
    check("missing_frame", "RTL_mutation", changed, size - 28, 0, FRAMES, 1, FV_FRAME_SEQUENCE, 14);

    memcpy(changed, original, 14 * 4);
    memcpy(changed + 14 * 4, original + 7 * 4, size - 7 * 4);
    check("duplicate_frame", "RTL_mutation", changed, size + 28, 0, FRAMES, 1, FV_FRAME_SEQUENCE, 14);

    memcpy(changed, original, size);
    put_word(changed + 14 * 4, 9U << 16);
    check("frame_jump", "RTL_mutation", changed, size, 0, FRAMES, 1, FV_FRAME_SEQUENCE, 14);

    check("tail_word_truncated", "RTL_mutation", original, size - 4, 0, FRAMES, 1, FV_TRUNCATED, 83);
    check("tail_frame_truncated", "RTL_mutation", original, size - 28, 0, FRAMES, 1, FV_TRUNCATED, 77);
    check("partial_word_bytes", "RTL_mutation", original, size - 1, 0, FRAMES, 0, FV_BAD_LENGTH, 0);
    for (size_t offset = 0; offset < size; offset += 4)
        for (size_t byte = 0; byte < 4; byte++) changed[offset + byte] = original[offset + 3 - byte];
    check("wrong_byte_order", "RTL_mutation", changed, size, 0, FRAMES, 1, FV_WORD_INDEX, 1);

    for (uint32_t word = 0; word < 28; word++)
        put_word(changed + word * 4, (((65534U + word / FRAME_WORDS) & 65535U) << 16) | (word % FRAME_WORDS));
    check("sequence_wrap_65535_to_0", "synthetic_C_fixture", changed, 28 * 4, 65534, 4, 1, FV_OK, 28);
    check("extra_complete_frame", "RTL", original, size, 0, FRAMES - 1, 1, FV_FRAME_COUNT, 84);
    check("empty_capture", "RTL_mutation", original, 0, 0, FRAMES, 1, FV_TRUNCATED, 0);

    frame_validator state;
    fv_reset(&state, FRAME_WORDS, 0);
    put_word(changed, 1);
    int sticky = fv_feed(&state, changed, 4) == FV_WORD_INDEX;
    sticky = sticky && fv_feed(&state, original, size) == FV_WORD_INDEX;
    sticky = sticky && fv_finish(&state, FRAMES) == FV_WORD_INDEX && state.accepted_words == 0;
    fv_reset(&state, FRAME_WORDS, 0);
    feed_batches(&state, original, size, 1);
    fv_finish(&state, FRAMES);
    record("explicit_reset_after_latched_error", "RTL_API_test", FV_OK, 84, &state, sticky);

    fprintf(stderr, "%d/%d cases passed; %d failures\n", cases - failures, cases, failures);
    return failures ? 1 : 0;
}
