# 04: Watchdog

Spec: `.scratch/ble-webapp/spec.md` (watchdog, Boot order). Reference watchdog module in `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2`.

**What to build:** A task watchdog with a 5 s window, armed after the Self-test and fed by the main loop only, so a hung main loop reboots the board and the next boot reports `watchdog` as its Reset reason. Port the Reset reason and watchdog modules. A debug-only build (a separate Kconfig fragment and build directory, never in the production image) adds a serial-shell command that stops the main loop from feeding, to prove the bite.

**Blocked by:** 03

**Board:** required

**Status:** ready-for-agent

- [x] Boot prints `[WDT] armed window=5000ms` after `[STAGE] selftest: done`.
  Evidence: `./verify.sh --flash` capture `build/verify/capture-20260930-042551.log`: `[STAGE] selftest: done` +3.605 s, `[WDT] armed window=5000ms` +3.626 s (`RESULT: PASS (11/11 checks)`).
- [x] No spurious bite over at least 60 s of idle running.
  Evidence: `./verify.sh --soak 60` (twice): `PASS  idle: no reset (no spurious watchdog bite)  (no reset in 64.4s after arming)`, `RESULT: PASS (4/4 checks)`.
- [x] With the debug image, the hang command leads to a reset within about 5 s and the next boot prints `[BOOT] reason=watchdog`.
  Evidence: `./verify.sh --bite`, `build/verify/bite-20260930-042842.log`: `PASS  debug image: hang command leads to a reset within ~5 s, next boot reason=watchdog  (reset 4.2s after the hang, then [BOOT] reason=watchdog)`; ROM line `rst:0x7 (TG0_WDT_HPSYS)`.
- [x] The production image is rebuilt and re-flashed afterwards and verified; the production image has no hang command.
  Evidence: the same `--bite` run rebuilt and re-flashed the production image (MD5 `f0fd36da2cd33b968e0d51ed9c45e74c`), all boot Checks PASS incl. `production build carries no hang command  (CONFIG_C6_HANG_CMD not set, no hang text in 152880 image bytes)` and `production image: hang command refused, no reset`; `RESULT: PASS (17/17 checks)`. Final default run below.
- [x] Harness Check for `[WDT] armed window=5000ms`; the watchdog bite scenario is a separate Harness mode, not part of the default run.
  Evidence: Harness Check `[WDT] armed window=5000ms after the Self-test` in the default run; bite is `--bite` (and idle `--soak`), neither in the default run; 65 Python unit tests OK, red paths in unit tests and the first `--bite` run (`RESULT: FAIL (16/17 checks)`, marker behind the shell prompt, fixed).

## Comments

- 2026-09-30 (implementer): no failure was hit three times. One single-attempt fix: the debug marker `[DBG] hang: ...` was printed without a leading newline and sat behind the shell prompt, so the Check did not match; the marker now starts with `\n`.
- Modules: Reset reason was already ported in ticket 01 (unchanged); the watchdog is ported from the reference with a 5000 ms window and the Sequencer wording replaced by main loop. Testing calls: no firmware module of this ticket is host-unit-tested (watchdog and `debug_hang.c` are glue proven on the board; the spec lists no watchdog suite). Harness Check logic (armed marker, idle soak, bite, no-hang, refused) is Python unittest in `tools/verify/test_checks.py`.
- Where the spec was silent: (1) the hang command is `debug hang` on the serial shell, compiled by `CONFIG_C6_HANG_CMD` (Kconfig), enabled only by `debug.conf` in build dir `build-debug`; it also switches the serial shell on, because production has no shell yet. (2) The main loop period is 1 s and the loop feeds after each sleep; the hang is honoured at the next period (marker printed by the main loop, then it blocks forever). (3) The idle-soak Check (>= 60 s) is Harness mode `--soak [N]`, not in the default run (only the armed marker is). (4) `--bite` always ends by rebuilding and re-flashing production and running the default Checks on it. (5) Bite limit 7 s from the hang marker (measured 4.2 s). (6) The default capture now ends at the `[WDT] armed` marker, and marker order gains it after `[LED] brightness=128` (spec Boot order: Brightness 128, then watchdog armed).
- Limit of the refused-on-production Check: production has no shell yet, so it passes trivially until a later ticket adds the console shell; the static Check (config and image) is the real proof today.
