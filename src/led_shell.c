/* SPDX-License-Identifier: Apache-2.0 */
/*
 * The `led` shell command group (glue): `led set <n>` and `led get`. The decisions and the reply
 * lines are in led_command.c (host suite); this file only feeds the shell's arguments in,
 * applies the Brightness through brightness_set() and prints the line. The group is registered
 * once and so is offered by every shell instance (the serial shell and the Shell link).
 */

#include <zephyr/shell/shell.h>

#include "brightness.h"
#include "led_command.h"

/* Optional arguments the shell accepts (CONFIG_SHELL_ARGC_MAX is 20): more than the commands take,
 * so that led_command_*() answers "ERR too many arguments" for an ordinary excess. On the Shell
 * link link_filter.c stops a command at LINK_FILTER_MAX_WORDS words first, so this limit only
 * matters on the serial shell. Input the shell itself rejects (a bare `led`, `led set -h`, an
 * unknown command) prints shell text on the serial shell; on the Shell link link_filter.c
 * refuses those first with an ERR line.
 */
#define LED_ARGS_MAX 15

static int print_reply(const struct shell *sh, const struct led_command_reply *r)
{
	shell_print(sh, "%s", r->line);
	return r->error ? -EINVAL : 0;
}

static int cmd_set(const struct shell *sh, size_t argc, char **argv)
{
	struct led_command_reply r;

	led_command_set(argc - 1, (const char *const *)&argv[1], &r);
	if (r.action == LED_COMMAND_APPLY && brightness_set(r.value) < 0) {
		led_command_apply_failed(&r);
	}
	return print_reply(sh, &r);
}

static int cmd_get(const struct shell *sh, size_t argc, char **argv)
{
	struct led_command_reply r;

	ARG_UNUSED(argv);
	led_command_get(argc - 1, brightness_get(), &r);
	return print_reply(sh, &r);
}

SHELL_STATIC_SUBCMD_SET_CREATE(led_cmds,
	SHELL_CMD_ARG(set, NULL, "Set the User LED Brightness 0..255: led set <n>", cmd_set, 1,
		      LED_ARGS_MAX),
	SHELL_CMD_ARG(get, NULL, "Print the User LED Brightness: led get", cmd_get, 1,
		      LED_ARGS_MAX),
	SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(led, &led_cmds, "User LED commands", NULL);
