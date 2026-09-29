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
RB_0 = "[LED] brightness=0 duty=0.0% freq=0"
RB_128 = "[LED] brightness=128 duty=50.1% freq=19998"
RB_255 = "[LED] brightness=255 duty=100.0% freq=0"
WDT = "[WDT] armed window=5000ms"
GOOD = [BOOT, START, RB_0, RB_128, RB_255, DONE, RB_128, WDT]
ADV = "[BLE] advertising name=XIAO-C6-LED"
CONNECTED = "[BLE] connected"
MTU_DEFAULT = "[BLE] mtu=23"
MTU_247 = "[BLE] mtu=247"
DISCONNECTED = "[BLE] disconnected reason=0x13"
GOOD_BOOT = GOOD + [ADV]


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
        ok, detail = checks.check_selftest_done(cap(BOOT, START, RB_0, "[STAGE] selftest: fail step=2", RB_128))
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
        ok, detail = checks.check_selftest_readbacks(cap(BOOT, START, RB_0, RB_255, DONE, RB_128))
        self.assertFalse(ok)
        self.assertIn("128", detail)

    def test_constant_level_with_edges_fails(self):
        ok, _ = checks.check_selftest_readbacks(
            cap(BOOT, START, "[LED] brightness=0 duty=0.0% freq=20000", RB_128, RB_255, DONE))
        self.assertFalse(ok)

    def test_wrong_constant_level_fails(self):
        ok, _ = checks.check_selftest_readbacks(
            cap(BOOT, START, RB_0, RB_128, "[LED] brightness=255 duty=0.0% freq=0", DONE))
        self.assertFalse(ok)

    def test_midpoint_out_of_tolerance_fails(self):
        ok, _ = checks.check_selftest_readbacks(
            cap(BOOT, START, RB_0, "[LED] brightness=128 duty=53.0% freq=19998", RB_255, DONE))
        self.assertFalse(ok)


class BootBrightness(unittest.TestCase):
    def test_in_tolerance_after_selftest_passes(self):
        ok, detail = checks.check_boot_brightness(cap(*GOOD))
        self.assertTrue(ok, detail)
        self.assertIn("brightness=128", detail)

    def test_the_selftest_128_readback_does_not_count(self):
        ok, _ = checks.check_boot_brightness(cap(BOOT, START, RB_0, RB_128, RB_255, DONE))
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
        ok, _ = checks.check_boot_brightness(cap(BOOT, START, "[STAGE] selftest: fail step=1", RB_128))
        self.assertTrue(ok)


class MarkerOrder(unittest.TestCase):
    def test_boot_selftest_led_watchdog_advertising_in_order_passes(self):
        ok, detail = checks.check_marker_order(cap(*GOOD_BOOT))
        self.assertTrue(ok, detail)

    def test_led_before_selftest_done_fails(self):
        ok, _ = checks.check_marker_order(cap(BOOT, START, RB_128, DONE))
        self.assertFalse(ok)

    def test_selftest_before_boot_fails(self):
        ok, _ = checks.check_marker_order(cap(START, DONE, BOOT, RB_128))
        self.assertFalse(ok)

    def test_missing_marker_names_it(self):
        ok, detail = checks.check_marker_order(cap(BOOT, START, DONE))
        self.assertFalse(ok)
        self.assertIn("[LED]", detail)

    def test_watchdog_before_the_boot_brightness_fails(self):
        ok, _ = checks.check_marker_order(cap(BOOT, START, DONE, WDT, RB_128, ADV))
        self.assertFalse(ok)

    def test_missing_watchdog_marker_names_it(self):
        ok, detail = checks.check_marker_order(cap(BOOT, START, DONE, RB_128))
        self.assertFalse(ok)
        self.assertIn("[WDT]", detail)

    def test_advertising_before_the_watchdog_fails(self):
        ok, _ = checks.check_marker_order(cap(BOOT, START, DONE, RB_128, ADV, WDT))
        self.assertFalse(ok)

    def test_missing_advertising_marker_names_it(self):
        ok, detail = checks.check_marker_order(cap(*GOOD))
        self.assertFalse(ok)
        self.assertIn("[BLE] advertising", detail)


class BootCaptureStop(unittest.TestCase):
    def test_stops_on_the_advertising_marker_after_the_watchdog(self):
        stop = checks.BootCaptureDone()
        fired = [stop(t) for t in GOOD_BOOT]
        self.assertEqual(fired, [False] * 8 + [True])

    def test_the_watchdog_marker_alone_does_not_stop(self):
        stop = checks.BootCaptureDone()
        self.assertFalse([stop(t) for t in GOOD][-1])

    def test_an_advertising_marker_before_the_watchdog_does_not_stop(self):
        stop = checks.BootCaptureDone()
        self.assertFalse(any(stop(t) for t in (BOOT, START, DONE, RB_128, ADV)))

    def test_an_advertising_marker_before_the_selftest_end_does_not_stop(self):
        stop = checks.BootCaptureDone()
        self.assertFalse(stop(ADV))

    def test_stops_after_a_selftest_failure_too(self):
        stop = checks.BootCaptureDone()
        fired = [stop(t) for t in (BOOT, START, "[STAGE] selftest: fail step=1", RB_128, WDT, ADV)]
        self.assertEqual(fired, [False] * 5 + [True])


class BleAdvertising(unittest.TestCase):
    def test_marker_after_the_watchdog_passes(self):
        ok, detail = checks.check_ble_advertising(cap(*GOOD_BOOT))
        self.assertTrue(ok, detail)
        self.assertIn("name=XIAO-C6-LED", detail)

    def test_missing_marker_fails(self):
        ok, detail = checks.check_ble_advertising(cap(*GOOD))
        self.assertFalse(ok)
        self.assertIn("no [BLE] advertising", detail)

    def test_wrong_name_fails(self):
        ok, _ = checks.check_ble_advertising(cap(*GOOD, "[BLE] advertising name=Zephyr"))
        self.assertFalse(ok)

    def test_start_failure_marker_is_named(self):
        ok, detail = checks.check_ble_advertising(cap(*GOOD, "[BLE] start failed err=-12"))
        self.assertFalse(ok)
        self.assertIn("start failed err=-12", detail)

    def test_marker_before_the_watchdog_fails(self):
        ok, _ = checks.check_ble_advertising(cap(BOOT, START, DONE, ADV, RB_128, WDT))
        self.assertFalse(ok)


class BleConnected(unittest.TestCase):
    def test_connected_then_mtu_247_passes(self):
        ok, detail = checks.check_ble_connected(cap(MTU_DEFAULT, CONNECTED, MTU_247), 247)
        self.assertTrue(ok, detail)
        self.assertIn("mtu=247", detail)

    def test_the_default_mtu_before_connected_is_not_the_negotiated_one(self):
        ok, _ = checks.check_ble_connected(cap(MTU_247, CONNECTED), 247)
        self.assertFalse(ok)

    def test_no_connected_marker_fails(self):
        ok, detail = checks.check_ble_connected(cap(ADV), 247)
        self.assertFalse(ok)
        self.assertIn("[BLE] connected", detail)

    def test_no_mtu_after_connected_fails(self):
        ok, detail = checks.check_ble_connected(cap(CONNECTED), 247)
        self.assertFalse(ok)
        self.assertIn("[BLE] mtu=", detail)

    def test_the_default_mtu_only_fails_and_names_it(self):
        ok, detail = checks.check_ble_connected(cap(CONNECTED, MTU_DEFAULT), 247)
        self.assertFalse(ok)
        self.assertIn("mtu=23", detail)

    def test_the_last_mtu_counts(self):
        ok, _ = checks.check_ble_connected(cap(CONNECTED, MTU_DEFAULT, MTU_247), 247)
        self.assertTrue(ok)

    def test_a_smaller_mtu_than_asked_fails(self):
        ok, _ = checks.check_ble_connected(cap(CONNECTED, "[BLE] mtu=185"), 247)
        self.assertFalse(ok)

    def test_noise_that_only_contains_the_marker_is_ignored(self):
        ok, _ = checks.check_ble_connected(cap("x [BLE] connected", "x [BLE] mtu=247"), 247)
        self.assertFalse(ok)


class BleNotAdvertisingWhileConnected(unittest.TestCase):
    def test_no_advertising_between_connected_and_disconnected_passes(self):
        ok, detail = checks.check_ble_silent_while_connected(cap(ADV, CONNECTED, MTU_247, DISCONNECTED, ADV))
        self.assertTrue(ok, detail)

    def test_advertising_inside_the_connection_fails(self):
        ok, detail = checks.check_ble_silent_while_connected(cap(CONNECTED, ADV, DISCONNECTED))
        self.assertFalse(ok)
        self.assertIn("advertising", detail)

    def test_needs_both_markers(self):
        self.assertFalse(checks.check_ble_silent_while_connected(cap(CONNECTED, MTU_247))[0])
        self.assertFalse(checks.check_ble_silent_while_connected(cap(DISCONNECTED))[0])


class BleDisconnected(unittest.TestCase):
    def test_disconnected_then_advertising_passes(self):
        ok, detail = checks.check_ble_disconnected(cap(CONNECTED, DISCONNECTED, ADV), 0x13)
        self.assertTrue(ok, detail)
        self.assertIn("reason=0x13", detail)

    def test_no_disconnected_marker_fails(self):
        ok, detail = checks.check_ble_disconnected(cap(CONNECTED), 0x13)
        self.assertFalse(ok)
        self.assertIn("[BLE] disconnected", detail)

    def test_advertising_missing_after_disconnect_fails(self):
        ok, detail = checks.check_ble_disconnected(cap(CONNECTED, DISCONNECTED), 0x13)
        self.assertFalse(ok)
        self.assertIn("[BLE] advertising", detail)

    def test_advertising_only_before_the_disconnect_does_not_count(self):
        ok, _ = checks.check_ble_disconnected(cap(ADV, CONNECTED, DISCONNECTED), 0x13)
        self.assertFalse(ok)

    def test_a_reason_other_than_the_expected_one_fails(self):
        ok, detail = checks.check_ble_disconnected(cap(CONNECTED, "[BLE] disconnected reason=0x08", ADV), 0x13)
        self.assertFalse(ok)
        self.assertIn("0x08", detail)

    def test_any_reason_is_accepted_when_none_is_expected(self):
        ok, _ = checks.check_ble_disconnected(cap(CONNECTED, "[BLE] disconnected reason=0x08", ADV), None)
        self.assertTrue(ok)

    def test_advertising_later_than_the_bound_fails(self):
        lines = [(0.0, None, CONNECTED), (1.0, None, DISCONNECTED), (3.5, None, ADV)]
        ok, detail = checks.check_ble_disconnected(lines, 0x13)
        self.assertFalse(ok)
        self.assertIn("2.500s", detail)

    def test_advertising_within_the_bound_passes(self):
        lines = [(0.0, None, CONNECTED), (1.0, None, DISCONNECTED), (1.9, None, ADV)]
        self.assertTrue(checks.check_ble_disconnected(lines, 0x13)[0])

    def test_the_bound_can_be_widened(self):
        lines = [(0.0, None, CONNECTED), (1.0, None, DISCONNECTED), (3.5, None, ADV)]
        self.assertTrue(checks.check_ble_disconnected(lines, 0x13, max_delay_s=5.0)[0])

    def test_a_reason_that_is_not_a_number_fails(self):
        ok, _ = checks.check_ble_disconnected(cap(CONNECTED, "[BLE] disconnected reason=x", ADV), None)
        self.assertFalse(ok)


class WatchdogArmed(unittest.TestCase):
    def test_marker_after_selftest_done_passes(self):
        ok, detail = checks.check_wdt_armed(cap(*GOOD))
        self.assertTrue(ok, detail)
        self.assertIn("[WDT] armed window=5000ms", detail)

    def test_missing_marker_fails(self):
        ok, detail = checks.check_wdt_armed(cap(*GOOD[:-1]))
        self.assertFalse(ok)
        self.assertIn("[WDT]", detail)

    def test_other_window_fails(self):
        for text in ("[WDT] armed window=30000ms", "[WDT] armed window=500ms", "[WDT] armed window=5000"):
            ok, _ = checks.check_wdt_armed(cap(BOOT, START, DONE, text))
            self.assertFalse(ok, text)

    def test_marker_before_selftest_done_fails(self):
        ok, detail = checks.check_wdt_armed(cap(BOOT, START, WDT, DONE))
        self.assertFalse(ok)
        self.assertIn("after", detail)

    def test_marker_after_a_selftest_failure_still_counts_as_after_the_end(self):
        ok, _ = checks.check_wdt_armed(cap(BOOT, START, "[STAGE] selftest: fail step=1", WDT))
        self.assertTrue(ok)


class IdleNoBite(unittest.TestCase):
    def test_quiet_for_the_whole_window_passes(self):
        lines = cap(*GOOD) + [(70.0, None, "")]
        ok, detail = checks.check_idle_no_bite(lines, 60.0)
        self.assertTrue(ok, detail)

    def test_window_shorter_than_asked_fails(self):
        lines = cap(*GOOD)
        ok, detail = checks.check_idle_no_bite(lines, 60.0, observed_s=30.0)
        self.assertFalse(ok)
        self.assertIn("need 60", detail)

    def test_a_second_boot_marker_after_arming_fails(self):
        lines = cap(*GOOD) + [(20.0, None, "ESP-ROM:esp32c6-20220919"), (22.0, None, "[BOOT] reason=watchdog")]
        ok, detail = checks.check_idle_no_bite(lines, 60.0, observed_s=60.0)
        self.assertFalse(ok)
        self.assertIn("reset", detail)

    def test_no_armed_marker_fails(self):
        ok, _ = checks.check_idle_no_bite(cap(BOOT, START, DONE), 60.0, observed_s=60.0)
        self.assertFalse(ok)

    def test_boot_lines_before_arming_are_not_a_bite(self):
        ok, _ = checks.check_idle_no_bite(cap("ESP-ROM:esp32c6", *GOOD), 10.0, observed_s=60.0)
        self.assertTrue(ok)


HANG = "[DBG] hang: main loop stops feeding"
ROM = "ESP-ROM:esp32c6-20220919"


def timed(*pairs):
    return [(t, None, s) for t, s in pairs]


class WatchdogBite(unittest.TestCase):
    def test_reset_within_the_limit_and_watchdog_reason_passes(self):
        lines = timed((10.0, HANG), (14.8, ROM), (17.0, "[BOOT] reason=watchdog"))
        ok, detail = checks.check_wdt_bite(lines, 7.0)
        self.assertTrue(ok, detail)
        self.assertIn("4.8", detail)

    def test_no_hang_marker_fails(self):
        ok, detail = checks.check_wdt_bite(timed((1.0, ROM), (3.0, "[BOOT] reason=watchdog")), 7.0)
        self.assertFalse(ok)
        self.assertIn("hang", detail)

    def test_no_reset_after_the_hang_fails(self):
        ok, detail = checks.check_wdt_bite(timed((10.0, HANG), (18.0, "noise")), 7.0)
        self.assertFalse(ok)
        self.assertIn("no reset", detail)

    def test_reset_too_late_fails(self):
        ok, detail = checks.check_wdt_bite(timed((10.0, HANG), (17.5, ROM), (19.5, "[BOOT] reason=watchdog")), 7.0)
        self.assertFalse(ok)
        self.assertIn("7.5", detail)

    def test_reset_too_early_fails(self):
        ok, _ = checks.check_wdt_bite(timed((10.0, HANG), (10.3, ROM), (12.3, "[BOOT] reason=watchdog")), 7.0)
        self.assertFalse(ok)

    def test_other_reason_fails_and_names_it(self):
        ok, detail = checks.check_wdt_bite(timed((10.0, HANG), (14.8, ROM), (17.0, "[BOOT] reason=software")), 7.0)
        self.assertFalse(ok)
        self.assertIn("software", detail)

    def test_no_boot_marker_after_the_reset_fails(self):
        ok, detail = checks.check_wdt_bite(timed((10.0, HANG), (14.8, ROM)), 7.0)
        self.assertFalse(ok)
        self.assertIn("[BOOT]", detail)


class NoHangCommand(unittest.TestCase):
    CFG = "CONFIG_WATCHDOG=y\n# CONFIG_C6_HANG_CMD is not set\n"

    def test_clean_config_and_image_pass(self):
        ok, detail = checks.check_no_hang_command(self.CFG, b"\x00firmware\x00")
        self.assertTrue(ok, detail)

    def test_option_set_fails(self):
        ok, detail = checks.check_no_hang_command(self.CFG + "CONFIG_C6_HANG_CMD=y\n", b"x")
        self.assertFalse(ok)
        self.assertIn("CONFIG_C6_HANG_CMD", detail)

    def test_command_text_in_the_image_fails(self):
        ok, detail = checks.check_no_hang_command(self.CFG, b"\x00" + checks.HANG_MARKER.encode() + b"\x00")
        self.assertFalse(ok)
        self.assertIn("image", detail)

    def test_command_registration_text_in_the_image_fails(self):
        ok, _ = checks.check_no_hang_command(self.CFG, b"..Stop the main loop feeding the watchdog..")
        self.assertFalse(ok)

    def test_empty_image_fails(self):
        ok, _ = checks.check_no_hang_command(self.CFG, b"")
        self.assertFalse(ok)


class HangRefused(unittest.TestCase):
    def test_nothing_happens_passes(self):
        ok, detail = checks.check_hang_refused(timed((0.1, "debug hang"), (9.0, "noise")), 8.0)
        self.assertTrue(ok, detail)

    def test_hang_marker_fails(self):
        ok, detail = checks.check_hang_refused(timed((1.0, HANG)), 8.0)
        self.assertFalse(ok)
        self.assertIn("accepted", detail)

    def test_reset_fails(self):
        ok, detail = checks.check_hang_refused(timed((3.0, ROM)), 8.0)
        self.assertFalse(ok)
        self.assertIn("reset", detail)

    def test_window_too_short_fails(self):
        ok, _ = checks.check_hang_refused(timed((0.1, "x")), 8.0, observed_s=3.0)
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


class LedApplied(unittest.TestCase):
    """Ticket 07: a Brightness set over the Shell link shows on the console with a Duty readback."""

    def test_each_level_in_tolerance_passes(self):
        for b, duty, freq in ((0, "0.0", 0), (128, "50.1", 19998), (255, "100.0", 0)):
            ok, detail = checks.check_led_applied(cap(f"[LED] brightness={b} duty={duty}% freq={freq}"), b)
            self.assertTrue(ok, detail)

    def test_missing_marker_fails(self):
        ok, detail = checks.check_led_applied(cap("LED 128"), 128)
        self.assertFalse(ok)
        self.assertIn("no [LED] brightness=128", detail)

    def test_other_brightness_marker_does_not_count(self):
        ok, _ = checks.check_led_applied(cap("[LED] brightness=0 duty=0.0% freq=0"), 128)
        self.assertFalse(ok)

    def test_out_of_tolerance_readback_fails(self):
        ok, detail = checks.check_led_applied(cap("[LED] brightness=128 duty=60.0% freq=19998"), 128)
        self.assertFalse(ok)
        self.assertIn("out of tolerance", detail)

    def test_level_without_a_tolerance_is_refused(self):
        ok, detail = checks.check_led_applied(cap("[LED] brightness=64 duty=25.0% freq=19998"), 64)
        self.assertFalse(ok)
        self.assertIn("no tolerance", detail)


class NoLedMarker(unittest.TestCase):
    def test_no_marker_passes(self):
        ok, _ = checks.check_no_led_marker(cap("something", "ERR x"))
        self.assertTrue(ok)

    def test_a_marker_fails_and_names_it(self):
        ok, detail = checks.check_no_led_marker(cap("[LED] brightness=255 duty=100.0% freq=0"))
        self.assertFalse(ok)
        self.assertIn("brightness=255", detail)


class SerialLedReplies(unittest.TestCase):
    """Ticket 07: the same `led` commands typed on the serial shell."""

    TYPED = ("uart:~$ led set 0", "[LED] brightness=0 duty=0.0% freq=0", "LED 0", "uart:~$ led get",
               "LED 0", "uart:~$ led set 300", "ERR out of range 0-255", "uart:~$ led get", "LED 0",
               "uart:~$ led set 128", "[LED] brightness=128 duty=50.1% freq=19998", "LED 128")
    WANT = ["LED 0", "LED 0", "ERR", "LED 0", "LED 128"]

    def test_replies_in_order_pass(self):
        ok, detail = checks.check_serial_led_replies(cap(*self.TYPED), self.WANT)
        self.assertTrue(ok, detail)

    def test_err_entry_matches_any_error_line(self):
        lines = cap("ERR not a number")
        self.assertTrue(checks.check_serial_led_replies(lines, ["ERR"])[0])

    def test_command_echo_is_not_a_reply(self):
        # "uart:~$ led get" contains "led get" but is not a reply line
        ok, _ = checks.check_serial_led_replies(cap("uart:~$ led get"), ["LED 0"])
        self.assertFalse(ok)

    def test_missing_reply_fails_and_says_which(self):
        ok, detail = checks.check_serial_led_replies(cap(*self.TYPED[:-3]), self.WANT)
        self.assertFalse(ok)
        self.assertIn("5 replies", detail)

    def test_wrong_value_fails(self):
        lines = cap("LED 1")
        ok, detail = checks.check_serial_led_replies(lines, ["LED 0"])
        self.assertFalse(ok)
        self.assertIn("LED 1", detail)



if __name__ == "__main__":
    unittest.main()
