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
- Test: `./build.sh test` = twister over `tests/` on `native_sim/native/64`, the esptool guard's red-path test and the Harness unittest (`tools/verify`); exit non-zero on any failure.
- Verify: `./verify.sh [--flash]` runs the acceptance Harness (final `RESULT:` line, exit 0 only on PASS); its red path is proven (see log: Harness).
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

<none yet in this repo>

### Production state to restore after a test

<not defined yet>

### Host browser and Bluetooth

- 2026-09-30 (verified on this PC): Google Chrome 154.0.8037.92 (.deb, `/usr/bin/google-chrome`), BlueZ 5.85, controller `hci0` `<hci0-mac-redacted>` powered, not rfkill-blocked; session is Wayland (`DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`).
- 2026-09-30 (verified, headless probe served from `http://localhost`): without `--enable-experimental-web-platform-features` Chrome reports `'bluetooth' in navigator` = false; with the flag `navigator.bluetooth.getAvailability()` = true. `localhost` counts as a secure context.

### Harness

- 2026-09-30 (ticket 02, this project's image, MD5 5af085eb6016fbcb5958e29dd9ca6990): `./verify.sh <&-` (stdin closed) ran build, guard, identify (`chip_id=13`), reset + capture, `[BOOT] reason=usb at +2.062s`: `RESULT: PASS (4/4 checks)`, exit 0, 4 s. `./verify.sh --flash` added `build.sh flash` (`MD5 相符: 5af085eb...`) before the capture: `RESULT: PASS (5/5 checks)`, exit 0, 7 s. The capture log is kept at `build/verify/capture-<stamp>.log`.
- 2026-09-30 red paths, all exit 1: `./verify.sh --seconds 1` (window ends before the 2 s boot delay, board run) gave `FAIL [BOOT] reason=<cause> present (no [BOOT] reason= marker in 26 captured line(s))` and `RESULT: FAIL (3/4 checks)`; `./verify.sh --replay <log without the [BOOT] line>` gave the same FAIL and `RESULT: FAIL (0/1 checks)`; the lock held by another `flock` gave `harness: board busy` and `RESULT: FAIL (0/0 checks)`; `PYTHONPATH=<dir with esptool.py>` made the build and the guard Check FAIL (`RESULT: FAIL (0/2 checks)`) before any board access.
- 2026-09-30: `--replay LOG` runs only the capture Checks over a saved log (lines before a `stale line(s)` note are dropped, as the live capture drops them): no board, no lock, no build. A capture window shorter than the boot marker delay is the cheapest on-board red path.
