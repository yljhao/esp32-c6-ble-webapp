# 09: Heartbeat

Spec: `.scratch/ble-webapp/spec.md` (Heartbeat rules, Wire contract). Glossary: Heartbeat. Reference heartbeat module and suite in `~/Desktop/Project/esp32-c6-wifi-vpn-mqtt-exam-2` (counts from a broker session there; here it counts from boot).

**What to build:** `seq` starts at 0 at boot and advances once a second whether or not a Central listens; a missed period is consumed, not queued. While a Central is subscribed the board sends one `{"seq":N,"uptime_ms":N}` line per second over the Shell link, and prints `[HB] seq=N` on the serial console every tenth Heartbeat. The main loop that emits Heartbeats is the one that feeds the watchdog.

**Blocked by:** 07

**Board:** required

**Status:** ready-for-agent

- [ ] The Harness receives 10 s of Heartbeat lines with consecutive `seq` and 1 s ± 200 ms spacing, interleaved correctly with `led` replies sent during that time.
- [ ] After a 5 s disconnect the first `seq` received is about 5 higher than the last one before it.
- [ ] After a reboot `seq` starts again near 0.
- [ ] `[HB] seq=N` appears on the serial console every tenth Heartbeat.
- [ ] Heartbeat host suite (ported and adapted) passes under `./build.sh test`, including encoding at maximum values.
- [ ] Harness Checks for the above.
