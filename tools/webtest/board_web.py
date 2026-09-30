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
# (slider percent, Brightness the board must apply): literals from the spec, 100 % -> 255, 50 % -> 128, 0 % -> 0
SLIDER_STEPS = ((0, 0), (100, 255), (50, 128))

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
                    page.click("#connect")
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

                # -- disconnect leaves the board advertising -------------------------------------------
                mark = cap.mark()
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
                obs["status_log"] = page.evaluate("window.__status")
                obs["stats"] = page.evaluate("window.__stats")
            except Exception as e:
                obs["error"] = f"{type(e).__name__}: {e}"
                _restore_brightness(page, log)
            finally:
                ctx.close()      # inside the driver context, so Chrome is stopped before the profile goes
    except Exception as e:
        obs["error"] = f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return obs
