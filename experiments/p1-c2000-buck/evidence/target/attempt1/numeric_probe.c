/* Compile-time ABI facts, not a target execution or timing measurement. */
#include <limits.h>
#include <float.h>
#include <stdint.h>

const uint16_t p1_numeric_format[] = {
    CHAR_BIT, sizeof(float) * CHAR_BIT, sizeof(double) * CHAR_BIT,
    FLT_RADIX, FLT_MANT_DIG, DBL_MANT_DIG
};
