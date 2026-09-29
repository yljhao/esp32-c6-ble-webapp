# 03: Boot Self-test and Duty readback

Spec: `.scratch/ble-webapp/spec.md` (Brightness rules, Boot order, Serial markers). Glossary: User LED, Brightness, Duty readback, Self-test.

**What to build:** At boot the board runs the Self-test (0→255→0 sweep of the User LED with a Duty readback at 0, 128 and 255), reports it, and leaves the User LED at Brightness 128. Every applied Brightness prints its Duty readback. Port the User LED (LEDC PWM on GPIO15, 20 kHz, inverted polarity, overlay as in the reference), Brightness and Duty readback modules from the reference project, and the duty readback host suite.

**Blocked by:** 02

**Board:** required

**Status:** ready-for-agent

- [ ] Boot prints `[BOOT] reason=` then `[STAGE] selftest: start` and `[STAGE] selftest: done`, then `[LED] brightness=128 duty=<pct>% freq=<hz>` with the duty within 50 ± 1 % low and the frequency near 20 kHz.
- [ ] A Self-test failure prints `[STAGE] selftest: fail step=<n>` and the boot continues (shown with a scratch build that breaks the readback, then restored).
- [ ] The duty readback host suite passes under `./build.sh test`.
- [ ] Harness Checks: Self-test done, `[LED] brightness=128` with duty in tolerance, marker order `[BOOT]` → selftest → `[LED]`. Red path shown.
- [ ] Board-notes records any Kconfig raised and the observed boot timeline.
