/*
 * Testing call: led_pulse.h gets a host unit test because it is pure arithmetic (Brightness to pulse width and
 * expected duty), the numbers the Duty readback is judged against; ported with the module it serves.
 * Seam: led_pulse_from_brightness() and led_on_permille().
 * Glue, proven on the board: user_led.c (PWM driver call), selftest.c (tolerances).
 */
/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Host unit suite for the Brightness to pulse conversion (src/led_pulse.h):
 * pure arithmetic, period * brightness / 255 rounded. 0 -> 0, 255 -> the
 * full period, 128 -> the rounded midpoint. Polarity is not tested here:
 * the devicetree owns it (PWM_POLARITY_INVERTED on the pwms cell).
 */

#include <zephyr/ztest.h>

#include "led_pulse.h"

/* The board's period: 20 kHz (boards overlay), in nanoseconds. */
#define PERIOD_20KHZ_NS 50000U

ZTEST_SUITE(led_pulse, NULL, NULL, NULL, NULL, NULL);

ZTEST(led_pulse, test_0_is_no_pulse)
{
	zassert_equal(led_pulse_from_brightness(PERIOD_20KHZ_NS, 0), 0U);
}

ZTEST(led_pulse, test_255_is_the_full_period)
{
	zassert_equal(led_pulse_from_brightness(PERIOD_20KHZ_NS, 255), PERIOD_20KHZ_NS);
}

ZTEST(led_pulse, test_128_is_the_rounded_midpoint)
{
	/* 50000 * 128 / 255 = 25098.04 -> 25098 */
	zassert_equal(led_pulse_from_brightness(PERIOD_20KHZ_NS, 128), 25098U);
}

ZTEST(led_pulse, test_rounds_to_nearest_not_down)
{
	/* 50000 * 1 / 255 = 196.08 -> 196; 50000 * 254 / 255 = 49803.9 -> 49804 */
	zassert_equal(led_pulse_from_brightness(PERIOD_20KHZ_NS, 1), 196U);
	zassert_equal(led_pulse_from_brightness(PERIOD_20KHZ_NS, 254), 49804U);
	/* 1000 * 128 / 255 = 502.1 -> 502 (the .5 case: 255 * 1 / 255 = 1 exact) */
	zassert_equal(led_pulse_from_brightness(1000U, 128), 502U);
	zassert_equal(led_pulse_from_brightness(255U, 1), 1U);
}

ZTEST(led_pulse, test_monotonic_and_within_period)
{
	uint32_t prev = 0;

	for (unsigned int b = 0; b <= 255U; b++) {
		uint32_t pulse = led_pulse_from_brightness(PERIOD_20KHZ_NS, (uint8_t)b);

		zassert_true(pulse >= prev, "brightness %u: %u < %u", b, pulse, prev);
		zassert_true(pulse <= PERIOD_20KHZ_NS, "brightness %u: %u > period", b, pulse);
		prev = pulse;
	}
}

ZTEST(led_pulse, test_zero_period_gives_zero)
{
	zassert_equal(led_pulse_from_brightness(0U, 255), 0U);
}

ZTEST(led_pulse, test_no_overflow_for_a_long_period)
{
	/* A 1 s period in ns * 255 exceeds 32 bits; the conversion is 64-bit. */
	zassert_equal(led_pulse_from_brightness(1000000000U, 255), 1000000000U);
	zassert_equal(led_pulse_from_brightness(1000000000U, 128), 501960784U);
}

/* The readback's expectation uses the same arithmetic in 0.1 % steps. */
ZTEST(led_pulse, test_on_permille_matches_the_pulse_fraction)
{
	zassert_equal(led_on_permille(0), 0U);
	zassert_equal(led_on_permille(255), 1000U);
	zassert_equal(led_on_permille(128), 502U);
	zassert_equal(led_on_permille(180), 706U); /* 70.6 % (ticket 07) */
}
