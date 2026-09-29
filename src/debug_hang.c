/* SPDX-License-Identifier: Apache-2.0 */

#include "debug_hang.h"

#include <zephyr/kernel.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/atomic.h>

static atomic_t requested;

bool debug_hang_requested(void)
{
	return atomic_get(&requested) != 0;
}

static int cmd_hang(const struct shell *sh, size_t argc, char **argv)
{
	ARG_UNUSED(argc);
	ARG_UNUSED(argv);

	atomic_set(&requested, 1);
	shell_print(sh, "hang requested: the main loop stops feeding at its next period");
	return 0;
}

SHELL_STATIC_SUBCMD_SET_CREATE(debug_cmds,
	SHELL_CMD_ARG(hang, NULL, "Stop the main loop feeding the watchdog (debug image only)",
		      cmd_hang, 1, 0),
	SHELL_SUBCMD_SET_END);
SHELL_CMD_REGISTER(debug, &debug_cmds, "Debug-only commands", NULL);
