/* SPDX-License-Identifier: Apache-2.0 */

#include "selftest.h"
#include "user_led.h"

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(selftest, CONFIG_LOG_DEFAULT_LEVEL);

#define SWEEP_STEP_MS      2       /* k_msleep(2) is ~3 ms: 0->255 in ~0.8 s each way */
#define DUTY_TOL_PERMILLE  20U     /* +-2 % */
#define FREQ_TOL_PERCENT   5U      /* +-5 % of the PWM frequency */

static const uint8_t readback_points[] = {0, 128, 255};

static bool readback_ok(uint8_t brightness, const struct duty_readback *rb)
{
	uint32_t pwm_hz = user_led_pwm_hz();
	uint32_t want_low = user_led_expected_low_permille(brightness);
	/* At 0 and 255 the driver parks the pad at a constant level: no edges. */
	uint32_t want_freq = (brightness == 0 || brightness == 255) ? 0U : pwm_hz;
	uint32_t dduty = rb->low_permille > want_low ? rb->low_permille - want_low
						      : want_low - rb->low_permille;
	uint32_t dfreq = rb->freq_hz > want_freq ? rb->freq_hz - want_freq
						  : want_freq - rb->freq_hz;

	return dduty <= DUTY_TOL_PERMILLE && dfreq <= pwm_hz * FREQ_TOL_PERCENT / 100U;
}

/* Ramp to target, taking a readback at every point on the way up. Returns 0,
 * or the 1-based readback step that failed; a driver error reports the step
 * being worked on (0 before the first readback).
 */
static int sweep_to(uint8_t from, uint8_t to, int *step)
{
	int dir = (to >= from) ? 1 : -1;
	int b = from;

	for (;;) {
		int ret = user_led_set((uint8_t)b);

		if (ret < 0) {
			LOG_ERR("user_led_set(%d): %d", b, ret);
			return *step;
		}

		for (size_t i = 0; i < ARRAY_SIZE(readback_points); i++) {
			if (readback_points[i] != b || dir < 0) {
				continue;
			}
			struct duty_readback rb;

			(*step)++;
			k_msleep(USER_LED_SETTLE_MS);
			ret = user_led_readback(&rb);
			user_led_print_marker((uint8_t)b, &rb);
			if (ret < 0 || !readback_ok((uint8_t)b, &rb)) {
				return *step;
			}
		}

		if (b == to) {
			return 0;
		}
		b += dir;
		k_msleep(SWEEP_STEP_MS);
	}
}

bool selftest_run(void)
{
	int step = 0;
	int failed;

	failed = sweep_to(0, 255, &step);
	if (failed == 0) {
		failed = sweep_to(255, 0, &step);
	}
	/* Park the LED at 0; main applies the boot Brightness (128) afterwards. */
	(void)user_led_set(0);

	if (failed == 0) {
		printk("[STAGE] selftest: done\n");
		return true;
	}
	printk("[STAGE] selftest: fail step=%d\n", failed);
	return false;
}
