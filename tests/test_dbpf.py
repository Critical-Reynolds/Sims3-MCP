import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import dbpf  # noqa: E402

GAME_BIN = r"C:\Program Files\EA Games\The Sims 3\Game\Bin"


def test_package_roundtrip(tmp_path):
    w = dbpf.PackageWriter()
    w.add(dbpf.TYPE_XML, 0, dbpf.fnv64("Sims3Mcp.Instantiator"), b"<?xml version='1.0'?><base/>")
    w.add(dbpf.TYPE_S3SA, 0, 0x1234_5678_9ABC_DEF0, b"payload" * 100)
    path = tmp_path / "t.package"
    w.save(str(path))
    p = dbpf.Package(str(path))
    assert [(e.type, e.instance) for e in p.entries] == [
        (dbpf.TYPE_XML, dbpf.fnv64("Sims3Mcp.Instantiator")), (dbpf.TYPE_S3SA, 0x1234_5678_9ABC_DEF0)]
    assert p.read(p.entries[1]) == b"payload" * 100


def test_s3sa_roundtrip():
    asm = bytes(range(256)) * 7 + b"MZ tail"
    out = dbpf.s3sa_decode(dbpf.s3sa_encode(asm))
    assert out[:len(asm)] == asm and set(out[len(asm):]) <= {0}


def test_fnv64_known_value():
    # FNV-1 64 of the empty string is the offset basis.
    assert dbpf.fnv64("") == 0xCBF29CE484222325


def test_refpack_literal_and_backref():
    # header: flags 0x10 0xFB, size 3 bytes BE = 8; then 0xE0+ literal (4 bytes), short copy, stop.
    data = bytes([0x10, 0xFB, 0, 0, 8, 0xE0]) + b"abcd" + bytes([0x00 | (1 << 2), 3]) + bytes([0xFC])
    # 0xE0 -> plain = 4 bytes "abcd"; short op: plain=0, copy=((4&0x1C)>>2)+3=4, off=3+1=4 -> "abcd"
    assert dbpf.refpack_decompress(data) == b"abcdabcd"


@pytest.mark.skipif(not os.path.isdir(GAME_BIN), reason="game not installed")
def test_game_assemblies_decode_to_pe():
    p = dbpf.Package(os.path.join(GAME_BIN, "scripts.package"))
    for e in p.find(dbpf.TYPE_S3SA):
        asm = dbpf.s3sa_decode(p.read(e))
        assert asm[:2] == b"MZ" and b"BSJB" in asm  # clean CLI metadata
