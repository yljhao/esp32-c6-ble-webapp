"""Testing call: per Testing Decisions (Harness Check logic gets Python unittest).
Seam: checks.py public functions (check_boot_marker, the Self-test / Duty readback Checks,
format_result, exit_code).
Glue, proven on the board: verify.py (lock, build.sh calls, capture, log file).

    .venv/bin/python -m unittest discover -s tools/verify
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks  # noqa: E402


def cap(*texts, t0=0.0):
    """A capture in console.capture()'s shape: (t_rel, wallclock, text)."""
    return [(t0 + i * 0.1, None, s) for i, s in enumerate(texts)]


class BootMarker(unittest.TestCase):
    def test_present_with_reason_passes(self):
        ok, detail = checks.check_boot_marker(cap("ESP-ROM:esp32c6", "[BOOT] reason=usb"))
        self.assertTrue(ok)
        self.assertIn("[BOOT] reason=usb", detail)

    def test_each_documented_reason_word_passes(self):
        for reason in ("poweron", "pin", "software", "watchdog", "brownout",
                       "panic", "deepsleep", "usb", "jtag", "unknown"):
            ok, _ = checks.check_boot_marker(cap(f"[BOOT] reason={reason}"))
            self.assertTrue(ok, reason)

    def test_missing_marker_fails_and_says_so(self):
        ok, detail = checks.check_boot_marker(cap("ESP-ROM:esp32c6", "tick 1"))
        self.assertFalse(ok)
        self.assertIn("no [BOOT] reason= marker", detail)

    def test_empty_capture_fails(self):
        ok, _ = checks.check_boot_marker([])
        self.assertFalse(ok)

    def test_marker_without_reason_word_fails(self):
        ok, _ = checks.check_boot_marker(cap("[BOOT] reason="))
        self.assertFalse(ok)

    def test_capture_stop_predicate_agrees_with_the_check(self):
        for text in ("[BOOT] reason=usb", "[BOOT] reason=", "noise [BOOT] reason=usb", "[BOOT] reason=usb\r"):
            self.assertEqual(checks.is_boot_line(text), checks.check_boot_marker(cap(text))[0], text)

    def test_marker_must_start_the_line(self):
        ok, _ = checks.check_boot_marker(cap("noise [BOOT] reason=usb"))
        self.assertFalse(ok)


BOOT = "[BOOT] reason=usb"
START = "[STAGE] selftest: start"
DONE = "[STAGE] selftest: done"
LED0 = "[LED] brightness=0 duty=0.0% freq=0"
LED128 = "[LED] brightness=128 duty=50.1% freq=19998"
LED255 = "[LED] brightness=255 duty=100.0% freq=0"
GOOD = [BOOT, START, LED0, LED128, LED255, DONE, LED128]


class LedMarker(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(checks.parse_led("[LED] brightness=128 duty=50.1% freq=19998"), (128, 50.1, 19998))

    def test_parse_rejects_other_lines(self):
        for text in ("[LED] brightness=128", "LED 128", "[LED] brightness=x duty=50.1% freq=1",
                     "noise [LED] brightness=1 duty=1.0% freq=0"):
            self.assertIsNone(checks.parse_led(text), text)


class SelftestDone(unittest.TestCase):
    def test_start_then_done_passes(self):
        ok, detail = checks.check_selftest_done(cap(*GOOD))
        self.assertTrue(ok, detail)

    def test_fail_marker_fails_and_names_the_step(self):
        ok, detail = checks.check_selftest_done(cap(BOOT, START, LED0, "[STAGE] selftest: fail step=2", LED128))
        self.assertFalse(ok)
        self.assertIn("fail step=2", detail)

    def test_done_without_start_fails(self):
        ok, _ = checks.check_selftest_done(cap(BOOT, DONE))
        self.assertFalse(ok)

    def test_done_before_start_fails(self):
        ok, _ = checks.check_selftest_done(cap(BOOT, DONE, START))
        self.assertFalse(ok)

    def test_nothing_fails(self):
        ok, detail = checks.check_selftest_done(cap(BOOT))
        self.assertFalse(ok)
        self.assertIn("selftest", detail)


class SelftestReadbacks(unittest.TestCase):
    def test_sweep_readbacks_pass(self):
        ok, detail = checks.check_selftest_readbacks(cap(*GOOD))
        self.assertTrue(ok, detail)

    def test_missing_point_fails(self):
        ok, detail = checks.check_selftest_readbacks(cap(BOOT, START, LED0, LED255, DONE, LED128))
        self.assertFalse(ok)
        self.assertIn("128", detail)

    def test_constant_level_with_edges_fails(self):
        ok, _ = checks.check_selftest_readbacks(
            cap(BOOT, START, "[LED] brightness=0 duty=0.0% freq=20000", LED128, LED255, DONE))
        self.assertFalse(ok)

    def test_wrong_constant_level_fails(self):
        ok, _ = checks.check_selftest_readbacks(
            cap(BOOT, START, LED0, LED128, "[LED] brightness=255 duty=0.0% freq=0", DONE))
        self.assertFalse(ok)

    def test_midpoint_out_of_tolerance_fails(self):
        ok, _ = checks.check_selftest_readbacks(
            cap(BOOT, START, LED0, "[LED] brightness=128 duty=53.0% freq=19998", LED255, DONE))
        self.assertFalse(ok)


class BootBrightness(unittest.TestCase):
    def test_in_tolerance_after_selftest_passes(self):
        ok, detail = checks.check_boot_brightness(cap(*GOOD))
        self.assertTrue(ok, detail)
        self.assertIn("brightness=128", detail)

    def test_the_selftest_128_readback_does_not_count(self):
        ok, _ = checks.check_boot_brightness(cap(BOOT, START, LED0, LED128, LED255, DONE))
        self.assertFalse(ok)

    def test_duty_out_of_tolerance_fails(self):
        for duty in ("48.9", "51.1", "100.0", "0.0"):
            ok, _ = checks.check_boot_brightness(cap(BOOT, START, DONE, f"[LED] brightness=128 duty={duty}% freq=20000"))
            self.assertFalse(ok, duty)

    def test_duty_at_the_edges_passes(self):
        for duty in ("49.0", "51.0"):
            ok, _ = checks.check_boot_brightness(cap(BOOT, START, DONE, f"[LED] brightness=128 duty={duty}% freq=20000"))
            self.assertTrue(ok, duty)

    def test_frequency_not_near_20_khz_fails(self):
        for freq in (0, 18999, 21001, 1000):
            ok, _ = checks.check_boot_brightness(cap(BOOT, START, DONE, f"[LED] brightness=128 duty=50.0% freq={freq}"))
            self.assertFalse(ok, freq)

    def test_a_selftest_failure_does_not_hide_the_boot_brightness(self):
        ok, _ = checks.check_boot_brightness(cap(BOOT, START, "[STAGE] selftest: fail step=1", LED128))
        self.assertTrue(ok)


class MarkerOrder(unittest.TestCase):
    def test_boot_selftest_led_in_order_passes(self):
        ok, detail = checks.check_marker_order(cap(*GOOD))
        self.assertTrue(ok, detail)

    def test_led_before_selftest_done_fails(self):
        ok, _ = checks.check_marker_order(cap(BOOT, START, LED128, DONE))
        self.assertFalse(ok)

    def test_selftest_before_boot_fails(self):
        ok, _ = checks.check_marker_order(cap(START, DONE, BOOT, LED128))
        self.assertFalse(ok)

    def test_missing_marker_names_it(self):
        ok, detail = checks.check_marker_order(cap(BOOT, START, DONE))
        self.assertFalse(ok)
        self.assertIn("[LED]", detail)


class BootCaptureStop(unittest.TestCase):
    def test_stops_on_the_led_marker_after_selftest_only(self):
        stop = checks.BootCaptureDone()
        fired = [stop(t) for t in GOOD]
        self.assertEqual(fired, [False, False, False, False, False, False, True])

    def test_stops_after_a_selftest_failure_too(self):
        stop = checks.BootCaptureDone()
        fired = [stop(t) for t in (BOOT, START, "[STAGE] selftest: fail step=1", LED128)]
        self.assertEqual(fired, [False, False, False, True])


class Result(unittest.TestCase):
    def test_all_pass(self):
        line = checks.format_result([("a", True, ""), ("b", True, "")])
        self.assertEqual(line, "RESULT: PASS (2/2 checks)")

    def test_one_fail(self):
        line = checks.format_result([("a", True, ""), ("b", False, "x")])
        self.assertEqual(line, "RESULT: FAIL (1/2 checks)")

    def test_no_checks_is_a_fail(self):
        self.assertEqual(checks.format_result([]), "RESULT: FAIL (0/0 checks)")

    def test_exit_code_zero_only_on_pass(self):
        self.assertEqual(checks.exit_code([("a", True, "")]), 0)
        self.assertEqual(checks.exit_code([("a", True, ""), ("b", False, "")]), 1)
        self.assertEqual(checks.exit_code([]), 1)

    def test_check_line_format(self):
        self.assertEqual(checks.format_check("boot", True, "d"), "PASS  boot  (d)")
        self.assertEqual(checks.format_check("boot", False, ""), "FAIL  boot")


if __name__ == "__main__":
    unittest.main()
