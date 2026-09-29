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
