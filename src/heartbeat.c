/* SPDX-License-Identifier: Apache-2.0 */

#include "heartbeat.h"

#include <stdio.h>

void heartbeat_boot(struct heartbeat *hb, uint64_t now_ms)
{
	hb->seq = 0;
	hb->due_ms = now_ms;
}

bool heartbeat_due(struct heartbeat *hb, uint64_t now_ms, uint32_t *seq)
{
	uint64_t missed; /* whole periods passed beyond the due one */

	if (now_ms < hb->due_ms) {
		return false;
	}
	/* Periods already passed beyond the due one are consumed: seq keeps pace with time and the
	 * caller sends once per pass.
	 */
	missed = (now_ms - hb->due_ms) / HEARTBEAT_PERIOD_MS;
	*seq = hb->seq + (uint32_t)missed; /* unsigned: wraps, never goes negative */
	hb->seq = *seq + 1U;
	hb->due_ms += (missed + 1U) * HEARTBEAT_PERIOD_MS;
	return true;
}

uint32_t heartbeat_wait_ms(const struct heartbeat *hb, uint64_t now_ms)
{
	return now_ms >= hb->due_ms ? 0U : (uint32_t)(hb->due_ms - now_ms);
}

bool heartbeat_marker_due(uint32_t seq)
{
	return (seq % HEARTBEAT_MARKER_EVERY) == 0U;
}

int heartbeat_encode(char *buf, size_t len, uint32_t seq, uint64_t uptime_ms)
{
	/* Unsigned conversions only: no value ever prints with a sign. */
	int n = snprintf(buf, len, "{\"seq\":%u,\"uptime_ms\":%llu}\n", (unsigned int)seq,
			 (unsigned long long)uptime_ms);

	if (n < 0 || (size_t)n >= len) {
		return -1;
	}
	return n;
}
