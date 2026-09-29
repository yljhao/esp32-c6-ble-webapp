"""The Harness as a BLE Central: a thin bleak wrapper (glue).

Scan for the board by name and NUS service UUID, connect, subscribe to NUS notifications,
write a command line, collect the classified lines, disconnect. All decisions (line
reassembly, classification, matching, chunking, continuity) live in central_logic.py and are
unit-tested there; this file only calls bleak, so it is proven on the board by the Checks that
use it (later tickets), not by a unit test. Importing this module touches no Bluetooth: bleak
is imported inside the functions that need it.

    async with Session.connect(device) as s:
        await s.wait_heartbeats(10.5)
        reply = await s.request("led set 128")      # Reply(ok=True, brightness=128, ...)
        check_heartbeats(s.heartbeats, min_samples=10)

The PC's Bluetooth adapter is this module's only hardware; it is used against the board only
by a ticket whose `Board:` line is `required`, and always inside the Harness's board lock.
"""
import asyncio
import time

import central_logic as cl

DEFAULT_SCAN_S = 10.0
DEFAULT_CONNECT_S = 15.0
DEFAULT_REPLY_S = 3.0


async def find_board(timeout=DEFAULT_SCAN_S, name=cl.BOARD_NAME, service_uuid=cl.NUS_SERVICE_UUID):
    """Scan until an advertisement with the board's name and NUS UUID shows up.
    Returns the BLEDevice, or None after `timeout` seconds (also the answer to
    'is it still advertising?' while a Connection exists)."""
    from bleak import BleakScanner

    def wanted(device, adv):
        return cl.matches_board(adv.local_name, adv.service_uuids, name, service_uuid)

    return await BleakScanner.find_device_by_filter(wanted, timeout=timeout)


class Session:
    """One Connection as a Central. Use `async with Session.connect(device) as s:`."""

    def __init__(self, device, clock=time.monotonic):
        self._device = device
        self._clock = clock
        self._client = None
        self._reasm = cl.LineReassembler()
        self._replies = asyncio.Queue()
        self.heartbeats = []         # central_logic.Sample, oldest first
        self.other_lines = []        # (t, raw) lines that are neither Heartbeat nor reply
        self.disconnected = asyncio.Event()
        self.disconnected_at = None  # clock() when the link dropped, else None

    @classmethod
    def connect(cls, device, clock=time.monotonic):
        return cls(device, clock)

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def open(self, timeout=DEFAULT_CONNECT_S):
        from bleak import BleakClient

        self._client = BleakClient(self._device, disconnected_callback=self._on_disconnect, timeout=timeout)
        await self._client.connect()
        self._reasm.reset()
        await self._client.start_notify(cl.NUS_TX_UUID, self._on_notify)

    async def close(self):
        if self._client is not None and self._client.is_connected:
            await self._client.disconnect()

    @property
    def mtu(self):
        """Negotiated ATT MTU (23 if the stack does not say)."""
        return getattr(self._client, "mtu_size", None) or 23

    @property
    def connected(self):
        return self._client is not None and self._client.is_connected

    def _on_disconnect(self, _client):
        self.disconnected_at = self._clock()
        self.disconnected.set()

    def _on_notify(self, _characteristic, data):
        now = self._clock()
        for text in self._reasm.feed(data):
            line = cl.classify_line(text)
            if line.kind == cl.HEARTBEAT:
                self.heartbeats.append(cl.Sample(now, line.seq, line.uptime_ms))
            elif line.kind in (cl.LED, cl.ERR):
                self._replies.put_nowait(cl.parse_reply(text))
            else:
                self.other_lines.append((now, text))

    async def send(self, command):
        """Write one command line (split into MTU - 3 chunks, write without response)."""
        for chunk in cl.chunk_for_mtu(cl.encode_command(command), self.mtu):
            await self._client.write_gatt_char(cl.NUS_RX_UUID, chunk, response=False)

    async def request(self, command, timeout=DEFAULT_REPLY_S):
        """Send a command and return its Reply; Heartbeats arriving meanwhile are kept.
        Raises asyncio.TimeoutError when no reply line comes."""
        while not self._replies.empty():          # a stale reply belongs to no request
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
