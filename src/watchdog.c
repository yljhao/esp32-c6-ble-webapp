/* SPDX-License-Identifier: Apache-2.0 */

#include "watchdog.h"

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/watchdog.h>
#include <zephyr/task_wdt/task_wdt.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/reboot.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(watchdog, CONFIG_LOG_DEFAULT_LEVEL);

static int channel = -1;

/*
 * The channel expired: the main loop has not fed it for a whole window. Runs
 * from the task_wdt timer (ISR context). Stop feeding the hardware watchdog
 * (its background feed is this same timer) and let it reset the SoC, so the
 * next boot prints "[BOOT] reason=watchdog" rather than "software". Should
 * the hardware fallback not bite, reboot in software after a bounded wait.
 */
static void on_expired(int channel_id, void *user_data)
{
	ARG_UNUSED(channel_id);
	ARG_UNUSED(user_data);

	uint32_t start = k_cycle_get_32();
	uint32_t limit = sys_clock_hw_cycles_per_sec(); /* 1 s */

	(void)irq_lock();
	while (k_cycle_get_32() - start < limit) {
	}
	sys_reboot(SYS_REBOOT_COLD);
}

int watchdog_arm(void)
{
	const struct device *hw = DEVICE_DT_GET(DT_ALIAS(watchdog0));
	int ret;

	if (channel >= 0) {
		return 0;
	}
	if (!device_is_ready(hw)) {
		LOG_ERR("hardware watchdog not ready");
		return -ENODEV;
	}
	ret = task_wdt_init(hw);
	if (ret < 0) {
		LOG_ERR("task_wdt_init: %d", ret);
		return ret;
	}
	ret = task_wdt_add(WATCHDOG_WINDOW_MS, on_expired, NULL);
	if (ret < 0) {
		LOG_ERR("task_wdt_add: %d", ret);
		return ret;
	}
	channel = ret;
	printk("[WDT] armed window=%ums\n", WATCHDOG_WINDOW_MS);
	return 0;
}

void watchdog_feed(void)
{
	if (channel >= 0) {
		(void)task_wdt_feed(channel);
	}
}
