/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SHELL_NUS_H
#define SHELL_NUS_H

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
 * - On this instance echo, prompt, colours and VT100 are off, so every line the Central reads is
 *   a command reply (or, later, a Heartbeat), with plain "\n" line ends.
 *
 * The serial console keeps its own shell instance.
 */

/* Start the shell thread of the Shell link. Call once, before ble_start(). 0, or -errno. */
int shell_nus_start(void);

#endif /* SHELL_NUS_H */
