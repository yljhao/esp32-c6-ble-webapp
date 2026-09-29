/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BLE_H
#define BLE_H

/*
 * Bluetooth peripheral: enables the stack, advertises as CONFIG_BT_DEVICE_NAME with the
 * Nordic UART Service UUID, accepts one Connection, stops advertising while it exists and
 * advertises again once it has ended. Markers (spec, grepped by the Harness):
 *
 *   [BLE] advertising name=<name>     advertising started (boot, and after every Connection)
 *   [BLE] advertising failed err=<n>  bt_le_adv_start() failed (retried after a Connection ends,
 *                                     at most 5 failures in a row)
 *   [BLE] start failed err=<n>        bt_enable() failed
 *   [BLE] connected                   a Connection was established
 *   [BLE] mtu=<n>                     the ATT MTU changed (negotiated by the Central)
 *   [BLE] disconnected reason=0x<rr>  the Connection ended (HCI reason)
 */

/* Call once, after the watchdog is armed. 0, or the error of bt_enable() / the first
 * bt_le_adv_start() with the reason logged and a marker; the board then runs without Bluetooth.
 */
int ble_start(void);

#endif /* BLE_H */
