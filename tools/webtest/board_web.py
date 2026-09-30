#!/usr/bin/env python3
"""The Web App in real Google Chrome against the real board (ticket 11; spec: Web App automation).

Launches the installed Chrome (`channel="chrome"`) with `--enable-experimental-web-platform-features`
in a throwaway profile, serves webapp/ on `localhost` (or takes a URL, e.g. the Pages one), answers
the native device chooser through the Chrome DevTools Protocol `DeviceAccess` domain (no human),
then drives the page: connect, read the slider, move it to 0 %, 100 % and 50 %, watch the
Heartbeat, disconnect. The board's serial console is read meanwhile by the caller's capture
(`cap`, tools/verify/verify.py BackgroundCapture); this module only records what the page did and
showed. The decisions (Checks) are in tools/verify/checks.py, run by `./verify.sh --web`.

Nothing here touches the board except through the browser; hold the board lock while it runs.
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "verify"))

import checks  # noqa: E402  (the shared literals of the scenario: WEB_KEPT_PCT, WEB_KEPT_BRIGHTNESS)

KEPT_PCT, KEPT_BRIGHTNESS = checks.WEB_KEPT_PCT, checks.WEB_KEPT_BRIGHTNESS
CHROME_FLAG = "--enable-experimental-web-platform-features"   # ADR-0002
DEVICE_NAME_PREFIX = "XIAO-C6-LED"
CONNECT_ATTEMPTS = 3          # a failed connect is repeated through the same device object (the PC's radio is flaky, board-notes)
CONNECT_WAIT_S = 20.0
SYNC_WAIT_S = 6.0             # slider enabled after `led get` (the page itself gives up after 3 s)
MARKER_WAIT_S = 5.0           # the console shows `[LED]` this long after the slider moved
ECHO_WAIT_S = 2.0             # the page's "board reports" text follows the reply
HB_WATCH_S = 12.5             # after the first Heartbeat: 12 or 13 seq, so one is a multiple of 10 (the console marker)
AFTER_STEPS_MIN_S = 9.5       # at least this long after the last slider step: three 3 s update windows (checks.check_hb_updates_retried)
DISCONNECT_WAIT_S = 5.0
RECONNECT_ATTEMPTS = 6        # Reconnect clicks (same device object, no chooser); a board that is still booting or a flaky radio needs a repeat
RECONNECT_PAUSE_S = 1.0
REBOOT_DROP_WAIT_S = 15.0     # how long to wait for the page to notice the reboot (the Check holds it to 5 s)
FIRST_HB_WAIT_S = 6.0         # a Heartbeat follows a subscribe within this
REBOOT_COMMAND = b"kernel reboot\r\n"  # typed on the serial shell (the Shell link refuses it, ticket 08)
# (slider percent, Brightness the board must apply): literals from the spec, 100 % -> 255, 50 % -> 128, 0 % -> 0
SLIDER_STEPS = ((0, 0), (100, 255), (50, 128))

# Counts requestDevice calls, so "the reconnect opens no chooser" is proven on the page's side too.
_COUNT_REQUESTS_JS = """() => {
  window.__requestDeviceCalls = 0;
  if (navigator.bluetooth) {
    const original = navigator.bluetooth.requestDevice.bind(navigator.bluetooth);
    navigator.bluetooth.requestDevice = (...args) => { window.__requestDeviceCalls++; return original(...args); };
  }
}"""

_OBSERVE_JS = """() => {
  window.__hb = []; window.__status = [];
  const seq = document.getElementById('hb-seq'), up = document.getElementById('hb-uptime');
  const status = document.getElementById('status');
  const opts = { childList: true, characterData: true, subtree: true };
  new MutationObserver(() => {
    const t = seq.textContent;
    if (/^[0-9]+$/.test(t) && (!window.__hb.length || window.__hb[window.__hb.length - 1][1] !== Number(t))) {
      window.__hb.push([Date.now(), Number(t), up.textContent]);
    }
  }).observe(seq, opts);
  new MutationObserver(() => window.__status.push([Date.now(), status.textContent]))
    .observe(status, opts);
  window.__status.push([Date.now(), status.textContent]);
}"""


def wait_console(cap, mark, pred, timeout):
    """Poll the capture's lines since `mark` until pred(lines) is true or `timeout` s; return the lines."""
    deadline = time.monotonic() + timeout
    while True:
        lines = cap.since(mark)
        if pred(lines) or time.monotonic() >= deadline:
            return lines
        time.sleep(0.05)


def _has_led_marker(lines):
    import checks
    return any(checks.parse_led(text) for _, _, text in lines)


def _has_disconnected(lines):
    import checks
    return any(checks.is_ble_disconnected(text) for _, _, text in lines)


def _restore_brightness(page, log):
    """Best effort after an aborted scenario: the board's Brightness goes back to the boot 128 (slider 50 %),
    so a failed run does not leave the User LED at 0 or 255."""
    try:
        if page.get_attribute("#status", "data-state") == "connected":
            page.fill("#slider", "50", timeout=3000)
            time.sleep(0.5)
            log("web: scenario aborted, slider put back to 50 %")
    except Exception:
        pass


class _Chooser:
    """Answers the device chooser through CDP DeviceAccess; records every event."""

    def __init__(self, cdp):
        self.cdp = cdp
        self.events = []           # (monotonic, prompt id, [device names])
        self.selected = None       # {"id", "name", "t"}
        self.select_error = None
        self._done = set()
        cdp.on("DeviceAccess.deviceRequestPrompted", self._on_prompt)
        cdp.send("DeviceAccess.enable")

    def _on_prompt(self, ev):
        self.events.append((time.monotonic(), ev["id"], [d["name"] for d in ev["devices"]]))
        if ev["id"] in self._done:
            return               # the same prompt is announced again whenever its list is refreshed
        for d in ev["devices"]:
            if d["name"].startswith(DEVICE_NAME_PREFIX):
                self._done.add(ev["id"])
                try:
                    self.cdp.send("DeviceAccess.selectPrompt", {"id": ev["id"], "deviceId": d["id"]})
                    self.selected = {"id": d["id"], "name": d["name"], "t": time.monotonic()}
                except Exception as e:      # recorded, the Check reports it
                    self.select_error = f"{type(e).__name__}: {e}"
                return


def _status(page):
    return page.get_attribute("#status", "data-state")


def _reconnect(page, log, tag):
    """Click Reconnect (repeated while the connect fails) until the page shows connected; returns
    (connected, first click wall ms, [attempt records]). Never opens the chooser: the page hides Connect."""
    attempts, first_ms = [], None
    for attempt in range(1, RECONNECT_ATTEMPTS + 1):
        t = time.monotonic()
        first_ms = first_ms or time.time() * 1000
        page.click("#reconnect")
        try:
            page.wait_for_function(
                "['connected','error'].includes(document.getElementById('status').dataset.state)",
                timeout=CONNECT_WAIT_S * 1000)
        except Exception:
            pass
        state, message = _status(page), page.inner_text("#message")
        attempts.append({"state": state, "message": message, "seconds": round(time.monotonic() - t, 2)})
        log(f"web: {tag} reconnect attempt {attempt}: {state} in {time.monotonic() - t:.1f} s {message!r}")
        if state == "connected":
            return True, first_ms, attempts
        time.sleep(RECONNECT_PAUSE_S)
    return False, first_ms, attempts


def _after_reconnect(page, cap, mark, click_ms, chooser, prompts_before, requests_before):
    """What the page shows once it is connected again: the chooser counters, the re-synced slider and the
    first Heartbeat displayed after the click."""
    try:
        page.wait_for_function("!document.getElementById('slider').disabled", timeout=SYNC_WAIT_S * 1000)
    except Exception:
        pass
    deadline = time.monotonic() + FIRST_HB_WAIT_S
    first = None
    while first is None and time.monotonic() < deadline:
        first = next((h for h in page.evaluate("window.__hb") if h[0] >= click_ms), None)
        if first is None:
            time.sleep(0.1)
    time.sleep(0.3)              # the console line of the last reply
    return {"prompts_before": prompts_before, "prompts_after": len(chooser.events),
            "requests_before": requests_before, "requests_after": page.evaluate("window.__requestDeviceCalls"),
            "state": _status(page), "slider_pct": int(page.input_value("#slider")),
            "board_text": page.inner_text("#board-brightness"),
            "first_hb": first, "console_lines": cap.since(mark)}


def _disconnected_view(page):
    """The disconnected page: status text, the Heartbeat left on screen, which buttons are offered."""
    return {"status": page.inner_text("#status"), "seq": page.inner_text("#hb-seq"),
            "uptime": page.inner_text("#hb-uptime"), "note": page.inner_text("#hb-note"),
            "reconnect_visible": page.is_visible("#reconnect"), "connect_visible": page.is_visible("#connect"),
            "disconnect_visible": page.is_visible("#disconnect")}


def drive(url, cap, log=print, hb_watch_s=HB_WATCH_S):
    """Run the whole page scenario at `url`; returns the observation dict for the Checks.
    `cap` is a BackgroundCapture (no reset) of the board's console. Never raises for a page or
    Chrome problem: it is recorded in the observation (`error`)."""
    from playwright.sync_api import sync_playwright

    obs = {"url": url, "error": None, "attempts": [], "steps": [], "page_errors": [], "bluetooth": None,
           "status_log": [], "hb": [], "chooser": None, "select_error": None}
    profile = tempfile.mkdtemp(prefix="c6-chrome-")
    t0 = time.monotonic()
    try:
        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                profile, channel="chrome", headless=True, args=[CHROME_FLAG])
            ctx.set_default_timeout(10000)      # every Playwright call is bounded
            page = ctx.new_page()
            try:
                page.on("pageerror", lambda e: obs["page_errors"].append(f"page error: {e}"))
                page.on("console", lambda m: obs["page_errors"].append(f"console.error: {m.text}")
                        if m.type == "error" else None)
                page.on("requestfailed", lambda r: obs["page_errors"].append(f"request failed: {r.url}"))
                chooser = _Chooser(ctx.new_cdp_session(page))
                page.add_init_script(f"({_COUNT_REQUESTS_JS})()")
                page.goto(url)
                page.evaluate(_OBSERVE_JS)
                obs["bluetooth"] = page.evaluate("'bluetooth' in navigator")
                obs["chrome_version"] = ctx.new_cdp_session(page).send("Browser.getVersion")["product"]
                log(f"web: page loaded, navigator.bluetooth={obs['bluetooth']}")

                # -- connect (the click is the user gesture requestDevice needs) ------------------------
                connected = False
                t_first_click = None
                for attempt in range(1, CONNECT_ATTEMPTS + 1):
                    t_click = time.monotonic()
                    t_first_click = t_first_click or t_click
                    # after the chooser has been answered the page offers Reconnect instead of Connect
                    page.click("#reconnect" if page.is_visible("#reconnect") else "#connect")
                    try:
                        page.wait_for_function(
                            "['connected','error'].includes(document.getElementById('status').dataset.state)",
                            timeout=CONNECT_WAIT_S * 1000)
                    except Exception:
                        pass
                    state = page.get_attribute("#status", "data-state")
                    message = page.inner_text("#message")
                    obs["attempts"].append({"state": state, "message": message,
                                            "seconds": round(time.monotonic() - t_click, 2)})
                    log(f"web: connect attempt {attempt}: {state} in {time.monotonic() - t_click:.1f} s {message!r}")
                    if state == "connected":
                        connected = True
                        obs["t_connected"] = time.monotonic() - t0
                        break
                first_prompt = chooser.events[0][0] if chooser.events else None
                obs["chooser"] = {
                    "events": len(chooser.events),
                    "listed": chooser.events[-1][2] if chooser.events else [],
                    "selected": chooser.selected["name"] if chooser.selected else None,
                }
                obs["select_error"] = chooser.select_error
                if first_prompt is not None:
                    obs["chooser"]["first_prompt_after_click_s"] = round(first_prompt - t_first_click, 2)
                if chooser.selected:
                    obs["chooser"]["selected_after_click_s"] = round(chooser.selected["t"] - t_first_click, 2)
                if connected:
                    obs["chooser"]["connected_after_click_s"] = round(obs["t_connected"] - (t_first_click - t0), 2)
                if not connected:
                    obs["error"] = f"the page never showed connected ({obs['attempts'][-1]})"
                    return obs

                # -- the slider shows the board's Brightness -------------------------------------------
                try:
                    page.wait_for_function("!document.getElementById('slider').disabled", timeout=SYNC_WAIT_S * 1000)
                except Exception:
                    pass
                obs["slider_pct"] = int(page.input_value("#slider"))
                obs["board_text"] = page.inner_text("#board-brightness")
                obs["console_before_steps"] = list(cap.lines)
                log(f"web: slider {obs['slider_pct']} %, board reports {obs['board_text']!r}")

                # -- slider steps: each must show on the console as an applied Brightness ---------------
                for pct, want in SLIDER_STEPS:
                    mark = cap.mark()
                    t_fill = time.monotonic()
                    page.fill("#slider", str(pct), timeout=5000)
                    lines = wait_console(cap, mark, _has_led_marker, MARKER_WAIT_S)
                    time.sleep(0.3)
                    lines = cap.since(mark)
                    try:
                        page.wait_for_function(
                            f"document.getElementById('board-brightness').textContent.startsWith('{want} ')",
                            timeout=ECHO_WAIT_S * 1000)
                    except Exception:
                        pass
                    obs["steps"].append({"pct": pct, "want": want, "lines": lines,
                                         "echo_s": round(time.monotonic() - t_fill - 0.3, 2),
                                         "echo": page.inner_text("#board-brightness"),
                                         "slider_value": page.inner_text("#slider-value")})
                    log(f"web: slider {pct} % -> console {[t for _, _, t in lines if t.startswith('[LED]')]}")
                t_steps_end = time.time() * 1000
                obs["hb_window_start_ms"] = t_steps_end

                # -- watch the Heartbeat -------------------------------------------------------------------
                hb = page.evaluate("window.__hb")
                first_ms = hb[0][0] if hb else t_steps_end
                until = max(first_ms + hb_watch_s * 1000, t_steps_end + AFTER_STEPS_MIN_S * 1000)
                while time.time() * 1000 < until:
                    time.sleep(0.1)
                obs["hb_observed_until_ms"] = time.time() * 1000
                obs["hb"] = page.evaluate("window.__hb")
                obs["uptime_text"] = page.inner_text("#hb-uptime")
                log(f"web: {len(obs['hb'])} Heartbeat display change(s), seq {[h[1] for h in obs['hb']]}")

                # -- a Brightness that is not the boot one, then a page-side disconnect -------------------
                mark_kept = cap.mark()
                t_fill = time.monotonic()
                page.fill("#slider", str(KEPT_PCT), timeout=5000)
                lines = wait_console(cap, mark_kept, _has_led_marker, MARKER_WAIT_S)
                time.sleep(0.3)
                lines = cap.since(mark_kept)
                try:
                    page.wait_for_function(
                        f"document.getElementById('board-brightness').textContent.startsWith('{KEPT_BRIGHTNESS} ')",
                        timeout=ECHO_WAIT_S * 1000)
                except Exception:
                    pass
                obs["steps"].append({"pct": KEPT_PCT, "want": KEPT_BRIGHTNESS, "lines": lines,
                                     "echo_s": round(time.monotonic() - t_fill - 0.3, 2),
                                     "echo": page.inner_text("#board-brightness"),
                                     "slider_value": page.inner_text("#slider-value")})
                log(f"web: slider {KEPT_PCT} % -> console {[t for _, _, t in lines if t.startswith('[LED]')]}")

                # -- disconnect leaves the board advertising -------------------------------------------
                seq_before = page.inner_text("#hb-seq")
                mark = cap.mark()
                click_ms = time.time() * 1000
                page.click("#disconnect")
                try:
                    page.wait_for_function("document.getElementById('status').dataset.state === 'disconnected'",
                                           timeout=DISCONNECT_WAIT_S * 1000)
                except Exception:
                    pass
                obs["status_after_disconnect"] = page.inner_text("#status")
                obs["seq_after_disconnect"] = page.inner_text("#hb-seq")
                obs["disconnect_lines"] = wait_console(cap, mark, _has_disconnected, DISCONNECT_WAIT_S)
                time.sleep(1.2)            # the advertising marker follows the disconnect marker
                obs["disconnect_lines"] = cap.since(mark)
                obs["stats"] = page.evaluate("window.__stats")

                # -- ticket 12, plain disconnect: reconnect through the same device, the Brightness is kept --
                plain = {"trigger_ms": click_ms, "seq_before": seq_before, "view": _disconnected_view(page)}
                obs["plain"] = plain
                prompts_before = len(chooser.events)
                requests_before = page.evaluate("window.__requestDeviceCalls")
                time.sleep(1.0)            # the board advertises again; BlueZ needs a moment
                connected, first_ms, attempts = _reconnect(page, log, "plain")
                plain["attempts"] = attempts
                plain["click_ms"] = first_ms
                if not connected:
                    obs["error"] = f"the plain reconnect never showed connected ({attempts[-1]})"
                    obs["status_log"] = page.evaluate("window.__status")
                    obs["hb_all"] = page.evaluate("window.__hb")
                    return obs
                plain.update(_after_reconnect(page, cap, mark_kept, first_ms, chooser, prompts_before, requests_before))
                log(f"web: plain reconnect: slider {plain['slider_pct']} %, board reports {plain['board_text']!r}, "
                    f"first Heartbeat {plain['first_hb']}, chooser events {plain['prompts_before']}->{plain['prompts_after']}")

                # -- ticket 12, board reboot: disconnected within 5 s, last seq kept, reconnect, boot Brightness --
                time.sleep(3.0)            # a few Heartbeats on screen to keep
                reboot = {"seq_before": page.inner_text("#hb-seq")}
                obs["reboot"] = reboot
                prompts_before = len(chooser.events)
                requests_before = page.evaluate("window.__requestDeviceCalls")
                mark_reboot = cap.mark()
                sent_ms = cap.send(REBOOT_COMMAND)
                reboot["sent_ms"] = sent_ms
                if sent_ms is None:
                    obs["error"] = "could not type `kernel reboot` on the serial shell"
                    obs["hb_all"] = page.evaluate("window.__hb")
                    return obs
                log(f"web: `kernel reboot` typed, page shows seq {reboot['seq_before']}")
                try:
                    page.wait_for_function("document.getElementById('status').dataset.state === 'disconnected'",
                                           timeout=REBOOT_DROP_WAIT_S * 1000)
                except Exception:
                    pass
                reboot["view"] = _disconnected_view(page)
                reboot["status_log"] = page.evaluate("window.__status")
                log(f"web: after the reboot the page shows {reboot['view']}")
                connected, first_ms, attempts = _reconnect(page, log, "reboot")
                reboot["attempts"] = attempts
                reboot["click_ms"] = first_ms
                if not connected:
                    obs["error"] = f"the reconnect after the reboot never showed connected ({attempts[-1]})"
                    obs["status_log"] = page.evaluate("window.__status")
                    obs["hb_all"] = page.evaluate("window.__hb")
                    reboot["console_lines"] = cap.since(mark_reboot)
                    return obs
                reboot.update(_after_reconnect(page, cap, mark_reboot, first_ms, chooser, prompts_before, requests_before))
                log(f"web: reboot reconnect: slider {reboot['slider_pct']} %, board reports {reboot['board_text']!r}, "
                    f"first Heartbeat {reboot['first_hb']}, chooser events {reboot['prompts_before']}->{reboot['prompts_after']}")

                # -- leave the board advertising: a last page-side disconnect ---------------------------------
                mark = cap.mark()
                page.click("#disconnect")
                try:
                    page.wait_for_function("document.getElementById('status').dataset.state === 'disconnected'",
                                           timeout=DISCONNECT_WAIT_S * 1000)
                except Exception:
                    pass
                wait_console(cap, mark, _has_disconnected, DISCONNECT_WAIT_S)
                time.sleep(1.2)
                obs["final_lines"] = cap.since(mark)
                obs["status_log"] = page.evaluate("window.__status")
                obs["hb_all"] = page.evaluate("window.__hb")
                obs["stats"] = page.evaluate("window.__stats")
            except Exception as e:
                obs["error"] = f"{type(e).__name__}: {e}"
                _restore_brightness(page, log)
            finally:
                if obs["error"]:
                    _restore_brightness(page, log)   # an aborted scenario must not leave the User LED at 25 %
                ctx.close()      # inside the driver context, so Chrome is stopped before the profile goes
    except Exception as e:
        obs["error"] = f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return obs
