"""Testing call: per Testing Decisions (Harness Check logic gets Python unittest): line
reassembly, line classification, Heartbeat continuity and reply parsing are pure logic and the
shared wire contract with the board and the Web App.
Seam: central_logic.py public names (LineReassembler, classify_line, parse_heartbeat,
parse_reply, step_kind, check_heartbeats, matches_board). The expected strings and numbers are
literals from the spec's Wire contract, not built with the code under test.
Glue, proven on the board (tickets 06 on): central.py, the bleak scan / connect / notify / write
wrapper. Nothing in this file scans, connects or opens a serial port; a test below proves the
logic module cannot (it imports neither bleak nor serial).

    .venv/bin/python -m unittest discover -s tools/verify
"""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import central_logic as cl  # noqa: E402


class LineReassembly(unittest.TestCase):
    def test_one_notification_with_one_line(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b"LED 128\n"), ["LED 128"])

    def test_line_split_across_notifications_is_joined(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b'{"seq":1,'), [])
        self.assertEqual(r.feed(b'"uptime_ms"'), [])
        self.assertEqual(r.feed(b':1000}\n'), ['{"seq":1,"uptime_ms":1000}'])

    def test_two_lines_in_one_notification(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b"LED 0\nLED 255\n"), ["LED 0", "LED 255"])

    def test_notification_ending_mid_line_keeps_the_rest_for_the_next(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b"LED 1\nERR bad"), ["LED 1"])
        self.assertEqual(r.feed(b" value\n"), ["ERR bad value"])

    def test_newline_alone_in_its_own_notification_ends_the_line(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b"LED 7"), [])
        self.assertEqual(r.feed(b"\n"), ["LED 7"])

    def test_crlf_is_stripped(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b"LED 5\r\n"), ["LED 5"])

    def test_empty_notification_yields_nothing(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b""), [])

    def test_blank_line_is_kept_as_an_empty_string(self):
        r = cl.LineReassembler()
        self.assertEqual(r.feed(b"\nLED 2\n"), ["", "LED 2"])

    def test_multibyte_character_split_between_notifications(self):
        r = cl.LineReassembler()
        raw = "ERR é\n".encode("utf-8")
        cut = raw.index(b"\xc3") + 1              # between the two bytes of 'é'
        self.assertEqual(r.feed(raw[:cut]), [])
        self.assertEqual(r.feed(raw[cut:]), ["ERR é"])

    def test_invalid_utf8_does_not_raise(self):
        r = cl.LineReassembler()
        lines = r.feed(b"\xff\xfe\n")
        self.assertEqual(len(lines), 1)

    def test_reset_drops_a_partial_line(self):
        r = cl.LineReassembler()
        r.feed(b"LED 12")
        r.reset()
        self.assertEqual(r.feed(b"3\n"), ["3"])

    def test_pending_shows_the_unfinished_line(self):
        r = cl.LineReassembler()
        r.feed(b"LED 12")
        self.assertEqual(r.pending, "LED 12")
        r.feed(b"8\n")
        self.assertEqual(r.pending, "")

class ReplyParsing(unittest.TestCase):
    def test_led_reply_gives_the_brightness(self):
        for n in (0, 1, 128, 254, 255):
            self.assertEqual(cl.parse_reply(f"LED {n}"), cl.Reply(ok=True, brightness=n, message=None), n)

    def test_err_reply_keeps_the_message_and_no_brightness(self):
        self.assertEqual(cl.parse_reply("ERR value out of range"),
                         cl.Reply(ok=False, brightness=None, message="value out of range"))

    def test_err_with_an_empty_message_is_still_an_error(self):
        self.assertEqual(cl.parse_reply("ERR "), cl.Reply(ok=False, brightness=None, message=""))

    def test_led_reply_outside_0_255_is_not_a_reply(self):
        for text in ("LED 256", "LED 300", "LED -1", "LED 1000"):
            self.assertIsNone(cl.parse_reply(text), text)

    def test_malformed_led_reply_is_not_a_reply(self):
        for text in ("LED", "LED ", "LED abc", "LED 12x", "LED 1.5", "LED  5", "LED 5 ", "LED 007",
                     "led 5", " LED 5", "LEDS 5", "LED\t5"):
            self.assertIsNone(cl.parse_reply(text), repr(text))

    def test_err_needs_the_space_after_it(self):
        self.assertIsNone(cl.parse_reply("ERR"))
        self.assertIsNone(cl.parse_reply("ERROR bad"))
        self.assertIsNone(cl.parse_reply("err bad"))

    def test_other_lines_are_not_replies(self):
        for text in ("", "{}", '{"seq":1,"uptime_ms":2}', "uart:~$ ", "hello"):
            self.assertIsNone(cl.parse_reply(text), repr(text))


class HeartbeatParsing(unittest.TestCase):
    def test_wire_contract_line(self):
        self.assertEqual(cl.parse_heartbeat('{"seq":7,"uptime_ms":7012}'), cl.Heartbeat(seq=7, uptime_ms=7012))

    def test_boot_values(self):
        self.assertEqual(cl.parse_heartbeat('{"seq":0,"uptime_ms":0}'), cl.Heartbeat(seq=0, uptime_ms=0))

    def test_maximum_values_of_the_wire_contract(self):
        line = '{"seq":4294967295,"uptime_ms":18446744073709551615}'
        self.assertEqual(cl.parse_heartbeat(line), cl.Heartbeat(seq=4294967295, uptime_ms=18446744073709551615))

    def test_past_the_maximum_is_rejected(self):
        self.assertIsNone(cl.parse_heartbeat('{"seq":4294967296,"uptime_ms":1}'))
        self.assertIsNone(cl.parse_heartbeat('{"seq":1,"uptime_ms":18446744073709551616}'))

    def test_key_order_and_spaces_do_not_matter(self):
        self.assertEqual(cl.parse_heartbeat('{ "uptime_ms": 5, "seq": 2 }'), cl.Heartbeat(seq=2, uptime_ms=5))

    def test_missing_key_is_rejected(self):
        self.assertIsNone(cl.parse_heartbeat('{"seq":1}'))
        self.assertIsNone(cl.parse_heartbeat('{"uptime_ms":1}'))
        self.assertIsNone(cl.parse_heartbeat("{}"))

    def test_wrong_types_are_rejected(self):
        for text in ('{"seq":"1","uptime_ms":2}', '{"seq":1.5,"uptime_ms":2}', '{"seq":-1,"uptime_ms":2}',
                     '{"seq":true,"uptime_ms":2}', '{"seq":null,"uptime_ms":2}', '{"seq":1,"uptime_ms":[2]}'):
            self.assertIsNone(cl.parse_heartbeat(text), text)

    def test_broken_json_is_rejected(self):
        for text in ('{"seq":1,"uptime_ms":', "{", '{"seq":1,"uptime_ms":2}}', "not json"):
            self.assertIsNone(cl.parse_heartbeat(text), text)

    def test_json_that_is_not_an_object_is_rejected(self):
        self.assertIsNone(cl.parse_heartbeat("[1,2]"))


class LineClassification(unittest.TestCase):
    def test_heartbeat(self):
        got = cl.classify_line('{"seq":3,"uptime_ms":3004}')
        self.assertEqual(got.kind, cl.HEARTBEAT)
        self.assertEqual((got.seq, got.uptime_ms), (3, 3004))

    def test_led_reply(self):
        got = cl.classify_line("LED 128")
        self.assertEqual(got.kind, cl.LED)
        self.assertEqual(got.brightness, 128)

    def test_err_reply(self):
        got = cl.classify_line("ERR out of range")
        self.assertEqual(got.kind, cl.ERR)
        self.assertEqual(got.message, "out of range")

    def test_other_lines_keep_their_text(self):
        for text in ("", "hello", "uart:~$ led set 5", "LED x", "ERR", '{"seq":1}', "{ broken"):
            got = cl.classify_line(text)
            self.assertEqual((got.kind, got.raw), (cl.OTHER, text), repr(text))

    def test_every_class_keeps_the_raw_line(self):
        for text in ('{"seq":3,"uptime_ms":3004}', "LED 128", "ERR x", "other"):
            self.assertEqual(cl.classify_line(text).raw, text)

    def test_reassembled_stream_classifies_in_order(self):
        r = cl.LineReassembler()
        lines = r.feed(b'{"seq":1,"uptime_ms":1000}\nLED 9\nERR bad')
        lines += r.feed(b'\nnoise\n')
        self.assertEqual([cl.classify_line(x).kind for x in lines],
                         [cl.HEARTBEAT, cl.LED, cl.ERR, cl.OTHER])

def hbs(*pairs, t0=0.0, dt=1.0):
    """Samples spaced dt apart from (seq, uptime_ms) pairs."""
    return [cl.Sample(t0 + i * dt, seq, up) for i, (seq, up) in enumerate(pairs)]


class HeartbeatStep(unittest.TestCase):
    def test_next_number_is_consecutive(self):
        self.assertEqual(cl.step_kind(cl.Sample(0, 4, 4000), cl.Sample(1, 5, 5001)), cl.CONSECUTIVE)

    def test_skipped_numbers_are_a_gap(self):
        self.assertEqual(cl.step_kind(cl.Sample(0, 4, 4000), cl.Sample(3, 7, 7000)), cl.GAP)

    def test_smaller_number_is_a_reboot(self):
        self.assertEqual(cl.step_kind(cl.Sample(0, 40, 40000), cl.Sample(1, 2, 2100)), cl.REBOOT)

    def test_reboot_to_zero(self):
        self.assertEqual(cl.step_kind(cl.Sample(0, 1, 1000), cl.Sample(1, 0, 40)), cl.REBOOT)

    def test_uptime_going_back_is_a_reboot_even_if_the_number_is_larger(self):
        # Rebooted, then ran longer than the old boot before the first line arrived.
        self.assertEqual(cl.step_kind(cl.Sample(0, 3, 30000), cl.Sample(1, 5, 5000)), cl.REBOOT)

    def test_same_number_twice_is_a_repeat(self):
        self.assertEqual(cl.step_kind(cl.Sample(0, 4, 4000), cl.Sample(1, 4, 4000)), cl.REPEAT)


class HeartbeatCheck(unittest.TestCase):
    def ten(self, **kw):
        return hbs(*[(n, 1000 * n + 5) for n in range(3, 13)], **kw)

    def test_ten_consecutive_one_second_apart_pass(self):
        ok, detail = cl.check_heartbeats(self.ten(), min_samples=10)
        self.assertTrue(ok, detail)
        self.assertIn("10 heartbeats", detail)
        self.assertIn("seq 3..12", detail)

    def test_too_few_samples_fail(self):
        ok, detail = cl.check_heartbeats(self.ten()[:5], min_samples=10)
        self.assertFalse(ok)
        self.assertIn("5 heartbeat(s)", detail)
        self.assertIn("10", detail)

    def test_no_samples_fail(self):
        ok, _ = cl.check_heartbeats([], min_samples=1)
        self.assertFalse(ok)

    def test_gap_fails_and_names_the_numbers(self):
        s = hbs((1, 1000), (2, 2000), (4, 4000), (5, 5000))
        ok, detail = cl.check_heartbeats(s, min_samples=4)
        self.assertFalse(ok)
        self.assertIn("gap", detail)
        self.assertIn("2 -> 4", detail)

    def test_reboot_fails_and_names_the_numbers(self):
        s = hbs((8, 8000), (9, 9000), (0, 100), (1, 1100))
        ok, detail = cl.check_heartbeats(s, min_samples=4)
        self.assertFalse(ok)
        self.assertIn("reboot", detail)
        self.assertIn("9 -> 0", detail)

    def test_repeated_number_fails(self):
        ok, detail = cl.check_heartbeats(hbs((1, 1000), (1, 1000), (2, 2000)), min_samples=3)
        self.assertFalse(ok)
        self.assertIn("repeat", detail)

    def test_period_edges_pass(self):
        for dt in (0.8, 1.0, 1.2):
            ok, detail = cl.check_heartbeats(self.ten(dt=dt), min_samples=10)
            self.assertTrue(ok, f"dt={dt}: {detail}")

    def test_period_just_outside_fails(self):
        for dt in (0.79, 1.21):
            ok, detail = cl.check_heartbeats(self.ten(dt=dt), min_samples=10)
            self.assertFalse(ok, f"dt={dt}")
            self.assertIn("period", detail)

    def test_one_slow_interval_among_good_ones_fails(self):
        s = self.ten()
        s = s[:5] + [x._replace(t=x.t + 0.5) for x in s[5:]]      # the step into index 5 lasts 1.5 s
        ok, detail = cl.check_heartbeats(s, min_samples=10)
        self.assertFalse(ok)
        self.assertIn("1.500", detail)

    def test_period_and_tolerance_are_parameters(self):
        s = hbs(*[(n, 500 * n) for n in range(6)], dt=0.5)
        self.assertFalse(cl.check_heartbeats(s, min_samples=6)[0])
        self.assertTrue(cl.check_heartbeats(s, min_samples=6, period_s=0.5, tol_s=0.1)[0])

    def test_single_sample_meets_min_one_with_no_intervals(self):
        self.assertTrue(cl.check_heartbeats(hbs((5, 5000)), min_samples=1)[0])

    def test_nothing_required_and_nothing_received_passes(self):
        self.assertTrue(cl.check_heartbeats([], min_samples=0)[0])

    def test_samples_may_be_plain_tuples(self):
        ok, _ = cl.check_heartbeats([(0.0, 1, 1000), (1.0, 2, 2000)], min_samples=2)
        self.assertTrue(ok)

NUS = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"      # Nordic UART Service, from the Nordic NUS specification


class BoardMatch(unittest.TestCase):
    def test_name_and_nus_uuid_match(self):
        self.assertTrue(cl.matches_board("XIAO-C6-LED", [NUS]))

    def test_uuid_case_does_not_matter(self):
        self.assertTrue(cl.matches_board("XIAO-C6-LED", [NUS.upper()]))

    def test_other_services_alongside_are_fine(self):
        self.assertTrue(cl.matches_board("XIAO-C6-LED", ["0000180a-0000-1000-8000-00805f9b34fb", NUS]))

    def test_right_name_without_the_service_is_not_the_board(self):
        self.assertFalse(cl.matches_board("XIAO-C6-LED", []))
        self.assertFalse(cl.matches_board("XIAO-C6-LED", None))

    def test_right_service_with_another_name_is_not_the_board(self):
        self.assertFalse(cl.matches_board("Other", [NUS]))
        self.assertFalse(cl.matches_board(None, [NUS]))
        self.assertFalse(cl.matches_board("xiao-c6-led", [NUS]))

    def test_name_and_uuid_are_parameters(self):
        self.assertTrue(cl.matches_board("Foo", ["abc"], name="Foo", service_uuid="ABC"))


class WriteEncoding(unittest.TestCase):
    def test_command_gets_one_newline(self):
        self.assertEqual(cl.encode_command("led set 128"), b"led set 128\n")

    def test_existing_trailing_newline_is_not_doubled(self):
        self.assertEqual(cl.encode_command("led get\n"), b"led get\n")

    def test_newline_inside_a_command_is_refused(self):
        with self.assertRaises(ValueError):
            cl.encode_command("led set 1\nkernel reboot")

    def test_chunks_are_at_most_mtu_minus_3(self):
        data = b"x" * 50
        for mtu in (23, 247):
            chunks = cl.chunk_for_mtu(data, mtu)
            self.assertTrue(all(0 < len(c) <= mtu - 3 for c in chunks), mtu)
            self.assertEqual(b"".join(chunks), data)

    def test_default_mtu_gives_20_byte_chunks(self):
        self.assertEqual([len(c) for c in cl.chunk_for_mtu(b"y" * 45, 23)], [20, 20, 5])

    def test_short_data_is_one_chunk_and_empty_is_none(self):
        self.assertEqual(cl.chunk_for_mtu(b"led get\n", 247), [b"led get\n"])
        self.assertEqual(cl.chunk_for_mtu(b"", 247), [])

    def test_mtu_too_small_to_carry_data_is_refused(self):
        with self.assertRaises(ValueError):
            cl.chunk_for_mtu(b"a", 3)


class NoHardware(unittest.TestCase):
    def test_logic_module_imports_neither_bleak_nor_serial(self):
        code = ("import sys; sys.path.insert(0, %r); import central_logic; "
                "bad = [m for m in ('bleak', 'serial', 'dbus_fast') if m in sys.modules]; "
                "sys.exit('imported: %%s' %% bad if bad else 0)") % os.path.dirname(os.path.abspath(__file__))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
