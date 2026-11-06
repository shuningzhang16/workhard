/* Host execution of the actual ADC decoder and measured-clear C entry point. */
#include "buck_control.h"
#include "adc_scaling.h"
#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>

static BuckController latched(void)
{
    BuckController control;
    buck_controller_init(&control);
    (void)buck_controller_step_observed(&control, 0U, 9.0, 0.0, 2.5, false, NULL);
    assert(control.state == BUCK_FAULT_LATCHED);
    return control;
}

static BuckCommand request(BuckController *control, uint64_t sample,
                           uint16_t raw_vout, uint16_t raw_current)
{
    const P1Measurements value = p1_scale_adc(1117U, raw_vout, raw_current);
    return buck_controller_step_observed(control, sample, value.input_v,
                value.output_v, value.current_a, true, &value.clear_evidence);
}

int main(void)
{
    BuckController control = latched();
    BuckCommand command;
    P1Measurements value;
    BuckClearEvidence invalid = {0.05, 0.05, false};
    unsigned int k;
    const uint16_t rejected[][2] = {{0U, 2048U}, {19U, 2060U}, {19U, 2035U},
                                   {62U, 2048U}, {4095U, 2048U}, {19U, 0U}, {19U, 4095U}};
    const uint16_t accepted[][2] = {{1U, 2048U}, {61U, 2059U}, {19U, 2036U}};

    /* Missing evidence and unchanged zero code cannot become observable with age. */
    command = buck_controller_step_observed(&control, 1U, 9.0, 0.0, 0.0, true, NULL);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_UNOBSERVABLE);
    command = request(&control, UINT64_C(50000000), 0U, 2048U);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_UNOBSERVABLE);
    assert(command.state == BUCK_FAULT_LATCHED && command.duty == 0.0);

    value = p1_scale_adc(1117U, 19U, 2060U);
    assert(value.current_a < 0.1 && value.clear_evidence.max_abs_current_a > 0.1045);
    printf("quantized_current=%.17g bound=%.17g\n", value.current_a, value.clear_evidence.max_abs_current_a);
    for (k = 0U; k < sizeof(rejected) / sizeof(rejected[0]); ++k) {
        control = latched();
        command = request(&control, 1U, rejected[k][0], rejected[k][1]);
        assert(command.clear_result != BUCK_CLEAR_ACCEPTED);
        assert(command.state == BUCK_FAULT_LATCHED && command.duty == 0.0);
    }
    for (k = 0U; k < sizeof(accepted) / sizeof(accepted[0]); ++k) {
        control = latched();
        command = request(&control, 7U, accepted[k][0], accepted[k][1]);
        assert(command.clear_result == BUCK_CLEAR_ACCEPTED);
        assert(command.state == BUCK_SOFT_START && command.reference_v == 0.0);
        assert(control.start_sample == 7U && control.latched_fault == 0U);
    }
    control = latched();
    command = buck_controller_step_observed(&control, 1U, 9.0, 0.01, 0.0, true, &invalid);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_UNOBSERVABLE);
    invalid.observable = true;
    invalid.max_abs_output_v = NAN;
    command = buck_controller_step_observed(&control, 2U, 9.0, 0.01, 0.0, true, &invalid);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_UNOBSERVABLE);
    invalid.max_abs_output_v = 0.0;
    command = buck_controller_step_observed(&control, 3U, 9.0, 0.01, 0.0, true, &invalid);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_UNOBSERVABLE);
    invalid.max_abs_output_v = 0.1;
    invalid.max_abs_current_a = 0.1;
    command = buck_controller_step_observed(&control, 4U, 9.0, 0.01, 0.0, false, &invalid);
    assert(command.state == BUCK_FAULT_LATCHED);
    command = buck_controller_step_observed(&control, 5U, 9.0, 0.01, 0.0, true, &invalid);
    assert(command.clear_result == BUCK_CLEAR_ACCEPTED);
    puts("PASS: endpoint/missing/invalid evidence, full-bin rejection, signed interior bounds, explicit clear; original thresholds unchanged");
    return 0;
}
