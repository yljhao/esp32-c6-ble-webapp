# 05: Harness BLE Central Check family

Spec: `.scratch/ble-webapp/spec.md` (Harness, Wire contract, Testing Decisions). ADR-0004.

**What to build:** The Harness's ability to act as a Central, as infrastructure only: `bleak` in the project venv; helpers to scan for a board by name and NUS service UUID, connect, subscribe to NUS notifications, write a line, reassemble received notifications into lines, classify lines (Heartbeat JSON, `LED <n>` reply, `ERR ` reply, other) and disconnect; and the pure Check logic used later (Heartbeat `seq` continuity and period tolerance, reply parsing). No board is touched in this ticket.

**Blocked by:** 02

**Board:** none

**Status:** ready-for-agent

- [x] `bleak` installed in the project venv (not the Zephyr venv) and recorded in its requirements.
  Evidence: `.venv/bin/python -m pip list`: `bleak 3.0.2`, `dbus-fast 5.0.22`; `tools/requirements.txt` has `bleak>=0.22`; `~/zephyrproject/.venv/bin/python -c "import bleak"` gives `ModuleNotFoundError` (Zephyr venv untouched).
- [x] Python `unittest` covers line reassembly across split notifications, line classification, Heartbeat continuity (consecutive, gap, reboot to a smaller `seq`, period 1 s ± 200 ms) and reply parsing; run by one host test command that also runs from `./build.sh test` or beside it, documented in board-notes.
  Evidence: `tools/verify/test_central_logic.py` (66 tests: reassembly across split notifications, classification, reply and Heartbeat parsing, continuity consecutive / gap / reboot to smaller `seq` / uptime going back / repeat, period 1 s +- 200 ms with edges 0.8, 1.2 pass and 0.79, 1.21 fail) run by `./build.sh test-tools`, also the last step of `./build.sh test`: `Ran 132 tests ... OK`, both exit 0. Command documented in board-notes (card Test line, log: Ticket 05 Central logic).
- [x] A broken assertion makes that command exit non-zero (red path shown, then restored).
  Evidence: one expected line changed (`["LED 128"]` to `["LED 129"]`): `./build.sh test-tools` printed `AssertionError: Lists differ: ['LED 128'] != ['LED 129']`, `FAILED (failures=1)`, exit 1; restored: `Ran 131 tests ... OK`, exit 0 (then 132 after one more test).
- [x] No scan, connect or serial access happens during these tests.
  Evidence: `Board: none`; nothing in the run opened `/dev/ttyACM0` or the Bluetooth adapter. `central_logic.py` (all tested code) imports neither `bleak` nor `serial`, proven by `NoHardware.test_logic_module_imports_neither_bleak_nor_serial`; `central.py` imports bleak only inside functions and no test imports it. Its one smoke run used a fake client.

## Comments

- 2026-09-30 (implementer): no failure was hit three times. One single-attempt snag: after the red path a restored test file still failed because a stale `.pyc` (same mtime second, same size) was reused; clearing `tools/verify/__pycache__` fixed it (board-notes, log: Ticket 05).
- Modules and testing calls (all `Testing call:` in the header of `tools/verify/test_central_logic.py`): `central_logic.py` (line reassembly, classification, reply and Heartbeat parsing, continuity, board match, command encoding and MTU chunking) gets host tests as shared contract with the board and the Web App; `central.py` (bleak scan / connect / notify / write) is glue with no unit test, proven by the later Checks that use it.
- Where the spec was silent: (1) a `{` line that does not parse as a Heartbeat, and an `LED`/`ERR` line that does not parse, are class `other`, not a fourth class; `LED <n>` must be canonical decimal 0-255 (no sign, no leading zeros, nothing after), `ERR ` needs the space, the message may be empty. (2) A Heartbeat needs integer `seq` (0..2^32-1) and `uptime_ms` (0..2^64-1), extra keys are ignored. (3) A reboot is `seq` smaller OR `uptime_ms` smaller, so a reboot whose new `seq` already exceeds the old one is still caught. (4) Period is measured between line arrival times on the PC, both edges of 1 s +- 200 ms pass; a `gap` fails `check_heartbeats` (steady state), the reconnect Check will use `step_kind` directly and expect GAP, not REBOOT. (5) `matches_board` is an exact, case-sensitive name match plus the NUS UUID compared case-insensitively. (6) Added `./build.sh test-tools` (Python suites alone) so the host command exists without twister; `./build.sh test` calls it. (7) Write chunks are MTU - 3 bytes, write without response, NUS RX/TX UUIDs from the Nordic NUS specification.
- No firmware file changed, so no board build was needed; twister still passes inside `./build.sh test`.
