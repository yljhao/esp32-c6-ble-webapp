# Board notes

Platform knowledge that outlives a session. Two layers: the **card** below is what every session reads first and is kept current (rewrite a line when a fact changes, never stack history); the **evidence log** under it is dated and append-only, read when a card line needs its reason. `implement` reads the card before its first build, and before finishing rewrites any card line that changed and appends its evidence to the log.

A ticket's `Board:` line is a permission, not a schedule: `required` lets the implementer flash, reset, capture serial, drive the probe, or stage the PC network; `none` forbids all of that, including driving the board through the network. Either way, one actor touches the board at a time.

## Every session

One line each, always current. This is the whole file for most sessions. A card line is one sentence: the command, or the fact. It never carries a measurement, a timing, a list of checks, or a date; those go under the evidence log with a dated heading, and the card line may say "see log: <heading>". A card longer than 25 lines, or a line longer than 200 characters, is moved to the log before the session ends.

- Board: Seeed Studio XIAO ESP32-C6, Zephyr target `xiao_esp32c6/esp32c6/hpcore`, Zephyr 4.4.2 at `~/zephyrproject/zephyr`, SDK `~/zephyr-sdk-1.0.1`.
- Port: `/dev/ttyACM0` (USB-Serial/JTAG `303a:1001`), 115200.
- Flash: `west flash -d build` day to day, `./build.sh flash` (pins `--chip esp32c6`) for the Harness and acceptance; both verified here; never `--no-reset`, `--sysbuild`, MCUboot (ADR-0003).
- Reset: `.venv/bin/python tools/board/reset.py` (RTS pulse through USB-Serial/JTAG, reads the ROM banner, port stays; see log: Reset method).
- Capture: `./build.sh serial [SECONDS] [--expect REGEX]` resets, captures with timestamps, exits 1 on a missing marker; `./build.sh console` skips the reset (see log: Capture command).
- Test: `./build.sh test` = twister on `native_sim/native/64`, the esptool guard test and `test-tools`; `./build.sh test-tools` = the `tools/verify` Python unittests alone (no board, BT or serial).
- Verify: `./verify.sh [--flash]` runs the acceptance Harness (final `RESULT:` line, exit 0 only on PASS); `--soak [N]` idle run, `--bite` debug watchdog bite; red path proven (see log: Harness).
- Overlay: a `boards/` overlay added after the first configure is not picked up by `-p auto`; `rm -rf build` once (see log: Ticket 03 Self-test).
- Debug image: `debug.conf` (adds `debug hang`) builds only into `build-debug` through `./verify.sh --bite`, which restores production; never flash it by hand (see log: Ticket 04).
- Production state: not defined yet.
- Quirks: `get-security-info` now resets the app itself; console bytes printed while the port is closed are lost; 32-bit `native_sim` does not link on this PC.

## Evidence log

Dated, append-only. A card line points here for its reason.

### Board and chip

- 2026-09-30 (inherited from `esp32-c6-wifi-vpn-mqtt-exam-2`, verified there 2026-09-13): Seeed Studio XIAO ESP32-C6, SoC ESP32-C6 (RISC-V), esptool `chip_id` 13. Built-in ceramic antenna; do NOT enable `CONFIG_XIAO_ESP32C6_EXT_ANTENNA`.
- Orange user LED: GPIO15, active-low. Red LED is the charger IC, not a GPIO. No user button.
- Board DTS has no `ledc0`/`pwm-leds`; LED is `gpio-leds` (`led0`). Reference overlay enables `ledc0` with pinctrl `LEDC_CH0_GPIO15` + `input-enable`, `pwms = <&ledc0 0 PWM_HZ(20000) PWM_POLARITY_INVERTED>`, brightness 0–255. GPIO15 is also the JTAG-select strapping pin (harmless while eFuse `JTAG_SEL_ENABLE=0`, factory default).
- Zephyr 4.4.2 has `BT_ZEPHYR_NUS` (`subsys/bluetooth/services/nus`) and `samples/bluetooth/peripheral_nus`, but no Zephyr shell backend over NUS (that exists only in NCS).

### Port and baud

- `/dev/ttyACM0`, VID:PID `303a:1001` ("Espressif USB JTAG/serial debug unit"), group `plugdev`, 115200. Identify with `lsusb | grep 303a:1001`.

### Flash tool and chip pin

- 2026-09-30 (verified with this project's image, 144400 bytes): plain `west flash -d build` auto-detected `esp32c6(chip_id=13)` and `/dev/ttyACM0`, wrote at 0x0 in about 2.7 s including the ninja check, MD5 matched `0226ce294543e56ac93fabf0a60bc376`, and the board booted into the image (`[BOOT] reason=usb`). After the CMake project was renamed (`c6_ble_led`) the final image is MD5 `5af085eb6016fbcb5958e29dd9ca6990`, flashed with `./build.sh flash` and booting the same way. `./build.sh flash` (`--chip esp32c6 --port /dev/ttyACM0`, dio 80m 4MB) wrote the same image, same MD5, same boot. Each `west flash` also prints `The module for runner "rtsflash" could not be imported (No module named 'usb')`: a Zephyr runner this board does not use, harmless.
- 2026-09-30 (reported by the esptool-build session, NOT verified here): before this ticket the board ran esptool-build's tick test image (`tick N on xiao_esp32c6/esp32c6/hpcore`, flash 0xFF elsewhere). Its uncommitted working tree now also supports `erase-flash` (RDID capacity, whole-chip erase, MD5 read-back), so `west flash --erase` should work; ADR-0003 still says never `--erase` until a ticket verifies it.

- esptool-build (`~/Desktop/Project/esptool-build`) only exposes `version`, `elf2image`, `write-flash`, `get-security-info`; its default chip is esp32c3, so it refuses a write without `--chip esp32c6` (this is why `west flash` is rejected on this board). `--baud` is ignored on USB-Serial/JTAG, `erase-flash` unsupported.
- Flash offset `CONFIG_FLASH_LOAD_OFFSET=0x0` (simple boot), artifact `build/zephyr/zephyr.bin`, `write-flash --after hard-reset` resets after writing.
- 2026-09-30 (esptool-build f22af07, reported by the esptool-build session; verified there on this XIAO with a scratch image, NOT yet with this project's image): with no `--chip`, `write-flash`/`get-security-info` detect the chip from `chip_id` (13 → esp32c6) and refuse an unknown or not-yet-verified chip; with no `--port`/`ESPTOOL_PORT`, it uses the port only when exactly one `303a:1001` is present, refuses zero or several. So plain `west flash -d build` works on the C6. The line above about refusing without `--chip` is superseded by this one.
- 2026-09-30 (esptool-build f22af07): an explicit `--chip esp32c6` still refuses a board whose `chip_id` differs; auto-detect instead flashes whatever chip is attached (a C3 would be flashed as a C3). Several boards: `west flash -d build --esp-device /dev/ttyACM1` or `ESPTOOL_PORT=...`; `/dev/serial/by-id/*` names carry the USB serial number and work as `--esp-device`.
- 2026-09-30 (esptool-build f22af07): launchers `~/zephyrproject/.venv/bin/esptool` (the one west finds first on PATH) and `~/.local/bin/esptool` both import the esptool-build working tree directly, so its checkout state is what runs; no reinstall after an update.
- 2026-09-30 (esptool-build f22af07): still unsupported: `--baud` (accepted, prints a note, ignored on USB-CDC), `erase-flash` (so `west flash --erase` fails; FLASH_BEGIN erases the written region anyway), `--encrypt` / `--esp-encrypt`. `--flash-size detect` falls back to 4MB (the board passes 4MB, so not reached). ROM-only (no stub): ~140 KB in ~4 s.
- 2026-09-30 (read from Zephyr 4.4.2 `runners/esp32.py` do_run, reported by esptool-build): never `west flash --no-reset`; with reset off the runner omits `write-flash -u` and builds a broken command.
- 2026-09-30 (verified on this PC): no upstream esptool anywhere. Both the runner (`runners/esp32.py:84`, bare `esptool`) and the build (`find_program(ESPTOOL_EXECUTABLE esptool)`) resolve through PATH; the only hits are the two esptool-build launchers (Zephyr venv `bin/esptool`, `~/.local/bin/esptool`, the latter first when the venv is not active). `pip show esptool` in the Zephyr venv: not found; `import esptool` fails in the venv and system Python; nothing in `/usr/bin`, `/usr/local/bin`, `~/.espressif/tools` (only `openocd-esp32`). A later `pip install esptool` would silently win on PATH, so the build script guards it (see spec).
- 2026-09-30 (reported by the esptool-build session): the `get-security-info --after` handling and `erase-flash` that this project relies on are committed and pushed as esptool-build d7b0966; the working tree the launchers import matched it when committed.

### Reset method

- 2026-09-30 (verified in this repo, image = this project's, `udevadm monitor --kernel --udev --property` started before each action, `lsusb` device number 006 before and after): no udev or kernel event across `west flash -d build` (run twice), `./build.sh flash`, `tools/board/reset.py` and `esptool get-security-info`; `/dev/ttyACM0` never disappeared. This replaces the CONFLICT line below: on this PC the post-flash hard reset and the RTS reset do not re-enumerate USB.
- 2026-09-30 (verified): `esptool --chip esp32c6 get-security-info` (esptool-build working tree, uncommitted at the time) restarted the running app by itself: the tick program's counter restarted at `tick 1` within ~1 s of the command, and after `./build.sh identify` `[BOOT] reason=usb` followed. So `identify` no longer needs `reset.py`; the two older lines below about `--after` being ignored are superseded.

- Reference `tools/board/reset.py`: TIOCEXCL open, DTR/RTS (1,1)->(0,1)->(0,0), RTS high (EN low) 200 ms, release, read ROM banner. RTS reset does not re-enumerate USB (`/dev/ttyACM0` stays). `get-security-info` leaves the chip idle in ROM download mode, so `identify` must be followed by this reset.
- 2026-09-30 (esptool-build f22af07; SUPERSEDED by the verified entry above): `get-security-info` ignores `--after` and only closes the port, unlike upstream esptool, which honours `--after hard-reset` there too. `write-flash --after hard-reset` (what `west flash` passes) boots straight into the app.
- 2026-09-30 (resolved): the earlier CONFLICT between esptool-build's report of a re-enumeration after the post-flash reset and the reference project's observation is settled by the first entry of this section: no re-enumeration on this PC in any case tested.

### Capture command

- 2026-09-30 (this repo, this project's image): `./build.sh serial 15 --expect '\[BOOT\] reason='` reset the board and printed `[BOOT] reason=usb` about 2.07 s after the reset (the boot delay is `CONFIG_C6_BOOT_MARKER_DELAY_MS=2000`), then `console.py: OK: all expected markers seen`, exit 0; with `--expect NOPE_MARKER` the window closed with `console.py: FAIL: marker missing: NOPE_MARKER`, exit 1. Capturing without a reset ~11 s after a `west flash` showed nothing: the marker was printed while the port was closed and is lost; starting the capture right after the flash (same shell line) caught `[BOOT] reason=usb` 1.5 s later. Reset cause after a flash is `usb`, same as after `reset.py`.

- Reference `./build.sh serial [SECONDS]` = `flock /tmp/_dev_ttyACM0.lock` + `console.py --port /dev/ttyACM0 --seconds N --reset`, lines stamped `HH:MM:SS.mmm +sss.ssss`; `./build.sh console [SECONDS] [--send TEXT]` captures without reset and can type a shell command. Captures sync on the ROM banner `ESP-ROM:`.
- Every boot prints `SHA-256 comparison failed: ... Attempting to boot anyway...` from the ROM: expected with simple boot, harmless.

### Test command

- Reference: `./build.sh test` = `west twister --testsuite-root tests --platform native_sim/native/64 ...` in the Zephyr venv. 32-bit `native_sim` does not link here (no gcc multilib).

### Known quirks

- 2026-09-13 (reference): `usb_serial` console drops bytes while no host reads the port; up to ~1.5 KB of stale bytes from the previous session can arrive at the next open. Reference firmware delays the first Marker 2000 ms after boot.
- 2026-09-13 (reference): with `CONFIG_LOG=y`, `CONFIG_LOG_PRINTK=y` makes printk Markers arrive clumped up to ~1 s late; set `CONFIG_LOG_PRINTK=n` for synchronous Markers.
- 2026-09-13 (reference): the default `LOG_PROCESS_THREAD_STACK_SIZE=768` overflowed; raised to 2048.

### Configuration raised and why

- 2026-09-30 (ticket 03): raised from default in `prj.conf`: `CONFIG_PWM=y` and `CONFIG_GPIO=y` (User LED and pad readback), `CONFIG_LOG=y` with `CONFIG_LOG_PRINTK=n` (diagnostics through the log, Markers stay synchronous). No stack raised: `main` peaked at 536 of 2048 bytes (26 %) after the Self-test and 10 s of idle loop (scratch build with `CONFIG_THREAD_ANALYZER_AUTO`, interval minimum 5 s; not in the image).

### Ticket 05 Central logic

- 2026-09-30 (ticket 05, `Board: none`, nothing touched the board or the PC's Bluetooth adapter): `bleak` 3.0.2 (with `dbus-fast` 5.0.22) installed into the project `.venv` only through `tools/requirements.txt` (`bleak>=0.22`); the Zephyr venv still has no `bleak`. Python 3.14.4 in the `.venv`.
- Host test command for the Harness Central logic: `./build.sh test-tools` (= `.venv/bin/python -m unittest discover -s tools/verify -v`), also the last step of `./build.sh test`. 132 tests pass in about 0.03 s: `test_central_logic.py` (line reassembly across split notifications, line classification, reply and Heartbeat parsing, Heartbeat continuity and period, board match by name and NUS UUID, write chunking) beside the older `test_checks.py`. A test proves `central_logic` imports neither `bleak` nor `serial`; `central.py` (the bleak wrapper, glue) imports bleak only inside its functions, so no test can scan or connect.
- 2026-09-30 red path: changing one expected line in `test_central_logic.py` (`["LED 128"]` to `["LED 129"]`) made `./build.sh test-tools` print `AssertionError: Lists differ` and `FAILED (failures=1)`, exit 1; restored, exit 0. Gotcha: editing a test file twice within one second with the same size leaves a stale `__pycache__/*.pyc` (same mtime and size), so the restored file still failed; `rm -rf tools/verify/__pycache__` fixed it.
- `central.py` was smoke-run once against a hand-written fake `BleakClient` (throwaway script, not committed): a 45-byte command went out as 20 + 20 + 5 byte writes at MTU 23, split notifications reassembled into the `LED 128` reply, disconnect set the event. It has not touched real Bluetooth; the first real use is a later ticket with `Board: required`.

### Production state to restore after a test

<not defined yet>

### Host browser and Bluetooth

- 2026-09-30 (verified on this PC): Google Chrome 154.0.8037.92 (.deb, `/usr/bin/google-chrome`), BlueZ 5.85, controller `hci0` `<hci0-mac-redacted>` powered, not rfkill-blocked; session is Wayland (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`).
- 2026-09-30 (verified, headless probe served from `http://localhost`): without `--enable-experimental-web-platform-features` Chrome reports `'bluetooth' in navigator` = false; with the flag `navigator.bluetooth.getAvailability()` = true. `localhost` counts as a secure context.

### Harness

- 2026-09-30 (ticket 02, this project's image, MD5 5af085eb6016fbcb5958e29dd9ca6990): `./verify.sh <&-` (stdin closed) ran build, guard, identify (`chip_id=13`), reset + capture, `[BOOT] reason=usb at +2.062s`: `RESULT: PASS (4/4 checks)`, exit 0, 4 s. `./verify.sh --flash` added `build.sh flash` (`MD5 相符: 5af085eb...`) before the capture: `RESULT: PASS (5/5 checks)`, exit 0, 7 s. The capture log is kept at `build/verify/capture-<stamp>.log`.
- 2026-09-30 red paths, all exit 1: `./verify.sh --seconds 1` (window ends before the 2 s boot delay, board run) gave `FAIL [BOOT] reason=<cause> present (no [BOOT] reason= marker in 26 captured line(s))` and `RESULT: FAIL (3/4 checks)`; `./verify.sh --replay <log without the [BOOT] line>` gave the same FAIL and `RESULT: FAIL (0/1 checks)`; the lock held by another `flock` gave `harness: board busy` and `RESULT: FAIL (0/0 checks)`; `PYTHONPATH=<dir with esptool.py>` made the build and the guard Check FAIL (`RESULT: FAIL (0/2 checks)`) before any board access.
- 2026-09-30: `--replay LOG` runs only the capture Checks over a saved log (lines before a `stale line(s)` note are dropped, as the live capture drops them): no board, no lock, no build. A capture window shorter than the boot marker delay is the cheapest on-board red path.

### Ticket 03 Self-test

- 2026-09-30 boot timeline (this project's image, `./build.sh serial`, times from the reset): ROM lines at +0.2 s, `[BOOT] reason=usb` +2.06 s (the 2 s marker delay), `[STAGE] selftest: start` +2.06 s, readbacks `brightness=0 duty=0.0% freq=0` +2.06 s, `brightness=128 duty=50.1% freq=19998` +2.45 s, `brightness=255 duty=100.0% freq=0` +2.84 s, `[STAGE] selftest: done` +3.61 s, `[LED] brightness=128 duty=50.1..50.2% freq=19998` +3.62 s. The sweep takes about 1.55 s; the boot ends about 1.6 s after the first marker.
- 2026-09-30: Duty readback of the User LED (active-low pad): Brightness 0 reads 0.0 % low, 255 reads 100.0 % low, both with no edges; 128 reads 50.1 to 50.2 % low. Readbacks are taken on the way up only (0, 128, 255); the way down has none. With the thread analyzer running the 128 frequency read 19988.
- 2026-09-30 red path for the Self-test: scratch build (`C6_BUILD_DIR=<scratch> C6_EXTRA_DTC_OVERLAY=<overlay setting PWM_POLARITY_NORMAL on user_led_pwm> ./verify.sh --flash`) printed `[LED] brightness=0 duty=100.0% freq=0` then `[STAGE] selftest: fail step=1`, and the boot continued to `[LED] brightness=128 duty=49.9% freq=19998` at +2.08 s; the Harness gave `RESULT: FAIL (7/9 checks)`. The production image was then rebuilt, re-flashed and `./verify.sh` gave `RESULT: PASS (9/9 checks)`.
- 2026-09-30: the reference project's overlay works unchanged here (LEDC channel 0 / timer 0 on GPIO15, 20 kHz, inverted); the `led0` alias of the Seeed board dts supplies the pad and its active-low flag. A `boards/xiao_esp32c6_esp32c6_hpcore.overlay` created after the first `west build` was ignored (the build failed on the missing `user_led_pwm` alias) until the build directory was removed.
- 2026-09-30 (ticket 03): the capture now ends at the boot's `[LED] brightness=128` after the Self-test (was `[BOOT]`), and the Checks are Self-test done, Self-test readbacks at 0/128/255, boot `[LED] brightness=128` in tolerance (duty 49 to 51 % low, freq 19000 to 21000), marker order; the run is 9 checks, about 9 s with `--flash`.

### Ticket 04 Watchdog

- 2026-09-30 (this project's image, `./verify.sh --flash`): the boot prints `[LED] brightness=128` and `[WDT] armed window=5000ms` in the same millisecond, about 3.6 s after the reset (the Self-test sweep is over by then, so it never counts against the window); the Harness capture now ends at the armed marker. Image 152880 bytes, MD5 `f0fd36da2cd33b968e0d51ed9c45e74c`.
- 2026-09-30 idle soak (`./verify.sh --soak 60`, twice): no ROM banner and no second `[BOOT]` in 64.4 s after arming, `RESULT: PASS (4/4 checks)`.
- 2026-09-30 bite (debug image, 177536 bytes, `build-debug`, MD5 `ccbec5c343a37e367ca2bc0159ed5571`): `debug hang` typed on the serial shell; the main loop printed `[DBG] hang: main loop stops feeding` about 0.96 s later (its next period), the ROM banner `rst:0x7 (TG0_WDT_HPSYS)` followed 4.2 s after that marker (5.2 s after the command), the next boot printed `[BOOT] reason=watchdog`. The hardware fallback bites; the reference callback's software `sys_reboot` fallback was not needed (the reason reads `watchdog`, not `software`).
- 2026-09-30: with the serial shell on, printk markers can follow the shell prompt on the same line (`uart:~$ [DBG] ...`, prompt with ANSI colour codes); the debug marker starts with a newline for that reason, as `[BOOT]` does.
- 2026-09-30 raised in `prj.conf` (ticket 04): `CONFIG_WATCHDOG=y`, `CONFIG_TASK_WDT=y`, `CONFIG_TASK_WDT_HW_FALLBACK=y` (hardware watchdog bites if the task watchdog's own timer stalls), `CONFIG_TASK_WDT_CHANNELS=2` (Kconfig range minimum, one channel used), `CONFIG_REBOOT=y` (bounded `sys_reboot` fallback in the expiry callback).
- 2026-09-30: production has no shell yet, so typing `debug hang` to the production image reaches no console. The Harness proves the absence statically (`CONFIG_C6_HANG_CMD` unset in `.config`, no hang text in the image) and also types the command and sees no marker and no reset; that second check only becomes meaningful once a later ticket adds the console shell to `prj.conf`.
- 2026-09-30 red path on the board: the first `./verify.sh --bite` run went `RESULT: FAIL (16/17 checks)` because the hang marker sat behind the shell prompt on its line (fixed as above); the same run restored production and its Checks passed. Unit tests cover the other red cases (late or early reset, wrong reason, no hang marker, idle reset).
- 2026-09-30 (read from Zephyr 4.4.2 `subsys/task_wdt/task_wdt.c`, embedded-review): with `CONFIG_TASK_WDT_HW_FALLBACK` the hardware watchdog window is `TASK_WDT_MIN_TIMEOUT` (100 ms) + 20 ms and the task watchdog's timer feeds it every 100 ms, so an interrupts-off stretch or timer stall over about 120 ms resets the board regardless of the 5 s window; recheck when Bluetooth and flash writes arrive. If a `--bite` restore step fails, the board stays on the debug image (shell and `debug hang`); rerun `./verify.sh --flash` to put the production image back.
