# 01: Toolchain and target loop

Spec: `.scratch/ble-webapp/spec.md`. Read `CLAUDE.md`, `CONTEXT.md`, `docs/adr/`, `docs/agents/board-notes.md` first. Reference project (port from it, do not modify it): `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2`.

**What to build:** The developer loop for this repo and nothing else: a minimal Zephyr 4.4.2 out-of-tree application for `xiao_esp32c6/esp32c6/hpcore` that prints `[BOOT] reason=<cause>` once after boot, the build script (build, flash, identify, serial, console, test) and the board tools (reset helper, timestamped console capture, port lock) ported from the reference project, the project's own Python virtual environment for host tools (pyserial now; west, twister and esptool stay in the Zephyr venv), and a host test target with one trivial native_sim suite. The build script refuses to build or flash when upstream esptool could be picked up (ADR-0003, spec "No upstream esptool").

**Blocked by:** None (can start immediately)

**Board:** required

**Status:** ready-for-agent

- [ ] The build script builds the app; `./build.sh test` runs twister on `native_sim/native/64` over the repo's tests and exits 0, and exits non-zero when an assertion is broken (red path shown, then restored).
- [ ] The esptool guard: build and flash abort with a clear message unless `command -v esptool` is an esptool-build launcher, the build's cached esptool executable is that launcher, and neither the Zephyr venv Python nor the system Python can `import esptool`. Red path shown (e.g. a PATH with a fake `esptool` first), then restored.
- [ ] `west flash -d build` flashes this project's image on the board (plain, no extra flags) and the board boots into it; `./build.sh flash` (explicit `--chip esp32c6` and port) does the same. Both outputs recorded in board-notes.
- [ ] `udevadm monitor` run across `west flash` and across the reset helper; the CONFLICT line in board-notes (USB re-enumeration after reset) replaced with what was observed for each.
- [ ] The capture resets the board and shows `[BOOT] reason=usb` (or the observed cause) with timestamps; the capture goes red (non-zero exit) when the expected marker is missing.
- [ ] The project `.venv` exists, is gitignored, and is never the Zephyr venv; a `.gitignore` covers build output and the venv.
- [ ] Board-notes card lines for Reset, Capture and Test rewritten from "not yet in this repo" to the real commands; ADR-0003 updated to say `west flash` is verified in this project.
