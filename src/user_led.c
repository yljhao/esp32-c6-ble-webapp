/* SPDX-License-Identifier: Apache-2.0 */
/*
 * User LED glue: LEDC PWM output plus a readback of the same pad.
 *
 * The PWM spec (channel, 20 kHz period, active-low polarity) comes from the
 * overlay's user-led-pwm alias. The pad and its physical polarity come from
 * the board's led0 gpio-leds node, so the readback judges the PWM path
 * against what the board says the LED is, not against the PWM flag.
 */

#include "user_led.h"
#include "led_pulse.h"

#include <zephyr/kernel.h>
#include <zephyr/drivers/pwm.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/dt-bindings/gpio/espressif-esp32-gpio.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>

LOG_MODULE_REGISTER(user_led, CONFIG_LOG_DEFAULT_LEVEL);

static const struct pwm_dt_spec led_pwm = PWM_DT_SPEC_GET(DT_ALIAS(user_led_pwm));
static const struct gpio_dt_spec led_pad = GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios);

/* One byte per sample. Measured in the reference project on this board: ~1350 samples per 2 ms window
 * through gpio_port_get_raw(); 4096 leaves 3x headroom for a faster loop.
 * Below MIN_SAMPLES the fraction is meaningless and the readback is an error.
 */
#define READBACK_MAX_SAMPLES 4096U
#define READBACK_MIN_SAMPLES 64U
static uint8_t readback_levels[READBACK_MAX_SAMPLES];
static bool ready;

int user_led_init(void)
{
	int ret;

	if (!pwm_is_ready_dt(&led_pwm)) {
		LOG_ERR("PWM device not ready");
		return -ENODEV;
	}
	if (!gpio_is_ready_dt(&led_pad)) {
		LOG_ERR("GPIO device not ready");
		return -ENODEV;
	}

	/*
	 * Enable the pad's input buffer while keeping the output buffer (driven
	 * by the LEDC signal through the GPIO matrix) untouched. Zephyr's ESP32
	 * GPIO driver provides ESP32_GPIO_PIN_OUT_EN for exactly this
	 * "input and output at once, for diagnosis" case.
	 */
	ret = gpio_pin_configure_dt(&led_pad, GPIO_INPUT | ESP32_GPIO_PIN_OUT_EN);
	if (ret < 0) {
		LOG_ERR("pad input enable failed: %d", ret);
		return ret;
	}

	ready = true;
	return user_led_set(0);
}

int user_led_set(uint8_t brightness)
{
	uint32_t pulse = led_pulse_from_brightness(led_pwm.period, brightness);

	if (!ready) {
		return -ENODEV;
	}
	return pwm_set_pulse_dt(&led_pwm, pulse);
}

uint32_t user_led_pwm_hz(void)
{
	return led_pwm.period ? NSEC_PER_SEC / led_pwm.period : 0U;
}

int user_led_readback(struct duty_readback *out)
{
	const uint32_t cps = sys_clock_hw_cycles_per_sec();
	const uint32_t window = (uint32_t)(((uint64_t)cps * USER_LED_READBACK_US) / 1000000U);
	const gpio_port_pins_t mask = BIT(led_pad.pin);
	uint32_t t0, t1;
	uint32_t n = 0;
	unsigned int key;

	/* The sampling rate must be uniform for the edge count to be a
	 * frequency: a preemption inside the window (a Bluetooth controller
	 * interrupt, once it is up) loses edges while the elapsed time keeps
	 * counting, seen in the reference project as freq 5 % low on a live
	 * command. 2 ms with interrupts masked is well inside every deadline
	 * here (5 s watchdog window, 1 s Heartbeat).
	 */
	key = irq_lock();
	t0 = k_cycle_get_32();
	do {
		gpio_port_value_t port = 0;

		(void)gpio_port_get_raw(led_pad.port, &port);
		readback_levels[n++] = (port & mask) ? 1 : 0;
		t1 = k_cycle_get_32();
	} while ((t1 - t0) < window && n < READBACK_MAX_SAMPLES);
	irq_unlock(key);

	duty_readback_compute(readback_levels, n, t1 - t0, cps, out);
	LOG_DBG("readback: %u samples in %u cycles (%u Hz), %u edges", n, t1 - t0, cps,
		out->edges);

	if (n < READBACK_MIN_SAMPLES) {
		LOG_WRN("readback captured only %u samples", n);
		return -EIO;
	}
	return 0;
}

uint32_t user_led_expected_low_permille(uint8_t brightness)
{
	uint32_t on_permille = led_on_permille(brightness);

	/* "On" is low only when the board declares the LED active-low. */
	return (led_pad.dt_flags & GPIO_ACTIVE_LOW) ? on_permille : 1000U - on_permille;
}

void user_led_print_marker(uint8_t brightness, const struct duty_readback *rb)
{
	printk("[LED] brightness=%u duty=%u.%u%% freq=%u\n", brightness,
	       rb->low_permille / 10U, rb->low_permille % 10U, rb->freq_hz);
}
