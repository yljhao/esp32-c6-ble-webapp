"""Testing call: per Testing Decisions (Harness Check logic gets Python unittest).
Seam: checks.py public functions (check_boot_marker, format_result, exit_code).
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
