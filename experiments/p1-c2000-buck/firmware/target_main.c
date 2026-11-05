/* Independent, output-inhibited F280049C RAM build. No TI Buck source copied. */
#include "driverlib.h"
#include "buck_control.h"
#include "adc_scaling.h"

typedef struct {
    uint32_t isr_count;
    uint16_t raw_vin;
    uint16_t raw_vout;
    uint16_t raw_current;
    uint16_t compare_a;
    uint16_t trip_flags;
    bool boot_inhibit_latched;
    bool external_trip_seen;
    bool adc_overflow_latched;
    bool clock_failed;
    P1Measurements measurements;
    BuckCommand command;
} P1Telemetry;

volatile P1Telemetry p1_telemetry;
volatile bool p1_clear_request = false;
static BuckController controller;
static uint64_t sample_index;

__interrupt void p1_adc_isr(void);

static void keep_pwm_pins_disconnected(void)
{
    GPIO_setPinConfig(GPIO_0_GPIO0);
    GPIO_setPinConfig(GPIO_1_GPIO1);
    GPIO_setDirectionMode(0U, GPIO_DIR_MODE_IN);
    GPIO_setDirectionMode(1U, GPIO_DIR_MODE_IN);
    GPIO_setPadConfig(0U, GPIO_PIN_TYPE_STD);
    GPIO_setPadConfig(1U, GPIO_PIN_TYPE_STD);
}

static void configure_pwm_and_trip(void)
{
    SysCtl_enablePeripheral(SYSCTL_PERIPH_CLK_EPWM1);
    SysCtl_disablePeripheral(SYSCTL_PERIPH_CLK_TBCLKSYNC);
    EPWM_setTimeBaseCounterMode(EPWM1_BASE, EPWM_COUNTER_MODE_STOP_FREEZE);
    EPWM_setTripZoneAction(EPWM1_BASE, EPWM_TZ_ACTION_EVENT_TZA, EPWM_TZ_ACTION_LOW);
    EPWM_setTripZoneAction(EPWM1_BASE, EPWM_TZ_ACTION_EVENT_TZB, EPWM_TZ_ACTION_LOW);
    EPWM_forceTripZoneEvent(EPWM1_BASE, EPWM_TZ_FORCE_EVENT_OST);
    p1_telemetry.boot_inhibit_latched = true;

    /* GPIO12 low -> INPUTXBAR1 -> TZ1 -> one-shot latch, independent of ISR.
     * This is an assigned interface, not a claim about actual board wiring. */
    GPIO_setPinConfig(GPIO_12_GPIO12);
    GPIO_setDirectionMode(P1_EXTERNAL_TRIP_GPIO, GPIO_DIR_MODE_IN);
    GPIO_setPadConfig(P1_EXTERNAL_TRIP_GPIO, GPIO_PIN_TYPE_PULLUP);
    GPIO_setQualificationMode(P1_EXTERNAL_TRIP_GPIO, GPIO_QUAL_ASYNC);
    XBAR_setInputPin(XBAR_INPUT1, P1_EXTERNAL_TRIP_GPIO);
    EPWM_enableTripZoneSignals(EPWM1_BASE, EPWM_TZ_SIGNAL_OSHT1);

    EPWM_setClockPrescaler(EPWM1_BASE, EPWM_CLOCK_DIVIDER_1, EPWM_HSCLOCK_DIVIDER_1);
    EPWM_setTimeBasePeriod(EPWM1_BASE, P1_PWM_COUNTS - 1U);
    EPWM_setTimeBaseCounter(EPWM1_BASE, 0U);
    EPWM_disablePhaseShiftLoad(EPWM1_BASE);
    EPWM_setCounterCompareShadowLoadMode(EPWM1_BASE, EPWM_COUNTER_COMPARE_A, EPWM_COMP_LOAD_ON_CNTR_ZERO);
    EPWM_setCounterCompareValue(EPWM1_BASE, EPWM_COUNTER_COMPARE_A, 0U);
    EPWM_setActionQualifierAction(EPWM1_BASE, EPWM_AQ_OUTPUT_A, EPWM_AQ_OUTPUT_HIGH, EPWM_AQ_OUTPUT_ON_TIMEBASE_ZERO);
    EPWM_setActionQualifierAction(EPWM1_BASE, EPWM_AQ_OUTPUT_A, EPWM_AQ_OUTPUT_LOW, EPWM_AQ_OUTPUT_ON_TIMEBASE_UP_CMPA);
    /* B has no switching command. No complementary/dead-time setup is assumed. */
    EPWM_setActionQualifierAction(EPWM1_BASE, EPWM_AQ_OUTPUT_B, EPWM_AQ_OUTPUT_LOW, EPWM_AQ_OUTPUT_ON_TIMEBASE_ZERO);
    EPWM_setEmulationMode(EPWM1_BASE, EPWM_EMULATION_STOP_AFTER_NEXT_TB);
    EPWM_disableADCTrigger(EPWM1_BASE, EPWM_SOC_A);
    EPWM_setADCTriggerSource(EPWM1_BASE, EPWM_SOC_A, EPWM_SOC_TBCTR_ZERO);
    EPWM_setADCTriggerEventPrescale(EPWM1_BASE, EPWM_SOC_A, 1U);
}

static void configure_adc(void)
{
    SysCtl_enablePeripheral(SYSCTL_PERIPH_CLK_ADCA);
    ADC_setPrescaler(ADCA_BASE, ADC_CLK_DIV_4_0);
    ADC_setVREF(ADCA_BASE, ADC_REFERENCE_INTERNAL, ADC_REFERENCE_3_3V);
    ADC_setInterruptPulseMode(ADCA_BASE, ADC_PULSE_END_OF_CONV);
    ADC_enableConverter(ADCA_BASE);
    SysCtl_delay(P1_SYSCLK_HZ / 5000UL); /* at least nominal 1 ms power-up */
    ADC_setSOCPriority(ADCA_BASE, ADC_PRI_ALL_HIPRI);
    ADC_setupSOC(ADCA_BASE, ADC_SOC_NUMBER0, ADC_TRIGGER_EPWM1_SOCA, ADC_CH_ADCIN0, P1_ADC_ACQUISITION_CYCLES);
    ADC_setupSOC(ADCA_BASE, ADC_SOC_NUMBER1, ADC_TRIGGER_EPWM1_SOCA, ADC_CH_ADCIN1, P1_ADC_ACQUISITION_CYCLES);
    ADC_setupSOC(ADCA_BASE, ADC_SOC_NUMBER2, ADC_TRIGGER_EPWM1_SOCA, ADC_CH_ADCIN2, P1_ADC_ACQUISITION_CYCLES);
    ADC_setInterruptSource(ADCA_BASE, ADC_INT_NUMBER1, ADC_SOC_NUMBER2);
    ADC_disableContinuousMode(ADCA_BASE, ADC_INT_NUMBER1);
    ADC_clearInterruptStatus(ADCA_BASE, ADC_INT_NUMBER1);
    ADC_clearInterruptOverflowStatus(ADCA_BASE, ADC_INT_NUMBER1);
    ADC_enableInterrupt(ADCA_BASE, ADC_INT_NUMBER1);
    Interrupt_register(INT_ADCA1, &p1_adc_isr);
    Interrupt_enable(INT_ADCA1);
}

__interrupt void p1_adc_isr(void)
{
    const uint16_t vin = ADC_readResult(ADCARESULT_BASE, ADC_SOC_NUMBER0);
    const uint16_t vout = ADC_readResult(ADCARESULT_BASE, ADC_SOC_NUMBER1);
    const uint16_t current = ADC_readResult(ADCARESULT_BASE, ADC_SOC_NUMBER2);
    const P1Measurements measurements = p1_scale_adc(vin, vout, current);
    const bool clear = p1_clear_request;
    BuckCommand command;
    p1_clear_request = false;
    command = buck_controller_step(&controller, sample_index, measurements.input_v,
                                   measurements.output_v, measurements.current_a, clear);
    ++sample_index;
    if (command.state == BUCK_FAULT_LATCHED || command.duty == 0.0) {
        EPWM_forceTripZoneEvent(EPWM1_BASE, EPWM_TZ_FORCE_EVENT_OST);
    }
    p1_telemetry.raw_vin = vin;
    p1_telemetry.raw_vout = vout;
    p1_telemetry.raw_current = current;
    p1_telemetry.measurements = measurements;
    p1_telemetry.command = command;
    p1_telemetry.compare_a = (uint16_t)(command.duty * (double)P1_PWM_COUNTS + 0.5);
    EPWM_setCounterCompareValue(EPWM1_BASE, EPWM_COUNTER_COMPARE_A, p1_telemetry.compare_a);
    p1_telemetry.trip_flags = EPWM_getTripZoneFlagStatus(EPWM1_BASE);
    if (GPIO_readPin(P1_EXTERNAL_TRIP_GPIO) == 0U) {
        p1_telemetry.external_trip_seen = true;
    }
    ++p1_telemetry.isr_count;
    ADC_clearInterruptStatus(ADCA_BASE, ADC_INT_NUMBER1);
    if (ADC_getInterruptOverflowStatus(ADCA_BASE, ADC_INT_NUMBER1)) {
        p1_telemetry.adc_overflow_latched = true;
        EPWM_forceTripZoneEvent(EPWM1_BASE, EPWM_TZ_FORCE_EVENT_OST);
        ADC_clearInterruptOverflowStatus(ADCA_BASE, ADC_INT_NUMBER1);
        ADC_clearInterruptStatus(ADCA_BASE, ADC_INT_NUMBER1);
    }
    Interrupt_clearACKGroup(INTERRUPT_ACK_GROUP1);
    /* Deliberately no hardware OST clear and no GPIO-to-ePWM pin mux. */
}

int main(void)
{
    DINT;
    SysCtl_disableWatchdog();
    keep_pwm_pins_disconnected();
    if (!SysCtl_setClock(SYSCTL_OSCSRC_OSC2 | SYSCTL_IMULT(20) | SYSCTL_FMULT_NONE |
                        SYSCTL_SYSDIV(2) | SYSCTL_PLL_ENABLE)) {
        p1_telemetry.clock_failed = true;
        for (;;) { __asm(" NOP"); }
    }
    SysCtl_deviceCal();
    Interrupt_initModule();
    Interrupt_initVectorTable();
    buck_controller_init(&controller);
    configure_pwm_and_trip();
    configure_adc();
    EPWM_enableADCTrigger(EPWM1_BASE, EPWM_SOC_A);
    EPWM_setTimeBaseCounterMode(EPWM1_BASE, EPWM_COUNTER_MODE_UP);
    SysCtl_enablePeripheral(SYSCTL_PERIPH_CLK_TBCLKSYNC);
    EINT;
    for (;;) { __asm(" NOP"); }
}
