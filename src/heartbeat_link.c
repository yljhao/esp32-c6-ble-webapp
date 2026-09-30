/* SPDX-License-Identifier: Apache-2.0 */

#include "heartbeat_link.h"

#include "heartbeat.h"
#include "shell_nus.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(heartbeat_link, LOG_LEVEL_INF);

/* Stack: the same 2048 as the shell threads, which run the same bt_nus_send() path. Measured with
 * the thread analyzer over a Connection that received Heartbeats: 640 of 2048 (board-notes,
 * Ticket 09); kept at 2048 for the notification path at the smallest MTU.
 */
#define SENDER_STACK_SIZE 2048
/* Preemptible priority 10: below the main thread (0), the Bluetooth threads (-1 to 8) and the
 * controller task (2), so the sender may sit in bt_nus_send() without holding any of them up;
 * above the shell threads (lowest application priority), so a slow shell command does not delay
 * a Heartbeat's uptime_ms.
 */
#define SENDER_PRIORITY K_PRIO_PREEMPT(10)

K_MSGQ_DEFINE(hb_queue, sizeof(uint32_t), HEARTBEAT_LINK_DEPTH, 4);

int heartbeat_link_post(uint32_t seq)
{
	uint32_t line = seq;
	uint32_t stale;
	int dropped = 0;

	/* Never wait (K_NO_WAIT): the caller feeds the watchdog. The sender is the only consumer,
	 * so at most one round of "make room" is needed; a second failure gives up the new line.
	 */
	if (k_msgq_put(&hb_queue, &line, K_NO_WAIT) != 0) {
		if (k_msgq_get(&hb_queue, &stale, K_NO_WAIT) == 0) {
			dropped = 1;
		}
		(void)k_msgq_put(&hb_queue, &line, K_NO_WAIT);
	}
	return dropped;
}

static void sender_entry(void *p1, void *p2, void *p3)
{
	char text[HEARTBEAT_LINE_MAX];
	uint32_t seq;
	int n;
	int err;

	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	while (1) {
		(void)k_msgq_get(&hb_queue, &seq, K_FOREVER);
		n = heartbeat_encode(text, sizeof(text), seq, (uint64_t)k_uptime_get());
		if (n < 0) {
			continue; /* cannot happen: HEARTBEAT_LINE_MAX holds the longest line */
		}
		/* -ENOTCONN: nobody is connected and subscribed; the Heartbeat is not sent then. */
		err = shell_nus_notify((const uint8_t *)text, (size_t)n);
		if (err && err != -ENOTCONN) {
			LOG_WRN("heartbeat not sent (err %d)", err);
		}
	}
}

K_THREAD_DEFINE(heartbeat_sender, SENDER_STACK_SIZE, sender_entry, NULL, NULL, NULL,
		SENDER_PRIORITY, 0, 0);
