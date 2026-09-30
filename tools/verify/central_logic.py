"""Pure logic of the Harness acting as a Central (spec: Wire contract, Harness).

No I/O: no bleak, no serial, no clock, no sleep. central.py (the bleak wrapper) feeds
notification bytes and timestamps in; the Checks read the results out.
"""
import codecs
import json
import re
from collections import namedtuple

# Line classes (spec: Wire contract). A line beginning `{` is a Heartbeat, one beginning
# `LED ` or `ERR ` is a reply; a line that claims a class but does not parse is OTHER.
HEARTBEAT = "heartbeat"
LED = "led"
ERR = "err"
OTHER = "other"

SEQ_MAX = 2**32 - 1
UPTIME_MAX = 2**64 - 1
BRIGHTNESS_MAX = 255

# `LED <n>`: decimal 0-255, no sign, no leading zeros, single space, nothing after.
_LED_RE = re.compile(r"LED (0|[1-9][0-9]{0,2})\Z")
_ERR_PREFIX = "ERR "

BOARD_NAME = "XIAO-C6-LED"
# Nordic UART Service (Nordic NUS specification): the Central writes RX, the board notifies on TX.
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
ATT_HEADER = 3      # a write or notification carries at most MTU - 3 bytes of data

Heartbeat = namedtuple("Heartbeat", "seq uptime_ms")
Reply = namedtuple("Reply", "ok brightness message")
# One classified line. Fields that do not apply to the kind are None.
Line = namedtuple("Line", "kind raw seq uptime_ms brightness message")


class LineReassembler:
    """Turns NUS notification chunks into complete lines.

    A line ends with `\\n` and may span several notifications, or several lines may share one.
    A trailing `\\r` is dropped. Bytes are buffered, so a multi-byte UTF-8 character split
    between two notifications is decoded whole; invalid bytes become U+FFFD, never an error.
    """

    def __init__(self):
        self._buf = b""

    def feed(self, chunk):
        """Add one notification's bytes; return the lines it completed, oldest first."""
        self._buf += bytes(chunk)
        *done, self._buf = self._buf.split(b"\n")
        return [codecs.decode(raw, "utf-8", "replace").rstrip("\r") for raw in done]

    @property
    def pending(self):
        """The unfinished line so far (what a Check reports when a capture ends mid-line)."""
        return codecs.decode(self._buf, "utf-8", "replace")

    def reset(self):
        """Drop a partial line, e.g. at a new Connection."""
        self._buf = b""


def parse_reply(text):
    """`LED <n>` -> Reply(True, n, None); `ERR <msg>` -> Reply(False, None, msg); else None."""
    m = _LED_RE.match(text)
    if m:
        n = int(m.group(1))
        return Reply(True, n, None) if n <= BRIGHTNESS_MAX else None
    if text.startswith(_ERR_PREFIX):
        return Reply(False, None, text[len(_ERR_PREFIX):])
    return None


def _is_uint(value, maximum):
    # bool is an int in Python; JSON true is not a number here.
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum


def parse_heartbeat(text):
    """`{"seq":<u32>,"uptime_ms":<u64>}` -> Heartbeat(seq, uptime_ms), else None."""
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    seq, uptime = obj.get("seq"), obj.get("uptime_ms")
    if not (_is_uint(seq, SEQ_MAX) and _is_uint(uptime, UPTIME_MAX)):
        return None
    return Heartbeat(seq, uptime)


def classify_line(text):
    """One reassembled line -> Line(kind, raw, seq, uptime_ms, brightness, message)."""
    if text.startswith("{"):
        hb = parse_heartbeat(text)
        if hb:
            return Line(HEARTBEAT, text, hb.seq, hb.uptime_ms, None, None)
    else:
        reply = parse_reply(text)
        if reply:
            return Line(LED if reply.ok else ERR, text, None, None, reply.brightness, reply.message)
    return Line(OTHER, text, None, None, None, None)


# Heartbeat continuity (spec: Heartbeat rules). The board counts `seq` from boot once per
# second whether or not a Central listens, so between two received Heartbeats:
#   seq + 1 = CONSECUTIVE; larger = GAP (a disconnect, or lines lost); smaller, or uptime_ms going
#   back, = REBOOT; same seq again = REPEAT.
CONSECUTIVE = "consecutive"
GAP = "gap"
REBOOT = "reboot"
REPEAT = "repeat"

# Sample = a Heartbeat with the PC time (seconds, any monotonic origin) its line was completed.
Sample = namedtuple("Sample", "t seq uptime_ms")

HB_PERIOD_S = 1.0
HB_TOLERANCE_S = 0.2
_EDGE = 1e-6      # float slack so an interval of exactly period +- tolerance passes


def step_kind(prev, cur):
    """CONSECUTIVE / GAP / REBOOT / REPEAT for two Samples, oldest first."""
    if cur.seq < prev.seq or cur.uptime_ms < prev.uptime_ms:
        return REBOOT
    if cur.seq == prev.seq:
        return REPEAT
    return CONSECUTIVE if cur.seq == prev.seq + 1 else GAP


def check_heartbeats(samples, min_samples, period_s=HB_PERIOD_S, tol_s=HB_TOLERANCE_S):
    """Steady-state Check: at least `min_samples` Heartbeats, every step CONSECUTIVE, every
    interval between arrivals within period_s +- tol_s. Returns (ok, detail); the detail names
    the first offender. Samples are Sample tuples or plain (t, seq, uptime_ms), oldest first."""
    samples = [Sample(*s) for s in samples]
    if len(samples) < min_samples:
        return False, f"{len(samples)} heartbeat(s), need at least {min_samples}"
    if not samples:
        return True, "no heartbeats required"
    intervals = []
    for prev, cur in zip(samples, samples[1:]):
        kind = step_kind(prev, cur)
        if kind != CONSECUTIVE:
            return False, f"{kind} at seq {prev.seq} -> {cur.seq} (uptime_ms {prev.uptime_ms} -> {cur.uptime_ms})"
        dt = cur.t - prev.t
        if abs(dt - period_s) > tol_s + _EDGE:
            return False, (f"period {dt:.3f} s between seq {prev.seq} -> {cur.seq} "
                           f"outside {period_s:g} +- {tol_s:g} s")
        intervals.append(dt)
    span = f"seq {samples[0].seq}..{samples[-1].seq}"
    if intervals:
        return True, (f"{len(samples)} heartbeats, {span} consecutive, "
                      f"period {min(intervals):.3f}..{max(intervals):.3f} s")
    return True, f"{len(samples)} heartbeat, {span}"


def matches_board(local_name, service_uuids, name=BOARD_NAME, service_uuid=NUS_SERVICE_UUID):
    """True when an advertisement carries the board's exact name AND the NUS service UUID."""
    if local_name != name:
        return False
    return service_uuid.lower() in {u.lower() for u in (service_uuids or ())}


def encode_command(text):
    """A command as the bytes to write: exactly one trailing `\\n`, none inside."""
    body = text[:-1] if text.endswith("\n") else text
    if "\n" in body or "\r" in body:
        raise ValueError("a command is one line")
    return (body + "\n").encode("utf-8")


def chunk_for_mtu(data, mtu):
    """Split bytes into writes of at most mtu - 3 bytes (empty data -> no chunks)."""
    size = mtu - ATT_HEADER
    if size < 1:
        raise ValueError(f"ATT MTU {mtu} leaves no room for data")
    return [data[i:i + size] for i in range(0, len(data), size)]


def expect_led_reply(reply, brightness):
    """The reply to a command that must succeed: `LED <brightness>` exactly. `reply` is a Reply,
    or None when none came. Returns (ok, detail)."""
    if reply is None:
        return False, "no reply line"
    if not reply.ok:
        return False, f"ERR {reply.message}, expected LED {brightness}"
    if reply.brightness != brightness:
        return False, f"LED {reply.brightness}, expected LED {brightness}"
    return True, f"LED {reply.brightness}"


def expect_err_reply(reply):
    """The reply to a command that must be rejected: a line starting `ERR `."""
    if reply is None:
        return False, "no reply line"
    if reply.ok:
        return False, f"LED {reply.brightness}, expected an ERR line"
    return True, f"ERR {reply.message}"


REFUSAL_MESSAGE = "command not allowed"   # the board's LINK_FILTER_REFUSAL is "ERR " + this


def expect_refusal(reply):
    """The reply to a command the Shell link must refuse (ticket 08): `ERR command not allowed`."""
    if reply is None:
        return False, "no reply line"
    if reply.ok:
        return False, f"LED {reply.brightness}, expected ERR {REFUSAL_MESSAGE}"
    if reply.message != REFUSAL_MESSAGE:
        return False, f"ERR {reply.message}, expected ERR {REFUSAL_MESSAGE}"
    return True, f"ERR {reply.message}"


def _replies_only(lines):
    return [ln for ln in lines if ln.kind != HEARTBEAT]


def expect_only_refusals(lines, count):
    """After `count` refused commands: exactly `count` lines came back (Heartbeats aside) and every
    one is the refusal, so no command produced shell text or a second reply."""
    got = _replies_only(lines)
    bad = [ln.raw for ln in got if not (ln.kind == ERR and ln.message == REFUSAL_MESSAGE)]
    if bad:
        return False, f"line(s) other than the refusal: {bad}"
    if len(got) != count:
        return False, f"{len(got)} line(s), expected {count}"
    return True, f"{count} line(s), each ERR {REFUSAL_MESSAGE}"


def check_clean_stream(raw, lines):
    """Nothing but reply and Heartbeat lines on the Shell link (spec: no echo, prompt or escape
    sequences). `raw` is every byte received, `lines` the Line tuples classified from it. Fails on
    an escape byte, a carriage return, a line that is neither reply nor Heartbeat (an echo, a
    prompt, a blank line) and a stream that stops mid-line. An empty stream is no evidence."""
    if not raw:
        return False, "nothing received, so nothing to judge"
    if b"\x1b" in raw:
        return False, f"escape byte 0x1b in the stream at offset {raw.index(b'\x1b')}"
    if b"\r" in raw:
        return False, f"carriage return in the stream at offset {raw.index(b'\r')}"
    if not raw.endswith(b"\n"):
        return False, f"stream ends without an end of line: {raw.rsplit(b'\n', 1)[-1]!r}"
    for line in lines:
        if line.kind == OTHER:
            return False, f"line that is neither reply nor Heartbeat: {line.raw!r}"
    return True, f"{len(lines)} line(s), all replies or Heartbeats, {len(raw)} bytes"


# -- Heartbeat Checks (ticket 09) ---------------------------------------------------------------

def check_interleaved(lines, expected_brightness, min_between=3):
    """`lines` = every Line received in a window during which the Harness sent one command per
    entry of `expected_brightness` (the `LED <n>` each must answer) and the board sent Heartbeats.
    Passes when the stream holds only whole Heartbeat and reply lines (a splice of one into the
    other classifies as OTHER), the replies are exactly the expected ones in order, and at least
    `min_between` replies sit between two Heartbeats, so the two kinds really did interleave.
    Returns (ok, detail)."""
    other = [ln.raw for ln in lines if ln.kind == OTHER]
    if other:
        return False, f"line(s) that are neither Heartbeat nor reply (spliced?): {other[:3]}"
    replies = _replies_only(lines)
    got = [ln.brightness if ln.kind == LED else f"ERR {ln.message}" for ln in replies]
    if got != list(expected_brightness):
        return False, f"replies {got}, expected LED {list(expected_brightness)}"
    between = 0
    for i, ln in enumerate(lines):
        if ln.kind in (LED, ERR):
            if any(p.kind == HEARTBEAT for p in lines[:i]) and any(n.kind == HEARTBEAT for n in lines[i + 1:]):
                between += 1
    if between < min_between:
        return False, f"only {between} reply line(s) between Heartbeats, need {min_between} to show interleaving"
    n_hb = sum(1 for ln in lines if ln.kind == HEARTBEAT)
    return True, f"{n_hb} Heartbeat line(s) and {len(replies)} reply line(s), all whole, {between} reply(ies) between Heartbeats"


def check_gap_after_disconnect(prev, cur, disconnect_s=5.0, max_extra_s=6.0, arrival_tol_s=0.6):
    """After the Central was away for at least `disconnect_s`: the first Heartbeat `cur` is a GAP
    after the last one before it, `prev`, `disconnect_s` higher or more (the board kept counting),
    not more than `max_extra_s` more (the reconnect itself takes time), and the number of seconds
    the seq advanced matches the PC clock between the two arrivals within `arrival_tol_s`.
    prev/cur are Samples (t, seq, uptime_ms)."""
    kind = step_kind(prev, cur)
    if kind != GAP:
        return False, f"{kind} at seq {prev.seq} -> {cur.seq}, expected a gap"
    delta = cur.seq - prev.seq
    elapsed = cur.t - prev.t
    if delta < disconnect_s:
        return False, f"seq only {delta} higher after a {disconnect_s:g} s disconnect ({prev.seq} -> {cur.seq})"
    if delta > disconnect_s + max_extra_s:
        return False, f"seq {delta} higher, more than {disconnect_s:g} + {max_extra_s:g} ({prev.seq} -> {cur.seq})"
    if abs(delta - elapsed) > arrival_tol_s:
        return False, f"seq advanced {delta} in {elapsed:.2f} s of PC time ({prev.seq} -> {cur.seq})"
    return True, (f"seq {prev.seq} -> {cur.seq}: {delta} higher after {elapsed:.2f} s "
                  f"({delta - disconnect_s:g} more than the {disconnect_s:g} s disconnect)")


def check_restart_after_reboot(prev, cur, max_seq=10):
    """After a reboot: the first Heartbeat `cur` reads as a REBOOT after `prev` (seq and uptime
    both restarted) and its seq is near 0 (at most `max_seq`)."""
    kind = step_kind(prev, cur)
    if kind != REBOOT:
        return False, f"{kind} at seq {prev.seq} -> {cur.seq}, expected a reboot"
    if cur.seq > max_seq:
        return False, f"seq restarted at {cur.seq}, expected at most {max_seq} (near 0)"
    return True, f"seq {prev.seq} -> {cur.seq} (uptime_ms {prev.uptime_ms} -> {cur.uptime_ms})"


def check_board_spacing(samples, min_samples, period_ms=1000, tol_ms=200, max_arrival_s=None):
    """The board's own spacing: at least `min_samples` Heartbeats, every step CONSECUTIVE and every
    `uptime_ms` step within period_ms +- tol_ms. It does not read the PC clock, so it tells a
    firmware period fault from delivery jitter on the radio link (the Harness retries a window that
    failed check_heartbeats() on the PC clock alone). With `max_arrival_s`, a line that reached the PC
    more than that after its predecessor also fails: link jitter is tolerated, a stall is not.
    Returns (ok, detail)."""
    samples = [Sample(*s) for s in samples]
    if len(samples) < min_samples:
        return False, f"{len(samples)} heartbeat(s), need at least {min_samples}"
    steps = []
    for prev, cur in zip(samples, samples[1:]):
        kind = step_kind(prev, cur)
        if kind != CONSECUTIVE:
            return False, f"{kind} at seq {prev.seq} -> {cur.seq}"
        dt = cur.uptime_ms - prev.uptime_ms
        if abs(dt - period_ms) > tol_ms:
            return False, f"board period {dt} ms between seq {prev.seq} -> {cur.seq}, outside {period_ms} +- {tol_ms} ms"
        if max_arrival_s is not None and cur.t - prev.t > max_arrival_s:
            return False, f"seq {cur.seq} arrived {cur.t - prev.t:.2f} s after seq {prev.seq}, limit {max_arrival_s:g} s"
        steps.append(dt)
    if not steps:
        return True, f"{len(samples)} heartbeat"
    return True, f"{len(samples)} heartbeats, board period {min(steps)}..{max(steps)} ms"
