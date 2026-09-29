# XIAO ESP32-C6 BLE Web App

A single board that advertises over BLE, accepts one Web App connection at a time, takes Brightness commands for its User LED through a Shell link, and streams Heartbeats back to the page.

## Language

### Board side

**User LED**:
The orange LED on the XIAO ESP32-C6 whose level the Web App controls; the red charger LED is not it.
_Avoid_: LED0, status LED

**Brightness**:
The User LED level as a number 0–255 on the board; the Web App shows it as 0–100 %. It survives a disconnect but not a reboot, which restores 128.
_Avoid_: duty, PWM value, intensity

**Duty readback**:
The board's own measurement of the User LED pad after a Brightness is applied, reported on the serial console, so a Brightness can be checked without a human eye.
_Avoid_: self-check, LED test

**Self-test**:
The 0→255→0 sweep of the User LED at boot with a Duty readback at 0, 128 and 255; a failure is reported, not retried, and the boot continues at Brightness 128.
_Avoid_: POST, LED check

**Heartbeat**:
A JSON line the board sends about once a second over the Shell link while a Central listens, carrying a per-boot sequence number and its uptime; a gap in the numbers marks a disconnect, a smaller number marks a reboot.
_Avoid_: ping, keepalive, tick

### Link

**Shell link**:
The Zephyr shell carried over the Nordic UART Service, through which the Web App types commands and receives their replies and Heartbeats as text lines.
_Avoid_: NUS console, BLE UART, serial-over-BLE

**Connection**:
The one BLE connection between the board and a Central; while it exists the board does not advertise, and when it ends the board advertises again.
_Avoid_: session, pairing, link-up

**Central**:
Whatever opens the Connection: the Web App in a browser, or the Harness.
_Avoid_: client, host, master

### Host side

**Web App**:
The static page served from GitHub Pages that finds the board by name, opens the Connection, sets Brightness with a slider and shows Heartbeats.
_Avoid_: webapp, UI, frontend, dashboard

**Harness**:
The host-side acceptance runner that acts as a Central from the PC and checks the board's Brightness, Duty readback and Heartbeat behaviour unattended.
_Avoid_: test script, bleak script
