/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SHELL_NUS_H
#define SHELL_NUS_H

#include <stddef.h>
#include <stdint.h>

/*
 * The Shell link (ADR-0001): a Zephyr shell instance whose transport is the Nordic UART Service.
 * Upstream Zephyr 4.4.2 has NUS but no shell backend over it, so this is the project's own.
 *
 * - Central to board: bytes written to the NUS RX characteristic are queued out of the Bluetooth
 *   callback, one complete line (up to and including "\n") at a time, and read by the shell
 *   thread. A line that is cut off by a disconnect, or longer than the line buffer, is dropped,
 *   never run.
 * - Board to Central: the shell's output is collected and sent as NUS notifications of at most
 *   ATT MTU - 3 bytes (nus_chunk.c) at each end of line. Output while no Central has subscribed
 *   is dropped.
 * - Command restriction (ticket 08): every queued line is judged by link_filter_line() on the
 *   shell thread before the shell sees a byte. Only the allow-list (`led set` and `led get`,
 *   ADR-0001) gets through, rebuilt from its words; anything else is answered with
 *   "ERR command not allowed" and never reaches the shell, so this instance has no other
 *   command, no shell error text and no help. The serial shell keeps every command.
 * - On this instance echo, prompt, colours and VT100 are off, so every line the Central reads is
 *   a command reply or a Heartbeat, with plain "\n" line ends.
 *
 * The serial console keeps its own shell instance.
 */

/* Start the shell thread of the Shell link. Call once, before ble_start(). 0, or -errno. */
int shell_nus_start(void);

/*
 * Board output on the Shell link that does not come from the shell: the Heartbeat (ticket 09).
 * `data` must be whole lines. It does not pass the command filter or the shell transport's read
 * side (it is output, not a command); it is chunked like the shell's output and sent under the
 * same lock, so a Heartbeat line and a command reply are not spliced as long as a reply is one
 * line shorter than the 256-byte TX buffer (every reply today is one short line; a longer reply
 * is flushed in pieces and a Heartbeat could land between them). Returns 0, or -ENOTCONN
 * when no Central is connected and subscribed (the bytes are dropped), or the error that ended
 * the send.
 *
 * May wait without bound for an ATT buffer while the link is stalled (bt_nus_send). Never call it
 * from the main loop: heartbeat_link.c calls it from a thread of its own.
 */
int shell_nus_notify(const uint8_t *data, size_t len);

#endif /* SHELL_NUS_H */
