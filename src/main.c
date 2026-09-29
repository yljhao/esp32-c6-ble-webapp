/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Boot order (spec): Reset reason marker -> Self-test (a failure is
 * reported, not retried, the boot continues) -> Brightness 128 -> watchdog
 * armed. Later tickets add Bluetooth and the main loop's Heartbeats.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "brightness.h"
#include "debug_hang.h"
#include "reset_reason.h"
#include "selftest.h"
#include "user_led.h"
#include "watchdog.h"

int main(void)
{
	/* The USB-Serial/JTAG console drops bytes while nobody reads it: give
	 * the host time to (re)open the port after the reset.
	 */
	k_msleep(CONFIG_C6_BOOT_MARKER_DELAY_MS);
	/* Leading newline: keeps the marker on its own line if anything left a
	 * prompt or partial line on the console.
	 */
	printk("\n[BOOT] reason=%s\n", reset_reason_string());

	printk("[STAGE] selftest: start\n");
	/* If the PWM or pad is not ready, user_led_init() logs why and the
	 * Self-test then fails at step 0: reported, boot continues.
	 */
	(void)user_led_init();
	(void)selftest_run();

	/* A failure is logged inside; no [LED] marker then, which the Harness reports. */
	(void)brightness_set(BRIGHTNESS_BOOT);

	/* Armed last: the Self-test sweep runs before it, so its length never counts
	 * against the window. A failure is logged inside; the board then runs unguarded.
	 */
	(void)watchdog_arm();

	while (1) {
		k_msleep(1000);
		if (debug_hang_requested()) {
			/* Debug image only: stop feeding for good; the watchdog must reset the board. */
			/* Leading newline: the shell prompt may be on the line. */
			printk("\n[DBG] hang: main loop stops feeding\n");
			k_sleep(K_FOREVER);
		}
		/* The main loop is the only feeder (spec). */
		watchdog_feed();
	}
	return 0;
}
