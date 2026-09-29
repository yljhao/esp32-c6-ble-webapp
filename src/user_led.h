/* SPDX-License-Identifier: Apache-2.0 */
#ifndef USER_LED_H
#define USER_LED_H

#include <stdint.h>
#include "duty_readback.h"

/* Duty readback window: about 40 periods at 20 kHz. */
#define USER_LED_READBACK_US 2000U
/* Wait after user_led_set() before a readback so the LEDC update has landed. */
#define USER_LED_SETTLE_MS 2

/* Ready the PWM channel and the pad's input buffer. Returns 0 or -errno. */
int user_led_init(void);

/* Apply a Brightness 0..255 immediately, no ramp. Returns 0 or -errno. */
int user_led_set(uint8_t brightness);

/* PWM frequency in Hz as declared in the devicetree (period of the pwms cell). */
uint32_t user_led_pwm_hz(void);

/* Sample the LED pad for USER_LED_READBACK_US and compute low fraction and
 * edge frequency. Runs in the caller's thread. Returns 0 or -errno.
 */
int user_led_readback(struct duty_readback *out);

/* Expected low fraction (0.1 % steps) of the pad for a Brightness, taken
 * from the board's own declaration of the User LED polarity (led0 node).
 */
uint32_t user_led_expected_low_permille(uint8_t brightness);

/* Print "[LED] brightness=<n> duty=<pct> freq=<hz>" for a readback. */
void user_led_print_marker(uint8_t brightness, const struct duty_readback *rb);

#endif /* USER_LED_H */
