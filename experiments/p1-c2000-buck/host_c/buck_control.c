/* Independent implementation of this experiment's Python sampled controller. */
#include "buck_control.h"

#include <math.h>

void buck_controller_init(BuckController *control)
{
    *control = (BuckController){0};
}

double buck_voltage_pi_step(BuckVoltagePI *pi, double reference_v, double measured_v)
{
    const double error = reference_v - measured_v;
    const double candidate = pi->integral + BUCK_KI * BUCK_TS_S * error;
    const double raw = BUCK_KP * error + candidate;
    double command;
    if (!((raw > BUCK_MAX_DUTY && error > 0.0) || (raw < 0.0 && error < 0.0))) {
        pi->integral = candidate;
    }
    command = BUCK_KP * error + pi->integral;
    return fmin(BUCK_MAX_DUTY, fmax(0.0, command));
}

BuckCommand buck_controller_step(BuckController *control, uint64_t sample,
                                 double input_v, double output_v, double current_a,
                                 bool clear_request)
{
    unsigned int active = BUCK_FAULT_NONE;
    BuckCommand result = {0};
    if (fabs(current_a) >= BUCK_OVERCURRENT_A) {
        active |= BUCK_FAULT_OVERCURRENT;
    }
    if (output_v >= BUCK_OVERVOLTAGE_V) {
        active |= BUCK_FAULT_OVERVOLTAGE;
    }
    if (input_v <= BUCK_UNDERVOLTAGE_V) {
        active |= BUCK_FAULT_UNDERVOLTAGE;
    }
    if (active != BUCK_FAULT_NONE && control->state != BUCK_FAULT_LATCHED) {
        control->state = BUCK_FAULT_LATCHED;
        control->latched_fault = active;
        control->pi.integral = 0.0;
    }
    result.clear_result = BUCK_CLEAR_NOT_REQUESTED;
    if (clear_request && control->state == BUCK_FAULT_LATCHED) {
        if (active != BUCK_FAULT_NONE) {
            result.clear_result = BUCK_CLEAR_REJECTED_ACTIVE;
        } else if (fabs(output_v) > BUCK_CLEAR_MAX_ABS_V || fabs(current_a) > BUCK_CLEAR_MAX_ABS_A) {
            result.clear_result = BUCK_CLEAR_REJECTED_RESIDUAL;
        } else {
            control->state = BUCK_SOFT_START;
            control->latched_fault = BUCK_FAULT_NONE;
            control->pi.integral = 0.0;
            control->start_sample = sample;
            result.clear_result = BUCK_CLEAR_ACCEPTED;
        }
    } else if (clear_request) {
        result.clear_result = BUCK_CLEAR_IGNORED_NOT_LATCHED;
    }
    if (control->state != BUCK_FAULT_LATCHED) {
        const uint64_t elapsed_samples = sample - control->start_sample;
        const double elapsed_s = (double)elapsed_samples * BUCK_TS_S;
        result.reference_v = BUCK_TARGET_V * fmin(elapsed_s / BUCK_SOFT_START_S, 1.0);
        if (control->state == BUCK_SOFT_START && elapsed_samples >= BUCK_SOFT_START_SAMPLES) {
            control->state = BUCK_RUN;
        }
        result.duty = buck_voltage_pi_step(&control->pi, result.reference_v, output_v);
    }
    result.state = control->state;
    result.active_faults = active;
    result.latched_fault = control->latched_fault;
    return result;
}
