/* SPDX-License-Identifier: Apache-2.0 */
#ifndef HEARTBEAT_LINK_H
#define HEARTBEAT_LINK_H

#include <stdint.h>

/*
 * Heartbeat glue: hands each Heartbeat line from the main loop to a sender thread that writes
 * it to the Shell link (shell_nus_notify()).
 *
 * Why a thread: bt_nus_send() can wait without bound for an ATT buffer while the link stalls,
 * and the main loop is the one that feeds the watchdog (spec). The main loop therefore only
 * encodes the line and puts it into a small queue without waiting; the sender thread may block.
 *
 * Bounded drop policy: the queue holds HEARTBEAT_LINK_DEPTH entries (3, i.e. 3 s of backlog: what
 * is worth delivering late; more would only be stale numbers). When the sender is stuck and
 * the queue is full, the OLDEST line is dropped to make room, so after a stall the Central gets
 * the newest numbers, not a backlog of stale ones. A missed Heartbeat is never resent.
 *
 * The line is board output: it does not pass the command filter (link_filter.c) or the shell
 * transport's read side, and it is sent under the shell transport's TX lock so it is never
 * spliced with a command reply.
 */

#define HEARTBEAT_LINK_DEPTH 3

/* Queue Heartbeat `seq` for the Shell link. Never blocks, never sends. The sender thread encodes
 * {"seq":N,"uptime_ms":N} when it takes the entry, so `uptime_ms` is the board's uptime at the
 * moment the line goes out and a sender delay shows in it. Returns the number of stale entries
 * dropped to make room (0 or 1).
 */
int heartbeat_link_post(uint32_t seq);

#endif /* HEARTBEAT_LINK_H */
