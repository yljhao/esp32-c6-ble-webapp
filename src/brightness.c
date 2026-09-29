/* SPDX-License-Identifier: Apache-2.0 */

#include "brightness.h"
#include "user_led.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

LOG_MODULE_REGISTER(brightness, CONFIG_LOG_DEFAULT_LEVEL);

static atomic_t current; /* 0 until the first brightness_set() */

int brightness_set(uint8_t brightness)
{
	struct duty_readback rb;
	int ret;

	ret = user_led_set(brightness);
	if (ret < 0) {
		LOG_ERR("user_led_set(%u): %d", brightness, ret);
		return ret;
	}

	/* The readback samples the pad for ~2 ms in this thread: short enough
	 * for the watchdog window (5 s) and the Heartbeat cadence (1 s).
	 */
	k_msleep(USER_LED_SETTLE_MS);
	ret = user_led_readback(&rb);
	if (ret < 0) {
		LOG_WRN("readback after brightness %u: %d", brightness, ret);
	}
	user_led_print_marker(brightness, &rb);

	atomic_set(&current, brightness);
	return 0;
}

uint8_t brightness_get(void)
{
	return (uint8_t)atomic_get(&current);
}
