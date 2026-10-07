"""Minimal reader/writer for Sims 3 DBPF 2.0 .package files.

Supports the subset needed to extract the game's script assemblies (S3SA)
and to build a script-mod package (S3SA + _XML tuning resource).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

TYPE_S3SA = 0x073FAA07  # script assembly
TYPE_XML = 0x0333406C   # _XML tuning

_HEADER_SIZE = 96


@dataclass
class Entry:
    type: int
    group: int
    instance: int
    offset: int = 0
    file_size: int = 0
    mem_size: int = 0
    compressed: int = 0

    @property
    def key(self) -> tuple[int, int, int]:
        return (self.type, self.group, self.instance)


def fnv64(text: str) -> int:
    """FNV-1 64-bit hash of the lowercase string (Sims 3 resource instance ids)."""
    h = 0xCBF29CE484222325
    for b in text.lower().encode("ascii"):
        h = (h * 0x00000100000001B3) & 0xFFFFFFFFFFFFFFFF
        h ^= b
    return h


def fnv32(text: str) -> int:
    h = 0x811C9DC5
    for b in text.lower().encode("ascii"):
        h = (h * 0x01000193) & 0xFFFFFFFF
        h ^= b
    return h


# ---------------------------------------------------------------- RefPack

def refpack_decompress(data: bytes) -> bytes:
    """Decompress EA RefPack (QFS) data as used by Sims 3 packages."""
    pos = 0
    flags = data[0]
    if data[1] != 0xFB:
        raise ValueError("not RefPack data")
    size_len = 4 if flags & 0x80 else 3
    pos = 2
    if flags & 0x01:  # compressed-size field present (unused)
        pos += size_len
    out_size = int.from_bytes(data[pos:pos + size_len], "big")
    pos += size_len
    out = bytearray()
    n = len(data)
    while pos < n:
        b0 = data[pos]
        if b0 < 0x80:
            b1 = data[pos + 1]
            plain = b0 & 0x03
            copy = ((b0 & 0x1C) >> 2) + 3
            off = ((b0 & 0x60) << 3) + b1 + 1
            pos += 2
        elif b0 < 0xC0:
            b1, b2 = data[pos + 1], data[pos + 2]
            plain = (b1 & 0xC0) >> 6
            copy = (b0 & 0x3F) + 4
            off = ((b1 & 0x3F) << 8) + b2 + 1
            pos += 3
        elif b0 < 0xE0:
            b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
            plain = b0 & 0x03
            copy = ((b0 & 0x0C) << 6) + b3 + 5
            off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            pos += 4
        elif b0 < 0xFC:
            plain = ((b0 & 0x1F) << 2) + 4
            copy = 0
            off = 0
            pos += 1
        else:
            plain = b0 & 0x03
            copy = 0
            off = 0
            pos += 1
            out += data[pos:pos + plain]
            break
        out += data[pos:pos + plain]
        pos += plain
        if copy:
            start = len(out) - off
            for i in range(copy):  # may overlap, copy byte-wise
                out.append(out[start + i])
    if len(out) != out_size:
        raise ValueError(f"RefPack size mismatch: {len(out)} != {out_size}")
    return bytes(out)


# ---------------------------------------------------------------- S3SA

_S3SA_UNKNOWN2 = 0x2BC4F79F


def _s3sa_seed(table: bytes | bytearray) -> int:
    seed = 0
    for i in range(0, len(table), 8):
        seed = (seed + struct.unpack_from("<Q", table, i)[0]) & 0xFFFFFFFFFFFFFFFF
    return seed & (len(table) - 1)


def s3sa_decode(blob: bytes) -> bytes:
    """Return the cleartext .NET assembly stored in an S3SA resource.

    Layout: version(u8) [game version (i32 char count + UTF-16LE) if version > 1]
    unknown(u32) md5(64) block_count(u16) table(8 * count) blocks(512 each,
    only for table entries with bit0 clear; others are all-zero blocks).
    Each byte is XORed with table[seed]; seed advances by the ciphertext byte.
    Matches s3pi's ScriptResource.decrypt().
    """
    p = 0
    version = blob[p]
    p += 1
    if version > 1:
        n = struct.unpack_from("<i", blob, p)[0]
        p += 4 + n * 2
    p += 4 + 64
    count = struct.unpack_from("<H", blob, p)[0]
    p += 2
    table = blob[p:p + count * 8]
    p += count * 8
    seed = _s3sa_seed(table)
    size = len(table)
    out = bytearray()
    for i in range(0, size, 8):
        block = bytearray(512)
        if table[i] & 1 == 0:
            for j in range(512):
                v = blob[p + j]
                block[j] = v ^ table[seed]
                seed = (seed + v) % size
            p += 512
        out += block
    return bytes(out)


def s3sa_encode(assembly: bytes) -> bytes:
    """Wrap a .NET assembly into a version-1 S3SA resource, as s3pe does.

    With an all-zero table every XOR key is 0, so the blocks are the
    zero-padded cleartext.
    """
    padded = assembly + bytes(1) * (-len(assembly) % 512)
    count = len(padded) // 512
    return (struct.pack("<BI", 1, _S3SA_UNKNOWN2) + bytes(1) * 64
            + struct.pack("<H", count) + bytes(count * 8) + padded)


# ---------------------------------------------------------------- reading

class Package:
    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()
        self.entries: list[Entry] = []
        self._parse()

    def _parse(self) -> None:
        d = self.data
        if d[:4] != b"DBPF":
            raise ValueError(f"{self.path}: not a DBPF file")
        major, minor = struct.unpack_from("<II", d, 4)
        if major != 2:
            raise ValueError(f"{self.path}: unsupported DBPF version {major}.{minor}")
        count = struct.unpack_from("<I", d, 0x24)[0]
        index_pos = struct.unpack_from("<I", d, 0x40)[0]
        pos = index_pos
        flags = struct.unpack_from("<I", d, pos)[0]
        pos += 4
        const = []
        for bit in range(4):
            if flags & (1 << bit):
                const.append(struct.unpack_from("<I", d, pos)[0])
                pos += 4
            else:
                const.append(None)
        for _ in range(count):
            vals = []
            for bit in range(4):
                if const[bit] is not None:
                    vals.append(const[bit])
                else:
                    vals.append(struct.unpack_from("<I", d, pos)[0])
                    pos += 4
            t, g, ihi, ilo = vals
            offset, fsize, msize, comp, _ = struct.unpack_from("<IIIHH", d, pos)
            pos += 16
            self.entries.append(Entry(t, g, (ihi << 32) | ilo, offset,
                                      fsize & 0x7FFFFFFF, msize, comp))

    def raw(self, e: Entry) -> bytes:
        return self.data[e.offset:e.offset + e.file_size]

    def read(self, e: Entry) -> bytes:
        blob = self.raw(e)
        if e.compressed == 0xFFFF:
            return refpack_decompress(blob)
        return blob

    def find(self, type_: int) -> list[Entry]:
        return [e for e in self.entries if e.type == type_]


# ---------------------------------------------------------------- writing

@dataclass
class NewResource:
    type: int
    group: int
    instance: int
    data: bytes


@dataclass
class PackageWriter:
    resources: list[NewResource] = field(default_factory=list)

    def add(self, type_: int, group: int, instance: int, data: bytes) -> None:
        self.resources.append(NewResource(type_, group, instance, data))

    def build(self) -> bytes:
        body = bytearray()
        offsets = []
        pos = _HEADER_SIZE
        for r in self.resources:
            offsets.append(pos)
            body += r.data
            pos += len(r.data)
        index = bytearray(struct.pack("<I", 0))  # no constant fields
        for r, off in zip(self.resources, offsets):
            index += struct.pack("<IIII", r.type, r.group,
                                 (r.instance >> 32) & 0xFFFFFFFF, r.instance & 0xFFFFFFFF)
            index += struct.pack("<IIIHH", off, len(r.data) | 0x80000000, len(r.data), 0, 1)
        index_pos = _HEADER_SIZE + len(body)
        header = bytearray(_HEADER_SIZE)
        header[0:4] = b"DBPF"
        struct.pack_into("<II", header, 4, 2, 0)
        struct.pack_into("<I", header, 0x24, len(self.resources))
        struct.pack_into("<I", header, 0x2C, len(index))
        struct.pack_into("<I", header, 0x3C, 3)
        struct.pack_into("<I", header, 0x40, index_pos)
        return bytes(header + body + index)

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.build())
