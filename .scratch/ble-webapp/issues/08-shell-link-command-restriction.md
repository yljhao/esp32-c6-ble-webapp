# 08: Shell link command restriction

Spec: `.scratch/ble-webapp/spec.md` (Shell link command restriction). ADR-0001.

**What to build:** The Shell link offers only the `led` command group and read-only status commands; anything else is refused there, while the serial shell keeps every command. `shell_set_root_cmd()` applies to all instances (unverified: read from the shell header), so the implementer picks a per-instance mechanism and records the choice and its evidence in board-notes.

**Blocked by:** 07

**Board:** required

**Status:** ready-for-agent

- [ ] `kernel reboot` sent over the Shell link is refused with a line starting `ERR ` and the board does not reset (no new `[BOOT]` within 5 s).
- [ ] `kernel reboot` on the serial shell resets the board (`[BOOT] reason=software`).
- [ ] `led set` / `led get` over the Shell link still work.
- [ ] Harness Checks for the refusal and the serial-shell acceptance.
