/* SPDX-License-Identifier: Apache-2.0 */
/*
 * Duty readback arithmetic: pure C, no Zephyr dependency, so it runs in a
 * host unit test (native_sim, tests/duty_readback) unchanged.
 *
 * Input: a level-per-sample array captured at an approximately uniform rate
 * over a known elapsed time. Output: the fraction of samples that were low
 * and the edge frequency, i.e. how often the level toggled per second.
 */

#ifndef DUTY_READBACK_H
#define DUTY_READBACK_H

#include <stdint.h>
#include <stddef.h>

struct duty_readback {
	uint32_t samples;      /* samples evaluated */
	uint32_t low_samples;  /* samples whose level was 0 */
	uint32_t edges;        /* level changes between consecutive samples */
	uint32_t low_permille; /* low_samples / samples, in 0.1 % steps */
	uint32_t freq_hz;      /* edges / 2 / elapsed; 0 when no edge or no time */
};

/*
 * levels[i] is 0 (low) or non-zero (high). elapsed_cycles is the time the
 * count samples took, in units of cycles_per_sec. Any zero input yields a
 * zeroed result rather than a division error.
 */
void duty_readback_compute(const uint8_t *levels, size_t count,
			   uint32_t elapsed_cycles, uint32_t cycles_per_sec,
			   struct duty_readback *out);

#endif /* DUTY_READBACK_H */
