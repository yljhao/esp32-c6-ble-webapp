"""The Harness as a BLE Central: a thin bleak wrapper (glue).

Scan for the board by name and NUS service UUID, connect, subscribe to NUS notifications,
write a command line, collect the classified lines, disconnect. All decisions (line
reassembly, classification, matching, chunking, continuity) live in central_logic.py and are
unit-tested there; this file only calls bleak, so it is proven on the board by the Checks that
use it (later tickets), not by a unit test. Importing this module touches no Bluetooth: bleak
is imported inside the functions that need it (a unit test checks that).

    async with CentralConnection(device) as c:
        await c.wait_heartbeats(10.5)
        reply = await c.request("led set 128")      # Reply(ok=True, brightness=128, ...)
        check_heartbeats(c.heartbeats, min_samples=10)

The PC's Bluetooth adapter is this module's only hardware; it is used against the board only
by a ticket whose `Board:` line is `required`, and always inside the Harness's board lock.
The board accepts one Connection and stops advertising while it exists, so a Connection that
is left up hides the board from the next run: every path out of `open` and `async with`
disconnects.
"""
import asyncio
import time

import central_logic as cl

# Bounds, seconds. A scan must outlast several advertising intervals; the connect bound covers
# BlueZ's own connection procedure; a shell reply comes within a fraction of a second on the
# board, so 3 s means "lost"; a disconnect or a write that takes 5 s means the link is stuck.
# Measured on the board (ticket 06, board-notes): the scan finds the board in 0.1 to 0.3 s, a
# connect with service discovery takes about 2 s, so these bounds stay as they are.
DEFAULT_SCAN_S = 10.0
DEFAULT_CONNECT_S = 15.0
DEFAULT_REPLY_S = 3.0
DEFAULT_IO_S = 5.0


async def find_board(timeout=DEFAULT_SCAN_S, name=cl.BOARD_NAME, service_uuid=cl.NUS_SERVICE_UUID):
    """Scan until an advertisement with the board's name and NUS UUID shows up.
    Returns the BLEDevice, or None after `timeout` seconds (also the answer to
    'is it still advertising?' while a Connection exists)."""
    from bleak import BleakScanner

    def wanted(device, adv):
        return cl.matches_board(adv.local_name, adv.service_uuids, name, service_uuid)

    return await BleakScanner.find_device_by_filter(wanted, timeout=timeout)


class CentralConnection:
    """One Connection as a Central. Use `async with CentralConnection(device) as c:`.

    Callbacks run on the asyncio loop (bleak schedules them there), so the lists and the queue
    below are only touched from the loop; lists grow for the length of a run (1 line/s)."""

    def __init__(self, device, clock=time.monotonic):
        self._device = device
        self._clock = clock
        self._gatt = None            # the bleak.BleakClient
        self._reasm = cl.LineReassembler()
        self._replies = asyncio.Queue()
        self.heartbeats = []         # central_logic.Sample, oldest first
        self.other_lines = []        # (t, raw) lines that are neither Heartbeat nor reply
        self.raw = bytearray()       # every notification byte received (the clean-stream Check reads it)
        self.lines = []              # central_logic.Line, every line received, oldest first
        self.disconnected = asyncio.Event()
        self.disconnected_at = None  # clock() when the link dropped, else None

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def open(self, timeout=DEFAULT_CONNECT_S):
        from bleak import BleakClient

        self.disconnected.clear()
        self.disconnected_at = None
        self._reasm.reset()
        self._gatt = BleakClient(self._device, disconnected_callback=self._on_disconnect, timeout=timeout)
        await self._gatt.connect()
        try:
            # AcquireNotify (a file descriptor of our own) instead of bleak's default StartNotify:
            # after a link that was lost (not closed by us) BlueZ keeps the old notify session,
            # and the next StartNotify then delivers every notification twice (measured, ticket 07).
            await self._gatt.start_notify(cl.NUS_TX_UUID, self._on_notify, bluez={"use_start_notify": False})
        except BaseException:
            await self.close()       # never leave the one Connection up behind a failed open
            raise

    async def close(self):
        if self._gatt is not None and self._gatt.is_connected:
            await asyncio.wait_for(self._gatt.disconnect(), DEFAULT_IO_S)

    @property
    def connected(self):
        return self._gatt is not None and self._gatt.is_connected

    @property
    def write_payload(self):
        """Bytes per write without response. bleak's `mtu_size` is always 23 on BlueZ, so ask
        the RX characteristic (it tracks the negotiated ATT MTU: MTU - 3, 20 as a floor)."""
        char = self._gatt.services.get_characteristic(cl.NUS_RX_UUID)
        return char.max_write_without_response_size

    def _on_disconnect(self, _bleak_client):
        self.disconnected_at = self._clock()
        self.disconnected.set()

    def _on_notify(self, _characteristic, data):
        now = self._clock()
        self.raw += bytes(data)
        for text in self._reasm.feed(data):
            line = cl.classify_line(text)
            self.lines.append(line)
            if line.kind == cl.HEARTBEAT:
                self.heartbeats.append(cl.Sample(now, line.seq, line.uptime_ms))
            elif line.kind in (cl.LED, cl.ERR):
                self._replies.put_nowait(cl.Reply(line.kind == cl.LED, line.brightness, line.message))
            else:
                self.other_lines.append((now, text))

    async def send(self, command):
        """Write one command line (chunks of the negotiated payload, write without response)."""
        payload = self.write_payload
        for chunk in cl.chunk_for_mtu(cl.encode_command(command), payload + cl.ATT_HEADER):
            await asyncio.wait_for(self._gatt.write_gatt_char(cl.NUS_RX_UUID, chunk, response=False),
                                   DEFAULT_IO_S)

    async def request(self, command, timeout=DEFAULT_REPLY_S):
        """Send a command and return its Reply; Heartbeats arriving meanwhile are kept.
        The next reply line answers it (the shell answers in order); a stale one from before is
        dropped. Raises asyncio.TimeoutError when no reply line comes."""
        while not self._replies.empty():
            self._replies.get_nowait()
        await self.send(command)
        return await asyncio.wait_for(self._replies.get(), timeout)

    async def wait_heartbeats(self, seconds):
        """Listen for `seconds`, or until the link drops. Returns the Heartbeats so far."""
        try:
            await asyncio.wait_for(self.disconnected.wait(), seconds)
        except asyncio.TimeoutError:
            pass
        return list(self.heartbeats)
