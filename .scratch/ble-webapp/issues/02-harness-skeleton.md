# 02: Harness skeleton

Spec: `.scratch/ble-webapp/spec.md` (Harness, Testing Decisions). Reference: the verify tool in `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2`.

**What to build:** The acceptance Harness as an unattended command: it holds the board lock for the whole run, builds, identifies the chip, optionally flashes through the build script's pinned `--chip esp32c6` path, resets and captures the console, runs named Checks, prints PASS/FAIL per Check and a final `RESULT: PASS|FAIL (n/m checks)` line, keeps the capture log under the build directory, never prompts, and exits 0 only on PASS. First Checks: the esptool guard and `[BOOT] reason=` present.

**Blocked by:** 01

**Board:** required

**Status:** ready-for-agent

- [ ] One command runs the whole Harness with stdin closed and prints the per-Check lines and the `RESULT:` line.
- [ ] A `--flash` mode flashes before capturing; without it the running image is checked.
- [ ] The esptool guard is a Check; `[BOOT] reason=` is a Check.
- [ ] Red path proven: a capture missing `[BOOT]` (a replayed or scratch-image capture) gives FAIL on that Check, `RESULT: FAIL`, exit 1.
- [ ] Board-notes card line "Verify" names the command and states that its red path is proven.
