# 02: Harness skeleton

Spec: `.scratch/ble-webapp/spec.md` (Harness, Testing Decisions). Reference: the verify tool in `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2`.

**What to build:** The acceptance Harness as an unattended command: it holds the board lock for the whole run, builds, identifies the chip, optionally flashes through the build script's pinned `--chip esp32c6` path, resets and captures the console, runs named Checks, prints PASS/FAIL per Check and a final `RESULT: PASS|FAIL (n/m checks)` line, keeps the capture log under the build directory, never prompts, and exits 0 only on PASS. First Checks: the esptool guard and `[BOOT] reason=` present.

**Blocked by:** 01

**Board:** required

**Status:** ready-for-agent

- [x] One command runs the whole Harness with stdin closed and prints the per-Check lines and the `RESULT:` line.
- [x] A `--flash` mode flashes before capturing; without it the running image is checked.
- [x] The esptool guard is a Check; `[BOOT] reason=` is a Check.
- [x] Red path proven: a capture missing `[BOOT]` (a replayed or scratch-image capture) gives FAIL on that Check, `RESULT: FAIL`, exit 1.
- [x] Board-notes card line "Verify" names the command and states that its red path is proven.

## Comments

### 2026-09-30 implementation (board work, esptool-build session had released the board; `fuser -v /dev/ttyACM0` showed no holder)

- Built: `./verify.sh` (wrapper, stdin from /dev/null) -> `tools/verify/verify.py` (glue: lock, build.sh calls, capture, log) + `tools/verify/checks.py` (pure Check logic and the `RESULT:` line, unit-tested by `tools/verify/test_checks.py`, 11 cases, run by `./build.sh test`). Checks: build produces zephyr.bin, esptool guard, chip_id 13, `[BOOT] reason=` (and `build.sh flash` with `--flash`). Options `--replay LOG` (Checks over a saved capture, no board) and `--seconds N` are additions to the spec.
- Green: `./verify.sh <&-`: `PASS [BOOT] reason=<cause> present ([BOOT] reason=usb at +2.062s)`, `RESULT: PASS (4/4 checks)`, exit 0. `./verify.sh --flash <&-`: `PASS build.sh flash ... (MD5 相符: 5af085eb6016fbcb5958e29dd9ca6990)`, `[BOOT] reason=usb at +2.054s`, `RESULT: PASS (5/5 checks)`, exit 0.
- Red: `./verify.sh --seconds 1` on the board (window closes before the boot marker): `FAIL [BOOT] reason=<cause> present (no [BOOT] reason= marker in 26 captured line(s))`, `RESULT: FAIL (3/4 checks)`, exit 1. `--replay` of a log without the `[BOOT]` line: `RESULT: FAIL (0/1 checks)`, exit 1. Lock held elsewhere: `RESULT: FAIL (0/0 checks)`, exit 1. Importable `esptool` on PYTHONPATH: build and guard Checks FAIL, exit 1.
- `./build.sh test`: twister passed, guard test 7 ok, Harness `Ran 11 tests ... OK`, exit 0.
- Testing call: the Harness Check logic (boot marker, result line) got the unit test the spec names; `verify.py` is glue and is proven on the board. The scratch-image red path from the ticket text is replaced by the shorter capture window and a replayed log, both of which lack `[BOOT]`.
- embedded-review (Standards + Spec, working tree vs dd29e71): no hard violations, no blocking spec gap. Applied: timeouts on every `build.sh` call (build 900 s, guard/identify 60 s, flash 180 s; exit 124 on expiry), `--seconds` must be positive (console.capture treats 0 as no limit), `--flash` with `--replay` refused, replay drops lines before a `stale line(s)` note as the live capture does, flash Check judges `rc` only (no dependence on esptool's localised MD5 text), one shared `checks.is_boot_line` for the capture stop and the Check (unit-tested), lock file closed on the busy path, board-notes evidence bullet dated. Not applied: `step_identify` still re-parses `chip_id` (it adds the value to the Check detail); `--seconds`-style options and the extra build/identify/flash Checks stay as disclosed additions; `stop_when` at `[BOOT]` is for later tickets to widen. Re-ran on the board after the fixes: `--seconds 1` `RESULT: FAIL (3/4 checks)` exit 1; `--flash` `RESULT: PASS (5/5 checks)` exit 0; plain `RESULT: PASS (4/4 checks)` exit 0 (`[BOOT] reason=usb at +2.062s`).
