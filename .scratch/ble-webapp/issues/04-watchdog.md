# 04: Watchdog

Spec: `.scratch/ble-webapp/spec.md` (watchdog, Boot order). Reference watchdog module in `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2`.

**What to build:** A task watchdog with a 5 s window, armed after the Self-test and fed by the main loop only, so a hung main loop reboots the board and the next boot reports `watchdog` as its Reset reason. Port the Reset reason and watchdog modules. A debug-only build (a separate Kconfig fragment and build directory, never in the production image) adds a serial-shell command that stops the main loop from feeding, to prove the bite.

**Blocked by:** 03

**Board:** required

**Status:** ready-for-agent

- [ ] Boot prints `[WDT] armed window=5000ms` after `[STAGE] selftest: done`.
- [ ] No spurious bite over at least 60 s of idle running.
- [ ] With the debug image, the hang command leads to a reset within about 5 s and the next boot prints `[BOOT] reason=watchdog`.
- [ ] The production image is rebuilt and re-flashed afterwards and verified; the production image has no hang command.
- [ ] Harness Check for `[WDT] armed window=5000ms`; the watchdog bite scenario is a separate Harness mode, not part of the default run.
