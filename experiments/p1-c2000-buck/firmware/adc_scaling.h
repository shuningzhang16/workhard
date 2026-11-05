#ifndef P1_ADC_SCALING_H
#define P1_ADC_SCALING_H

#include <stdint.h>
#include "board_config.h"

typedef struct {
    double input_v;
    double output_v;
    double current_a;
} P1Measurements;

static inline P1Measurements p1_scale_adc(uint16_t raw_vin, uint16_t raw_vout, uint16_t raw_current)
{
    P1Measurements value;
    value.input_v = (double)raw_vin * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) * P1_VIN_DIVIDER_GAIN;
    value.output_v = (double)raw_vout * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) * P1_VOUT_DIVIDER_GAIN;
    value.current_a = ((double)raw_current * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) - P1_CURRENT_ZERO_V)
                      / P1_CURRENT_GAIN_V_PER_A;
    return value;
}

#endif
