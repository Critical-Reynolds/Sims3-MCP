import json
import os
import struct
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
from sims3_mcp import mailbox as mb  # noqa: E402

CAP = 256 * 1024


class FakeMemory:
    """A flat address space holding mailboxes at chosen addresses."""

    def __init__(self):
        self.blocks: dict[int, bytearray] = {}

    def add_mailbox(self, addr: int, nonce: int, tick: int = 1) -> bytearray:
        buf = bytearray(CAP)
        buf[:16] = mb.MAGIC
        check = mb.VERSION ^ nonce ^ CAP ^ mb.CHECK_SALT
        struct.pack_into("<11I", buf, 16, mb.VERSION, nonce, 0, 0, 0, 0, CAP, check, 0, tick, 1)
        self.blocks[addr] = buf
        return buf

    def _locate(self, addr):
        for base, buf in self.blocks.items():
            if base <= addr < base + len(buf):
                return buf, addr - base
        raise OSError("unmapped")

    def read(self, addr, size):
        buf, off = self._locate(addr)
        return bytes(buf[off:off + size])

    def write(self, addr, data):
        buf, off = self._locate(addr)
        buf[off:off + len(data)] = data

    def scan(self, needle, readwrite_only=False):
        for base, buf in self.blocks.items():
            i = buf.find(needle)
            while i != -1:
                yield base + i
                i = buf.find(needle, i + 1)


def responder(buf: bytearray, stop: threading.Event, handler):
    """Mimic the mod's poll loop."""
    while not stop.is_set():
        hb = struct.unpack_from("<I", buf, mb.OFF_HEARTBEAT)[0]
        struct.pack_into("<I", buf, mb.OFF_HEARTBEAT, hb + 1)
        req_seq, resp_seq = struct.unpack_from("<II", buf, mb.OFF_REQ_SEQ)
        if req_seq != resp_seq:
            n = struct.unpack_from("<I", buf, mb.OFF_REQ_LEN)[0]
            req = json.loads(buf[mb.HEADER:mb.HEADER + n].decode())
            resp = json.dumps(handler(req)).encode()
            buf[mb.HEADER + mb.REQ_CAP:mb.HEADER + mb.REQ_CAP + len(resp)] = resp
            struct.pack_into("<I", buf, mb.OFF_RESP_LEN, len(resp))
            struct.pack_into("<I", buf, mb.OFF_RESP_SEQ, req_seq)
        time.sleep(0.001)


@pytest.fixture
def game():
    mem = FakeMemory()
    stops = []

    def start(addr, nonce, tick=1, handler=None):
        buf = mem.add_mailbox(addr, nonce, tick)
        stop = threading.Event()
        stops.append(stop)
        h = handler or (lambda r: {"id": r["id"], "ok": True, "result": {"cmd": r["cmd"], "args": r["args"]}})
        threading.Thread(target=responder, args=(buf, stop, h), daemon=True).start()
        return buf

    yield mem, start
    for s in stops:
        s.set()


def test_roundtrip_and_sequence(game):
    mem, start = game
    start(0x1000_0000, nonce=42)
    box = mb.Mailbox(mem)
    assert box.call("ping", {"x": "héllo"}) == {"cmd": "ping", "args": {"x": "héllo"}}
    assert box.call("look") == {"cmd": "look", "args": {}}
    assert box.nonce == 42


def test_game_error_is_raised(game):
    mem, start = game
    start(0x1000_0000, nonce=1, handler=lambda r: {"id": r["id"], "ok": False, "error": "no active sim"})
    with pytest.raises(mb.GameError, match="no active sim"):
        mb.Mailbox(mem).call("look")


def test_prefers_live_newest_mailbox(game):
    mem, start = game
    mem.add_mailbox(0x2000_0000, nonce=7, tick=999)  # stale: no heartbeat
    start(0x3000_0000, nonce=8, tick=5)
    box = mb.Mailbox(mem)
    box.call("ping")
    assert box.addr == 0x3000_0000


def test_rescan_after_world_reload(game):
    mem, start = game
    old = start(0x1000_0000, nonce=1)
    box = mb.Mailbox(mem)
    box.call("ping")
    old[:16] = b"\0" * 16  # mod wipes magic on world quit
    start(0x5000_0000, nonce=2)
    box.call("ping")
    assert box.addr == 0x5000_0000 and box.nonce == 2


def test_timeout_when_mod_not_polling(game):
    mem, _ = game
    mem.add_mailbox(0x1000_0000, nonce=3)
    with pytest.raises(mb.MailboxError, match="timed out"):
        mb.Mailbox(mem).call("ping", timeout=0.2)


def test_not_found():
    with pytest.raises(mb.MailboxError, match="not found"):
        mb.Mailbox(FakeMemory()).call("ping")


def test_header_rejects_bad_check():
    raw = bytearray(64)
    raw[:16] = mb.MAGIC
    struct.pack_into("<11I", raw, 16, 1, 5, 0, 0, 0, 0, CAP, 0xDEAD, 0, 0, 0)
    assert mb.Header.parse(bytes(raw)) is None
