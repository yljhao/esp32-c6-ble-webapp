/* SPDX-License-Identifier: Apache-2.0 */

#include "ble.h"

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/services/nus.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/sys/printk.h>

LOG_MODULE_REGISTER(ble, LOG_LEVEL_INF);

#define DEVICE_NAME     CONFIG_BT_DEVICE_NAME
#define DEVICE_NAME_LEN (sizeof(DEVICE_NAME) - 1)

/* The name goes in the advertising data, the 128-bit NUS UUID in the scan response
 * (both together do not fit the 31 bytes of one PDU). A Central that scans actively
 * (the Harness, Chrome) sees both.
 */
static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA(BT_DATA_NAME_COMPLETE, DEVICE_NAME, DEVICE_NAME_LEN),
};

static const struct bt_data sd[] = {
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, BT_UUID_NUS_SRV_VAL),
};

/* A failed bt_le_adv_start() after a connection object was allocated makes the stack drop that
 * object, which fires "recycled" again and so calls advertise() again: a persistent failure would
 * loop without end on the system workqueue. Give up after this many failures in a row.
 */
#define ADV_FAILURES_MAX 5

static int adv_failures;

static int advertise(void)
{
	int err = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));

	if (err) {
		adv_failures++;
		LOG_ERR("advertising failed to start (err %d, %d in a row)", err, adv_failures);
		printk("\n[BLE] advertising failed err=%d\n", err);
		return err;
	}
	adv_failures = 0;
	printk("\n[BLE] advertising name=%s\n", DEVICE_NAME);
	return 0;
}

/* Ask the Central for a 4 s supervision timeout (interval 30 to 50 ms, no latency): BlueZ's
 * default is 420 ms, which a PC adapter that scans while connected can miss. For a peripheral the
 * call only stores the request; the stack sends it after CONFIG_BT_CONN_PARAM_UPDATE_TIMEOUT
 * (5 s) and the Central may refuse it, so the log in on_params_updated() shows what took effect.
 */
static const struct bt_le_conn_param conn_params = BT_LE_CONN_PARAM_INIT(24, 40, 0, 400);

static void on_connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		/* No Connection exists; the stack recycles the object, which restarts advertising. */
		LOG_WRN("connection failed (HCI err 0x%02x)", err);
		return;
	}
	printk("\n[BLE] connected\n");

	err = bt_conn_le_param_update(conn, &conn_params);
	if (err) {
		LOG_WRN("connection parameter request rejected (err %d)", err);
	}
}

static void on_disconnected(struct bt_conn *conn, uint8_t reason)
{
	ARG_UNUSED(conn);

	printk("\n[BLE] disconnected reason=0x%02x\n", reason);
}

/* Advertising restarts here, not in on_disconnected(): with CONFIG_BT_MAX_CONN=1 the
 * connection object is still in use there and bt_le_adv_start() would fail with -ENOMEM.
 * "Recycled" fires once it is free again, also after a connection that failed to open.
 */
static void on_recycled(void)
{
	if (adv_failures >= ADV_FAILURES_MAX) {
		return;
	}
	(void)advertise();
}

static void on_params_updated(struct bt_conn *conn, uint16_t interval, uint16_t latency,
			      uint16_t timeout)
{
	ARG_UNUSED(conn);

	/* Units: interval 1.25 ms, timeout 10 ms. Diagnostics only, not a Marker. */
	LOG_INF("connection parameters: interval=%u latency=%u timeout=%u", interval, latency,
		timeout);
}

BT_CONN_CB_DEFINE(conn_cbs) = {
	.le_param_updated = on_params_updated,
	.connected = on_connected,
	.disconnected = on_disconnected,
	.recycled = on_recycled,
};

static void on_mtu_updated(struct bt_conn *conn, uint16_t tx, uint16_t rx)
{
	ARG_UNUSED(conn);

	/* The ATT MTU in force is the smaller of the two directions (equal after an exchange). */
	printk("\n[BLE] mtu=%u\n", MIN(tx, rx));
}

static struct bt_gatt_cb gatt_cbs = {
	.att_mtu_updated = on_mtu_updated,
};

int ble_start(void)
{
	int err;

	bt_gatt_cb_register(&gatt_cbs);
	err = bt_enable(NULL);
	if (err) {
		LOG_ERR("bluetooth enable failed (err %d)", err);
		printk("\n[BLE] start failed err=%d\n", err);
		return err;
	}
	return advertise();
}
