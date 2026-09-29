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

	for (size_t i = 0; i < count; i++) {
		uint8_t cur = levels[i] ? 1 : 0;

		low += (cur == 0);
		edges += (cur != prev);
		prev = cur;
	}

	out->samples = (uint32_t)count;
	out->low_samples = low;
	out->edges = edges;
	out->low_permille = (uint32_t)(((uint64_t)low * 1000U + count / 2) / count);

	if (elapsed_cycles != 0 && cycles_per_sec != 0) {
		/* One period contains two edges. */
		out->freq_hz = (uint32_t)(((uint64_t)edges * cycles_per_sec) /
					  ((uint64_t)elapsed_cycles * 2U));
	}
}
