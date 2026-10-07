"""Client side of the in-memory mailbox shared with the Sims3Mcp script mod.

The mod allocates a managed byte[] inside TS3.exe laid out as:

    0   magic[16]   "S3MCP-MAILBOX-01"
    16  u32 version
    20  u32 nonce        random per allocation
    24  u32 req_seq      bumped by us (last) after writing a request
    28  u32 resp_seq     set by the mod (last) after writing the response
    32  u32 req_len
    36  u32 resp_len
    40  u32 capacity     total buffer size
    44  u32 check        version ^ nonce ^ capacity ^ CHECK_SALT
    48  u32 heartbeat    incremented by the mod every poll
    52  u32 alloc_tick   Environment.TickCount at allocation (newest wins)
    56  u32 state        0 = world not loaded, 1 = world loaded
    60  u32 reserved
    64  request  area   [REQ_CAP bytes]
    64+REQ_CAP response area [capacity - 64 - REQ_CAP bytes]

We find it by scanning the game's read/write memory for the magic, then talk
to it with ReadProcessMemory / WriteProcessMemory. Requests and responses are
UTF-8 JSON.
"""
from __future__ import annotations

import json
import struct
import threading
import time
from dataclasses import dataclass
from typing import Any, Protocol

MAGIC = b"S3MCP-MAILBOX-01"
VERSION = 1
CHECK_SALT = 0x53334D43
HEADER = 64
REQ_CAP = 64 * 1024

OFF_REQ_SEQ = 24
OFF_RESP_SEQ = 28
OFF_REQ_LEN = 32
OFF_RESP_LEN = 36
OFF_HEARTBEAT = 48


class Memory(Protocol):
    def read(self, addr: int, size: int) -> bytes: ...
    def write(self, addr: int, data: bytes) -> None: ...
    def scan(self, needle: bytes, readwrite_only: bool = False): ...


class MailboxError(RuntimeError):
    pass


class GameError(RuntimeError):
    """The mod executed the request but reported an error."""


@dataclass
class Header:
    version: int
    nonce: int
    req_seq: int
    resp_seq: int
    req_len: int
    resp_len: int
    capacity: int
    check: int
    heartbeat: int
    alloc_tick: int
    state: int

    @classmethod
    def parse(cls, raw: bytes) -> "Header | None":
        if raw[:16] != MAGIC:
            return None
        h = cls(*struct.unpack_from("<11I", raw, 16))
        if h.version != VERSION or h.check != (h.version ^ h.nonce ^ h.capacity ^ CHECK_SALT):
            return None
        if not HEADER + REQ_CAP < h.capacity <= 64 << 20:
            return None
        return h


class Mailbox:
    def __init__(self, mem: Memory):
        self.mem = mem
        self.addr: int | None = None
        self.nonce: int | None = None
        self.capacity = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------ discovery
    def _header(self, addr: int) -> Header | None:
        try:
            return Header.parse(self.mem.read(addr, HEADER))
        except OSError:
            return None

    def locate(self, settle: float = 0.25) -> int:
        """Scan for live mailboxes and attach to the newest one with a beating heart."""
        cands = {}
        for addr in self.mem.scan(MAGIC, readwrite_only=True):
            h = self._header(addr)
            if h:
                cands[addr] = h
        if not cands:
            raise MailboxError("mailbox not found: is the Sims3Mcp mod installed and a world (or main menu) loaded?")
        if settle and len(cands) > 1:
            time.sleep(settle)
        alive = []
        for addr, h in cands.items():
            h2 = self._header(addr)
            if h2 and h2.nonce == h.nonce:
                alive.append((h2.heartbeat != h.heartbeat, h2.alloc_tick, addr, h2))
        if not alive:
            raise MailboxError("mailbox candidates vanished while validating; retry")
        alive.sort(reverse=True)
        _, _, addr, h = alive[0]
        self.addr, self.nonce, self.capacity = addr, h.nonce, h.capacity
        return addr

    def _valid(self) -> Header | None:
        if self.addr is None:
            return None
        h = self._header(self.addr)
        if h is None or h.nonce != self.nonce:
            return None
        return h

    # ------------------------------------------------------------ calls
    def call(self, cmd: str, args: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
        with self._lock:
            h = self._valid()
            if h is None:
                self.locate()
                h = self._valid()
                if h is None:
                    raise MailboxError("mailbox lost right after attaching; retry")
            seq = (max(h.req_seq, h.resp_seq) + 1) & 0xFFFFFFFF or 1
            body = json.dumps({"id": seq, "cmd": cmd, "args": args or {}},
                              ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(body) > REQ_CAP:
                raise MailboxError(f"request too large ({len(body)} > {REQ_CAP} bytes)")
            a = self.addr
            self.mem.write(a + HEADER, body)
            self.mem.write(a + OFF_REQ_LEN, struct.pack("<I", len(body)))
            self.mem.write(a + OFF_REQ_SEQ, struct.pack("<I", seq))  # publish last

            deadline = time.monotonic() + timeout
            delay = 0.002
            while True:
                raw = self.mem.read(a, HEADER)
                h = Header.parse(raw)
                if h is None or h.nonce != self.nonce:
                    self.addr = None
                    raise MailboxError("mailbox disappeared while waiting (world reloaded or game closed)")
                if h.resp_seq == seq:
                    break
                if time.monotonic() > deadline:
                    raise MailboxError(
                        f"timed out after {timeout:.0f}s waiting for '{cmd}' "
                        "(game minimized/paused in a loading screen or blocked by a modal dialog?)")
                time.sleep(delay)
                delay = min(delay * 1.5, 0.05)

            if h.resp_len > h.capacity - HEADER - REQ_CAP:
                raise MailboxError(f"corrupt response length {h.resp_len}")
            data = self.mem.read(a + HEADER + REQ_CAP, h.resp_len)
        resp = json.loads(data.decode("utf-8"))
        if not resp.get("ok"):
            raise GameError(resp.get("error", "unknown error"))
        return resp.get("result")
