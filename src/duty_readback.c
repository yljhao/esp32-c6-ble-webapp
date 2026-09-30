/* SPDX-License-Identifier: Apache-2.0 */

#include "duty_readback.h"

#include <string.h>

void duty_readback_compute(const uint8_t *levels, size_t count,
			   uint32_t elapsed_cycles, uint32_t cycles_per_sec,
			   struct duty_readback *out)
{
	memset(out, 0, sizeof(*out));

	if (levels == NULL || count == 0) {
		return;
	}

	uint32_t low = 0;
	uint32_t edges = 0;
	uint8_t prev = levels[0] ? 1 : 0;
	/* Whole periods: from the first edge to the last edge into the same level (first_edge ..
	 * last_edge, at least one period apart). low_in_span counts the low samples between them.
	 */
	uint8_t span_level = 0;
	size_t first_edge = 0;
	size_t last_edge = 0;
	uint32_t same_edges = 0;
	uint32_t low_before_first = 0;
	uint32_t low_before_last = 0;

	for (size_t i = 0; i < count; i++) {
		uint8_t cur = levels[i] ? 1 : 0;

		if (cur != prev) {
			if (edges == 0) {
				span_level = cur;
			}
			if (cur == span_level) {
				if (same_edges == 0) {
					first_edge = i;
					low_before_first = low;
				}
				last_edge = i;
				low_before_last = low;
				same_edges++;
			}
		}
		low += (cur == 0);
		edges += (cur != prev);
		prev = cur;
	}

	out->samples = (uint32_t)count;
	out->low_samples = low;
	out->edges = edges;
	out->low_permille = (uint32_t)(((uint64_t)low * 1000U + count / 2) / count);
	if (same_edges >= 2) {
		/* The window holds a fractional number of periods; the partial ones at both ends would
		 * skew a plain count by up to one period in the number of periods captured.
		 */
		uint32_t span = (uint32_t)(last_edge - first_edge);
		uint32_t span_low = low_before_last - low_before_first;

		out->low_permille = (uint32_t)(((uint64_t)span_low * 1000U + span / 2) / span);
	}

	if (elapsed_cycles != 0 && cycles_per_sec != 0) {
		/* One period contains two edges. */
		out->freq_hz = (uint32_t)(((uint64_t)edges * cycles_per_sec) /
					  ((uint64_t)elapsed_cycles * 2U));
	}
}
