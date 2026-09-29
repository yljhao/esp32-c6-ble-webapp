# 07: Shell link carrying `led set` / `led get`

Spec: `.scratch/ble-webapp/spec.md` (Shell link, Wire contract, Brightness rules). ADR-0001. Glossary: Shell link.

**What to build:** This project's own Zephyr shell transport over NUS, with echo, prompt, colours and VT100 off on that instance, received bytes queued out of the Bluetooth callback, and output split into notifications of at most MTU − 3 bytes. Over it a Central sends `led set <n>` and `led get` and reads `LED <n>` or `ERR ...`. The serial shell keeps working. Brightness survives a disconnect.

**Blocked by:** 06

**Board:** required

**Status:** done

- [x] `led set 0`, `led set 128`, `led set 255` over the Shell link each reply exactly `LED <n>` and print `[LED] brightness=<n> duty=...` with the Duty readback in tolerance (0 and 255 constant levels, 128 → 50 ± 1 % low).
- [x] `led set 300`, `led set abc` and `led set` reply a line starting `ERR ` and the Brightness is unchanged (`led get` confirms).
- [x] Disconnect, reconnect, `led get` returns the value set before the disconnect.
- [x] Nothing but reply lines arrives on the Shell link (no echo, prompt or escape sequences).
- [x] The same `led` commands work on the serial shell.
- [x] Host suites under `./build.sh test`: chunking (MTU 23 and 247, line boundaries, empty output) and LED command parsing (range, non-numeric, missing argument, exact reply strings).
- [x] Harness Checks for all board behaviour above.

## Comments

2026-09-30 (implementer, `./verify.sh --flash` on image MD5 `85e3d41b64e55994a439467c26b69b1e`, `RESULT: PASS (39/39 checks)`, capture logs `build/verify/shell-*.log`, `serial-led1-*.log`, `serial-led2-*.log`):

- Box 1: `led set 0|128|255` reply `LED 0`, `LED 128`, `LED 255`; markers `[LED] brightness=0 duty=0.0% freq=0 at +1.349s`, `brightness=128 duty=50.4% freq=19986 at +1.431s`, `brightness=255 duty=100.0% freq=0 at +1.533s`.
- Box 2: `led set 300` -> `ERR out of range 0-255`, `led set abc` -> `ERR not a number`, `led set` -> `ERR missing value`; each with no `[LED]` marker and `led get` still `LED 255` (255 differs from the boot level 128, so "unchanged" is not vacuous).
- Box 3: after disconnect (`reason=0x13`) and reconnect `led get` -> `LED 255`.
- Box 4: `Shell link: nothing but reply lines arrives ... (9 line(s), all replies or Heartbeats, 104 bytes)`; red path on the board: scratch build with `.echo = 1` on the link gave `FAIL ... line that is neither reply nor Heartbeat: 'led set 0'`, `RESULT: FAIL (37/39 checks)`; source restored, scratch dir removed.
- Box 5: serial shell typed `led set 0`, `led get`, `led set 255`, `led set 300`, `led set abc`, `led set`, `led get`, `led set 128`: replies `LED 0, LED 0, LED 255, ERR out of range 0-255, ERR not a number, ERR missing value, LED 255, LED 128`, three `[LED]` markers only.
- Box 6: `./build.sh test`: twister `38 of 38 executed test cases passed` (new suites `c6.led_command` 11 cases, `c6.nus_chunk` 9 cases), esptool guard test all passed, `Ran 190 tests ... OK`.
- Box 7: the Checks above are in `tools/verify/verify.py` (`run_shell_link`, `run_serial_led`) with their logic in `central_logic.py` / `checks.py`, unit-tested.
- Also: `./verify.sh --bite` `RESULT: PASS (18/18 checks)`; the refused-`debug hang` Check is now meaningful (`debug: command not found` on the serial shell).
- Review (embedded-review, two read-only reviewers) fixes applied: reply carries an `error` flag instead of glue testing `line[0]`; dropped Central lines and failed notifications are logged; the unbounded `bt_nus_send` wait is documented at `tx_flush`; the serial script covers 0/255/128 and all three rejections; `session` renamed away (glossary); sizing reasons in `prj.conf`.
- Handed on: ticket 08 (the Shell link currently offers every shell built-in, and bare `led`, `led set -h` or an unknown command print shell text, not an `ERR ` line); ticket 09 (the main loop must not call `shell_print` on the link's shell: `bt_nus_send` can wait for a buffer without bound while the link is stalled, and the main loop feeds the watchdog; hand the Heartbeat text to the shell thread or send it from a thread of its own).
