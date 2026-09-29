# 11: Web App connects, sets Brightness and shows Heartbeats in Chrome

Spec: `.scratch/ble-webapp/spec.md` (Web App, Web App automation, user stories 17–20). ADR-0002 (Chrome needs `--enable-experimental-web-platform-features`, verified), ADR-0004.

**What to build:** The Web App page: a connect button that opens the device chooser filtered on the `XIAO-C6-LED` name prefix with NUS as an optional service; after connecting it shows "connected", sends `led get` and sets its 0–100 % slider from the reply; moving the slider sends `led set`; the latest Heartbeat `seq` and uptime are shown and update. Served locally on `localhost`. A Playwright run launches real Chrome with the flag in a throwaway profile, answers the chooser through CDP `DeviceAccess` (unverified: first time on this PC), and cross-checks the page against the serial console.

**Blocked by:** 09, 10

**Board:** required

**Status:** ready-for-agent

- [ ] Playwright selects `XIAO-C6-LED` through CDP `DeviceAccess` without a human; if this cannot work, stop and report instead of substituting a human step.
- [ ] The page shows connected and the slider shows the board's current Brightness (50 % at Brightness 128).
- [ ] Setting the slider to 50 % prints `[LED] brightness=128` on the serial console; 0 % and 100 % give 0 and 255.
- [ ] The displayed Heartbeat `seq` updates at least twice within 3 s.
- [ ] Board-notes records how the chooser was answered (CDP calls, timing, any Chrome quirk).
