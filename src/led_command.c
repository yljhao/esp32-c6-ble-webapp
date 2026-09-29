/* SPDX-License-Identifier: Apache-2.0 */

#include "led_command.h"

#include <stdio.h>

#define ERR_MISSING   "ERR missing value"
#define ERR_NOT_NUM   "ERR not a number"
#define ERR_RANGE     "ERR out of range 0-255"
#define ERR_EXTRA     "ERR too many arguments"
#define ERR_NOT_APPLY "ERR led not applied"

static void reply_error(struct led_command_reply *out, const char *line)
{
	out->action = LED_COMMAND_REPLY_ONLY;
	out->error = true;
	out->value = 0;
	snprintf(out->line, sizeof(out->line), "%s", line);
}

static void reply_value(struct led_command_reply *out, enum led_command_action action, uint8_t v)
{
	out->action = action;
	out->error = false;
	out->value = v;
	snprintf(out->line, sizeof(out->line), "LED %u", (unsigned int)v);
}

void led_command_set(size_t nargs, const char *const *args, struct led_command_reply *out)
{
	const char *s;
	unsigned long value = 0;

	if (nargs == 0 || args == NULL) {
		reply_error(out, ERR_MISSING);
		return;
	}
	if (nargs > 1) {
		reply_error(out, ERR_EXTRA);
		return;
	}
	s = args[0];
	if (s == NULL || *s == '\0') {
		reply_error(out, ERR_NOT_NUM);
		return;
	}
	for (const char *p = s; *p != '\0'; p++) {
		if (*p < '0' || *p > '9') {
			reply_error(out, ERR_NOT_NUM);
			return;
		}
	}
	/* Digits only from here: accumulate with a cap so a long string cannot overflow. */
	for (const char *p = s; *p != '\0'; p++) {
		value = value * 10UL + (unsigned long)(*p - '0');
		if (value > 255UL) {
			value = 256UL;
		}
	}
	if (value > 255UL) {
		reply_error(out, ERR_RANGE);
		return;
	}
	reply_value(out, LED_COMMAND_APPLY, (uint8_t)value);
}

void led_command_get(size_t nargs, uint8_t current, struct led_command_reply *out)
{
	if (nargs > 0) {
		reply_error(out, ERR_EXTRA);
		return;
	}
	reply_value(out, LED_COMMAND_REPLY_ONLY, current);
}

void led_command_apply_failed(struct led_command_reply *out)
{
	reply_error(out, ERR_NOT_APPLY);
}
