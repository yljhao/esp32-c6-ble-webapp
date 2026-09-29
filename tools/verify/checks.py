"""Pure Harness logic: Checks over a console capture and the result line.

No I/O, no board, no subprocess: verify.py does the work and hands the
capture (console.capture()'s [(t_rel, wallclock, text), ...]) to these.
A Check returns (ok, detail); results are (name, ok, detail).
"""
import re

BOOT_RE = re.compile(r"^\[BOOT\] reason=([a-z]+)\s*$")


def is_boot_line(text):
    """True for a line the boot Check accepts; the capture stops on the same test."""
    return BOOT_RE.match(text) is not None


def check_boot_marker(lines):
    """`[BOOT] reason=<cause>` present on a line of its own."""
    for t, _, text in lines:
        if is_boot_line(text):
            return True, f"{text.strip()} at +{t:.3f}s"
    return False, f"no [BOOT] reason= marker in {len(lines)} captured line(s)"


def format_check(name, ok, detail=""):
    return f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else "")


def format_result(results):
    passed = sum(1 for r in results if r[1])
    ok = bool(results) and passed == len(results)
    return f"RESULT: {'PASS' if ok else 'FAIL'} ({passed}/{len(results)} checks)"


def exit_code(results):
    return 0 if results and all(r[1] for r in results) else 1
