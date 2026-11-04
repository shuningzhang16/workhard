#include "frame_validator.h"

static uint32_t expected_word(const frame_validator *state)
{
    return ((uint32_t)state->expected_frame << 16) | state->expected_index;
}

fv_status fv_reset(frame_validator *state, uint32_t frame_words, uint16_t first_frame)
{
    if (state == NULL) return FV_BAD_CONFIG;
    *state = (frame_validator){0};
    state->frame_words = frame_words;
    state->expected_frame = first_frame;
    state->expected_word = expected_word(state);
    if (frame_words == 0 || frame_words > 65536) state->status = FV_BAD_CONFIG;
    return state->status;
}

fv_status fv_feed(frame_validator *state, const void *bytes, size_t byte_count)
{
    if (state == NULL) return FV_BAD_CONFIG;
    if (state->status != FV_OK) return state->status;
    if ((byte_count % 4) != 0 || (bytes == NULL && byte_count != 0)) {
        state->status = FV_BAD_LENGTH;
        return state->status;
    }
    const uint8_t *data = bytes;
    for (size_t offset = 0; offset < byte_count; offset += 4) {
        /* Byte loads avoid alignment and host-endianness assumptions. */
        uint32_t word = (uint32_t)data[offset] |
                        ((uint32_t)data[offset + 1] << 8) |
                        ((uint32_t)data[offset + 2] << 16) |
                        ((uint32_t)data[offset + 3] << 24);
        state->expected_word = expected_word(state);
        state->observed_word = word;
        if ((uint16_t)word != state->expected_index) state->status = FV_WORD_INDEX;
        else if ((uint16_t)(word >> 16) != state->expected_frame) state->status = FV_FRAME_SEQUENCE;
        if (state->status != FV_OK) return state->status;
        state->accepted_words++;
        if ((uint32_t)state->expected_index + 1 == state->frame_words) {
            state->expected_index = 0;
            state->expected_frame = (uint16_t)(state->expected_frame + 1U);
            state->complete_frames++;
        } else {
            state->expected_index++;
        }
    }
    state->expected_word = expected_word(state);
    return FV_OK;
}

fv_status fv_finish(frame_validator *state, uint64_t requested_frames)
{
    if (state == NULL) return FV_BAD_CONFIG;
    if (state->status != FV_OK) return state->status;
    if (state->expected_index != 0 || state->complete_frames < requested_frames)
        state->status = FV_TRUNCATED;
    else if (state->complete_frames > requested_frames)
        state->status = FV_FRAME_COUNT;
    return state->status;
}

const char *fv_status_name(fv_status status)
{
    switch (status) {
    case FV_OK: return "OK";
    case FV_BAD_CONFIG: return "BAD_CONFIG";
    case FV_BAD_LENGTH: return "BAD_LENGTH";
    case FV_WORD_INDEX: return "WORD_INDEX";
    case FV_FRAME_SEQUENCE: return "FRAME_SEQUENCE";
    case FV_TRUNCATED: return "TRUNCATED";
    case FV_FRAME_COUNT: return "FRAME_COUNT";
    default: return "UNKNOWN";
    }
}
