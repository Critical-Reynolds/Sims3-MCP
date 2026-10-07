"""Win32 process memory access via ctypes (no third-party deps)."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass
from typing import Iterator

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_READWRITE = 0x04
PAGE_WRITECOPY = 0x08
PAGE_EXECUTE_READWRITE = 0x40
PAGE_EXECUTE_WRITECOPY = 0x80
WRITABLE = PAGE_READWRITE | PAGE_WRITECOPY | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01

TH32CS_SNAPPROCESS = 0x00000002
GAME_EXE_NAMES = ("ts3.exe", "ts3w.exe")

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wt.DWORD),
        ("PartitionId", wt.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


_k32.OpenProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.CloseHandle.argtypes = [wt.HANDLE]
_k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                    ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
_k32.VirtualQueryEx.restype = ctypes.c_size_t
_k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p,
                                ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
_k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
_k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
_k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]

STILL_ACTIVE = 259


class ProcessError(OSError):
    pass


def find_pid(names: tuple[str, ...] = GAME_EXE_NAMES) -> int | None:
    snap = _k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (None, wt.HANDLE(-1).value):
        raise ProcessError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in names:
                return int(entry.th32ProcessID)
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return None


@dataclass
class Region:
    base: int
    size: int
    protect: int
    type: int


class Process:
    def __init__(self, pid: int, write: bool = True):
        access = PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
        if write:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION
        self.pid = pid
        self.handle = _k32.OpenProcess(access, False, pid)
        if not self.handle:
            raise ProcessError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")

    def close(self) -> None:
        if self.handle:
            _k32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "Process":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def alive(self) -> bool:
        code = wt.DWORD()
        return bool(_k32.GetExitCodeProcess(self.handle, ctypes.byref(code))) and code.value == STILL_ACTIVE

    def read(self, addr: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        if not _k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)) \
                or got.value != size:
            raise ProcessError(ctypes.get_last_error(), f"ReadProcessMemory(0x{addr:X}, {size}) failed")
        return buf.raw

    def write(self, addr: int, data: bytes) -> None:
        got = ctypes.c_size_t()
        if not _k32.WriteProcessMemory(self.handle, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got)) \
                or got.value != len(data):
            raise ProcessError(ctypes.get_last_error(), f"WriteProcessMemory(0x{addr:X}, {len(data)}) failed")

    def regions(self, readwrite_only: bool = False) -> Iterator[Region]:
        mbi = MEMORY_BASIC_INFORMATION()
        addr = 0
        limit = 0xFFFF0000  # the game is 32-bit (WOW64): user space ends below 4 GiB
        while addr < limit:
            if not _k32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            base = mbi.BaseAddress or 0
            size = mbi.RegionSize
            readable = (mbi.State == MEM_COMMIT and not (mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS))
                        and mbi.Protect != 0)
            # Mono's GC heap is PAGE_EXECUTE_READWRITE, so accept any writable page.
            if readable and (not readwrite_only or mbi.Protect & WRITABLE):
                yield Region(base, size, mbi.Protect, mbi.Type)
            addr = base + size
            if size == 0:
                break

    def scan(self, needle: bytes, readwrite_only: bool = False, chunk: int = 4 << 20) -> Iterator[int]:
        """Yield addresses of every occurrence of needle in readable memory."""
        overlap = len(needle) - 1
        for r in self.regions(readwrite_only):
            off = 0
            while off < r.size:
                n = min(chunk, r.size - off)
                try:
                    data = self.read(r.base + off, n + (overlap if off + n < r.size else 0))
                except ProcessError:
                    break
                i = data.find(needle)
                while i != -1:
                    if i < n:  # hits in the overlap are reported by the next chunk
                        yield r.base + off + i
                    i = data.find(needle, i + 1)
                off += n
