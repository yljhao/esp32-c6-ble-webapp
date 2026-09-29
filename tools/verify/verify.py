#!/usr/bin/env python3
"""Acceptance Harness (spec: Harness). Runs unattended: never prompts, stdin
is not read (every subprocess gets /dev/null). Prints PASS/FAIL per Check and
one final `RESULT: PASS|FAIL (n/m checks)` line; exit 0 only on PASS.

    ./verify.sh                 build, guard, identify, reset + capture, Checks (checks the running image)
    ./verify.sh --flash         same, with `build.sh flash` (--chip esp32c6 pinned) before the capture
    ./verify.sh --replay LOG    run the capture Checks over a saved capture log; no board, no lock, no build
    ./verify.sh --seconds N     capture window after the reset (default 20 s; [BOOT] ends the capture early)

The Harness holds the board lock (/tmp/<port>.lock) for the whole run and
passes C6_BOARD_LOCK_HELD=1 to build.sh so its calls do not wait on it. The
capture log is kept at <build dir>/verify/capture-<stamp>.log.

Checks so far (pure logic in checks.py, unit-tested by test_checks.py):
  build.sh build produces zephyr.bin; the esptool guard; chip_id 13 (identify);
  [--flash] build.sh flash; `[BOOT] reason=<cause>` present in the capture.
"""
import argparse
import datetime
import fcntl
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools", "board"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks  # noqa: E402
import console  # noqa: E402
import reset as board_reset  # noqa: E402

BUILD_DIR = os.environ.get("C6_BUILD_DIR", os.path.join(ROOT, "build"))
CAPTURE_WINDOW_S = 20.0
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


class Harness:
    def __init__(self, args):
        self.args = args
        self.results = []      # (name, ok, detail)
        self.lines = []        # (t_rel, wallclock, text)
        self.log_path = None
        self.t_start = time.monotonic()

    def check(self, name, ok, detail=""):
        self.results.append((name, bool(ok), detail))
        print(checks.format_check(name, bool(ok), detail), flush=True)
        return bool(ok)

    def run_build_sh(self, *cmd):
        env = dict(os.environ, C6_BOARD_LOCK_HELD="1", C6_PORT=self.args.port)
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
        binp = os.path.join(BUILD_DIR, "zephyr", "zephyr.bin")
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

    def step_capture(self):
        os.makedirs(os.path.join(BUILD_DIR, "verify"), exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = os.path.join(BUILD_DIR, "verify", f"capture-{stamp}.log")
        with open(self.log_path, "w") as f:
            def sink(t, w, s):
                f.write(console.fmt(t, w, s) + "\n")
                f.flush()
            self.lines = console.capture(self.args.port, self.args.seconds, do_reset=True,
                                         stop_when=checks.is_boot_line, sink=sink)
        print(f"captured {len(self.lines)} lines -> {self.log_path}", flush=True)

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
        build_ok = self.step_build()
        guard_ok = self.step_guard()
        if not (build_ok and guard_ok and self.step_identify()):
            return self.finish()
        if self.args.flash and not self.step_flash():
            return self.finish()
        try:
            self.step_capture()
        except (OSError, TimeoutError) as e:
            self.check("console capture", False, str(e))
            return self.finish()
        self.capture_checks()
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
    args = ap.parse_args()
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
