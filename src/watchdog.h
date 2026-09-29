/* SPDX-License-Identifier: Apache-2.0 */
#ifndef WATCHDOG_H
#define WATCHDOG_H

/*
 * Task watchdog: one channel with a WATCHDOG_WINDOW_MS window, backed by the
 * hardware watchdog (task_wdt HW fallback), fed by the main loop only.
 * A main loop blocked longer than the window ends in a hardware reset whose
 * Reset reason reads "watchdog".
 */

#define WATCHDOG_WINDOW_MS 5000U

/* Arm the channel and print "[WDT] armed window=<ms>ms" once. 0 or -errno. */
int watchdog_arm(void);

/* Feed the channel; a no-op before watchdog_arm(). */
void watchdog_feed(void);

#endif /* WATCHDOG_H */
