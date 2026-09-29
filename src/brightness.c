/* SPDX-License-Identifier: Apache-2.0 */

#include "brightness.h"
#include "user_led.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/atomic.h>

LOG_MODULE_REGISTER(brightness, CONFIG_LOG_DEFAULT_LEVEL);

static atomic_t current; /* 0 until the first brightness_set() */

/* set, settle, readback and the remembered value are one step: a second
 * caller (the shell thread, later) must not run its readback over the
 * shared sample buffer or interleave its set. Held for about 5 ms.
 */
static K_MUTEX_DEFINE(apply_lock);
#define APPLY_LOCK_WAIT K_MSEC(500)

int brightness_set(uint8_t brightness)
{
	struct duty_readback rb;
	int ret;

	ret = k_mutex_lock(&apply_lock, APPLY_LOCK_WAIT);
	if (ret < 0) {
		LOG_ERR("brightness %u: apply lock busy: %d", brightness, ret);
		return ret;
	}

	ret = user_led_set(brightness);
	if (ret < 0) {
		LOG_ERR("user_led_set(%u): %d", brightness, ret);
		k_mutex_unlock(&apply_lock);
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
	k_mutex_unlock(&apply_lock);
	return 0;
}

uint8_t brightness_get(void)
{
	return (uint8_t)atomic_get(&current);
}
