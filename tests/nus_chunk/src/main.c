/*
 * Testing call: per Testing Decisions (Shell link chunking); it is pure arithmetic whose result the Central
 * depends on (a notification above MTU - 3 bytes is refused by the stack).
 * Seam: nus_payload_for_mtu() and the nus_chunker_init() / nus_chunker_next() iterator.
 * Glue, proven on the board: src/shell_nus.c (bt_nus_send, the MTU read from the Connection).
 */
/* SPDX-License-Identifier: Apache-2.0 */

#include <string.h>
#include <zephyr/ztest.h>

#include "nus_chunk.h"

ZTEST_SUITE(nus_chunk, NULL, NULL, NULL, NULL, NULL);

#define OUT_MAX 1024

struct split {
	size_t count;
	size_t biggest;
	size_t sizes[64];
	uint8_t joined[OUT_MAX];
	size_t joined_len;
};

static void run(const uint8_t *data, size_t len, uint16_t mtu, struct split *s)
{
	struct nus_chunker c;
	const uint8_t *chunk;
	size_t n;

	memset(s, 0, sizeof(*s));
	nus_chunker_init(&c, data, len, mtu);
	while ((n = nus_chunker_next(&c, &chunk)) > 0) {
		zassert_true(s->count < ARRAY_SIZE(s->sizes), "too many chunks");
		s->sizes[s->count++] = n;
		s->biggest = MAX(s->biggest, n);
		memcpy(&s->joined[s->joined_len], chunk, n);
		s->joined_len += n;
	}
}

ZTEST(nus_chunk, test_payload_is_mtu_minus_3)
{
	zassert_equal(nus_payload_for_mtu(23), 20);
	zassert_equal(nus_payload_for_mtu(247), 244);
}

ZTEST(nus_chunk, test_an_mtu_below_the_default_is_treated_as_23)
{
	zassert_equal(nus_payload_for_mtu(0), 20);
	zassert_equal(nus_payload_for_mtu(22), 20);
}

ZTEST(nus_chunk, test_empty_output_yields_no_chunk)
{
	struct split s;

	run((const uint8_t *)"", 0, 23, &s);
	zassert_equal(s.count, 0);
	run((const uint8_t *)"", 0, 247, &s);
	zassert_equal(s.count, 0);
}

ZTEST(nus_chunk, test_short_line_is_one_chunk_at_both_mtus)
{
	static const char line[] = "LED 128\n";
	struct split s;

	run((const uint8_t *)line, strlen(line), 23, &s);
	zassert_equal(s.count, 1);
	zassert_equal(s.sizes[0], 8);
	run((const uint8_t *)line, strlen(line), 247, &s);
	zassert_equal(s.count, 1);
}

ZTEST(nus_chunk, test_mtu_23_splits_at_20_bytes)
{
	uint8_t data[45];
	struct split s;

	for (size_t i = 0; i < sizeof(data); i++) {
		data[i] = (uint8_t)('a' + i % 26);
	}
	run(data, sizeof(data), 23, &s);
	zassert_equal(s.count, 3);
	zassert_equal(s.sizes[0], 20);
	zassert_equal(s.sizes[1], 20);
	zassert_equal(s.sizes[2], 5);
	zassert_equal(s.joined_len, sizeof(data));
	zassert_mem_equal(s.joined, data, sizeof(data));
}

ZTEST(nus_chunk, test_exact_multiple_has_no_empty_trailing_chunk)
{
	uint8_t data[40];
	struct split s;

	memset(data, 'x', sizeof(data));
	run(data, sizeof(data), 23, &s);
	zassert_equal(s.count, 2);
	zassert_equal(s.sizes[0], 20);
	zassert_equal(s.sizes[1], 20);
}

ZTEST(nus_chunk, test_mtu_247_splits_at_244_bytes)
{
	uint8_t data[600];
	struct split s;

	memset(data, 'y', sizeof(data));
	run(data, sizeof(data), 247, &s);
	zassert_equal(s.count, 3);
	zassert_equal(s.sizes[0], 244);
	zassert_equal(s.sizes[1], 244);
	zassert_equal(s.sizes[2], 112);
}

ZTEST(nus_chunk, test_lines_are_cut_anywhere_and_the_stream_is_unchanged)
{
	/* Several lines, so chunk boundaries fall inside a line and across a newline. */
	static const char text[] = "LED 128\nERR out of range 0-255\n{\"seq\":1,\"uptime_ms\":1000}\nLED 0\n";
	const uint16_t mtus[] = { 23, 247, 50 };
	struct split s;

	for (size_t m = 0; m < ARRAY_SIZE(mtus); m++) {
		run((const uint8_t *)text, strlen(text), mtus[m], &s);
		zassert_true(s.biggest <= (size_t)mtus[m] - 3, "mtu %u: chunk of %zu", mtus[m], s.biggest);
		zassert_equal(s.joined_len, strlen(text));
		zassert_mem_equal(s.joined, text, strlen(text));
	}
	run((const uint8_t *)text, strlen(text), 23, &s);
	zassert_true(s.count >= 3, "mid-line splits expected at MTU 23");
}

ZTEST(nus_chunk, test_exhausted_iterator_keeps_returning_zero)
{
	struct nus_chunker c;
	const uint8_t *chunk;

	nus_chunker_init(&c, "ab", 2, 23);
	zassert_equal(nus_chunker_next(&c, &chunk), 2);
	zassert_equal(nus_chunker_next(&c, &chunk), 0);
	zassert_equal(nus_chunker_next(&c, &chunk), 0);
}
