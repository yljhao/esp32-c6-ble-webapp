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


def check_marker_order(lines):
    """[BOOT] reason= -> [STAGE] selftest: start -> selftest end -> [LED] brightness=128."""
    steps = [("[BOOT] reason=", is_boot_line), ("[STAGE] selftest: start", _is_start),
             ("[STAGE] selftest: done|fail", _is_selftest_end),
             ("[LED] brightness=128", lambda t: (parse_led(t) or (None,))[0] == 128)]
    at = -1
    for name, pred in steps:
        i = _first(lines, pred, at + 1)
        if i is None:
            return False, f"{name} missing or out of order"
        at = i
    return True, " -> ".join(n for n, _ in steps)


class BootCaptureDone:
    """Capture stop predicate: the boot is complete once `[LED] brightness=128` follows
    the Self-test's end marker (done or fail)."""

    def __init__(self):
        self.ended = False

    def __call__(self, text):
        if _is_selftest_end(text):
            self.ended = True
            return False
        led = parse_led(text)
        return self.ended and led is not None and led[0] == 128


def format_check(name, ok, detail=""):
    return f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else "")


def format_result(results):
    passed = sum(1 for r in results if r[1])
    ok = bool(results) and passed == len(results)
    return f"RESULT: {'PASS' if ok else 'FAIL'} ({passed}/{len(results)} checks)"


def exit_code(results):
    return 0 if results and all(r[1] for r in results) else 1
