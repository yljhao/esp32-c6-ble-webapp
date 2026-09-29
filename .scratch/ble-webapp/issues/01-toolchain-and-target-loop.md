# 01: Toolchain and target loop

Spec: `.scratch/ble-webapp/spec.md`. Read `CLAUDE.md`, `CONTEXT.md`, `docs/adr/`, `docs/agents/board-notes.md` first. Reference project (port from it, do not modify it): `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2`.

**What to build:** The developer loop for this repo and nothing else: a minimal Zephyr 4.4.2 out-of-tree application for `xiao_esp32c6/esp32c6/hpcore` that prints `[BOOT] reason=<cause>` once after boot, the build script (build, flash, identify, serial, console, test) and the board tools (reset helper, timestamped console capture, port lock) ported from the reference project, the project's own Python virtual environment for host tools (pyserial now; west, twister and esptool stay in the Zephyr venv), and a host test target with one trivial native_sim suite. The build script refuses to build or flash when upstream esptool could be picked up (ADR-0003, spec "No upstream esptool").

**Blocked by:** None (can start immediately)

**Board:** required

**Status:** ready-for-agent

- [x] The build script builds the app; `./build.sh test` runs twister on `native_sim/native/64` over the repo's tests and exits 0, and exits non-zero when an assertion is broken (red path shown, then restored).
- [x] The esptool guard: build and flash abort with a clear message unless `command -v esptool` is an esptool-build launcher, the build's cached esptool executable is that launcher, and neither the Zephyr venv Python nor the system Python can `import esptool`. Red path shown (e.g. a PATH with a fake `esptool` first), then restored.
- [ ] `west flash -d build` flashes this project's image on the board (plain, no extra flags) and the board boots into it; `./build.sh flash` (explicit `--chip esp32c6` and port) does the same. Both outputs recorded in board-notes.
- [ ] `udevadm monitor` run across `west flash` and across the reset helper; the CONFLICT line in board-notes (USB re-enumeration after reset) replaced with what was observed for each.
- [ ] The capture resets the board and shows `[BOOT] reason=usb` (or the observed cause) with timestamps; the capture goes red (non-zero exit) when the expected marker is missing.
- [x] The project `.venv` exists, is gitignored, and is never the Zephyr venv; a `.gitignore` covers build output and the venv.
- [ ] Board-notes card lines for Reset, Capture and Test rewritten from "not yet in this repo" to the real commands; ADR-0003 updated to say `west flash` is verified in this project.

## Comments

### 2026-09-30 host work (no board touched)

- Build: `./build.sh build` builds `build/zephyr/zephyr.bin` (144400 bytes), simple boot, console on USB-Serial/JTAG.
- Test: `./build.sh test` runs twister on `native_sim/native/64` (`1 of 1 executed test cases passed (100.00%)`) and then `tools/test_esptool_guard.sh` (7 cases, all passed) and exits 0. Red path: with the assertion changed to `2 + 2 == 5`, `Assertion failed at CMAKE_SOURCE_DIR/src/main.c:10 ... (2 + 2 not equal to 5)`, `SUITE FAIL`, exit 1; restored, exit 0.
- Guard: `tools/esptool-guard.sh` (called by `./build.sh build|flash|identify|guard`). Red paths automated in `tools/test_esptool_guard.sh` (fake `esptool` first on PATH, no esptool on PATH, cache naming a non-launcher, cache naming another launcher, importable `esptool` module, flash without a build). Shown through the build script with `PYTHONPATH=<dir with esptool.py>`: `./build.sh build`, `guard` and `flash` all print `esptool-guard: FAIL ... refusing to build or flash (ADR-0003)` and exit 1 before touching the board; without it `esptool-guard: OK`.
- Venv: `.venv` (Python 3.14.4, `home = /usr/bin`, pyserial 3.5) created by `tools/venv.sh`; `git check-ignore` confirms `.venv` and `build` are ignored.
