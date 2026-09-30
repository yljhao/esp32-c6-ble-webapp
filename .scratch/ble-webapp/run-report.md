# Run report: BLE Web App (unattended run, 2026-09-30)

## Tickets

| # | Title | Result | Commits (implementation) | Close commit |
|---|-------|--------|--------------------------|--------------|
| 01 | Toolchain and target loop | done | 663249d, dfb31e5, 2c56ae1 | e3dec44 |
| 02 | Harness skeleton | done | f277de7 | b2b6253 |
| 03 | Self-test and Duty readback | done | 01dc948, cf8f576 | 8c9e92f |
| 04 | Watchdog | done | f2eb015, 6b5d6bf, d7a3983 | 9ec97ec |
| 05 | Harness BLE Central Checks | done | 0a50ed2, eef40ed | a7d88cc |
| 06 | Advertising and one Connection | done | e025d57 | 2558f65 |
| 07 | Shell link `led set` / `led get` | done | 1d5e152 | 176b89f |
| 08 | Shell link command restriction | done | f550489 | e8caa9f |
| 09 | Heartbeat | done | 95a6666 | 48fce6d |
| 10 | Web App logic and Playwright runner | done | 7e5c30d | 258fbff |
| 11 | Web App connect / control / Heartbeat | done | 828f041 | 508a396 |
| 12 | Web App disconnect and reconnect | done | 4677f04 | 8b77712 |
| 13 | GitHub repo, Pages, full acceptance | done | 0425a77, a685b13, 65a3ca0 | 58e84b5 |
| 14 | Bluefy acceptance on the iPhone | not started (human) | none | none |

Parked (`needs-info`): none. No ticket needed the Opus/Fable escalation.

## Last full run

- `./verify.sh --flash` on the production image: `RESULT: PASS (51/51 checks)` (exit 0), run by the driver at the end of this run.
- `./build.sh test`: exit 0 (twister 65/65, esptool guard test all passed, tools/verify 291 unittests OK, Web App logic 85/85 in headless Chrome).
- Repo: https://github.com/yljhao/esp32-c6-ble-webapp (public). Pages: https://yljhao.github.io/esp32-c6-ble-webapp/ (workflow run 36658520504, success; only `webapp/` is served, `build.sh` etc. return 404).
- Board state at the end: **production state** (image of `main` without `debug.conf`/`analyze.conf`, flashed by `./verify.sh --flash`, MD5 `e7b2ab427aece2ffc27bb5f84b9bb4fc`). The board was handed back by esptool-build before ticket 01; that session agreed not to touch it during the run.

## Things to know (judgement calls the user may want to revisit)

1. **The PC's Bluetooth link was unreliable for stretches** (supervision timeouts `reason=0x08`, seen mainly in tickets 09, 11, 12, 13). A BLE mouse (MX Master 3) is connected to the same adapter; whether it is the cause is unproven. No PC network, rfkill or power setting was changed. Because of it the Harness now has bounded, visible retry rules:
   - Heartbeat cadence (tickets 09, 11): the PC-clock 1 s ± 200 ms criterion is retried over up to 3 windows, but only when the board's own `uptime_ms` steps are exactly 1000 ms and `seq` is continuous. The Spec reviewer of ticket 11 called this softer than the literal criterion.
   - `./verify.sh --web` repeats the whole Chrome scenario (max 4 runs, only the last judged) when the console shows a link lost by something other than the Harness's own disconnect (`reason` != 0x13). Every run is listed in the Check detail.
   - A board-side failure (wrong period, missing `seq`, reboot, bad reply) is never retried away.
   - Ticket 13's first `--flash` run failed 45/49 purely from `0x08` drops; the immediate rerun and the final driver run passed 51/51.
2. **Firmware suggestion (not done):** the board asks the Central for a 4 s supervision timeout via `bt_conn_le_param_update`, but only after `CONFIG_BT_CONN_PARAM_UPDATE_TIMEOUT` (5 s); asking sooner might reduce the drops (ticket 11 note).
3. **Disconnect detection margin is small:** after a board reboot the page shows "disconnected" in 3.9 to 4.0 s against the 5 s limit (the 4 s supervision timeout).
4. **Ticket 08:** "read-only status commands" on the Shell link is realised as `led get` only (ADR-0001: no kernel/device commands). Anything else answers `ERR command not allowed`.
5. **Ticket 09:** "no Heartbeat while nobody is subscribed" has no Harness Check, only the design guarantee (`bt_nus_send` error drops the line). The Heartbeat is sent by a separate sender thread so a stalled link cannot starve the watchdog (proved by `./verify.sh --stall`). The Duty readback (ticket 03 module) now counts whole PWM periods.
6. **Publishing (ticket 13):** the public repo contains, in the docs/tickets/history, the board's and the PC Bluetooth adapter's MAC addresses and `~` paths. The driver and the implementer judged these not to be secrets (no tokens, keys, venv or build output; commit author is the GitHub noreply address), so the ticket was not parked. If you want them scrubbed, that needs a history rewrite and a force push, which was not authorized.
7. **esptool-build:** this project relies on esptool-build d7b0966 (`get-security-info` honours `--after`, `erase-flash`), committed and pushed by that session during this run. `west flash` itself is not covered by the build script's esptool guard (west calls the PATH `esptool` directly; ADR-0003 notes it).
8. Ticket 03's LED sweep is proved by Duty readbacks (0 / 128 / 255); nobody watched the LED.

## Human checks waiting for the user, in order

1. (Optional, ticket 03) Reset the board and watch the orange User LED: off to full and back to off in about 1.6 s, then half brightness. Duty readbacks already prove it.
2. **Ticket 14 (last): Bluefy on the iPhone**, board in production state, Pages URL https://yljhao.github.io/esp32-c6-ble-webapp/. Start a serial capture first (`./build.sh console 600`, or `./build.sh serial 600` which resets the board). Expected values:
   - Bluefy opens the Pages URL and Connect finds `XIAO-C6-LED`.
   - Moving the slider visibly dims and brightens the orange LED; the capture shows the matching `[LED] brightness=` lines (0 % → 0, 50 % → 128, 100 % → 255).
   - The Heartbeat `seq` on the page increases about once a second.
   - After closing and reopening Bluefy (or turning Bluetooth off and on), Reconnect shows the Brightness kept.
   - Any Bluefy-specific behaviour (reconnect without chooser, MTU, pairing prompt) is written into `docs/agents/board-notes.md`.

## After the run: history rewrite (2026-09-30)

At the user's request the Bluetooth adapter MAC of the PC and the board's MAC were redacted (`<hci0-mac-redacted>`, `<board-mac-redacted>`) from the whole history of the public repository, and `main` was force-pushed. Every commit hash therefore changed; the hashes in this report and in tickets 02 to 05 were remapped to the new ones. Commit hashes elsewhere in the tickets' `## Comments` or board-notes evidence log are not a concern: none of them referred to this repository's commits except the ones remapped here. The `esptool-build` commit `d7b0966` belongs to the other repository and is unchanged.
