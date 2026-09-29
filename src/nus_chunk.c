/* SPDX-License-Identifier: Apache-2.0 */

#include "nus_chunk.h"

#define ATT_HEADER      3U
#define ATT_MTU_DEFAULT 23U

size_t nus_payload_for_mtu(uint16_t att_mtu)
{
	if (att_mtu < ATT_MTU_DEFAULT) {
		att_mtu = ATT_MTU_DEFAULT;
	}
	return (size_t)att_mtu - ATT_HEADER;
}

void nus_chunker_init(struct nus_chunker *c, const void *data, size_t len, uint16_t att_mtu)
{
	c->data = data;
	c->len = len;
	c->pos = 0;
	c->payload = nus_payload_for_mtu(att_mtu);
}

size_t nus_chunker_next(struct nus_chunker *c, const uint8_t **chunk)
{
	size_t left = c->len - c->pos;
	size_t n = left < c->payload ? left : c->payload;

	if (n == 0) {
		return 0;
	}
	*chunk = &c->data[c->pos];
	c->pos += n;
	return n;
}
