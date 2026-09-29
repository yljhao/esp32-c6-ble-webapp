/*
 * Testing call: per Testing Decisions (LED command parsing); it is also the shared contract of the Shell link
 * (the Web App and the Harness read these exact reply lines).
 * Seam: led_command_set() and led_command_get() with the reply they fill in.
 * Glue, proven on the board: the shell command handlers (src/led_shell.c), brightness_set().
 */
/* SPDX-License-Identifier: Apache-2.0 */

#include <string.h>
#include <zephyr/ztest.h>

#include "led_command.h"

ZTEST_SUITE(led_command, NULL, NULL, NULL, NULL, NULL);

static struct led_command_reply set1(const char *arg)
{
	const char *args[] = { arg };
	struct led_command_reply r;

	led_command_set(1, args, &r);
	return r;
}

static void zassert_applies(const char *arg, uint8_t value, const char *line)
{
	struct led_command_reply r = set1(arg);

	zassert_equal(r.action, LED_COMMAND_APPLY, "'%s' must be applied, got '%s'", arg, r.line);
	zassert_equal(r.value, value, "'%s' value", arg);
	zassert_str_equal(r.line, line);
}

static void zassert_rejects(size_t nargs, const char *const *args, const char *line)
{
	struct led_command_reply r;

	led_command_set(nargs, args, &r);
	zassert_equal(r.action, LED_COMMAND_REPLY_ONLY, "must not be applied, line '%s'", r.line);
	zassert_str_equal(r.line, line);
}

ZTEST(led_command, test_accepted_values_reply_LED_n)
{
	zassert_applies("0", 0, "LED 0");
	zassert_applies("128", 128, "LED 128");
	zassert_applies("255", 255, "LED 255");
	zassert_applies("7", 7, "LED 7");
}

ZTEST(led_command, test_leading_zeros_are_the_same_number)
{
	zassert_applies("007", 7, "LED 7");
	zassert_applies("000", 0, "LED 0");
}

ZTEST(led_command, test_out_of_range_is_rejected_not_clamped)
{
	const char *a300[] = { "300" };
	const char *a256[] = { "256" };
	const char *huge[] = { "99999999999999999999" };

	zassert_rejects(1, a300, "ERR out of range 0-255");
	zassert_rejects(1, a256, "ERR out of range 0-255");
	zassert_rejects(1, huge, "ERR out of range 0-255");
}

ZTEST(led_command, test_non_numeric_is_rejected)
{
	const char *abc[] = { "abc" };
	const char *neg[] = { "-5" };
	const char *plus[] = { "+5" };
	const char *hex[] = { "0x10" };
	const char *frac[] = { "1.5" };
	const char *mixed[] = { "12a" };
	const char *empty[] = { "" };

	zassert_rejects(1, abc, "ERR not a number");
	zassert_rejects(1, neg, "ERR not a number");
	zassert_rejects(1, plus, "ERR not a number");
	zassert_rejects(1, hex, "ERR not a number");
	zassert_rejects(1, frac, "ERR not a number");
	zassert_rejects(1, mixed, "ERR not a number");
	zassert_rejects(1, empty, "ERR not a number");
}

ZTEST(led_command, test_missing_argument_is_rejected)
{
	zassert_rejects(0, NULL, "ERR missing value");
}

ZTEST(led_command, test_extra_arguments_are_rejected)
{
	const char *two[] = { "128", "1" };

	zassert_rejects(2, two, "ERR too many arguments");
}

ZTEST(led_command, test_get_replies_the_current_brightness)
{
	struct led_command_reply r;

	led_command_get(0, 0, &r);
	zassert_equal(r.action, LED_COMMAND_REPLY_ONLY);
	zassert_str_equal(r.line, "LED 0");
	led_command_get(0, 128, &r);
	zassert_str_equal(r.line, "LED 128");
	led_command_get(0, 255, &r);
	zassert_str_equal(r.line, "LED 255");
}

ZTEST(led_command, test_get_with_an_argument_is_rejected)
{
	struct led_command_reply r;

	led_command_get(1, 128, &r);
	zassert_equal(r.action, LED_COMMAND_REPLY_ONLY);
	zassert_str_equal(r.line, "ERR too many arguments");
}

ZTEST(led_command, test_error_flag_marks_exactly_the_ERR_lines)
{
	const char *a300[] = { "300" };
	struct led_command_reply r;

	led_command_set(1, a300, &r);
	zassert_true(r.error);
	led_command_set(0, NULL, &r);
	zassert_true(r.error);
	r = set1("5");
	zassert_false(r.error);
	led_command_get(0, 5, &r);
	zassert_false(r.error);
	led_command_get(1, 5, &r);
	zassert_true(r.error);
	led_command_apply_failed(&r);
	zassert_true(r.error);
}

ZTEST(led_command, test_apply_failure_line_is_an_error_line)
{
	struct led_command_reply r = set1("128");

	led_command_apply_failed(&r);
	zassert_equal(r.action, LED_COMMAND_REPLY_ONLY);
	zassert_true(strncmp(r.line, "ERR ", 4) == 0);
}

ZTEST(led_command, test_every_line_fits_the_reply_buffer_and_has_no_newline)
{
	const char *inputs[] = { "0", "255", "300", "abc", "", "99999999999999999999" };

	for (size_t i = 0; i < ARRAY_SIZE(inputs); i++) {
		struct led_command_reply r = set1(inputs[i]);

		zassert_true(strlen(r.line) < sizeof(r.line));
		zassert_is_null(strchr(r.line, '\n'));
	}
}
