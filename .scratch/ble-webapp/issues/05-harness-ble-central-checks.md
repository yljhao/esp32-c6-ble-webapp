# 05: Harness BLE Central Check family

Spec: `.scratch/ble-webapp/spec.md` (Harness, Wire contract, Testing Decisions). ADR-0004.

**What to build:** The Harness's ability to act as a Central, as infrastructure only: `bleak` in the project venv; helpers to scan for a board by name and NUS service UUID, connect, subscribe to NUS notifications, write a line, reassemble received notifications into lines, classify lines (Heartbeat JSON, `LED <n>` reply, `ERR ` reply, other) and disconnect; and the pure Check logic used later (Heartbeat `seq` continuity and period tolerance, reply parsing). No board is touched in this ticket.

**Blocked by:** 02

**Board:** none

**Status:** ready-for-agent

- [ ] `bleak` installed in the project venv (not the Zephyr venv) and recorded in its requirements.
- [ ] Python `unittest` covers line reassembly across split notifications, line classification, Heartbeat continuity (consecutive, gap, reboot to a smaller `seq`, period 1 s ± 200 ms) and reply parsing; run by one host test command that also runs from `./build.sh test` or beside it, documented in board-notes.
- [ ] A broken assertion makes that command exit non-zero (red path shown, then restored).
- [ ] No scan, connect or serial access happens during these tests.
