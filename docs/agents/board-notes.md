# Board notes

Platform knowledge that outlives a session. Two layers: the **card** below is what every session reads first and is kept current (rewrite a line when a fact changes, never stack history); the **evidence log** under it is dated and append-only, read when a card line needs its reason. `implement` reads the card before its first build, and before finishing rewrites any card line that changed and appends its evidence to the log.

A ticket's `Board:` line is a permission, not a schedule: `required` lets the implementer flash, reset, capture serial, drive the probe, or stage the PC network; `none` forbids all of that, including driving the board through the network. Either way, one actor touches the board at a time.

## Every session

One line each, always current. This is the whole file for most sessions. A card line is one sentence: the command, or the fact. It never carries a measurement, a timing, a list of checks, or a date; those go under the evidence log with a dated heading, and the card line may say "see log: <heading>". A card longer than 25 lines, or a line longer than 200 characters, is moved to the log before the session ends.

- Board: Seeed Studio XIAO ESP32-C6, Zephyr target `xiao_esp32c6/esp32c6/hpcore`, Zephyr 4.4.2 at `~/zephyrproject/zephyr`, SDK `~/zephyr-sdk-1.0.1`.
- Port: `/dev/ttyACM0` (USB-Serial/JTAG `303a:1001`), 115200.
- Flash: `west flash -d build` day to day; `./build.sh flash` (pins `--chip esp32c6`) for the Harness and acceptance; both run esptool-build; no MCUboot, no `--sysbuild`, no `--no-reset` (ADR-0003).
- Reset: not yet in this repo; port `tools/board/reset.py` from `../esp32-c6-wifi-vpn-mqtt-exam-2` (see log: Reset method).
- Capture: not yet in this repo; port `build.sh serial` + `tools/board/console.py` from the reference project (see log: Capture command).
- Test: not yet in this repo; reference uses `./build.sh test` = twister on `native_sim/native/64`.
- Verify: none yet.
- Production state: not defined yet.
- Quirks to know before touching the board: `get-security-info` ignores `--after` and leaves the chip in ROM download mode until an explicit reset; console bytes printed while the port is closed are lost; 32-bit `native_sim` does not link on this PC.

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

- esptool-build (`~/Desktop/Project/esptool-build`) only exposes `version`, `elf2image`, `write-flash`, `get-security-info`; its default chip is esp32c3, so it refuses a write without `--chip esp32c6` (this is why `west flash` is rejected on this board). `--baud` is ignored on USB-Serial/JTAG, `erase-flash` unsupported.
- Flash offset `CONFIG_FLASH_LOAD_OFFSET=0x0` (simple boot), artifact `build/zephyr/zephyr.bin`, `write-flash --after hard-reset` resets after writing.
- 2026-09-30 (esptool-build f22af07, reported by the esptool-build session; verified there on this XIAO with a scratch image, NOT yet with this project's image): with no `--chip`, `write-flash`/`get-security-info` detect the chip from `chip_id` (13 → esp32c6) and refuse an unknown or not-yet-verified chip; with no `--port`/`ESPTOOL_PORT`, it uses the port only when exactly one `303a:1001` is present, refuses zero or several. So plain `west flash -d build` works on the C6. The line above about refusing without `--chip` is superseded by this one.
- 2026-09-30 (esptool-build f22af07): an explicit `--chip esp32c6` still refuses a board whose `chip_id` differs; auto-detect instead flashes whatever chip is attached (a C3 would be flashed as a C3). Several boards: `west flash -d build --esp-device /dev/ttyACM1` or `ESPTOOL_PORT=...`; `/dev/serial/by-id/*` names carry the USB serial number and work as `--esp-device`.
- 2026-09-30 (esptool-build f22af07): launchers `~/zephyrproject/.venv/bin/esptool` (the one west finds first on PATH) and `~/.local/bin/esptool` both import the esptool-build working tree directly, so its checkout state is what runs; no reinstall after an update.
- 2026-09-30 (esptool-build f22af07): still unsupported: `--baud` (accepted, prints a note, ignored on USB-CDC), `erase-flash` (so `west flash --erase` fails; FLASH_BEGIN erases the written region anyway), `--encrypt` / `--esp-encrypt`. `--flash-size detect` falls back to 4MB (the board passes 4MB, so not reached). ROM-only (no stub): ~140 KB in ~4 s.
- 2026-09-30 (read from Zephyr 4.4.2 `runners/esp32.py` do_run, reported by esptool-build): never `west flash --no-reset`; with reset off the runner omits `write-flash -u` and builds a broken command.
- 2026-09-30 (verified on this PC): no upstream esptool anywhere. Both the runner (`runners/esp32.py:84`, bare `esptool`) and the build (`find_program(ESPTOOL_EXECUTABLE esptool)`) resolve through PATH; the only hits are the two esptool-build launchers (Zephyr venv `bin/esptool`, `~/.local/bin/esptool`, the latter first when the venv is not active). `pip show esptool` in the Zephyr venv: not found; `import esptool` fails in the venv and system Python; nothing in `/usr/bin`, `/usr/local/bin`, `~/.espressif/tools` (only `openocd-esp32`). A later `pip install esptool` would silently win on PATH, so the build script guards it (see spec).

### Reset method

- Reference `tools/board/reset.py`: TIOCEXCL open, DTR/RTS (1,1)->(0,1)->(0,0), RTS high (EN low) 200 ms, release, read ROM banner. RTS reset does not re-enumerate USB (`/dev/ttyACM0` stays). `get-security-info` leaves the chip idle in ROM download mode, so `identify` must be followed by this reset.
- 2026-09-30 (esptool-build f22af07): `get-security-info` ignores `--after` and only closes the port, unlike upstream esptool, which honours `--after hard-reset` there too. `write-flash --after hard-reset` (what `west flash` passes) boots straight into the app.
- 2026-09-30 CONFLICT, unverified: the esptool-build session reports that USB-Serial/JTAG re-enumerates after the post-flash hard reset (`/dev/ttyACM0` briefly disappears), while the reference project saw no re-enumeration on an RTS reset of a running app (`udevadm monitor` silent, 2026-09-13). Both may hold (reset from ROM download mode vs. from the app). The first flashing ticket runs `udevadm monitor` across `west flash` and across `reset.py` and replaces this line with what it saw.

### Capture command

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
