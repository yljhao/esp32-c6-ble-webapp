"""Pure Harness logic: Checks over a console capture and the result line.

No I/O, no board, no subprocess: verify.py does the work and hands the
capture (console.capture()'s [(t_rel, wallclock, text), ...]) to these.
A Check returns (ok, detail); results are (name, ok, detail).
"""
import re

BOOT_RE = re.compile(r"^\[BOOT\] reason=([a-z]+)\s*$")
SELFTEST_START = "[STAGE] selftest: start"
SELFTEST_DONE = "[STAGE] selftest: done"
SELFTEST_FAIL_RE = re.compile(r"^\[STAGE\] selftest: fail step=(\d+)\s*$")
LED_RE = re.compile(r"^\[LED\] brightness=(\d+) duty=(\d+(?:\.\d+)?)% freq=(\d+)\s*$")

WDT_ARMED = "[WDT] armed window=5000ms"
BLE_NAME = "XIAO-C6-LED"
BLE_ADVERTISING = f"[BLE] advertising name={BLE_NAME}"
BLE_CONNECTED = "[BLE] connected"
BLE_MTU_RE = re.compile(r"^\[BLE\] mtu=(\d+)\s*$")
BLE_DISCONNECTED_RE = re.compile(r"^\[BLE\] disconnected reason=(0x[0-9a-fA-F]+|\d+)\s*$")
BLE_START_FAILED_RE = re.compile(r"^\[BLE\] (start failed|advertising failed) err=(-?\d+)\s*$")
ROM_BANNER = "ESP-ROM:"
HANG_MARKER = "[DBG] hang: main loop stops feeding"
# The watchdog bites 5 s after the last feed; the main loop feeds once a second, so the
# reset follows the hang command by 4 to 5 s (plus the ROM start). Anything faster means the
# hang did not stop the feeding; anything slower than the limit means the bite is late.
BITE_MIN_S = 2.0

# Duty readback tolerances (spec: Testing Decisions; reference tolerance).
# The User LED is active-low, so the pad is low for the time the LED is on:
# Brightness 0 reads 0.0 % low, 255 reads 100.0 % low, both with no edges.
MID_DUTY_LOW, MID_DUTY_HIGH = 49.0, 51.0      # Brightness 128: 50 +- 1 % low
# Ticket 12: the Brightness the Web App scenario sets before its plain disconnect, a level other than the boot 128.
# Spec rule round(pct * 255 / 100): slider 25 % -> 64. Read by board_web.py (the slider step) and verify.py.
WEB_KEPT_PCT, WEB_KEPT_BRIGHTNESS = 25, 64
QUARTER_DUTY_LOW, QUARTER_DUTY_HIGH = 24.1, 26.1   # Brightness 64: 64 * 100 / 255 = 25.1 % low, +- 1 %
CONST_DUTY_TOL = 1.0                          # 0 and 255: constant level, +- 1 %
PWM_FREQ_LOW, PWM_FREQ_HIGH = 19000, 21000    # "near 20 kHz": +- 5 %


def is_boot_line(text):
    """True for a line the boot Check accepts; the capture stops on the same test."""
    return BOOT_RE.match(text) is not None


def check_boot_marker(lines):
    """`[BOOT] reason=<cause>` present on a line of its own."""
    for t, _, text in lines:
        if is_boot_line(text):
            return True, f"{text.strip()} at +{t:.3f}s"
    return False, f"no [BOOT] reason= marker in {len(lines)} captured line(s)"


def parse_led(text):
    """`[LED] brightness=<n> duty=<pct>% freq=<hz>` -> (n, pct, hz), else None."""
    m = LED_RE.match(text)
    if not m:
        return None
    return int(m.group(1)), float(m.group(2)), int(m.group(3))


def _first(lines, pred, start=0):
    """Index of the first line at or after `start` whose text satisfies pred, else None."""
    for i in range(start, len(lines)):
        if pred(lines[i][2]):
            return i
    return None


def _is_selftest_end(text):
    return text.strip() == SELFTEST_DONE or SELFTEST_FAIL_RE.match(text) is not None


def _is_start(text):
    return text.strip() == SELFTEST_START


def _led_ok(brightness, duty, freq):
    """Is a Duty readback in tolerance for this Brightness (see the constants above)?"""
    if brightness == 0:
        return abs(duty - 0.0) <= CONST_DUTY_TOL and freq == 0
    if brightness == 255:
        return abs(duty - 100.0) <= CONST_DUTY_TOL and freq == 0
    if brightness == 128:
        return MID_DUTY_LOW <= duty <= MID_DUTY_HIGH and PWM_FREQ_LOW <= freq <= PWM_FREQ_HIGH
    if brightness == WEB_KEPT_BRIGHTNESS:
        return QUARTER_DUTY_LOW <= duty <= QUARTER_DUTY_HIGH and PWM_FREQ_LOW <= freq <= PWM_FREQ_HIGH
    return False


def check_selftest_done(lines):
    """`[STAGE] selftest: start` followed by `[STAGE] selftest: done` (a fail marker fails the Check)."""
    i = _first(lines, _is_start)
    if i is None:
        return False, "no [STAGE] selftest: start marker"
    j = _first(lines, _is_selftest_end, i + 1)
    if j is None:
        return False, "no [STAGE] selftest: done after start"
    text = lines[j][2].strip()
    if text != SELFTEST_DONE:
        return False, text
    return True, f"{text} at +{lines[j][0]:.3f}s"


def check_selftest_readbacks(lines):
    """The Self-test's Duty readbacks at 0, 128, 255, in that order, each in tolerance."""
    i = _first(lines, _is_start)
    if i is None:
        return False, "no [STAGE] selftest: start marker"
    j = _first(lines, _is_selftest_end, i + 1)
    if j is None:
        return False, "no selftest end marker"
    seen = {}
    order = []
    for t, _, text in lines[i + 1:j]:
        led = parse_led(text)
        if led and led[0] in (0, 128, 255) and led[0] not in seen:
            seen[led[0]] = led
            order.append(led[0])
    for want in (0, 128, 255):
        if want not in seen:
            return False, f"no readback at brightness {want} inside the Self-test"
    if order != [0, 128, 255]:
        return False, f"readbacks out of order: {order}"
    for want in (0, 128, 255):
        b, duty, freq = seen[want]
        if not _led_ok(b, duty, freq):
            return False, f"brightness={b} duty={duty}% freq={freq} out of tolerance"
    return True, ", ".join(f"{b}:{d}%/{f}Hz" for b, d, f in (seen[k] for k in (0, 128, 255)))


def _boot_led(lines):
    """Index and value of the first `[LED] brightness=128` line after the Self-test ended, else None."""
    i = _first(lines, _is_start)
    j = _first(lines, _is_selftest_end, i + 1) if i is not None else None
    if j is None:
        return None
    for k in range(j + 1, len(lines)):
        led = parse_led(lines[k][2])
        if led and led[0] == 128:
            return k, led
    return None


def check_led_applied(lines, brightness):
    """A Brightness applied over a link shows on the console as `[LED] brightness=<n> duty=..`
    in tolerance (0 and 255 constant, 128 at 50 +- 1 % low, 64 at 25 +- 1 % low). Only those four levels
    have a tolerance defined; any other is refused rather than passed unchecked."""
    if brightness not in (0, WEB_KEPT_BRIGHTNESS, 128, 255):
        return False, f"no tolerance defined for brightness={brightness}"
    for t, _, text in lines:
        led = parse_led(text)
        if led and led[0] == brightness:
            _, duty, freq = led
            detail = f"[LED] brightness={brightness} duty={duty}% freq={freq} at +{t:.3f}s"
            if not _led_ok(brightness, duty, freq):
                return False, detail + " out of tolerance"
            return True, detail
    return False, f"no [LED] brightness={brightness} marker in {len(lines)} captured line(s)"


def check_no_led_marker(lines):
    """No `[LED] brightness=` marker: a rejected command applied nothing."""
    for t, _, text in lines:
        if parse_led(text):
            return False, f"'{text.strip()}' at +{t:.3f}s after a rejected command"
    return True, f"no [LED] marker in {len(lines)} captured line(s)"


_REPLY_RE = re.compile(r"^(LED \d+|ERR .*)$")


def check_serial_led_replies(lines, want):
    """`led` commands typed on the serial shell. `want` lists the reply lines expected, in order:
    `LED <n>` exactly, or `ERR` for any line starting `ERR `. The shell echoes each command behind
    its prompt, so only lines that ARE a reply count (a line starting `LED ` or `ERR `)."""
    got = [text.strip() for _, _, text in lines if _REPLY_RE.match(text.strip())]
    if len(got) < len(want):
        return False, f"{len(got)} reply line(s) {got}, expected {len(want)} replies {want}"
    for i, (g, w) in enumerate(zip(got, want)):
        if not (g.startswith("ERR ") if w == "ERR" else g == w):
            return False, f"reply {i + 1} is '{g}', expected '{w}'"
    return True, f"{len(want)} replies: {got[:len(want)]}"


def check_boot_brightness(lines):
    """After the Self-test the boot leaves Brightness 128: `[LED] brightness=128` with duty
    50 +- 1 % low and the frequency near 20 kHz."""
    found = _boot_led(lines)
    if found is None:
        return False, "no [LED] brightness=128 marker after the Self-test"
    k, (b, duty, freq) = found
    detail = f"[LED] brightness={b} duty={duty}% freq={freq} at +{lines[k][0]:.3f}s"
    if not _led_ok(b, duty, freq):
        return False, detail + " out of tolerance"
    return True, detail


def _is_wdt_armed(text):
    return text.strip() == WDT_ARMED


def check_wdt_armed(lines):
    """`[WDT] armed window=5000ms` after the Self-test ended (done or fail)."""
    i = _first(lines, _is_start)
    j = _first(lines, _is_selftest_end, i + 1) if i is not None else None
    if j is None:
        return False, "no Self-test end marker to order the watchdog after"
    k = _first(lines, _is_wdt_armed)
    if k is None:
        return False, f"no {WDT_ARMED} marker"
    if k < j:
        return False, f"{WDT_ARMED} printed before the Self-test ended (must come after)"
    return True, f"{WDT_ARMED} at +{lines[k][0]:.3f}s"


def _is_ble_advertising(text):
    return text.strip() == BLE_ADVERTISING


def _is_ble_connected(text):
    return text.strip() == BLE_CONNECTED


def _is_ble_disconnected(text):
    return text.startswith("[BLE] disconnected")


def check_ble_advertising(lines):
    """`[BLE] advertising name=XIAO-C6-LED` after the watchdog was armed (boot order)."""
    w = _first(lines, _is_wdt_armed)
    if w is None:
        return False, f"no {WDT_ARMED} marker to order Bluetooth after"
    k = _first(lines, _is_ble_advertising, w + 1)
    if k is not None:
        return True, f"{BLE_ADVERTISING} at +{lines[k][0]:.3f}s"
    for t, _, text in lines[w + 1:]:
        m = BLE_START_FAILED_RE.match(text)
        if m:
            return False, f"{text.strip()} at +{t:.3f}s"
    if _first(lines, _is_ble_advertising) is not None:
        return False, f"{BLE_ADVERTISING} printed before {WDT_ARMED} (must come after)"
    return False, f"no {BLE_ADVERTISING} marker after {WDT_ARMED}"


def _last_mtu_after(lines, start):
    """(index, value) of the last `[BLE] mtu=<n>` line after `start`, else None."""
    found = None
    for i in range(start + 1, len(lines)):
        m = BLE_MTU_RE.match(lines[i][2])
        if m:
            found = (i, int(m.group(1)))
    return found


def check_ble_connected(lines, expected_mtu):
    """`[BLE] connected`, then `[BLE] mtu=<n>` with n == expected_mtu. The stack also reports
    the default 23 when it creates the connection; the last MTU after `connected` is the
    negotiated one."""
    c = _first(lines, _is_ble_connected)
    if c is None:
        return False, f"no {BLE_CONNECTED} marker in {len(lines)} captured line(s)"
    mtu = _last_mtu_after(lines, c)
    if mtu is None:
        return False, f"{BLE_CONNECTED} at +{lines[c][0]:.3f}s but no [BLE] mtu= marker after it"
    i, n = mtu
    if n != expected_mtu:
        return False, f"[BLE] mtu={n} after {BLE_CONNECTED}, expected mtu={expected_mtu}"
    return True, f"{BLE_CONNECTED} at +{lines[c][0]:.3f}s, [BLE] mtu={n} at +{lines[i][0]:.3f}s"


def check_ble_silent_while_connected(lines):
    """No `[BLE] advertising` marker between `[BLE] connected` and the next `[BLE] disconnected`:
    the board does not advertise while a Connection exists."""
    c = _first(lines, _is_ble_connected)
    if c is None:
        return False, f"no {BLE_CONNECTED} marker"
    d = _first(lines, _is_ble_disconnected, c + 1)
    if d is None:
        return False, "no [BLE] disconnected marker after connected, cannot bound the Connection"
    for t, _, text in lines[c + 1:d]:
        if text.startswith("[BLE] advertising"):
            return False, f"'{text.strip()}' at +{t:.3f}s while the Connection existed"
    return True, f"no advertising marker in the {lines[d][0] - lines[c][0]:.1f}s of the Connection"


BLE_ADVERTISE_AGAIN_S = 1.0   # spec: advertises again "as soon as" a Connection ends


def check_ble_disconnected(lines, expected_reason, max_delay_s=BLE_ADVERTISE_AGAIN_S):
    """`[BLE] disconnected reason=<r>` (r == expected_reason unless it is None), then
    `[BLE] advertising name=XIAO-C6-LED` again after it, within `max_delay_s`."""
    d = _first(lines, _is_ble_disconnected)
    if d is None:
        return False, "no [BLE] disconnected marker"
    m = BLE_DISCONNECTED_RE.match(lines[d][2])
    if not m:
        return False, f"unparsable marker '{lines[d][2].strip()}'"
    reason = int(m.group(1), 0)
    if expected_reason is not None and reason != expected_reason:
        return False, f"{lines[d][2].strip()}, expected reason=0x{expected_reason:02x}"
    a = _first(lines, _is_ble_advertising, d + 1)
    if a is None:
        return False, f"{lines[d][2].strip()} but no {BLE_ADVERTISING} marker after it"
    delay = lines[a][0] - lines[d][0]
    if delay > max_delay_s:
        return False, (f"{lines[d][2].strip()} but advertising again only {delay:.3f}s later, "
                       f"limit {max_delay_s:g}s")
    return True, (f"reason=0x{reason:02x} at +{lines[d][0]:.3f}s, advertising again at "
                  f"+{lines[a][0]:.3f}s ({lines[a][0] - lines[d][0]:.3f}s later)")


def check_idle_no_bite(lines, min_s, observed_s=None):
    """No reset in at least `min_s` seconds after the watchdog was armed. A reset shows as a
    ROM banner or a second `[BOOT] reason=` line after the armed marker. `observed_s` is how
    long the capture ran (default: the time of its last line)."""
    k = _first(lines, _is_wdt_armed)
    if k is None:
        return False, f"no {WDT_ARMED} marker, cannot judge the idle run"
    t_armed = lines[k][0]
    for t, _, text in lines[k + 1:]:
        if text.startswith(ROM_BANNER) or is_boot_line(text):
            return False, f"board reset at +{t:.1f}s ({text.strip()}), {t - t_armed:.1f}s after arming"
    end = observed_s if observed_s is not None else (lines[-1][0] if lines else 0.0)
    span = end - t_armed
    if span < min_s:
        return False, f"observed {span:.1f}s after arming, need {min_s:.0f}s"
    return True, f"no reset in {span:.1f}s after arming"


def check_wdt_bite(lines, max_s):
    """After the debug hang marker: a reset (ROM banner) BITE_MIN_S..max_s later, then
    `[BOOT] reason=watchdog`."""
    h = _first(lines, lambda t: t.strip() == HANG_MARKER)
    if h is None:
        return False, f"no '{HANG_MARKER}' marker (was the hang command accepted?)"
    r = _first(lines, lambda t: t.startswith(ROM_BANNER), h + 1)
    if r is None:
        return False, f"no reset after the hang marker within the capture"
    dt = lines[r][0] - lines[h][0]
    if dt > max_s:
        return False, f"reset {dt:.1f}s after the hang, limit {max_s:.0f}s"
    if dt < BITE_MIN_S:
        return False, f"reset {dt:.1f}s after the hang, too soon for the watchdog"
    b = _first(lines, is_boot_line, r + 1)
    if b is None:
        return False, f"reset {dt:.1f}s after the hang, but no [BOOT] reason= marker followed"
    text = lines[b][2].strip()
    if text != "[BOOT] reason=watchdog":
        return False, f"reset {dt:.1f}s after the hang, but {text}"
    return True, f"reset {dt:.1f}s after the hang, then {text}"


HANG_TEXTS = (b"Stop the main loop feeding the watchdog", HANG_MARKER.encode())


def check_no_hang_command(config_text, image):
    """The production build carries no hang command: CONFIG_C6_HANG_CMD is not set in its
    .config and none of the command's strings is in the image."""
    if not image:
        return False, "image is empty"
    if re.search(r"^CONFIG_C6_HANG_CMD=y", config_text, re.M):
        return False, "CONFIG_C6_HANG_CMD=y in the build's .config"
    for text in HANG_TEXTS:
        if text in image:
            return False, f"'{text.decode()}' found in the image"
    return True, f"CONFIG_C6_HANG_CMD not set, no hang text in {len(image)} image bytes"


def check_hang_refused(lines, window_s, observed_s=None):
    """After typing `debug hang` to the production image, for `window_s` seconds: no hang
    marker and no reset."""
    for t, _, text in lines:
        if text.strip() == HANG_MARKER:
            return False, f"hang accepted at +{t:.1f}s"
        if text.startswith(ROM_BANNER):
            return False, f"board reset at +{t:.1f}s"
    end = observed_s if observed_s is not None else (lines[-1][0] if lines else 0.0)
    if end < window_s:
        return False, f"observed {end:.1f}s, need {window_s:.0f}s"
    return True, f"hang command not accepted, no reset in {end:.1f}s"


def check_no_reboot(lines, window_s, observed_s=None):
    """Nothing reset the board while a command was refused: no `[BOOT]` marker and no ROM banner in
    `lines`, and the capture covered `window_s` seconds (`observed_s`, measured by the caller: a
    quiet board prints nothing, so the lines cannot tell how long the capture ran)."""
    for t, _, text in lines:
        if is_boot_line(text):
            return False, f"'{text.strip()}' at +{t:.1f}s"
        if text.startswith(ROM_BANNER):
            return False, f"board reset (ROM banner) at +{t:.1f}s"
    end = observed_s if observed_s is not None else (lines[-1][0] if lines else 0.0)
    if end < window_s:
        return False, f"observed {end:.1f}s, need {window_s:.0f}s"
    return True, f"no [BOOT] marker and no reset in {end:.1f}s"


def check_boot_reason(lines, reason):
    """The first `[BOOT] reason=<cause>` in `lines` carries `reason`."""
    for t, _, text in lines:
        m = BOOT_RE.match(text)
        if m:
            if m.group(1) == reason:
                return True, f"{text.strip()} at +{t:.3f}s"
            return False, f"'{text.strip()}', expected reason={reason}"
    return False, f"no [BOOT] reason= marker in {len(lines)} captured line(s)"


def check_marker_order(lines):
    """[BOOT] reason= -> [STAGE] selftest: start -> selftest end -> [LED] brightness=128 -> [WDT] armed
    -> [BLE] advertising."""
    steps = [("[BOOT] reason=", is_boot_line), ("[STAGE] selftest: start", _is_start),
             ("[STAGE] selftest: done|fail", _is_selftest_end),
             ("[LED] brightness=128", lambda t: (parse_led(t) or (None,))[0] == 128),
             (WDT_ARMED, _is_wdt_armed), (BLE_ADVERTISING, _is_ble_advertising)]
    at = -1
    for name, pred in steps:
        i = _first(lines, pred, at + 1)
        if i is None:
            return False, f"{name} missing or out of order"
        at = i
    return True, " -> ".join(n for n, _ in steps)


class BootCaptureDone:
    """Capture stop predicate: the boot is complete once `[BLE] advertising name=...` follows
    `[WDT] armed window=5000ms`, which follows the Self-test's end marker (done or fail); the
    boot's `[LED] brightness=128` precedes them."""

    def __init__(self):
        self.ended = False
        self.armed = False

    def __call__(self, text):
        if _is_selftest_end(text):
            self.ended = True
            return False
        if self.ended and _is_wdt_armed(text):
            self.armed = True
            return False
        return self.armed and _is_ble_advertising(text)


def format_check(name, ok, detail=""):
    return f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else "")


def format_result(results):
    passed = sum(1 for r in results if r[1])
    ok = bool(results) and passed == len(results)
    return f"RESULT: {'PASS' if ok else 'FAIL'} ({passed}/{len(results)} checks)"


def exit_code(results):
    return 0 if results and all(r[1] for r in results) else 1


# -- Heartbeat marker on the serial console (ticket 09) ------------------------------------------
HB_MARKER_RE = re.compile(r"^\[HB\] seq=(\d+)\s*$")
HB_STALLED_RE = re.compile(r"^\[HB\] link stalled: (\d+) stale heartbeat\(s\) dropped\s*$")
HB_MARKER_EVERY = 10
STALL_MARKER = "[DBG] stall: heartbeat sender stops"


def parse_hb_marker(text):
    """`[HB] seq=<n>` -> n, else None."""
    m = HB_MARKER_RE.match(text)
    return int(m.group(1)) if m else None


def check_hb_markers(lines, received_seqs=(), min_markers=2):
    """`[HB] seq=N` on the console for every tenth Heartbeat: at least `min_markers`, each N a
    multiple of 10, consecutive markers exactly 10 apart (a reboot inside `lines` breaks that, so
    pass a window without one). Every tenth seq the Central received inside the marker range must
    also have its marker, and at least one such seq must exist, so the console and the Shell link
    are shown to be the same counter."""
    seqs = [n for n in (parse_hb_marker(text) for _, _, text in lines) if n is not None]
    if len(seqs) < min_markers:
        return False, f"{len(seqs)} [HB] marker(s), need at least {min_markers}"
    for n in seqs:
        if n % HB_MARKER_EVERY:
            return False, f"[HB] seq={n} is not a multiple of {HB_MARKER_EVERY}"
    for a, b in zip(seqs, seqs[1:]):
        if b - a != HB_MARKER_EVERY:
            return False, f"[HB] seq={a} followed by seq={b}, not {HB_MARKER_EVERY} apart"
    tenths = sorted({n for n in received_seqs if n % HB_MARKER_EVERY == 0 and seqs[0] <= n <= seqs[-1]})
    missing = [n for n in tenths if n not in seqs]
    if missing:
        return False, f"Central received seq {missing} but the console has no [HB] marker for it"
    if received_seqs and not tenths:
        return False, "no tenth seq received inside the marker range, cannot compare with the Shell link"
    return True, (f"{len(seqs)} markers, seq {seqs[0]}..{seqs[-1]} every {HB_MARKER_EVERY}"
                  + (f", matched Shell link seq {tenths}" if tenths else ""))


def check_stall_survived(lines, min_s, min_markers=2):
    """Debug image, after `debug stall`: the sender-stopped marker, then for at least `min_s`
    seconds no reset (no ROM banner, no [BOOT]), `[HB] seq=N` markers still coming (the main loop
    runs on), and the stale Heartbeats dropped and reported."""
    k = _first(lines, lambda t: t.strip() == STALL_MARKER)
    if k is None:
        return False, f"no '{STALL_MARKER}' marker (was the stall command accepted, was a Heartbeat posted?)"
    t0 = lines[k][0]
    for t, _, text in lines[k + 1:]:
        if text.startswith(ROM_BANNER) or is_boot_line(text):
            return False, f"board reset at +{t - t0:.1f}s after the stall ({text.strip()})"
    end = lines[-1][0] - t0
    if end < min_s:
        return False, f"observed {end:.1f}s after the stall, need {min_s:g}s"
    after = lines[k + 1:]
    markers = [n for n in (parse_hb_marker(text) for _, _, text in after) if n is not None]
    if len(markers) < min_markers:
        return False, f"{len(markers)} [HB] marker(s) in {end:.1f}s after the stall, need {min_markers}"
    dropped = [int(m.group(1)) for m in (HB_STALLED_RE.match(text) for _, _, text in after) if m]
    if not dropped:
        return False, "no '[HB] link stalled: ... dropped' report, the bounded drop policy did not run"
    return True, (f"no reset in {end:.1f}s after the stall, {len(markers)} [HB] markers "
                  f"(seq {markers[0]}..{markers[-1]}), {dropped[-1]} stale heartbeat(s) reported dropped")


# -- Web App in Chrome against the board (ticket 11) ------------------------------------------------
WEB_UPDATE_WINDOW_S = 3.0    # spec: the displayed seq updates at least twice within 3 s
WEB_MIN_UPDATES = 2
WEB_MAX_SKEW_S = 1.5         # page and console see one Heartbeat this close in PC time (the connection interval is 45 ms)


def check_hb_updates(changes, start_ms, window_s=WEB_UPDATE_WINDOW_S, min_updates=WEB_MIN_UPDATES,
                     observed_until_ms=None):
    """The Heartbeat `seq` the page displays changes at least `min_updates` times in the `window_s`
    seconds after `start_ms`. `changes` is the page's display log [(wall_ms, seq), ...], oldest first
    (an entry per change of the displayed text); a repeated seq is not an update. `observed_until_ms`
    is when the observation ended (default: the last change): a window it does not cover cannot be judged."""
    end = start_ms + window_s * 1000
    observed = changes[-1][0] if observed_until_ms is None and changes else observed_until_ms
    if observed is None or observed < end:
        return False, f"the observation ended before the {window_s:g} s window did"
    updates, previous = [], None
    for ms, seq in changes:
        if start_ms < ms <= end and seq != previous:
            updates.append((ms - start_ms, seq))
        previous = seq
    detail = (f"{len(updates)} update(s) in {window_s:g} s: "
              + ", ".join(f"seq {n} at +{ms / 1000:.2f}s" for ms, n in updates))
    return len(updates) >= min_updates, detail


def check_page_matches_console(changes, lines, max_skew_s=WEB_MAX_SKEW_S):
    """The page shows the same Heartbeats the console counts: its displayed seq never goes backwards,
    and for at least one `[HB] seq=N` marker (every tenth) the page showed N within `max_skew_s` of the
    marker's wall-clock time; every such match must be within the skew. `changes` are [(wall_ms, seq)],
    `lines` the console capture (t_rel, wallclock datetime, text). A marker the page never showed is
    tolerated (the PC's radio can lose a notification's timing, not its number, but a page may join late)."""
    if not changes:
        return False, "the page displayed no Heartbeat"
    for (_, a), (_, b) in zip(changes, changes[1:]):
        if b < a:
            return False, f"the page's seq went backwards: {a} then {b}"
    shown = {}
    for ms, seq in changes:
        shown.setdefault(seq, ms)
    matches = []
    for _, wall, text in lines:
        n = parse_hb_marker(text)
        if n is None or n not in shown or wall is None:
            continue
        skew = abs(shown[n] - wall.timestamp() * 1000) / 1000
        matches.append((n, skew))
    if not matches:
        return False, (f"no [HB] marker on the console for a seq the page showed "
                       f"({changes[0][1]}..{changes[-1][1]})")
    worst = max(matches, key=lambda m: m[1])
    detail = ", ".join(f"seq {n} skew {s:.2f}s" for n, s in matches)
    if worst[1] > max_skew_s:
        return False, f"{detail}; seq {worst[0]} is more than {max_skew_s:g}s apart"
    return True, detail


def check_slider_shows_board(slider_pct, board_text, lines, expect_brightness=None):
    """After connecting, the slider shows the Brightness the console last reported (`[LED] brightness=<n>`)
    as round(n * 100 / 255) %, and the page's own "board reports" text starts with that n. With
    `expect_brightness` (the boot's 128 after a reset) the console's own value must be that too."""
    last = None
    for _, _, text in lines:
        led = parse_led(text)
        if led:
            last = led[0]
    if last is None:
        return False, "no [LED] brightness= marker on the console, the board's Brightness is unknown"
    if expect_brightness is not None and last != expect_brightness:
        return False, f"console brightness={last}, expected {expect_brightness}: the board was not in the state the scenario assumes"
    want = int(last * 100 / 255 + 0.5)
    detail = f"console brightness={last}, slider {slider_pct} % (want {want} %), page text '{board_text}'"
    ok = slider_pct == want and board_text.split(" ")[0] == str(last)
    return ok, detail


def is_ble_disconnected(text):
    """`[BLE] disconnected reason=<r>` marker (any reason)."""
    return _is_ble_disconnected(text)


def is_ble_link_lost(text):
    """`[BLE] disconnected reason=<r>` with r other than 0x13 (the Central asked): the link was lost."""
    m = BLE_DISCONNECTED_RE.match(text)
    return bool(m) and int(m.group(1), 0) != 0x13


WEB_UPDATE_WINDOWS = 3       # windows tried when the page's display was late but the board's spacing was exact
WEB_UPTIME_TOL_MS = 50       # the board's uptime_ms step is exactly 1000 ms; allow rounding
_UPTIME_TEXT_RE = re.compile(r"^(\d+):(\d\d):(\d\d)\.(\d{3})$")


def _uptime_ms(text):
    m = _UPTIME_TEXT_RE.match(text)
    if not m:
        return None
    h, mi, s, ms = (int(g) for g in m.groups())
    return ((h * 60 + mi) * 60 + s) * 1000 + ms


def check_hb_updates_retried(hb, start_ms, observed_until_ms, window_s=WEB_UPDATE_WINDOW_S,
                             windows=WEB_UPDATE_WINDOWS):
    """check_hb_updates over up to `windows` consecutive windows, the first that passes wins. A later
    window is credited (reported as link jitter) only if the board's own spacing, read from the uptime
    the page displays, is 1000 ms per seq step throughout: the board kept its period, the link was late.
    `hb` is the page's display log [(wall_ms, seq, 'h:mm:ss.mmm'), ...]."""
    changes = [(ms, seq) for ms, seq, _ in hb]
    seen = []
    for k in range(windows):
        start = start_ms + k * window_s * 1000
        if start + window_s * 1000 > observed_until_ms:
            seen.append(f"window {k + 1} not observed")
            break
        ok, detail = check_hb_updates(changes, start, window_s, observed_until_ms=observed_until_ms)
        if ok and k == 0:
            return True, f"window 1: {detail}"
        if ok:
            bad = board_spacing_error(hb)
            if bad:
                return False, f"window {k + 1} passed but the board's uptime is not exact: {bad}"
            return True, f"window {k + 1} (link jitter in window(s) before: {'; '.join(seen)}): {detail}"
        seen.append(f"window {k + 1}: {detail}")
    return False, "; ".join(seen)


def board_spacing_error(hb, tol_ms=WEB_UPTIME_TOL_MS):
    """None when every pair of displayed Heartbeats is 1000 ms of board uptime per seq step, else a description."""
    for (_, a, ta), (_, b, tb) in zip(hb, hb[1:]):
        ua, ub = _uptime_ms(ta), _uptime_ms(tb)
        if ua is None or ub is None:
            return f"unreadable uptime '{ta}' / '{tb}'"
        if abs((ub - ua) - 1000 * (b - a)) > tol_ms:
            return f"seq {a}->{b} uptime {ta}->{tb}"
    return None


# -- Web App disconnect and reconnect (ticket 12) ---------------------------------------------------
WEB_DISCONNECT_SHOWN_S = 5.0     # spec: after a board reboot the page shows disconnected within 5 s
WEB_RESUME_MAX_SEQ = 15          # "a small seq" after a reboot: the counter starts ~3.7 s after the reset (ticket 09)
                                 # and the page needs the reconnect on top; a counter that kept running is far higher


def seq_shown_at(hb_log, ms):
    """The Heartbeat seq the page displayed at wall-clock `ms`: the last change of its display at or before
    that time (`hb_log` is [(wall_ms, seq, uptime), ...], oldest first), else None."""
    shown = None
    for t, seq, _ in hb_log:
        if t <= ms:
            shown = seq
    return shown


def check_disconnect_shown(status_log, since_ms, hb_log, seq_shown, limit_s=WEB_DISCONNECT_SHOWN_S):
    """The page's status text became `disconnected` within `limit_s` seconds after `since_ms` (the moment the
    reboot command was typed, or the Disconnect click), and the Heartbeat seq still on screen afterwards
    (`seq_shown`, read from the page) is the one it displayed when it said disconnected, not cleared.
    `status_log` is the page's status log [(wall_ms, text), ...], `hb_log` its Heartbeat display log."""
    for ms, text in status_log:
        if ms >= since_ms and text == "disconnected":
            delay = (ms - since_ms) / 1000
            last = seq_shown_at(hb_log, ms)
            if last is None:
                return False, f"no Heartbeat was on screen when the page said disconnected, so there is nothing to keep"
            if delay > limit_s:
                return False, f"the page said disconnected {delay:.1f} s after the trigger, limit {limit_s:g} s"
            if seq_shown != str(last):
                return False, (f"disconnected after {delay:.1f} s, but the seq on screen is {seq_shown!r}, "
                               f"not the last one, {last}")
            return True, (f"disconnected {delay:.1f} s after the trigger (limit {limit_s:g} s), "
                          f"last Heartbeat seq {last} kept on screen")
    return False, f"the page never said disconnected after the trigger (status log {[t for _, t in status_log]})"


def check_reconnect_no_chooser(prompts_before, prompts_after, requests_before, requests_after, state_after):
    """Reconnecting went through the device the page already holds: the chooser was not prompted again
    (CDP DeviceAccess prompt events) and `navigator.bluetooth.requestDevice` was not called, and the page
    is connected."""
    if prompts_after != prompts_before:
        return False, f"{prompts_after - prompts_before} new chooser prompt(s) during the reconnect"
    if requests_after != requests_before:
        return False, f"requestDevice was called {requests_after - requests_before} time(s) during the reconnect"
    if state_after != "connected":
        return False, f"no chooser prompt, but the page state is {state_after!r}, not connected"
    return True, (f"no chooser prompt (events stay at {prompts_after}), requestDevice calls stay at "
                  f"{requests_after}, page connected")


def check_resumed_after_reboot(seq_before, first_seq, max_seq=WEB_RESUME_MAX_SEQ):
    """After a reboot the first Heartbeat the page shows is small (<= `max_seq`) and below the last one
    shown before the reboot (the counter restarted; it did not just keep running)."""
    if first_seq is None:
        return False, "the page showed no Heartbeat after the reconnect"
    if first_seq >= seq_before:
        return False, f"first seq after the reboot {first_seq} is not below the last one before it, {seq_before}"
    if first_seq > max_seq:
        return False, f"first seq after the reboot {first_seq} is not small (limit {max_seq}), before it {seq_before}"
    return True, f"first seq after the reboot {first_seq} (limit {max_seq}), last one before it {seq_before}"


def check_brightness_kept(slider_pct, board_text, lines, set_brightness):
    """A disconnect and reconnect without a reboot keeps the Brightness set before it: the console `lines`
    from the set on show no reset and end at `set_brightness`, and the re-synced slider and the page's own
    "board reports" text show that value."""
    for t, _, text in lines:
        if text.startswith(ROM_BANNER) or is_boot_line(text):
            return False, f"the board reset at +{t:.1f}s ({text.strip()}), the Brightness was not kept by a plain disconnect"
    return check_slider_shows_board(slider_pct, board_text, lines, expect_brightness=set_brightness)
