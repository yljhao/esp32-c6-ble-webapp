# 12: Web App disconnect and reconnect

Spec: `.scratch/ble-webapp/spec.md` (user story 21, Web App).

**What to build:** When the Connection drops the Web App shows "disconnected", keeps the last Heartbeat on screen and offers a reconnect button that reconnects through the same device without opening the chooser; after reconnecting it re-syncs the slider with `led get`.

**Blocked by:** 11

**Board:** required

**Status:** ready-for-agent

- [ ] Playwright + Harness: a board reboot (serial shell `kernel reboot`) makes the page show disconnected within 5 s with the last `seq` still shown.
- [ ] The reconnect button reconnects with no chooser prompt, the slider shows 50 % (Brightness 128 after reboot) and Heartbeats resume from a small `seq`.
- [ ] A plain disconnect without reboot (Harness-forced or page-side) followed by reconnect keeps the Brightness set before it.
