#!/usr/bin/env python3
"""Timestamped console capture with an optional reset through reset.py.

Holds the port exclusively (TIOCEXCL) for the whole capture. Every line is
prefixed with wall-clock time and seconds since the reset (or since the
capture started when --reset is not given).

    python tools/board/console.py --port /dev/ttyACM0 --seconds 30 --reset
    python tools/board/console.py --seconds 0            # until Ctrl-C, no reset
    python tools/board/console.py --reset --expect "\\[BOOT\\] reason="   # exit 1 if a marker is missing
    python tools/board/console.py --seconds 3 --send "led get"   # type a serial-shell command

Library use (Harness): capture(...) returns [(t_rel, wallclock, text), ...].
"""
import argparse
import datetime
import os
import re
import sys
import time

import serial

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reset as board_reset  # noqa: E402

BAUD = 115200
ROM_BANNER = "ESP-ROM:"   # first line the chip prints after any reset
SYNC_GRACE_S = 1.5        # give up waiting for the banner after this


def _open(port):
    # read(256) returns on 256 bytes or this timeout: lines are stamped when
    # the read returns, so keep it short (0.2 s batched Markers printed within
    # the same 200 ms onto one timestamp; 20 ms keeps the stamp within 20 ms).
    return board_reset.open_exclusive(port, timeout=0.02)


def capture(port, seconds, do_reset=True, stop_when=None, sink=None, on_ready=None, linger=0.0,
            send=None, stop_event=None):
    """Capture for `seconds` (0 = forever) or until stop_when(text) is true,
    plus `linger` seconds after that. sink(t_rel, wallclock, text) is called
    per line as it arrives; on_ready() once the port is open (and the reset
    pulsed), i.e. when nothing the board prints can be lost any more (the
    console drops bytes while the port is closed).
    `send` (bytes) is written to the port once it is open, after on_ready:
    the Harness types a serial-shell command with it and captures the
    board's response, no reset (the board keeps running).
    `stop_event` (a threading.Event) ends the capture when set: the Harness runs the capture in a
    thread while it acts as a Central, and stops it once the Central is done."""
    lines = []
    ser = _open(port)
    buf = b""
    t0 = time.monotonic()
    # ser is always the port currently open: the finally closes whichever it is,
    # including one reopened after the device re-enumerated.
    try:
        ser.reset_input_buffer()
        # The port stays open across the reset: the USB-Serial/JTAG controller
        # survives an RTS reset on this board, so the ROM's first lines are caught.
        t0 = board_reset.pulse(ser) if do_reset else time.monotonic()
        if on_ready:
            on_ready()
        if send:
            ser.write(send)
        # Bytes the previous session left in flight are delivered together with
        # the fresh boot; after a reset only lines from the ROM banner on count.
        syncing = do_reset
        stop_at = None   # monotonic time to return at once stop_when has fired
        while True:
            if seconds and time.monotonic() - t0 >= seconds:
                break
            if stop_event is not None and stop_event.is_set():
                break
            if stop_at is not None and time.monotonic() >= stop_at:
                break
            try:
                chunk = ser.read(256)
            except serial.SerialException as e:
                # the device re-enumerated (port node gone): reopen
                if sink:
                    sink(time.monotonic() - t0, datetime.datetime.now(),
                         f"<console: port lost ({e}); reopening>")
                try:
                    ser.close()
                except (OSError, serial.SerialException):
                    pass
                board_reset.wait_for_port(port)
                ser = _open(port)
                continue
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                entry = (time.monotonic() - t0, datetime.datetime.now(),
                         raw.decode("utf-8", "replace").rstrip("\r"))
                if syncing and (entry[2].startswith(ROM_BANNER) or entry[0] > SYNC_GRACE_S):
                    syncing = False
                    if lines and sink:
                        sink(entry[0], entry[1],
                             f"<console: {len(lines)} stale line(s) above predate the reset>")
                    lines = []
                lines.append(entry)
                if sink:
                    sink(*entry)
                if stop_when and stop_at is None and not syncing and stop_when(entry[2]):
                    if linger <= 0:
                        return lines
                    stop_at = time.monotonic() + linger
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ser.close()
        except (OSError, serial.SerialException):
            pass
    if buf:
        entry = (time.monotonic() - t0, datetime.datetime.now(),
                 buf.decode("utf-8", "replace"))
        lines.append(entry)
        if sink:
            sink(*entry)
    return lines


def fmt(t_rel, wall, text):
    return f"{wall.strftime('%H:%M:%S.%f')[:-3]} +{t_rel:7.3f}s {text}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=board_reset.DEFAULT_PORT)
    ap.add_argument("--seconds", type=float, default=30.0, help="0 = until Ctrl-C")
    ap.add_argument("--reset", action="store_true", help="reset through tools/board/reset.py first")
    ap.add_argument("--send", metavar="TEXT",
                    help="type TEXT (plus CR LF) on the console once the port is open, e.g. "
                         "a shell command such as \"led get\"; the board is not reset")
    ap.add_argument("--expect", metavar="REGEX", action="append", default=[],
                    help="marker (regular expression) that must appear on the console; repeatable. "
                         "The capture ends as soon as all were seen and exits 1 if the window "
                         "closes with one missing")
    args = ap.parse_args()
    patterns = [re.compile(p) for p in args.expect]
    missing = list(patterns)

    def all_seen(text):
        for p in list(missing):
            if p.search(text):
                missing.remove(p)
        return bool(patterns) and not missing

    print(f"console.py: {args.port} exclusive, reset={'yes' if args.reset else 'no'}, "
          f"window={'until Ctrl-C' if not args.seconds else f'{args.seconds:.0f} s'}, "
          f"{'send=' + repr(args.send) + ', ' if args.send else ''}"
          f"started {datetime.datetime.now().isoformat(timespec='milliseconds')}")
    try:
        capture(args.port, args.seconds, args.reset,
                sink=lambda t, w, s: print(fmt(t, w, s), flush=True),
                stop_when=all_seen if patterns else None,
                send=(args.send + "\r\n").encode() if args.send else None)
    except (serial.SerialException, TimeoutError, OSError) as e:
        print(f"console.py: FAIL: {e}")
        return 1
    if missing:
        print("console.py: FAIL: marker missing: " + ", ".join(p.pattern for p in missing))
        return 1
    if patterns:
        print("console.py: OK: all expected markers seen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
