/*
 * Testing call: per Testing Decisions (Duty readback arithmetic: ported suite from the reference project).
 * Seam: duty_readback_compute() and struct duty_readback (pure arithmetic, the Duty readback marker's numbers).
 * Glue, proven on the board: user_led.c (pad sampling), selftest.c, brightness.c.
 */
/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Host unit suite for the Duty readback arithmetic (src/duty_readback.c):
 * a sample array plus an elapsed cycle count give the low-time fraction and
 * the edge frequency. Units are abstract: elapsed_cycles / cycles_per_sec
 * is the window in seconds. The board samples ~1350 levels in a 2 ms
 * window (~34 per 20 kHz period, board-notes); the synthetic waveforms here
 * use round numbers instead.
 */

#include <zephyr/ztest.h>

#include "duty_readback.h"

#define CYCLES_PER_SEC 1000000U /* 1 cycle = 1 us in this suite */

ZTEST_SUITE(duty_readback, NULL, NULL, NULL, NULL, NULL);

ZTEST(duty_readback, test_all_low_is_100_percent_low_no_edges)
{
	uint8_t levels[100] = {0};
	struct duty_readback r;

	duty_readback_compute(levels, sizeof(levels), 2000, CYCLES_PER_SEC, &r);
	zassert_equal(r.samples, 100, "samples %u", r.samples);
	zassert_equal(r.low_samples, 100, "low %u", r.low_samples);
	zassert_equal(r.low_permille, 1000, "permille %u", r.low_permille);
	zassert_equal(r.edges, 0, "edges %u", r.edges);
	zassert_equal(r.freq_hz, 0, "freq %u", r.freq_hz);
}

ZTEST(duty_readback, test_all_high_is_0_percent_low_no_edges)
{
	uint8_t levels[100];
	struct duty_readback r;

	memset(levels, 1, sizeof(levels));
	duty_readback_compute(levels, sizeof(levels), 2000, CYCLES_PER_SEC, &r);
	zassert_equal(r.low_samples, 0, "low %u", r.low_samples);
	zassert_equal(r.low_permille, 0, "permille %u", r.low_permille);
	zassert_equal(r.edges, 0, "edges %u", r.edges);
	zassert_equal(r.freq_hz, 0, "freq %u", r.freq_hz);
}

ZTEST(duty_readback, test_any_nonzero_level_counts_as_high)
{
	uint8_t levels[4] = {0, 1, 0xff, 0x80};
	struct duty_readback r;

	duty_readback_compute(levels, sizeof(levels), 4, CYCLES_PER_SEC, &r);
	zassert_equal(r.low_samples, 1, "only the 0 is low");
	zassert_equal(r.low_permille, 250, "permille %u", r.low_permille);
	zassert_equal(r.edges, 1, "0->1 is the only edge; 1->0xff->0x80 are not");
}

ZTEST(duty_readback, test_single_edge)
{
	/* 30 low then 70 high over 1000 us: one edge, half a period. */
	uint8_t levels[100];
	struct duty_readback r;

	memset(levels, 0, 30);
	memset(levels + 30, 1, 70);
	duty_readback_compute(levels, sizeof(levels), 1000, CYCLES_PER_SEC, &r);
	zassert_equal(r.low_samples, 30, "low %u", r.low_samples);
	zassert_equal(r.low_permille, 300, "permille %u", r.low_permille);
	zassert_equal(r.edges, 1, "edges %u", r.edges);
	/* 1 edge / 2 per period / 1 ms = 500 Hz. */
	zassert_equal(r.freq_hz, 500, "freq %u", r.freq_hz);
}

ZTEST(duty_readback, test_40_period_waveform_gives_duty_and_frequency)
{
	/*
	 * 20 kHz for 40 periods = 2000 us, 40 samples per period, 10 low + 30
	 * high per period (an active-low LED at brightness ~64, 25 % low).
	 * The capture starts mid-high so all 80 edges fall inside the window.
	 */
	enum { PERIOD = 40, LOW = 10, PERIODS = 40, OFFSET = 25 };
	static uint8_t levels[PERIOD * PERIODS];
	struct duty_readback r;

	for (size_t i = 0; i < sizeof(levels); i++) {
		levels[i] = ((i + OFFSET) % PERIOD) < LOW ? 0 : 1;
	}
	duty_readback_compute(levels, sizeof(levels), 2000, CYCLES_PER_SEC, &r);
	zassert_equal(r.samples, 1600, "samples %u", r.samples);
	zassert_equal(r.low_samples, LOW * PERIODS, "low %u", r.low_samples);
	zassert_equal(r.low_permille, 250, "permille %u", r.low_permille);
	zassert_equal(r.edges, 2 * PERIODS, "edges %u", r.edges);
	zassert_equal(r.freq_hz, 20000, "freq %u", r.freq_hz);
}

ZTEST(duty_readback, test_40_period_waveform_at_brightness_128)
{
	/* 34 samples per period as on the board, 17 low: the Self-test's 50 % point. */
	enum { PERIOD = 34, LOW = 17, PERIODS = 40, OFFSET = 8 };
	static uint8_t levels[PERIOD * PERIODS];
	struct duty_readback r;

	for (size_t i = 0; i < sizeof(levels); i++) {
		levels[i] = ((i + OFFSET) % PERIOD) < LOW ? 0 : 1;
	}
	/* 40 periods at 20 kHz on a 160 MHz cycle counter: 320000 cycles. */
	duty_readback_compute(levels, sizeof(levels), 320000, 160000000, &r);
	zassert_equal(r.low_permille, 500, "permille %u", r.low_permille);
	zassert_equal(r.edges, 80, "edges %u", r.edges);
	zassert_equal(r.freq_hz, 20000, "freq %u", r.freq_hz);
}

ZTEST(duty_readback, test_permille_rounds_to_nearest)
{
	uint8_t one_of_three[3] = {0, 1, 1};
	uint8_t two_of_three[3] = {0, 0, 1};
	struct duty_readback r;

	duty_readback_compute(one_of_three, 3, 3, CYCLES_PER_SEC, &r);
	zassert_equal(r.low_permille, 333, "1/3 -> %u", r.low_permille);
	duty_readback_compute(two_of_three, 3, 3, CYCLES_PER_SEC, &r);
	zassert_equal(r.low_permille, 667, "2/3 -> %u", r.low_permille);
}

ZTEST(duty_readback, test_zero_inputs_give_zero_result_not_a_division)
{
	uint8_t levels[10] = {0, 1, 0, 1, 0, 1, 0, 1, 0, 1};
	struct duty_readback r;

	/* No time: fraction still computed, frequency 0. */
	duty_readback_compute(levels, sizeof(levels), 0, CYCLES_PER_SEC, &r);
	zassert_equal(r.low_permille, 500, "permille %u", r.low_permille);
	zassert_equal(r.edges, 9, "edges %u", r.edges);
	zassert_equal(r.freq_hz, 0, "freq %u", r.freq_hz);

	duty_readback_compute(levels, sizeof(levels), 100, 0, &r);
	zassert_equal(r.freq_hz, 0, "freq %u with no clock", r.freq_hz);

	/* No samples: everything zero. */
	memset(&r, 0xaa, sizeof(r));
	duty_readback_compute(levels, 0, 100, CYCLES_PER_SEC, &r);
	zassert_equal(r.samples + r.low_samples + r.edges + r.low_permille + r.freq_hz, 0,
		      "zeroed");

	memset(&r, 0xaa, sizeof(r));
	duty_readback_compute(NULL, 10, 100, CYCLES_PER_SEC, &r);
	zassert_equal(r.samples + r.low_samples + r.edges + r.low_permille + r.freq_hz, 0,
		      "zeroed for NULL");
}

ZTEST(duty_readback, test_large_counts_do_not_overflow)
{
	/*
	 * 100 000 samples toggling every sample over 0.1 s of a 160 MHz cycle
	 * counter: edges * cycles_per_sec = 99999 * 160e6 needs 64 bits.
	 */
	static uint8_t levels[100000];
	struct duty_readback r;

	for (size_t i = 0; i < sizeof(levels); i++) {
		levels[i] = i & 1;
	}
	duty_readback_compute(levels, sizeof(levels), 16000000, 160000000, &r);
	zassert_equal(r.low_permille, 500, "permille %u", r.low_permille);
	zassert_equal(r.edges, 99999, "edges %u", r.edges);
	/* 99999 / 2 / 0.1 s = 499995 Hz. */
	zassert_equal(r.freq_hz, 499995, "freq %u", r.freq_hz);
}
