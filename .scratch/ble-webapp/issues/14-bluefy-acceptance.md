# 14: Bluefy acceptance on the iPhone

Spec: `.scratch/ble-webapp/spec.md` (Human checks remaining).

**What to build:** Nothing new; the user's final acceptance of the Web App in Bluefy on an iPhone against the board in its production state.

**Blocked by:** 13

**Board:** required

**Status:** ready-for-human

- [ ] The implementer puts the board in the production state, keeps a serial capture running, and hands the user this checklist with the Pages URL.
- [ ] User: Bluefy opens the Pages URL and the connect button finds `XIAO-C6-LED`.
- [ ] User: moving the slider visibly dims and brightens the orange User LED; the capture shows the matching `[LED] brightness=` lines.
- [ ] User: the Heartbeat on the page updates about once a second.
- [ ] User: closing and reopening Bluefy (or turning Bluetooth off and on), then reconnecting, shows the Brightness kept.
- [ ] Any Bluefy-specific behaviour (reconnect without chooser, MTU, pairing prompts) is recorded in board-notes.
