#ifndef P1_BOARD_CONFIG_H
#define P1_BOARD_CONFIG_H

/* PROVISIONAL laboratory interface assignments, not verified BOOSTXL wiring.
 * No code in this project enables PWM pin mux or clears the hardware OST. */
#define P1_SYSCLK_HZ 100000000UL
#define P1_PWM_COUNTS 2000U
#define P1_ADC_ACQUISITION_CYCLES 20U
#define P1_EXTERNAL_TRIP_GPIO 12U

/* Nominal ADC transfer: pin voltage = raw * 3.3 / 4096.
 * These analog front-end values are explicit placeholders requiring schematic
 * confirmation and calibration; they are NOT TI Buck board component values. */
#define P1_ADC_REFERENCE_V 3.3
#define P1_ADC_COUNTS 4096.0
#define P1_VIN_DIVIDER_GAIN 10.0
#define P1_VOUT_DIVIDER_GAIN 2.0
#define P1_CURRENT_ZERO_V 1.65
#define P1_CURRENT_GAIN_V_PER_A 0.1

#endif
