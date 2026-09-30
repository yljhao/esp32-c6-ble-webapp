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

/*
 * Debug-only Heartbeat stall proof (same option, ticket 09). "debug stall" makes the Heartbeat
 * sender thread stop for good inside shell_nus_notify(), holding the TX lock as a bt_nus_send()
 * stuck on a stalled link would; the main loop must then keep feeding the watchdog and printing "[HB] seq=N". In the
 * production image the stall point is empty.
 */
#ifdef CONFIG_C6_HANG_CMD
void debug_hb_stall_point(void);
#else
static inline void debug_hb_stall_point(void)
{
}
#endif

#endif /* DEBUG_HANG_H */
