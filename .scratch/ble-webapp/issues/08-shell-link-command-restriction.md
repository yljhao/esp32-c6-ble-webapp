# 08: Shell link command restriction

Spec: `.scratch/ble-webapp/spec.md` (Shell link command restriction). ADR-0001.

**What to build:** The Shell link offers only the `led` command group and read-only status commands; anything else is refused there, while the serial shell keeps every command. `shell_set_root_cmd()` applies to all instances (unverified: read from the shell header), so the implementer picks a per-instance mechanism and records the choice and its evidence in board-notes.

**Blocked by:** 07

**Board:** required

**Status:** ready-for-agent

- [x] `kernel reboot` sent over the Shell link is refused with a line starting `ERR ` and the board does not reset (no new `[BOOT]` within 5 s).
- [x] `kernel reboot` on the serial shell resets the board (`[BOOT] reason=software`).
- [x] `led set` / `led get` over the Shell link still work.
- [x] Harness Checks for the refusal and the serial-shell acceptance.

## Comments

2026-09-30 (implementer, `./verify.sh --flash` on image MD5 `c44567cca189da4637cb7c594b7f7e3b`, `RESULT: PASS (44/44 checks)`, capture logs `build/verify/shell-20260930-055627.log`, `serial-reboot-20260930-055644.log`):

- Mechanism: an allow-list in the Shell link's own transport (`src/link_filter.c`, called from `transport_read()` in `src/shell_nus.c`); `shell_set_root_cmd()` was read and rejected (it sets `selected_cmd` on every instance). Reasons and evidence in `docs/agents/board-notes.md`, `### Ticket 08`.
- Box 1: `Shell link: kernel reboot is refused with ERR command not allowed and the board does not reset (no [BOOT] within 5 s)` PASS (`ERR command not allowed; no [BOOT] marker and no reset in 5.5s`); the same Connection then answers `led get` with `LED 128`; 13 more refused inputs (incl. `led get\rkernel reboot`, ESC, TAB) each one `ERR command not allowed`, no reset.
- Box 2: `serial shell: kernel reboot resets the board, next boot [BOOT] reason=software` PASS (`[BOOT] reason=software at +2.097s`).
- Box 3: the ticket 07 Checks `led set 0|128|255` over the Shell link (exact `LED <n>`, `[LED]` marker with Duty readback), `led set 300|abc|<none>` `ERR`, reconnect `led get` all still PASS in the same run.
- Box 4: the Checks are `refusal_checks` and `run_serial_reboot` in `tools/verify/verify.py`, with logic in `central_logic.py` (`expect_refusal`, `expect_only_refusals`) and `checks.py` (`check_no_reboot`, `check_boot_reason`), unit-tested. Red path on the board: with `allowed()` forced to true the Harness gave `FAIL ... kernel reboot is refused ... (no reply line; board reset (ROM banner) at +6.2s)`, `RESULT: FAIL (39/42 checks)`; source restored, scratch dir removed.
- `./build.sh test`: twister `49 of 49 executed test cases passed` (new suite `c6.link_filter`, 11 cases), esptool guard test all passed, `Ran 204 tests ... OK`.
- Review (embedded-review, two read-only reviewers) fixes applied: the `kernel version|uptime` status commands were removed from the allow-list because ADR-0001 says never a kernel or device command (the spec's "read-only status commands" is `led get`); `transport_read` trusts the filter's length only on PASS; the refusal log line is rate limited (1st, 2nd, 4th ...); `LINK_FILTER_MAX_WORDS` and `LED_ARGS_MAX` reasons written down; the stack figure in `prj.conf` updated (1344); SPDX line first in the new test file.
- Handed on: the Wire contract now holds for anything a Central sends (one `LED <n>` or `ERR ` reply per line). Ticket 09's Heartbeat must not go through `transport_read` or be judged by the filter; it is board output.
