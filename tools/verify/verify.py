#!/usr/bin/env python3
"""Acceptance Harness (spec: Harness). Runs unattended: never prompts, stdin
is not read (every subprocess gets /dev/null). Prints PASS/FAIL per Check and
one final `RESULT: PASS|FAIL (n/m checks)` line; exit 0 only on PASS.

    ./verify.sh                 build, guard, identify, reset + capture, Checks (checks the running image)
    ./verify.sh --flash         same, with `build.sh flash` (--chip esp32c6 pinned) before the capture
    ./verify.sh --replay LOG    run the capture Checks over a saved capture log; no board, no lock, no build
    ./verify.sh --seconds N     capture window after the reset (default 20 s; the boot's [WDT] armed marker ends the capture early)
    ./verify.sh --soak N        idle mode: after the boot keep capturing N s (default 60) and fail on any reset
                                (no spurious watchdog bite); not part of the default run
    ./verify.sh --bite          watchdog bite scenario (separate mode, not part of the default run): builds the
                                debug image (debug.conf, build dir build-debug), flashes it, types `debug hang`, expects
                                a reset within ~5 s and `[BOOT] reason=watchdog`; then ALWAYS rebuilds and re-flashes
                                the production image, runs the default Checks on it and shows that `debug hang` is
                                refused there

The Harness holds the board lock (/tmp/<port>.lock) for the whole run and
passes C6_BOARD_LOCK_HELD=1 to build.sh so its calls do not wait on it. The
capture log is kept at <build dir>/verify/capture-<stamp>.log.

Checks so far (pure logic in checks.py, unit-tested by test_checks.py):
  build.sh build produces zephyr.bin; the esptool guard; chip_id 13 (identify);
  [--flash] build.sh flash; `[BOOT] reason=<cause>` present in the capture; Self-test done
  (and its readbacks at 0, 128, 255 in tolerance); `[LED] brightness=128` after it with duty
  50 +- 1 % low and freq near 20 kHz; `[WDT] armed window=5000ms` after the Self-test; marker order
  [BOOT] -> selftest -> [LED] -> [WDT] -> [BLE] advertising; the production build carries no hang command.
  Then, as a Central (bleak) with the console recorded meanwhile (BackgroundCapture): the board is found by
  name and NUS UUID; connect + subscribe; console `[BLE] connected` then `[BLE] mtu=247`; a second scan while
  connected does not see the board (link stays up; an attempt whose link the PC's radio dropped during the
  scan is repeated, at most 3 attempts) and the console shows no advertising while the Connection exists;
  disconnect -> `[BLE] disconnected reason=0x13` and advertising again; found again, reconnect with the same
  markers; final disconnect leaves the board advertising.
  Shell link (ticket 07), a second Central scenario: `led set 0|128|255` reply exactly `LED <n>` and print
  `[LED]` with the Duty readback in tolerance; `led set 300`, `led set abc`, `led set` reply `ERR ` and apply
  nothing (`led get` unchanged); the received stream holds nothing but reply lines; after a disconnect and
  reconnect `led get` returns the value set before; then the same `led` commands typed on the serial shell.
  Command restriction (ticket 08), on the same Shell link Connection: `kernel reboot` answers `ERR command not
  allowed` and no [BOOT] follows within 5 s, `led get` still works on that Connection; other commands
  (`kernel reboot cold`, `kernel version`, `help`, `device list`, a bare `led`, `led set -h`, an escape
  sequence, and a second command smuggled behind a `\\r`) each answer one such ERR line and reset nothing
  (ADR-0001: no kernel or device command on the link). Last of all, `kernel reboot` typed on the serial shell
  resets the board (`[BOOT] reason=software`).
"""
import argparse
import asyncio
import datetime
import fcntl
import os
import re
import subprocess
import sys
import threading
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "board"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks  # noqa: E402
import console  # noqa: E402
import reset as board_reset  # noqa: E402

BUILD_DIR = os.environ.get("C6_BUILD_DIR", os.path.join(ROOT, "build"))
DEBUG_BUILD_DIR = os.path.join(ROOT, "build-debug")
DEBUG_CONF = os.path.join(ROOT, "debug.conf")
SOAK_DEFAULT_S = 60.0
SOAK_BOOT_SLACK_S = 8.0     # boot (~4 s to the armed marker) plus margin, before the idle window counts
BITE_LIMIT_S = 7.0          # window 5 s, the last feed is up to 1 s old: 4..5 s, plus the ROM start
BITE_CAPTURE_S = 25.0       # hang marker + bite + 2 s boot delay, with margin
REFUSED_WINDOW_S = 8.0
CAPTURE_WINDOW_S = 20.0
BLE_MTU = 247                # spec: ATT MTU raised to 247
BLE_REMOTE_TERMINATED = 0x13 # HCI reason the board sees when the Central disconnects
BLE_SCAN_S = 10.0            # find the board: many advertising intervals (100 to 150 ms)
BLE_HIDDEN_SCAN_S = 3.0      # second scan while connected; shorter = less radio time taken from the link
BLE_MARKER_WAIT_S = 5.0      # a marker follows its cause within this
BLE_HIDDEN_ATTEMPTS = 3      # the PC's radio can drop the link while it scans; see run_ble
BLE_SCENARIO_S = 120.0       # bound on the whole Central scenario
SHELL_MARKER_WAIT_S = 3.0    # an applied Brightness prints its [LED] marker within this
SHELL_SETTLE_S = 0.3         # after a rejected command, wait this long for a marker that must not come
SHELL_SERIAL_S = 10.0        # bound on typing the `led` commands on the serial shell
REBOOT_WINDOW_S = 5.0        # a refused `kernel reboot` must show no [BOOT] in this window (ticket 08)
SERIAL_REBOOT_S = 20.0       # `kernel reboot` on the serial shell: the [BOOT] marker follows within this
BLE_LOG_TAIL_S = 1.0         # keep capturing this long after the last step
LOCK_WAIT_S = 5.0
# Bounds on the build.sh calls (the Harness never waits for ever while it holds the lock):
BUILD_TIMEOUT_S = {"build": 900, "guard": 60, "identify": 60, "flash": 180}
# console.fmt() output: "HH:MM:SS.mmm +  1.234s text"
LOG_LINE_RE = re.compile(r"^(\d\d:\d\d:\d\d\.\d{3}) \+\s*(-?[0-9.]+)s (.*)$")

STALE_NOTE_RE = re.compile(r"^<console: \d+ stale line\(s\) above predate the reset>$")

A_BUILD = "build.sh build produces zephyr.bin"
A_GUARD = "esptool guard: esptool-build launcher only, no importable esptool"
A_IDENTIFY = "build.sh identify sees chip_id 13"
A_FLASH = "build.sh flash writes the image via esptool-build --chip esp32c6"
A_BOOT = "[BOOT] reason=<cause> present"
A_SELFTEST = "[STAGE] selftest: done"
A_SELFTEST_RB = "Self-test Duty readbacks at 0, 128, 255 in tolerance"
A_BOOT_LED = "[LED] brightness=128 after the Self-test, duty 50 +- 1 % low, freq near 20 kHz"
A_WDT = "[WDT] armed window=5000ms after the Self-test"
A_BLE_ADV = "[BLE] advertising name=XIAO-C6-LED after [WDT] armed"
A_ORDER = "marker order: [BOOT] -> selftest -> [LED] -> [WDT] -> [BLE] advertising"
A_BLE_FOUND = "Central finds the board by name XIAO-C6-LED and NUS UUID"
A_BLE_CONNECT = "Central connects and subscribes to NUS notifications"
A_BLE_MARKERS = "console: [BLE] connected, then [BLE] mtu=247"
A_BLE_HIDDEN = "second scan while connected does not see the board (link stays up)"
A_BLE_SILENT = "console: no [BLE] advertising while the Connection exists"
A_BLE_DISC = "Central disconnects: console [BLE] disconnected reason=0x13, then advertising again"
A_BLE_REFOUND = "Central finds the board again after the disconnect"
A_BLE_RECONNECT = "Central reconnects: console [BLE] connected, then [BLE] mtu=247"
A_BLE_LEFT = "final disconnect leaves the board advertising"
A_SHELL_FOUND = "Shell link: Central finds the board and connects"
A_SHELL_CLEAN = "Shell link: nothing but reply lines arrives (no echo, prompt, escape sequence or CR)"
A_SHELL_PERSIST = "Shell link: after disconnect and reconnect `led get` returns the value set before"
A_SHELL_RESTORE = "Shell link: `led set 128` on the second Connection restores the boot level"
A_SHELL_LEFT = "Shell link: final disconnect leaves the board advertising"
A_SERIAL_LED = "serial shell: `led set` / `led get` reply as on the Shell link"
A_SERIAL_MARKERS = "serial shell: `led set 0`, `255`, `128` print [LED] with Duty readback in tolerance"
A_SERIAL_ERR = "serial shell: only the three applied commands print [LED] (`led set 300|abc|<none>` apply nothing)"
A_REFUSE_REBOOT = ("Shell link: `kernel reboot` is refused with `ERR command not allowed` and the board does not "
                   "reset (no [BOOT] within 5 s)")
A_REFUSE_ALIVE = "Shell link: after the refused `kernel reboot` the same Connection still answers `led get` with LED 128"
A_REFUSE_OTHERS = "Shell link: every other command outside the allow-list, and each input trick, is refused, one ERR line each"
A_REFUSE_QUIET = "Shell link: none of the refused input reset the board or printed anything but the refusal"
A_SERIAL_REBOOT = "serial shell: `kernel reboot` resets the board, next boot [BOOT] reason=software"
A_NOHANG = "production build carries no hang command"
A_SOAK = "idle: no reset (no spurious watchdog bite)"
A_BITE = "debug image: hang command leads to a reset within ~5 s, next boot reason=watchdog"
A_REFUSED = "production image: hang command refused, no reset"


class BackgroundCapture:
    """A console capture (no reset) in a thread, so the board's markers are recorded while the
    Harness acts as a Central. `lines` grows as the board prints (list.append is atomic);
    `mark()` / `since(mark)` slice it. The capture ends at stop() or after `seconds`."""

    def __init__(self, port, log_path, seconds):
        self.port, self.log_path, self.seconds = port, log_path, seconds
        self.lines = []
        self.error = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="console-capture", daemon=True)

    def _run(self):
        try:
            with open(self.log_path, "w") as f:
                def sink(t, w, s):
                    self.lines.append((t, w, s))
                    f.write(console.fmt(t, w, s) + "\n")
                    f.flush()
                console.capture(self.port, self.seconds, do_reset=False, sink=sink,
                                on_ready=self._ready.set, stop_event=self._stop)
        except BaseException as e:      # reported by start()/stop(), never lost in the thread
            self.error = e
        finally:
            self._ready.set()

    def start(self, ready_timeout=5.0):
        self._thread.start()
        if not self._ready.wait(ready_timeout) or self.error:
            self._stop.set()
            raise OSError(f"console capture did not start: {self.error or 'timeout'}")

    def stop(self, tail_s=0.0):
        time.sleep(tail_s)
        self._stop.set()
        self._thread.join(10.0)
        if self._thread.is_alive():
            raise OSError("console capture thread did not stop")
        if self.error:
            raise OSError(f"console capture failed: {self.error}")

    def mark(self):
        return len(self.lines)

    def since(self, mark):
        return list(self.lines[mark:])

    async def wait_check(self, mark, check, timeout):
        """Poll `check(lines since mark)` until it passes or `timeout` s; returns its last (ok, detail)."""
        deadline = time.monotonic() + timeout
        while True:
            ok, detail = check(self.since(mark))
            if ok or time.monotonic() >= deadline:
                return ok, detail
            await asyncio.sleep(0.05)


class Harness:
    def __init__(self, args):
        self.args = args
        self.results = []      # (name, ok, detail)
        self.lines = []        # (t_rel, wallclock, text)
        self.log_path = None
        self.t_start = time.monotonic()
        self.build_dir = BUILD_DIR
        self.build_env = {}
        self.capture_elapsed = 0.0   # measured length of the last capture

    def check(self, name, ok, detail=""):
        self.results.append((name, bool(ok), detail))
        print(checks.format_check(name, bool(ok), detail), flush=True)
        return bool(ok)

    def run_build_sh(self, *cmd):
        env = dict(os.environ, C6_BOARD_LOCK_HELD="1", C6_PORT=self.args.port, C6_BUILD_DIR=self.build_dir,
                   **self.build_env)
        try:
            p = subprocess.run([os.path.join(ROOT, "build.sh"), *cmd], env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               timeout=BUILD_TIMEOUT_S[cmd[0]])
        except subprocess.TimeoutExpired as e:
            return 124, f"build.sh {cmd[0]} timed out after {e.timeout} s\n"
        return p.returncode, p.stdout

    # -- steps (glue, proven on the board) ---------------------------------
    def step_build(self):
        rc, out = self.run_build_sh("build")
        binp = os.path.join(self.build_dir, "zephyr", "zephyr.bin")
        ok = rc == 0 and os.path.isfile(binp) and os.path.getsize(binp) > 0
        if not ok:
            print(out[-3000:])
        return self.check(A_BUILD, ok, f"{os.path.getsize(binp)} bytes" if ok else f"rc={rc}")

    def step_guard(self):
        rc, out = self.run_build_sh("guard")
        if rc != 0:
            print(out[-2000:])
        last = out.strip().splitlines()[-1] if out.strip() else ""
        return self.check(A_GUARD, rc == 0, last)

    def step_identify(self):
        rc, out = self.run_build_sh("identify")
        m = re.search(r"chip_id:\s*(\d+)", out)
        ok = rc == 0 and m is not None and m.group(1) == "13"
        if not ok:
            print(out[-2000:])
        return self.check(A_IDENTIFY, ok, f"chip_id={m.group(1) if m else '?'}")

    def step_flash(self):
        rc, out = self.run_build_sh("flash")
        ok = rc == 0   # esptool-build verifies the MD5 itself and exits non-zero on a mismatch
        if not ok:
            print(out[-2000:])
        else:
            board_reset.wait_for_port(self.args.port)   # a re-enumeration, should one ever happen
        md5 = re.search(r"MD5[^\n]*", out)
        return self.check(A_FLASH, ok, md5.group(0) if (ok and md5) else f"rc={rc}")

    def capture_to_log(self, seconds, do_reset, stop_when=None, send=None, tag="capture"):
        """One console capture, also written to <build dir>/verify/<tag>-<stamp>.log."""
        os.makedirs(os.path.join(BUILD_DIR, "verify"), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = os.path.join(BUILD_DIR, "verify", f"{tag}-{stamp}.log")
        with open(self.log_path, "w") as f:
            def sink(t, w, s):
                f.write(console.fmt(t, w, s) + "\n")
                f.flush()
            t0 = time.monotonic()
            lines = console.capture(self.args.port, seconds, do_reset=do_reset, stop_when=stop_when,
                                    sink=sink, send=send)
            self.capture_elapsed = time.monotonic() - t0
        print(f"captured {len(lines)} lines in {self.capture_elapsed:.1f} s -> {self.log_path}", flush=True)
        return lines

    def step_capture(self, seconds=None, stop_when="boot"):
        seconds = self.args.seconds if seconds is None else seconds
        self.lines = self.capture_to_log(seconds, True,
                                         checks.BootCaptureDone() if stop_when == "boot" else None)

    def load_replay(self, path):
        """Rebuild the capture the live run returned: console.capture() drops what
        arrived before the ROM banner and leaves this note in the log instead."""
        self.lines = []
        with open(path, errors="replace") as f:
            for raw in f:
                m = LOG_LINE_RE.match(raw.rstrip("\n"))
                if not m:
                    continue
                if STALE_NOTE_RE.match(m.group(3)):
                    self.lines = []
                    continue
                self.lines.append((float(m.group(2)), None, m.group(3)))
        self.log_path = path
        print(f"replaying {len(self.lines)} lines from {path}", flush=True)

    # -- Checks over the capture -------------------------------------------
    def capture_checks(self):
        ok, detail = checks.check_boot_marker(self.lines)
        self.check(A_BOOT, ok, detail)
        self.check(A_SELFTEST, *checks.check_selftest_done(self.lines))
        self.check(A_SELFTEST_RB, *checks.check_selftest_readbacks(self.lines))
        self.check(A_BOOT_LED, *checks.check_boot_brightness(self.lines))
        self.check(A_WDT, *checks.check_wdt_armed(self.lines))
        self.check(A_BLE_ADV, *checks.check_ble_advertising(self.lines))
        self.check(A_ORDER, *checks.check_marker_order(self.lines))

    def check_production_has_no_hang(self):
        """Static half of "the production image has no hang command": its .config and image."""
        try:
            with open(os.path.join(BUILD_DIR, "zephyr", ".config")) as f:
                cfg = f.read()
            with open(os.path.join(BUILD_DIR, "zephyr", "zephyr.bin"), "rb") as f:
                image = f.read()
        except OSError as e:
            return self.check(A_NOHANG, False, str(e))
        return self.check(A_NOHANG, *checks.check_no_hang_command(cfg, image))

    # -- the Harness as a Central (glue; the decisions are in central_logic.py / checks.py) --
    def run_ble(self):
        """Advertising and one Connection, proven as a Central with the console recorded meanwhile."""
        os.makedirs(os.path.join(BUILD_DIR, "verify"), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = os.path.join(BUILD_DIR, "verify", f"ble-{stamp}.log")
        cap = BackgroundCapture(self.args.port, self.log_path, BLE_SCENARIO_S + 30.0)
        try:
            cap.start()
        except OSError as e:
            return self.check("console capture (Bluetooth scenario)", False, str(e))
        try:
            asyncio.run(asyncio.wait_for(self.ble_scenario(cap), BLE_SCENARIO_S))
        except asyncio.TimeoutError:
            self.check("Bluetooth scenario finishes", False, f"not done after {BLE_SCENARIO_S:.0f} s")
        except Exception as e:      # bleak / BlueZ / D-Bus: report what was seen, exactly
            self.check("Bluetooth scenario runs", False, f"{type(e).__name__}: {e}")
        finally:
            try:
                cap.stop(BLE_LOG_TAIL_S)
            except OSError as e:
                self.check("console capture (Bluetooth scenario)", False, str(e))
        print(f"captured {len(cap.lines)} lines -> {self.log_path}", flush=True)

    async def ble_scenario(self, cap):
        import central

        dev = None
        conn = None
        try:
            t0 = time.monotonic()
            dev = await central.find_board(BLE_SCAN_S)
            if not self.check(A_BLE_FOUND, dev is not None,
                              f"{dev.address} in {time.monotonic() - t0:.1f} s" if dev else
                              f"no advertisement with the name and UUID in {BLE_SCAN_S:.0f} s"):
                return

            # Connect; a second scan while connected must not see the board. The PC's radio can
            # drop the link while it scans (supervision timeout on the board, reason 0x08), which
            # says nothing about the firmware, so an attempt whose link dropped is repeated; a
            # scan that sees the board while the link is up fails at once.
            hidden_ok, hidden_detail = False, ""
            for attempt in range(1, BLE_HIDDEN_ATTEMPTS + 1):
                note = f" (attempt {attempt})" if attempt > 1 else ""
                mark = cap.mark()
                conn = central.CentralConnection(dev)
                t0 = time.monotonic()
                await conn.open()
                connect = (conn.connected, f"connected in {time.monotonic() - t0:.1f} s, "
                           f"write payload {conn.write_payload} bytes{note}")
                markers = await cap.wait_check(mark, lambda ls: checks.check_ble_connected(ls, BLE_MTU),
                                               BLE_MARKER_WAIT_S)
                t0 = time.monotonic()
                seen = await central.find_board(BLE_HIDDEN_SCAN_S)
                if seen is not None and conn.connected:
                    hidden_ok, hidden_detail = False, f"scan saw {seen.address} while the link was up"
                    break
                if conn.connected:
                    hidden_ok = True
                    hidden_detail = (f"no advertisement in {time.monotonic() - t0:.1f} s of scanning, "
                                     f"link still up{note}")
                    break
                hidden_detail = f"the link dropped during the scan in all {attempt} attempt(s)"
                await conn.close()
                await cap.wait_check(mark, lambda ls: checks.check_ble_disconnected(ls, None), BLE_MARKER_WAIT_S)
                # the board advertises again; a fresh scan gives BlueZ the device back
                dev = await central.find_board(BLE_SCAN_S)
                if dev is None:
                    hidden_detail += "; the board did not advertise again"
                    break
            self.check(A_BLE_CONNECT, *connect)
            self.check(A_BLE_MARKERS, *markers)
            self.check(A_BLE_HIDDEN, hidden_ok, hidden_detail)
            if conn is None or not conn.connected:
                return

            await conn.close()
            ok, detail = await cap.wait_check(mark, lambda ls: checks.check_ble_disconnected(ls, BLE_REMOTE_TERMINATED),
                                              BLE_MARKER_WAIT_S)
            self.check(A_BLE_DISC, ok, detail)
            self.check(A_BLE_SILENT, *checks.check_ble_silent_while_connected(cap.since(mark)))

            # Advertising again: the Central finds the board and reconnects.
            t0 = time.monotonic()
            dev = await central.find_board(BLE_SCAN_S)
            if not self.check(A_BLE_REFOUND, dev is not None,
                              f"{dev.address} in {time.monotonic() - t0:.1f} s" if dev else
                              f"not advertising again within {BLE_SCAN_S:.0f} s"):
                return
            mark = cap.mark()
            conn = central.CentralConnection(dev)
            await conn.open()
            ok, detail = await cap.wait_check(mark, lambda ls: checks.check_ble_connected(ls, BLE_MTU),
                                              BLE_MARKER_WAIT_S)
            self.check(A_BLE_RECONNECT, ok and conn.connected, detail)

            await conn.close()
            ok, detail = await cap.wait_check(mark, lambda ls: checks.check_ble_disconnected(ls, BLE_REMOTE_TERMINATED),
                                              BLE_MARKER_WAIT_S)
            self.check(A_BLE_LEFT, ok, detail)
        finally:
            # Never leave the one Connection up: it hides the board from the next run.
            if conn is not None and conn.connected:
                try:
                    await conn.close()
                except Exception as e:
                    print(f"harness: closing the Connection failed: {type(e).__name__}: {e}", flush=True)

    # -- the Shell link (ticket 07) ----------------------------------------------
    def run_shell_link(self):
        """`led` commands over the Shell link with the console recorded meanwhile, then the same
        commands on the serial shell."""
        os.makedirs(os.path.join(BUILD_DIR, "verify"), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = os.path.join(BUILD_DIR, "verify", f"shell-{stamp}.log")
        cap = BackgroundCapture(self.args.port, self.log_path, BLE_SCENARIO_S + 30.0)
        try:
            cap.start()
        except OSError as e:
            return self.check("console capture (Shell link scenario)", False, str(e))
        try:
            asyncio.run(asyncio.wait_for(self.shell_scenario(cap), BLE_SCENARIO_S))
        except asyncio.TimeoutError:
            self.check("Shell link scenario finishes", False, f"not done after {BLE_SCENARIO_S:.0f} s")
        except Exception as e:
            self.check("Shell link scenario runs", False, f"{type(e).__name__}: {e}")
        finally:
            try:
                cap.stop(BLE_LOG_TAIL_S)
            except OSError as e:
                self.check("console capture (Shell link scenario)", False, str(e))
        print(f"captured {len(cap.lines)} lines -> {self.log_path}", flush=True)
        self.run_serial_led()
        self.run_serial_reboot()

    @staticmethod
    async def ask(conn, command):
        """The Reply to a command, or None when no reply line came in time."""
        try:
            return await conn.request(command)
        except asyncio.TimeoutError:
            return None

    async def shell_scenario(self, cap):
        import central
        import central_logic as cl

        conn = None
        try:
            dev = await central.find_board(BLE_SCAN_S)
            if dev is None:
                self.check(A_SHELL_FOUND, False, f"no advertisement in {BLE_SCAN_S:.0f} s")
                return
            conn = central.CentralConnection(dev)
            await conn.open()
            if not self.check(A_SHELL_FOUND, conn.connected, f"{dev.address}"):
                return

            # led set 0 / 128 / 255: exact reply and the console's Duty readback.
            for n in (0, 128, 255):
                mark = cap.mark()
                reply = await self.ask(conn, f"led set {n}")
                ok, detail = cl.expect_led_reply(reply, n)
                self.check(f"led set {n} over the Shell link replies exactly LED {n}", ok, detail)
                ok, detail = await cap.wait_check(mark, lambda ls, n=n: checks.check_led_applied(ls, n),
                                                  SHELL_MARKER_WAIT_S)
                self.check(f"led set {n} over the Shell link prints [LED] brightness={n}, Duty readback in tolerance",
                           ok, detail)

            # Rejected input: ERR line, no [LED] marker, Brightness unchanged (still 255).
            for cmd in ("led set 300", "led set abc", "led set"):
                mark = cap.mark()
                reply = await self.ask(conn, cmd)
                ok_err, d_err = cl.expect_err_reply(reply)
                await asyncio.sleep(SHELL_SETTLE_S)
                ok_mark, d_mark = checks.check_no_led_marker(cap.since(mark))
                ok_get, d_get = cl.expect_led_reply(await self.ask(conn, "led get"), 255)
                self.check(f"`{cmd}` over the Shell link replies ERR, applies nothing, `led get` still LED 255",
                           ok_err and ok_mark and ok_get,
                           f"{d_err}; {d_mark}; led get: {d_get}")

            self.check(A_SHELL_CLEAN, *cl.check_clean_stream(bytes(conn.raw), conn.lines))

            # Disconnect, reconnect: the Brightness set before is still there.
            mark = cap.mark()
            await conn.close()
            await cap.wait_check(mark, lambda ls: checks.check_ble_disconnected(ls, None), BLE_MARKER_WAIT_S)
            dev = await central.find_board(BLE_SCAN_S)
            if dev is None:
                self.check(A_SHELL_PERSIST, False, "the board did not advertise again")
                return
            conn = central.CentralConnection(dev)
            await conn.open()
            ok, detail = cl.expect_led_reply(await self.ask(conn, "led get"), 255)
            self.check(A_SHELL_PERSIST, ok, detail)

            # Put the boot level back; the second Connection's stream must be clean too.
            mark = cap.mark()
            ok, detail = cl.expect_led_reply(await self.ask(conn, "led set 128"), 128)
            ok_led, d_led = await cap.wait_check(mark, lambda ls: checks.check_led_applied(ls, 128),
                                                 SHELL_MARKER_WAIT_S)
            self.check(A_SHELL_RESTORE, ok and ok_led, f"{detail}; {d_led}")
            ok_clean, d_clean = cl.check_clean_stream(bytes(conn.raw), conn.lines)
            self.check(A_SHELL_CLEAN + " (second Connection)", ok_clean, d_clean)

            await self.refusal_checks(conn, cap)

            mark = cap.mark()
            await conn.close()
            ok, detail = await cap.wait_check(mark, lambda ls: checks.check_ble_disconnected(ls, BLE_REMOTE_TERMINATED),
                                              BLE_MARKER_WAIT_S)
            self.check(A_SHELL_LEFT, ok, detail)
        finally:
            if conn is not None and conn.connected:
                try:
                    await conn.close()
                except Exception as e:
                    print(f"harness: closing the Connection failed: {type(e).__name__}: {e}", flush=True)

    # Input the Shell link must refuse; each one answers exactly one refusal line. The last four try
    # to get past the filter: extra spaces, a second command behind "\r" (the shell reads "\r" as
    # Enter), an escape sequence, a tab.
    REFUSED_INPUT = (b"kernel reboot cold\n", b"kernel version\n", b"kernel uptime\n", b"help\n", b"device list\n",
                     b"kernel threads\n", b"debug hang\n",
                     b"led\n", b"led set -h\n", b"  kernel   reboot  \n", b"led get\rkernel reboot\n",
                     b"led get\x1b[A\n", b"led\tget\n")

    async def refusal_checks(self, conn, cap):
        """Ticket 08: the Shell link offers only `led set` / `led get` (ADR-0001: no kernel or device command)."""
        import central_logic as cl

        # `kernel reboot`: refused, and the board does not reset within the window.
        mark = cap.mark()
        t0 = time.monotonic()
        reply = await self.ask(conn, "kernel reboot")
        ok_reply, d_reply = cl.expect_refusal(reply)
        # the window plus half a second, so a reset at the very end of it still prints its banner
        await asyncio.sleep(max(0.0, REBOOT_WINDOW_S + 0.5 - (time.monotonic() - t0)))
        ok_boot, d_boot = checks.check_no_reboot(cap.since(mark), REBOOT_WINDOW_S,
                                                 observed_s=time.monotonic() - t0)
        self.check(A_REFUSE_REBOOT, ok_reply and ok_boot, f"{d_reply}; {d_boot}")
        ok, detail = cl.expect_led_reply(await self.ask(conn, "led get") if conn.connected else None, 128)
        self.check(A_REFUSE_ALIVE, ok and conn.connected, detail)
        if not conn.connected:
            return

        # Everything else outside the allow-list, and the tricks.
        mark = cap.mark()
        t1 = time.monotonic()
        first = len(conn.lines)
        failed = []
        for data in self.REFUSED_INPUT:
            ok, detail = cl.expect_refusal(await self.ask_bytes(conn, data))
            if not ok:
                failed.append(f"{data!r}: {detail}")
        self.check(A_REFUSE_OTHERS, not failed,
                   "; ".join(failed) if failed else f"{len(self.REFUSED_INPUT)} inputs, each ERR command not allowed")
        await asyncio.sleep(SHELL_SETTLE_S)
        ok_lines, d_lines = cl.expect_only_refusals(conn.lines[first:], len(self.REFUSED_INPUT))
        ok_boot, d_boot = checks.check_no_reboot(cap.since(mark), 0.0, observed_s=time.monotonic() - t1)
        ok_led, d_led = cl.expect_led_reply(await self.ask(conn, "led get"), 128)
        self.check(A_REFUSE_QUIET, ok_lines and ok_boot and ok_led and conn.connected,
                   f"{d_lines}; {d_boot}; led get: {d_led}")

    @staticmethod
    async def ask_bytes(conn, data):
        try:
            return await conn.request_bytes(data)
        except asyncio.TimeoutError:
            return None

    def run_serial_reboot(self):
        """`kernel reboot` typed on the serial shell (which keeps every command) resets the board. Last
        step of the run: the board restarts and advertises again."""
        try:
            lines = self.capture_to_log(SERIAL_REBOOT_S, False, stop_when=checks.is_boot_line,
                                        send=b"kernel reboot\r\n", tag="serial-reboot")
        except (OSError, TimeoutError) as e:
            self.check("console capture (serial shell reboot)", False, str(e))
            return
        self.check(A_SERIAL_REBOOT, *checks.check_boot_reason(lines, "software"))

    def run_serial_led(self):
        """The same commands typed on the serial shell (the console keeps every command)."""
        want = ["LED 0", "LED 0", "LED 255", "ERR", "ERR", "ERR", "LED 255", "LED 128"]
        # Two short bursts: the serial shell's RX ring (with echo and the colour codes it prints)
        # overflows on about 80 bytes typed at once ("RX ring buffer full"), which loses commands.
        bursts = [(b"led set 0\r\nled get\r\nled set 255\r\nled set 300\r\n", lambda t: t.startswith("ERR ")),
                  (b"led set abc\r\nled set\r\nled get\r\nled set 128\r\n", lambda t: t.strip() == "LED 128")]
        lines = []
        for n, (script, stop) in enumerate(bursts, 1):
            try:
                lines += self.capture_to_log(SHELL_SERIAL_S, False, stop_when=stop, send=script,
                                             tag=f"serial-led{n}")
            except (OSError, TimeoutError) as e:
                self.check("console capture (serial shell)", False, str(e))
                return
        self.check(A_SERIAL_LED, *checks.check_serial_led_replies(lines, want))
        detail = "; ".join(checks.check_led_applied(lines, b)[1] for b in (0, 255, 128))
        self.check(A_SERIAL_MARKERS, all(checks.check_led_applied(lines, b)[0] for b in (0, 255, 128)), detail)
        # eight commands, three applied (0, 255, 128): the three rejected ones must not print a marker
        markers = [text.strip() for _, _, text in lines if checks.parse_led(text)]
        self.check(A_SERIAL_ERR, [m.split()[1] for m in markers] == ["brightness=0", "brightness=255", "brightness=128"],
                   f"{len(markers)} [LED] marker(s): {markers}")

    # -- separate modes ----------------------------------------------------
    def run_soak(self):
        """Idle mode: after the boot keep capturing and fail on any reset."""
        seconds = SOAK_BOOT_SLACK_S + self.args.soak
        print(f"soak: capturing {seconds:.0f} s after the reset", flush=True)
        self.step_capture(seconds=seconds, stop_when=None)
        self.check(A_SOAK, *checks.check_idle_no_bite(self.lines, self.args.soak, observed_s=self.capture_elapsed))

    def run_bite(self):
        """Watchdog bite scenario on the debug image, then the production image is restored."""
        self.build_dir = DEBUG_BUILD_DIR
        self.build_env = {"C6_EXTRA_CONF": DEBUG_CONF}
        try:
            self.bite_on_debug_image()
        finally:
            self.build_dir = BUILD_DIR
            self.build_env = {}
            print("restore: rebuilding and re-flashing the production image", flush=True)
            self.restore_production()

    def bite_on_debug_image(self):
        if not (self.step_build() and self.step_guard() and self.step_identify()):
            return
        if not self.step_flash():
            return
        try:
            self.step_capture()
            self.check(A_WDT + " (debug image)", *checks.check_wdt_armed(self.lines))
            # Second capture, no reset: type the command, wait for the bite and the next boot marker.
            lines = self.capture_to_log(BITE_CAPTURE_S, False, stop_when=checks.is_boot_line,
                                        send=b"debug hang\r\n", tag="bite")
        except (OSError, TimeoutError) as e:
            self.check("console capture (debug image)", False, str(e))
            return
        self.check(A_BITE, *checks.check_wdt_bite(lines, BITE_LIMIT_S))

    def restore_production(self):
        if not (self.step_build() and self.step_guard() and self.step_flash()):
            return
        try:
            self.step_capture()
            self.capture_checks()
            self.check_production_has_no_hang()
            lines = self.capture_to_log(REFUSED_WINDOW_S, False, send=b"debug hang\r\n", tag="refused")
        except (OSError, TimeoutError) as e:
            self.check("console capture (production image)", False, str(e))
            return
        self.check(A_REFUSED, *checks.check_hang_refused(lines, REFUSED_WINDOW_S, observed_s=self.capture_elapsed))

    def finish(self):
        if self.log_path:
            print(f"capture log: {self.log_path}")
        print(f"elapsed: {time.monotonic() - self.t_start:.0f} s")
        print(checks.format_result(self.results), flush=True)
        return checks.exit_code(self.results)

    def run(self):
        if self.args.replay:
            self.load_replay(self.args.replay)
            self.capture_checks()
            return self.finish()
        if self.args.bite:
            self.run_bite()
            return self.finish()
        build_ok = self.step_build()
        guard_ok = self.step_guard()
        if not (build_ok and guard_ok and self.step_identify()):
            return self.finish()
        if self.args.flash and not self.step_flash():
            return self.finish()
        try:
            if self.args.soak:
                self.run_soak()
                return self.finish()
            self.step_capture()
        except (OSError, TimeoutError) as e:
            self.check("console capture", False, str(e))
            return self.finish()
        self.capture_checks()
        self.check_production_has_no_hang()
        self.run_ble()
        self.run_shell_link()
        return self.finish()


def take_lock(port):
    """Hold /tmp/<port>.lock (the same file build.sh's board_lock uses) until exit."""
    path = "/tmp/" + port.replace("/", "_") + ".lock"
    f = open(path, "w")
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except BlockingIOError:
            if time.monotonic() > deadline:
                f.close()
                print(f"harness: board busy: another tool holds {path}", flush=True)
                return None
            time.sleep(0.2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flash", action="store_true", help="flash the fresh build before capturing")
    ap.add_argument("--replay", metavar="LOG", help="run the capture Checks over a saved capture log (no board)")
    ap.add_argument("--port", default=os.environ.get("C6_PORT", board_reset.DEFAULT_PORT))
    ap.add_argument("--seconds", type=float, default=CAPTURE_WINDOW_S, help="capture window after the reset")
    ap.add_argument("--soak", nargs="?", type=float, const=SOAK_DEFAULT_S, default=0.0, metavar="N",
                    help="idle mode: keep capturing N s after the boot (default 60) and fail on any reset")
    ap.add_argument("--bite", action="store_true",
                    help="watchdog bite scenario on the debug image; restores the production image afterwards")
    args = ap.parse_args()
    if args.bite and (args.replay or args.soak):
        ap.error("--bite is a mode of its own (no --replay, no --soak)")
    if args.soak and args.replay:
        ap.error("--soak needs the board; it cannot be combined with --replay")
    if args.seconds <= 0:
        ap.error("--seconds must be positive (console.capture treats 0 as no limit)")
    if args.replay and args.flash:
        ap.error("--flash and --replay cannot be combined (a replay never touches the board)")

    if args.replay:
        return Harness(args).run()
    lock = take_lock(args.port)
    if lock is None:
        print(checks.format_result([]))
        return 1
    with lock:
        return Harness(args).run()


if __name__ == "__main__":
    sys.exit(main())
