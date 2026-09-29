/* SPDX-License-Identifier: Apache-2.0 */
#ifndef LED_PULSE_H
#define LED_PULSE_H

#include <stdint.h>

/* Brightness 0..255 to pulse width: period * brightness / 255, rounded. */
static inline uint32_t led_pulse_from_brightness(uint32_t period, uint8_t brightness)
{
	return (uint32_t)(((uint64_t)period * brightness + 127U) / 255U);
}

/* Fraction of the period the LED is on for a Brightness, in 0.1 % steps. */
static inline uint32_t led_on_permille(uint8_t brightness)
{
	return (1000U * brightness + 127U) / 255U;
}

#endif /* LED_PULSE_H */
