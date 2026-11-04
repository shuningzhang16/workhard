#ifndef BUCK_CONTROL_H
#define BUCK_CONTROL_H

#include <stdbool.h>
#include <stdint.h>

/* Fixed teaching parameters, in SI units; not hardware protection ratings. */
#define BUCK_TS_S (20e-6)
#define BUCK_TARGET_V (2.0)
#define BUCK_KP (0.03)
#define BUCK_KI (30.0)
#define BUCK_MAX_DUTY (0.95)
#define BUCK_SOFT_START_S (0.020)
#define BUCK_SOFT_START_SAMPLES UINT64_C(1000)
#define BUCK_OVERCURRENT_A (2.5)
#define BUCK_OVERVOLTAGE_V (2.4)
#define BUCK_UNDERVOLTAGE_V (6.0)
#define BUCK_CLEAR_MAX_ABS_V (0.1)
#define BUCK_CLEAR_MAX_ABS_A (0.1)

typedef enum {
    BUCK_SOFT_START = 0,
    BUCK_RUN = 1,
    BUCK_FAULT_LATCHED = 2
} BuckState;

enum {
    BUCK_FAULT_NONE = 0,
    BUCK_FAULT_OVERCURRENT = 1,
    BUCK_FAULT_OVERVOLTAGE = 2,
    BUCK_FAULT_UNDERVOLTAGE = 4
};

typedef enum {
    BUCK_CLEAR_NOT_REQUESTED = 0,
    BUCK_CLEAR_REJECTED_ACTIVE = 1,
    BUCK_CLEAR_REJECTED_RESIDUAL = 2,
    BUCK_CLEAR_ACCEPTED = 3,
    BUCK_CLEAR_IGNORED_NOT_LATCHED = 4
} BuckClearResult;

typedef struct {
    double integral;
} BuckVoltagePI;

typedef struct {
    BuckVoltagePI pi;
    BuckState state;
    unsigned int latched_fault;
    uint64_t start_sample;
} BuckController;

typedef struct {
    double duty;
    double reference_v;
    BuckState state;
    unsigned int active_faults;
    unsigned int latched_fault;
    BuckClearResult clear_result;
} BuckCommand;

/* Initialize once; then supply finite measurements at consecutive sample indices.
 * Each true clear_request is one explicit command. No ADC/PWM/ISR is implemented.
 * PI state can also be initialized independently with BuckVoltagePI pi = {0}. */
void buck_controller_init(BuckController *control);
double buck_voltage_pi_step(BuckVoltagePI *pi, double reference_v, double measured_v);
BuckCommand buck_controller_step(BuckController *control, uint64_t sample,
                                 double input_v, double output_v, double current_a,
                                 bool clear_request);

#endif
