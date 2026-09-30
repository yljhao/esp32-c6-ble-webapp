/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Boot order (spec): Reset reason marker -> Self-test (a failure is
 * reported, not retried, the boot continues) -> Brightness 128 -> watchdog
 * armed -> Shell link started -> Bluetooth enabled and advertising. The main loop then feeds the
 * watchdog and emits the Heartbeats.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "ble.h"
#include "brightness.h"
#include "debug_hang.h"
#include "heartbeat.h"
#include "heartbeat_link.h"
#include "reset_reason.h"
#include "selftest.h"
#include "shell_nus.h"
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

	/* The Shell link's shell thread before Bluetooth, so a command written by the first Central
	 * finds it running. A failure is reported inside; the serial shell still works.
	 */
	(void)shell_nus_start();

	/* Bluetooth after the watchdog (spec boot order). A failure is reported inside; the
	 * board then runs without a radio.
	 */
	(void)ble_start();

	/* The main loop is the only feeder (spec) and the one that emits Heartbeats. It sleeps until
	 * the next Heartbeat is due, never longer than one period (1 s) against the 5 s window; the
	 * Harness expects a bite 4 to 5 s after the hang, so nothing here may wait for anything
	 * else: the Heartbeat line is only queued for the sender thread (heartbeat_link.c), which is
	 * the one that can block on a stalled link.
	 */
	struct heartbeat hb;
	uint32_t dropped_total = 0;

	heartbeat_boot(&hb, (uint64_t)k_uptime_get());
	while (1) {
		uint64_t now = (uint64_t)k_uptime_get();
		uint32_t seq;

		if (debug_hang_requested()) {
			/* Debug image only: stop feeding for good; the watchdog must reset the board.
			 * Leading newline: the shell prompt may be on the line.
			 */
			printk("\n[DBG] hang: main loop stops feeding\n");
			k_sleep(K_FOREVER);
		}
		/* seq counts from boot whether or not a Central listens; the sender drops the line
		 * when nobody is subscribed.
		 */
		if (heartbeat_due(&hb, now, &seq)) {
			int dropped = heartbeat_link_post(seq);

			if (dropped > 0) {
				dropped_total += (uint32_t)dropped;
				/* a stalled link drops one a second: report the 1st, 2nd, 4th, 8th ... */
				if ((dropped_total & (dropped_total - 1U)) == 0U) {
					printk("\n[HB] link stalled: %u stale heartbeat(s) dropped\n",
					       dropped_total);
				}
			}
			if (heartbeat_marker_due(seq)) {
				printk("\n[HB] seq=%u\n", seq);
			}
		}
		watchdog_feed();
		k_msleep(MAX(1U, MIN(heartbeat_wait_ms(&hb, (uint64_t)k_uptime_get()),
				     HEARTBEAT_PERIOD_MS)));
	}
	return 0;
}
