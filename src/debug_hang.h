/* SPDX-License-Identifier: Apache-2.0 */
#ifndef DEBUG_HANG_H
#define DEBUG_HANG_H

#include <stdbool.h>
#include <zephyr/sys/util.h>

/*
 * Debug-only watchdog bite proof (CONFIG_C6_HANG_CMD, enabled by debug.conf,
 * never in the production image). The serial-shell command "debug hang" sets
 * a request; the main loop polls it once per period and, when set, stops
 * feeding the watchdog for good, so the board must reset within the window.
 * In the production image the request is a constant false and the compiler
 * removes the branch.
 */
#ifdef CONFIG_C6_HANG_CMD
bool debug_hang_requested(void);
#else
static inline bool debug_hang_requested(void)
{
	return false;
}
#endif

#endif /* DEBUG_HANG_H */
