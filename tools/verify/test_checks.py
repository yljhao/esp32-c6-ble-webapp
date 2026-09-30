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


class NoReboot(unittest.TestCase):
    """Ticket 08: `kernel reboot` over the Shell link must not reset the board."""

    def test_quiet_window_passes(self):
        ok, detail = checks.check_no_reboot(timed((0.5, "[HB] seq=10")), 5.0, observed_s=5.2)
        self.assertTrue(ok, detail)

    def test_a_boot_marker_fails(self):
        ok, detail = checks.check_no_reboot(timed((3.0, "[BOOT] reason=software")), 5.0, observed_s=5.2)
        self.assertFalse(ok)
        self.assertIn("[BOOT]", detail)

    def test_a_rom_banner_fails(self):
        ok, detail = checks.check_no_reboot(timed((2.0, ROM)), 5.0, observed_s=5.2)
        self.assertFalse(ok)
        self.assertIn("reset", detail)

    def test_window_too_short_fails(self):
        ok, detail = checks.check_no_reboot([], 5.0, observed_s=2.0)
        self.assertFalse(ok)
        self.assertIn("need 5", detail)


class BootReason(unittest.TestCase):
    """Ticket 08: `kernel reboot` on the serial shell resets the board with reason software."""

    def test_wanted_reason_passes(self):
        ok, detail = checks.check_boot_reason(timed((2.0, ROM), (3.0, "[BOOT] reason=software")), "software")
        self.assertTrue(ok, detail)

    def test_another_reason_fails_and_names_it(self):
        ok, detail = checks.check_boot_reason(timed((3.0, "[BOOT] reason=watchdog")), "software")
        self.assertFalse(ok)
        self.assertIn("watchdog", detail)

    def test_no_boot_marker_fails(self):
        ok, detail = checks.check_boot_reason(timed((3.0, "noise")), "software")
        self.assertFalse(ok)
        self.assertIn("no [BOOT]", detail)


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
        ok, detail = checks.check_led_applied(cap("[LED] brightness=100 duty=39.2% freq=19998"), 100)
        self.assertFalse(ok)
        self.assertIn("no tolerance", detail)

    def test_64_reads_25_percent_low_within_one_percent(self):
        # Ticket 12: slider 25 % -> Brightness 64 -> 64 * 100 / 255 = 25.1 % low, near 20 kHz.
        self.assertTrue(checks.check_led_applied(cap("[LED] brightness=64 duty=25.0% freq=19988"), 64)[0])
        self.assertTrue(checks.check_led_applied(cap("[LED] brightness=64 duty=26.0% freq=20000"), 64)[0])
        ok, detail = checks.check_led_applied(cap("[LED] brightness=64 duty=27.5% freq=20000"), 64)
        self.assertFalse(ok)
        self.assertIn("out of tolerance", detail)
        self.assertFalse(checks.check_led_applied(cap("[LED] brightness=64 duty=25.0% freq=0"), 64)[0])


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



class WebHeartbeatUpdates(unittest.TestCase):
    """Web App (ticket 11): the Heartbeat seq the page displays updates at least twice within 3 s.
    `changes` are the page's display changes [(wall_ms, seq)], oldest first."""

    def test_three_updates_within_the_window_pass(self):
        ok, detail = checks.check_hb_updates([(0, 1), (1000, 2), (2000, 3), (3000, 4)], start_ms=0)
        self.assertTrue(ok)
        self.assertIn("3 update(s)", detail)

    def test_exactly_two_updates_pass(self):
        ok, _ = checks.check_hb_updates([(500, 1), (1500, 2), (2500, 3), (9000, 4)], start_ms=400,
                                        observed_until_ms=9000)
        self.assertTrue(ok)

    def test_one_update_fails(self):
        ok, detail = checks.check_hb_updates([(500, 1), (3600, 2), (4500, 3)], start_ms=400,
                                             observed_until_ms=5000)
        self.assertFalse(ok)
        self.assertIn("1 update(s)", detail)

    def test_no_update_fails(self):
        ok, _ = checks.check_hb_updates([], start_ms=0, observed_until_ms=5000)
        self.assertFalse(ok)

    def test_an_update_after_the_window_does_not_count(self):
        ok, _ = checks.check_hb_updates([(1000, 1), (3001, 2), (3500, 3)], start_ms=0,
                                        observed_until_ms=4000)
        self.assertFalse(ok)

    def test_a_repeated_seq_is_not_an_update(self):
        ok, _ = checks.check_hb_updates([(100, 5), (1000, 5), (2000, 5)], start_ms=0, observed_until_ms=4000)
        self.assertFalse(ok)

    def test_an_observation_that_ended_inside_the_window_cannot_pass_or_fail_the_page(self):
        ok, detail = checks.check_hb_updates([(500, 1), (1500, 2)], start_ms=0, observed_until_ms=2000)
        self.assertFalse(ok)
        self.assertIn("ended", detail)


class WebHeartbeatUpdatesRetried(unittest.TestCase):
    """The PC's radio delivers Heartbeats late and in bunches (board-notes: radio episodes), so a
    3 s window that saw fewer than 2 updates is repeated on the next window, at most 3 windows, but
    only when the board's own uptime steps (shown by the page) are exactly 1000 ms per seq: then the
    board did its part and the delay is the link's."""

    @staticmethod
    def hb(*rows):
        """rows of (wall_ms, seq, uptime_ms) -> the page's display log [(wall_ms, seq, 'h:mm:ss.mmm')]."""
        def fmt(ms):
            return f"{ms // 3600000}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"
        return [(w, n, fmt(u)) for w, n, u in rows]

    def test_first_window_passing_is_reported_as_window_1(self):
        rows = self.hb((100, 1, 1000), (1100, 2, 2000), (2100, 3, 3000), (3100, 4, 4000))
        ok, detail = checks.check_hb_updates_retried(rows, start_ms=0, observed_until_ms=12000)
        self.assertTrue(ok)
        self.assertIn("window 1", detail)

    def test_a_late_bunch_passes_on_a_later_window_when_the_board_spacing_is_exact(self):
        rows = self.hb((100, 1, 1000), (4000, 2, 2000), (4010, 3, 3000), (5000, 4, 4000), (6000, 5, 5000))
        ok, detail = checks.check_hb_updates_retried(rows, start_ms=0, observed_until_ms=12000)
        self.assertTrue(ok)
        self.assertIn("window 2", detail)
        self.assertIn("link jitter", detail)

    def test_a_retry_is_not_credited_when_the_board_spacing_is_off(self):
        rows = self.hb((100, 1, 1000), (4000, 2, 2000), (5000, 3, 3500), (6000, 4, 4500), (7000, 5, 5500))
        ok, detail = checks.check_hb_updates_retried(rows, start_ms=0, observed_until_ms=12000)
        self.assertFalse(ok)
        self.assertIn("uptime", detail)

    def test_three_dead_windows_fail(self):
        rows = self.hb((100, 1, 1000))
        ok, _ = checks.check_hb_updates_retried(rows, start_ms=0, observed_until_ms=12000)
        self.assertFalse(ok)

    def test_a_missing_seq_between_two_rows_scales_the_expected_uptime_step(self):
        rows = self.hb((100, 1, 1000), (4000, 3, 3000), (5000, 4, 4000), (6000, 5, 5000))
        ok, _ = checks.check_hb_updates_retried(rows, start_ms=0, observed_until_ms=12000)
        self.assertTrue(ok)

    def test_an_observation_shorter_than_the_windows_cannot_pass_a_later_one(self):
        rows = self.hb((100, 1, 1000), (4000, 2, 2000), (4010, 3, 3000))
        ok, _ = checks.check_hb_updates_retried(rows, start_ms=0, observed_until_ms=5000)
        self.assertFalse(ok)


class WebPageMatchesConsole(unittest.TestCase):
    """The page's displayed seq against the console's `[HB] seq=N` marker (every tenth Heartbeat)."""

    @staticmethod
    def console(*pairs):
        import datetime
        base = datetime.datetime(2026, 9, 30, 12, 0, 0)
        return [(0.0, base + datetime.timedelta(milliseconds=ms), f"[HB] seq={n}") for ms, n in pairs]

    def changes(self, *pairs):
        import datetime
        base = datetime.datetime(2026, 9, 30, 12, 0, 0).timestamp() * 1000
        return [(base + ms, n) for ms, n in pairs]

    def test_a_shown_tenth_seq_on_the_console_within_the_skew_passes(self):
        ok, detail = checks.check_page_matches_console(
            self.changes((0, 9), (1000, 10), (2000, 11)), self.console((980, 10)))
        self.assertTrue(ok)
        self.assertIn("seq 10", detail)

    def test_a_skew_above_the_limit_fails(self):
        ok, detail = checks.check_page_matches_console(
            self.changes((0, 9), (3000, 10)), self.console((980, 10)), max_skew_s=1.5)
        self.assertFalse(ok)
        self.assertIn("seq 10", detail)

    def test_no_console_marker_for_any_displayed_seq_fails(self):
        ok, _ = checks.check_page_matches_console(self.changes((0, 3), (1000, 4)), self.console((500, 10)))
        self.assertFalse(ok)

    def test_a_page_seq_that_goes_backwards_fails(self):
        ok, detail = checks.check_page_matches_console(
            self.changes((0, 9), (1000, 10), (2000, 8)), self.console((980, 10)))
        self.assertFalse(ok)
        self.assertIn("backwards", detail)

    def test_the_console_marker_the_page_never_showed_is_not_a_failure_when_another_matches(self):
        ok, _ = checks.check_page_matches_console(
            self.changes((0, 9), (1000, 10), (2000, 11), (12000, 21)), self.console((980, 10), (10980, 20)))
        self.assertTrue(ok)

    def test_no_page_change_at_all_fails(self):
        ok, _ = checks.check_page_matches_console([], self.console((980, 10)))
        self.assertFalse(ok)


class WebSliderShowsBoard(unittest.TestCase):
    """After connecting, the slider shows the Brightness the console last reported."""

    def test_128_shows_50_percent(self):
        ok, detail = checks.check_slider_shows_board(50, "128 (50 %)", cap("[LED] brightness=128 duty=50.0% freq=20000"))
        self.assertTrue(ok)
        self.assertIn("brightness=128", detail)

    def test_the_last_marker_counts(self):
        lines = cap("[LED] brightness=128 duty=50.0% freq=20000", "[LED] brightness=255 duty=100.0% freq=0")
        self.assertTrue(checks.check_slider_shows_board(100, "255 (100 %)", lines)[0])
        self.assertFalse(checks.check_slider_shows_board(50, "128 (50 %)", lines)[0])

    def test_a_slider_that_still_shows_zero_fails(self):
        self.assertFalse(checks.check_slider_shows_board(0, "-", cap("[LED] brightness=128 duty=50.0% freq=20000"))[0])

    def test_a_board_text_that_disagrees_with_the_console_fails(self):
        ok, detail = checks.check_slider_shows_board(50, "64 (25 %)", cap("[LED] brightness=128 duty=50.0% freq=20000"))
        self.assertFalse(ok)
        self.assertIn("64 (25 %)", detail)

    def test_no_led_marker_fails(self):
        self.assertFalse(checks.check_slider_shows_board(50, "128 (50 %)", cap("tick"))[0])

    def test_an_expected_brightness_makes_a_consistent_but_other_value_fail(self):
        lines = cap("[LED] brightness=255 duty=100.0% freq=0")
        self.assertTrue(checks.check_slider_shows_board(100, "255 (100 %)", lines)[0])
        ok, detail = checks.check_slider_shows_board(100, "255 (100 %)", lines, expect_brightness=128)
        self.assertFalse(ok)
        self.assertIn("expected 128", detail)

    def test_an_expected_brightness_that_matches_passes(self):
        lines = cap("[LED] brightness=128 duty=50.2% freq=19995")
        self.assertTrue(checks.check_slider_shows_board(50, "128 (50 %)", lines, expect_brightness=128)[0])


class LinkLost(unittest.TestCase):
    def test_a_supervision_timeout_is_a_lost_link(self):
        self.assertTrue(checks.is_ble_link_lost("[BLE] disconnected reason=0x08"))

    def test_the_central_asking_to_disconnect_is_not(self):
        self.assertFalse(checks.is_ble_link_lost("[BLE] disconnected reason=0x13"))

    def test_other_lines_are_not(self):
        self.assertFalse(checks.is_ble_link_lost("[BLE] connected"))
        self.assertFalse(checks.is_ble_link_lost("[BLE] disconnected reason=zzz"))


if __name__ == "__main__":
    unittest.main()


class HeartbeatMarkers(unittest.TestCase):
    """Ticket 09: `[HB] seq=N` on every tenth Heartbeat."""

    def test_markers_ten_apart_pass(self):
        ok, detail = checks.check_hb_markers(cap("[HB] seq=10", "x", "[HB] seq=20", "[HB] seq=30"))
        self.assertTrue(ok, detail)

    def test_too_few_markers_fail(self):
        self.assertFalse(checks.check_hb_markers(cap("[HB] seq=10"))[0])
        self.assertFalse(checks.check_hb_markers(cap("noise"))[0])

    def test_a_marker_that_is_not_a_tenth_fails(self):
        ok, detail = checks.check_hb_markers(cap("[HB] seq=10", "[HB] seq=15"))
        self.assertFalse(ok)
        self.assertIn("multiple of 10", detail)

    def test_a_skipped_tenth_fails(self):
        ok, detail = checks.check_hb_markers(cap("[HB] seq=10", "[HB] seq=30"))
        self.assertFalse(ok)
        self.assertIn("apart", detail)

    def test_every_received_tenth_inside_the_range_needs_its_marker(self):
        lines = cap("[HB] seq=10", "[HB] seq=30")
        # seq 20 was received but the console skipped it (also caught as "not 10 apart" first)
        lines_ok = cap("[HB] seq=10", "[HB] seq=20", "[HB] seq=30")
        self.assertTrue(checks.check_hb_markers(lines_ok, received_seqs=[18, 19, 20, 21])[0])
        self.assertTrue(checks.check_hb_markers(lines_ok, received_seqs=[20, 40])[0])  # 40: outside the range
        self.assertFalse(checks.check_hb_markers(lines, received_seqs=[20])[0])

    def test_nothing_received_near_a_marker_gives_no_comparison(self):
        ok, _ = checks.check_hb_markers(cap("[HB] seq=10", "[HB] seq=20"), received_seqs=[5, 6, 7])
        self.assertFalse(ok)

    def test_marker_line_must_stand_alone(self):
        self.assertIsNone(checks.parse_hb_marker("[HB] seq=10 extra"))
        self.assertEqual(checks.parse_hb_marker("[HB] seq=10"), 10)


class StallSurvived(unittest.TestCase):
    def good(self):
        return [(0.0, None, "[DBG] stall: heartbeat sender stops"),
                (3.0, None, "[HB] link stalled: 1 stale heartbeat(s) dropped"),
                (5.0, None, "[HB] seq=30"),
                (12.0, None, "[HB] seq=40"),
                (15.0, None, "tail")]

    def test_no_reset_markers_and_drops_pass(self):
        ok, detail = checks.check_stall_survived(self.good(), 12.0)
        self.assertTrue(ok, detail)

    def test_reset_after_the_stall_fails(self):
        lines = self.good() + [(16.0, None, "ESP-ROM:esp32c6")]
        ok, detail = checks.check_stall_survived(lines, 12.0)
        self.assertFalse(ok)
        self.assertIn("reset", detail)

    def test_missing_stall_marker_fails(self):
        self.assertFalse(checks.check_stall_survived(self.good()[1:], 12.0)[0])

    def test_short_observation_fails(self):
        self.assertFalse(checks.check_stall_survived(self.good()[:4], 30.0)[0])

    def test_no_markers_fails(self):
        lines = [l for l in self.good() if "seq=" not in l[2]]
        self.assertFalse(checks.check_stall_survived(lines, 10.0, min_markers=2)[0])

    def test_no_drop_report_fails(self):
        lines = [l for l in self.good() if "stalled:" not in l[2]]
        ok, detail = checks.check_stall_survived(lines, 12.0)
        self.assertFalse(ok)
        self.assertIn("dropped", detail)


class WebDisconnectShown(unittest.TestCase):
    """Ticket 12: the page says disconnected within 5 s and keeps the last Heartbeat seq on screen."""

    STATUS = [(1000, "connected"), (61000, "disconnected")]
    HB = [(55000, 41, "0:00:41.000"), (57000, 42, "0:00:42.000")]

    def test_shown_in_time_with_the_seq_kept_passes(self):
        ok, detail = checks.check_disconnect_shown(self.STATUS, 58000, self.HB, "42")
        self.assertTrue(ok, detail)
        self.assertIn("3.0 s", detail)
        self.assertIn("seq 42", detail)

    def test_shown_too_late_fails(self):
        ok, detail = checks.check_disconnect_shown(self.STATUS, 55000, self.HB, "42")
        self.assertFalse(ok)
        self.assertIn("limit 5 s", detail)

    def test_never_shown_fails(self):
        ok, detail = checks.check_disconnect_shown([(1000, "connected")], 58000, self.HB, "42")
        self.assertFalse(ok)
        self.assertIn("never", detail)

    def test_a_disconnected_before_the_trigger_does_not_count(self):
        ok, _ = checks.check_disconnect_shown([(1000, "disconnected"), (2000, "connected")], 58000, self.HB, "42")
        self.assertFalse(ok)

    def test_a_seq_that_was_cleared_fails(self):
        ok, detail = checks.check_disconnect_shown(self.STATUS, 58000, self.HB, "-")
        self.assertFalse(ok)
        self.assertIn("'-'", detail)

    def test_a_seq_that_changed_after_the_drop_fails(self):
        self.assertFalse(checks.check_disconnect_shown(self.STATUS, 58000, self.HB, "43")[0])

    def test_a_heartbeat_that_arrived_after_the_drop_is_not_the_one_kept(self):
        hb = self.HB + [(62000, 43, "0:00:43.000")]
        self.assertTrue(checks.check_disconnect_shown(self.STATUS, 58000, hb, "42")[0])

    def test_no_heartbeat_before_the_drop_fails(self):
        ok, detail = checks.check_disconnect_shown(self.STATUS, 58000, [(62000, 43, "x")], "43")
        self.assertFalse(ok)
        self.assertIn("no Heartbeat", detail)


class WebSeqShownAt(unittest.TestCase):
    HB = [(1000, 5, "a"), (2000, 6, "b"), (3000, 7, "c")]

    def test_the_last_change_at_or_before(self):
        self.assertEqual(checks.seq_shown_at(self.HB, 2500), 6)
        self.assertEqual(checks.seq_shown_at(self.HB, 3000), 7)

    def test_none_before_the_first(self):
        self.assertIsNone(checks.seq_shown_at(self.HB, 500))
        self.assertIsNone(checks.seq_shown_at([], 500))


class WebReconnectNoChooser(unittest.TestCase):
    def test_no_new_prompt_and_no_request_passes(self):
        self.assertTrue(checks.check_reconnect_no_chooser(1, 1, 1, 1, "connected")[0])

    def test_a_new_chooser_prompt_fails(self):
        ok, detail = checks.check_reconnect_no_chooser(1, 3, 1, 1, "connected")
        self.assertFalse(ok)
        self.assertIn("prompt", detail)

    def test_a_requestDevice_call_fails(self):
        ok, detail = checks.check_reconnect_no_chooser(1, 1, 1, 2, "connected")
        self.assertFalse(ok)
        self.assertIn("requestDevice", detail)

    def test_not_connected_fails(self):
        ok, detail = checks.check_reconnect_no_chooser(1, 1, 1, 1, "error")
        self.assertFalse(ok)
        self.assertIn("error", detail)


class WebResumedAfterReboot(unittest.TestCase):
    def test_a_small_seq_below_the_old_one_passes(self):
        ok, detail = checks.check_resumed_after_reboot(90, 4)
        self.assertTrue(ok, detail)

    def test_a_seq_that_kept_counting_fails(self):
        ok, detail = checks.check_resumed_after_reboot(90, 95)
        self.assertFalse(ok)
        self.assertIn("not below", detail)

    def test_a_large_seq_fails_even_below_the_old_one(self):
        ok, detail = checks.check_resumed_after_reboot(500, 200)
        self.assertFalse(ok)
        self.assertIn("small", detail)

    def test_no_heartbeat_fails(self):
        self.assertFalse(checks.check_resumed_after_reboot(90, None)[0])

    def test_the_limit_is_included(self):
        self.assertTrue(checks.check_resumed_after_reboot(90, checks.WEB_RESUME_MAX_SEQ)[0])
        self.assertFalse(checks.check_resumed_after_reboot(90, checks.WEB_RESUME_MAX_SEQ + 1)[0])


class WebBrightnessKept(unittest.TestCase):
    """A plain disconnect and reconnect (no reboot) keeps the Brightness set before it."""

    SET = "[LED] brightness=64 duty=25.1% freq=20000"

    def test_slider_and_text_at_the_set_value_pass(self):
        ok, detail = checks.check_brightness_kept(25, "64 (25 %)", cap(self.SET, "[BLE] disconnected reason=0x13"), 64)
        self.assertTrue(ok, detail)

    def test_a_reset_in_between_fails(self):
        lines = cap(self.SET, "ESP-ROM:esp32c6", "[BOOT] reason=software", "[LED] brightness=128 duty=50.0% freq=20000")
        ok, detail = checks.check_brightness_kept(50, "128 (50 %)", lines, 64)
        self.assertFalse(ok)
        self.assertIn("reset", detail)

    def test_a_slider_that_shows_another_value_fails(self):
        self.assertFalse(checks.check_brightness_kept(50, "64 (25 %)", cap(self.SET), 64)[0])

    def test_a_console_that_no_longer_holds_the_value_fails(self):
        lines = cap(self.SET, "[LED] brightness=128 duty=50.0% freq=20000")
        self.assertFalse(checks.check_brightness_kept(25, "64 (25 %)", lines, 64)[0])
