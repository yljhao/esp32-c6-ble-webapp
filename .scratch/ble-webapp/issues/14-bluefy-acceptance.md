# 14: Bluefy acceptance on the iPhone

Spec: `.scratch/ble-webapp/spec.md` (Human checks remaining).

**What to build:** Nothing new; the user's final acceptance of the Web App in Bluefy on an iPhone against the board in its production state.

**Blocked by:** 13

**Board:** required

**Status:** done

- [x] The implementer puts the board in the production state, keeps a serial capture running, and hands the user this checklist with the Pages URL.
- [x] User: Bluefy opens the Pages URL and the connect button finds `XIAO-C6-LED`.
- [x] User: moving the slider visibly dims and brightens the orange User LED; the capture shows the matching `[LED] brightness=` lines.
- [x] User: the Heartbeat on the page updates about once a second.
- [ ] User: closing and reopening Bluefy (or turning Bluetooth off and on), then reconnecting, shows the Brightness kept.
- [x] Any Bluefy-specific behaviour (reconnect without chooser, MTU, pairing prompts) is recorded in board-notes.

## Comments

- 2026-09-30 the user reported (in chat, after the unattended run): "驗收完成，Bluefy一次連上就可以看到HB與拖拉PWM Duty改變燈的狀態". Ticked from that report: Bluefy opened the Pages URL and connected on the first try, the Heartbeat was visible, and dragging the slider changed the LED. Not individually reported by the user, so not claimed: the serial capture lines matching the slider moves, and the close/reopen reconnect (that box stays open). No Bluefy-specific setting, pairing prompt or chooser problem was mentioned. The user declared the acceptance complete, so Status is `done`.
