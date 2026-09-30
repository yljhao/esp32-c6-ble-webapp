/* SPDX-License-Identifier: Apache-2.0 */
#ifndef HEARTBEAT_H
#define HEARTBEAT_H

/*
 * Heartbeat (CONTEXT.md): the line {"seq":N,"uptime_ms":N} the board sends about once a second
 * over the Shell link while a Central listens. This module owns the wire contract shared with
 * the Web App and the Harness (the exact line) and the counter's rules:
 *
 * - `seq` is 0 at boot and advances once per second from boot whether or not a Central
 *   listens, so a gap in the numbers a Central sees marks a disconnect and a smaller number
 *   marks a reboot; only a boot resets it;
 * - a period the caller missed (it was busy longer than a second) is consumed, not queued:
 *   `seq` keeps pace with time and at most one Heartbeat is due per poll.
 *
 * Pure C, no Zephyr dependency: the same code runs on the board and in the native_sim host
 * suite (tests/heartbeat).
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HEARTBEAT_PERIOD_MS 1000U
#define HEARTBEAT_MARKER_EVERY 10U /* "[HB] seq=N" on every tenth Heartbeat */
/* Longest line: {"seq":4294967295,"uptime_ms":18446744073709551615} + "\n" + NUL */
#define HEARTBEAT_LINE_MAX 53U

struct heartbeat {
	uint32_t seq;    /* the number of the next Heartbeat */
	uint64_t due_ms; /* uptime at which it is due */
};

/* Boot event: seq 0, the first Heartbeat due at `now_ms`. */
void heartbeat_boot(struct heartbeat *hb, uint64_t now_ms);

/* Poll from the loop. Returns true when a Heartbeat is due and stores its number in *seq; the
 * counter then advances one for that period and one for every further period `now_ms` has
 * already passed.
 */
bool heartbeat_due(struct heartbeat *hb, uint64_t now_ms, uint32_t *seq);

/* Milliseconds from `now_ms` until the next Heartbeat is due; 0 when it is due now. */
uint32_t heartbeat_wait_ms(const struct heartbeat *hb, uint64_t now_ms);

/* True when the serial console prints "[HB] seq=N" for this Heartbeat (every tenth). */
bool heartbeat_marker_due(uint32_t seq);

/* Encode the wire line {"seq":N,"uptime_ms":N}\n into buf (NUL-terminated). Returns the length
 * without the NUL, or -1 when buf is too small.
 */
int heartbeat_encode(char *buf, size_t len, uint32_t seq, uint64_t uptime_ms);

#endif /* HEARTBEAT_H */
