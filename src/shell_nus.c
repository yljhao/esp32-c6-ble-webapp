/* SPDX-License-Identifier: Apache-2.0 */

#include "shell_nus.h"

#include "nus_chunk.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/services/nus.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/shell/shell.h>
#include <zephyr/sys/ring_buffer.h>

LOG_MODULE_REGISTER(shell_nus, LOG_LEVEL_INF);

/* Complete lines waiting for the shell thread. A command is short ("led set 255\n" is 12 bytes),
 * the shell's own command buffer is CONFIG_SHELL_CMD_BUFF_SIZE (256).
 */
#define RX_RING_SIZE 256
/* Longest line accepted (with its "\n"); longer lines are dropped whole. */
#define RX_LINE_MAX 128
/* Output collected until an end of line; a longer run is sent in pieces. */
#define TX_BUF_SIZE 256

static const struct shell_transport_api transport_api;
static struct shell_transport transport = { .api = &transport_api };

/* Prompt "" and plain "\n" line ends (SHELL_FLAG_CRLF_DEFAULT): nothing but the reply text. */
SHELL_DEFINE(shell_nus, "", &transport, 0, 0, SHELL_FLAG_CRLF_DEFAULT);

static shell_transport_handler_t evt_handler;
static void *evt_context;

/* -- Central to board -------------------------------------------------------------------- */

RING_BUF_DECLARE(rx_ring, RX_RING_SIZE);
static uint8_t rx_line[RX_LINE_MAX];
static size_t rx_line_len;
static bool rx_line_over; /* inside a line that was too long: drop up to its "\n" */
static uint32_t rx_dropped_lines;
static struct k_spinlock rx_lock;

static void rx_line_reset(void)
{
	k_spinlock_key_t key = k_spin_lock(&rx_lock);

	rx_line_len = 0;
	rx_line_over = false;
	k_spin_unlock(&rx_lock, key);
}

/* Runs in the Bluetooth thread: copy only, the shell thread does the work. */
static void on_received(struct bt_conn *conn, const void *data, uint16_t len, void *ctx)
{
	const uint8_t *in = data;
	bool complete = false;
	uint32_t dropped_before;
	uint32_t dropped_now;
	k_spinlock_key_t key;

	ARG_UNUSED(conn);
	ARG_UNUSED(ctx);

	key = k_spin_lock(&rx_lock);
	dropped_before = rx_dropped_lines;
	for (uint16_t i = 0; i < len; i++) {
		uint8_t b = in[i];

		if (b == '\n') {
			if (rx_line_over) {
				rx_line_over = false;
			} else {
				rx_line[rx_line_len++] = b;
				if (ring_buf_space_get(&rx_ring) >= rx_line_len) {
					ring_buf_put(&rx_ring, rx_line, rx_line_len);
					complete = true;
				} else {
					rx_dropped_lines++;
				}
			}
			rx_line_len = 0;
		} else if (rx_line_over) {
			continue;
		} else if (rx_line_len < sizeof(rx_line) - 1) {
			rx_line[rx_line_len++] = b;
		} else {
			rx_line_over = true;
			rx_line_len = 0;
			rx_dropped_lines++;
		}
	}
	dropped_now = rx_dropped_lines;
	k_spin_unlock(&rx_lock, key);

	/* The Central gets no reply for a dropped line (the Bluetooth thread must not print to the
	 * link); the console shows it, so the Harness and a developer can see it.
	 */
	if (dropped_now != dropped_before) {
		LOG_WRN("line from the Central dropped (too long or queue full), %u so far", dropped_now);
	}

	if (complete && evt_handler != NULL) {
		evt_handler(SHELL_TRANSPORT_EVT_RX_RDY, evt_context);
	}
}

/* A half-typed line must not be finished by the next Central's first bytes. Complete lines
 * already queued stay and run: the Central did send them.
 */
static void on_conn_change(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(conn);
	ARG_UNUSED(reason);
	rx_line_reset();
}

static void on_connected(struct bt_conn *conn, uint8_t err)
{
	on_conn_change(conn, err);
}

BT_CONN_CB_DEFINE(shell_nus_conn_cbs) = {
	.connected = on_connected,
	.disconnected = on_conn_change,
};

static struct bt_nus_cb nus_cb = {
	.received = on_received,
};

/* -- Board to Central -------------------------------------------------------------------- */

static K_MUTEX_DEFINE(tx_lock);
static uint8_t tx_buf[TX_BUF_SIZE];
static size_t tx_len;

static void pick_connected(struct bt_conn *conn, void *user_data)
{
	struct bt_conn **found = user_data;
	struct bt_conn_info info;

	if (*found == NULL && bt_conn_get_info(conn, &info) == 0 &&
	    info.state == BT_CONN_STATE_CONNECTED) {
		*found = bt_conn_ref(conn);
	}
}

/* Send what is collected; called with tx_lock held. Dropped when no Central is connected and
 * subscribed. bt_nus_send() waits without bound for an ATT buffer (att.c, any thread other than
 * the system work queue) while the link is stalled, until the link drops. The shell thread may
 * wait like that; a thread that must not (the main loop feeds the watchdog) must never print to
 * this shell instance from its own context: hand the text to the shell thread instead.
 */
static void tx_flush(void)
{
	struct bt_conn *conn = NULL;
	struct nus_chunker chunker;
	const uint8_t *chunk;
	size_t n;

	if (tx_len == 0) {
		return;
	}
	bt_conn_foreach(BT_CONN_TYPE_LE, pick_connected, &conn);
	if (conn != NULL) {
		nus_chunker_init(&chunker, tx_buf, tx_len, bt_gatt_get_mtu(conn));
		while ((n = nus_chunker_next(&chunker, &chunk)) > 0) {
			int err = bt_nus_send(conn, chunk, (uint16_t)n);

			if (err) {
				/* -EINVAL: the Central has not subscribed (expected, silent); anything
				 * else loses the rest of this output.
				 */
				if (err != -EINVAL && err != -ENOTCONN) {
					LOG_WRN("notification failed (err %d), output dropped", err);
				}
				break;
			}
		}
		bt_conn_unref(conn);
	}
	tx_len = 0;
}

/* -- shell transport --------------------------------------------------------------------- */

static int transport_init(const struct shell_transport *t, const void *config,
			  shell_transport_handler_t handler, void *context)
{
	ARG_UNUSED(t);
	ARG_UNUSED(config);

	evt_handler = handler;
	evt_context = context;
	return bt_nus_cb_register(&nus_cb, NULL);
}

static int transport_uninit(const struct shell_transport *t)
{
	ARG_UNUSED(t);
	return -ENOTSUP;
}

static int transport_enable(const struct shell_transport *t, bool blocking_tx)
{
	ARG_UNUSED(t);
	ARG_UNUSED(blocking_tx);
	return 0;
}

static int transport_write(const struct shell_transport *t, const void *data, size_t length,
			   size_t *cnt)
{
	const uint8_t *in = data;
	size_t left = length;

	ARG_UNUSED(t);

	/* Everything is accepted at once (sent or dropped), so the shell never waits for TX done. */
	k_mutex_lock(&tx_lock, K_FOREVER);
	while (left > 0) {
		size_t n = MIN(left, sizeof(tx_buf) - tx_len);

		memcpy(&tx_buf[tx_len], in, n);
		tx_len += n;
		in += n;
		left -= n;
		if (tx_len == sizeof(tx_buf)) {
			tx_flush();
		}
	}
	if (length > 0 && in[-1] == '\n') {
		tx_flush();
	}
	k_mutex_unlock(&tx_lock);

	*cnt = length;
	return 0;
}

static int transport_read(const struct shell_transport *t, void *data, size_t length, size_t *cnt)
{
	ARG_UNUSED(t);

	*cnt = ring_buf_get(&rx_ring, data, length);
	return 0;
}

/* Runs at the end of every pass of the shell thread: send a partial line left in the buffer. */
static void transport_update(const struct shell_transport *t)
{
	ARG_UNUSED(t);

	k_mutex_lock(&tx_lock, K_FOREVER);
	tx_flush();
	k_mutex_unlock(&tx_lock);
}

static const struct shell_transport_api transport_api = {
	.init = transport_init,
	.uninit = transport_uninit,
	.enable = transport_enable,
	.write = transport_write,
	.read = transport_read,
	.update = transport_update,
};

int shell_nus_start(void)
{
	static const struct shell_backend_config_flags flags = {
		.insert_mode = 0,
		.echo = 0,
		.obscure = 0,
		.mode_delete = 1,
		.use_colors = 0,
		.use_vt100 = 0,
	};
	int err = shell_init(&shell_nus, NULL, flags, false, 0);

	if (err) {
		LOG_ERR("shell link failed to start (err %d)", err);
	}
	return err;
}
