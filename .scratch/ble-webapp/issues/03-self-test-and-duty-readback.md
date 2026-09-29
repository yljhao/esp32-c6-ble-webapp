# 03: Boot Self-test and Duty readback

Spec: `.scratch/ble-webapp/spec.md` (Brightness rules, Boot order, Serial markers). Glossary: User LED, Brightness, Duty readback, Self-test.

**What to build:** At boot the board runs the Self-test (0→255→0 sweep of the User LED with a Duty readback at 0, 128 and 255), reports it, and leaves the User LED at Brightness 128. Every applied Brightness prints its Duty readback. Port the User LED (LEDC PWM on GPIO15, 20 kHz, inverted polarity, overlay as in the reference), Brightness and Duty readback modules from the reference project, and the duty readback host suite.

**Blocked by:** 02

**Board:** required

**Status:** ready-for-agent

- [x] Boot prints `[BOOT] reason=` then `[STAGE] selftest: start` and `[STAGE] selftest: done`, then `[LED] brightness=128 duty=<pct>% freq=<hz>` with the duty within 50 ± 1 % low and the frequency near 20 kHz.
  Evidence: `./verify.sh --flash` capture `build/verify/capture-20260930-041842.log`: `[BOOT] reason=usb` +2.06 s, `[STAGE] selftest: start`, `[STAGE] selftest: done` +3.61 s, `[LED] brightness=128 duty=50.2% freq=19998` +3.62 s (Harness `RESULT: PASS (9/9 checks)`).
- [x] A Self-test failure prints `[STAGE] selftest: fail step=<n>` and the boot continues (shown with a scratch build that breaks the readback, then restored).
  Evidence: scratch build with `PWM_POLARITY_NORMAL` overlay printed `[STAGE] selftest: fail step=1` at +2.06 s, then `[LED] brightness=128 duty=49.9% freq=19998` at +2.08 s (boot continued); Harness `RESULT: FAIL (7/9 checks)`. Production image restored and `RESULT: PASS (9/9 checks)`.
- [x] The duty readback host suite passes under `./build.sh test`.
  Evidence: `./build.sh test`: `18 of 18 executed test cases passed (100.00%)` (twister: smoke, duty_readback, led_pulse), then `esptool guard test: all passed`, `Ran 36 tests ... OK`.
- [x] Harness Checks: Self-test done, `[LED] brightness=128` with duty in tolerance, marker order `[BOOT]` → selftest → `[LED]`. Red path shown.
  Evidence: Harness Checks `[STAGE] selftest: done`, Self-test readbacks, `[LED] brightness=128` in tolerance, marker order (all PASS above); red path is the scratch build (FAIL on selftest done and readbacks, exit 1) plus 36 unit tests including out-of-tolerance and out-of-order cases.
- [x] Board-notes records any Kconfig raised and the observed boot timeline.
  Evidence: `docs/agents/board-notes.md` log sections Configuration raised and why, and Ticket 03 Self-test (timeline).

## Comments

- 2026-09-30 (implementer): no failure was hit three times. Two single-attempt build problems, both fixed at once: (1) the ported overlay was ignored until `rm -rf build` (recorded in board-notes); (2) `THREAD_ANALYZER_AUTO_INTERVAL=2` is below the Kconfig minimum 5 (scratch measurement only).
- Testing calls: `tests/duty_readback` (per Testing Decisions, ported suite) and `tests/led_pulse` (pure arithmetic the readback is judged against; the spec is silent, ported with the module) are host suites; `user_led.c`, `selftest.c`, `brightness.c` and `main.c` are glue proven on the board. Harness Check logic is Python unittest (`tools/verify/test_checks.py`).
- Spec deviation: none. Where the spec is silent: `brightness.c` is a new, smaller module than the reference's (no command parsing, ticket 07 adds it): `brightness_set(n)` applies, waits 2 ms, reads back, prints the `[LED]` marker; `brightness_get()` returns the last applied value. The Harness also checks the Self-test's own readbacks at 0, 128, 255 (0 and 255 constant with no edges), which the ticket did not ask for.
