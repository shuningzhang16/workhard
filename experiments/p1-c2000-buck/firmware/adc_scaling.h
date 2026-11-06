#ifndef P1_ADC_SCALING_H
#define P1_ADC_SCALING_H

#include <stdint.h>
#include <math.h>
#include "board_config.h"
#include "buck_control.h"

typedef struct {
    double input_v;
    double output_v;
    double current_a;
    BuckClearEvidence clear_evidence;
} P1Measurements;

static inline P1Measurements p1_scale_adc(uint16_t raw_vin, uint16_t raw_vout, uint16_t raw_current)
{
    P1Measurements value;
    value.input_v = (double)raw_vin * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) * P1_VIN_DIVIDER_GAIN;
    value.output_v = (double)raw_vout * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) * P1_VOUT_DIVIDER_GAIN;
    value.current_a = ((double)raw_current * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) - P1_CURRENT_ZERO_V)
                      / P1_CURRENT_GAIN_V_PER_A;
    /* Declared ideal floor-bin model only: include the upper bin edge.
     * Endpoint codes also represent clipping; zero Vout cannot exclude negative
     * voltage. No timer, decoded zero or hidden plant state establishes validity.
     * Real hardware must supply validated frontend/error bounds before enabling
     * any output; the existing target output inhibit remains mandatory. */
    value.clear_evidence.observable = raw_vout > 0U && raw_vout < P1_ADC_COUNTS - 1U
                                     && raw_current > 0U && raw_current < P1_ADC_COUNTS - 1U;
    value.clear_evidence.max_abs_output_v = ((double)raw_vout + 1.0)
                                           * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS) * P1_VOUT_DIVIDER_GAIN;
    value.clear_evidence.max_abs_current_a = fmax(fabs(value.current_a),
        fabs((((double)raw_current + 1.0) * (P1_ADC_REFERENCE_V / P1_ADC_COUNTS)
              - P1_CURRENT_ZERO_V) / P1_CURRENT_GAIN_V_PER_A));
    return value;
}

#endif
