/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Boot: give the host time to (re)open the console after the reset, since
 * the USB-Serial/JTAG console drops bytes while nobody reads it, then print
 * the Reset reason as the first serial marker.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "reset_reason.h"

int main(void)
{
	k_msleep(CONFIG_C6_BOOT_MARKER_DELAY_MS);
	/* Leading newline: keeps the marker on its own line if anything left a
	 * prompt or partial line on the console.
	 */
	printk("\n[BOOT] reason=%s\n", reset_reason_string());
	return 0;
}
