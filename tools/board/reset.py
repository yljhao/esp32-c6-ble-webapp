#!/usr/bin/env python3
"""The single board reset helper.

Pulls the ESP32-C6's EN line through the USB-Serial/JTAG controller: with
DTR low, RTS high asserts reset (RTS high + DTR high does nothing, which is
why the sequence steps through (1,1) and (0,0) and never through (0,1) while
a reset is pending). The helper waits for the port node to come back in case the
USB-Serial/JTAG controller re-enumerates (see docs/agents/board-notes.md,
log: Reset method, for what was observed on this board).

Used by build.sh serial (console.py) and the Harness.

    python tools/board/reset.py [--port /dev/ttyACM0] [--timeout 10]
"""
import argparse
import fcntl
import os
import re
import sys
import termios
import time

import serial

DEFAULT_PORT = "/dev/ttyACM0"
REENUMERATE_TIMEOUT_S = 10.0
RESET_HOLD_S = 0.2
BANNER_TIMEOUT_S = 1.5
# ROM banner line: "rst:0x15 (USB_UART_HPSYS),boot:0x1e (SPI_FAST_FLASH_BOOT)"
BANNER_RE = re.compile(r"rst:(0x[0-9a-fA-F]+) \(([A-Za-z_0-9]+)\),boot:(0x[0-9a-fA-F]+) \(([A-Za-z_0-9()/]+)\)")


def open_exclusive(port, timeout=0.1):
    """Open the port so that any other process's open() fails with EBUSY:
    pyserial's exclusive=True only takes an advisory flock, TIOCEXCL makes
    the kernel refuse further opens (root excepted) until we close."""
    ser = serial.Serial(port, 115200, timeout=timeout, exclusive=True)
    fcntl.ioctl(ser.fd, termios.TIOCEXCL)
    return ser


def pulse(ser):
    """Assert then release reset on an open port. Returns the monotonic time
    at which reset was asserted (the boot's t=0)."""
    # The kernel asserts DTR and RTS together on open: (1,1), idle.
    ser.rts = False          # (0,1): DTR alone only pulls the boot strap, harmless
    ser.dtr = False          # (0,0): idle
    time.sleep(0.05)
    t_reset = time.monotonic()
    try:
        ser.rts = True       # (1,0): EN low
        time.sleep(RESET_HOLD_S)
        ser.rts = False      # release; the device may already be re-enumerating
    except (OSError, serial.SerialException):
        pass                 # the USB device vanished under us: reset took
    return t_reset


def read_banner(ser, timeout=BANNER_TIMEOUT_S):
    """Read the ROM's reset banner after a pulse. Returns (rst, boot) names,
    e.g. ("USB_UART_HPSYS", "SPI_FAST_FLASH_BOOT"), or None on timeout. Only
    the ROM prints this line, so seeing it proves the chip really restarted
    and which mode it booted into (DOWNLOAD(...) would mean download mode)."""
    deadline = time.monotonic() + timeout
    buf = b""
    while time.monotonic() < deadline:
        try:
            chunk = ser.read(256)
        except (OSError, serial.SerialException):
            return None
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            m = BANNER_RE.search(raw.decode("utf-8", "replace"))
            if m:
                return m.group(2), m.group(4)
    return None


def wait_for_port(port, timeout=REENUMERATE_TIMEOUT_S, gone_grace=0.3):
    """Wait for the port node to disappear (within gone_grace, if it does at
    all) and come back. Returns seconds waited. Raises TimeoutError.
    Sets wait_for_port.last_gone to whether the node was seen to vanish."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < gone_grace and os.path.exists(port):
        time.sleep(0.005)
    wait_for_port.last_gone = not os.path.exists(port)
    while not os.path.exists(port):
        if time.monotonic() - t0 > timeout:
            raise TimeoutError(f"{port} did not re-enumerate within {timeout:.0f} s")
        time.sleep(0.05)
    # udev needs a moment to apply permissions after the node appears
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if os.access(port, os.R_OK | os.W_OK):
            break
        time.sleep(0.05)
    return time.monotonic() - t0


def reset_board(port=DEFAULT_PORT, timeout=REENUMERATE_TIMEOUT_S):
    """Open the port exclusively, pulse reset, read the ROM banner, wait for
    the port. Returns (t_reset, seconds_until_port_back, banner_or_None)."""
    ser = open_exclusive(port)
    banner = None
    try:
        ser.reset_input_buffer()
        t_reset = pulse(ser)
        banner = read_banner(ser)
    finally:
        try:
            ser.close()
        except (OSError, serial.SerialException):
            pass
    waited = wait_for_port(port, timeout)
    return t_reset, waited, banner


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=REENUMERATE_TIMEOUT_S)
    args = ap.parse_args()
    try:
        _, waited, banner = reset_board(args.port, args.timeout)
    except (TimeoutError, serial.SerialException, OSError) as e:
        print(f"reset.py: FAIL: {e}")
        return 1
    how = "re-enumerated" if wait_for_port.last_gone else "node never disappeared"
    rom = f"ROM banner rst={banner[0]} boot={banner[1]}" if banner else "no ROM banner within timeout"
    print(f"reset.py: reset pulsed, {rom}, {args.port} back after {waited:.2f} s ({how})")
    return 0 if banner else 1


if __name__ == "__main__":
    sys.exit(main())
