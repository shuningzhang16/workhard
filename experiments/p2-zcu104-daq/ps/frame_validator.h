#ifndef FRAME_VALIDATOR_H
#define FRAME_VALIDATOR_H

#include <stddef.h>
#include <stdint.h>

typedef enum {
    FV_OK = 0,
    FV_BAD_CONFIG,
    FV_BAD_LENGTH,
    FV_WORD_INDEX,
    FV_FRAME_SEQUENCE,
    FV_TRUNCATED,
    FV_FRAME_COUNT
} fv_status;

typedef struct {
    uint32_t frame_words;
    uint16_t expected_frame;
    uint16_t expected_index;
    uint64_t accepted_words;
    uint64_t complete_frames;
    fv_status status;
    uint32_t expected_word;
    uint32_t observed_word;
} frame_validator;

/* Start a known acquisition epoch; frame_words is 1..65536.
 * first_frame is explicit, normally zero after resetting the PL source/FIFO.
 * This is the only function that clears a latched error. It does not touch hardware.
 */
fv_status fv_reset(frame_validator *state, uint32_t frame_words, uint16_t first_frame);

/* Consume little-endian 32-bit words. byte_count must be divisible by 4.
 * Batches may end inside a frame, but not inside a word. No allocation is needed.
 * On error, stop before the bad word and latch the first error. accepted_words
 * is the zero-based position of a bad word, or the number accepted before an
 * end/length error. observed_word is meaningful for INDEX/SEQUENCE errors only.
 */
fv_status fv_feed(frame_validator *state, const void *bytes, size_t byte_count);

/* End a capture. An explicit requested frame count detects loss of whole tail
 * frames that cannot be inferred from sequence numbers alone. Does not reset.
 */
fv_status fv_finish(frame_validator *state, uint64_t requested_frames);
const char *fv_status_name(fv_status status);

#endif
