/* SPDX-License-Identifier: Apache-2.0 */
#ifndef NUS_CHUNK_H
#define NUS_CHUNK_H

#include <stddef.h>
#include <stdint.h>

/*
 * Shell link output chunking (pure C, host suite tests/nus_chunk): the output is cut into
 * notifications of at most ATT MTU - 3 bytes (spec: Shell link). Chunks are cut anywhere, also
 * inside a line; the Central reassembles lines. Empty output yields no chunk.
 */

/* Data bytes one notification can carry at this ATT MTU (MTU - 3); an MTU under the default
 * 23 counts as 23, so the result is at least 20.
 */
size_t nus_payload_for_mtu(uint16_t att_mtu);

struct nus_chunker {
	const uint8_t *data;
	size_t len;
	size_t pos;
	size_t payload;
};

void nus_chunker_init(struct nus_chunker *c, const void *data, size_t len, uint16_t att_mtu);

/* The next chunk: sets *chunk and returns its length (1..payload), or 0 when the data is used up. */
size_t nus_chunker_next(struct nus_chunker *c, const uint8_t **chunk);

#endif /* NUS_CHUNK_H */
