# 07: Shell link carrying `led set` / `led get`

Spec: `.scratch/ble-webapp/spec.md` (Shell link, Wire contract, Brightness rules). ADR-0001. Glossary: Shell link.

**What to build:** This project's own Zephyr shell transport over NUS, with echo, prompt, colours and VT100 off on that instance, received bytes queued out of the Bluetooth callback, and output split into notifications of at most MTU − 3 bytes. Over it a Central sends `led set <n>` and `led get` and reads `LED <n>` or `ERR ...`. The serial shell keeps working. Brightness survives a disconnect.

**Blocked by:** 06

**Board:** required

**Status:** ready-for-agent

- [ ] `led set 0`, `led set 128`, `led set 255` over the Shell link each reply exactly `LED <n>` and print `[LED] brightness=<n> duty=...` with the Duty readback in tolerance (0 and 255 constant levels, 128 → 50 ± 1 % low).
- [ ] `led set 300`, `led set abc` and `led set` reply a line starting `ERR ` and the Brightness is unchanged (`led get` confirms).
- [ ] Disconnect, reconnect, `led get` returns the value set before the disconnect.
- [ ] Nothing but reply lines arrives on the Shell link (no echo, prompt or escape sequences).
- [ ] The same `led` commands work on the serial shell.
- [ ] Host suites under `./build.sh test`: chunking (MTU 23 and 247, line boundaries, empty output) and LED command parsing (range, non-numeric, missing argument, exact reply strings).
- [ ] Harness Checks for all board behaviour above.
