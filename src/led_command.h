/* SPDX-License-Identifier: Apache-2.0 */
#ifndef LED_COMMAND_H
#define LED_COMMAND_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * The `led set <n>` / `led get` commands as decisions (pure C, no Zephyr: it runs in the host
 * suite tests/led_command). It owns the reply lines of the wire contract (spec: Shell link):
 *
 *   success          "LED <n>"
 *   rejected         "ERR <reason>"   the Brightness is left unchanged
 *
 * Accepted: 1 or more decimal digits (leading zeros allowed) with a value of 0..255. Rejected,
 * never clamped: a value above 255, anything with a sign, a prefix or a non-digit, an empty
 * argument, a missing argument, extra arguments. The glue (src/led_shell.c) applies the value
 * when the action says so and prints the line.
 */

enum led_command_action {
	LED_COMMAND_REPLY_ONLY, /* print the line, change nothing */
	LED_COMMAND_APPLY,      /* apply `value` as the Brightness, then print the line */
};

struct led_command_reply {
	enum led_command_action action;
	bool error;     /* the line is an "ERR " line (the command was rejected or failed) */
	uint8_t value;  /* the Brightness to apply when action is LED_COMMAND_APPLY */
	char line[32];  /* reply line without the newline */
};

/* `led set` with its `nargs` arguments (the words after "set"). */
void led_command_set(size_t nargs, const char *const *args, struct led_command_reply *out);

/* `led get` with its `nargs` arguments (none accepted); `current` is the Brightness now. */
void led_command_get(size_t nargs, uint8_t current, struct led_command_reply *out);

/* Turn an APPLY reply into an error line after the LED could not be driven. */
void led_command_apply_failed(struct led_command_reply *out);

#endif /* LED_COMMAND_H */
