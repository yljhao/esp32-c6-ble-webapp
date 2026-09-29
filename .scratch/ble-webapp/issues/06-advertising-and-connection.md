# 06: Advertising and one Connection

Spec: `.scratch/ble-webapp/spec.md` (Bluetooth, Serial markers). Glossary: Connection, Central.

**What to build:** After the watchdog is armed the board enables Bluetooth and advertises as `XIAO-C6-LED` with the NUS service UUID; it accepts one Connection, stops advertising while it exists, reports the negotiated MTU, and advertises again when the Connection ends. ATT MTU raised to 247. The Harness proves each step as a Central.

**Blocked by:** 04, 05

**Board:** required

**Status:** ready-for-agent

- [ ] Boot prints `[BLE] advertising name=XIAO-C6-LED` after `[WDT] armed`.
- [ ] The Harness finds the board by name and NUS UUID, connects; the board prints `[BLE] connected` and `[BLE] mtu=<n>`; a second scan while connected does not see the board.
- [ ] The Harness disconnects; the board prints `[BLE] disconnected reason=<r>` and `[BLE] advertising ...` again; the Harness reconnects.
- [ ] Heap and thread stack headroom measured (thread analyzer in a scenario build) with Bluetooth running; any Kconfig raised is recorded in board-notes with the measurement.
- [ ] Harness Checks for all of the above; red path shown for at least one.
