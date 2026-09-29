/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Testing call: shared contract and security rule. The Shell link must refuse everything but the
 * allow-list with an "ERR " line (the Web App and the Harness read it), and a decision that
 * takes a bypass to break (a "\r" mid-line, a quote, an escape) is cheaper to prove on the host
 * than on the board. Not named in Testing Decisions; the spec leaves the mechanism to the
 * implementer.
 * Seam: link_filter_line() with the verdict and the rebuilt line it returns.
 * Glue, proven on the board: the shell transport that calls it (src/shell_nus.c) and the
 * refusal reaching a Central (Harness: kernel reboot refused, no [BOOT]).
 */

#include <string.h>
#include <zephyr/ztest.h>

#include "link_filter.h"

ZTEST_SUITE(link_filter, NULL, NULL, NULL, NULL, NULL);

static enum link_filter_verdict judge(const char *text, char *out, size_t out_size)
{
	size_t n = 0;

	memset(out, 0xAA, out_size);
	return link_filter_line((const uint8_t *)text, strlen(text), out, out_size, &n);
}

static void zassert_passes_as(const char *in, const char *expected)
{
	char out[160];
	size_t n = 0;
	enum link_filter_verdict v;

	memset(out, 0xAA, sizeof(out));
	v = link_filter_line((const uint8_t *)in, strlen(in), out, sizeof(out), &n);
	zassert_equal(v, LINK_FILTER_PASS, "'%s' must pass", in);
	zassert_equal(n, strlen(expected), "'%s' length", in);
	zassert_mem_equal(out, expected, n, "'%s' rebuilt as", in);
}

static void zassert_refused(const char *in)
{
	char out[160];

	zassert_equal(judge(in, out, sizeof(out)), LINK_FILTER_REFUSE, "'%s' must be refused", in);
}

ZTEST(link_filter, test_refusal_line_is_an_err_line)
{
	zassert_true(strncmp(LINK_FILTER_REFUSAL, "ERR ", 4) == 0);
	zassert_true(strchr(LINK_FILTER_REFUSAL, '\n') == NULL);
}

ZTEST(link_filter, test_led_commands_pass)
{
	zassert_passes_as("led set 128\n", "led set 128\n");
	zassert_passes_as("led get\n", "led get\n");
	/* wrong arguments are the led command's business: it answers with its own ERR line */
	zassert_passes_as("led set\n", "led set\n");
	zassert_passes_as("led set 300\n", "led set 300\n");
	zassert_passes_as("led set abc\n", "led set abc\n");
	zassert_passes_as("led set -5\n", "led set -5\n");
	zassert_passes_as("led set 1 2\n", "led set 1 2\n");
	zassert_passes_as("led get 1\n", "led get 1\n");
}

ZTEST(link_filter, test_everything_else_is_refused)
{
	zassert_refused("kernel reboot\n");
	zassert_refused("kernel reboot cold\n");
	zassert_refused("kernel reboot warm\n");
	zassert_refused("kernel\n");
	zassert_refused("kernel version\n");
	zassert_refused("kernel uptime\n");
	zassert_refused("version\n");
	zassert_refused("app version\n");
	zassert_refused("kernel threads\n");
	zassert_refused("device list\n");
	zassert_refused("help\n");
	zassert_refused("history\n");
	zassert_refused("shell colors off\n");
	zassert_refused("debug hang\n");
	zassert_refused("reboot\n");
	zassert_refused("led\n");
	zassert_refused("led foo\n");
	zassert_refused("led sets 5\n");
	zassert_refused("LED get\n");
	zassert_refused("ledget\n");
	zassert_refused("kernelversion\n");
}

ZTEST(link_filter, test_spacing_is_normalised)
{
	zassert_passes_as("  led   set    64  \n", "led set 64\n");
	zassert_passes_as("led get\r\n", "led get\n");
	zassert_passes_as("led  get \r\n", "led get\n");
}

ZTEST(link_filter, test_empty_lines_are_ignored)
{
	char out[16];

	zassert_equal(judge("\n", out, sizeof(out)), LINK_FILTER_IGNORE);
	zassert_equal(judge("\r\n", out, sizeof(out)), LINK_FILTER_IGNORE);
	zassert_equal(judge("   \n", out, sizeof(out)), LINK_FILTER_IGNORE);
}

ZTEST(link_filter, test_a_second_command_cannot_ride_along)
{
	/* the shell treats "\r" as Enter, so "led get\rkernel reboot" would run both */
	zassert_refused("led get\rkernel reboot\n");
	zassert_refused("led get\r\rkernel reboot\n");
	zassert_refused("led get\n" "kernel reboot\n");
	zassert_refused("\rkernel reboot\n");
	zassert_refused("led get \r\r\n");
}

ZTEST(link_filter, test_control_and_non_ascii_bytes_are_refused)
{
	zassert_refused("led get\t\n");
	zassert_refused("led\tget\n");
	zassert_refused("led get\x1b[A\n");
	zassert_refused("led get\x03\n");
	zassert_refused("led get\x7f\n");
	zassert_refused("led get\x08\x08\x08 kernel reboot\n");
	zassert_refused("led set 5\xc3\xa9\n");
	{
		char out[16];
		const uint8_t with_nul[] = { 'l', 'e', 'd', ' ', 'g', 'e', 't', 0, '\n' };
		size_t n;

		zassert_equal(link_filter_line(with_nul, sizeof(with_nul), out, sizeof(out), &n),
			      LINK_FILTER_REFUSE);
	}
}

ZTEST(link_filter, test_shell_syntax_in_arguments_is_refused)
{
	zassert_refused("led set -h\n");
	zassert_refused("led set --help\n");
	zassert_refused("led get -h\n");
	zassert_refused("led set \"5\"\n");
	zassert_refused("led set '5'\n");
	zassert_refused("led set 5\\\n");
	zassert_refused("led set 1*\n");
	zassert_refused("led set ?\n");
	zassert_refused("led -h\n");
	zassert_refused("kernel -h\n");
	zassert_refused("led -h\n");
}

ZTEST(link_filter, test_word_limit)
{
	zassert_passes_as("led set 1 2 3 4 5 6\n", "led set 1 2 3 4 5 6\n");
	zassert_refused("led set 1 2 3 4 5 6 7\n");
	zassert_refused("led set 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21\n");
}

ZTEST(link_filter, test_a_line_without_its_end_is_refused_not_run)
{
	char out[16];

	zassert_equal(judge("led get", out, sizeof(out)), LINK_FILTER_REFUSE);
	zassert_equal(judge("", out, sizeof(out)), LINK_FILTER_REFUSE);
}

ZTEST(link_filter, test_output_never_exceeds_input_plus_nothing)
{
	/* out needs len + 1 bytes; the rebuilt line is never longer than the input */
	const char *in = "  led   set    64  \n";
	char out[32];
	size_t n = 0;

	memset(out, 0xAA, sizeof(out));
	zassert_equal(link_filter_line((const uint8_t *)in, strlen(in), out, strlen(in) + 1, &n),
		      LINK_FILTER_PASS);
	zassert_true(n <= strlen(in));
	zassert_equal((uint8_t)out[strlen(in) + 1], 0xAA, "wrote past len + 1");
}
