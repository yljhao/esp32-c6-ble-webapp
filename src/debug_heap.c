/* SPDX-License-Identifier: Apache-2.0 */

/*
 * Debug-only heap report (CONFIG_C6_HEAP_REPORT, enabled by analyze.conf in a build directory of
 * its own, never in the production image): every few seconds it prints the kernel heap (the pool
 * the Bluetooth driver allocates from) as "[DBG] heap ...", next to the thread analyzer's stack
 * report, so the headroom with Bluetooth running can be read from the console.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/sys_heap.h>

#define REPORT_PERIOD_MS 5000

/* Private kernel symbol (kernel/mempool.c, no public header): re-check it when Zephyr is bumped.
 * Acceptable here because this file is debug-only.
 */
extern struct k_heap _system_heap;

static void report(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(report_work, report);

static void report(struct k_work *work)
{
	struct sys_memory_stats stats;

	ARG_UNUSED(work);
	if (sys_heap_runtime_stats_get(&_system_heap.heap, &stats) == 0) {
		/* size = free + allocated: the usable heap, not the requested K_HEAP_MEM_POOL_SIZE */
		printk("\n[DBG] heap size=%zu free=%zu allocated=%zu max_allocated=%zu\n",
		       stats.free_bytes + stats.allocated_bytes, stats.free_bytes,
		       stats.allocated_bytes, stats.max_allocated_bytes);
	}
	(void)k_work_reschedule(&report_work, K_MSEC(REPORT_PERIOD_MS));
}

static int start_report(void)
{
	(void)k_work_reschedule(&report_work, K_MSEC(REPORT_PERIOD_MS));
	return 0;
}

/* Priority 90: late in the APPLICATION level, after every driver and service has initialised */
SYS_INIT(start_report, APPLICATION, 90);
