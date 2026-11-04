#include "buck_control.h"

#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>

static void threshold_boundaries(void)
{
    const struct {
        double input_v;
        double output_v;
        double current_a;
        unsigned int expected;
    } cases[] = {
        {9.0, 2.0, nextafter(2.5, 0.0), BUCK_FAULT_NONE},
        {9.0, 2.0, 2.5, BUCK_FAULT_OVERCURRENT},
        {9.0, 2.0, nextafter(-2.5, 0.0), BUCK_FAULT_NONE},
        {9.0, 2.0, -2.5, BUCK_FAULT_OVERCURRENT},
        {9.0, nextafter(2.4, 0.0), 0.5, BUCK_FAULT_NONE},
        {9.0, 2.4, 0.5, BUCK_FAULT_OVERVOLTAGE},
        {nextafter(6.0, 9.0), 2.0, 0.5, BUCK_FAULT_NONE},
        {6.0, 2.0, 0.5, BUCK_FAULT_UNDERVOLTAGE},
        {6.0, 2.4, 2.5, BUCK_FAULT_OVERCURRENT | BUCK_FAULT_OVERVOLTAGE | BUCK_FAULT_UNDERVOLTAGE}
    };
    for (size_t k = 0; k < sizeof(cases) / sizeof(cases[0]); ++k) {
        BuckController control;
        BuckCommand command;
        buck_controller_init(&control);
        command = buck_controller_step(&control, 0, cases[k].input_v, cases[k].output_v, cases[k].current_a, false);
        assert(command.active_faults == cases[k].expected);
        assert(command.latched_fault == cases[k].expected);
        assert(command.state == (cases[k].expected == BUCK_FAULT_NONE ? BUCK_SOFT_START : BUCK_FAULT_LATCHED));
    }
    puts("PASS: 9 exact/adjacent threshold and combined-fault vectors");
}

static void latch_clear_and_restart(void)
{
    BuckController control;
    BuckCommand command;
    buck_controller_init(&control);
    command = buck_controller_step(&control, 0, 9.0, 0.0, 0.0, true);
    assert(command.clear_result == BUCK_CLEAR_IGNORED_NOT_LATCHED);
    control.pi.integral = 0.2;
    command = buck_controller_step(&control, 1, 9.0, 0.0, 2.5, true);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_ACTIVE);
    assert(command.duty == 0.0 && control.pi.integral == 0.0);
    command = buck_controller_step(&control, 2, 6.0, 2.4, 0.0, true);
    assert(command.active_faults == (BUCK_FAULT_OVERVOLTAGE | BUCK_FAULT_UNDERVOLTAGE));
    assert(command.latched_fault == BUCK_FAULT_OVERCURRENT);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_ACTIVE);
    command = buck_controller_step(&control, 3, 9.0, 0.0, 0.0, false);
    assert(command.state == BUCK_FAULT_LATCHED && command.duty == 0.0);
    command = buck_controller_step(&control, 4, 9.0, nextafter(-0.1, -1.0), 0.0, true);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_RESIDUAL);
    command = buck_controller_step(&control, 5, 9.0, 0.0, nextafter(0.1, 1.0), true);
    assert(command.clear_result == BUCK_CLEAR_REJECTED_RESIDUAL);
    command = buck_controller_step(&control, 6, 9.0, -0.1, 0.1, true);
    assert(command.clear_result == BUCK_CLEAR_ACCEPTED);
    assert(command.state == BUCK_SOFT_START && command.latched_fault == BUCK_FAULT_NONE);
    assert(command.reference_v == 0.0);
    /* Accepted clear resets PI before its same-sample update; negative vO can
     * therefore produce a small positive duty, just as in Python. */
    assert(fabs(command.duty - 0.00306) < 1e-14);
    assert(fabs(control.pi.integral - 0.00006) < 1e-14);
    for (uint64_t k = 7; k <= 1006; ++k) {
        command = buck_controller_step(&control, k, 9.0, 0.0, 0.0, false);
        if (k == 7) {
            assert(fabs(command.reference_v - 0.002) < 1e-14);
        }
        if (k == 1005) {
            assert(command.state == BUCK_SOFT_START);
            assert(fabs(command.reference_v - 1.998) < 1e-14);
        }
    }
    assert(command.state == BUCK_RUN && command.reference_v == 2.0);
    puts("PASS: first-cause latch, no auto-clear, active/residual rejects, inclusive clear and 999/1000-step ramp");
}

static void pi_saturation(void)
{
    BuckVoltagePI pi = {0};
    assert(buck_voltage_pi_step(&pi, 100.0, 0.0) == BUCK_MAX_DUTY);
    assert(pi.integral == 0.0);
    assert(buck_voltage_pi_step(&pi, 0.0, 100.0) == 0.0);
    assert(pi.integral == 0.0);
    assert(fabs(buck_voltage_pi_step(&pi, 1.0, 0.0) - 0.0306) < 1e-14);
    assert(fabs(pi.integral - 0.0006) < 1e-14);
    pi.integral = BUCK_MAX_DUTY;
    assert(fabs(buck_voltage_pi_step(&pi, 0.0, 1.0) - 0.9194) < 1e-14);
    assert(fabs(pi.integral - 0.9494) < 1e-14);
    puts("PASS: PI upper/lower saturation holds integral and opposite error resumes integration");
}

int main(void)
{
    printf("sizeof_double=%zu FLT_RADIX=%d DBL_MANT_DIG=%d DBL_EPSILON=%.17g\n",
           sizeof(double), FLT_RADIX, DBL_MANT_DIG, DBL_EPSILON);
    threshold_boundaries();
    latch_clear_and_restart();
    pi_saturation();
    return 0;
}
