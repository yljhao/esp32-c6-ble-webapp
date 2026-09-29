# Spec: XIAO ESP32-C6 BLE Web App

Status: ready-for-agent

## Problem Statement

The user wants a reference example where a web page, opened in a browser that supports Web Bluetooth, controls the User LED of a Seeed Studio XIAO ESP32-C6 running Zephyr and shows the board's Heartbeat live. The example must work first in Google Chrome on the development PC, so that every behaviour is proven before the user accepts it with Bluefy on an iPhone. Today there is nothing: no firmware, no page, no way to check either without a human watching.

## Solution

The board advertises as `XIAO-C6-LED` and accepts one Connection at a time. Over that Connection it runs a Shell link: the Zephyr shell carried over the Nordic UART Service. The Web App, a static page published on GitHub Pages, finds the board, opens the Connection, sets Brightness with a 0–100 % slider through `led set`, and shows each Heartbeat as it arrives. When the Connection drops the page says so and offers a reconnect button; the board goes back to advertising and keeps its Brightness. The board proves each Brightness on its serial console with a Duty readback, so a PC Harness (acting as a Central) and a Playwright-driven Chrome can check the whole path unattended. The user's only manual step is the final Bluefy acceptance.

## User Stories

1. As the user, I want the board to print its Reset reason at boot, so that I can tell a watchdog reset from a power-on or a USB reset.
2. As the user, I want the board to run a Self-test of the User LED at boot and end at Brightness 128, so that a broken PWM path is reported before any Central connects.
3. As the user, I want the board to arm a watchdog with a 5 s window that its main loop feeds, so that a hung firmware reboots itself.
4. As the user, I want the board to advertise as `XIAO-C6-LED` with the NUS service, so that the Web App and the Harness can find it by name and service.
5. As the user, I want the board to accept only one Connection and stop advertising while it exists, so that two pages never fight over the User LED.
6. As the user, I want the board to advertise again as soon as a Connection ends, so that I can reconnect without touching the board.
7. As a Central, I want to send `led set <n>` for n in 0–255 and get `LED <n>` back, so that I know the Brightness was applied.
8. As a Central, I want `led set` with a value outside 0–255, a non-number, or no argument to return an error and leave the Brightness unchanged, so that a bad input never changes the LED.
9. As a Central, I want `led get` to return `LED <n>`, so that I can learn the current Brightness after connecting.
10. As the user, I want every applied Brightness to print a Duty readback on the serial console, so that the LED path is proven without looking at the LED.
11. As a Central, I want a Heartbeat line `{"seq":N,"uptime_ms":N}` about once a second while I listen, so that I can see the board is alive.
12. As the user, I want the Heartbeat `seq` to count from boot and keep advancing while no Central listens, so that a gap marks a disconnect and a smaller number marks a reboot.
13. As the user, I want the Brightness kept across a disconnect and reset to 128 by a reboot, so that reconnecting shows the LED as I left it.
14. As the user, I want the Shell link to offer only the `led` commands and read-only status commands, so that anyone who connects without pairing cannot reboot or reconfigure the board.
15. As a developer, I want the serial console shell to keep every command, so that I can still debug the board over USB.
16. As the user, I want to open the Web App from a GitHub Pages URL, so that Bluefy on my iPhone can load it over HTTPS.
17. As the user, I want the Web App to show a connect button that opens the browser's device chooser filtered to `XIAO-C6-LED`, so that I pick the right board.
18. As the user, I want the Web App to show "connected" and sync its slider from `led get` after connecting, so that the slider starts at the real Brightness.
19. As the user, I want moving the slider to send the matching `led set` (0–100 % mapped to 0–255), so that the User LED follows the slider.
20. As the user, I want the Web App to show the latest Heartbeat `seq` and uptime and update them as lines arrive, so that I can see the Connection is live.
21. As the user, I want the Web App to show "disconnected", keep the last Heartbeat on screen, and offer a reconnect button that reuses the chosen board without the chooser, so that recovering a drop takes one tap.
22. As a developer, I want the Harness to check the board's boot, Brightness, Heartbeat and reconnect behaviour from the PC unattended, so that firmware tickets are accepted without a human eye.
23. As a developer, I want a Playwright run to drive the Web App in real Chrome against the real board, so that the page is accepted without a human hand.

## Implementation Decisions

- **Platform**: Zephyr 4.4.2, board `xiao_esp32c6/esp32c6/hpcore`, an out-of-tree application at the repository root in the same shape as the reference project `esp32-c6-wifi-vpn-mqtt-exam-2`. Simple boot, no MCUboot, no sysbuild.
- **Flashing** (ADR-0003): both paths run esptool-build. `west flash -d build` for day-to-day builds (esptool-build f22af07 detects the chip and the single USB-Serial/JTAG port; verified by the esptool-build session with a scratch image, not yet with this project's image). The build script's flash command passes `--chip esp32c6` and the port explicitly and is what the Harness and acceptance use, so a wrong board is refused. The first ticket that flashes proves both paths here and records whether the post-flash reset re-enumerates USB.
- **No upstream esptool**: the build script refuses to build or flash unless the `esptool` found on PATH is an esptool-build launcher, the build's cached esptool executable is that same launcher, and no Python it uses can import an `esptool` module; the Harness runs the same guard as a Check.
- **Python environments**: host tools (the Harness, the Web App automation, the board console tools) run in the project's own virtual environment with `bleak`, `playwright` and `pyserial`. West, twister and esptool stay in the Zephyr virtual environment. Playwright drives the installed Chrome (`channel="chrome"`), so no browser download.
- **Modules ported from the reference project**, adapted and renamed where the glossary differs: User LED driver (LEDC PWM on GPIO15, 20 kHz, inverted polarity, 0–255), Brightness, Duty readback (including the Self-test sweep 0→255→0 with readbacks at 0, 128, 255), Reset reason, Heartbeat (pure counter and encoder, now counting from boot rather than from a broker session), watchdog (task watchdog, 5 s window, fed by the main loop only), the build script and the board tools (reset helper, console capture with the port lock). Nothing from WiFi, Tunnel, SNTP or MQTT is ported.
- **Boot order**: Reset reason marker → Self-test (failure reported, not retried, boot continues) → Brightness 128 → watchdog armed → Bluetooth enabled → advertising. The main loop then feeds the watchdog and emits Heartbeats.
- **Shell link** (ADR-0001): a shell transport of this project's own over the Zephyr NUS service (upstream 4.4.2 has NUS but no shell backend). On that shell instance echo, prompt, colours and VT100 are off, so every line the Central reads is either a command reply or a Heartbeat. Output is split into notifications no larger than the negotiated ATT MTU minus 3; received bytes are queued out of the Bluetooth callback and consumed by the shell thread, never processed in the callback. The serial console keeps its own full shell instance.
- **Shell link command restriction**: the Shell link exposes only the `led` command group and read-only status commands; the serial shell keeps all commands. `shell_set_root_cmd()` applies to all instances (read from the shell header), so the restriction needs a per-instance mechanism; the implementer chooses it and proves it on the board by showing `kernel reboot` refused on the Shell link and accepted on the serial shell.
- **Wire contract on the Shell link** (shared with the Web App and the Harness):
  - Central → board: `led set <n>\n` (n decimal 0–255), `led get\n`.
  - Board → Central, reply: `LED <n>` on success; a line starting `ERR ` on a rejected value, missing argument or non-number, with the Brightness unchanged. Out-of-range values are rejected, not clamped.
  - Board → Central, Heartbeat: `{"seq":<u32>,"uptime_ms":<u64>}`, one per second while a Central is subscribed to NUS notifications. A line beginning `{` is a Heartbeat; a line beginning `LED ` or `ERR ` is a reply.
  - Lines end with `\n`; a line may span several notifications and the reader reassembles it.
- **Heartbeat rules**: `seq` is 0 at boot and advances once per second from boot whether or not a Central listens; a missed period is consumed, not queued; only a reboot resets it. Sent only while a Central is subscribed.
- **Brightness rules**: 0–255 on the board, 128 at boot, not persisted to flash, unchanged by a disconnect. The Web App maps its 0–100 % slider to 0–255 with `round(pct × 255 / 100)` and maps back with `round(n × 100 / 255)`.
- **Bluetooth**: peripheral only, one Connection (`CONFIG_BT_MAX_CONN=1`), device name `XIAO-C6-LED`, NUS service UUID in the advertising or scan response data, no pairing or encryption, ATT MTU raised to 247 with matching buffer sizes. Advertising restarts when the Connection ends.
- **Serial markers** (grepped by the Harness): `[BOOT] reason=<cause>`, `[STAGE] selftest: start|done|fail step=<n>`, `[LED] brightness=<n> duty=<pct>% freq=<hz>`, `[WDT] armed window=5000ms`, `[BLE] advertising name=XIAO-C6-LED`, `[BLE] connected`, `[BLE] mtu=<n>`, `[BLE] disconnected reason=<r>`, `[HB] seq=<n>` every tenth Heartbeat.
- **Web App**: plain HTML, CSS and ES-module JavaScript with no framework and no build step, chosen for compatibility with Chrome and Bluefy. It lives in its own directory, separate from `docs/`, and is published to GitHub Pages by a GitHub Actions workflow from the public repository `yljhao/esp32-c6-ble-webapp`. `requestDevice` filters on the name prefix and lists the NUS service as optional. The pure logic (percent conversion, line reassembly, line classification) is its own module with no DOM or Bluetooth access so it can be tested alone. On disconnect it keeps the device object and reconnects through it.
- **Harness**: a Python tool in the project's virtual environment that holds the board lock, captures the serial console, connects as a Central through `bleak`, runs named Checks, prints PASS/FAIL per Check and a final `RESULT: PASS|FAIL (n/m checks)` line, exits 0 only on PASS, and never prompts. Structure follows the reference project's verify tool.
- **Web App automation**: a Python Playwright run that launches Chrome with `--enable-experimental-web-platform-features` in a throwaway profile, answers the native device chooser through the Chrome DevTools Protocol `DeviceAccess` domain, and cross-checks the page against the serial console. It can target the local page or the Pages URL.

## Testing Decisions

- **What makes a good test here**: it checks behaviour visible at a module's interface or on the wire (a returned value, an encoded line, a marker), not internal state; firmware glue (Bluetooth callbacks, the shell transport, the PWM driver) is proven on the board, not mocked.
- **Host unit tests** (twister on `native_sim/native/64`, no board):
  - Heartbeat: `seq` 0 at boot and +1 per second from boot; advances while nobody listens; missed periods consumed, not queued; JSON encoding at maximum values fits its buffer.
  - LED command parsing: `led set` accepts 0–255; rejects out-of-range, non-numeric and missing arguments without changing the Brightness; reply strings `LED <n>` and `ERR ...` exactly as in the wire contract.
  - Shell link chunking: splitting output into chunks of at most MTU − 3 bytes for MTU 23 and 247, across line boundaries, and for empty output.
  - Duty readback arithmetic: ported suite from the reference project.
- **Host tool tests** (PC, no board):
  - Web App logic module: percent ↔ 0–255 conversion both ways including 0, 50, 100 %; line reassembly across split chunks; line classification (Heartbeat, reply, error, noise). Run in headless Chrome through Playwright, since this PC has no Node.js.
  - Harness Check logic (e.g. Heartbeat continuity, reply parsing): Python `unittest`.
- **Board acceptance, unattended**:
  - Harness: boot markers in order (`[BOOT] reason=`, `[STAGE] selftest: done`, `[WDT] armed window=5000ms`, `[BLE] advertising name=XIAO-C6-LED`); scan finds the board by name and NUS UUID; after connecting, advertising stops; `led set 0|128|255` each reply `LED <n>` and print `[LED] brightness=<n>` with Duty readback within the reference tolerance (128 → 50 ± 1 % low; 0 and 255 constant levels); `led set 300` replies `ERR` and the Brightness is unchanged; 10 s of Heartbeats with consecutive `seq` at 1 s ± 200 ms; `[BLE] mtu=` printed; disconnect → advertising again → reconnect → `led get` returns the pre-disconnect value; `kernel reboot` refused on the Shell link and accepted on the serial shell.
  - Playwright: page served locally and from the Pages URL; `DeviceAccess` selects `XIAO-C6-LED`; the page shows connected; the slider set to 50 % produces `[LED] brightness=128` on the console; the displayed Heartbeat `seq` updates at least twice within 3 s; a board reboot forced by the Harness makes the page show disconnected; the reconnect button reconnects without a chooser and the slider shows 128.
- **Verified by serial marker**: Self-test, watchdog armed, Reset reason, every applied Brightness with its Duty readback, advertising, Connection, MTU, disconnect.
- **Verified by an instrument a human holds**: none; the Duty readback replaces an oscilloscope on the User LED pad (verified on the board in the reference project).
- **Human checks remaining** (accepted by the user 2026-09-30):
  - Bluefy on the iPhone: open the Pages URL, connect, move the slider and see the User LED dim and brighten, watch the Heartbeat update, close and reopen Bluefy and reconnect with the Brightness kept. Considered: driving Bluefy from the PC; not applicable because iOS offers no automation interface to Bluefy, and this run is the user's chosen final acceptance.
  - Not a human check: the LED diode actually glowing. The Duty readback proves the pad waveform, as in the reference project, and the Bluefy run sees the LED anyway.
- **Prior art**: the reference project's host suites for heartbeat, LED command and duty readback (ztest on native_sim), its verify tool (Checks, PASS/FAIL, `RESULT:` line), and its board console capture with the port lock.

## Out of Scope

- Pairing, bonding, encryption, or any access control beyond restricting the Shell link's commands.
- Persisting Brightness across reboots.
- More than one simultaneous Connection.
- Low power or sleep; the board stays awake.
- WiFi, OTA updates, MCUboot.
- Firefox support (it has no Web Bluetooth) and snap Chromium.
- Automating Bluefy or any iOS testing.
- Changes to esptool-build itself; they belong to the esptool-build session.

## Further Notes

- ADRs: 0001 (Shell link over NUS), 0002 (Chrome .deb with the experimental web-platform flag for local testing; flag need verified on this PC), 0003 (`west flash` day to day, `build.sh flash` pinned to the C6 for acceptance; both through esptool-build), 0004 (unattended acceptance: bleak Harness and Playwright over CDP).
- Unverified until a ticket proves them on this board and PC: Zephyr 4.4.2 Bluetooth on the ESP32-C6 and its heap and stack cost; the per-instance shell command restriction; Playwright answering the Web Bluetooth chooser through CDP `DeviceAccess`; Bluefy's behaviour on reconnect.
- The user must enable `chrome://flags/#enable-experimental-web-platform-features` in their own Chrome for manual use; automation passes the flag itself.
- Creating the public GitHub repository is an outward-facing step; the ticket that does it confirms with the user first.
- The board currently runs esptool-build's tick test image; the first flashing ticket replaces it.
