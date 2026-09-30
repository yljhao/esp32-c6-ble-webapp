# 12: Web App disconnect and reconnect

Spec: `.scratch/ble-webapp/spec.md` (user story 21, Web App).

**What to build:** When the Connection drops the Web App shows "disconnected", keeps the last Heartbeat on screen and offers a reconnect button that reconnects through the same device without opening the chooser; after reconnecting it re-syncs the slider with `led get`.

**Blocked by:** 11

**Board:** required

**Status:** done

- [x] Playwright + Harness: a board reboot (serial shell `kernel reboot`) makes the page show disconnected within 5 s with the last `seq` still shown.
- [x] The reconnect button reconnects with no chooser prompt, the slider shows 50 % (Brightness 128 after reboot) and Heartbeats resume from a small `seq`.
- [x] A plain disconnect without reboot (Harness-forced or page-side) followed by reconnect keeps the Brightness set before it.

## Comments

- 2026-09-30 implementation (no stuck failure, no escalation). `webapp/app.js` and `index.html`: `#reconnect` button (Connect is hidden once the chooser was answered), on `gattserverdisconnected` the status says `disconnected`, the slider is disabled and shows `-`, the last Heartbeat seq and uptime stay with a note; Reconnect calls `device.gatt.connect()` on the kept device and re-syncs the slider with `led get`. `./verify.sh --web` (= `./build.sh test-web-board`) runs the extra scenario in the same real Chrome session; new pure Checks in `tools/verify/checks.py` with unit tests (`check_disconnect_shown`, `check_reconnect_no_chooser`, `check_resumed_after_reboot`, `check_brightness_kept`, `seq_shown_at`, a fourth Duty tolerance for Brightness 64). `BackgroundCapture.send` types `kernel reboot` on the serial shell through an outbox queue in `tools/board/console.py`.
- Evidence, last run (`./verify.sh --web`, `RESULT: PASS (32/32 checks)`, 44 s, no repeat, log `build/verify/web-20260930-094404.log`):
  - box 1: `PASS Web App: a board reboot (serial kernel reboot) makes the page show disconnected within 5 s, last seq still shown, Reconnect offered (disconnected 4.0 s after the trigger (limit 5 s), last Heartbeat seq 25 kept on screen ...)` and `PASS ... [BOOT] reason=software at +27.548s`. The 4.0 s is the link's supervision timeout, about 1 s of margin.
  - box 2: `PASS ... Reconnect after the reboot opens no chooser (no chooser prompt (events stay at 2), requestDevice calls stay at 1, page connected; Reconnect click(s): connected after 1.75 s)`, `PASS ... slider shows 50 % (boot Brightness 128) from led get (console brightness=128, slider 50 % (want 50 %), page text '128 (50 %)')`, `PASS ... Heartbeats resume from a small seq after the reboot (first seq after the reboot 1 (limit 15), last one before it 25)`.
  - box 3: `PASS ... slider 25 % prints [LED] brightness=64 ...`, `PASS ... Reconnect after a plain disconnect opens no chooser ...`, `PASS ... after a plain disconnect and Reconnect the slider shows the Brightness set before it (25 % = 64), no reset in between (console brightness=64, slider 25 % (want 25 %), page text '64 (25 %)')`.
  - Red paths on the board (scratch page copies, exit 1, `RESULT: FAIL (30/32 checks)` each): the seq cleared on disconnect, a Reconnect through `requestDevice`, a reconnect without `led get`. Details in `docs/agents/board-notes.md` (Ticket 12).
  - Other runs: default Harness `./verify.sh` `RESULT: PASS (50/50 checks)` (after several radio-caused failures, also seen at HEAD: `reason=0x08`, late replies, link jitter with exact board spacing); `./build.sh test` passes (65 twister cases, 291 tool tests, 85 Web App logic tests).
- Review (embedded-review, two reviewers) applied: the reboot Check now also requires the Disconnect button to be hidden (it had drifted from the plain one), the slider and board text are cleared on disconnect so a missing `led get` re-sync fails (spec reviewer: the old Check could pass without it), a 2 s write timeout on the console port, an aborted scenario puts the slider back to 50 %, the scenario time bound is derived, the 64 / 25 % literals live in `checks.WEB_KEPT_*`. Not changed: the hb note and the "Press Reconnect" message are small UI extras kept on purpose (the ticket says the last Heartbeat stays on screen; the note says it is not live).
- Testing calls: web glue (DOM, Web Bluetooth) has no host test, proven by `--web` on the board; the new pure Checks got unit tests first (red, then green) in `tools/verify/test_checks.py`.
