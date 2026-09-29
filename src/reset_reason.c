/* SPDX-License-Identifier: Apache-2.0 */

#include "reset_reason.h"

#include <zephyr/drivers/hwinfo.h>
#include <esp_system.h>

const char *reset_reason_string(void)
{
	uint32_t cause = 0;

	if (hwinfo_get_reset_cause(&cause) == 0 && cause != 0) {
		if (cause & RESET_POR) {
			return "poweron";
		}
		if (cause & RESET_BROWNOUT) {
			return "brownout";
		}
		if (cause & RESET_WATCHDOG) {
			return "watchdog";
		}
		if (cause & RESET_CPU_LOCKUP) {
			return "panic";
		}
		if (cause & RESET_SOFTWARE) {
			return "software";
		}
		if (cause & RESET_PIN) {
			return "pin";
		}
		if (cause & RESET_LOW_POWER_WAKE) {
			return "deepsleep";
		}
	}

	/*
	 * Zephyr's hwinfo driver maps only the classic causes. A reset pulled
	 * through the USB-Serial/JTAG controller (RTS from the host, which is
	 * how every host-side reset in this project works) is ESP_RST_USB and
	 * comes back as 0 above, so fall through to the SoC's own classification.
	 */
	switch (esp_reset_reason()) {
	case ESP_RST_USB:
		return "usb";
	case ESP_RST_JTAG:
		return "jtag";
	case ESP_RST_PWR_GLITCH:
		return "glitch";
	default:
		return "unknown";
	}
}
