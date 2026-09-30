/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Testing call: per Testing Decisions (Heartbeat: seq 0 at boot and +1 per second from boot,
 * advances while nobody listens, missed periods consumed not queued, JSON encoding at maximum
 * values fits its buffer): a shared contract (the Web App and the Harness parse the line) and
 * slow rules (a period rule that takes minutes to exercise on the board).
 * Seam: heartbeat_boot / heartbeat_due / heartbeat_wait_ms / heartbeat_marker_due /
 * heartbeat_encode.
 * Glue, proven on the board: the main loop that polls it and feeds the watchdog, the sender
 * thread that hands the line to the Shell link (src/heartbeat_link.c, src/shell_nus.c).
 */

#include <string.h>
#include <zephyr/ztest.h>

#include "heartbeat.h"

static struct heartbeat hb;

static void before(void *fixture)
{
	ARG_UNUSED(fixture);
	heartbeat_boot(&hb, 0);
}

ZTEST_SUITE(heartbeat, NULL, NULL, before, NULL, NULL);

/* -- counter: boot, cadence ----------------------------------------------------------------- */

ZTEST(heartbeat, test_first_heartbeat_is_seq_zero_at_boot)
{
	uint32_t seq = 99;

	heartbeat_boot(&hb, 2500);
	zassert_false(heartbeat_due(&hb, 2499, &seq), "due before the boot time");
	zassert_equal(seq, 99, "seq written without a Heartbeat being due");
	zassert_true(heartbeat_due(&hb, 2500, &seq));
	zassert_equal(seq, 0, "first seq %u", seq);
}

ZTEST(heartbeat, test_one_per_second_from_boot_no_drift)
{
	uint32_t seq;

	zassert_true(heartbeat_due(&hb, 0, &seq));
	zassert_equal(seq, 0);
	zassert_false(heartbeat_due(&hb, 200, &seq));
	zassert_false(heartbeat_due(&hb, 999, &seq));
	zassert_true(heartbeat_due(&hb, 1150, &seq)); /* 150 ms late */
	zassert_equal(seq, 1);
	zassert_false(heartbeat_due(&hb, 1999, &seq));
	zassert_true(heartbeat_due(&hb, 2000, &seq), "the cadence drifted by the lateness");
	zassert_equal(seq, 2);
}

ZTEST(heartbeat, test_seq_advances_with_time_when_nobody_listens)
{
	uint32_t seq = 0;

	/* The counter has no notion of a listener: polling for 60 s gives 0..59 in order. */
	for (uint64_t t = 0; t < 60000; t += 100) {
		if (heartbeat_due(&hb, t, &seq)) {
			zassert_equal(seq, t / 1000, "seq %u at %llu ms", seq, (unsigned long long)t);
		}
	}
	zassert_equal(seq, 59, "last seq %u", seq);
}

ZTEST(heartbeat, test_missed_periods_are_consumed_not_queued)
{
	uint32_t seq;

	zassert_true(heartbeat_due(&hb, 0, &seq));
	zassert_equal(seq, 0);
	/* The caller was busy for 3.5 s: one Heartbeat now, numbered by the time that passed. */
	zassert_true(heartbeat_due(&hb, 3500, &seq));
	zassert_equal(seq, 3, "seq %u after 3.5 s", seq);
	zassert_false(heartbeat_due(&hb, 3900, &seq), "a missed period was queued");
	zassert_true(heartbeat_due(&hb, 4000, &seq));
	zassert_equal(seq, 4);
}

ZTEST(heartbeat, test_boot_resets_seq)
{
	uint32_t seq;

	zassert_true(heartbeat_due(&hb, 0, &seq));
	zassert_true(heartbeat_due(&hb, 20000, &seq));
	zassert_equal(seq, 20);

	heartbeat_boot(&hb, 30000);
	zassert_true(heartbeat_due(&hb, 30000, &seq));
	zassert_equal(seq, 0, "seq %u after boot", seq);
}

ZTEST(heartbeat, test_seq_wraps_unsigned_without_sign)
{
	char buf[HEARTBEAT_LINE_MAX];
	uint32_t seq;

	hb.seq = 4294967295U;
	zassert_true(heartbeat_due(&hb, 0, &seq));
	zassert_equal(seq, 4294967295U);
	zassert_true(heartbeat_encode(buf, sizeof(buf), seq, 4294967295000ULL) > 0);
	zassert_str_equal(buf, "{\"seq\":4294967295,\"uptime_ms\":4294967295000}\n");
	zassert_true(heartbeat_due(&hb, 1000, &seq));
	zassert_equal(seq, 0, "wrap gave %u", seq);
}

/* -- wait until the next Heartbeat (the main loop sleeps this long) -------------------------- */

ZTEST(heartbeat, test_wait_counts_down_to_the_due_time_and_never_exceeds_a_period)
{
	uint32_t seq;

	zassert_equal(heartbeat_wait_ms(&hb, 0), 0, "first Heartbeat is due at boot");
	zassert_true(heartbeat_due(&hb, 0, &seq));
	zassert_equal(heartbeat_wait_ms(&hb, 0), 1000);
	zassert_equal(heartbeat_wait_ms(&hb, 400), 600);
	zassert_equal(heartbeat_wait_ms(&hb, 999), 1);
	zassert_equal(heartbeat_wait_ms(&hb, 1000), 0);
	zassert_equal(heartbeat_wait_ms(&hb, 5000), 0, "a late poll waits 0");
}

/* -- serial marker cadence -------------------------------------------------------------------- */

ZTEST(heartbeat, test_marker_on_every_tenth_heartbeat)
{
	unsigned int marked = 0;

	for (uint32_t seq = 0; seq < 100; seq++) {
		if (heartbeat_marker_due(seq)) {
			zassert_equal(seq % 10, 0, "marker at seq %u", seq);
			marked++;
		}
	}
	zassert_equal(marked, 10, "%u markers in 100 Heartbeats", marked);
	zassert_true(heartbeat_marker_due(0));
	zassert_false(heartbeat_marker_due(9));
	zassert_true(heartbeat_marker_due(4294967290U)); /* the wrap point keeps its cadence */
}

/* -- encoder: exact line ------------------------------------------------------------------------ */

ZTEST(heartbeat, test_encode_is_byte_exact_and_ends_with_newline)
{
	char buf[HEARTBEAT_LINE_MAX];
	const char *want = "{\"seq\":7,\"uptime_ms\":12345}\n";
	int n = heartbeat_encode(buf, sizeof(buf), 7, 12345);

	zassert_equal(n, (int)strlen(want), "length %d", n);
	zassert_mem_equal(buf, want, n + 1, "line \"%s\"", buf);
}

ZTEST(heartbeat, test_encode_zero_values)
{
	char buf[HEARTBEAT_LINE_MAX];
	int n = heartbeat_encode(buf, sizeof(buf), 0, 0);

	zassert_equal(n, (int)strlen("{\"seq\":0,\"uptime_ms\":0}\n"));
	zassert_str_equal(buf, "{\"seq\":0,\"uptime_ms\":0}\n");
}

ZTEST(heartbeat, test_encode_no_sign_overflow_at_32bit_limits)
{
	char buf[HEARTBEAT_LINE_MAX];

	zassert_true(heartbeat_encode(buf, sizeof(buf), 2147483648U, 2147483648ULL) > 0);
	zassert_str_equal(buf, "{\"seq\":2147483648,\"uptime_ms\":2147483648}\n");

	zassert_true(heartbeat_encode(buf, sizeof(buf), 4294967295U, 4294967296ULL) > 0);
	zassert_str_equal(buf, "{\"seq\":4294967295,\"uptime_ms\":4294967296}\n");
	zassert_is_null(strchr(buf, '-'), "a sign leaked into \"%s\"", buf);
}

ZTEST(heartbeat, test_encode_longest_line_fits_the_buffer_exactly)
{
	char buf[HEARTBEAT_LINE_MAX];
	const char *want = "{\"seq\":4294967295,\"uptime_ms\":18446744073709551615}\n";
	int n = heartbeat_encode(buf, sizeof(buf), 4294967295U, 18446744073709551615ULL);

	/* the expected text is a literal: 53 = its length + the NUL */
	zassert_equal(strlen(want) + 1, HEARTBEAT_LINE_MAX);
	zassert_equal(n, (int)strlen(want), "length %d", n);
	zassert_str_equal(buf, want);
}

ZTEST(heartbeat, test_encode_rejects_a_buffer_one_byte_short)
{
	char buf[HEARTBEAT_LINE_MAX];
	char small[8];

	zassert_equal(heartbeat_encode(small, sizeof(small), 1, 1), -1);
	zassert_equal(heartbeat_encode(buf, HEARTBEAT_LINE_MAX - 1, 4294967295U,
				       18446744073709551615ULL), -1);
}
