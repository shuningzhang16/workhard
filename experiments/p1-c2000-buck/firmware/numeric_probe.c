/* Compile-time ABI facts, not a target execution or timing measurement. */
#include <limits.h>
#include <float.h>
#include <stdint.h>
#include "buck_control.h"
#include "board_config.h"

const uint16_t p1_numeric_format[] = {
    CHAR_BIT, sizeof(float) * CHAR_BIT, sizeof(double) * CHAR_BIT,
    FLT_RADIX, FLT_MANT_DIG, DBL_MANT_DIG
};

const double p1_numeric_constants[] = {
    BUCK_TS_S, BUCK_KP, BUCK_KI * BUCK_TS_S, BUCK_MAX_DUTY,
    BUCK_OVERCURRENT_A, BUCK_OVERVOLTAGE_V, BUCK_UNDERVOLTAGE_V,
    BUCK_CLEAR_MAX_ABS_V, BUCK_CLEAR_MAX_ABS_A,
    BUCK_TARGET_V * ((999.0 * BUCK_TS_S) / BUCK_SOFT_START_S),
    2048.0 * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) * P1_VIN_DIVIDER_GAIN,
    1241.0 * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) * P1_VOUT_DIVIDER_GAIN,
    (2048.0 * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) - P1_CURRENT_ZERO_V) / P1_CURRENT_GAIN_V_PER_A,
    (2560.0 * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) - P1_CURRENT_ZERO_V) / P1_CURRENT_GAIN_V_PER_A
};
